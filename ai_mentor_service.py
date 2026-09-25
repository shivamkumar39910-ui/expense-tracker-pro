import os
import sqlite3
import calendar
from datetime import datetime, date
import forecasting_engine
import database

def get_mom_analysis(user_id, target_date=None, db_path="expenses.db"):
    """
    Computes Month-over-Month (MoM) spending comparison by category.
    TRANSFERS ARE STRICTLY EXCLUDED.
    """
    if target_date is None:
        today = date.today()
    elif isinstance(target_date, str):
        today = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        today = target_date

    cur_year = today.year
    cur_month = today.month

    # Previous Month
    prev_month = cur_month - 1
    prev_year = cur_year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1

    cur_pattern = f"{cur_year:04d}-{cur_month:02d}%"
    prev_pattern = f"{prev_year:04d}-{prev_month:02d}%"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Current Month Total
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0.0) as total, COUNT(id) as count
        FROM transactions
        WHERE user_id = ? AND transaction_type = 'EXPENSE' AND date LIKE ?
    """, (user_id, cur_pattern))
    cur_row = cursor.fetchone()
    cur_total = float(cur_row["total"])
    cur_count = int(cur_row["count"])

    # Previous Month Total
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0.0) as total, COUNT(id) as count
        FROM transactions
        WHERE user_id = ? AND transaction_type = 'EXPENSE' AND date LIKE ?
    """, (user_id, prev_pattern))
    prev_row = cursor.fetchone()
    prev_total = float(prev_row["total"])
    prev_count = int(prev_row["count"])

    # Overall MoM Change
    if prev_total > 0:
        overall_change_pct = round(((cur_total - prev_total) / prev_total) * 100, 1)
    else:
        overall_change_pct = 0.0

    # Category Breakdown
    cursor.execute("""
        SELECT c.id, c.name, c.icon, c.color_hex,
               COALESCE(SUM(t.amount), 0.0) as spend
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        GROUP BY c.id
    """, (user_id, cur_pattern))
    cur_cats = {r["id"]: dict(r) for r in cursor.fetchall()}

    cursor.execute("""
        SELECT c.id, COALESCE(SUM(t.amount), 0.0) as spend
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        GROUP BY c.id
    """, (user_id, prev_pattern))
    prev_cats = {r["id"]: float(r["spend"]) for r in cursor.fetchall()}

    categories_mom = []
    highest_cat = None
    highest_amt = 0.0

    for cid, cdata in cur_cats.items():
        c_amt = cdata["spend"]
        p_amt = prev_cats.get(cid, 0.0)
        diff = round(c_amt - p_amt, 2)
        pct = round(((c_amt - p_amt) / p_amt * 100), 1) if p_amt > 0 else 100.0

        if c_amt > highest_amt:
            highest_amt = c_amt
            highest_cat = cdata["name"]

        categories_mom.append({
            "category_id": cid,
            "category_name": cdata["name"],
            "icon": cdata["icon"],
            "color": cdata["color_hex"],
            "current_spend": round(c_amt, 2),
            "previous_spend": round(p_amt, 2),
            "diff": diff,
            "pct_change": pct,
            "is_increase": diff > 0
        })

    categories_mom.sort(key=lambda x: x["current_spend"], reverse=True)
    conn.close()

    return {
        "current_month_total": round(cur_total, 2),
        "previous_month_total": round(prev_total, 2),
        "overall_change_pct": overall_change_pct,
        "is_increase": cur_total > prev_total,
        "current_count": cur_count,
        "previous_count": prev_count,
        "highest_category": highest_cat or "None",
        "highest_category_amount": round(highest_amt, 2),
        "categories_mom": categories_mom
    }

def get_six_month_trends(user_id, db_path="expenses.db"):
    """
    Returns last 6 months of historical Incomes vs Expenses.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    today = date.today()
    trends = []

    y, m = today.year, today.month
    months_list = []
    for _ in range(6):
        months_list.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months_list.reverse()

    for y, m in months_list:
        month_label = calendar.month_abbr[m]
        pattern = f"{y:04d}-{m:02d}%"

        cursor.execute("""
            SELECT transaction_type, COALESCE(SUM(amount), 0.0) as total
            FROM transactions
            WHERE user_id = ? AND date LIKE ?
            GROUP BY transaction_type
        """, (user_id, pattern))
        rows = cursor.fetchall()
        inc = 0.0
        exp = 0.0
        for r in rows:
            if r["transaction_type"] == 'INCOME':
                inc = float(r["total"])
            elif r["transaction_type"] == 'EXPENSE':
                exp = float(r["total"])

        trends.append({
            "label": f"{month_label} {y % 100}",
            "month": m,
            "year": y,
            "income": round(inc, 2),
            "expense": round(exp, 2),
            "net_savings": round(inc - exp, 2)
        })

    conn.close()
    return trends

def generate_ai_mentor_advice(user_id, user_prompt=None, db_path="expenses.db"):
    """
    AI FINANCIAL MENTOR ENGINE
    Strict Principle: The mentor is an EXPLANATION LAYER over deterministic forecast math.
    Zero hallucination on numbers; empathetic, actionable coaching in response.
    """
    forecast = forecasting_engine.calculate_month_end_forecast(user_id, db_path=db_path)
    anomalies = forecasting_engine.detect_spending_anomalies(user_id, db_path=db_path)
    mom = get_mom_analysis(user_id, db_path=db_path)
    net_worth = database.get_net_worth_summary(user_id)

    cur_spend = forecast["mtd_actual_spend"]
    daily_velocity = forecast["daily_spending_velocity"]
    proj_spend = forecast["projected_month_end_spend"]
    budget = forecast["monthly_budget"]
    risk = forecast["risk_status"]
    days_left = forecast["days_remaining"]

    # Construct contextual, empathetic advice
    insights = []
    action_steps = []

    # 1. Pacing & Budget Coaching
    if budget > 0:
        if risk == "DANGER":
            overrun = forecast["overrun_amount"]
            insights.append(
                f"🚨 **Budget Alert**: At your current pace of ₹{daily_velocity:.1f}/day, you are on track to overspend by **₹{overrun:,.2f}** "
                f"({forecast['projected_budget_utilization_pct']}% of your ₹{budget:,.2f} budget)."
            )
            safe_cap = max(0.0, (budget - cur_spend) / max(1, days_left))
            action_steps.append(f"Cap non-essential daily spending to **₹{safe_cap:.1f}/day** for the remaining {days_left} days to avoid budget overrun.")
        elif risk == "WARNING":
            insights.append(
                f"⚠️ **Caution**: You've utilized a significant portion of your budget. Your projected month-end spend is ₹{proj_spend:,.2f} "
                f"({forecast['projected_budget_utilization_pct']}% of budget)."
            )
            safe_cap = max(0.0, (budget - cur_spend) / max(1, days_left))
            action_steps.append(f"Aim for a daily cap of **₹{safe_cap:.1f}/day** to keep a comfortable savings buffer.")
        else:
            insights.append(
                f"✅ **Healthy Pacing**: You are managing your finances well! At ₹{daily_velocity:.1f}/day, your projected month-end spend is "
                f"**₹{proj_spend:,.2f}**, which will leave you with **₹{max(0.0, budget - proj_spend):,.2f}** in surplus savings."
            )
            action_steps.append("Consider allocating this projected surplus towards your Emergency Fund or high-interest investments.")
    else:
        insights.append(
            f"📊 You have spent ₹{cur_spend:,.2f} so far this month at a velocity of ₹{daily_velocity:.1f}/day. "
            f"Projected month-end spend is ₹{proj_spend:,.2f}."
        )
        action_steps.append("Set a monthly budget cap in the 'Budgets' tab to enable automatic overrun warnings and daily safe pacing.")

    # 2. Category Concentration & MoM Trend
    if mom["highest_category"] != "None" and cur_spend > 0:
        highest_pct = round((mom["highest_category_amount"] / cur_spend) * 100, 1)
        if highest_pct >= 30:
            insights.append(
                f"🔍 **High Concentration**: **{mom['highest_category']}** accounts for **{highest_pct}%** of your total spending (₹{mom['highest_category_amount']:,.2f})."
            )
            save_est = round(mom["highest_category_amount"] * 0.15, 2)
            action_steps.append(f"Trimming 15% from {mom['highest_category']} could save you approx. **₹{save_est:,.2f}** this month.")

    # 3. Anomaly Coaching
    if anomalies:
        top_anomaly = anomalies[0]
        insights.append(
            f"⚡ **Unusual Spend Detected**: {top_anomaly['alert']}"
        )
        action_steps.append(f"Review recent transactions in '{top_anomaly['category']}' to ensure no duplicate or erroneous charges.")

    # Specific response if user asked a question
    user_q = (user_prompt or "").strip().lower()
    answer_text = ""
    if "afford" in user_q:
        # Check liquidity & projected runway
        avail_cash = net_worth["total_assets"]
        remaining_budget = max(0.0, budget - proj_spend) if budget > 0 else avail_cash
        answer_text = (
            f"Regarding your affordability query: You currently have ₹{avail_cash:,.2f} across your liquid accounts. "
            f"After accounting for your projected month-end expenses (₹{proj_spend:,.2f}), your estimated discretionary cushion is ₹{remaining_budget:,.2f}."
        )
    elif "save" in user_q or "cut" in user_q:
        answer_text = (
            f"To maximize savings this month: Focus on your top spending category **{mom['highest_category']}** (₹{mom['highest_category_amount']:,.2f}). "
            f"Also, reducing your daily velocity from ₹{daily_velocity:.1f}/day down to ₹{daily_velocity * 0.8:.1f}/day will save you ~₹{(daily_velocity * 0.2 * days_left):,.2f} over the remaining {days_left} days."
        )
    else:
        answer_text = (
            "Here is your personalized Financial Mentor assessment based on your deterministic numbers, run-rate velocity, and historical patterns:"
        )

    return {
        "reply": answer_text,
        "insights": insights,
        "action_steps": action_steps,
        "metrics_snapshot": {
            "net_worth": net_worth["net_worth"],
            "daily_velocity": daily_velocity,
            "projected_month_end": proj_spend,
            "monthly_budget": budget,
            "risk_status": risk,
            "highest_category": mom["highest_category"]
        }
    }
