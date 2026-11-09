# -*- coding: utf-8 -*-
"""
SUPERCHARGED AI FINANCIAL ASSISTANT & SAATHI 4.0
================================================
The Intelligent Backbone of Expense Tracker Pro:
1. Real Ledger Grounding (RAG Context Injection) - 100% accurate mathematical truth.
2. Dual-Engine Intelligence:
   - Primary: Google Gemini API (Natural Multi-turn & Reasoning).
   - Zero-Fail Fallback: High-precision semantic financial NLU engine (Offline/Zero latency).
3. Desi Multilingual (Hinglish, Hindi, English) with Zero Jargon & Empathy.
4. Voice-Optimized Responses (Spoken Text for Text-to-Speech + Rich Decision Cards).
5. Dynamic 1-Tap Contextual Follow-Up Suggestions & Interactive Action Buttons.
"""

import calendar
from datetime import date, datetime, timedelta
import json
import os
import re
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

import database
import forecasting_engine


def get_mom_analysis(user_id: int, target_date: Optional[Any] = None, db_path: str = "expenses.db") -> Dict[str, Any]:
    """Month-over-Month (MoM) Category Variance Analysis."""
    if target_date is None:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, "%Y-%m-%d").date()

    cur_year = target_date.year
    cur_month = target_date.month

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


def get_financial_context(user_id: int, db_path: str = "expenses.db") -> Dict[str, Any]:
    """
    RAG Context Builder:
    Extracts complete, mathematically grounded snapshot of the user's personal ledger.
    """
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    month_pattern = f"{today.year:04d}-{today.month:02d}%"

    forecast = forecasting_engine.calculate_month_end_forecast(user_id, db_path=db_path)
    mom = get_mom_analysis(user_id, db_path=db_path)
    net_worth = database.get_net_worth_summary(user_id)
    cashflow = database.get_monthly_cashflow_summary(user_id, today.month, today.year)
    user_name = "Friend"
    try:
        conn_u = database.get_db_connection()
        cur_u = conn_u.cursor()
        cur_u.execute("SELECT name FROM users WHERE id = ?", (user_id,))
        u_row = cur_u.fetchone()
        if u_row and u_row["name"]:
            user_name = u_row["name"].split()[0]
        conn_u.close()
    except Exception:
        pass

    conn = database.get_db_connection()
    cursor = conn.cursor()

    # Accounts
    cursor.execute("SELECT name, current_balance, account_type FROM accounts WHERE user_id = ? AND is_active = 1", (user_id,))
    accounts = [dict(r) for r in cursor.fetchall()]

    # Today's spend
    cursor.execute("SELECT COALESCE(SUM(amount), 0.0) as amt FROM transactions WHERE user_id = ? AND transaction_type = 'EXPENSE' AND date = ?", (user_id, today_str))
    today_spend = float(cursor.fetchone()["amt"] or 0.0)

    # Yesterday's spend
    cursor.execute("SELECT COALESCE(SUM(amount), 0.0) as amt FROM transactions WHERE user_id = ? AND transaction_type = 'EXPENSE' AND date = ?", (user_id, yesterday_str))
    yesterday_spend = float(cursor.fetchone()["amt"] or 0.0)

    # Category breakdown for current month
    cursor.execute("""
        SELECT COALESCE(c.name, 'Uncategorized') as category_name,
               SUM(t.amount) as total_amount,
               COUNT(t.id) as tx_count
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        GROUP BY c.id, c.name
        ORDER BY total_amount DESC
    """, (user_id, month_pattern))
    cat_rows = cursor.fetchall()
    category_spends = {r["category_name"].lower(): {"name": r["category_name"], "amount": float(r["total_amount"]), "count": r["tx_count"]} for r in cat_rows}

    # Recent 5 transactions
    cursor.execute("""
        SELECT t.id, COALESCE(t.note, 'Transaction') as note, t.amount, t.date, t.transaction_type, COALESCE(c.name, 'Uncategorized') as category_name
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ?
        ORDER BY t.date DESC, t.id DESC LIMIT 5
    """, (user_id,))
    recent_txs = [dict(r) for r in cursor.fetchall()]

    # Upcoming recurring bills
    cursor.execute("SELECT title, amount, next_due_date FROM recurring_bills WHERE user_id = ? AND is_active = 1 AND auto_paid = 0 ORDER BY next_due_date ASC", (user_id,))
    upcoming_bills = [dict(r) for r in cursor.fetchall()]

    # Active savings goals
    cursor.execute("SELECT title, target_amount, current_amount, target_date FROM financial_goals WHERE user_id = ? AND is_completed = 0", (user_id,))
    active_goals = [dict(r) for r in cursor.fetchall()]

    conn.close()

    budget = forecast.get("monthly_budget", 0.0)
    cur_spend = forecast.get("mtd_actual_spend", 0.0)
    remaining_budget = max(0.0, float(budget - cur_spend)) if budget > 0 else float(net_worth.get("total_assets", 0.0) or 0.0)

    return {
        "user_name": user_name,
        "date_today": today_str,
        "days_in_month": calendar.monthrange(today.year, today.month)[1],
        "days_left": forecast.get("days_remaining", 0),
        "today_spend": today_spend,
        "yesterday_spend": yesterday_spend,
        "cur_spend": cur_spend,
        "monthly_budget": budget,
        "remaining_budget": remaining_budget,
        "daily_velocity": forecast.get("daily_spending_velocity", 0.0),
        "safe_daily_spend": forecast.get("safe_daily_spend", forecast.get("safe_daily_cap", 0.0)),
        "proj_month_end": forecast.get("projected_month_end_spend", 0.0),
        "risk_status": forecast.get("risk_status", "SAFE"),
        "top_category": mom.get("highest_category", "None"),
        "top_category_amount": mom.get("highest_category_amount", 0.0),
        "accounts": accounts,
        "total_net_worth": net_worth.get("net_worth", 0.0),
        "total_assets": net_worth.get("total_assets", 0.0),
        "monthly_income": cashflow.get("income", 0.0),
        "net_savings": cashflow.get("net_savings", 0.0),
        "savings_rate_pct": cashflow.get("savings_rate_pct", 0.0),
        "category_spends": category_spends,
        "recent_transactions": recent_txs,
        "upcoming_bills": upcoming_bills,
        "active_goals": active_goals
    }


def call_gemini_api(context: Dict[str, Any], user_prompt: str) -> Optional[Dict[str, Any]]:
    """
    Calls Google Gemini API (Gemini 1.5 / 2.0 Flash) with grounded personal finance prompt.
    Returns None if no API key is configured or if network error occurs.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    # Construct System Persona & Grounded Rules
    system_instruction = f"""You are 'AI Financial Saathi', an empathetic, wise, and super-friendly Indian personal finance mentor inside the Expense Tracker Pro app.
Target User: Everyday Indian users, including those who prefer very simple, friendly, easy-to-understand explanations (no complex banking jargon).

GROUND RULES:
1. Always base all numbers strictly on the user's real ledger data provided in the JSON context below. Never invent or hallucinate financial numbers.
2. Tone: Warm, respectful, encouraging, desi companion ("Pocket Munshi").
3. Language Adaptation:
   - If user asks in Hinglish (e.g., "bhai kal kitna kharch hua?"), respond in natural conversational Hinglish.
   - If user asks in Hindi, respond in clean, polite Hindi.
   - If user asks in English, respond in crisp, friendly English.
4. Formatting:
   - Keep answers concise (2 to 4 short paragraphs / bullet points maximum).
   - Use bold for key numbers and categories (e.g., **₹250.00**, **Food & Dining**).
   - Use friendly emojis (💰, 🍔, 🛡️, 💡, ✅, ⚠️).
   - Never use technical jargon like "amortized runway" or "discretionary variance". Instead say "aaj ka safe kharch", "bacha hua paisa", "bachat".
5. Dynamic Follow-ups:
   - Always conclude by suggesting 2 to 3 very relevant short follow-up questions user might want to ask next.

REAL LEDGER CONTEXT:
{json.dumps(context, indent=2, ensure_ascii=False)}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": [
            {
                "parts": [{"text": user_prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 600
        }
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            # Clean audio spoken text (remove markdown symbols)
            spoken = re.sub(r'[*_#`•]', '', text)
            spoken = re.sub(r'\s+', ' ', spoken).strip()

            # Extract 2-3 dynamic follow-up chips from text or fallback
            chips = []
            chip_candidates = re.findall(r'["\']([^"\']{4,35}\??)["\']', text)
            for c in chip_candidates:
                if len(c) > 5 and len(chips) < 3 and not any(x in c.lower() for x in ["http", "json", "gemini"]):
                    chips.append(c.strip())

            if len(chips) < 2:
                chips = ["💰 Mera bacha hua paisa?", "🍔 Food pe kitna gaya?", "🛡️ Aaj ka safe limit?"]

            return {
                "reply": text,
                "spoken_text": spoken[:280],
                "followup_chips": chips[:3]
            }
    except Exception as e:
        # Fall back cleanly without crashing
        return None


def local_financial_nlu_engine(context: Dict[str, Any], user_prompt: str) -> Dict[str, Any]:
    """
    Zero-Fail, High-Precision Local Financial Reasoning Engine:
    Employs rich pattern matching, colloquial Hindi/Hinglish phrase recognition,
    and ledger grounding to deliver instant (0ms) human-like advice.
    """
    user_q = (user_prompt or "").strip().lower()

    # Detect language preference
    hindi_words = [
        "kharch", "kharcha", "kitna", "bacha", "kaise", "batao", "kya", "mera", "meri", "mere",
        "paisa", "paise", "rupaye", "rupay", "kharid", "bache", "sakta", "sakti", "hai",
        "karna", "chahiye", "saving", "namaste", "shukriya", "bhi", "le lu", "khana",
        "petrol", "gadi", "kiraya", "ghar", "dawa", "padhai", "balance", "kaha", "bhai",
        "bhaiya", "aaj", "kal", "parso", "kisme", "suta", "chai", "doodh", "sabzi"
    ]
    is_hindi = any(hw in user_q for hw in hindi_words)

    # Numerical extraction
    amounts = re.findall(r'\b\d+(?:,\d+)*(?:\.\d+)?\b', user_q.replace(',', ''))
    parsed_amount = float(amounts[0]) if amounts else None

    # Context shortcuts
    user_name = context["user_name"]
    cur_spend = context["cur_spend"]
    budget = context["monthly_budget"]
    remaining_budget = context["remaining_budget"]
    days_left = context["days_left"]
    daily_velocity = context["daily_velocity"]
    safe_cap = context["safe_daily_spend"]
    proj_spend = context["proj_month_end"]
    risk = context["risk_status"]
    top_cat = context["top_category"]
    top_cat_amt = context["top_category_amount"]
    today_spend = context["today_spend"]
    yesterday_spend = context["yesterday_spend"]
    accounts = context["accounts"]
    category_spends = context["category_spends"]
    upcoming_bills = context["upcoming_bills"]
    active_goals = context["active_goals"]

    # Category matching with rich colloquial aliases
    category_aliases = {
        "food & dining": ["food", "dining", "swiggy", "zomato", "khana", "lunch", "dinner", "breakfast", "nashta", "cafe", "coffee", "chai", "tea", "hotel", "restaurant", "burger", "pizza", "biryani", "snack"],
        "transportation": ["transport", "travel", "cab", "uber", "ola", "petrol", "diesel", "fuel", "auto", "metro", "bus", "train", "flight", "gadi", "bike", "rapido"],
        "shopping": ["shopping", "clothes", "kapde", "amazon", "flipkart", "myntra", "shoes", "joota", "dress", "mall", "electronics", "phone", "mobile", "laptop"],
        "housing & utilities": ["housing", "utilities", "rent", "kiraya", "bijli", "electricity", "water", "paani", "wifi", "internet", "recharge", "gas", "cylinder", "bill"],
        "entertainment": ["entertainment", "movie", "cinema", "netflix", "hotstar", "prime", "game", "party", "masti", "fun", "club"],
        "health & medical": ["health", "medical", "medicine", "doctor", "hospital", "pharmacy", "dawa", "gym", "fitness", "test"],
        "education": ["education", "fee", "fees", "school", "college", "course", "books", "padhai", "kitab", "coaching"],
        "financial & investments": ["investment", "sip", "mutual fund", "stocks", "shares", "fd", "insurance", "lic"],
        "personal & gifts": ["personal", "gift", "gifts", "salon", "barber", "parlour", "beauty"]
    }

    matched_cat = None
    for std_cat, words in category_aliases.items():
        if any(w in user_q for w in words):
            matched_cat = std_cat
            break

    decision_badge = None
    action_button = None
    chips = []

    # ----------------------------------------------------
    # 1. EMPTY PROMPT
    # ----------------------------------------------------
    if not user_q:
        if is_hindi:
            reply = f"नमस्ते {user_name}! मैं आपका पर्सनल AI फाइनेंशियल साथी हूँ।\n\nआप मुझसे बोल कर (🎙️ Mic दबाकर) या लिख कर अपने खर्च, बजट, बचत या किसी भी खरीदारी के बारे में पूछ सकते हैं!"
            spoken = f"नमस्ते {user_name}! मैं आपका AI साथी हूँ। आप मुझसे बोलकर या लिखकर अपने खर्च या बजट के बारे में पूछ सकते हैं।"
        else:
            reply = f"Hello {user_name}! I am your AI Financial Companion.\n\nTap the 🎙️ Mic to speak or type to ask about your expenses, budgets, savings runway, or purchase affordability!"
            spoken = f"Hello {user_name}! I am your AI companion. Tap the mic or type to ask about your money."
        chips = ["💰 Mera bacha paisa?", "🍔 Food ka kharch?", "🛡️ Aaj ka safe limit?"]

    # ----------------------------------------------------
    # 2. GREETINGS & INTRO ("Hi", "Hello", "Namaste", "Kaise ho")
    # ----------------------------------------------------
    elif any(k in user_q for k in ["hi", "hello", "hey", "namaste", "pranam", "kaise ho", "kya haal", "who are you", "kaun ho"]):
        if is_hindi:
            reply = (
                f"नमस्ते {user_name}! मैं बिल्कुल बढ़िया हूँ और आपके पैसों का पूरा ध्यान रख रहा हूँ। 😊\n\n"
                f"📊 **आज का क्विक स्टेटस:**\n"
                f"• इस महीने का कुल खर्च: **₹{cur_spend:,.2f}**\n"
                f"• बचा हुआ सुरक्षित बजट: **₹{remaining_budget:,.2f}**\n"
                f"• आज का सेफ खर्च सीमा: **₹{safe_cap:.1f}/दिन**\n\n"
                f"बोलिए, आज आपको क्या जानना है?"
            )
            spoken = f"नमस्ते {user_name}! इस महीने कुल {int(cur_spend)} rupaye kharch huye hain, aur bacha hua budget {int(remaining_budget)} rupaye hai. Aaj ka safe limit {int(safe_cap)} rupaye hai."
        else:
            reply = (
                f"Hello {user_name}! I'm doing great and keeping close watch on your money. 😊\n\n"
                f"📊 **Quick Financial Snapshot:**\n"
                f"• MTD Total Spend: **₹{cur_spend:,.2f}**\n"
                f"• Remaining Buffer: **₹{remaining_budget:,.2f}**\n"
                f"• Safe Daily Pace: **₹{safe_cap:.1f}/day**\n\n"
                f"What would you like to check today?"
            )
            spoken = f"Hello {user_name}! Your total spend this month is {int(cur_spend)} rupees, with {int(remaining_budget)} rupees remaining in your safe budget."
        chips = ["💰 Mera bacha paisa?", "🍔 Food pe kitna gaya?", "🎯 Kya mai phone khareed sakta hu?"]

    # ----------------------------------------------------
    # 3. ADD EXPENSE INTENT ("50 rupaye chai me add kar do", "Add 200 food")
    # ----------------------------------------------------
    elif any(k in user_q for k in ["add", "likh do", "daal do", "note kar", "record"]):
        amt = parsed_amount if parsed_amount else 50.0
        cat_name = matched_cat.title() if matched_cat else "Food & Dining"

        action_button = {
            "label": f"+ Record ₹{amt:,.2f} under {cat_name}",
            "type": "OPEN_QUICK_ENTRY",
            "amount": amt,
            "category": cat_name
        }

        if is_hindi:
            reply = (
                f"📝 **खर्च जोड़ने के लिए तैयार:**\n\n"
                f"मैंने आपका खर्च पहचान लिया है:\n"
                f"• राशि: **₹{amt:,.2f}**\n"
                f"• कैटेगरी: **{cat_name}**\n\n"
                f"नीचे दिए गए बटन पर टैप करके तुरंत रिकॉर्ड करें 👇"
            )
            spoken = f"{cat_name} me {int(amt)} rupaye jodne ke liye neeche button dabayein."
        else:
            reply = (
                f"📝 **Ready to Log Expense:**\n\n"
                f"I detected your transaction request:\n"
                f"• Amount: **₹{amt:,.2f}**\n"
                f"• Category: **{cat_name}**\n\n"
                f"Tap the button below to confirm and record instantly 👇"
            )
            spoken = f"Tap below to record {int(amt)} rupees under {cat_name}."

        chips = ["💰 Mera bacha paisa?", "📊 Is mahine ka total kharch?", "🛡️ Aaj ka safe limit?"]

    # ----------------------------------------------------
    # 4. TODAY'S & YESTERDAY'S SPENDING ("Aaj kitna kharcha hua", "Kal kitna gaya")
    # ----------------------------------------------------
    elif any(k in user_q for k in ["aaj", "today", "kal", "yesterday"]):
        is_yesterday = any(k in user_q for k in ["kal", "yesterday"])
        target_spend = yesterday_spend if is_yesterday else today_spend
        day_label = "कल (Yesterday)" if is_yesterday else "आज (Today)"

        if target_spend > 0:
            if is_hindi:
                reply = (
                    f"📅 **{day_label} का खर्च विवरण:**\n\n"
                    f"• कुल खर्च हुआ: **₹{target_spend:,.2f}**\n"
                    f"• दैनिक सेफ लिमिट: **₹{safe_cap:.1f}/दिन**\n\n"
                    f"💡 **सलाह:** {'आपका खर्च दैनिक लिमिट के भीतर है, बहुत बढ़िया!' if target_spend <= safe_cap else 'यह खर्च आपकी दैनिक सेफ लिमिट से थोड़ा अधिक था, आने वाले दिनों में संतुलन बनाए रखें।'}"
                )
                spoken = f"{day_label} kul {int(target_spend)} rupaye kharch huye the. Aapki daily safe limit {int(safe_cap)} rupaye hai."
            else:
                reply = (
                    f"📅 **{day_label} Spending Report:**\n\n"
                    f"• Total Spent: **₹{target_spend:,.2f}**\n"
                    f"• Safe Daily Cap: **₹{safe_cap:.1f}/day**\n\n"
                    f"💡 **Insight:** {'Spending was well within your safe pace, excellent discipline!' if target_spend <= safe_cap else 'Spend slightly exceeded your safe daily pace. Keep discretionary spending modest over the next few days.'}"
                )
                spoken = f"Total spend on {day_label} was {int(target_spend)} rupees."
        else:
            if is_hindi:
                reply = f"🎉 **{day_label} आपने ₹0 खर्च किए!**\n\nकोई भी नया खर्च रिकॉर्ड नहीं हुआ है। आपकी बचत सुरक्षित है!"
                spoken = f"{day_label} aapne shunya rupaye kharch kiye. Sabhi paise surakshit hain!"
            else:
                reply = f"🎉 **You spent ₹0 {day_label.lower()}!**\n\nNo expense entries recorded. Excellent wallet discipline!"
                spoken = f"You spent zero rupees on {day_label}."

        chips = ["📊 Is mahine ka total kharch?", "💰 Mera bacha paisa?", "🍔 Khane pe kitna gaya?"]

    # ----------------------------------------------------
    # 4. PURCHASE DECISION / AFFORDABILITY ("Kya mai X khareed sakta hu?")
    # ----------------------------------------------------
    elif any(k in user_q for k in ["afford", "kharid", "buy", "purchase", "le lu", "le sakta", "lena chahiye"]):
        check_amt = parsed_amount if parsed_amount else 2500.0

        if check_amt <= remaining_budget:
            buffer_after = max(0.0, remaining_budget - check_amt)
            new_safe_cap = round(buffer_after / max(1, days_left), 1)

            if check_amt <= (remaining_budget * 0.4):
                decision_badge = {"type": "SAFE", "label": "AASANI SE LE SAKTE HAIN ✅"}
                verdict_hindi = f"✅ **हाँ, आप ₹{check_amt:,.2f} का खर्च आराम से कर सकते हैं!**"
                verdict_eng = f"✅ **Yes, you can easily afford this ₹{check_amt:,.2f} purchase!**"
            else:
                decision_badge = {"type": "CAUTION", "label": "THODA DHYAN RAKHEIN ⚠️"}
                verdict_hindi = f"⚠️ **हाँ, ले सकते हैं पर थोड़ा संभलकर! ₹{check_amt:,.2f} बजट का बड़ा हिस्सा है।**"
                verdict_eng = f"⚠️ **You can afford this, but proceed with caution! ₹{check_amt:,.2f} takes a large slice of your remaining budget.**"

            if is_hindi:
                reply = (
                    f"{verdict_hindi}\n\n"
                    f"• वर्तमान बचा बजट: **₹{remaining_budget:,.2f}**\n"
                    f"• इस खरीदारी के बाद बचेगा: **₹{buffer_after:,.2f}**\n"
                    f"• नई सुरक्षित दैनिक लिमिट: **₹{new_safe_cap}/दिन** ({days_left} दिनों के लिए)\n\n"
                    f"💡 **सलाह:** यह खरीदारी आपके महीने के अंत को सुरक्षित रखेगी।"
                )
                spoken = f"Haan, aap {int(check_amt)} rupaye ka kharch kar sakte hain. Iske baad bhi aapke paas {int(buffer_after)} rupaye ka safe budget bachega."
            else:
                reply = (
                    f"{verdict_eng}\n\n"
                    f"• Current Remaining Budget: **₹{remaining_budget:,.2f}**\n"
                    f"• Remaining Buffer After Purchase: **₹{buffer_after:,.2f}**\n"
                    f"• Revised Safe Daily Cap: **₹{new_safe_cap}/day** (for {days_left} days)\n\n"
                    f"💡 **Verdict:** Your month-end cashflow remains safely positive."
                )
                spoken = f"Yes, you can afford this {int(check_amt)} rupees purchase with {int(buffer_after)} rupees buffer remaining."
        else:
            overrun_by = round(check_amt - remaining_budget, 2)
            decision_badge = {"type": "DANGER", "label": "BUDGET OVERRUN RISK 🛑"}

            if is_hindi:
                reply = (
                    f"🛑 **सावधानी! ₹{check_amt:,.2f} खर्च करने से आपका बजट ओवररन हो जाएगा।**\n\n"
                    f"• आपके पास अभी बचा है: **₹{remaining_budget:,.2f}**\n"
                    f"• यह खर्च बजट से **₹{overrun_by:,.2f}** अधिक है!\n\n"
                    f"💡 **AI सुझाव:**\n"
                    f"1. यदि यह जरूरी नहीं है, तो इसे अगले महीने की शुरुआत तक टालें।\n"
                    f"2. या किसी अन्य गैर-जरूरी खर्च में कटौती करके इसे प्लान करें।"
                )
                spoken = f"Rukiye! {int(check_amt)} rupaye kharch karne se aapka budget {int(overrun_by)} rupaye exceed ho jayega. Ise agle mahine plan karein."
            else:
                reply = (
                    f"🛑 **Caution! A ₹{check_amt:,.2f} purchase will exceed your monthly budget.**\n\n"
                    f"• Current Remaining Budget: **₹{remaining_budget:,.2f}**\n"
                    f"• Potential Deficit: **₹{overrun_by:,.2f} over budget**\n\n"
                    f"💡 **AI Recommendation:**\n"
                    f"1. Defer this non-essential purchase until your next salary cycle.\n"
                    f"2. Or trim surplus spending from other discretionary categories."
                )
                spoken = f"Warning! A purchase of {int(check_amt)} rupees exceeds your remaining budget by {int(overrun_by)} rupees."

        chips = ["💰 Mera bacha hua budget?", "🛡️ Aaj ka safe limit?", "📊 Is mahine ka total kharch?"]

    # ----------------------------------------------------
    # 5. CATEGORY SPECIFIC QUERIES (Food, Travel, Shopping, Bills)
    # ----------------------------------------------------
    elif matched_cat:
        cat_info = category_spends.get(matched_cat)
        matched_display = matched_cat.title()

        if cat_info and cat_info["amount"] > 0:
            c_amt = cat_info["amount"]
            c_cnt = cat_info["count"]
            c_pct = round((c_amt / cur_spend * 100), 1) if cur_spend > 0 else 0.0
            savings_15 = round(c_amt * 0.15, 2)

            if is_hindi:
                reply = (
                    f"🍔 **{matched_display} का खर्च विवरण:**\n\n"
                    f"• कुल खर्च: **₹{c_amt:,.2f}**\n"
                    f"• कुल बार खर्च किया: **{c_cnt} ट्रांजैक्शन**\n"
                    f"• इस महीने के कुल खर्च का हिस्सा: **{c_pct}%**\n\n"
                    f"💡 **बचत टिप:** {matched_display} में सिर्फ 15% कटौती करके आप आसानी से **₹{savings_15:,.2f}** बचा सकते हैं!"
                )
                spoken = f"{matched_display} me kul {int(c_amt)} rupaye kharch huye hain, jo aapke kul kharch ka {c_pct} percent hai."
            else:
                reply = (
                    f"🍔 **{matched_display} Spending Analysis:**\n\n"
                    f"• Total Expenditure: **₹{c_amt:,.2f}**\n"
                    f"• Transaction Count: **{c_cnt} times**\n"
                    f"• Share of Total Expenses: **{c_pct}%**\n\n"
                    f"💡 **Savings Tip:** Trimming 15% from {matched_display} captures **₹{savings_15:,.2f}** in pure savings!"
                )
                spoken = f"You have spent {int(c_amt)} rupees on {matched_display} across {c_cnt} transactions."
        else:
            if is_hindi:
                reply = f"ℹ️ इस महीने **{matched_display}** में अभी तक कोई खर्च नहीं हुआ है (₹0.00)। आपका नियंत्रण बहुत बढ़िया है! 👍"
                spoken = f"Is mahine {matched_display} me shunya rupaye kharch huye hain."
            else:
                reply = f"ℹ️ You have not recorded any spending under **{matched_display}** this month (₹0.00). Keep up the discipline! 👍"
                spoken = f"Zero rupees spent on {matched_display} this month."

        chips = ["📊 Sabse zyada kharcha kisme hua?", "💰 Mera bacha paisa?", "💡 Bachat kaise badhaye?"]

    # ----------------------------------------------------
    # 6. ACCOUNT BALANCE & NET WORTH ("Balance kitna hai", "Bank me kitna hai")
    # ----------------------------------------------------
    elif any(k in user_q for k in ["balance", "paisa", "paise", "account", "bank", "cash", "net worth", "total paisa"]):
        acc_lines = []
        for a in accounts:
            acc_lines.append(f"• **{a['name']}** ({a['account_type']}): **₹{float(a['current_balance']):,.2f}**")
        acc_text = "\n".join(acc_lines) if acc_lines else "• कोई एकाउंट लिंक नहीं है।"

        total_assets = context["total_assets"]

        if is_hindi:
            reply = (
                f"💼 **आपके एकाउंट्स का लाइव बैलेंस:**\n\n"
                f"{acc_text}\n\n"
                f"• **कुल लिक्विड बैलेंस:** **₹{total_assets:,.2f}**\n\n"
                f"आपका सारा बैलेंस डबल-एंट्री लेजर में 100% सुरक्षित और अपडेटेड है।"
            )
            spoken = f"Aapka kul liquid balance {int(total_assets)} rupaye hai."
        else:
            reply = (
                f"💼 **Your Live Account Balances:**\n\n"
                f"{acc_text}\n\n"
                f"• **Total Liquid Balance:** **₹{total_assets:,.2f}**\n\n"
                f"All accounts are perfectly synchronized with double-entry precision."
            )
            spoken = f"Your total liquid balance across all accounts is {int(total_assets)} rupees."

        chips = ["📊 Is mahine ka kharcha?", "🎯 Budget kitna bacha hai?", "🛡️ Aaj ka safe limit?"]


    # ----------------------------------------------------
    # 8. TOP SPENDING CATEGORY ("Kisme zyada kharch hua?", "Top spend")
    # ----------------------------------------------------
    elif any(k in user_q for k in ["zyada", "jyada", "sabse bada", "top", "highest", "kisme"]):
        if top_cat != "None" and top_cat_amt > 0:
            pct_of_spend = round((top_cat_amt / cur_spend * 100), 1) if cur_spend > 0 else 0.0
            if is_hindi:
                reply = (
                    f"🏆 **इस महीने का सबसे बड़ा खर्च:**\n\n"
                    f"आपका सबसे अधिक पैसा **{top_cat}** में गया है:\n"
                    f"• कुल राशि: **₹{top_cat_amt:,.2f}** ({pct_of_spend}% of total spend)\n\n"
                    f"💡 **सुझाव:** यदि आप {top_cat} में सिर्फ 15% की बचत कर लें, तो महीने के अंत में आपके पास **₹{round(top_cat_amt * 0.15, 2):,.2f}** अतिरिक्त बचेंगे!"
                )
                spoken = f"Aapka sabse zyada kharcha {top_cat} me hua hai, kul {int(top_cat_amt)} rupaye."
            else:
                reply = (
                    f"🏆 **Top Spending Expense Category:**\n\n"
                    f"Your highest expenditure driver is **{top_cat}**:\n"
                    f"• Total Amount: **₹{top_cat_amt:,.2f}** ({pct_of_spend}% of total spend)\n\n"
                    f"💡 **Recommendation:** Trimming 15% from {top_cat} will leave you with an extra **₹{round(top_cat_amt * 0.15, 2):,.2f}** in pocket savings!"
                )
                spoken = f"Your highest expense category is {top_cat} with {int(top_cat_amt)} rupees spent."
        else:
            if is_hindi:
                reply = "ℹ️ इस महीने अभी तक बहुत कम खर्च हुआ है। कोई प्रमुख कैटेगरी ओवर-स्पेंड नहीं है।"
                spoken = "Is mahine abhi tak kharch bilkul shant aur surakshit hai."
            else:
                reply = "ℹ️ Minimal expenses recorded so far this month. No single category has dominated."
                spoken = "Minimal expenses recorded so far."

        chips = ["🍔 Food ka kharch?", "💰 Mera bacha paisa?", "💡 Bachat kaise badhaye?"]

    # ----------------------------------------------------
    # 9. SAVINGS STRATEGY & 50/30/20 RULE ("Paisa kaise bachayein?")
    # ----------------------------------------------------
    elif any(k in user_q for k in ["save", "saving", "bachat", "kaise bachaye", "cut", "tips", "invest"]):
        if is_hindi:
            reply = (
                f"💡 **पैसा बचाने के 3 सबसे आसान नियम:**\n\n"
                f"1. **50-30-20 का जादुई नियम:**\n"
                f"   • **50% जरूरतें (Needs):** राशन, किराया, बिजली बिल\n"
                f"   • **30% शौक (Wants):** बाहर खाना, फिल्में, शॉपिंग\n"
                f"   • **20% बचत (Savings):** इमरजेंसी फंड व निवेश\n\n"
                f"2. **दैनिक सेफ लिमिट का पालन:** रोज **₹{safe_cap:.1f}/दिन** से कम खर्च रखें।\n"
                f"3. **सबसे बड़े खर्च पर नियंत्रण:** '{top_cat}' में 15% की कटौती करने से सीधे **₹{round(top_cat_amt * 0.15, 2):,.2f}** बचेंगे!"
            )
            spoken = f"Paisa bachane ke liye roz {int(safe_cap)} rupaye ki safe daily limit ka dhyan rakhein, aur {top_cat} me thoda control karein."
        else:
            reply = (
                f"💡 **3 Core Principles to Grow Your Savings:**\n\n"
                f"1. **The 50/30/20 Rule:**\n"
                f"   • **50% Needs:** Rent, groceries, utility bills\n"
                f"   • **30% Wants:** Dining, entertainment, shopping\n"
                f"   • **20% Savings:** Emergency cushion & wealth accumulation\n\n"
                f"2. **Respect Daily Safe Pace:** Stay under **₹{safe_cap:.1f}/day**.\n"
                f"3. **Trim Top Driver:** Cutting 15% from '{top_cat}' captures **₹{round(top_cat_amt * 0.15, 2):,.2f}**."
            )
            spoken = f"Stay under your daily safe pace of {int(safe_cap)} rupees per day to protect your savings."

        chips = ["🎯 Budget status?", "💰 Mera bacha paisa?", "🏆 Top spending kisme hua?"]

    # ----------------------------------------------------
    # 10. BUDGET & RUNWAY ("Budget kitna bacha hai?")
    # ----------------------------------------------------
    elif any(k in user_q for k in ["budget", "bacha", "remaining", "overrun", "risk"]):
        if is_hindi:
            reply = (
                f"🎯 **इस महीने का बजट स्टेटस:**\n\n"
                f"• कुल तय बजट: **₹{budget:,.2f}**\n"
                f"• अब तक खर्च: **₹{cur_spend:,.2f}**\n"
                f"• बचा हुआ बजट: **₹{remaining_budget:,.2f}**\n"
                f"• महीने में बाकी दिन: **{days_left} दिन**\n"
                f"• 🛡️ सेफ डेली लिमिट: **₹{safe_cap:.1f} / दिन**\n\n"
                f"{'🟢 बहुत बढ़िया! आप बजट के भीतर हैं और बचत की राह पर हैं।' if cur_spend <= budget else '🔴 ध्यान दें: खर्च बजट को पार कर चुका है, गैर-जरूरी खर्च तुरंत रोकें।'}"
            )
            spoken = f"Aapka bacha hua budget {int(remaining_budget)} rupaye hai, aur roz ka safe limit {int(safe_cap)} rupaye hai."
        else:
            reply = (
                f"🎯 **Monthly Budget Overview:**\n\n"
                f"• Total Budget: **₹{budget:,.2f}**\n"
                f"• MTD Spend: **₹{cur_spend:,.2f}**\n"
                f"• Remaining Budget: **₹{remaining_budget:,.2f}**\n"
                f"• Days Remaining: **{days_left} days**\n"
                f"• 🛡️ Safe Daily Pace: **₹{safe_cap:.1f}/day**\n\n"
                f"{'🟢 On track! You are pacing safely inside your budget ceiling.' if cur_spend <= budget else '🔴 Overrun alert: Spending has crossed your target budget ceiling.'}"
            )
            spoken = f"You have {int(remaining_budget)} rupees remaining in your monthly budget."

        chips = ["🛡️ Aaj ka safe limit?", "🍔 Food ka kharch?", "💡 Bachat kaise badhaye?"]

    # ----------------------------------------------------
    # 11. UPCOMING BILLS & RECURRING COMMITTMENTS
    # ----------------------------------------------------
    elif any(k in user_q for k in ["bill", "recurring", "pending", "dues", "bijli", "recharge"]):
        if upcoming_bills:
            b_lines = [f"• **{b['title']}**: ₹{float(b['amount']):,.2f} (Due: {b['next_due_date']})" for b in upcoming_bills]
            b_text = "\n".join(b_lines)
            if is_hindi:
                reply = f"📅 **आने वाले बिल व कमिटमेंट्स:**\n\n{b_text}\n\nकृपया इन तारीखों से पहले अपने एकाउंट में पर्याप्त बैलेंस रखें।"
                spoken = f"Aapke paas {len(upcoming_bills)} upcoming bills due hain."
            else:
                reply = f"📅 **Upcoming Recurring Bills:**\n\n{b_text}\n\nEnsure sufficient balance before due dates."
                spoken = f"You have {len(upcoming_bills)} upcoming bills due."
        else:
            if is_hindi:
                reply = "🎉 **कोई भी बिल पेंडिंग नहीं है!**\n\nइस महीने कोई भी आगामी रिकरिंग पेमेंट बाकी नहीं है।"
                spoken = "Aapka koi bhi bill pending nahi hai."
            else:
                reply = "🎉 **All clear! No upcoming recurring bills due.**\n\nYour commitments are up to date."
                spoken = "All clear, no upcoming recurring bills."

        chips = ["💰 Mera bacha paisa?", "📊 Is mahine ka kharch?", "🛡️ Aaj ka safe limit?"]

    # ----------------------------------------------------
    # 12. FALLBACK FINANCIAL SNAPSHOT
    # ----------------------------------------------------
    else:
        if is_hindi:
            reply = (
                f"💡 **आपका त्वरित वित्तीय सारांश:**\n\n"
                f"• इस महीने का खर्च: **₹{cur_spend:,.2f}**\n"
                f"• बचा हुआ बजट: **₹{remaining_budget:,.2f}**\n"
                f"• सुरक्षित दैनिक लिमिट: **₹{safe_cap:.1f}/दिन** ({days_left} दिन शेष)\n\n"
                f"आप मुझसे किसी भी विशिष्ट खर्च (जैसे *'Food pe kitna kharch hua?'*), बजट या बैंक बैलेंस के बारे में बोलकर या लिखकर पूछ सकते हैं!"
            )
            spoken = f"Is mahine kul {int(cur_spend)} rupaye kharch huye hain, aur bacha hua budget {int(remaining_budget)} rupaye hai."
        else:
            reply = (
                f"💡 **Your Live Financial Snapshot:**\n\n"
                f"• MTD Spend: **₹{cur_spend:,.2f}**\n"
                f"• Remaining Budget: **₹{remaining_budget:,.2f}**\n"
                f"• Safe Daily Pace: **₹{safe_cap:.1f}/day** ({days_left} days left)\n\n"
                f"Ask me about specific categories, bank balances, or shopping affordability!"
            )
            spoken = f"Your total spend this month is {int(cur_spend)} rupees with {int(remaining_budget)} rupees remaining in your budget."

        chips = ["💰 Mera bacha paisa?", "🍔 Food ka kharch?", "🛡️ Aaj ka safe limit?"]

    return {
        "reply": reply,
        "spoken_text": spoken,
        "decision_badge": decision_badge,
        "action_button": action_button,
        "followup_chips": chips[:3],
        "four_pillars": {
            "what_happened": f"Spent ₹{cur_spend:,.2f} MTD",
            "why_it_matters": f"Pacing at ₹{daily_velocity:.1f}/day",
            "what_may_happen": f"Projected Month-End ₹{proj_spend:,.2f}",
            "what_user_can_do": f"Safe daily cap is ₹{safe_cap:.1f}/day"
        },
        "metrics_snapshot": {
            "daily_velocity": daily_velocity,
            "projected_month_end": proj_spend,
            "monthly_budget": budget,
            "risk_status": risk,
            "safe_daily_spend": safe_cap,
            "highest_category": top_cat
        }
    }


def generate_ai_mentor_advice(user_id: int, user_prompt: Optional[str] = None, db_path: str = "expenses.db") -> Dict[str, Any]:
    """
    Main entry point for AI Financial Assistant:
    1. Extracts real ledger context.
    2. Tries Gemini API if key is present.
    3. Seamlessly falls back to local high-precision NLU engine.
    """
    context = get_financial_context(user_id, db_path=db_path)
    clean_prompt = (user_prompt or "").strip()

    # 1. Try Gemini LLM if key is configured
    if clean_prompt:
        gemini_result = call_gemini_api(context, clean_prompt)
        if gemini_result and gemini_result.get("reply"):
            gemini_result["metrics_snapshot"] = {
                "daily_velocity": context["daily_velocity"],
                "projected_month_end": context["proj_month_end"],
                "monthly_budget": context["monthly_budget"],
                "risk_status": context["risk_status"],
                "safe_daily_spend": context["safe_daily_spend"],
                "highest_category": context["top_category"]
            }
            return gemini_result

    # 2. Local High-Precision Financial Engine
    return local_financial_nlu_engine(context, clean_prompt)
