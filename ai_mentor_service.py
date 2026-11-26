# -*- coding: utf-8 -*-
"""
FINLY 5.0 — CONVERSATIONAL AI FINANCIAL ASSISTANT
==================================================
ChatGPT / Gemini-grade Personal Finance Companion for Expense Tracker Pro:
1. Full Grounded Ledger Intelligence (Daily/Weekly/Monthly/All-Time, Categories,
   Subcategories, Payment Channels [Cash/UPI/Cards], Note Search, Budgets, Goals, Bills, 6M Trends).
2. Multi-Turn Conversation Memory (follows up naturally across turns).
3. Multi-Provider LLM Brain (Gemini 2.5/2.0 Flash, OpenAI GPT-4o-mini, Groq Llama 3.3, OpenRouter)
   using strict JSON structured responses & dynamic ledger lookup injection.
4. Upgraded High-Precision Local Conversational Engine (Zero-Fail Offline/No-Key Backup)
   with 3-way language mirroring (Devanagari Hindi, Hinglish, English), natural conversational
   greetings, dynamic SQL filtering, and zero fixed-template repetition.
"""

import calendar
from datetime import date, datetime, timedelta
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.request

import database
import forecasting_engine


def _normalize_payment_channel(name: Optional[str]) -> str:
    if not name:
        return "Cash"
    low = str(name).lower().strip()
    if "cash" in low:
        return "Cash"
    if "card" in low or "credit" in low or "debit" in low:
        return "Cards"
    if any(k in low for k in ("upi", "bank", "online", "account", "vault")):
        return "UPI"
    return "Cash"


def _parse_client_date(client_date: Optional[str]) -> date:
    if client_date:
        try:
            return datetime.strptime(str(client_date).strip()[:10], "%Y-%m-%d").date()
        except Exception:
            pass
    return date.today()


def get_mom_analysis(user_id: int, target_date: Optional[Any] = None, db_path: str = "expenses.db") -> Dict[str, Any]:
    """Month-over-Month (MoM) Category Variance Analysis."""
    if target_date is None:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = _parse_client_date(target_date)

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


def get_six_month_trends(user_id: int, db_path: str = "expenses.db", target_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """Fetches rolling 6 calendar months income vs expense for historical trend analysis."""
    today = target_date or date.today()
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


def get_financial_context(user_id: int, db_path: str = "expenses.db", target_date: Optional[Any] = None) -> Dict[str, Any]:
    """
    Comprehensive RAG Context Builder:
    Extracts complete, mathematically grounded ledger intelligence across all time windows,
    categories, subcategories, payment channels (Cash/UPI/Cards), budgets, goals, and recent rows.
    """
    today = _parse_client_date(target_date) if isinstance(target_date, str) else (target_date or date.today())
    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    week_start_str = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    last_7d_str = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    month_pattern = f"{today.year:04d}-{today.month:02d}%"

    conn = database.get_db_connection()
    cursor = conn.cursor()

    forecast = forecasting_engine.calculate_month_end_forecast(user_id, target_date=today, db_path=db_path, conn=conn, use_cache=False)
    mom = get_mom_analysis(user_id, target_date=today, db_path=db_path)
    net_worth = database.get_net_worth_summary(user_id)
    cashflow = database.get_monthly_cashflow_summary(user_id, today.month, today.year)
    trends_6m = get_six_month_trends(user_id, db_path=db_path, target_date=today)

    user_name = "Friend"
    currency_symbol = "₹"
    currency_code = "INR"
    try:
        cursor.execute("SELECT name, currency_symbol, currency_code FROM users WHERE id = ?", (user_id,))
        u_row = cursor.fetchone()
        if u_row:
            if u_row["name"]:
                user_name = str(u_row["name"]).split()[0]
            if u_row["currency_symbol"]:
                currency_symbol = u_row["currency_symbol"]
            if u_row["currency_code"]:
                currency_code = u_row["currency_code"]
    except Exception:
        pass

    # Accounts (normalized payment labels + raw names)
    cursor.execute("SELECT id, name, current_balance, account_type FROM accounts WHERE user_id = ? AND is_active = 1", (user_id,))
    accounts = []
    for r in cursor.fetchall():
        d = dict(r)
        d["channel"] = _normalize_payment_channel(d.get("name"))
        d["current_balance"] = round(float(d.get("current_balance") or 0.0), 2)
        accounts.append(d)

    # Today's & Yesterday's expenses + weekly spend
    cursor.execute("""
        SELECT t.id, t.amount, t.date, t.transaction_type, COALESCE(t.note, '') as note,
               COALESCE(c.name, 'Uncategorized') as category_name,
               COALESCE(s.name, '') as subcategory_name,
               COALESCE(a.name, 'Cash') as account_name
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN subcategories s ON t.subcategory_id = s.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ? AND SUBSTR(t.date, 1, 10) IN (?, ?)
        ORDER BY t.date DESC, t.id DESC
    """, (user_id, today_str, yesterday_str))
    recent_2d = [dict(r) for r in cursor.fetchall()]

    today_txs = []
    yesterday_txs = []
    today_spend = 0.0
    yesterday_spend = 0.0
    for tx in recent_2d:
        tx["account_name"] = _normalize_payment_channel(tx.get("account_name"))
        tx["amount"] = round(float(tx["amount"] or 0.0), 2)
        d_s = str(tx["date"])[:10]
        if d_s == today_str:
            today_txs.append(tx)
            if tx["transaction_type"] == "EXPENSE":
                today_spend += tx["amount"]
        elif d_s == yesterday_str:
            yesterday_txs.append(tx)
            if tx["transaction_type"] == "EXPENSE":
                yesterday_spend += tx["amount"]

    # This week & Last 7 days expense spend
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0.0) as amt, COUNT(id) as cnt
        FROM transactions
        WHERE user_id = ? AND transaction_type = 'EXPENSE' AND SUBSTR(date, 1, 10) >= ? AND SUBSTR(date, 1, 10) <= ?
    """, (user_id, week_start_str, today_str))
    w_row = cursor.fetchone()
    this_week_spend = round(float(w_row["amt"] or 0.0), 2)
    this_week_count = int(w_row["cnt"] or 0)

    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0.0) as amt, COUNT(id) as cnt
        FROM transactions
        WHERE user_id = ? AND transaction_type = 'EXPENSE' AND SUBSTR(date, 1, 10) >= ? AND SUBSTR(date, 1, 10) <= ?
    """, (user_id, last_7d_str, today_str))
    l7_row = cursor.fetchone()
    last_7d_spend = round(float(l7_row["amt"] or 0.0), 2)
    last_7d_count = int(l7_row["cnt"] or 0)

    # Category breakdown MTD (EXPENSE)
    cursor.execute("""
        SELECT c.id as category_id,
               COALESCE(c.name, 'Uncategorized') as category_name,
               SUM(t.amount) as total_amount,
               COUNT(t.id) as tx_count
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        GROUP BY c.id, c.name
        ORDER BY total_amount DESC
    """, (user_id, month_pattern))
    cat_rows = cursor.fetchall()
    category_spends = {
        r["category_name"].lower(): {
            "category_id": r["category_id"],
            "name": r["category_name"],
            "amount": round(float(r["total_amount"] or 0.0), 2),
            "count": int(r["tx_count"] or 0),
        }
        for r in cat_rows
    }

    # Subcategory breakdown MTD (EXPENSE)
    cursor.execute("""
        SELECT COALESCE(s.name, '') as subcategory_name,
               COALESCE(c.name, 'Uncategorized') as category_name,
               SUM(t.amount) as total_amount,
               COUNT(t.id) as tx_count
        FROM transactions t
        LEFT JOIN subcategories s ON t.subcategory_id = s.id
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ? AND s.name IS NOT NULL AND s.name != ''
        GROUP BY s.id, s.name, c.name
        ORDER BY total_amount DESC
    """, (user_id, month_pattern))
    subcategory_spends = {
        r["subcategory_name"].lower(): {
            "name": r["subcategory_name"],
            "category_name": r["category_name"],
            "amount": round(float(r["total_amount"] or 0.0), 2),
            "count": int(r["tx_count"] or 0),
        }
        for r in cursor.fetchall()
    }

    # Income breakdown MTD by category
    cursor.execute("""
        SELECT COALESCE(c.name, 'Income') as category_name,
               SUM(t.amount) as total_amount,
               COUNT(t.id) as tx_count
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'INCOME' AND t.date LIKE ?
        GROUP BY c.id, c.name
        ORDER BY total_amount DESC
    """, (user_id, month_pattern))
    income_by_category = {
        r["category_name"].lower(): {
            "name": r["category_name"],
            "amount": round(float(r["total_amount"] or 0.0), 2),
            "count": int(r["tx_count"] or 0),
        }
        for r in cursor.fetchall()
    }

    # Payment channel breakdown MTD (Cash / UPI / Cards)
    cursor.execute("""
        SELECT COALESCE(a.name, 'Cash') as account_name,
               SUM(t.amount) as total_amount,
               COUNT(t.id) as tx_count
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        GROUP BY a.name
    """, (user_id, month_pattern))
    payment_method_spends = {
        "Cash": {"amount": 0.0, "count": 0},
        "UPI": {"amount": 0.0, "count": 0},
        "Cards": {"amount": 0.0, "count": 0},
    }
    for r in cursor.fetchall():
        ch = _normalize_payment_channel(r["account_name"])
        payment_method_spends[ch]["amount"] = round(payment_method_spends[ch]["amount"] + float(r["total_amount"] or 0.0), 2)
        payment_method_spends[ch]["count"] += int(r["tx_count"] or 0)

    # Category budget limits for current month
    cursor.execute("""
        SELECT b.category_id, c.name as category_name, b.amount as limit_amount
        FROM budgets b
        JOIN categories c ON b.category_id = c.id
        WHERE b.user_id = ? AND b.month = ? AND b.year = ? AND b.category_id IS NOT NULL
    """, (user_id, today.month, today.year))
    category_budgets = []
    for r in cursor.fetchall():
        cname = r["category_name"]
        lim = round(float(r["limit_amount"] or 0.0), 2)
        spent = category_spends.get(cname.lower(), {}).get("amount", 0.0)
        category_budgets.append({
            "category": cname,
            "limit": lim,
            "spent": spent,
            "remaining": round(max(0.0, lim - spent), 2),
            "pct_used": round((spent / lim * 100), 1) if lim > 0 else 0.0,
            "exceeded": spent > lim and lim > 0,
        })

    # Largest single expense this month
    cursor.execute("""
        SELECT t.amount, t.date, COALESCE(t.note, '') as note,
               COALESCE(c.name, 'Uncategorized') as category_name,
               COALESCE(s.name, '') as subcategory_name,
               COALESCE(a.name, 'Cash') as account_name
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN subcategories s ON t.subcategory_id = s.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        ORDER BY t.amount DESC LIMIT 1
    """, (user_id, month_pattern))
    lg_row = cursor.fetchone()
    largest_expense_mtd = dict(lg_row) if lg_row else None
    if largest_expense_mtd:
        largest_expense_mtd["amount"] = round(float(largest_expense_mtd["amount"] or 0.0), 2)
        largest_expense_mtd["account_name"] = _normalize_payment_channel(largest_expense_mtd.get("account_name"))

    # Last 30 transactions (rich details for ChatGPT-style inspection)
    cursor.execute("""
        SELECT t.id, COALESCE(t.note, '') as note, t.amount, t.date, t.transaction_type,
               COALESCE(c.name, 'Uncategorized') as category_name,
               COALESCE(s.name, '') as subcategory_name,
               COALESCE(a.name, 'Cash') as account_name
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN subcategories s ON t.subcategory_id = s.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ?
        ORDER BY t.date DESC, t.id DESC LIMIT 30
    """, (user_id,))
    recent_txs = []
    for r in cursor.fetchall():
        tx = dict(r)
        tx["amount"] = round(float(tx["amount"] or 0.0), 2)
        tx["account_name"] = _normalize_payment_channel(tx.get("account_name"))
        recent_txs.append(tx)

    # Available categories & subcategories (excluding user-deleted)
    cursor.execute("""
        SELECT id, name, type FROM categories
        WHERE (user_id IS NULL OR user_id = ?)
          AND id NOT IN (SELECT category_id FROM user_hidden_categories WHERE user_id = ?)
        ORDER BY is_default DESC, name ASC
    """, (user_id, user_id))
    avail_cats = [dict(r) for r in cursor.fetchall()]
    avail_subcats = []
    if avail_cats:
        cat_ids = [c["id"] for c in avail_cats]
        ph = ",".join("?" for _ in cat_ids)
        cat_map = {c["id"]: c["name"] for c in avail_cats}
        cursor.execute(f"""
            SELECT id, category_id, name FROM subcategories
            WHERE category_id IN ({ph})
              AND id NOT IN (SELECT subcategory_id FROM user_hidden_subcategories WHERE user_id = ?)
        """, tuple(cat_ids + [user_id]))
        for sr in cursor.fetchall():
            avail_subcats.append({
                "id": sr["id"],
                "name": sr["name"],
                "category_id": sr["category_id"],
                "category_name": cat_map.get(sr["category_id"], ""),
            })

    # Upcoming recurring bills
    cursor.execute("SELECT title, amount, next_due_date FROM recurring_bills WHERE user_id = ? AND is_active = 1 AND auto_paid = 0 ORDER BY next_due_date ASC", (user_id,))
    upcoming_bills = [dict(r) for r in cursor.fetchall()]

    # Active savings goals
    cursor.execute("SELECT title, target_amount, current_amount, target_date FROM financial_goals WHERE user_id = ? AND is_completed = 0", (user_id,))
    active_goals = []
    for r in cursor.fetchall():
        g = dict(r)
        tgt = float(g.get("target_amount") or 0.0)
        cur = float(g.get("current_amount") or 0.0)
        g["progress_pct"] = round((cur / tgt * 100), 1) if tgt > 0 else 0.0
        active_goals.append(g)

    conn.close()

    budget = float(forecast.get("monthly_budget", 0.0) or 0.0)
    cur_spend = float(forecast.get("mtd_actual_spend", 0.0) or 0.0)
    remaining_budget = max(0.0, round(budget - cur_spend, 2)) if budget > 0 else float(net_worth.get("total_assets", 0.0) or 0.0)

    return {
        "user_name": user_name,
        "currency": currency_symbol,
        "currency_code": currency_code,
        "date_today": today_str,
        "yesterday_date": yesterday_str,
        "week_start_date": week_start_str,
        "month_label": today.strftime("%B %Y"),
        "days_in_month": calendar.monthrange(today.year, today.month)[1],
        "days_left": forecast.get("days_remaining", 0),
        "today_spend": round(today_spend, 2),
        "today_transactions": today_txs,
        "yesterday_spend": round(yesterday_spend, 2),
        "yesterday_transactions": yesterday_txs,
        "this_week_spend": this_week_spend,
        "this_week_count": this_week_count,
        "last_7d_spend": last_7d_spend,
        "last_7d_count": last_7d_count,
        "cur_spend": round(cur_spend, 2),
        "mtd_tx_count": mom.get("current_count", 0),
        "largest_expense_mtd": largest_expense_mtd,
        "monthly_budget": round(budget, 2),
        "remaining_budget": round(remaining_budget, 2),
        "daily_velocity": float(forecast.get("daily_spending_velocity", 0.0) or 0.0),
        "safe_daily_spend": float(forecast.get("safe_daily_spend", forecast.get("safe_daily_cap", 0.0)) or 0.0),
        "proj_month_end": float(forecast.get("projected_month_end_spend", 0.0) or 0.0),
        "risk_status": forecast.get("risk_status", "SAFE"),
        "top_category": mom.get("highest_category", "None"),
        "top_category_amount": float(mom.get("highest_category_amount", 0.0) or 0.0),
        "prev_month_label": mom.get("previous_month", ""),
        "prev_month_spend": float(mom.get("previous_total", 0.0) or 0.0),
        "mom_diff": float(mom.get("overall_difference", 0.0) or 0.0),
        "mom_change_pct": float(mom.get("overall_change_pct", 0.0) or 0.0),
        "accounts": accounts,
        "total_net_worth": float(net_worth.get("net_worth", 0.0) or 0.0),
        "total_assets": float(net_worth.get("total_assets", 0.0) or 0.0),
        "monthly_income": float(cashflow.get("income", 0.0) or 0.0),
        "monthly_transfers": float(cashflow.get("transfers", 0.0) or 0.0),
        "net_savings": float(cashflow.get("net_savings", 0.0) or 0.0),
        "savings_rate_pct": float(cashflow.get("savings_rate_pct", 0.0) or 0.0),
        "payment_method_spends": payment_method_spends,
        "category_spends": category_spends,
        "subcategory_spends": subcategory_spends,
        "income_by_category": income_by_category,
        "category_budgets": category_budgets,
        "recent_transactions": recent_txs,
        "upcoming_bills": upcoming_bills,
        "active_goals": active_goals,
        "trends_6m": trends_6m,
        "available_categories": avail_cats,
        "available_subcategories": avail_subcats,
    }


def _query_ledger_dynamic(
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category_name: Optional[str] = None,
    subcategory_name: Optional[str] = None,
    payment_channel: Optional[str] = None,
    tx_type: Optional[str] = "EXPENSE",
    search_term: Optional[str] = None,
) -> Dict[str, Any]:
    """Performs exact grounded SQL lookup across custom period/category/subcategory/payment/note filters."""
    sql = """
        SELECT t.id, t.date, t.transaction_type, t.amount, COALESCE(t.note, '') as note,
               COALESCE(c.name, 'Uncategorized') as category_name,
               COALESCE(s.name, '') as subcategory_name,
               COALESCE(a.name, 'Cash') as account_name
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN subcategories s ON t.subcategory_id = s.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ?
    """
    params: List[Any] = [user_id]
    if tx_type:
        sql += " AND t.transaction_type = ?"
        params.append(tx_type.upper())
    if start_date:
        sql += " AND SUBSTR(t.date, 1, 10) >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND SUBSTR(t.date, 1, 10) <= ?"
        params.append(end_date)
    if category_name:
        sql += " AND LOWER(COALESCE(c.name, '')) = LOWER(?)"
        params.append(category_name)
    if subcategory_name:
        sql += " AND LOWER(COALESCE(s.name, '')) = LOWER(?)"
        params.append(subcategory_name)
    if search_term:
        like_pat = f"%{search_term.lower()}%"
        sql += " AND (LOWER(COALESCE(t.note, '')) LIKE ? OR LOWER(COALESCE(c.name, '')) LIKE ? OR LOWER(COALESCE(s.name, '')) LIKE ?)"
        params.extend([like_pat, like_pat, like_pat])

    sql += " ORDER BY t.date DESC, t.id DESC LIMIT 200"

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, tuple(params))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    matched = []
    for r in rows:
        r["account_name"] = _normalize_payment_channel(r.get("account_name"))
        r["amount"] = round(float(r.get("amount") or 0.0), 2)
        if payment_channel and r["account_name"].lower() != payment_channel.lower():
            continue
        matched.append(r)

    total = round(sum(x["amount"] for x in matched), 2)
    return {
        "total": total,
        "count": len(matched),
        "transactions": matched[:15],
    }


def _detect_language_mode(user_prompt: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    """
    Returns exact language/script mode:
    - 'hi': Devanagari Hindi script
    - 'hinglish': Conversational Romanized Hindi
    - 'en': English
    """
    txt = (user_prompt or "").strip()
    if re.search(r"[\u0900-\u097F]", txt):
        return "hi"

    tokens = set(re.findall(r"[a-z]+", txt.lower()))
    hinglish_markers = {
        "kharch", "kharcha", "kharche", "kitna", "kitni", "kitne", "kaisa", "kaisi", "kaise",
        "batao", "bata", "bataye", "batayein", "bataiye", "kya", "mera", "meri", "mere",
        "mujhe", "mujhko", "hum", "hume", "aaj", "kal", "parso", "paisa", "paise", "rupay",
        "rupaye", "bhai", "bhaiya", "dost", "yaar", "hai", "hain", "tha", "thi", "the",
        "hua", "huye", "hui", "karo", "kar", "karna", "chahiye", "lu", "lelu", "sakta",
        "sakti", "sakte", "bacha", "bache", "bachat", "bachaye", "bachayein", "mahina",
        "mahine", "hafta", "hafte", "khareed", "kharid", "kharidu", "khareedu", "namaste",
        "pranam", "shukriya", "dhanyawad", "thik", "theek", "kaha", "kahan", "kisme",
        "kispe", "kaun", "kaunsa", "kyu", "kyun", "kyon", "haan", "nahi", "nhi", "mat",
        "sabse", "zyada", "jyada", "kam", "dekho", "dikhao", "likh", "daal", "jod",
        "abhi", "ab", "tak", "se", "pe", "mein", "me", "aur", "par", "kiraya", "khana",
        "dawa", "dawai", "bijli", "chai", "sabzi", "doodh", "gadi", "padhai", "udhar",
        "kholo", "khol", "set", "karein", "karenge", "bhejo", "sahi", "galat"
    }
    # Require explicit Hinglish markers (note 'me', 'set' can be English words too -> keep 'set' out and check 'me' only alongside another marker or Hindi context!)
    strict_hinglish = hinglish_markers - {"me", "set", "par", "kar", "hum", "ha"}
    if tokens & strict_hinglish:
        return "hinglish"

    # Multi-word safe Hinglish phrases even with short particles
    low = txt.lower()
    if any(p in low for p in ["kitna ", "kya hai", "kaise ", "batao", "kharch", "paisa", "aaj ", "kal "]):
        return "hinglish"

    # Follow-up short prompt inheritance
    if len(tokens) <= 2 and history:
        for msg in reversed(history):
            if msg.get("role") == "user":
                prev = msg.get("content", "")
                if re.search(r"[\u0900-\u097F]", prev):
                    return "hi"
                prev_tok = set(re.findall(r"[a-z]+", prev.lower()))
                if prev_tok & strict_hinglish:
                    return "hinglish"
                break

    return "en"


def _format_currency(amount: float, sym: str = "₹") -> str:
    return f"{sym}{amount:,.2f}"


def _clean_llm_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """Extracts structured JSON cleanly even if wrapped in markdown fences."""
    s = (raw_text or "").strip()
    if not s:
        return None
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict) and parsed.get("reply"):
            return parsed
    except Exception:
        # Try extracting first {...} JSON block
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, dict) and parsed.get("reply"):
                    return parsed
            except Exception:
                pass
    # Plain text response fallback -> wrap cleanly
    return {"reply": s}


def _build_llm_system_prompt(context: Dict[str, Any], targeted_lookup: Optional[Dict[str, Any]], lang_mode: str) -> str:
    lang_rule = {
        "hi": "The user wrote in Devanagari Hindi. Reply naturally in fluent Devanagari Hindi.",
        "hinglish": "The user wrote in conversational Hinglish (Romanized Hindi + English). Reply naturally in friendly Hinglish.",
        "en": "The user wrote in English. Reply in crisp, natural English.",
    }.get(lang_mode, "Match the user's exact language and script.")

    compact_ctx = {
        "user_name": context["user_name"],
        "currency": context["currency"],
        "dates": {
            "today": context["date_today"],
            "yesterday": context["yesterday_date"],
            "month": context["month_label"],
            "days_left": context["days_left"],
        },
        "summary": {
            "today_spend": context["today_spend"],
            "yesterday_spend": context["yesterday_spend"],
            "this_week_spend": context["this_week_spend"],
            "last_7d_spend": context["last_7d_spend"],
            "mtd_spend": context["cur_spend"],
            "mtd_tx_count": context["mtd_tx_count"],
            "monthly_income": context["monthly_income"],
            "net_savings": context["net_savings"],
            "savings_rate_pct": context["savings_rate_pct"],
            "monthly_budget": context["monthly_budget"],
            "remaining_budget": context["remaining_budget"],
            "safe_daily_spend": context["safe_daily_spend"],
            "daily_velocity": context["daily_velocity"],
            "projected_month_end": context["proj_month_end"],
            "risk_status": context["risk_status"],
            "prev_month_spend": context["prev_month_spend"],
            "mom_change_pct": context["mom_change_pct"],
            "top_category": context["top_category"],
            "top_category_amount": context["top_category_amount"],
            "largest_expense_mtd": context["largest_expense_mtd"],
        },
        "accounts": context["accounts"],
        "total_liquid_balance": context["total_assets"],
        "payment_method_spends_mtd": context["payment_method_spends"],
        "category_spends_mtd": list(context["category_spends"].values()),
        "subcategory_spends_mtd": list(context["subcategory_spends"].values()),
        "income_by_category_mtd": list(context["income_by_category"].values()),
        "category_budgets_mtd": context["category_budgets"],
        "today_transactions": context["today_transactions"],
        "yesterday_transactions": context["yesterday_transactions"],
        "recent_30_transactions": context["recent_transactions"],
        "upcoming_bills": context["upcoming_bills"],
        "active_goals": context["active_goals"],
        "trends_6m": context["trends_6m"],
        "available_categories": [
            {"id": c["id"], "name": c["name"], "type": c["type"]}
            for c in context["available_categories"]
        ],
    }
    if targeted_lookup:
        compact_ctx["targeted_sql_lookup"] = targeted_lookup

    return f"""You are Finly — the intelligent AI companion inside Expense Tracker Pro (ChatGPT-level naturalness, precision, and warmth).

HOW TO RESPOND (CRITICAL RULES):
1. Answer ONLY what the user asked cleanly and naturally — DO NOT dump unrequested multi-line financial summaries on casual greetings ("hi", "hello", "how are you", "thanks") or unrelated chat.
2. Match response length to intent:
   - Greeting / casual chat -> 1-2 friendly natural sentences (just like ChatGPT).
   - Direct factual query ("Aaj kitna kharch hua?", "UPI spend?", "Last tx?") -> Direct, crisp, accurate answer first with exact numbers/items.
   - Analytical / coaching / "detail me" / "why" / "advice" query -> Clear bullet breakdown and practical actionable advice.
3. Strict Mathematical Truth: Every rupee/dollar figure, transaction, balance, budget, goal, or category spend MUST come strictly from REAL_LEDGER_CONTEXT below. Never invent numbers.
4. Language Mirroring: {lang_rule}
5. Capabilities:
   - You can answer general personal finance questions (SIP, 50/30/20, CIBIL, EMI payoff, emergency fund, budgeting), analyze any timeframe/category/subcategory/payment mode in the ledger, check purchase affordability, and hold normal friendly conversation naturally!
   - If the user wants to record a transaction (e.g., "Add 150 chai via UPI"), include `"action_button"` with `type: "OPEN_QUICK_ENTRY"`, `amount`, `transaction_type` ("EXPENSE"|"INCOME"), `category`, `account_name` ("Cash"|"UPI"|"Cards"), `note`.
   - If the user wants to view a screen, you may include `type: "NAVIGATE"` with `target: "tab-home"|"tab-analytics"|"tab-budgets"|"tab-history"`.

OUTPUT FORMAT:
Return a valid JSON object ONLY with keys:
- "reply": string (Markdown supported cleanly: bold **text**, bullets •, headings)
- "spoken_text": string (short clean voice-friendly sentence in the exact reply language without markdown)
- "followup_chips": array of 2-3 short contextual next questions the user might tap (max 34 chars each)
- "decision_badge": optional null OR {{"type": "SAFE"|"CAUTION"|"DANGER", "label": "SHORT BADGE"}}
- "action_button": optional null OR {{"label": "...", "type": "OPEN_QUICK_ENTRY"|"NAVIGATE", ...}}

REAL_LEDGER_CONTEXT:
{json.dumps(compact_ctx, ensure_ascii=False)}"""


def _post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int = 12) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _format_llm_output(parsed: Dict[str, Any], context: Dict[str, Any], lang_mode: str, provider: str) -> Dict[str, Any]:
    reply = str(parsed.get("reply") or "").strip()
    spoken = str(parsed.get("spoken_text") or "").strip()
    if not spoken:
        spoken = re.sub(r"[*_#`•>\[\]]", "", reply)
        spoken = re.sub(r"\s+", " ", spoken).strip()[:280]

    chips = parsed.get("followup_chips")
    if not isinstance(chips, list) or len(chips) == 0:
        chips = (
            ["आज का खर्च?", "मेरा बजट स्टेटस?", "टॉप खर्च किसमें?"]
            if lang_mode == "hi"
            else (["Aaj ka kharcha?", "Bacha hua budget?", "UPI pe kitna gaya?"] if lang_mode == "hinglish"
                  else ["Today's spend?", "Budget status?", "Top spending?"])
        )
    else:
        chips = [str(c).strip() for c in chips if str(c).strip()][:3]

    return {
        "reply": reply,
        "spoken_text": spoken[:320],
        "decision_badge": parsed.get("decision_badge"),
        "action_button": parsed.get("action_button"),
        "followup_chips": chips,
        "engine_mode": "llm",
        "provider": provider,
    }


def call_llm_engine(
    context: Dict[str, Any],
    user_prompt: str,
    history: Optional[List[Dict[str, str]]] = None,
    targeted_lookup: Optional[Dict[str, Any]] = None,
    lang_mode: str = "en",
) -> Optional[Dict[str, Any]]:
    """
    Calls the configured Cloud LLM (Gemini 2.5/2.0 Flash, OpenAI, Groq, or OpenRouter)
    with multi-turn conversation history and complete grounded RAG ledger context.
    """
    system_prompt = _build_llm_system_prompt(context, targeted_lookup, lang_mode)
    clean_history = []
    for m in (history or [])[-10:]:
        role = m.get("role")
        txt = (m.get("content") or "").strip()
        if role in ("user", "assistant") and txt:
            clean_history.append({"role": role, "content": txt[:1200]})

    # 1. Google Gemini API (gemini-2.5-flash -> gemini-2.0-flash)
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if gemini_key:
        contents = []
        for m in clean_history:
            contents.append({
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            })
        contents.append({"role": "user", "parts": [{"text": user_prompt}]})

        for model_name in ("gemini-2.5-flash", "gemini-2.0-flash"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.5,
                    "maxOutputTokens": 700,
                    "responseMimeType": "application/json",
                },
            }
            try:
                data = _post_json(url, {"Content-Type": "application/json"}, payload, timeout=12)
                raw = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = _clean_llm_json(raw)
                if parsed:
                    return _format_llm_output(parsed, context, lang_mode, f"gemini:{model_name}")
            except Exception:
                continue

    # 2. OpenAI API / Groq API / OpenRouter API (OpenAI-compatible Chat Completions)
    openai_key = os.environ.get("OPENAI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")

    providers = []
    if openai_key:
        providers.append((
            "openai",
            "https://api.openai.com/v1/chat/completions",
            openai_key,
            os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        ))
    if groq_key:
        providers.append((
            "groq",
            "https://api.groq.com/openai/v1/chat/completions",
            groq_key,
            os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        ))
    if openrouter_key:
        providers.append((
            "openrouter",
            "https://openrouter.ai/api/v1/chat/completions",
            openrouter_key,
            os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        ))

    if providers:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(clean_history)
        messages.append({"role": "user", "content": user_prompt})
        for prov_name, url, key, model_id in providers:
            payload = {
                "model": model_id,
                "messages": messages,
                "temperature": 0.5,
                "max_tokens": 700,
                "response_format": {"type": "json_object"},
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            }
            try:
                data = _post_json(url, headers, payload, timeout=12)
                raw = data["choices"][0]["message"]["content"]
                parsed = _clean_llm_json(raw)
                if parsed:
                    return _format_llm_output(parsed, context, lang_mode, f"{prov_name}:{model_id}")
            except Exception:
                continue

    return None


def call_gemini_api(context: Dict[str, Any], user_prompt: str, history: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, Any]]:
    """Legacy-compatible alias backed by call_llm_engine."""
    lang_mode = _detect_language_mode(user_prompt, history)
    return call_llm_engine(context, user_prompt, history=history, lang_mode=lang_mode)


def _extract_time_window(user_q: str, today: date) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parses natural English/Hinglish/Hindi date references into (start_date, end_date, label)."""
    low = user_q.lower()
    if any(w in low for w in ("parso", "day before yesterday")):
        d = (today - timedelta(days=2)).strftime("%Y-%m-%d")
        return d, d, "parso"
    if any(k in low for k in ("aaj", "today", "आज")):
        d = today.strftime("%Y-%m-%d")
        return d, d, "today"
    if any(k in low for k in ("kal", "yesterday", "कल")):
        d = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        return d, d, "yesterday"
    if any(p in low for p in ("last 7 days", "past 7 days", "pichle 7 din", "पिछले 7 दिन", "7 din", "7 days")):
        return (today - timedelta(days=6)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), "last_7d"
    if any(p in low for p in ("this week", "is hafte", "week", "hafta", "hafte", "सप्ताह", "हफ्ते")):
        ws = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        return ws, today.strftime("%Y-%m-%d"), "this_week"
    if any(p in low for p in ("last month", "previous month", "pichle mahine", "pichla mahina", "पिछले महीने")):
        m = today.month - 1 if today.month > 1 else 12
        y = today.year if today.month > 1 else today.year - 1
        last_day = calendar.monthrange(y, m)[1]
        return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last_day:02d}", "last_month"
    if any(p in low for p in ("all time", "all-time", "overall", "ab tak", "kul milakar", "now till", "poora", "अब तक")):
        return None, None, "all_time"
    if any(p in low for p in ("this month", "is mahine", "iss mahine", "current month", "month", "mahine", "महीने")):
        return f"{today.year:04d}-{today.month:02d}-01", today.strftime("%Y-%m-%d"), "this_month"

    # Specific ISO date YYYY-MM-DD
    m_iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", low)
    if m_iso:
        return m_iso.group(1), m_iso.group(1), m_iso.group(1)

    return None, None, None


def _match_entity_filters(user_q: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Matches category (default or custom), subcategory, payment channel, and aliases cleanly."""
    low = user_q.lower()
    tokens = set(re.findall(r"[a-z0-9]+", low))

    # 1. Exact dynamic match against user's real categories (custom + default)
    matched_category = None
    best_len = 0
    for cat in context.get("available_categories", []):
        cname = cat["name"]
        clow = cname.lower()
        cat_toks = re.findall(r"[a-z0-9]+", clow)
        if clow in low and len(clow) > best_len:
            matched_category = cname
            best_len = len(clow)
        elif cat_toks and any(ct in tokens for ct in cat_toks if len(ct) >= 3) and len(clow) > best_len:
            matched_category = cname
            best_len = len(clow)

    # Alias mapping -> resolves colloquial terms (chai/swiggy -> Food & Dining, petrol -> Transportation/Fuel, etc.)
    if not matched_category:
        colloquial_groups = [
            (["food", "dining", "meal", "khana", "खाना", "खानपान", "lunch", "dinner", "breakfast", "swiggy", "zomato", "restaurant", "chai", "coffee", "snack", "pizza", "burger", "biryani"], ["food", "dining"]),
            (["grocery", "groceries", "kirana", "sabzi", "सब्जी", "ration", "milk", "doodh", "fruit", "vegetable"], ["food", "grocer"]),
            (["transport", "cab", "uber", "ola", "petrol", "diesel", "fuel", "auto", "metro", "bus", "train", "gadi", "गाड़ी", "bike", "scooter"], ["transport", "fuel", "bike"]),
            (["shopping", "clothes", "kapde", "कपड़े", "amazon", "flipkart", "myntra", "shoes", "mall"], ["shop"]),
            (["house", "housing", "rent", "kiraya", "किराया", "bijli", "electricity", "water", "wifi", "internet", "recharge", "gas", "cylinder"], ["hous", "rent", "util"]),
            (["entertainment", "movie", "cinema", "netflix", "prime", "hotstar", "game", "party"], ["entertain", "movie"]),
            (["health", "medical", "medicine", "doctor", "hospital", "pharmacy", "dawa", "दवा", "gym", "fitness"], ["health", "medic"]),
            (["education", "school", "college", "tuition", "fees", "course", "books", "padhai", "पढ़ाई"], ["educat", "book"]),
            (["emi", "loan", "repayment", "kist", "debt", "mutual", "sip", "stock", "investment", "financial"], ["emi", "loan", "finan"]),
            (["personal", "gift", "salon", "barber", "grooming"], ["person"]),
            (["salary", "वेतन", "income", "freelance", "business", "bonus"], ["salary", "business", "freelance"]),
        ]
        avail_lower = [(c["name"], c["name"].lower()) for c in context.get("available_categories", [])]
        for user_terms, target_fragments in colloquial_groups:
            if any((t in tokens or t in low) for t in user_terms):
                for orig_name, lname in avail_lower:
                    if any(frag in lname for frag in target_fragments):
                        matched_category = orig_name
                        break
                if matched_category:
                    break

    # 2. Match real subcategories dynamically
    matched_subcategory = None
    for sub in context.get("available_subcategories", []):
        sname = sub["name"].lower()
        if sname in low and len(sname) >= 3:
            matched_subcategory = sub["name"]
            if not matched_category:
                matched_category = sub.get("category_name") or None
            break

    # 3. Payment channel match
    payment_channel = None
    if any(k in tokens for k in ("upi", "online", "gpay", "phonepe", "paytm")):
        payment_channel = "UPI"
    elif "cash" in tokens or "नकद" in low:
        payment_channel = "Cash"
    elif any(k in tokens for k in ("card", "cards", "credit", "debit")):
        payment_channel = "Cards"

    return {
        "category": matched_category,
        "subcategory": matched_subcategory,
        "payment_channel": payment_channel,
    }


def _infer_followup_carryover(user_q: str, history: Optional[List[Dict[str, str]]], today: date) -> Dict[str, Any]:
    """Carries over date/category/topic when user asks short follow-ups like 'aur kal?', 'upi se?', 'detail me?'."""
    low = user_q.lower().strip()
    tokens = re.findall(r"[a-z0-9]+|[\u0900-\u097F]+", low)
    if len(tokens) > 5 or not history:
        return {}

    is_detail_followup = any(k in low for k in ("detail", "breakdown", "list", "kaunsa", "kya kya", "kispe", "explain", "visthar", "विस्तार"))
    prev_user = ""
    for m in reversed(history):
        if m.get("role") == "user":
            prev_user = (m.get("content") or "").strip()
            break
    if not prev_user:
        return {}

    return {"prev_user": prev_user, "wants_detail": is_detail_followup}


def smart_conversational_engine(
    user_id: int,
    context: Dict[str, Any],
    user_prompt: str,
    history: Optional[List[Dict[str, str]]] = None,
    lang_mode: str = "en",
) -> Dict[str, Any]:
    """
    Upgraded Natural Conversational & Dynamic Ledger Query Engine.
    Responds naturally and proportionally (never dumps unrelated giant blocks on 'hello'),
    supports Devanagari Hindi, Hinglish, and English identically, queries exact SQL slices
    across categories/subcategories/payment modes/dates, and handles follow-up memory.
    """
    today = _parse_client_date(context["date_today"])
    sym = context["currency"]
    user_name = context["user_name"]
    cur_spend = context["cur_spend"]
    budget = context["monthly_budget"]
    remaining = context["remaining_budget"]
    safe_cap = context["safe_daily_spend"]
    days_left = context["days_left"]
    daily_velocity = context["daily_velocity"]
    proj_spend = context["proj_month_end"]
    top_cat = context["top_category"]
    top_cat_amt = context["top_category_amount"]
    accounts = context["accounts"]
    total_assets = context["total_assets"]

    raw_q = (user_prompt or "").strip()
    low = raw_q.lower()
    tokens = set(re.findall(r"[a-z0-9]+", low))
    wants_detail = any(k in low for k in ("detail", "details", "breakdown", "list", "full", "all", "sab", "kya kya", "explain", "विस्तार", "सूची"))

    carryover = _infer_followup_carryover(raw_q, history, today)
    effective_q = raw_q
    time_start, time_end, time_label = _extract_time_window(raw_q, today)
    entities = _match_entity_filters(raw_q, context)

    # Carry over entity or date from previous turn for ultra-short follow-ups ("aur kal?", "upi se?", "detail me?")
    if carryover.get("prev_user"):
        prev_q = carryover["prev_user"]
        prev_t_start, prev_t_end, prev_t_label = _extract_time_window(prev_q, today)
        prev_ent = _match_entity_filters(prev_q, context)
        if not time_label and not any(entities.values()):
            # Follow-up like "detail me batao" -> re-run previous question with detail flag
            effective_q = prev_q
            time_start, time_end, time_label = prev_t_start, prev_t_end, prev_t_label
            entities = prev_ent
            wants_detail = True
        elif time_label and not any(entities.values()) and any(prev_ent.values()):
            entities = prev_ent
        elif any(entities.values()) and not time_label and prev_t_label:
            time_start, time_end, time_label = prev_t_start, prev_t_end, prev_t_label

    eff_low = effective_q.lower()
    eff_tokens = set(re.findall(r"[a-z0-9]+", eff_low))

    def _reply(text: str, spoken: str, chips: List[str], badge=None, action=None) -> Dict[str, Any]:
        return {
            "reply": text,
            "spoken_text": spoken[:320],
            "decision_badge": badge,
            "action_button": action,
            "followup_chips": chips[:3],
            "engine_mode": "smart_local",
            "metrics_snapshot": {
                "daily_velocity": daily_velocity,
                "projected_month_end": proj_spend,
                "monthly_budget": budget,
                "risk_status": context["risk_status"],
                "safe_daily_spend": safe_cap,
                "highest_category": top_cat,
            },
        }

    # 1. EMPTY PROMPT
    if not raw_q:
        if lang_mode == "hi":
            return _reply(
                f"नमस्ते {user_name}! बताइए आज मैं आपके पैसों या खर्च में क्या मदद कर सकता हूँ?",
                f"नमस्ते {user_name}! बताइए आज मैं क्या मदद करूं?",
                ["आज कितना खर्च हुआ?", "बचा हुआ बजट?", "UPI पे कितना गया?"],
            )
        if lang_mode == "hinglish":
            return _reply(
                f"Hey {user_name}! Batao aaj kya check karna hai — aaj ka kharcha, UPI spend, ya budget?",
                f"Hey {user_name}! Batao aaj kya check karna hai?",
                ["Aaj ka kharcha?", "Bacha hua budget?", "UPI se kitna gaya?"],
            )
        return _reply(
            f"Hi {user_name}! What would you like to check today — your daily spending, budgets, or balances?",
            f"Hi {user_name}! What would you like to check today?",
            ["Today's spend?", "Budget remaining?", "Recent transactions?"],
        )

    # 2. PURE SOCIAL GREETINGS & SMALL TALK (ChatGPT-natural short replies!)
    greeting_words = {"hi", "hello", "hey", "hii", "hlo", "namaste", "namaskar", "pranam", "sup", "yo"}
    greeting_phrases = ("good morning", "good afternoon", "good evening", "kaise ho", "kaise hain", "kya haal", "how are you", "नमस्ते", "प्रणाम", "कैसे हो", "क्या हाल")
    thank_words = {"thanks", "thank", "thankyou", "ty", "shukriya", "dhanyawad", "welcome", "ok", "okay", "cool", "nice", "great", "awesome", "badhiya", "badiya", "bye", "alvida", "शुक्रिया", "धन्यवाद", "ठीक"}
    identity_phrases = ("who are you", "what can you do", "tum kaun ho", "kya kar sakte ho", "तुम कौन हो", "क्या कर सकते हो", "help")

    is_pure_greeting = (tokens <= greeting_words or any(p in low for p in greeting_phrases)) and len(tokens) <= 5 and not time_label and not any(entities.values())
    if is_pure_greeting:
        if lang_mode == "hi":
            return _reply(
                f"नमस्ते {user_name}! मैं बिल्कुल बढ़िया हूँ 😊\n\nबताइए आज क्या देखना है — आज का खर्च, किसी कैटेगरी का हिसाब, या कोई नया खर्च जोड़ना है?",
                f"नमस्ते {user_name}! बताइए आज आपको क्या जानना है?",
                ["आज कितना खर्च हुआ?", "बजट कितना बचा है?", "UPI से कितना खर्च?"],
            )
        if lang_mode == "hinglish":
            return _reply(
                f"Hello {user_name}! Sab badhiya 😊\n\nBatao aaj kya puchna hai — aaj ka kharcha, monthly budget, ya koi naya expense add karna hai?",
                f"Hello {user_name}! Sab badhiya, batao aaj kya puchna hai?",
                ["Aaj kitna kharcha hua?", "Bacha hua budget?", "Is hafte ka spend?"],
            )
        return _reply(
            f"Hey {user_name}! Doing great 😊 What would you like to check today — your spending, category breakdown, or budget?",
            f"Hey {user_name}! What would you like to check today?",
            ["Today's spend?", "Remaining budget?", "Top expense?"],
        )

    if (tokens <= thank_words or any(w in low for w in ("thank you", "धन्यवाद", "शुक्रिया"))) and len(tokens) <= 4 and not time_label:
        if lang_mode == "hi":
            return _reply("आपका स्वागत है! जब भी कोई हिसाब देखना हो, बस बता दीजिएगा। 😊", "आपका स्वागत है!", ["आज का खर्च?", "बजट स्टेटस?"])
        if lang_mode == "hinglish":
            return _reply("Always welcome! Koi aur kharch ya hisaab dekhna ho to kabhi bhi puch lena. 😊", "Always welcome!", ["Aaj ka kharcha?", "Balance kitna hai?"])
        return _reply("You're welcome! Let me know anytime you want to check your expenses or budget. 😊", "You're welcome!", ["Today's spend?", "Account balances?"])

    if any(p in low for p in identity_phrases) and len(tokens) <= 6:
        if lang_mode == "hi":
            return _reply(
                "मैं **Finly** हूँ — आपका स्मार्ट पर्सनल फाइनेंस साथी! आप मुझसे आज/कल/महीने का खर्च, किसी भी कैटेगरी (जैसे Food, EMI, Petrol), Cash vs UPI खर्च, बजट और बचत के बारे में पूछ सकते हैं, या बोलकर नया खर्च जोड़ सकते हैं।",
                "मैं Finly हूँ, आपका फाइनेंस साथी! आप मुझसे अपने खर्च, बजट और बचत के बारे में कुछ भी पूछ सकते हैं।",
                ["आज कितना खर्च हुआ?", "बचा हुआ बजट?", "50/30/20 नियम क्या है?"],
            )
        if lang_mode == "hinglish":
            return _reply(
                "Main **Finly** hu — aapka smart expense companion! Aap mujhse aaj/kal/hafta/mahina ka kharch, kisi bhi category ya subcategory, UPI vs Cash spend, budget status puch sakte ho, ya direct naya expense add karwa sakte ho.",
                "Main Finly hu! Aap mujhse apne kharch, UPI spend, budget aur bachat ke baare me kuch bhi puch sakte ho.",
                ["Aaj ka kharcha?", "UPI se kitna gaya?", "50 chai add kar do"],
            )
        return _reply(
            "I'm **Finly**, your personal finance assistant! Ask me about today's or this week's spending, any category or payment channel (UPI/Cash/Cards), purchase affordability, or ask me to log a new expense.",
            "I'm Finly, your personal finance assistant! Ask me about your spending, budgets, or affordability.",
            ["How much spent today?", "UPI vs Cash spend?", "Budget remaining?"],
        )

    # 3. NAVIGATION INTENTS
    if any(k in eff_low for k in ("open analytics", "analytics kholo", "show analytics", "charts dikhao")):
        msg = "Analytics screen kholne ke liye neeche button dabaye 👇" if lang_mode == "hinglish" else ("नीचे बटन दबाकर एनालिटिक्स खोलें 👇" if lang_mode == "hi" else "Tap below to open Analytics 👇")
        return _reply(msg, msg, ["Today's spend?", "Budget status?"], action={"label": "Open Analytics", "type": "NAVIGATE", "target": "tab-analytics"})
    if any(k in eff_low for k in ("open history", "all time history", "saari history", "all transactions dikhao", "show history")):
        msg = "Poori transaction history dekhne ke liye neeche tap karein 👇" if lang_mode == "hinglish" else ("पूरी हिस्ट्री देखने के लिए नीचे टैप करें 👇" if lang_mode == "hi" else "Tap below to view All Time History 👇")
        return _reply(msg, msg, ["Today's spend?", "Top expense?"], action={"label": "View All History", "type": "NAVIGATE", "target": "tab-history"})
    if any(k in eff_low for k in ("set budget", "open budget", "budget set karna")):
        msg = "Budget manage karne ke liye neeche button par tap karein 👇" if lang_mode == "hinglish" else ("बजट सेट करने के लिए नीचे टैप करें 👇" if lang_mode == "hi" else "Tap below to manage your Budgets 👇")
        return _reply(msg, msg, ["Remaining budget?", "Safe daily limit?"], action={"label": "Open Budgets", "type": "NAVIGATE", "target": "tab-budgets"})

    # 4. RECORD / ADD EXPENSE OR INCOME INTENT
    amounts = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", eff_low.replace(",", ""))
    parsed_amt = float(amounts[0]) if amounts else None
    if any(k in eff_tokens for k in ("add", "record", "log", "likh", "daal", "jod", "entry")) or any(p in eff_low for p in ("add kar", "likh do", "daal do", "note kar", "जोड़ दो", "लिख दो")):
        amt = parsed_amt if (parsed_amt and parsed_amt > 0) else 50.0
        is_inc = any(k in eff_tokens for k in ("salary", "income", "received", "aayi", "mila", "bonus"))
        tx_t = "INCOME" if is_inc else "EXPENSE"
        cat_name = entities["category"] or ("Salary" if is_inc else "Food & Dining")
        ch = entities["payment_channel"] or "Cash"

        action = {
            "label": f"+ Record {_format_currency(amt, sym)} ({cat_name} • {ch})",
            "type": "OPEN_QUICK_ENTRY",
            "amount": amt,
            "transaction_type": tx_t,
            "category": cat_name,
            "subcategory": entities["subcategory"] or "",
            "account_name": ch,
        }
        if lang_mode == "hi":
            return _reply(
                f"तैयार है! **{_format_currency(amt, sym)}** (**{cat_name}**, **{ch}**) रिकॉर्ड करने के लिए नीचे टैप करें 👇",
                f"{cat_name} में {int(amt)} रुपये जोड़ने के लिए नीचे बटन दबाएं।",
                ["आज का खर्च?", "बचा हुआ बजट?"],
                action=action,
            )
        if lang_mode == "hinglish":
            return _reply(
                f"Done! **{_format_currency(amt, sym)}** (**{cat_name}**, **{ch}**) record karne ke liye neeche tap karein 👇",
                f"{cat_name} me {int(amt)} rupaye add karne ke liye neeche button dabaye.",
                ["Aaj ka kharcha?", "Bacha hua budget?"],
                action=action,
            )
        return _reply(
            f"Ready! Tap below to log **{_format_currency(amt, sym)}** under **{cat_name}** via **{ch}** 👇",
            f"Tap below to record {int(amt)} under {cat_name}.",
            ["Today's spend?", "Remaining budget?"],
            action=action,
        )

    # 5. PURCHASE AFFORDABILITY ("Kya mai 5000 ka phone le sakta hu?", "Can I buy shoes for 2000?")
    if any(k in eff_low for k in ("afford", "kharid", "khareed", "kharidu", "khareedu", "buy", "purchase", "le lu", "le sakta", "le sakti", "lena chahiye", "खरीद")):
        check_amt = parsed_amt if (parsed_amt and parsed_amt > 0) else 2500.0
        if check_amt <= remaining:
            buf = max(0.0, round(remaining - check_amt, 2))
            new_cap = round(buf / max(1, days_left), 1)
            safe_badge = {"type": "SAFE", "label": "AFFORDABLE ✅"} if check_amt <= remaining * 0.4 else {"type": "CAUTION", "label": "MANAGE WITH CARE ⚠️"}
            if lang_mode == "hi":
                return _reply(
                    f"✅ **हाँ, आप {_format_currency(check_amt, sym)} खर्च कर सकते हैं।**\n• अभी बचा बजट: **{_format_currency(remaining, sym)}**\n• इसके बाद बचेगा: **{_format_currency(buf, sym)}** (नई डेली लिमिट **{_format_currency(new_cap, sym)}/दिन**)",
                    f"हाँ, आप {int(check_amt)} रुपये खर्च कर सकते हैं। इसके बाद भी {int(buf)} रुपये बचेंगे।",
                    ["बचा हुआ बजट?", "आज का खर्च?"],
                    badge=safe_badge,
                )
            if lang_mode == "hinglish":
                return _reply(
                    f"✅ **Haan, aap {_format_currency(check_amt, sym)} aram se kharch kar sakte ho.**\n• Abhi bacha hua budget: **{_format_currency(remaining, sym)}**\n• Kharidari ke baad bachega: **{_format_currency(buf, sym)}** (naya safe limit **{_format_currency(new_cap, sym)}/day**)",
                    f"Haan, {int(check_amt)} rupaye le sakte ho. Iske baad {int(buf)} rupaye bachenge.",
                    ["Bacha hua budget?", "Paisa kaise bachaye?"],
                    badge=safe_badge,
                )
            return _reply(
                f"✅ **Yes, {_format_currency(check_amt, sym)} fits within your budget.**\n• Current Remaining Budget: **{_format_currency(remaining, sym)}**\n• After Purchase: **{_format_currency(buf, sym)}** (**{_format_currency(new_cap, sym)}/day** safe pace for {days_left} days)",
                f"Yes, you can afford {int(check_amt)}, leaving {int(buf)} in your remaining budget.",
                ["Budget status?", "Top category?"],
                badge=safe_badge,
            )
        else:
            over = round(check_amt - remaining, 2)
            badge = {"type": "DANGER", "label": "OVER BUDGET RISK 🛑"}
            if lang_mode == "hi":
                return _reply(
                    f"🛑 **थोड़ा रुकें:** {_format_currency(check_amt, sym)} आपके बचे बजट (**{_format_currency(remaining, sym)}**) से **{_format_currency(over, sym)}** ज़्यादा है। अगले महीने प्लान करना बेहतर रहेगा।",
                    f"रुकिए! यह खर्च आपके बजट से {int(over)} रुपये ज़्यादा है।",
                    ["पैसे कैसे बचाएं?", "टॉप खर्च किसमें?"],
                    badge=badge,
                )
            if lang_mode == "hinglish":
                return _reply(
                    f"🛑 **Thoda wait karein:** {_format_currency(check_amt, sym)} aapke bache budget (**{_format_currency(remaining, sym)}**) se **{_format_currency(over, sym)}** zyada hai. Zaruri na ho to agle cycle tak rokna safe rahega.",
                    f"Rukiye! Ye aapke budget se {int(over)} rupaye zyada hai.",
                    ["Paisa kaise bachaye?", "Bacha budget kitna?"],
                    badge=badge,
                )
            return _reply(
                f"🛑 **Hold on:** {_format_currency(check_amt, sym)} exceeds your remaining budget (**{_format_currency(remaining, sym)}**) by **{_format_currency(over, sym)}**. Deferring or trimming non-essential spend would keep you safe.",
                f"Caution: that exceeds your remaining budget by {int(over)}.",
                ["How to save more?", "Top expense?"],
                badge=badge,
            )

    # 6. RECENT / LAST TRANSACTION LIST ("Last transaction kya tha?", "Aaj kya kya kharch hua?", "Show transactions")
    if any(p in eff_low for p in ("last transaction", "latest transaction", "recent transaction", "kya kya kharch", "kya kharida", "transactions dikhao", "recent list", "show transactions", "ट्रांजैक्शन")):
        target_txs = context["today_transactions"] if time_label == "today" else (
            context["yesterday_transactions"] if time_label == "yesterday" else context["recent_transactions"]
        )
        slice_cnt = 1 if ("last transaction" in eff_low or "latest transaction" in eff_low) else (10 if wants_detail else 5)
        shown = target_txs[:slice_cnt]
        if not shown:
            msg = "इस अवधि में कोई ट्रांजैक्शन रिकॉर्ड नहीं मिला।" if lang_mode == "hi" else ("Is time ka koi transaction record nahi mila." if lang_mode == "hinglish" else "No transactions found for that period.")
            return _reply(msg, msg, ["This month's spend?", "Account balances?"])

        lines = []
        for t in shown:
            sub = f" • {t['subcategory_name']}" if t.get("subcategory_name") else ""
            note = f" ({t['note']})" if t.get("note") else ""
            lines.append(f"• **{t['date']}**: {t['category_name']}{sub} — **{_format_currency(t['amount'], sym)}** ({t['account_name']}){note}")
        hdr = "हालिया ट्रांजैक्शन:" if lang_mode == "hi" else ("Recent transactions:" if lang_mode == "hinglish" else "Recent transactions:")
        return _reply(f"**{hdr}**\n" + "\n".join(lines), f"Latest: {shown[0]['category_name']} {int(shown[0]['amount'])}.", ["Today's spend?", "All Time History"])

    # 7. DYNAMIC TARGETED LEDGER QUERY (Any Combination of Time Window + Category + Subcategory + Payment Channel!)
    has_targeted_scope = bool(time_label or entities["category"] or entities["subcategory"] or entities["payment_channel"])
    is_budget_only = any(k in eff_tokens for k in ("budget", "limit", "runway", "bacha", "remaining")) and not time_label and not entities["category"] and not entities["payment_channel"]

    if has_targeted_scope and not is_budget_only:
        res = _query_ledger_dynamic(
            user_id,
            start_date=time_start,
            end_date=time_end,
            category_name=entities["category"],
            subcategory_name=entities["subcategory"],
            payment_channel=entities["payment_channel"],
            tx_type="EXPENSE",
        )
        # Check if query explicitly asks about INCOME + category (e.g. Salary)
        if ("salary" in eff_tokens or "income" in eff_tokens) and res["total"] == 0:
            res = _query_ledger_dynamic(
                user_id,
                start_date=time_start,
                end_date=time_end,
                category_name=entities["category"],
                payment_channel=entities["payment_channel"],
                tx_type="INCOME",
            )

        q_amt = res["total"]
        q_cnt = res["count"]
        q_txs = res["transactions"]

        # Build natural scope label
        t_names = {
            "today": ("आज", "aaj", "today"),
            "yesterday": ("कल", "kal", "yesterday"),
            "parso": ("परसों", "parso", "the day before yesterday"),
            "this_week": ("इस हफ्ते", "is hafte", "this week"),
            "last_7d": ("पिछले 7 दिनों में", "pichle 7 din me", "in the last 7 days"),
            "last_month": ("पिछले महीने", "pichle mahine", "last month"),
            "this_month": ("इस महीने", "is mahine", "this month"),
            "all_time": ("अब तक कुल", "ab tak total", "overall all-time"),
        }
        t_hi, t_hg, t_en = t_names.get(time_label, ("इस महीने", "is mahine", "this month"))
        scope_parts = []
        if entities["subcategory"]:
            scope_parts.append(f"{entities['category']} • {entities['subcategory']}" if entities["category"] else entities["subcategory"])
        elif entities["category"]:
            scope_parts.append(entities["category"])
        if entities["payment_channel"]:
            scope_parts.append(entities["payment_channel"])
        scope_str = " (" + " • ".join(scope_parts) + ")" if scope_parts else ""

        tx_preview = ""
        if q_txs and (wants_detail or time_label in ("today", "yesterday") or q_cnt <= 3):
            preview_items = []
            for tx in q_txs[:5]:
                sub_lbl = f" ({tx['subcategory_name']})" if tx.get("subcategory_name") else ""
                preview_items.append(f"• {tx['category_name']}{sub_lbl}: **{_format_currency(tx['amount'], sym)}** ({tx['account_name']})")
            tx_preview = "\n\n" + "\n".join(preview_items)

        if lang_mode == "hi":
            if q_cnt == 0:
                reply = f"{t_hi}{scope_str} कोई खर्च रिकॉर्ड नहीं हुआ है (**{sym}0.00**)। 👍"
                spoken = f"{t_hi} कोई खर्च नहीं हुआ है।"
            else:
                reply = f"{t_hi}{scope_str} कुल **{_format_currency(q_amt, sym)}** खर्च हुए ({q_cnt} ट्रांजैक्शन)।{tx_preview}"
                spoken = f"{t_hi} कुल {int(q_amt)} रुपये खर्च हुए हैं।"
            chips = ["बचा हुआ बजट?", "UPI से कितना खर्च?", "इस महीने का कुल खर्च?"]
        elif lang_mode == "hinglish":
            if q_cnt == 0:
                reply = f"{t_hg.capitalize()}{scope_str} koi kharch record nahi hua (**{sym}0.00**). 👍"
                spoken = f"{t_hg} koi kharch nahi hua hai."
            else:
                reply = f"{t_hg.capitalize()}{scope_str} total **{_format_currency(q_amt, sym)}** kharch huye ({q_cnt} transaction{'s' if q_cnt != 1 else ''}).{tx_preview}"
                spoken = f"{t_hg} total {int(q_amt)} rupaye kharch huye hain."
            chips = ["Kal kitna gaya?", "UPI vs Cash spend?", "Bacha hua budget?"]
        else:
            if q_cnt == 0:
                reply = f"No expenses recorded {t_en}{scope_str} (**{sym}0.00**). 👍"
                spoken = f"Zero spent {t_en}."
            else:
                reply = f"You spent **{_format_currency(q_amt, sym)}** {t_en}{scope_str} across **{q_cnt}** transaction{'s' if q_cnt != 1 else ''}.{tx_preview}"
                spoken = f"You spent {int(q_amt)} {t_en}."
            chips = ["Yesterday's spend?", "UPI vs Cash split?", "Remaining budget?"]

        return _reply(reply, spoken, chips)

    # 8. INCOME & NET SAVINGS ("Income kitni hai?", "Kitna save hua?")
    if any(k in eff_tokens for k in ("income", "salary", "earned", "earning", "savings", "net", "aamdani", "kamayi", "आमदनी", "बचत")):
        inc = context["monthly_income"]
        sav = context["net_savings"]
        sr = context["savings_rate_pct"]
        if lang_mode == "hi":
            return _reply(
                f"इस महीने की कुल आय **{_format_currency(inc, sym)}**, खर्च **{_format_currency(cur_spend, sym)}** और शुद्ध बचत **{_format_currency(sav, sym)}** ({sr}%) है।",
                f"इस महीने आय {int(inc)} और बचत {int(sav)} रुपये है।",
                ["आज का खर्च?", "बजट स्टेटस?"],
            )
        if lang_mode == "hinglish":
            return _reply(
                f"Is mahine aapki total income **{_format_currency(inc, sym)}**, kharch **{_format_currency(cur_spend, sym)}**, aur net savings **{_format_currency(sav, sym)}** ({sr}%) rahi hai.",
                f"Is mahine income {int(inc)} aur net savings {int(sav)} rupaye hai.",
                ["Aaj ka kharcha?", "Paisa kaise bachaye?"],
            )
        return _reply(
            f"This month's income is **{_format_currency(inc, sym)}** vs expenses of **{_format_currency(cur_spend, sym)}**, leaving net savings of **{_format_currency(sav, sym)}** ({sr}%).",
            f"Income is {int(inc)} with net savings of {int(sav)}.",
            ["Today's spend?", "Top expense?"],
        )

    # 9. ACCOUNT BALANCES ("Balance kitna hai?")
    if any(k in eff_tokens for k in ("balance", "account", "accounts", "bank", "wallet", "wallets", "worth", "बैलेंस", "खाते")):
        acc_lines = [f"• **{a['name']}**: **{_format_currency(a['current_balance'], sym)}**" for a in accounts]
        body = "\n".join(acc_lines) if acc_lines else "• No active accounts"
        if lang_mode == "hi":
            return _reply(f"आपके खातों का लाइव बैलेंस (कुल **{_format_currency(total_assets, sym)}**):\n{body}", f"कुल बैलेंस {int(total_assets)} रुपये है।", ["आज का खर्च?", "बजट स्टेटस?"])
        if lang_mode == "hinglish":
            return _reply(f"Aapke accounts ka live balance (Total **{_format_currency(total_assets, sym)}**):\n{body}", f"Total balance {int(total_assets)} rupaye hai.", ["Aaj ka kharcha?", "Is mahine ka total?"])
        return _reply(f"Your live account balances (Total **{_format_currency(total_assets, sym)}**):\n{body}", f"Total balance is {int(total_assets)}.", ["Today's spend?", "Monthly budget?"])

    # 10. TOP SPENDING / LARGEST EXPENSE
    if any(k in eff_tokens for k in ("top", "highest", "biggest", "largest", "zyada", "jyada", "sabse", "ज्यादा", "सबसे")):
        lg = context.get("largest_expense_mtd")
        if top_cat == "None" or top_cat_amt <= 0:
            msg = "इस महीने अभी तक कोई बड़ा खर्च दर्ज नहीं हुआ है।" if lang_mode == "hi" else ("Is mahine abhi tak koi bada kharch nahi hua." if lang_mode == "hinglish" else "No major expenses recorded so far this month.")
            return _reply(msg, msg, ["Today's spend?", "Monthly budget?"])
        lg_str = f" (सबसे बड़ा सिंगल खर्च: **{_format_currency(lg['amount'], sym)}** on {lg['date']})" if (lg and lang_mode == "hi") else (
            f" (Sabse bada single expense: **{_format_currency(lg['amount'], sym)}** on {lg['date']})" if lg else ""
        )
        if lang_mode == "hi":
            return _reply(f"इस महीने सबसे ज़्यादा खर्च **{top_cat}** में **{_format_currency(top_cat_amt, sym)}** हुआ है।{lg_str}", f"सबसे ज़्यादा खर्च {top_cat} में {int(top_cat_amt)} रुपये हुआ है।", ["बचा हुआ बजट?", "पैसे कैसे बचाएं?"])
        if lang_mode == "hinglish":
            return _reply(f"Is mahine sabse zyada kharch **{top_cat}** me **{_format_currency(top_cat_amt, sym)}** hua hai.{lg_str}", f"Sabse zyada kharch {top_cat} me {int(top_cat_amt)} rupaye hua hai.", ["Bacha budget kitna?", "Paisa kaise bachaye?"])
        return _reply(f"Your top spending category this month is **{top_cat}** at **{_format_currency(top_cat_amt, sym)}**.{lg_str}", f"Top category is {top_cat} with {int(top_cat_amt)}.", ["Remaining budget?", "UPI vs Cash split?"])

    # 11. GOALS & UPCOMING BILLS
    if any(k in eff_tokens for k in ("goal", "goals", "lakshya", "लक्ष्य", "saving goal")):
        goals = context["active_goals"]
        if not goals:
            msg = "अभी कोई सक्रिय सेविंग्स गोल नहीं है।" if lang_mode == "hi" else ("Abhi koi active savings goal set nahi hai." if lang_mode == "hinglish" else "No active savings goals set right now.")
            return _reply(msg, msg, ["Account balances?", "Monthly budget?"])
        g_lines = [f"• **{g['title']}**: **{_format_currency(float(g['current_amount']), sym)}** / {_format_currency(float(g['target_amount']), sym)} ({g['progress_pct']}%)" for g in goals]
        return _reply("**Savings Goals:**\n" + "\n".join(g_lines), f"You have {len(goals)} active savings goals.", ["Account balances?", "Budget status?"])

    if any(k in eff_tokens for k in ("upcoming", "recurring", "dues", "pending", "bill", "bills", "बिल")):
        bills = context["upcoming_bills"]
        if not bills:
            msg = "🎉 कोई आगामी रिकरिंग बिल पेंडिंग नहीं है!" if lang_mode == "hi" else ("🎉 Koi bhi upcoming recurring bill pending nahi hai!" if lang_mode == "hinglish" else "🎉 No upcoming recurring bills due right now.")
            return _reply(msg, msg, ["Today's spend?", "Budget status?"])
        b_lines = [f"• **{b['title']}**: **{_format_currency(float(b['amount']), sym)}** (Due: {b['next_due_date']})" for b in bills]
        return _reply("**Upcoming Bills:**\n" + "\n".join(b_lines), f"You have {len(bills)} upcoming bills.", ["Account balances?", "Remaining budget?"])

    # 12. BUDGET & SAFE DAILY PACE
    if is_budget_only or any(k in eff_tokens for k in ("budget", "safe", "pace", "limit", "overrun", "बजट")):
        cat_limits = context.get("category_budgets", [])
        extra = ""
        if cat_limits:
            c_strs = [f"• **{cb['category']}**: {_format_currency(cb['spent'], sym)} / {_format_currency(cb['limit'], sym)} ({cb['pct_used']}%)" for cb in cat_limits[:4]]
            extra = "\n\n**Category Limits:**\n" + "\n".join(c_strs)
        if lang_mode == "hi":
            return _reply(
                f"मासिक बजट: **{_format_currency(budget, sym)}** | खर्च: **{_format_currency(cur_spend, sym)}** | बचा बजट: **{_format_currency(remaining, sym)}**\n🛡️ सेफ डेली लिमिट: **{_format_currency(safe_cap, sym)}/दिन** ({days_left} दिन बाकी){extra}",
                f"आपका बचा बजट {int(remaining)} रुपये है और रोज का सेफ लिमिट {int(safe_cap)} रुपये है।",
                ["आज का खर्च?", "टॉप खर्च किसमें?"],
            )
        if lang_mode == "hinglish":
            return _reply(
                f"Monthly Budget: **{_format_currency(budget, sym)}** | Spend: **{_format_currency(cur_spend, sym)}** | Remaining: **{_format_currency(remaining, sym)}**\n🛡️ Safe Daily Cap: **{_format_currency(safe_cap, sym)}/day** ({days_left} days left){extra}",
                f"Bacha hua budget {int(remaining)} rupaye hai aur daily safe limit {int(safe_cap)} rupaye hai.",
                ["Aaj ka kharcha?", "Top expense?"],
            )
        return _reply(
            f"Monthly Budget: **{_format_currency(budget, sym)}** | Spent: **{_format_currency(cur_spend, sym)}** | Remaining: **{_format_currency(remaining, sym)}**\n🛡️ Safe Daily Cap: **{_format_currency(safe_cap, sym)}/day** ({days_left} days left){extra}",
            f"You have {int(remaining)} remaining in your budget with a safe daily pace of {int(safe_cap)}.",
            ["Today's spend?", "Top expense?"],
        )

    # 13. PERSONAL FINANCE KNOWLEDGE / SAVINGS COACHING
    if any(p in eff_low for p in ("save kaise", "kaise bachaye", "kaise bachayein", "how to save", "50/30/20", "50-30-20", "tips", "sip", "mutual fund", "cibil", "credit score", "emergency fund", "बचत कैसे", "पैसे कैसे बचाएं")):
        if "sip" in eff_low or "mutual fund" in eff_low:
            ans = "SIP (Systematic Investment Plan) me har mahine fix amount invest hoti hai, jisse rupee-cost averaging aur compounding milta hai. Pehle 3-6 mahine ka emergency fund alag rakh kar apne monthly surplus"
            if lang_mode == "en":
                ans = "A SIP lets you invest a fixed amount monthly into mutual funds, smoothing market volatility through rupee-cost averaging. Based on your current net savings of **{}**, start small once your emergency buffer is ready!".format(_format_currency(max(0.0, context["net_savings"]), sym))
            else:
                ans += f" (abhi net savings **{_format_currency(max(0.0, context['net_savings']), sym)}**) ka ek hissa start kar sakte hain!"
            return _reply(ans, ans, ["Budget status?", "Remaining budget?"])

        tip_line = f"Sabse bada kharch **{top_cat}** (**{_format_currency(top_cat_amt, sym)}**) me 15% kam karne se **{_format_currency(round(top_cat_amt * 0.15, 2), sym)}** seedha bachega." if top_cat_amt > 0 else "Discretionary spending par daily limit lagakar rakhein."
        if lang_mode == "hi":
            return _reply(f"💡 **बचत बढ़ाने के प्रैक्टिकल तरीके:**\n• 50/30/20 नियम (50% जरूरतें, 30% शौक, 20% बचत) अपनाएं।\n• रोज़ **{_format_currency(safe_cap, sym)}/दिन** के अंदर रहें।\n• {tip_line}", f"सेफ डेली लिमिट {int(safe_cap)} रुपये के अंदर रहें।", ["बजट स्टेटस?", "टॉप खर्च किसमें?"])
        if lang_mode == "hinglish":
            return _reply(f"💡 **Bachat badhane ke smart steps:**\n• 50/30/20 rule follow karein (50% needs, 30% wants, 20% savings).\n• Roz ka kharch **{_format_currency(safe_cap, sym)}/day** ke andar rakhein.\n• {tip_line}", f"Roz {int(safe_cap)} rupaye ke andar kharch rakhein aur top category trim karein.", ["Budget status?", "Top expense?"])
        return _reply(f"💡 **Practical Ways to Save More:**\n• Follow 50/30/20 (50% Needs, 30% Wants, 20% Savings).\n• Stay under **{_format_currency(safe_cap, sym)}/day**.\n• Trimming 15% from **{top_cat}** saves **{_format_currency(round(top_cat_amt * 0.15, 2), sym)}**.", f"Stay under {int(safe_cap)} per day and trim your top expense.", ["Monthly budget?", "Recent transactions?"])

    # 14. NOTE / MERCHANT KEYWORD SEARCH IN LEDGER
    # Search user's actual transaction notes for non-stopword terms (e.g. "bhujiya", "uber", "medicine")
    stopwords = {"what", "when", "where", "which", "how", "much", "many", "did", "does", "was", "were", "the", "for", "and", "with", "about", "tell", "show", "give", "mera", "mere", "meri", "kitna", "kitne", "kya", "hai", "hain", "hua", "tha", "pe", "me", "se", "ka", "ki", "ke", "ko", "mein", "batao", "bata", "dikhao", "कर", "क्या", "कितना", "हुआ", "बताओ", "है", "में"}
    content_terms = [t for t in re.findall(r"[a-z0-9]+", eff_low) if t not in stopwords and len(t) >= 3]
    for term in content_terms:
        note_res = _query_ledger_dynamic(user_id, tx_type=None, search_term=term)
        if note_res["count"] > 0:
            items = "\n".join(
                f"• {tx['date']}: **{tx['category_name']}** — **{_format_currency(tx['amount'], sym)}** ({tx['account_name']})" + (f" [{tx['note']}]" if tx.get("note") else "")
                for tx in note_res["transactions"][:4]
            )
            if lang_mode == "hi":
                return _reply(f"**'{term}'** से जुड़े {note_res['count']} ट्रांजैक्शन मिले (कुल **{_format_currency(note_res['total'], sym)}**):\n{items}", f"{term} पर कुल {int(note_res['total'])} रुपये मिले।", ["आज का खर्च?", "हालिया ट्रांजैक्शन?"])
            if lang_mode == "hinglish":
                return _reply(f"**'{term}'** ke {note_res['count']} transaction mile (Total **{_format_currency(note_res['total'], sym)}**):\n{items}", f"{term} par total {int(note_res['total'])} rupaye mile.", ["Aaj ka kharcha?", "Recent transactions?"])
            return _reply(f"Found **{note_res['count']}** matching transaction(s) for **'{term}'** totaling **{_format_currency(note_res['total'], sym)}**:\n{items}", f"Found {note_res['count']} matching transactions totaling {int(note_res['total'])}.", ["Today's spend?", "Budget status?"])

    # 15. OPEN-DOMAIN HONEST RESPONSE (No unrelated MTD dump!)
    if lang_mode == "hi":
        return _reply(
            f"मैं इस सवाल को सीधे आपके डेटा से जोड़ नहीं पाया। आप मुझसे इस तरह पूछ सकते हैं:\n• *\"आज कितना खर्च हुआ?\"*\n• *\"कल क्या-क्या खर्च किया?\"*\n• *\"UPI से कितना खर्च हुआ?\"*\n• *\"फूड / EMI पर कितना गया?\"*\n\n*(नोट: ओपन-एंडेड ChatGPT जैसे हर सामान्य सवाल के लिए सर्वर पर `GEMINI_API_KEY` या `OPENAI_API_KEY` कॉन्फ़िगर करना होगा।)*",
            "कृपया अपने खर्च, कैटेगरी, UPI या बजट के बारे में पूछें।",
            ["आज कितना खर्च हुआ?", "बजट स्टेटस?", "हालिया ट्रांजैक्शन?"],
        )
    if lang_mode == "hinglish":
        return _reply(
            f"Ye sawal aapke expense ledger se directly match nahi hua. Aap mujhse is tarah kuch bhi puch sakte ho:\n• *\"Aaj kitna kharch hua?\"*\n• *\"UPI vs Cash me kitna gaya?\"*\n• *\"Food ya EMI pe kitna kharch?\"*\n• *\"150 coffee add kar do\"*\n\n*(Open-ended ChatGPT jaise har general sawaal ke liye Render environment me `GEMINI_API_KEY` ya `GROQ_API_KEY` add karne par full Generative AI bhi active ho jata hai.)*",
            "Aap apne kharch, UPI spend, category ya budget ke baare me puch sakte hain.",
            ["Aaj kitna kharcha hua?", "UPI se kitna gaya?", "Bacha hua budget?"],
        )
    return _reply(
        "I couldn't map that question to a specific ledger record. Try asking naturally about:\n• *\"How much did I spend today / this week?\"*\n• *\"What's my UPI vs Cash spending?\"*\n• *\"How much spent on Food or EMI?\"*\n• *\"Can I afford a ₹3,000 purchase?\"*\n\n*(Note: Add a `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `GROQ_API_KEY` in server environment variables to enable full open-ended ChatGPT conversations on any topic.)*",
        "Ask me about your expenses, payment methods, categories, or budgets.",
        ["Today's spend?", "UPI vs Cash spend?", "Remaining budget?"],
    )


def generate_ai_mentor_advice(
    user_id: int,
    user_prompt: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    client_date: Optional[str] = None,
    db_path: str = "expenses.db",
) -> Dict[str, Any]:
    """
    Main Entry Point for Finly 5.0:
    1. Detects exact user language/script (Devanagari Hindi, Hinglish, English).
    2. Builds full grounded RAG ledger context & targeted SQL slice lookup.
    3. Attempts Cloud LLM (Gemini 2.5/2.0 Flash, OpenAI, Groq, OpenRouter) with multi-turn memory.
    4. Seamlessly uses upgraded Natural Conversational Engine when running offline/without API key.
    """
    today = _parse_client_date(client_date)
    context = get_financial_context(user_id, db_path=db_path, target_date=today)
    clean_prompt = (user_prompt or "").strip()
    lang_mode = _detect_language_mode(clean_prompt, history)

    if clean_prompt:
        t_start, t_end, t_label = _extract_time_window(clean_prompt, today)
        ent = _match_entity_filters(clean_prompt, context)
        targeted_lookup = None
        if t_label or any(ent.values()):
            targeted_lookup = {
                "period": t_label or "all_or_unspecified",
                "start_date": t_start,
                "end_date": t_end,
                "filters": ent,
                "expense_match": _query_ledger_dynamic(
                    user_id,
                    start_date=t_start,
                    end_date=t_end,
                    category_name=ent["category"],
                    subcategory_name=ent["subcategory"],
                    payment_channel=ent["payment_channel"],
                    tx_type="EXPENSE",
                ),
            }

        llm_result = call_llm_engine(
            context,
            clean_prompt,
            history=history,
            targeted_lookup=targeted_lookup,
            lang_mode=lang_mode,
        )
        if llm_result and llm_result.get("reply"):
            llm_result["metrics_snapshot"] = {
                "daily_velocity": context["daily_velocity"],
                "projected_month_end": context["proj_month_end"],
                "monthly_budget": context["monthly_budget"],
                "risk_status": context["risk_status"],
                "safe_daily_spend": context["safe_daily_spend"],
                "highest_category": context["top_category"],
            }
            return llm_result

    return smart_conversational_engine(user_id, context, clean_prompt, history=history, lang_mode=lang_mode)
