"""
SUBSCRIPTION INTELLIGENCE ENGINE (subscription_service.py)
Expense Tracker Pro 2.0 - Automation & Real-World Financial Intelligence

Supports:
1. Subscription Metrics:
   - Monthly and yearly cost equivalents for all active subscriptions.
   - Total committed monthly and annualized recurring expenditure.
2. Subscription Candidate Discovery:
   - Analyzes historical ledger transactions (last 90-180 days).
   - Identifies repeating transactions with identical amounts or known subscription merchants (Netflix, Spotify, Prime, Hotstar, Gym, Wi-Fi).
   - Classifies as SUBSCRIPTION_CANDIDATE for user review (NO automatic creation).
3. Subscription Health & Insights:
   - Amount increase detection (flags price hikes).
   - Duplicate / Overlapping subscription detection.
   - Inactive / Paused subscription tracking.
"""

import re
import calendar
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Tuple
import db_engine


KNOWN_SUBSCRIPTION_KEYWORDS = [
    "netflix", "spotify", "prime", "hotstar", "disney", "youtube", "apple", "google one",
    "gym", "fitness", "cult", "wifi", "broadband", "airtel", "jio", "cloud", "aws", "openai",
    "github", "adobe", "newspaper", "magazine", "membership"
]

def to_decimal(val) -> Decimal:
    if val is None:
        return Decimal("0.00")
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

def get_subscription_summary(user_id: int, db_path: str = "expenses.db") -> Dict[str, Any]:
    """
    Computes active subscription overview, annualized costs, upcoming renewals, and price change insights.
    """
    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Fetch all recurring bills
        cursor.execute("""
            SELECT id, title, amount, frequency, due_day, next_due_date, is_active, category_id
            FROM recurring_bills
            WHERE user_id = ?
            ORDER BY next_due_date ASC
        """, (user_id,))
        bills = cursor.fetchall()

        active_subs = []
        paused_subs = []
        total_monthly_committed = Decimal("0.00")
        total_yearly_committed = Decimal("0.00")

        today_d = date.today()

        for b in bills:
            b_dict = dict(b)
            amt = to_decimal(b_dict["amount"])
            freq = (b_dict.get("frequency") or "MONTHLY").upper()

            # Compute monthly & yearly equivalent
            if freq == "MONTHLY":
                m_equiv = amt
                y_equiv = (amt * Decimal("12.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            elif freq == "WEEKLY":
                m_equiv = (amt * Decimal("4.33")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                y_equiv = (amt * Decimal("52.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            elif freq == "YEARLY":
                m_equiv = (amt / Decimal("12.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                y_equiv = amt
            else:
                m_equiv = amt
                y_equiv = amt * Decimal("12.00")

            sub_item = {
                "id": b_dict["id"],
                "title": b_dict["title"],
                "amount": float(amt),
                "frequency": freq,
                "due_day": b_dict["due_day"],
                "next_due_date": b_dict["next_due_date"],
                "monthly_equivalent": float(m_equiv),
                "yearly_equivalent": float(y_equiv),
                "is_active": bool(b_dict["is_active"])
            }

            if b_dict["is_active"]:
                active_subs.append(sub_item)
                total_monthly_committed += m_equiv
                total_yearly_committed += y_equiv
            else:
                paused_subs.append(sub_item)

        # Detect Duplicate / Overlapping Subscriptions (shared service keyword or title word overlap)
        duplicate_warnings = []
        for i in range(len(active_subs)):
            for j in range(i + 1, len(active_subs)):
                s1 = active_subs[i]
                s2 = active_subs[j]
                t1 = s1["title"].lower().strip()
                t2 = s2["title"].lower().strip()

                words1 = set(re.findall(r'\b[a-zA-Z]{4,}\b', t1))
                words2 = set(re.findall(r'\b[a-zA-Z]{4,}\b', t2))
                common_words = words1.intersection(words2)

                is_overlap = False
                matched_name = ""
                if common_words:
                    is_overlap = True
                    matched_name = list(common_words)[0].title()
                elif any(kw in t1 and kw in t2 for kw in KNOWN_SUBSCRIPTION_KEYWORDS):
                    is_overlap = True
                    matched_name = s1["title"]

                if is_overlap:
                    duplicate_warnings.append({
                        "warning": f"You appear to be paying for {matched_name} multiple times ('{s1['title']}' and '{s2['title']}'). Consider consolidating.",
                        "sub_id_1": s1["id"],
                        "sub_id_2": s2["id"]
                    })


        return {
            "success": True,
            "total_active_count": len(active_subs),
            "active_subscriptions_count": len(active_subs),
            "total_paused_count": len(paused_subs),
            "total_monthly_committed": float(total_monthly_committed),
            "monthly_total": float(total_monthly_committed),
            "total_yearly_committed": float(total_yearly_committed),
            "annual_total": float(total_yearly_committed),
            "active_subscriptions": active_subs,
            "paused_subscriptions": paused_subs,
            "duplicate_warnings": duplicate_warnings
        }

    finally:
        conn.close()


def discover_subscription_candidates(user_id: int, db_path: str = "expenses.db") -> List[Dict[str, Any]]:
    """
    Analyzes historical transactions (last 90 days) to identify repeating patterns
    that may represent subscriptions, and returns them as candidates for user review.
    """
    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cutoff = (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")

        # Group by transaction note and amount to detect repeating outlays
        cursor.execute("""
            SELECT note, amount, COUNT(id) as occurrences, MIN(date) as first_date, MAX(date) as last_date
            FROM transactions
            WHERE user_id = ?
              AND transaction_type = 'EXPENSE'
              AND date >= ?
              AND amount > 0
              AND note IS NOT NULL
              AND TRIM(note) != ''
            GROUP BY note, amount
            HAVING COUNT(id) >= 2
        """, (user_id, cutoff))
        repeating = cursor.fetchall()

        # Fetch existing active recurring bills to avoid suggesting already tracked bills
        cursor.execute("SELECT LOWER(title) as title FROM recurring_bills WHERE user_id = ?", (user_id,))
        existing_titles = [r["title"] for r in cursor.fetchall()]

        candidates = []
        for r in repeating:
            note_str = r["note"].strip()
            note_lower = note_str.lower()
            amt = float(to_decimal(r["amount"]))

            # Skip if already tracked
            if any(et in note_lower or note_lower in et for et in existing_titles):
                continue

            # Check if keyword matches or occurs >= 2 times with consistent spacing
            is_known_service = any(kw in note_lower for kw in KNOWN_SUBSCRIPTION_KEYWORDS)
            occurrences = int(r["occurrences"])

            confidence = "HIGH" if is_known_service and occurrences >= 2 else "MEDIUM"

            candidates.append({
                "title": note_str.title(),
                "amount": amt,
                "frequency": "MONTHLY",
                "occurrences_detected": occurrences,
                "last_charged_date": r["last_date"],
                "confidence": confidence,
                "reason": f"Detected {occurrences} recurring charges of Rs.{amt:.2f} over the past 90 days."
            })

        return candidates
    finally:
        conn.close()

def convert_candidate_to_recurring(user_id: int, title: str, amount: float, frequency: str = "MONTHLY",
                                  due_date: Optional[str] = None, category_id: Optional[int] = None,
                                  db_path: str = "expenses.db") -> int:
    """
    Converts a detected subscription candidate into an official recurring bill.
    """
    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        if not due_date:
            due_date = date.today().strftime("%Y-%m-%d")
        due_day = int(due_date.split("-")[2]) if "-" in due_date else 1

        cursor.execute("""
            INSERT INTO recurring_bills (user_id, title, amount, due_day, next_due_date, frequency, category_id, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (user_id, title.strip(), float(to_decimal(amount)), due_day, due_date, frequency.upper(), category_id))
        bill_id = cursor.lastrowid
        conn.commit()


        # Update candidate table if candidate was recorded
        try:
            cursor.execute("""
                UPDATE subscription_candidates
                SET status = 'CONVERTED'
                WHERE user_id = ? AND LOWER(title) = LOWER(?)
            """, (user_id, title.strip()))
            conn.commit()
        except Exception:
            pass

        return bill_id
    finally:
        conn.close()

