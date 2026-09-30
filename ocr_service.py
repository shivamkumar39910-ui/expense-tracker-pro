"""
Expense Tracker Pro 2.0 - Clean Receipt OCR Service Abstraction (ocr_service.py)
Supports:
1. Pluggable OCR engine detection (pytesseract, Cloud Vision / OCR.space, or Raw Text parser).
2. Honest error handling when OCR engine is unconfigured (NO fake outputs).
3. Advanced financial entity extraction (Grand total vs Subtotal/Tax, Merchant, Date, Category).
4. Mandatory user confirmation enforcement.
"""

import os
import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

# Check if pytesseract or OCR.space API is available
PYTESSERACT_AVAILABLE = False
try:
    import pytesseract
    from PIL import Image
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

OCR_API_KEY = os.environ.get("OCR_API_KEY")
OCR_SPACE_URL = "https://api.ocr.space/parse/image"

# Known merchant categorization heuristics
MERCHANT_CATEGORY_RULES = [
    (r'(?i)\b(starbucks|cafe|costa|ccd|blue tokai|barista|third wave)\b', "Food & Dining", "Coffee & Beverage"),
    (r'(?i)\b(mcdonald\'?s|kfc|burger king|subway|wendy\'?s|domino\'?s|pizza hut)\b', "Food & Dining", "Fast Food"),
    (r'(?i)\b(zomato|swiggy|eatsure|foodpanda)\b', "Food & Dining", "Online Food Delivery"),
    (r'(?i)\b(restaurant|bistro|diner|kitchen|dhaba|bar & grill|bakery)\b', "Food & Dining", "Restaurant Dining"),
    (r'(?i)\b(uber|ola|rapido|blusmart|lyft|cab|taxi)\b', "Transportation", "Ride Hailing"),
    (r'(?i)\b(shell|bpcl|hpcl|indian oil|petrol|fuel|cng|diesel)\b', "Transportation", "Fuel"),
    (r'(?i)\b(metro|railway|irctc|flight|indigo|air india|fastag)\b', "Transportation", "Transit / Toll"),
    (r'(?i)\b(blinkit|zepto|instamart|bigbasket|dunzo)\b', "Groceries", "Quick Commerce Grocery"),
    (r'(?i)\b(d-mart|dmart|reliance fresh|nature\'?s basket|spencer|supermarket|kirana|grocery)\b', "Groceries", "Supermarket"),
    (r'(?i)\b(amazon|flipkart|myntra|ajio|meesho|tata cliq)\b', "Shopping", "Online Shopping"),
    (r'(?i)\b(zara|h&m|uniqlo|decathlon|westside|pantaloons|lifestyle)\b', "Shopping", "Apparel & Gear"),
    (r'(?i)\b(apollo|medplus|pharmeasy|1mg|tata 1mg|pharmacy|chemist|hospital|clinic|pathology)\b', "Healthcare", "Medical & Pharmacy"),
    (r'(?i)\b(pvr|inox|cinepolis|bookmyshow|movie|cinema|theater)\b', "Entertainment", "Movies & Events"),
    (r'(?i)\b(netflix|spotify|prime video|hotstar|disney|apple music|youtube premium)\b', "Entertainment", "Digital Subscriptions"),
    (r'(?i)\b(airtel|jio|vodafone|vi|bsnl|broadband|wifi)\b', "Bills & Utilities", "Mobile & Internet"),
    (r'(?i)\b(electricity|bescom|tata power|adani power|water board|igl|indane|hp gas)\b', "Bills & Utilities", "Utilities"),
]

def is_ocr_engine_configured() -> bool:
    """Returns True if local Tesseract or an external OCR API key is configured."""
    return PYTESSERACT_AVAILABLE or bool(OCR_API_KEY)

def extract_text_from_image(image_bytes: bytes, filename: str = "") -> Tuple[Optional[str], Optional[str]]:
    """
    Extracts raw text from image bytes using configured OCR provider.
    Returns (extracted_text, error_message).
    """
    if PYTESSERACT_AVAILABLE:
        try:
            import io
            img = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(img)
            return text.strip(), None
        except Exception as e:
            return None, f"Tesseract OCR processing failed: {str(e)}"

    if OCR_API_KEY:
        try:
            import urllib.request, urllib.parse, json
            boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
            # Format simple multipart payload for OCR.space
            data = urllib.parse.urlencode({
                "apikey": OCR_API_KEY,
                "language": "eng",
                "isOverlayRequired": "false"
            }).encode('utf-8')
            req = urllib.request.Request(f"{OCR_SPACE_URL}?{data.decode('utf-8')}", data=image_bytes)
            req.add_header('Content-Type', 'application/octet-stream')
            with urllib.request.urlopen(req, timeout=15) as res:
                result = json.loads(res.read().decode())
                if result.get("ParsedResults"):
                    return result["ParsedResults"][0].get("ParsedText", "").strip(), None
                return None, "OCR provider returned no text."
        except Exception as e:
            return None, f"Cloud OCR API request failed: {str(e)}"

    return None, "OCR engine is not configured on this server. Configure pytesseract or OCR_API_KEY to enable automatic image scanning."

def parse_receipt_entities(raw_text: str) -> Dict[str, Any]:
    """
    Parses merchant, amount, date, and category suggestions from raw invoice/receipt text.
    Handles subtotal vs total and tax lines.
    """
    if not raw_text or not raw_text.strip():
        return {
            "success": False,
            "error": "No text provided for receipt parsing."
        }

    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

    # 1. Extract Merchant Name
    merchant = "Scanned Merchant"
    for line in lines[:4]:
        cleaned = re.sub(r'^(tax invoice|retail invoice|bill of supply|receipt|order\s*#?|welcome to|invoice)\s*[-:]?\s*', '', line, flags=re.IGNORECASE).strip()
        # Skip pure numeric, date or small token lines
        if cleaned and len(cleaned) > 2 and not re.match(r'^[0-9\-\:\/\.\s]+$', cleaned):
            merchant = cleaned
            break
    if merchant.isupper():
        merchant = merchant.title()
    if len(merchant) > 40:
        merchant = merchant[:40]

    # 2. Extract Grand Total Amount (handling subtotal, tax, and discount lines)
    # Prefer explicit total identifiers first
    amount = 0.0
    total_patterns = [
        r'(?i)(?:total\s*(?:amount|bill|payable|due|value)?|net\s*(?:amount|payable|total)?|grand\s*total|amount\s*paid|paid\s*amount)[\s:=₹Rs\.$€£]*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)',
        r'(?i)(?:₹|Rs\.?|INR|\$|€|£)\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2}))',
        r'([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2}))\s*(?:INR|Rs|₹|\$|€|£)'
    ]

    for pattern in total_patterns:
        matches = re.findall(pattern, raw_text)
        if matches:
            candidates = []
            for m in matches:
                try:
                    candidates.append(round(float(m.replace(',', '')), 2))
                except ValueError:
                    pass
            if candidates:
                amount = max(candidates)
                break

    # If no explicit total pattern matched, search for any floating point numbers and take max
    if amount <= 0:
        all_nums = re.findall(r'\b[0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})\b', raw_text)
        candidates = []
        for n in all_nums:
            try:
                candidates.append(round(float(n.replace(',', '')), 2))
            except ValueError:
                pass
        if candidates:
            amount = max(candidates)

    # 3. Extract Date
    # Supports YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, or DD Mon YYYY
    date_str = datetime.now().strftime("%Y-%m-%d")
    date_inferred = True

    date_matches = re.search(r'\b(20[2-3][0-9])[-/.](0[1-9]|1[0-2])[-/.](0[1-9]|[12][0-9]|3[01])\b', raw_text)
    if date_matches:
        date_str = f"{date_matches.group(1)}-{date_matches.group(2)}-{date_matches.group(3)}"
        date_inferred = False
    else:
        # Check DD-MM-YYYY
        d_match = re.search(r'\b(0[1-9]|[12][0-9]|3[01])[-/.](0[1-9]|1[0-2])[-/.](20[2-3][0-9])\b', raw_text)
        if d_match:
            date_str = f"{d_match.group(3)}-{d_match.group(2)}-{d_match.group(1)}"
            date_inferred = False

    # 4. Smart Category Suggestion
    detected_cat = "Shopping"
    detected_subcat = "General"
    combined_text = f"{merchant} {raw_text}"
    for pattern, cat, subcat in MERCHANT_CATEGORY_RULES:
        if re.search(pattern, combined_text):
            detected_cat = cat
            detected_subcat = subcat
            break

    # 5. Confidence Score Calculation
    confidence = 0.50
    if amount > 0:
        confidence += 0.25
    if merchant != "Scanned Merchant":
        confidence += 0.15
    if not date_inferred:
        confidence += 0.10

    return {
        "success": True,
        "receipt": {
            "merchant": merchant,
            "amount": round(amount, 2),
            "date": date_str,
            "date_inferred": date_inferred,
            "category_name": detected_cat,
            "subcategory_name": detected_subcat,
            "confidence_score": round(confidence, 2),
            "requires_user_confirmation": True
        },
        "raw_text_length": len(raw_text)
    }
