"""
SMART SMS & UPI FINANCIAL TRANSACTION PARSER (sms_parser_service.py)
Expense Tracker Pro 2.0 - Automation & Real-World Financial Intelligence

Supports:
1. Regex extraction across major Indian banks & UPI payment gateways:
   - HDFC, SBI, ICICI, Axis, Kotak, PNB, Bank of Baroda
   - Google Pay, PhonePe, Paytm, CRED, Amazon Pay
2. Extraction of:
   - Amount (INR / Rs / ₹)
   - Transaction Type (EXPENSE / DEBIT vs INCOME / CREDIT)
   - Merchant / Payee / Beneficiary
   - Account / Card Identifier hint (e.g., "A/c XX1234")
   - Reference Number (UPI Ref / UTR / Txn ID)
   - Transaction Date
   - Suggested Category & Subcategory
3. Deterministic Confidence Rating:
   - HIGH: Amount, Type, Date, and Merchant extracted with high certainty.
   - MEDIUM: Core financial fields found, but Merchant or Date inferred.
   - LOW: Critical fields ambiguous or missing. Requires manual review.
4. Intelligent Duplicate Detection:
   - Scans user transactions in a +/- 2 day window for matching amount and merchant/ref.
5. Strict User Confirmation Guard:
   - NEVER silently saves transactions; returns structured review payload.
"""

import re
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional, List, Tuple
import db_engine

# Known merchant categorization heuristics (shared with OCR for consistency)
MERCHANT_CATEGORY_RULES = [
    (r'(?i)\b(starbucks|cafe|costa|ccd|blue tokai|barista|third wave)\b', "Food & Dining", "Coffee & Beverage"),
    (r'(?i)\b(mcdonald\'?s|kfc|burger king|subway|wendy\'?s|domino\'?s|pizza hut)\b', "Food & Dining", "Fast Food"),
    (r'(?i)\b(zomato|swiggy|eatsure|foodpanda)\b', "Food & Dining", "Online Food Delivery"),
    (r'(?i)\b(restaurant|bistro|diner|kitchen|dhaba|bar & grill|bakery|canteen)\b', "Food & Dining", "Restaurant Dining"),
    (r'(?i)\b(uber|ola|rapido|blusmart|lyft|cab|taxi)\b', "Transportation", "Ride Hailing"),
    (r'(?i)\b(shell|bpcl|hpcl|indian oil|petrol|fuel|cng|diesel)\b', "Transportation", "Fuel"),
    (r'(?i)\b(metro|railway|irctc|flight|indigo|air india|fastag|toll)\b', "Transportation", "Transit & Toll"),
    (r'(?i)\b(blinkit|zepto|instamart|bigbasket|dunzo)\b', "Food & Dining", "Groceries"),
    (r'(?i)\b(d-mart|dmart|reliance fresh|nature\'?s basket|spencer|supermarket|kirana|grocery)\b', "Food & Dining", "Supermarket"),
    (r'(?i)\b(amazon|flipkart|myntra|ajio|meesho|tata cliq)\b', "Shopping", "Online Shopping"),
    (r'(?i)\b(zara|h&m|uniqlo|decathlon|westside|pantaloons|lifestyle)\b', "Shopping", "Apparel & Gear"),
    (r'(?i)\b(apollo|medplus|pharmeasy|1mg|tata 1mg|pharmacy|chemist|hospital|clinic)\b', "Healthcare", "Medical & Pharmacy"),
    (r'(?i)\b(pvr|inox|cinepolis|bookmyshow|movie|cinema)\b', "Entertainment", "Movies & Events"),
    (r'(?i)\b(netflix|spotify|prime video|hotstar|disney|apple music|youtube)\b', "Entertainment", "Digital Subscriptions"),
    (r'(?i)\b(airtel|jio|vodafone|vi|bsnl|broadband|wifi)\b', "Bills & Utilities", "Mobile & Internet"),
    (r'(?i)\b(electricity|bescom|tata power|adani power|water board|igl|indane|hp gas)\b', "Bills & Utilities", "Utilities"),
    (r'(?i)\b(salary|payroll|stipend|wages)\b', "Salary", "Salary")
]


def to_decimal(val) -> Decimal:
    if val is None:
        return Decimal("0.00")
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

class DuplicateResult(dict):
    def __init__(self, is_duplicate: bool, matched_transaction: Optional[Dict[str, Any]] = None, warning_message: str = ""):
        super().__init__(
            is_duplicate=is_duplicate,
            matched_transaction=matched_transaction,
            warning_message=warning_message
        )
        self.is_duplicate = is_duplicate
        self.matched_transaction = matched_transaction
        self.warning_message = warning_message

    def __iter__(self):
        return iter((self.is_duplicate, self.matched_transaction, self.warning_message))

def parse_sms_text(sms_text: str) -> Dict[str, Any]:
    """
    Parses bank or UPI SMS text into structured financial transaction fields.
    """
    if not sms_text or not sms_text.strip():
        return {
            "success": False,
            "error": "No SMS text provided.",
            "confidence": "LOW"
        }

    text = sms_text.strip()
    warnings = []
    unrecognized_tokens = []

    # Check for pure OTP / verification SMS without transaction action
    otp_pattern = r'(?i)\b(otp|one[-\s]time[-\s]password|verification\s+code|security\s+code)\b'
    if re.search(otp_pattern, text) and not re.search(r'(?i)\b(debited|credited|spent|paid|withdrawn|refunded)\b', text):
        return {
            "success": False,
            "error": "Message appears to be an authentication code or OTP, not a financial transaction.",
            "confidence": "NONE",
            "warnings": ["Authentication OTP detected. Ignored for transaction parsing."],
            "raw_text": text
        }

    # 1. Transaction Type Detection (DEBIT / EXPENSE vs CREDIT / INCOME)
    tx_type = "EXPENSE"
    type_confidence = False

    debit_patterns = [
        r'(?i)\b(debited|debit|spent|paid|withdrawn|deducted|sent|transferred to|charged)\b',
        r'(?i)\bdr\.?\b'
    ]
    credit_patterns = [
        r'(?i)\b(credited|credit|received|refunded|deposited|added to|salary|reversal)\b',
        r'(?i)\bcr\.?\b'
    ]

    for p in credit_patterns:
        if re.search(p, text):
            tx_type = "INCOME"
            type_confidence = True
            break

    if not type_confidence:
        for p in debit_patterns:
            if re.search(p, text):
                tx_type = "EXPENSE"
                type_confidence = True
                break

    if not type_confidence:
        warnings.append("Could not definitively determine if transaction is Debit or Credit. Defaulted to Expense.")

    # 2. Amount Extraction
    amount = Decimal("0.00")
    amount_patterns = [
        r'(?i)(?:inr|rs\.?|₹)\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)',
        r'(?i)(?:debited\s+by|debited\s+with|credited\s+by|spent|for)\s*(?:inr|rs\.?|₹)?\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)',
        r'([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2}))\s*(?:inr|rs\.?|₹)'
    ]

    for p in amount_patterns:
        match = re.search(p, text)
        if match:
            raw_amt = match.group(1).replace(',', '')
            try:
                val = Decimal(raw_amt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if val > Decimal("0.00"):
                    amount = val
                    break
            except Exception:
                pass

    if amount == Decimal("0.00"):
        # Fallback search for any isolated decimal number
        nums = re.findall(r'\b[0-9]+(?:\.[0-9]{2})\b', text)
        if nums:
            amount = to_decimal(nums[0])
            warnings.append("Amount inferred without explicit currency prefix.")

    if amount <= Decimal("0.00"):
        return {
            "success": False,
            "error": "Failed to extract transaction amount from message.",
            "confidence": "NONE",
            "warnings": warnings,
            "raw_text": text
        }

    # Extract Bank Name
    bank_name = None
    bank_match = re.search(r'(?i)\b(HDFC|SBI|ICICI|AXIS|KOTAK|PNB|BOB|CANARA|IDFC|CITI|YES BANK|PAYTM|INDUSIND)\b', text)
    if bank_match:
        bank_name = bank_match.group(1).upper()

    # 3. Account / Card Identifier Hint
    account_hint = None
    acc_patterns = [
        r'(?i)\b(?:a/c|acct|account|card|ac)\s*(?:no\.?|ending)?\s*[:\s]*([xX*]*[0-9]{3,6})\b',
        r'(?i)\b([xX*]{2,}[0-9]{3,4})\b',
        r'(?i)\b([A-Z0-9]+)\s+Bank\b'

    ]
    for p in acc_patterns:
        m = re.search(p, text)
        if m:
            account_hint = m.group(1).strip()
            break

    # 4. Reference Number (UPI / UTR / Txn ID)
    reference_number = None
    ref_patterns = [
        r'(?i)\b(?:upi\s*ref(?:\s*no)?|utr|rrn|txn\s*(?:id|no)?|ref(?:\s*no)?)\s*[:\-\s]*([a-zA-Z0-9]{6,20})\b',
        r'(?i)\bupi:([0-9]{8,16})\b'
    ]
    for p in ref_patterns:
        m = re.search(p, text)
        if m:
            reference_number = m.group(1).strip()
            break

    # 5. Transaction Date
    parsed_date = date.today().strftime("%Y-%m-%d")
    date_found = False

    # Check DD-MM-YYYY or DD/MM/YYYY or YYYY-MM-DD
    d1 = re.search(r'\b(20[2-3][0-9])[-/.](0[1-9]|1[0-2])[-/.](0[1-9]|[12][0-9]|3[01])\b', text)
    if d1:
        parsed_date = f"{d1.group(1)}-{d1.group(2)}-{d1.group(3)}"
        date_found = True
    else:
        d2 = re.search(r'\b(0[1-9]|[12][0-9]|3[01])[-/.](0[1-9]|1[0-2])[-/.](20[2-3][0-9]|[2-3][0-9])\b', text)
        if d2:
            yr = d2.group(3)
            if len(yr) == 2:
                yr = f"20{yr}"
            parsed_date = f"{yr}-{d2.group(2)}-{d2.group(1)}"
            date_found = True
        else:
            # Check DD-Mon-YY (e.g. 30-Sep-26, 29Sep26)
            d3 = re.search(r'\b(0[1-9]|[12][0-9]|3[01])\s*[-]?\s*([a-zA-Z]{3})\s*[-]?\s*(20[2-3][0-9]|[2-3][0-9])?\b', text)
            if d3:
                try:
                    day_part = d3.group(1)
                    mon_part = d3.group(2).title()
                    yr_part = d3.group(3) or str(date.today().year)
                    if len(yr_part) == 2:
                        yr_part = f"20{yr_part}"
                    dt = datetime.strptime(f"{day_part}-{mon_part}-{yr_part}", "%d-%b-%Y").date()
                    parsed_date = dt.strftime("%Y-%m-%d")
                    date_found = True
                except Exception:
                    pass

    if not date_found:
        warnings.append("Date not found in text; defaulted to today's date.")

    # 6. Merchant / Payee Extraction
    merchant = None
    merchant_patterns = [
        r'(?i)(?:at|to|info:|vpa|merchant:)\s*([a-zA-Z0-9\s&\'\.\-]+?)(?:\s+on|\s+ref|\s+upi|\s+bal|\.|$)',
        r'(?i)transfer(?:red)?\s+to\s+([a-zA-Z0-9\s&\'\.\-]+?)(?:\s+on|\s+ref|\s+upi|\.|$)',
        r'(?i)paid\s+to\s+([a-zA-Z0-9\s&\'\.\-]+?)(?:\s+on|\s+ref|\s+upi|\.|$)'
    ]
    for p in merchant_patterns:
        m = re.search(p, text)
        if m:
            cand = m.group(1).strip()
            # Clean unwanted tokens
            cand = re.sub(r'(?i)^(the|m/s|vpa)\s+', '', cand)
            if len(cand) >= 2 and not cand.lower() in ("your", "a/c", "account"):
                merchant = cand[:35].strip()
                break

    if not merchant:
        # Check against known merchant list
        for p, _, _ in MERCHANT_CATEGORY_RULES:
            m = re.search(p, text)
            if m:
                merchant = m.group(0).title()
                break

    if not merchant:
        merchant = "Unknown Payee"
        warnings.append("Merchant / Payee could not be detected reliably.")

    # 7. Category & Subcategory Suggestion
    suggested_category = "Food & Dining" if tx_type == "EXPENSE" else "Income"
    suggested_subcategory = "General"
    combined_query = f"{merchant} {text}"
    for p, cat, subcat in MERCHANT_CATEGORY_RULES:
        if re.search(p, combined_query):
            suggested_category = cat
            suggested_subcategory = subcat
            break

    # 8. Deterministic Confidence Rating
    score = 0
    if amount > Decimal("0.00"):
        score += 40
    if type_confidence:
        score += 20
    if date_found:
        score += 20
    if merchant != "Unknown Payee":
        score += 20

    if score >= 80:
        confidence = "HIGH"
    elif score >= 50:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "success": True,
        "amount": float(amount),
        "transaction_type": tx_type,
        "merchant": merchant,
        "merchant_clean": merchant,
        "date": parsed_date,
        "bank_name": bank_name,
        "account_last4": account_hint,
        "ref_number": reference_number,
        "category_inferred": suggested_category,
        "parsed_transaction": {
            "amount": float(amount),
            "transaction_type": tx_type,
            "merchant": merchant,
            "date": parsed_date,
            "date_inferred": not date_found,
            "account_hint": account_hint,
            "reference_number": reference_number,
            "suggested_category": suggested_category,
            "suggested_subcategory": suggested_subcategory,
            "note": f"{merchant} ({reference_number})" if reference_number else merchant
        },
        "confidence": confidence,
        "confidence_score": score,
        "warnings": warnings,
        "raw_text": text
    }


def detect_duplicate_transaction(
    user_id: int,
    amount: float,
    tx_date_str: Optional[str] = None,
    merchant: Optional[str] = None,
    reference_number: Optional[str] = None,
    db_path: str = "expenses.db",
    tx_date: Optional[str] = None,
    ref_number: Optional[str] = None,
    **kwargs
) -> DuplicateResult:
    """
    Detects potential duplicate transactions in the ledger.
    Searches +/- 2 days around target date for:
    1. Exact amount match AND (matching reference_number in note OR matching merchant substring in note).
    Returns DuplicateResult object (accessible as dict and unpackable as tuple).
    """
    tx_date_str = tx_date_str or tx_date or date.today().strftime("%Y-%m-%d")
    reference_number = reference_number or ref_number

    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        try:
            target_d = datetime.strptime(tx_date_str, "%Y-%m-%d").date()
        except Exception:
            target_d = date.today()

        min_d = (target_d - timedelta(days=2)).strftime("%Y-%m-%d")
        max_d = (target_d + timedelta(days=2)).strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT id, amount, date, note, transaction_type, account_id
            FROM transactions
            WHERE user_id = ?
              AND date >= ?
              AND date <= ?
              AND amount = ?
        """, (user_id, min_d, max_d, amount))
        candidates = cursor.fetchall()

        for c in candidates:
            c_dict = dict(c)
            note_lower = (c_dict.get("note") or "").lower()

            # Signal 1: Reference number match
            if reference_number and reference_number.lower() in note_lower:
                return DuplicateResult(True, c_dict, f"Found matching reference number '{reference_number}' already recorded on {c_dict['date']}.")


            # Signal 2: Merchant name match
            if merchant and merchant.lower() in note_lower:
                return DuplicateResult(True, c_dict, f"Matching amount (Rs.{amount:.2f}) and merchant '{merchant}' recorded on {c_dict['date']}.")

        # If matching exact date & amount even without merchant match, flag warning
        cursor.execute("""
            SELECT id, amount, date, note, transaction_type, account_id
            FROM transactions
            WHERE user_id = ? AND date = ? AND amount = ?
        """, (user_id, tx_date_str, amount))
        same_day_matches = cursor.fetchall()
        if same_day_matches:
            c_dict = dict(same_day_matches[0])
            return DuplicateResult(True, c_dict, f"Transaction of identical amount (Rs.{amount:.2f}) exists on the same day ({tx_date_str}).")

        return DuplicateResult(False, None, "No duplicate signals detected.")
    finally:
        conn.close()

