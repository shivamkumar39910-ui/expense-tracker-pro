"""
AI FINANCIAL MENTOR 2.0 SERVICE (ai_mentor_service.py)
Expense Tracker Pro 2.0 - Automation & Real-World Financial Intelligence

Principles:
1. Pure explanation layer over deterministic mathematical models (Forecast Engine 2.0, Cash Flow, Alerts).
2. Four-Pillar Explainable Framework:
   - WHAT HAPPENED: Verifiable historical & MTD activity facts.
   - WHY IT MATTERS: Impact on monthly budget utilization and financial cushion.
   - WHAT MAY HAPPEN: Forecasted trajectory and upcoming committed obligations.
   - WHAT USER CAN DO: Concrete, mathematically grounded daily pacing actions.
3. Zero Hallucination: Never invents numbers, phantom bills, or fake bank connections.
"""

import os
import sqlite3
import calendar
from datetime import datetime, date
from typing import Dict, Any, List, Optional
import forecasting_engine
import database
import db_engine

def get_mom_analysis(user_id: int, target_date: Optional[Any] = None, db_path: str = "expenses.db") -> Dict[str, Any]:
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

    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
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
    finally:
        conn.close()


def get_six_month_trends(user_id: int, db_path: str = "expenses.db") -> List[Dict[str, Any]]:
    """
    Returns last 6 months of historical Incomes vs Expenses.
    """
    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
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

    try:
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
        return trends
    finally:
        conn.close()


def generate_ai_mentor_advice(user_id: int, user_prompt: Optional[str] = None, db_path: str = "expenses.db") -> Dict[str, Any]:
    """
    AI FINANCIAL MENTOR 2.0
    Grounded explanation engine delivering the 4-part structure:
    1. WHAT HAPPENED: MTD spend facts, MoM category variances.
    2. WHY IT MATTERS: Forecasted budget consumption, liquidity impact.
    3. WHAT MAY HAPPEN: Projected month-end total, upcoming committed obligations.
    4. WHAT USER CAN DO: Safe daily cap, category pacing recommendations.
    """
    forecast = forecasting_engine.calculate_month_end_forecast(user_id, db_path=db_path)
    anomalies = forecasting_engine.detect_spending_anomalies(user_id, db_path=db_path)
    mom = get_mom_analysis(user_id, db_path=db_path)
    net_worth = database.get_net_worth_summary(user_id)

    cur_spend = forecast["mtd_actual_spend"]
    daily_velocity = forecast["daily_spending_velocity"]
    proj_spend = forecast["projected_month_end_spend"]
    budget = forecast["monthly_budget"]
    risk = forecast.get("risk_level", forecast["risk_status"])
    days_left = forecast["days_remaining"]
    safe_cap = forecast.get("safe_daily_spend", 0.0)

    # 1. WHAT HAPPENED
    if cur_spend > 0:
        what_happened = f"You have spent Rs.{cur_spend:,.2f} so far this month across {mom['current_count']} transaction(s)."
        if mom["highest_category"] != "None":
            what_happened += f" Your primary expenditure driver is {mom['highest_category']} at Rs.{mom['highest_category_amount']:,.2f}."
    else:
        what_happened = "No expenses recorded yet in the current month."

    # 2. WHY IT MATTERS
    if budget > 0:
        util_pct = forecast["projected_budget_utilization_pct"]
        if risk in ("CRITICAL", "HIGH", "DANGER"):
            why_it_matters = f"At your current pace of Rs.{daily_velocity:.1f}/day, you are on track to exceed your Rs.{budget:,.2f} budget by Rs.{forecast['overrun_amount']:,.2f} ({util_pct}% utilized)."
        elif risk in ("MODERATE", "WARNING"):
            why_it_matters = f"You have consumed a substantial portion of your budget ceiling ({util_pct}% projected utilization)."
        else:
            why_it_matters = f"Your spending velocity is well controlled, leaving you with an estimated Rs.{max(0.0, budget - proj_spend):,.2f} in projected savings buffer."
    else:
        why_it_matters = f"Without an active monthly budget ceiling, spending runs at Rs.{daily_velocity:.1f}/day without an automated overrun guard."

    # 3. WHAT MAY HAPPEN
    upcoming_bills = forecast.get("upcoming_recurring", [])
    upcoming_sum = forecast.get("upcoming_recurring_total", 0.0)
    what_may_happen = f"Forecast Engine projects month-end spending to reach Rs.{proj_spend:,.2f}."
    if upcoming_sum > 0:
        what_may_happen += f" This includes Rs.{upcoming_sum:,.2f} in {len(upcoming_bills)} upcoming committed bill(s) before month-end."

    # 4. WHAT USER CAN DO
    action_steps = []
    if budget > 0 and risk in ("CRITICAL", "HIGH", "DANGER", "MODERATE", "WARNING"):
        action_steps.append(f"Cap discretionary spending to Rs.{safe_cap:.1f}/day for the remaining {days_left} days.")
    if mom["highest_category"] != "None" and cur_spend > 0:
        trim_target = round(mom["highest_category_amount"] * 0.15, 2)
        action_steps.append(f"Trimming 15% from {mom['highest_category']} would preserve ~Rs.{trim_target:,.2f}.")
    if budget == 0:
        action_steps.append("Set a monthly budget cap in the Budgets tab to unlock live overrun alerts.")
    if not action_steps:
        action_steps.append("Maintain your current pace and consider allocating surplus cash towards your Savings Goals.")

    what_user_can_do = " • ".join(action_steps)

    # Contextual query response
    user_q = (user_prompt or "").strip().lower()
    if "afford" in user_q:
        avail_cash = net_worth["total_assets"]
        remaining_budget = max(0.0, budget - proj_spend) if budget > 0 else avail_cash
        reply_text = f"Regarding affordability: You have Rs.{avail_cash:,.2f} across liquid accounts. After accounting for projected month-end obligations (Rs.{proj_spend:,.2f}), your discretionary cushion is Rs.{remaining_budget:,.2f}."
    elif "save" in user_q or "cut" in user_q:
        reply_text = f"To maximize savings: Focus on {mom['highest_category']}. Lowering daily velocity by 20% saves ~Rs.{(daily_velocity * 0.2 * max(1, days_left)):,.2f} over the remaining {days_left} days."
    else:
        reply_text = f"AI Financial Mentor 2.0 Assessment:\n\n• What Happened: {what_happened}\n• Why It Matters: {why_it_matters}\n• What May Happen: {what_may_happen}\n• What You Can Do: {what_user_can_do}"

    return {
        "reply": reply_text,
        "four_pillars": {
            "what_happened": what_happened,
            "why_it_matters": why_it_matters,
            "what_may_happen": what_may_happen,
            "what_user_can_do": what_user_can_do
        },
        "insights": [what_happened, why_it_matters, what_may_happen],
        "action_steps": action_steps,
        "metrics_snapshot": {
            "net_worth": net_worth["net_worth"],
            "daily_velocity": daily_velocity,
            "projected_month_end": proj_spend,
            "monthly_budget": budget,
            "risk_status": risk,
            "safe_daily_spend": safe_cap,
            "highest_category": mom["highest_category"]
        }
    }
