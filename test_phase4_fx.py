"""
Phase 4 Live FX Rates & Caching Test Suite
Tests:
1. Retrieve supported currencies with live exchange rates
2. Verify display pair formatting (1 USD = ₹XX.XX)
3. Verify rate caching behavior
4. Verify graceful timeout/network error fallback to baseline rates
"""

import time
import app
import fx_service

def run_tests():
    client = app.app.test_client()

    print("=" * 50)
    print("RUNNING PHASE 4 LIVE FX RATES & CACHING TESTS")
    print("=" * 50)

    # 1. Test live rates retrieval
    res = client.get('/api/v1/currencies')
    assert res.status_code == 200
    data = res.json["currencies"]
    assert len(data) == 9
    print(f"TEST 1 PASSED: Retrieved {len(data)} currencies with exchange rates.")

    # 2. Verify display pair structure
    usd_item = [c for c in data if c["code"] == "USD"][0]
    assert "display_pair" in usd_item
    assert usd_item["display_pair"].startswith("1 USD = ")
    assert usd_item["rate_to_inr"] > 0
    assert "last_updated" in usd_item
    print(f"TEST 2 PASSED: Display pair verified: 1 USD = Rs. {usd_item['rate_to_inr']:.2f} (Updated: {usd_item['last_updated']}).")

    # 3. Test Cache (Warm cache response)
    start_time = time.time()
    res_cached = client.get('/api/v1/currencies')
    elapsed = time.time() - start_time
    assert res_cached.status_code == 200
    assert elapsed < 0.1, f"Expected sub-100ms cached response, took {elapsed:.3f}s"
    print(f"TEST 3 PASSED: In-memory cache returned in {elapsed*1000:.1f}ms.")

    # 4. Test Failure Fallback (Simulate network outage)
    orig_url = fx_service.FX_API_PROVIDER_URL
    fx_service.FX_API_PROVIDER_URL = "https://invalid-nonexistent-domain-fx-test.com/api"
    # Force cache expiry to test fallback branch
    from datetime import datetime, timedelta
    fx_service._CACHE_EXPIRY = datetime.utcnow() - timedelta(minutes=1)

    fallback_currencies = fx_service.get_currencies_with_live_rates()
    assert len(fallback_currencies) == 9
    usd_fallback = [c for c in fallback_currencies if c["code"] == "USD"][0]
    assert usd_fallback["rate_to_inr"] > 0
    print(f"TEST 4 PASSED: Graceful network outage fallback returned baseline rate (1 USD = Rs. {usd_fallback['rate_to_inr']:.2f}).")

    # Restore URL
    fx_service.FX_API_PROVIDER_URL = orig_url

    print("=" * 50)
    print("ALL PHASE 4 LIVE FX TESTS PASSED (100% SUCCESS)!")
    print("=" * 50)

if __name__ == '__main__':
    run_tests()
