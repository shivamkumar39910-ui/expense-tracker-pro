"""
CASH-FLOW CALENDAR & BALANCE RUNWAY ENGINE (cashflow_calendar_service.py)
Expense Tracker Pro 2.0 - Automation & Real-World Financial Intelligence

Supports:
1. Day-by-day calendar timeline across the current month.
2. Clear distinction of data layers:
   - ACTUAL: Verified past transactions.
   - COMMITTED: Scheduled recurring bills and fixed obligations.
   - PROJECTED: Discretionary spend trajectory based on velocity.
3. Liquid Balance Runway:
   - Starts with current actual liquid accounts balance.
   - Traverses each day of the month applying actuals (past) and committed+projected (future).
4. Low Balance Warning:
   - Generates deterministic warning if projected balance falls below safety threshold (e.g. Rs. 2,000 or negative).
"""

import calendar
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple
import db_engine
import forecasting_engine

def to_decimal(val) -> Decimal:
    if val is None:
        return Decimal("0.00")
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

def get_cashflow_calendar(
    user_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db_path: str = "expenses.db",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Computes a daily cash-flow calendar and projected balance trajectory for the requested month.
    """
    today = date.today()
    if isinstance(year, str) and "-" in year:
        start_date = year
        if isinstance(month, str) and "-" in month:
            end_date = month
        year = None
        month = None

    if start_date:
        try:
            dt = datetime.strptime(start_date, "%Y-%m-%d")
            year = dt.year
            month = dt.month
        except Exception:
            pass

    cur_year = int(year) if year else today.year
    cur_month = int(month) if month else today.month
    total_days = calendar.monthrange(cur_year, cur_month)[1]



    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 1. Total Current Liquid Balance (Cash, Bank, Savings)
        cursor.execute("""
            SELECT COALESCE(SUM(current_balance), 0.0) as liquid_balance
            FROM accounts
            WHERE user_id = ? AND is_active = 1 AND account_type IN ('CASH', 'BANK', 'SAVINGS', 'WALLET')
        """, (user_id,))
        row = cursor.fetchone()
        liquid_balance = to_decimal(row["liquid_balance"] if row else 0.0)

        # 2. Fetch all actual transactions for this month
        month_pattern = f"{cur_year:04d}-{cur_month:02d}%"
        cursor.execute("""
            SELECT id, date, amount, transaction_type, note, category_id
            FROM transactions
            WHERE user_id = ? AND date LIKE ? AND amount > 0
            ORDER BY date ASC
        """, (user_id, month_pattern))
        tx_rows = cursor.fetchall()

        actuals_by_day: Dict[int, List[Dict[str, Any]]] = {}
        for r in tx_rows:
            try:
                d_day = int(r["date"].split("-")[2])
            except Exception:
                continue
            if d_day not in actuals_by_day:
                actuals_by_day[d_day] = []
            actuals_by_day[d_day].append({
                "id": r["id"],
                "type": r["transaction_type"],
                "amount": float(to_decimal(r["amount"])),
                "note": r["note"]
            })

        # 3. Fetch active recurring bills
        cursor.execute("""
            SELECT id, title, amount, frequency, due_day, next_due_date
            FROM recurring_bills
            WHERE user_id = ? AND is_active = 1
        """, (user_id,))
        bills = cursor.fetchall()

        committed_by_day: Dict[int, List[Dict[str, Any]]] = {}
        for b in bills:
            due_day = int(b["due_day"]) if b["due_day"] else 1
            if 1 <= due_day <= total_days:
                if due_day not in committed_by_day:
                    committed_by_day[due_day] = []
                committed_by_day[due_day].append({
                    "id": b["id"],
                    "title": b["title"],
                    "amount": float(to_decimal(b["amount"])),
                    "type": "RECURRING_BILL"
                })

        # 4. Get Daily Velocity from Forecast Engine
        fc = forecasting_engine.calculate_month_end_forecast(
            user_id, target_date=f"{cur_year:04d}-{cur_month:02d}-{min(today.day, total_days):02d}", db_path=db_path
        )
        daily_velocity = to_decimal(fc.get("daily_spending_velocity", 0.0))

        # 5. Build Timeline
        days_timeline = []
        running_projected_balance = liquid_balance
        low_balance_warnings = []
        safety_threshold = Decimal("2000.00")

        eval_day = today.day if (cur_year == today.year and cur_month == today.month) else total_days

        for day in range(1, total_days + 1):
            date_str = f"{cur_year:04d}-{cur_month:02d}-{day:02d}"
            day_actuals = actuals_by_day.get(day, [])
            day_committed = committed_by_day.get(day, [])

            actual_expense = sum(t["amount"] for t in day_actuals if t["type"] == "EXPENSE")
            actual_income = sum(t["amount"] for t in day_actuals if t["type"] == "INCOME")
            committed_expense = sum(b["amount"] for b in day_committed)

            is_past = day <= eval_day
            is_today = day == eval_day and (cur_year == today.year and cur_month == today.month)

            if is_past:
                # Past day: balance updated via actuals
                status = "ACTUAL"
                projected_spend = 0.0
            else:
                # Future day: balance projected via committed bills + discretionary velocity
                status = "PROJECTED"
                projected_spend = float(daily_velocity)
                running_projected_balance -= (to_decimal(committed_expense) + daily_velocity)

                # Check low balance trigger
                if running_projected_balance < safety_threshold:
                    low_balance_warnings.append({
                        "date": date_str,
                        "day": day,
                        "projected_balance": float(running_projected_balance),
                        "warning": f"Projected liquid balance drops to Rs.{running_projected_balance:.2f} on {date_str} (below safety threshold of Rs.{safety_threshold:.2f})."
                    })

            days_timeline.append({
                "day": day,
                "date": date_str,
                "is_past": is_past,
                "is_today": is_today,
                "status": status,
                "actual_expense": actual_expense,
                "actual_income": actual_income,
                "committed_expense": committed_expense,
                "projected_discretionary_spend": projected_spend,
                "projected_balance": float(running_projected_balance),
                "actual_items": day_actuals,
                "committed_items": day_committed
            })

        balances = [d["projected_balance"] for d in days_timeline]
        lowest_bal = min(balances) if balances else float(liquid_balance)
        lowest_day = next((d["date"] for d in days_timeline if d["projected_balance"] == lowest_bal), "")
        liquidity_status = "LOW_BALANCE_RISK" if (len(low_balance_warnings) > 0 or lowest_bal < float(safety_threshold)) else "HEALTHY"

        return {
            "success": True,
            "user_id": user_id,
            "year": cur_year,
            "month": cur_month,
            "starting_liquid_balance": float(liquid_balance),
            "lowest_projected_balance": lowest_bal,
            "lowest_balance_date": lowest_day,
            "liquidity_status": liquidity_status,
            "runway_days_remaining": len(days_timeline) - today.day if cur_month == today.month else len(days_timeline),
            "end_of_month_projected_balance": float(running_projected_balance),
            "safety_threshold": float(safety_threshold),
            "has_low_balance_risk": len(low_balance_warnings) > 0,
            "low_balance_warnings": low_balance_warnings,
            "daily_timeline": days_timeline,
            "days_timeline": days_timeline
        }

    finally:
        conn.close()
