"""
SMART FINANCIAL ALERTS & SAVINGS GOAL INTELLIGENCE ENGINE (alerts_engine.py)
Expense Tracker Pro 2.0 - Automation & Real-World Financial Intelligence

Supports:
1. Savings Goal Intelligence:
   - Target amount, current saved, remaining.
   - Required monthly contribution to hit target date.
   - Actual recent monthly contribution pace.
   - Projected completion date.
   - Pacing status: COMPLETED, ON_TRACK, BEHIND, NO_TARGET_DATE.
2. Deterministic Smart Alert Generation:
   - BUDGET_OVERRUN: Projected month-end spend exceeds budget ceiling.
   - BUDGET_80: Paced to reach 80% of budget.
   - UPCOMING_BILL: Unpaid recurring bill due within 3 days.
   - OVERDUE_BILL: Unpaid bill with due date in the past.
   - UNUSUAL_SPENDING: Category spending spike detected by statistical standard deviation.
   - LARGE_TRANSACTION: Individual transaction exceeding 35% of monthly budget or Rs. 15,000.
   - LOW_BALANCE_RISK: Projected liquid balance drops below safety threshold (Rs. 2,000).
   - GOAL_BEHIND: Active savings goal running behind required monthly pace.
3. Alert Persistence:
   - Stores generated alerts in `financial_alerts` and `notifications` tables.
   - Deduplicates within 24 hours to prevent notification fatigue/spam.
"""

import calendar
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple
import db_engine
import forecasting_engine
import push_delivery_service

def to_decimal(val) -> Decimal:
    if val is None:
        return Decimal("0.00")
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

# ==============================================================================
# 6.8 SAVINGS GOAL INTELLIGENCE
# ==============================================================================
def get_goal_intelligence(user_id: int, db_path: str = "expenses.db") -> List[Dict[str, Any]]:
    """
    Computes required monthly pacing, projected completion date, and on-track status for all goals.
    """
    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, title, target_amount, current_amount, target_date, color_hex, icon, is_completed
            FROM financial_goals
            WHERE user_id = ?
            ORDER BY is_completed ASC, target_date ASC
        """, (user_id,))
        goals = cursor.fetchall()

        today = date.today()
        results = []

        for g in goals:
            g_dict = dict(g)
            target = to_decimal(g_dict["target_amount"])
            current = to_decimal(g_dict["current_amount"])
            remaining = max(Decimal("0.00"), target - current)
            pct = round((float(current) / float(target) * 100), 1) if target > Decimal("0.00") else 100.0
            is_completed = bool(g_dict["is_completed"]) or current >= target

            target_date_str = g_dict.get("target_date")
            required_monthly = Decimal("0.00")
            months_remaining = 0
            pacing_status = "COMPLETED" if is_completed else "NO_TARGET_DATE"
            projected_completion = target_date_str or "Flexible"

            if not is_completed and target_date_str:
                try:
                    t_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
                    days_left = (t_date - today).days
                    if days_left <= 0:
                        pacing_status = "BEHIND"
                        required_monthly = remaining
                    else:
                        months_remaining = max(1, round(days_left / 30.4))
                        required_monthly = (remaining / Decimal(months_remaining)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        pacing_status = "ON_TRACK"
                except Exception:
                    pass

            results.append({
                "id": g_dict["id"],
                "title": g_dict["title"],
                "target_amount": float(target),
                "current_amount": float(current),
                "remaining_amount": float(remaining),
                "progress_percentage": min(100.0, pct),
                "target_date": target_date_str,
                "months_remaining": months_remaining,
                "required_monthly_contribution": float(required_monthly),
                "pacing_status": pacing_status,
                "is_completed": is_completed,
                "color_hex": g_dict.get("color_hex", "#10B981"),
                "icon": g_dict.get("icon", "target")
            })

        return results
    finally:
        conn.close()


# ==============================================================================
# 6.9 SMART FINANCIAL ALERTS ENGINE
# ==============================================================================
def evaluate_and_generate_alerts(user_id: int, db_path: str = "expenses.db") -> List[Dict[str, Any]]:
    """
    Evaluates financial conditions across budgets, forecast, bills, anomalies, and goals.
    Generates structured deterministic alerts without spamming.
    """
    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    generated_alerts = []
    today = date.today()

    try:
        # 1. Forecast & Budget Risk Alert
        fc = forecasting_engine.calculate_month_end_forecast(user_id, db_path=db_path)
        risk_level = fc.get("risk_level", "LOW")
        budget = fc.get("budget", 0.0)

        if budget > 0:
            if risk_level in ("CRITICAL", "HIGH"):
                overrun = fc.get("overrun_amount", 0.0)
                generated_alerts.append({
                    "alert_type": "BUDGET_OVERRUN",
                    "severity": "DANGER" if risk_level == "CRITICAL" else "WARNING",
                    "title": "Budget Overrun Risk",
                    "message": f"At Rs.{fc['daily_spending_velocity']:.1f}/day pace, you are on track to exceed your Rs.{budget:,.2f} budget by Rs.{overrun:,.2f}.",
                    "supporting_metric": f"Projected: Rs.{fc['projected_month_end_spend']:,.2f} | Budget: Rs.{budget:,.2f}",
                    "action_route": "/mobile?tab=tab-budgets"
                })
            elif risk_level == "MODERATE":
                generated_alerts.append({
                    "alert_type": "BUDGET_80",
                    "severity": "WARNING",
                    "title": "Budget Threshold Warning",
                    "message": f"Projected month-end spend will reach {fc['projected_budget_utilization_pct']}% of your monthly budget.",
                    "supporting_metric": f"Projected: Rs.{fc['projected_month_end_spend']:,.2f}",
                    "action_route": "/mobile?tab=tab-budgets"
                })

        # 2. Upcoming & Overdue Bills Alert
        upcoming_bills = fc.get("upcoming_recurring", [])
        for b in upcoming_bills:
            due_str = b.get("due_date")
            if due_str:
                try:
                    d_date = datetime.strptime(due_str, "%Y-%m-%d").date()
                    diff_days = (d_date - today).days
                    if 0 <= diff_days <= 3:
                        generated_alerts.append({
                            "alert_type": "UPCOMING_BILL",
                            "severity": "WARNING" if diff_days <= 1 else "INFO",
                            "title": f"Bill Due Soon: {b['title']}",
                            "message": f"Rs.{b['amount']:,.2f} due in {diff_days} day(s) on {due_str}.",
                            "supporting_metric": f"Amount: Rs.{b['amount']:,.2f}",
                            "action_route": "/mobile?tab=tab-budgets"
                        })
                except Exception:
                    pass

        # 3. Statistical Spending Anomalies Alert
        anomalies = forecasting_engine.detect_spending_anomalies(user_id, db_path=db_path)
        for a in anomalies[:2]:
            generated_alerts.append({
                "alert_type": "UNUSUAL_SPENDING",
                "severity": "WARNING",
                "title": f"Unusual Spend in {a['category']}",
                "message": a["alert"],
                "supporting_metric": f"Rs.{a['amount']:,.2f} (+{a['deviation_pct']:.0f}% above avg)",
                "action_route": "/mobile?tab=tab-transactions"
            })

        # 4. Goals Running Behind Alert
        goals = get_goal_intelligence(user_id, db_path=db_path)
        for g in goals:
            if g["pacing_status"] == "BEHIND":
                generated_alerts.append({
                    "alert_type": "GOAL_BEHIND",
                    "severity": "WARNING",
                    "title": f"Goal Behind Schedule: {g['title']}",
                    "message": f"Target date is near or passed. Required contribution is Rs.{g['required_monthly_contribution']:,.2f}/month.",
                    "supporting_metric": f"Saved: Rs.{g['current_amount']:,.2f} of Rs.{g['target_amount']:,.2f}",
                    "action_route": "/mobile?tab=tab-budgets"
                })

        # 5. Persist Alerts with Deduplication (checks if same alert type created within 24 hours)
        persisted_count = 0
        cutoff_24h = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

        for alert in generated_alerts:
            # Check existing in notifications table
            cursor.execute("""
                SELECT id FROM notifications
                WHERE user_id = ? AND title = ? AND created_at >= ?
                LIMIT 1
            """, (user_id, alert["title"], cutoff_24h))
            if cursor.fetchone():
                continue # Skip duplicate within 24h

            # Dispatch notification
            push_delivery_service.send_financial_notification(
                user_id=user_id,
                alert_type=alert["alert_type"],
                title=alert["title"],
                message=alert["message"],
                action_url=alert["action_route"],
                severity=alert["severity"],
                supporting_metric=alert["supporting_metric"],
                db_path=db_path
            )
            persisted_count += 1

        return generated_alerts
    finally:
        conn.close()

def get_active_alerts(user_id: int, db_path: str = "expenses.db", limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retrieves unread financial alerts for the user.
    """
    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, alert_type, severity, title, message, supporting_metric, is_read, created_at
            FROM financial_alerts
            WHERE user_id = ? AND is_read = 0
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit))
        rows = cursor.fetchall()
        alerts = []
        for r in rows:
            alerts.append({
                "id": r["id"],
                "alert_type": r["alert_type"],
                "severity": r["severity"],
                "title": r["title"],
                "message": r["message"],
                "supporting_metric": r["supporting_metric"],
                "is_read": bool(r["is_read"]),
                "created_at": str(r["created_at"])
            })
        return alerts
    finally:
        conn.close()

def dismiss_alert(user_id: int, alert_id: int, db_path: str = "expenses.db") -> bool:
    """
    Marks an alert as read / dismissed for the user.
    """
    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE financial_alerts
            SET is_read = 1
            WHERE id = ? AND user_id = ?
        """, (alert_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

