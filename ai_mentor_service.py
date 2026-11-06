import calendar
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import re
import database
import forecasting_engine


def get_mom_analysis(user_id: int, target_date: Optional[Any] = None, db_path: str = "expenses.db") -> Dict[str, Any]:
    """
    Month-over-Month (MoM) Category Variance Analysis.
    Compares spending in the current month against the preceding calendar month.
    """
    if target_date is None:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, "%Y-%m-%d").date()

    cur_year = target_date.year
    cur_month = target_date.month

    # Calculate preceding month
    if cur_month == 1:
        prev_month = 12
        prev_year = cur_year - 1
    else:
        prev_month = cur_month - 1
        prev_year = cur_year

    cur_pattern = f"{cur_year:04d}-{cur_month:02d}%"
    prev_pattern = f"{prev_year:04d}-{prev_month:02d}%"

    conn = database.get_db_connection()
    cursor = conn.cursor()

    # Current month category breakdown
    cursor.execute("""
        SELECT COALESCE(c.name, 'Uncategorized') as category_name,
               SUM(t.amount) as total_amount,
               COUNT(t.id) as tx_count
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        GROUP BY c.id, c.name
    """, (user_id, cur_pattern))
    cur_rows = {r["category_name"]: {"amount": float(r["total_amount"]), "count": r["tx_count"]} for r in cursor.fetchall()}

    # Previous month category breakdown
    cursor.execute("""
        SELECT COALESCE(c.name, 'Uncategorized') as category_name,
               SUM(t.amount) as total_amount,
               COUNT(t.id) as tx_count
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        GROUP BY c.id, c.name
    """, (user_id, prev_pattern))
    prev_rows = {r["category_name"]: {"amount": float(r["total_amount"]), "count": r["tx_count"]} for r in cursor.fetchall()}

    conn.close()

    # Merge all category names
    all_cats = set(cur_rows.keys()).union(set(prev_rows.keys()))
    categories_comparison = []

    cur_total = sum(d["amount"] for d in cur_rows.values())
    prev_total = sum(d["amount"] for d in prev_rows.values())

    highest_cat = "None"
    highest_cat_amt = 0.0

    for cat in sorted(all_cats):
        c_amt = cur_rows.get(cat, {}).get("amount", 0.0)
        p_amt = prev_rows.get(cat, {}).get("amount", 0.0)
        diff = round(c_amt - p_amt, 2)
        pct = round(((c_amt - p_amt) / p_amt * 100), 1) if p_amt > 0 else (100.0 if c_amt > 0 else 0.0)

        if c_amt > highest_cat_amt:
            highest_cat_amt = c_amt
            highest_cat = cat

        categories_comparison.append({
            "category": cat,
            "current_month_amount": c_amt,
            "previous_month_amount": p_amt,
            "difference": diff,
            "percentage_change": pct,
            "is_increase": diff > 0
        })

    overall_diff = round(cur_total - prev_total, 2)
    overall_pct = round((overall_diff / prev_total * 100), 1) if prev_total > 0 else (100.0 if cur_total > 0 else 0.0)

    return {
        "current_month": f"{cur_year}-{cur_month:02d}",
        "previous_month": f"{prev_year}-{prev_month:02d}",
        "current_total": round(cur_total, 2),
        "previous_total": round(prev_total, 2),
        "overall_difference": overall_diff,
        "overall_change_pct": overall_pct,
        "is_increase": overall_diff > 0,
        "highest_category": highest_cat,
        "highest_category_amount": round(highest_cat_amt, 2),
        "categories": categories_comparison,
        "current_count": sum(d["count"] for d in cur_rows.values())
    }


def get_six_month_trends(user_id: int, db_path: str = "expenses.db") -> List[Dict[str, Any]]:
    """Fetches rolling 6 calendar months income vs expense for historical trend analysis."""
    today = date.today()
    months_list = []
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        months_list.append((y, m))

    earliest_y, earliest_m = months_list[0]
    start_date_str = f"{earliest_y:04d}-{earliest_m:02d}-01"

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT SUBSTR(date, 1, 7) as ym, transaction_type, SUM(amount) as total
        FROM transactions
        WHERE user_id = ? AND date >= ?
        GROUP BY SUBSTR(date, 1, 7), transaction_type
    """, (user_id, start_date_str))
    rows = cursor.fetchall()
    conn.close()

    monthly_totals = {}
    for r in rows:
        ym = str(r["ym"])[:7]
        ttype = r["transaction_type"]
        tot = float(r["total"] or 0.0)
        if ym not in monthly_totals:
            monthly_totals[ym] = {"INCOME": 0.0, "EXPENSE": 0.0, "TRANSFER": 0.0}
        monthly_totals[ym][ttype] = tot

    history = []
    for y, m in months_list:
        ym_key = f"{y:04d}-{m:02d}"
        d = monthly_totals.get(ym_key, {"INCOME": 0.0, "EXPENSE": 0.0, "TRANSFER": 0.0})
        inc = round(d.get("INCOME", 0.0), 2)
        exp = round(d.get("EXPENSE", 0.0), 2)
        net_savings = round(inc - exp, 2)
        savings_rate = round((net_savings / inc * 100), 1) if inc > 0 else 0.0
        month_label = date(y, m, 1).strftime("%b %y")
        history.append({
            "label": month_label,
            "month": m,
            "year": y,
            "income": inc,
            "expenses": exp,
            "net_savings": net_savings,
            "savings_rate_pct": savings_rate
        })
    return history


def generate_ai_mentor_advice(user_id: int, user_prompt: Optional[str] = None, db_path: str = "expenses.db") -> Dict[str, Any]:
    """
    SUPERCHARGED AI FINANCIAL ADVISOR 3.0
    Grounded financial intelligence engine delivering:
    1. Real ledger queries for category breakdown, accounts balance & cashflow
    2. Deep pattern recognition for Indian and global personal finance queries
    3. Natural, friendly bilingual (Hindi, Hinglish & English) responses
    4. Structured 4-pillar financial explanations
    """
    forecast = forecasting_engine.calculate_month_end_forecast(user_id, db_path=db_path)
    mom = get_mom_analysis(user_id, db_path=db_path)
    net_worth = database.get_net_worth_summary(user_id)
    accounts = database.get_user_accounts(user_id)

    today = date.today()
    pattern = f"{today.year:04d}-{today.month:02d}%"
    cashflow = database.get_monthly_cashflow_summary(user_id, today.month, today.year)

    # Detailed category spending query for current month
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COALESCE(c.name, 'Uncategorized') as category_name,
               SUM(t.amount) as total_amount,
               COUNT(t.id) as tx_count
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        GROUP BY c.id, c.name
        ORDER BY total_amount DESC
    """, (user_id, pattern))
    cat_rows = cursor.fetchall()
    conn.close()

    category_spends = {}
    for r in cat_rows:
        c_name = r["category_name"]
        category_spends[c_name.lower()] = {
            "name": c_name,
            "amount": float(r["total_amount"]),
            "count": r["tx_count"]
        }

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

    # ----------------------------------------------------
    # BILINGUAL NATURAL LANGUAGE QUERY ENGINE
    # ----------------------------------------------------
    user_q = (user_prompt or "").strip().lower()

    hindi_keywords = [
        "kharch", "kitna", "bacha", "kaise", "batao", "kya", "mera", "meri", "mere",
        "paisa", "paise", "rupaye", "kharid", "bache", "sakta", "sakti", "hai",
        "karna", "chahiye", "saving", "namaste", "shukriya", "bhi", "le lu", "khana",
        "petrol", "gadi", "kiraya", "ghar", "dawa", "padhai", "balance", "kaha"
    ]
    is_hindi = any(hk in user_q for hk in hindi_keywords)

    amounts_found = re.findall(r'\b\d+(?:,\d+)*(?:\.\d+)?\b', user_q.replace(',', ''))
    parsed_amount = float(amounts_found[0]) if amounts_found else None

    avail_cash = float(net_worth.get("total_assets", 0.0) or 0.0)
    remaining_budget = max(0.0, float(budget - cur_spend)) if budget > 0 else avail_cash

    # Helper function for matching category queries
    def find_category_in_query(q):
        aliases = {
            "food & dining": ["food", "dining", "restaurant", "swiggy", "zomato", "khana", "lunch", "dinner", "breakfast", "cafe", "coffee", "tea", "chai"],
            "transportation": ["transport", "travel", "cab", "uber", "ola", "petrol", "diesel", "fuel", "auto", "metro", "bus", "train", "flight", "gadi"],
            "shopping": ["shopping", "clothes", "kapde", "amazon", "flipkart", "myntra", "shoes", "dress", "mall", "electronics"],
            "housing & utilities": ["housing", "utilities", "rent", "kiraya", "bijli", "electricity", "water", "wifi", "internet", "maintenance", "gas", "bill"],
            "entertainment": ["entertainment", "movie", "cinema", "netflix", "hotstar", "prime", "game", "party", "fun"],
            "health & medical": ["health", "medical", "medicine", "doctor", "hospital", "pharmacy", "dawa", "gym", "fitness"],
            "education": ["education", "fee", "fees", "school", "college", "course", "books", "padhai"],
            "financial & investments": ["investment", "sip", "mutual fund", "stocks", "shares", "fd", "insurance", "lic"],
            "personal & gifts": ["personal", "gift", "gifts", "salon", "barber", "beauty", "spa"],
            "salary": ["salary", "stipend", "paycheck", "tankha", "vetan"],
            "business & freelance": ["business", "freelance", "client", "project", "side hustle"]
        }
        for standard_cat, word_list in aliases.items():
            if any(w in q for w in word_list):
                return standard_cat
        return None

    matched_cat = find_category_in_query(user_q)

    # 1. EMPTY PROMPT
    if not user_q:
        if is_hindi:
            reply_text = "नमस्ते! मैं आपका पर्सनल AI फाइनेंशियल एडवाइज़र हूँ। आप मुझसे अपने खर्च (Expenses), बजट, बचत (Savings) या किसी भी खरीदारी के बारे में हिंदी या इंग्लिश में पूछ सकते हैं!"
        else:
            reply_text = "Hello! I am your AI Financial Advisor. Ask me anything about your expenses, budgets, savings runway, or purchase affordability."

    # 2. GREETINGS & INTRODUCTIONS
    elif any(k in user_q for k in ["hi", "hello", "hey", "namaste", "pranam", "kya haal", "kaise ho", "who are you", "kaun ho"]):
        if is_hindi:
            reply_text = f"नमस्ते! मैं बिल्कुल ठीक हूँ और आपके खर्चों पर 24/7 नज़र रख रहा हूँ।\n\n• इस महीने का कुल खर्च: ₹{cur_spend:,.2f}\n• बचा हुआ बजट: ₹{remaining_budget:,.2f}\n• सेफ डेली लिमिट: ₹{safe_cap:.1f}/दिन\n\nबताइए, आज मैं आपकी वित्तीय योजना में क्या मदद करूँ?"
        else:
            reply_text = f"Hello! I am your AI Financial Mentor, monitoring your finances in real-time.\n\n• MTD Spend: ₹{cur_spend:,.2f}\n• Remaining Budget: ₹{remaining_budget:,.2f}\n• Safe Daily Pace: ₹{safe_cap:.1f}/day\n\nHow can I assist you with your money management today?"

    # 3. CATEGORY SPECIFIC QUERIES (Food, Travel, Shopping, Bills, etc.)
    elif matched_cat:
        cat_data = category_spends.get(matched_cat)
        matched_cat_display = matched_cat.title()
        if cat_data:
            cat_amt = cat_data["amount"]
            cat_cnt = cat_data["count"]
            cat_pct = round((cat_amt / cur_spend * 100), 1) if cur_spend > 0 else 0.0
            if is_hindi:
                reply_text = f"📊 **{matched_cat_display} खर्च विवरण:**\n\n• कुल खर्च: ₹{cat_amt:,.2f}\n• कुल ट्रांजैक्शन: {cat_cnt} बार\n• इस महीने के कुल खर्च का हिस्सा: {cat_pct}%\n\n💡 **AI सुझाव:** इस कैटेगरी में 15% नियंत्रण करके आप ~₹{round(cat_amt * 0.15, 2):,.2f} की सीधी बचत कर सकते हैं।"
            else:
                reply_text = f"📊 **{matched_cat_display} Spend Analysis:**\n\n• Total Spend: ₹{cat_amt:,.2f}\n• Transactions: {cat_cnt}\n• Share of MTD Expenses: {cat_pct}%\n\n💡 **AI Insight:** Trimming 15% from {matched_cat_display} would save you ~₹{round(cat_amt * 0.15, 2):,.2f} this month."
        else:
            if is_hindi:
                reply_text = f"ℹ️ इस महीने **{matched_cat_display}** में अभी तक कोई खर्च रिकॉर्ड नहीं हुआ है (₹0.00)। आपका खर्च पूरी तरह नियंत्रित है!"
            else:
                reply_text = f"ℹ️ You have not recorded any expenses under **{matched_cat_display}** this month (₹0.00). Keep up the disciplined spending!"

    # 4. AFFORDABILITY & PURCHASE CHECKS ("Kya mai phone khareed sakta hu?")
    elif any(k in user_q for k in ["afford", "kharid", "buy", "purchase", "le lu", "le sakta", "lena chahiye"]):
        check_amt = parsed_amount if parsed_amount else (5000.0 if "5000" in user_q else 2500.0)
        if check_amt <= remaining_budget:
            buffer_after = max(0.0, remaining_budget - check_amt)
            new_daily_cap = round(buffer_after / max(1, days_left), 1)
            if is_hindi:
                reply_text = f"✅ **हाँ, आप ₹{check_amt:,.2f} का खर्च आसानी से कर सकते हैं!**\n\n• वर्तमान बचा बजट: ₹{remaining_budget:,.2f}\n• इस खरीदारी के बाद भी आपके पास ₹{buffer_after:,.2f} का सुरक्षित बजट बचेगा।\n• नई दैनिक सेफ लिमिट: ₹{new_daily_cap}/दिन ({days_left} दिनों के लिए)।\n\nयह खर्च आपकी वित्तीय स्थिरता को प्रभावित नहीं करेगा।"
            else:
                reply_text = f"✅ **Yes, you can comfortably afford this ₹{check_amt:,.2f} purchase!**\n\n• Current remaining budget: ₹{remaining_budget:,.2f}\n• Remaining buffer after purchase: ₹{buffer_after:,.2f}\n• Revised safe daily pace: ₹{new_daily_cap}/day for {days_left} days.\n\nYour cashflow remains fully protected."
        else:
            overrun_by = round(check_amt - remaining_budget, 2)
            if is_hindi:
                reply_text = f"⚠️ **सावधानी आवश्यक! ₹{check_amt:,.2f} खर्च करने से बजट ओवररन हो जाएगा।**\n\n• वर्तमान बचा हुआ बजट: ₹{remaining_budget:,.2f}\n• यह खर्च आपके बजट से ₹{overrun_by:,.2f} अधिक है!\n• 💡 **सुझाव:** यदि यह अनिवार्य नहीं है, तो इसे अगले महीने की शुरुआत में प्लान करें या गैर-जरूरी मदों में कटौती करें।"
            else:
                reply_text = f"⚠️ **Caution! A ₹{check_amt:,.2f} expense exceeds your available budget.**\n\n• Remaining budget: ₹{remaining_budget:,.2f}\n• Potential deficit: ₹{overrun_by:,.2f}\n• 💡 **Recommendation:** Defer this non-essential purchase until next month or reallocate surplus from another category."

    # 5. ACCOUNT BALANCE & NET WORTH QUERIES
    elif any(k in user_q for k in ["balance", "paisa", "paise", "account", "bank", "cash", "net worth", "total paisa"]):
        acc_lines = []
        for a in accounts:
            acc_lines.append(f"• {a['name']} ({a['account_type']}): ₹{float(a['current_balance']):,.2f}")
        acc_text = "\n".join(acc_lines) if acc_lines else "• कोई एकाउंट लिंक नहीं है।"

        total_net_worth = net_worth.get("net_worth", 0.0)
        total_assets = net_worth.get("total_assets", 0.0)

        if is_hindi:
            reply_text = f"💼 **एकाउंट बैलेंस व वित्तीय स्थिति:**\n\n{acc_text}\n\n• **कुल नेट वर्थ (Net Worth):** ₹{total_net_worth:,.2f}\n• कुल लिक्विड बैलेंस (Assets): ₹{total_assets:,.2f}\n\nआपका सारा बैलेंस डबल-एंट्री लेजर में सुरक्षित और अपडेटेड है।"
        else:
            reply_text = f"💼 **Account Balances & Financial Position:**\n\n{acc_text}\n\n• **Total Net Worth:** ₹{total_net_worth:,.2f}\n• Total Liquid Assets: ₹{total_assets:,.2f}\n\nAll accounts are synchronized with double-entry precision."

    # 6. INCOME & CASHFLOW QUERIES
    elif any(k in user_q for k in ["income", "kamai", "salary", "cashflow", "inflow", "aamadani"]):
        inc = cashflow.get("income", 0.0)
        exp = cashflow.get("expenses", 0.0)
        net_save = cashflow.get("net_savings", 0.0)
        rate = cashflow.get("savings_rate_pct", 0.0)
        if is_hindi:
            reply_text = f"📈 **इस महीने का कैशफ्लो सारांश:**\n\n• कुल आय (Income): ₹{inc:,.2f}\n• कुल खर्च (Expenses): ₹{exp:,.2f}\n• शुद्ध बचत (Net Savings): ₹{net_save:,.2f}\n• बचत दर (Savings Rate): {rate}%\n\n💡 एक आदर्श वित्तीय बजट में बचत दर कम से कम 20% होनी चाहिए।"
        else:
            reply_text = f"📈 **Monthly Cashflow Performance:**\n\n• Total Income: ₹{inc:,.2f}\n• Total Expenses: ₹{exp:,.2f}\n• Net Savings: ₹{net_save:,.2f}\n• Savings Rate: {rate}%\n\n💡 Aim for a savings rate of at least 20% according to the 50/30/20 benchmark."

    # 7. OVERALL EXPENSE SUMMARY & VELOCITY
    elif any(k in user_q for k in ["kharch", "spent", "spending", "total kharcha", "kitna kharcha"]):
        top_cat_info = f"सबसे ज्यादा खर्च **{mom['highest_category']}** (₹{mom['highest_category_amount']:,.2f}) में हुआ है।" if mom["highest_category"] != "None" else ""
        if is_hindi:
            reply_text = f"📊 **इस महीने का कुल खर्च सारांश:**\n\n• अब तक का खर्च: ₹{cur_spend:,.2f}\n• खर्च की दैनिक गति (Velocity): ₹{daily_velocity:.1f} / दिन\n• {top_cat_info}\n• अनुमानित महीना अंत खर्च: ₹{proj_spend:,.2f}\n• बाकी बचे दिन: {days_left} दिन"
        else:
            reply_text = f"📊 **Monthly Spending Velocity:**\n\n• Total MTD Spend: ₹{cur_spend:,.2f}\n• Daily Velocity: ₹{daily_velocity:.1f}/day\n• Top Category: {mom['highest_category']} (₹{mom['highest_category_amount']:,.2f})\n• Projected Month-End: ₹{proj_spend:,.2f}\n• Days Remaining: {days_left}"

    # 8. BUDGET & REMAINING RUNWAY
    elif any(k in user_q for k in ["budget", "bacha", "remaining", "overrun", "risk"]):
        if is_hindi:
            reply_text = f"🎯 **मासिक बजट स्टेटस:**\n\n• कुल बजट सीमा: ₹{budget:,.2f}\n• खर्च हुआ: ₹{cur_spend:,.2f}\n• बचा हुआ बजट: ₹{remaining_budget:,.2f}\n• बाकी दिन: {days_left} दिन\n• 🛡️ सेफ डेली खर्च सीमा: ₹{safe_cap:.1f} / दिन\n• रिस्क स्टेटस: {risk}\n\nयदि आप प्रतिदिन ₹{safe_cap:.1f} के भीतर खर्च करेंगे, तो आपका बजट कभी ओवररन नहीं होगा।"
        else:
            reply_text = f"🎯 **Monthly Budget Ceiling:**\n\n• Total Budget: ₹{budget:,.2f}\n• MTD Spend: ₹{cur_spend:,.2f}\n• Remaining Balance: ₹{remaining_budget:,.2f}\n• Days Remaining: {days_left}\n• 🛡️ Safe Daily Cap: ₹{safe_cap:.1f}/day\n• Risk Status: {risk}\n\nPacing your daily spend under ₹{safe_cap:.1f} guarantees you finish within budget."

    # 9. SAVINGS STRATEGY & 50/30/20 RULE
    elif any(k in user_q for k in ["save", "saving", "bachat", "kaise bachaye", "cut", "50-30-20", "invest"]):
        trim_val = round(mom['highest_category_amount'] * 0.15, 2) if mom['highest_category'] != "None" else 500.0
        if is_hindi:
            reply_text = f"💡 **बचत बढ़ाने और वेल्थ बनाने के अचूक नियम:**\n\n1. **50-30-20 का स्वर्णिम नियम:**\n   • 50% अनिवार्य जरूरतें (Needs): राशन, बिल, किराया\n   • 30% जीवनशैली (Wants): डाइनिंग, मूवी, गैजेट\n   • 20% बचत (Savings): इमरजेंसी फंड, SIP\n\n2. **तुरंत कार्रवाई:** अपने सबसे बड़े खर्च '{mom['highest_category']}' में 15% की कमी करके आप महीने में ₹{trim_val:,.2f} तुरंत बचा सकते हैं।\n3. सुरक्षित दैनिक खर्च सीमा ₹{safe_cap:.1f}/दिन का पालन करें।"
        else:
            reply_text = f"💡 **Savings & Wealth Acceleration Strategy:**\n\n1. **The 50/30/20 Rule:**\n   • 50% Needs: Groceries, utilities, rent\n   • 30% Wants: Dining, entertainment, shopping\n   • 20% Savings: Emergency buffer, investments\n\n2. **Immediate Action:** Trimming 15% from '{mom['highest_category']}' captures ~₹{trim_val:,.2f} in immediate savings.\n3. Respect your safe daily cap of ₹{safe_cap:.1f}/day."

    # 10. PREDICTIONS & NEXT MONTH FORECAST
    elif any(k in user_q for k in ["forecast", "next month", "aage", "bhavishya", "future", "agla mahina"]):
        if is_hindi:
            reply_text = f"🔮 **AI खर्च भविष्यवाणी (Forecast):**\n\n• इस महीने का अनुमानित कुल खर्च: ₹{proj_spend:,.2f}\n• आपकी वर्तमान स्पीड (₹{daily_velocity:.1f}/दिन) के आधार पर अगले महीने का बेसलाइन खर्च भी लगभग ₹{proj_spend:,.2f} रहने का अनुमान है।\n• रिस्क स्टेटस: {risk}\n\n💡 **सलाह:** अगले महीने के लिए अभी से ₹{round(proj_spend * 0.9, -2):,.2f} का बजट तय कर लें।"
        else:
            reply_text = f"🔮 **AI Predictive Horizon:**\n\n• Projected Current Month Total: ₹{proj_spend:,.2f}\n• Next Month Baseline Projection: ~₹{proj_spend:,.2f} at current velocity (₹{daily_velocity:.1f}/day).\n• Risk Status: {risk}\n\n💡 **Tip:** Set a target budget of ₹{round(proj_spend * 0.9, -2):,.2f} for next month in the Budgets section."

    # 11. APP USAGE & CAPABILITIES
    elif any(k in user_q for k in ["app", "feature", "kaise use", "help", "madad"]):
        if is_hindi:
            reply_text = "📱 **Expense Tracker Pro 2.0 का पूरा उपयोग:**\n\n• **+ बटन:** तुरंत 0ms में नया खर्च/कमाई जोड़ें।\n• **Analytics (2nd Tab):** Donut Chart और 6-महीने का ट्रेंड देखें।\n• **AI Advisor (4th Tab):** Spending Trajectory vs Budget Ceiling ग्राफ का लाइव एनालिसिस।\n• **✨ AI Assistant:** किसी भी स्क्रीन से मुझसे कोई भी वित्तीय सवाल पूछें!"
        else:
            reply_text = "📱 **Expense Tracker Pro 2.0 Feature Guide:**\n\n• **+ FAB Button:** Instant 0ms transaction logging (Expense, Income, Transfer).\n• **Analytics Tab:** Neon Donut breakdown and 6-month historical cashflow.\n• **AI Advisor Tab:** Spending trajectory vs budget ceiling interactive scrubber.\n• **✨ AI Assistant:** Tap the floating orb anywhere to ask financial questions!"

    # 12. FALLBACK FINANCIAL SNAPSHOT
    else:
        if is_hindi:
            reply_text = f"💡 **आपका त्वरित वित्तीय सारांश:**\n\n• इस महीने का खर्च: ₹{cur_spend:,.2f}\n• बचा हुआ बजट: ₹{remaining_budget:,.2f}\n• सेफ डेली लिमिट: ₹{safe_cap:.1f}/दिन\n• रिस्क स्टेटस: {risk}\n\nआप मुझसे किसी भी विशिष्ट खर्च (जैसे 'Food pe kitna kharch hua?'), बजट या एकाउंट बैलेंस के बारे में पूछ सकते हैं!"
        else:
            reply_text = f"💡 **Your Financial Snapshot:**\n\n• MTD Spend: ₹{cur_spend:,.2f}\n• Remaining Budget: ₹{remaining_budget:,.2f}\n• Safe Daily Pace: ₹{safe_cap:.1f}/day\n• Status: {risk}\n\nYou can ask me specific questions like 'How much spent on food?', 'Can I buy a watch for 5000?', or 'Check bank balance'!"

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
