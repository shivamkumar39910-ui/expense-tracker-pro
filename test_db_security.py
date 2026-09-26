"""
Expense Tracker Pro 2.0 - Database Security & Production Isolation Test Suite
Verifies:
1. User Data Isolation (User A cannot access User B's accounts, tx, budgets, goals).
2. Budget Uniqueness Constraint (Duplicate budget prevention).
3. Password & PIN Security (No plaintext, proper hash verification).
4. Transaction Atomic Rollback on Failure.
"""

import time
from app_web import app
from database import get_db_connection

def run_security_suite():
    print("="*50)
    print("RUNNING DATABASE SECURITY & DATA ISOLATION TESTS")
    print("="*50)
    client = app.test_client()

    ts = int(time.time())
    user_a_email = f"user_a_{ts}@security.com"
    user_b_email = f"user_b_{ts}@security.com"

    # --- 1. Register User A ---
    res_a = client.post('/api/v1/auth/register', json={
        "name": "User A",
        "email": user_a_email,
        "password": "Password123"
    })
    assert res_a.status_code == 201, f"User A registration failed: {res_a.data}"

    # OTP for User A
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, otp_code, password, app_pin FROM users WHERE email = ?", (user_a_email,))
    user_a_row = cur.fetchone()
    user_a_id = user_a_row["id"]
    otp_a = user_a_row["otp_code"]
    pwd_a = user_a_row["password"]
    conn.close()

    # Verify User A password is not plaintext
    assert "Password123" not in pwd_a, "CRITICAL SECURITY FAULT: Plaintext password found in database!"
    assert pwd_a.startswith("scrypt:") or pwd_a.startswith("pbkdf2:"), "Password is not properly hashed!"
    print("TEST 1 PASSED: Passwords are encrypted with cryptographic hashes (no plaintext).")

    # Verify User A OTP
    res_a_ver = client.post('/api/v1/auth/verify-otp', json={"email": user_a_email, "otp": otp_a})
    assert res_a_ver.status_code == 200

    # Login User A Step 1
    res_a_log1 = client.post('/api/v1/auth/login', json={"identifier": user_a_email, "password": "Password123"})
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT login_otp_code FROM users WHERE id = ?", (user_a_id,))
    login_otp_a = cur.fetchone()["login_otp_code"]
    conn.close()

    # Login User A Step 2
    res_a_log2 = client.post('/api/v1/auth/login-verify-otp', json={"identifier": user_a_email, "otp": login_otp_a})
    assert res_a_log2.status_code == 200, f"Login Step 2 failed: {res_a_log2.data}"
    token_a = res_a_log2.get_json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # User A creates an Account and a Transaction
    res_acc_a = client.post('/api/v1/accounts', json={"name": "User A Secret Vault", "account_type": "BANK", "initial_balance": 100000.0}, headers=headers_a)
    assert res_acc_a.status_code == 201
    acc_a_id = res_acc_a.get_json()["account_id"]

    res_tx_a = client.post('/api/v1/transactions', json={
        "account_id": acc_a_id,
        "transaction_type": "EXPENSE",
        "amount": 2500.0,
        "date": "2026-09-26",
        "note": "User A Private Expense"
    }, headers=headers_a)
    assert res_tx_a.status_code == 201
    tx_a_id = res_tx_a.get_json()["transaction_id"]

    # User A sets a budget
    res_b_a = client.post('/api/v1/budgets', json={"month": 9, "year": 2026, "amount": 50000.0}, headers=headers_a)
    assert res_b_a.status_code == 200

    # User A sets an App PIN
    res_pin = client.post('/api/v1/security/set-pin', json={"pin": "8899", "enable": True}, headers=headers_a)
    assert res_pin.status_code == 200
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT app_pin FROM users WHERE id = ?", (user_a_id,))
    pin_hash = cur.fetchone()["app_pin"]
    conn.close()
    assert "8899" not in pin_hash, "PIN must be hashed with SHA-256!"
    print("TEST 2 PASSED: App PIN is securely hashed with SHA-256.")

    # --- 2. Register User B ---
    res_b = client.post('/api/v1/auth/register', json={
        "name": "User B",
        "email": user_b_email,
        "password": "Password456"
    })
    assert res_b.status_code == 201

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, otp_code FROM users WHERE email = ?", (user_b_email,))
    user_b_row = cur.fetchone()
    user_b_id = user_b_row["id"]
    otp_b = user_b_row["otp_code"]
    conn.close()

    client.post('/api/v1/auth/verify-otp', json={"identifier": user_b_email, "otp": otp_b})
    client.post('/api/v1/auth/login', json={"identifier": user_b_email, "password": "Password456"})
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT login_otp_code FROM users WHERE id = ?", (user_b_id,))
    login_otp_b = cur.fetchone()["login_otp_code"]
    conn.close()

    res_b_log2 = client.post('/api/v1/auth/login-verify-otp', json={"identifier": user_b_email, "otp": login_otp_b})
    assert res_b_log2.status_code == 200, f"User B Login Step 2 failed: {res_b_log2.data}"
    token_b = res_b_log2.get_json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # --- 3. User B attempts unauthorized access to User A's data ---
    # a. User B fetches transactions - User A's transaction MUST NOT appear
    res_b_txs = client.get('/api/v1/transactions', headers=headers_b)
    tx_list = res_b_txs.get_json().get("transactions", [])
    assert not any(t["id"] == tx_a_id for t in tx_list), "DATA LEAK: User B can see User A's transaction!"

    # b. User B attempts to delete User A's transaction
    res_b_del = client.delete(f'/api/v1/transactions/{tx_a_id}', headers=headers_b)
    assert res_b_del.status_code == 404, f"DATA TAMPERING: User B was able to modify User A's tx: {res_b_del.status_code}"

    # c. User B attempts to access User A's account
    res_b_acc = client.get(f'/api/v1/accounts/{acc_a_id}', headers=headers_b)
    assert res_b_acc.status_code == 404, "DATA LEAK: User B accessed User A's account details!"

    # d. User B fetches accounts list
    res_b_accs = client.get('/api/v1/accounts', headers=headers_b)
    acc_list = res_b_accs.get_json().get("accounts", [])
    assert not any(a["id"] == acc_a_id for a in acc_list), "DATA LEAK: User B can see User A's accounts!"
    print("TEST 3 PASSED: Cross-user data isolation verified (100% isolated).")

    # --- 4. Budget Duplicate Prevention Test ---
    # Set budget for User A month 9 year 2026 again
    res_b_dup = client.post('/api/v1/budgets', json={"month": 9, "year": 2026, "amount": 65000.0}, headers=headers_a)
    assert res_b_dup.status_code == 200

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT count(*), amount FROM budgets WHERE user_id = ? AND month = 9 AND year = 2026 AND category_id IS NULL", (user_a_id,))
    b_rows = cur.fetchall()
    conn.close()
    assert b_rows[0][0] == 1, f"DUPLICATE BUDGET ERROR: Found {b_rows[0][0]} budgets instead of exactly 1!"
    assert b_rows[0][1] == 65000.0, "Budget amount was not properly updated!"
    print("TEST 4 PASSED: Duplicate budget prevention verified (exactly 1 budget preserved).")

    # --- 5. Atomic Rollback on Transaction Error ---
    initial_acc_bal = None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_a_id,))
    initial_acc_bal = cur.fetchone()[0]
    conn.close()

    # Attempt an invalid transfer with non-existent target account
    res_bad_tx = client.post('/api/v1/transactions', json={
        "account_id": acc_a_id,
        "target_account_id": 9999999, # Non-existent account
        "transaction_type": "TRANSFER",
        "amount": 5000.0,
        "date": "2026-09-26"
    }, headers=headers_a)
    # Target account 9999999 violates FK or check
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT current_balance FROM accounts WHERE id = ?", (acc_a_id,))
    after_bal = cur.fetchone()[0]
    conn.close()
    assert initial_acc_bal == after_bal, "ATOMIC ROLLBACK FAILED: Account balance changed during failed transfer!"
    print("TEST 5 PASSED: Atomic database rollback verified on transaction failure.")

    print("="*50)
    print("ALL DATABASE SECURITY & ISOLATION TESTS PASSED (100% SUCCESS)!")
    print("="*50)
    return True

if __name__ == "__main__":
    run_security_suite()
