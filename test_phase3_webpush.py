"""
Phase 3 Web Push & Notification Preferences Test Suite
Tests:
1. Retrieve VAPID public key
2. Save push subscription
3. Read & update notification preferences
4. Unsubscribe push endpoint
"""

import time
import app

def run_tests():
    client = app.app.test_client()
    ts = int(time.time())
    email = f"push_tester_{ts}@test.com"

    r = client.post('/api/v1/auth/register', json={'name': 'Push Tester', 'email': email, 'password': 'Password123'})
    v = client.post('/api/v1/auth/verify-otp', json={'identifier': email, 'otp': r.json['otp_code']})
    token = v.json['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    print("=" * 50)
    print("RUNNING PHASE 3 WEB PUSH & PREFERENCES TESTS")
    print("=" * 50)

    # 1. Get VAPID public key
    pk_res = client.get('/api/v1/notifications/push/public-key', headers=headers)
    assert pk_res.status_code == 200
    assert "public_key" in pk_res.json
    print("TEST 1 PASSED: VAPID public key endpoint verified.")

    # 2. Subscribe push endpoint
    sub_res = client.post('/api/v1/notifications/push/subscribe', headers=headers, json={
        "endpoint": f"https://updates.push.services.mozilla.com/wpush/v2/{ts}",
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9t0A4If_ZqMmLzYAReXWCqrVWehS49-GuA",
            "auth": "tBHItJI5svbpez7KI4CCXg"
        }
    })
    assert sub_res.status_code == 201
    assert sub_res.json["success"] is True
    print("TEST 2 PASSED: Push subscription saved successfully.")

    # 3. Read default notification preferences
    prefs_res = client.get('/api/v1/notifications/preferences', headers=headers)
    assert prefs_res.status_code == 200
    prefs = prefs_res.json["preferences"]
    assert prefs["budget_80"] == 1
    assert prefs["budget_100"] == 1
    print("TEST 3 PASSED: Default notification preferences retrieved (budget alerts active).")

    # 4. Update notification preferences
    update_prefs = client.post('/api/v1/notifications/preferences', headers=headers, json={
        "budget_80": 0,
        "budget_100": 1,
        "bill_due": 1,
        "security_alerts": 1
    })
    assert update_prefs.status_code == 200
    assert update_prefs.json["preferences"]["budget_80"] == 0
    print("TEST 4 PASSED: Notification preferences updated (budget_80 toggled off).")

    # 5. Unsubscribe push endpoint
    unsub_res = client.post('/api/v1/notifications/push/unsubscribe', headers=headers, json={
        "endpoint": f"https://updates.push.services.mozilla.com/wpush/v2/{ts}"
    })
    assert unsub_res.status_code == 200
    print("TEST 5 PASSED: Push endpoint unsubscribed successfully.")

    print("=" * 50)
    print("ALL PHASE 3 WEB PUSH TESTS PASSED (100% SUCCESS)!")
    print("=" * 50)

if __name__ == '__main__':
    run_tests()
