import sqlite3
import calendar
from datetime import datetime, date
import db_engine

def get_days_in_month(year, month):
    return calendar.monthrange(year, month)[1]

def calculate_month_end_forecast(user_id, target_date=None, db_path="expenses.db"):
    """
    DETERMINISTIC PERSONAL EXPENSE FORECASTING ENGINE
    Formula:
      1. Baseline WMA (past 3 months): B = 0.50 * M1 + 0.30 * M2 + 0.20 * M3
      2. Run-rate Velocity: V = (Spend_MTD / Days_Elapsed) * Total_Days
      3. Recurring Bills Overlay: R_unpaid = Sum of recurring bills due after today this month
      4. Early-month smoothing alpha: alpha = Days_Elapsed / Total_Days
      5. Final Forecast: F = (alpha * V) + ((1 - alpha) * B) + R_unpaid
    """
    if target_date is None:
        today = date.today()
    elif isinstance(target_date, str):
        today = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        today = target_date

    current_year = today.year
    current_month = today.month
    current_day = today.day
    total_days = get_days_in_month(current_year, current_month)

    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()


    # 1. Month-to-Date (MTD) Actual Expense Spend (EXCLUDING TRANSFERS & INCOMES)
    month_pattern = f"{current_year:04d}-{current_month:02d}%"
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0.0) as mtd_spend
        FROM transactions
        WHERE user_id = ? AND transaction_type = 'EXPENSE' AND date LIKE ? AND date <= ?
    """, (user_id, month_pattern, today.strftime("%Y-%m-%d")))
    mtd_spend = float(cursor.fetchone()["mtd_spend"])

    # Category-wise MTD Spend
    cursor.execute("""
        SELECT c.name as category_name, COALESCE(SUM(t.amount), 0.0) as spend
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ? AND t.date <= ?
        GROUP BY c.name
    """, (user_id, month_pattern, today.strftime("%Y-%m-%d")))
    category_mtd = {r["category_name"] or "Others": float(r["spend"]) for r in cursor.fetchall()}

    # 2. Historical Past 3 Months Actual Expense Totals (WMA Baseline)
    past_months_totals = []
    y, m = current_year, current_month
    for _ in range(3):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        p_pattern = f"{y:04d}-{m:02d}%"
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0.0) as spend
            FROM transactions
            WHERE user_id = ? AND transaction_type = 'EXPENSE' AND date LIKE ?
        """, (user_id, p_pattern))
        past_months_totals.append(float(cursor.fetchone()["spend"]))

    # Weights for past 3 months (most recent to oldest)
    # If no past history, fallback to current velocity
    if sum(past_months_totals) > 0:
        w1, w2, w3 = 0.50, 0.30, 0.20
        baseline_wma = (w1 * past_months_totals[0]) + (w2 * past_months_totals[1]) + (w3 * past_months_totals[2])
    else:
        baseline_wma = mtd_spend * (total_days / max(1, current_day))

    # 3. Velocity / Run-rate
    days_elapsed = max(1, current_day)
    daily_velocity = mtd_spend / days_elapsed
    projected_velocity_spend = daily_velocity * total_days

    # 4. Unpaid Recurring Bills for the remainder of this month
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0.0) as unpaid_bills
        FROM recurring_bills
        WHERE user_id = ? AND is_active = 1 AND due_day > ? AND due_day <= ?
    """, (user_id, current_day, total_days))
    unpaid_bills = float(cursor.fetchone()["unpaid_bills"])

    # 5. Combined Forecast Formula
    alpha = min(1.0, max(0.1, days_elapsed / total_days))
    final_forecast = (alpha * projected_velocity_spend) + ((1.0 - alpha) * baseline_wma) + (unpaid_bills * (1.0 - alpha))
    final_forecast = max(mtd_spend, round(final_forecast, 2))

    # 6. Budget Status & Predictive Warning Alert
    cursor.execute("""
        SELECT amount FROM budgets
        WHERE user_id = ? AND month = ? AND year = ? AND (category_id IS NULL OR category_id = 0)
        LIMIT 1
    """, (user_id, current_month, current_year))
    budget_row = cursor.fetchone()
    monthly_budget = float(budget_row["amount"]) if budget_row else 0.0

    risk_status = "SAFE" # SAFE, WARNING, DANGER, NO_BUDGET
    warning_message = "Your spending velocity is healthy and well within limits."
    overrun_amount = 0.0

    if monthly_budget > 0:
        projected_utilization_pct = round((final_forecast / monthly_budget) * 100, 1)
        if final_forecast > monthly_budget:
            overrun_amount = round(final_forecast - monthly_budget, 2)
            risk_status = "DANGER"
            warning_message = (
                f"ALERT: At your current pace (₹{daily_velocity:.1f}/day), you are projected to exceed your "
                f"monthly budget by ₹{overrun_amount:.2f} ({projected_utilization_pct}% of budget)!"
            )
        elif projected_utilization_pct >= 85:
            risk_status = "WARNING"
            warning_message = (
                f"CAUTION: You are on track to consume {projected_utilization_pct}% of your budget. "
                f"Recommended daily spending cap for remainder of month: ₹{max(0.0, (monthly_budget - mtd_spend) / max(1, total_days - current_day)):.1f}/day."
            )
        else:
            risk_status = "SAFE"
            warning_message = f"On track! Projected to finish month using {projected_utilization_pct}% of budget."
    else:
        projected_utilization_pct = 0.0
        risk_status = "NO_BUDGET"
        warning_message = "No monthly budget set yet. Set a budget to enable real-time overrun warnings!"

    # 7. Category-level projection
    category_forecasts = []
    for cat_name, c_spend in category_mtd.items():
        c_proj = (c_spend / days_elapsed) * total_days
        category_forecasts.append({
            "category": cat_name,
            "mtd_spend": round(c_spend, 2),
            "projected_month_end": round(c_proj, 2),
            "pct_of_projected_total": round((c_proj / max(1.0, final_forecast)) * 100, 1)
        })
    category_forecasts.sort(key=lambda x: x["projected_month_end"], reverse=True)

    conn.close()

    return {
        "current_date": today.strftime("%Y-%m-%d"),
        "days_elapsed": days_elapsed,
        "total_days_in_month": total_days,
        "days_remaining": total_days - current_day,
        "mtd_actual_spend": round(mtd_spend, 2),
        "daily_spending_velocity": round(daily_velocity, 2),
        "baseline_wma_history": round(baseline_wma, 2),
        "unpaid_recurring_bills": round(unpaid_bills, 2),
        "projected_month_end_spend": round(final_forecast, 2),
        "monthly_budget": round(monthly_budget, 2),
        "projected_budget_utilization_pct": projected_utilization_pct,
        "risk_status": risk_status,
        "overrun_amount": overrun_amount,
        "warning_message": warning_message,
        "category_forecasts": category_forecasts
    }

def detect_spending_anomalies(user_id, db_path="expenses.db"):
    """
    Detects statistical anomalies across categories using standard deviation (mean + 2*sigma).
    Returns alerts for categories exceeding normal spending behavior.
    """
    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get average and std dev per category over transactions
    cursor.execute("""
        SELECT COALESCE(c.name, 'Others') as category_name,
               AVG(t.amount) as avg_amount,
               COUNT(t.id) as tx_count,
               MAX(t.amount) as max_amount
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE'
        GROUP BY c.name
        HAVING COUNT(t.id) >= 2
    """, (user_id,))
    stats = cursor.fetchall()

    anomalies = []
    for s in stats:
        cat = s["category_name"]
        avg = s["avg_amount"]
        # Fetch individual amounts to compute variance & standard deviation
        cursor.execute("""
            SELECT t.amount, t.date, t.note
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND COALESCE(c.name, 'Others') = ?
        """, (user_id, cat))
        amounts = [r["amount"] for r in cursor.fetchall()]
        if len(amounts) >= 3:
            variance = sum((x - avg) ** 2 for x in amounts) / len(amounts)
            std_dev = variance ** 0.5
            threshold = avg + (1.75 * std_dev)

            # Check recent transactions exceeding threshold
            for r in cursor.execute("""
                SELECT t.id, t.amount, t.date, t.note
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND COALESCE(c.name, 'Others') = ?
                AND t.amount > ?
                ORDER BY t.date DESC LIMIT 3
            """, (user_id, cat, threshold)).fetchall():
                anomalies.append({
                    "transaction_id": r["id"],
                    "category": cat,
                    "amount": r["amount"],
                    "date": r["date"],
                    "note": r["note"],
                    "normal_average": round(avg, 2),
                    "deviation_pct": round(((r["amount"] - avg) / avg) * 100, 1),
                    "alert": f"Unusual spend: ₹{r['amount']} in {cat} is {round(((r['amount'] - avg) / avg) * 100)}% above your average (₹{avg:.1f})."
                })

    conn.close()
    return anomalies
