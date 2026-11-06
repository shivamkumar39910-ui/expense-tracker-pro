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

    # Intelligent Bilingual Natural Language Processing (Hindi, Hinglish & English)
    user_q = (user_prompt or "").strip().lower()
    
    # Check if prompt contains Hindi/Hinglish indicators
    hindi_keywords = ["kharch", "kitna", "bacha", "kaise", "batao", "kya", "mera", "meri", "mere", "paisa", "paise", "rupaye", "kharid", "bache", "sakta", "sakti", "hai", "karna", "chahiye", "saving", "namaste", "shukriya"]
    is_hindi = any(hk in user_q for hk in hindi_keywords)

    import re
    amounts_found = re.findall(r'\b\d+(?:,\d+)*(?:\.\d+)?\b', user_q.replace(',', ''))
    parsed_amount = float(amounts_found[0]) if amounts_found else None

    avail_cash = float(net_worth.get("total_assets", 0.0) or 0.0)
    remaining_budget = max(0.0, float(budget - cur_spend)) if budget > 0 else avail_cash

    if not user_q:
        if is_hindi:
            reply_text = f"नमस्ते! मैं आपका पर्सनल AI फाइनेंशियल एडवाइज़र हूँ। आप मुझसे अपने खर्च (Expenses), बजट, बचत (Savings) या किसी भी खरीदारी के बारे में हिंदी या इंग्लिश में पूछ सकते हैं!"
        else:
            reply_text = f"Hello! I am your AI Financial Advisor. Ask me anything about your expenses, budgets, savings runway, or purchase affordability."

    elif any(k in user_q for k in ["hi", "hello", "hey", "namaste", "pranam", "kya haal"]):
        if is_hindi:
            reply_text = f"नमस्ते! मैं बिल्कुल ठीक हूँ। इस महीने आपका कुल खर्च ₹{cur_spend:,.2f} हुआ है और ₹{remaining_budget:,.2f} का बजट बचा है। मैं आपकी क्या मदद कर सकता हूँ?"
        else:
            reply_text = f"Hello! You have spent ₹{cur_spend:,.2f} so far this month, with ₹{remaining_budget:,.2f} remaining in your budget. How can I assist you with your finances today?"

    elif any(k in user_q for k in ["afford", "kharid", "buy", "purchase", "le lu", "le sakta"]):
        check_amt = parsed_amount if parsed_amount else (5000.0 if "5000" in user_q else 2000.0)
        if check_amt <= remaining_budget:
            if is_hindi:
                reply_text = f"✅ हाँ, आप ₹{check_amt:,.2f} का खर्च आसानी से कर सकते हैं!\n\n• आपका बचा हुआ बजट: ₹{remaining_budget:,.2f}\n• इस खरीदारी के बाद भी आपके पास ₹{max(0.0, remaining_budget - check_amt):,.2f} का बजट सुरक्षित रहेगा।\n• सेफ डेली लिमिट: ₹{safe_cap:.1f}/दिन।"
            else:
                reply_text = f"✅ Yes, you can comfortably afford this ₹{check_amt:,.2f} purchase!\n\n• Current remaining budget: ₹{remaining_budget:,.2f}\n• Post-purchase buffer: ₹{max(0.0, remaining_budget - check_amt):,.2f}\n• Safe daily pace: ₹{safe_cap:.1f}/day."
        else:
            if is_hindi:
                reply_text = f"⚠️ थोड़ा ध्यान दें! ₹{check_amt:,.2f} खर्च करने से आपका बजट ओवररन हो सकता है।\n\n• वर्तमान बचा हुआ बजट: ₹{remaining_budget:,.2f}\n• यह राशि आपके बचे बजट से ₹{(check_amt - remaining_budget):,.2f} अधिक है।\n• सुझाव: इसे अगले महीने प्लान करें या किसी अन्य कैटेगरी में कटौती करें।"
            else:
                reply_text = f"⚠️ Caution! A ₹{check_amt:,.2f} expense may exceed your budget ceiling.\n\n• Remaining budget: ₹{remaining_budget:,.2f}\n• Potential deficit: ₹{(check_amt - remaining_budget):,.2f}\n• Suggestion: Defer discretionary purchases or trim other categories."

    elif any(k in user_q for k in ["kharch", "spent", "spending", "total kharcha", "kitna kharcha"]):
        top_cat_info = f"सबसे ज्यादा खर्च '{mom['highest_category']}' (₹{mom['highest_category_amount']:,.2f}) में हुआ है।" if mom["highest_category"] != "None" else ""
        if is_hindi:
            reply_text = f"📊 इस महीने का खर्च सारांश:\n\n• कुल खर्च (Total Expense): ₹{cur_spend:,.2f}\n• दैनिक खर्च स्पीड (Pace): ₹{daily_velocity:.1f} प्रति दिन\n• {top_cat_info}\n• अनुमानित महीना अंत खर्च: ₹{proj_spend:,.2f}"
        else:
            reply_text = f"📊 Current Month Expense Summary:\n\n• Total Spend to date: ₹{cur_spend:,.2f}\n• Daily Velocity: ₹{daily_velocity:.1f}/day\n• Top Category: {mom['highest_category']} (₹{mom['highest_category_amount']:,.2f})\n• Projected Month-End: ₹{proj_spend:,.2f}"

    elif any(k in user_q for k in ["budget", "bacha", "remaining"]):
        if is_hindi:
            reply_text = f"🎯 आपका बजट स्टेटस:\n\n• कुल बजट: ₹{budget:,.2f}\n• खर्च हुआ: ₹{cur_spend:,.2f}\n• बचा हुआ बजट: ₹{remaining_budget:,.2f}\n• बाकी बचे दिन: {days_left} दिन\n• सेफ डेली खर्च सीमा: ₹{safe_cap:.1f} / दिन"
        else:
            reply_text = f"🎯 Monthly Budget Status:\n\n• Total Budget Ceiling: ₹{budget:,.2f}\n• MTD Actual Spend: ₹{cur_spend:,.2f}\n• Remaining Balance: ₹{remaining_budget:,.2f}\n• Days Remaining: {days_left}\n• Safe Daily Pace: ₹{safe_cap:.1f}/day"

    elif any(k in user_q for k in ["save", "saving", "bachat", "kaise bachaye", "cut"]):
        if is_hindi:
            reply_text = f"💡 बचत (Savings) बढ़ाने के आसान सुझाव:\n\n1. '{mom['highest_category']}' में 15% की कमी करके आप लगभग ₹{round(mom['highest_category_amount'] * 0.15, 2):,.2f} बचा सकते हैं।\n2. अपनी दैनिक खर्च सीमा ₹{safe_cap:.1f}/दिन के भीतर रखें।\n3. महीने के अंत में संभावित बचत: ₹{max(0.0, budget - proj_spend):,.2f}।"
        else:
            reply_text = f"💡 Actionable Savings Recommendations:\n\n1. Focus on {mom['highest_category']}: Trimming 15% saves ~₹{round(mom['highest_category_amount'] * 0.15, 2):,.2f}.\n2. Cap discretionary spending to ₹{safe_cap:.1f}/day for the remaining {days_left} days.\n3. Projected savings buffer: ₹{max(0.0, budget - proj_spend):,.2f}."

    elif any(k in user_q for k in ["forecast", "next month", "aage", "bhavishya"]):
        if is_hindi:
            reply_text = f"🔮 AI खर्च अनुमान (Forecast):\n\n• इस महीने का अनुमानित कुल खर्च: ₹{proj_spend:,.2f}\n• रिस्क स्टेटस: {risk}\n• अगर यही स्पीड रही तो अगले महीने का अनुमानित बेसलाइन खर्च: ₹{proj_spend:,.2f} के आसपास रहेगा।"
        else:
            reply_text = f"🔮 AI Predictive Forecast:\n\n• Projected Month-End Total: ₹{proj_spend:,.2f}\n• Risk Assessment: {risk}\n• Baseline Run-Rate: ₹{daily_velocity:.1f}/day across {days_left} remaining days."

    else:
        if is_hindi:
            reply_text = f"💡 आपका फाइनेंशियल ओवरव्यू:\n\n• इस महीने का कुल खर्च: ₹{cur_spend:,.2f}\n• बचा हुआ बजट: ₹{remaining_budget:,.2f}\n• सेफ डेली खर्च सीमा: ₹{safe_cap:.1f}/दिन\n\nआप किसी भी विशिष्ट खर्च या बजट के बारे में कभी भी पूछ सकते हैं!"
        else:
            reply_text = f"💡 Financial Snapshot:\n\n• MTD Spend: ₹{cur_spend:,.2f}\n• Remaining Budget: ₹{remaining_budget:,.2f}\n• Safe Daily Pace: ₹{safe_cap:.1f}/day\n• Status: {risk}\n\nAsk me any question about your transactions, savings goals, or budgets!"

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
