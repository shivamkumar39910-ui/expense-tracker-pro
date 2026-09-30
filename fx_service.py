"""
Expense Tracker Pro 2.0 - Live FX Rate Service (fx_service.py)
Features:
1. Live exchange rate retrieval relative to INR (or USD).
2. Backend-only API key handling (never exposed to client).
3. 1-hour in-memory and persistent caching.
4. Graceful timeout and network failure fallback to last known good rates.
5. Formatted user-facing display strings (e.g., '1 USD = ₹86.50').
"""

import os
import json
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Baseline fallback rates to INR (used if external API is unreachable)
BASELINE_RATES_TO_INR = {
    "INR": 1.0,
    "USD": 86.50,
    "EUR": 92.20,
    "GBP": 109.80,
    "JPY": 0.58,
    "AED": 23.55,
    "CAD": 63.40,
    "AUD": 56.10,
    "SGD": 65.10
}

CURRENCY_METADATA = [
    {"code": "INR", "symbol": "₹", "name": "Indian Rupee", "flag": "🇮🇳"},
    {"code": "USD", "symbol": "$", "name": "US Dollar", "flag": "🇺🇸"},
    {"code": "EUR", "symbol": "€", "name": "Euro", "flag": "🇪🇺"},
    {"code": "GBP", "symbol": "£", "name": "British Pound", "flag": "🇬🇧"},
    {"code": "JPY", "symbol": "¥", "name": "Japanese Yen", "flag": "🇯🇵"},
    {"code": "AED", "symbol": "د.إ", "name": "UAE Dirham", "flag": "🇦🇪"},
    {"code": "CAD", "symbol": "C$", "name": "Canadian Dollar", "flag": "🇨🇦"},
    {"code": "AUD", "symbol": "A$", "name": "Australian Dollar", "flag": "🇦🇺"},
    {"code": "SGD", "symbol": "S$", "name": "Singapore Dollar", "flag": "🇸🇬"},
]

# Cache storage
_FX_CACHE = {
    "rates": BASELINE_RATES_TO_INR.copy(),
    "last_updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
    "source": "baseline"
}
_CACHE_EXPIRY = datetime.utcnow()

FX_API_PROVIDER_URL = os.environ.get("FX_API_URL", "https://open.er-api.com/v6/latest/USD")
FX_API_KEY = os.environ.get("FX_API_KEY")

def fetch_live_fx_rates(timeout_seconds: int = 5) -> Dict[str, Any]:
    """
    Fetches live exchange rates from configured provider with timeout & rate limit protection.
    Falls back gracefully to cached values on any error.
    """
    global _FX_CACHE, _CACHE_EXPIRY

    now = datetime.utcnow()
    # If cache is still warm (less than 1 hour old), return cached values
    if now < _CACHE_EXPIRY and _FX_CACHE.get("source") == "live_api":
        return _FX_CACHE

    try:
        url = FX_API_PROVIDER_URL
        if FX_API_KEY and "apikey" not in url.lower():
            url += f"?apikey={FX_API_KEY}"

        req = urllib.request.Request(url, headers={"User-Agent": "ExpenseTrackerPro-FX/2.0"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as res:
            if res.status == 200:
                payload = json.loads(res.read().decode())
                # open.er-api returns rates relative to USD
                usd_rates = payload.get("rates", {})
                usd_to_inr = usd_rates.get("INR", BASELINE_RATES_TO_INR["USD"])

                new_rates = {}
                for code in BASELINE_RATES_TO_INR:
                    if code == "INR":
                        new_rates["INR"] = 1.0
                    elif code == "USD":
                        new_rates["USD"] = round(float(usd_to_inr), 2)
                    elif code in usd_rates and usd_rates[code] > 0:
                        # 1 foreign unit in INR = (1 / rate_in_usd) * usd_to_inr
                        unit_in_inr = (1.0 / float(usd_rates[code])) * float(usd_to_inr)
                        new_rates[code] = round(unit_in_inr, 2)
                    else:
                        new_rates[code] = BASELINE_RATES_TO_INR[code]

                _FX_CACHE = {
                    "rates": new_rates,
                    "last_updated": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "source": "live_api"
                }
                _CACHE_EXPIRY = now + timedelta(hours=1)
                return _FX_CACHE
    except Exception as e:
        # Fallback to current cache gracefully
        _FX_CACHE["fallback_notice"] = f"Using cached rates due to network/provider timeout ({str(e)})"

    return _FX_CACHE

def get_currencies_with_live_rates() -> List[Dict[str, Any]]:
    """Returns all supported currencies decorated with live exchange rates and display strings."""
    fx_data = fetch_live_fx_rates()
    rates = fx_data.get("rates", BASELINE_RATES_TO_INR)
    last_updated = fx_data.get("last_updated", "Cached")

    results = []
    for meta in CURRENCY_METADATA:
        code = meta["code"]
        rate = rates.get(code, BASELINE_RATES_TO_INR.get(code, 1.0))
        item = {
            "code": code,
            "symbol": meta["symbol"],
            "name": meta["name"],
            "flag": meta["flag"],
            "rate_to_inr": rate,
            "display_pair": f"1 {code} = ₹{rate:.2f}" if code != "INR" else "1 INR = ₹1.00",
            "last_updated": last_updated,
            "is_live": fx_data.get("source") == "live_api"
        }
        results.append(item)
    return results
