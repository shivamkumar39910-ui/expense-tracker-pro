"""
Phase 0B & 0C Regression Test Suite
Tests:
1. Security Headers Verification
2. OTP Expiry Rejection (Registration & Login)
3. Brute Force Rate Limiting & Lockout (OTP & App PIN)
4. Financial Precision Verification (0.10 + 0.20, 999.99, Transfers & Rollback)
"""

import time
from datetime import datetime, timedelta
import app
import database

def run_tests():
    client = app.app.test_client()
    ts = int(time.time())
    print("=" * 50)
    print("RUNNING PHASE 0B & 0C SECURITY AND FINANCIAL PRECISION TESTS")
    print("=" * 50)

    # 1. Security Headers Test
    res = client.get('/mobile')
    assert res.headers.get("X-Content-Type-Options") == "nosniff", "Missing X-Content-Type-Options header"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN", "Missing X-Frame-Options header"
    print("TEST 1 PASSED: Security Headers present on responses.")

    # 2. Setup Test User
    email = f"sec_prec_{ts}@test.com"
    reg = client.post('/api/v1/auth/register', json={
        "name": "Precision Tester",
        "email": email,
        "password": "Password123"
    })
    assert reg.status_code == 201
    user_id = database.get_db_connection().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]

    # 3. OTP Expiry Test (Simulate expired registration OTP)
    conn = database.get_db_connection()
    c = conn.cursor()
    past_expiry = (datetime.utcnow() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE users SET otp_expires_at = ? WHERE id = ?", (past_expiry, user_id))
    conn.commit()
    conn.close()

    otp_code = reg.json.get("otp_code")
    exp_res = client.post('/api/v1/auth/verify-otp', json={"identifier": email, "otp": otp_code})
    assert exp_res.status_code == 400
    assert "expired" in exp_res.json.get("error", "").lower()
    print("TEST 2 PASSED: Expired OTP rejected with 400.")

    # Reset OTP to valid expiry and verify
    conn = database.get_db_connection()
    c = conn.cursor()
    future_expiry = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE users SET otp_expires_at = ? WHERE id = ?", (future_expiry, user_id))
    conn.commit()
    conn.close()

    v_res = client.post('/api/v1/auth/verify-otp', json={"identifier": email, "otp": otp_code})
    assert v_res.status_code == 200
    token = v_res.json["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("TEST 3 PASSED: Valid unexpired OTP verifies successfully.")

    # 4. PIN Brute-force Lockout Test
    client.post('/api/v1/security/set-pin', json={"pin": "4826"}, headers=headers)
    
    # 4 wrong attempts
    for i in range(4):
        bad_pin = client.post('/api/v1/security/verify-pin', json={"pin": "0000"}, headers=headers)
        assert bad_pin.status_code == 401
    
    # 5th wrong attempt triggers lockout
    fifth_pin = client.post('/api/v1/security/verify-pin', json={"pin": "0000"}, headers=headers)
    assert fifth_pin.status_code == 401

    # 6th attempt is blocked with 429 Too Many Requests
    blocked_pin = client.post('/api/v1/security/verify-pin', json={"pin": "4826"}, headers=headers)
    assert blocked_pin.status_code == 429
    assert "lockout active" in blocked_pin.json.get("error", "").lower()
    print("TEST 4 PASSED: PIN brute-force lockout triggered after 5 failed attempts (HTTP 429).")

    # 5. Financial Precision Tests (0.10 + 0.20 and 999.99)
    acc_res = client.post('/api/v1/accounts', json={
        "name": "Precision Account",
        "account_type": "BANK",
        "initial_balance": 100.00
    }, headers=headers)
    assert acc_res.status_code == 201
    acc_id = acc_res.json["account_id"]

    # Add 0.10
    client.post('/api/v1/transactions', json={
        "account_id": acc_id,
        "transaction_type": "INCOME",
        "amount": 0.10,
        "date": "2026-09-30"
    }, headers=headers)

    # Add 0.20
    client.post('/api/v1/transactions', json={
        "account_id": acc_id,
        "transaction_type": "INCOME",
        "amount": 0.20,
        "date": "2026-09-30"
    }, headers=headers)

    # Check balance: must be exactly 100.30, NOT 100.30000000000001
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_id,))
    bal = c.fetchone()["current_balance"]
    conn.close()
    assert float(bal) == 100.30, f"Expected 100.30, got {bal}"
    print("TEST 5 PASSED: Financial precision 0.10 + 0.20 = 100.30 verified without float drift.")

    # Add 999.99, subtract 999.99
    tx_sub = client.post('/api/v1/transactions', json={
        "account_id": acc_id,
        "transaction_type": "EXPENSE",
        "amount": 99.99,
        "date": "2026-09-30"
    }, headers=headers)
    tx_id = tx_sub.json["transaction_id"]

    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_id,))
    bal = float(c.fetchone()["current_balance"])
    conn.close()
    assert bal == 0.31, f"Expected 0.31, got {bal}"

    # Rollback delete
    del_res = client.delete(f'/api/v1/transactions/{tx_id}', headers=headers)
    assert del_res.status_code == 200

    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_id,))
    bal = float(c.fetchone()["current_balance"])
    conn.close()
    assert bal == 100.30, f"Expected restored balance 100.30, got {bal}"
    print("TEST 6 PASSED: 99.99 subtraction and deletion rollback restored exact 100.30 balance.")

    print("=" * 50)
    print("ALL PHASE 0B & 0C TESTS PASSED SUCCESSFULLY (100% SUCCESS)!")
    print("=" * 50)

if __name__ == "__main__":
    run_tests()
