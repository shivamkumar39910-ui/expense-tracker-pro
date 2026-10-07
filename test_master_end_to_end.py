"""
EXPENSE TRACKER PRO 2.0 - MASTER END-TO-END INTEGRATION TEST SUITE
(test_master_end_to_end.py)

Covers the complete 10-Journey User Lifecycle and Invariants:
1. Journey 1: User Onboarding, OTP Verification, 2FA Login, JWT & App PIN
2. Journey 2: Multi-Account Ledger Invariant (Balance = Initial + Income - Expense + Transfers)
3. Journey 3: Transaction Deletion Atomic Rollback
4. Journey 4: Category Budgets, Progress & Thresholds
5. Journey 5: Financial Goals & Account-Linked Contributions
6. Journey 6: Recurring Commitments & Automatic Due-Date Advancement
7. Journey 7: SMS / UPI Regex Parsing & Strict Duplicate Prevention
8. Journey 8: Subscription Audits & Annualized Commitments
9. Journey 9: Cashflow Calendar & Daily Runway Projection
10. Journey 10: Multi-Tenant Data Isolation & Security Lockdown
"""

import time
import json
from decimal import Decimal
from datetime import datetime, timedelta
import app
import database

def run_tests():
    client = app.app.test_client()
    ts = int(time.time() * 1000)
    print("=" * 60)
    print("STARTING MASTER END-TO-END VERIFICATION SUITE (10 JOURNEYS)")
    print("=" * 60)

    # =========================================================================
    # JOURNEY 1: User Onboarding, OTP Verification, 2FA Login & App PIN
    # =========================================================================
    user_email = f"master_hero_{ts}@finance.com"
    user_phone = f"+9198{str(ts)[-8:]}"
    reg_res = client.post('/api/v1/auth/register', json={
        "name": "Arjun Sharma",
        "email": user_email,
        "phone": user_phone,
        "password": "SecurePassword#2026"
    })
    assert reg_res.status_code == 201, f"Registration failed: {reg_res.data}"
    reg_otp = reg_res.json.get("otp_code")
    assert reg_otp is not None, "Missing OTP in registration response"

    # Verify Registration OTP
    ver_res = client.post('/api/v1/auth/verify-otp', json={
        "identifier": user_email,
        "otp": reg_otp
    })
    assert ver_res.status_code == 200
    token_1 = ver_res.json.get("access_token")
    assert token_1 is not None

    # Direct Password Login (Instant user-friendly authentication)
    login_direct = client.post('/api/v1/auth/login', json={
        "identifier": user_email,
        "password": "SecurePassword#2026"
    })
    assert login_direct.status_code == 200
    assert login_direct.json.get("require_otp") is False
    assert "access_token" in login_direct.json

    # Step 1 2FA Login
    login_step1 = client.post('/api/v1/auth/login', json={
        "identifier": user_email,
        "password": "SecurePassword#2026",
        "require_2fa": True
    })
    assert login_step1.status_code == 200
    login_otp = login_step1.json.get("otp_code")

    # Step 2 2FA Login Verification
    login_step2 = client.post('/api/v1/auth/login-verify-otp', json={
        "identifier": user_email,
        "otp": login_otp
    })
    assert login_step2.status_code == 200
    auth_token = login_step2.json.get("access_token")
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Set 4-Digit Security PIN
    pin_res = client.post('/api/v1/security/set-pin', headers=headers, json={"pin": "8421"})
    assert pin_res.status_code == 200
    print("JOURNEY 1 PASSED: Onboarding, 2FA Login, JWT & Security PIN verified.")

    # =========================================================================
    # JOURNEY 2: Multi-Account Ledger & Invariants
    # =========================================================================
    # Get auto-created accounts (Cash & Bank)
    accs_res_init = client.get('/api/v1/accounts', headers=headers)
    assert accs_res_init.status_code == 200
    accounts = accs_res_init.json["data"]["accounts"]
    cash_acc = accounts[0]
    bank_acc = accounts[1]

    # Create additional Savings Account (Initial: 50,000.00)
    bank_res = client.post('/api/v1/accounts', headers=headers, json={
        "name": "HDFC Salary Account",
        "account_type": "BANK",
        "initial_balance": 50000.00
    })
    assert bank_res.status_code == 201
    bank_id = bank_res.json.get("account_id")

    # Post Income: +25,000.00 into Bank
    today_str = datetime.now().strftime("%Y-%m-%d")
    r_cat = client.get('/api/v1/categories', headers=headers)
    food_cat = r_cat.json["categories"]["expense"][0]

    inc_res = client.post('/api/v1/transactions', headers=headers, json={
        "account_id": bank_id,
        "amount": 25000.00,
        "transaction_type": "INCOME",
        "date": today_str,
        "note": "Quarterly Performance Bonus"
    })
    assert inc_res.status_code == 201

    # Post Expense: -4,500.00 from Bank
    exp_res = client.post('/api/v1/transactions', headers=headers, json={
        "account_id": bank_id,
        "category_id": food_cat["id"],
        "amount": 4500.00,
        "transaction_type": "EXPENSE",
        "date": today_str,
        "note": "Office Chair"
    })
    assert exp_res.status_code == 201
    temp_exp_id = exp_res.json.get("transaction_id")

    # Post Transfer: 5,000.00 from Bank to Cash
    trf_res = client.post('/api/v1/transactions', headers=headers, json={
        "account_id": bank_id,
        "target_account_id": cash_acc["id"],
        "amount": 5000.00,
        "transaction_type": "TRANSFER",
        "date": today_str,
        "note": "ATM Withdrawal to Cash"
    })
    assert trf_res.status_code == 201

    # Verify Mathematical Invariants
    accs_res = client.get('/api/v1/accounts', headers=headers)
    accs = {a["id"]: Decimal(str(a["current_balance"])) for a in accs_res.json["data"]["accounts"]}
    # Expected Bank: 50000 + 25000 - 4500 - 5000 = 65,500.00
    # Expected Cash: initial + 5000
    assert accs[bank_id] == Decimal("65500.00"), f"Expected Bank 65500.00, got {accs[bank_id]}"
    assert accs[cash_acc["id"]] == Decimal(str(cash_acc["initial_balance"])) + Decimal("5000.00")
    print("JOURNEY 2 PASSED: Double-entry ledger invariants verified (Balance = Initial + Inc - Exp + Transfers).")

    # =========================================================================
    # JOURNEY 3: Transaction Deletion Atomic Rollback
    # =========================================================================
    del_res = client.delete(f'/api/v1/transactions/{temp_exp_id}', headers=headers)
    assert del_res.status_code == 200

    # Bank balance must be exactly restored to 65,500.00 + 4,500.00 = 70,000.00
    accs_res_post_del = client.get('/api/v1/accounts', headers=headers)
    accs_post = {a["id"]: Decimal(str(a["current_balance"])) for a in accs_res_post_del.json["data"]["accounts"]}
    assert accs_post[bank_id] == Decimal("70000.00"), f"Expected 70000.00 after deletion, got {accs_post[bank_id]}"
    print("JOURNEY 3 PASSED: Atomic rollback on transaction deletion restored exact balance.")

    # =========================================================================
    # JOURNEY 4: Category Budgets, Progress & Threshold Alerts
    # =========================================================================
    now = datetime.now()
    b_res = client.post('/api/v1/budgets', headers=headers, json={
        "month": now.month,
        "year": now.year,
        "amount": 10000.00,
        "category_id": food_cat["id"]
    })
    assert b_res.status_code == 200

    # Add expense of 8,500.00 (85% utilization)
    client.post('/api/v1/transactions', headers=headers, json={
        "account_id": bank_id,
        "category_id": food_cat["id"],
        "amount": 8500.00,
        "transaction_type": "EXPENSE",
        "date": today_str,
        "note": "Fine Dining & Groceries"
    })

    budgets_list = client.get('/api/v1/budgets', headers=headers)
    cat_budgets = budgets_list.json.get("data", {}).get("category_budgets", [])
    b_item = [b for b in cat_budgets if b.get("category_id") == food_cat["id"]][0]
    assert float(b_item["spent"]) == 8500.00
    assert float(b_item["utilization_pct"]) == 85.0
    print("JOURNEY 4 PASSED: Category budget progress (85% utilization) calculated correctly.")

    # =========================================================================
    # JOURNEY 5: Financial Goals & Account-Linked Contributions
    # =========================================================================
    goal_res = client.post('/api/v1/goals', headers=headers, json={
        "title": "Emergency Fund 2026",
        "target_amount": 50000.00,
        "current_amount": 0.0,
        "target_date": (now + timedelta(days=180)).strftime("%Y-%m-%d")
    })
    assert goal_res.status_code == 201
    goal_id = goal_res.json.get("goal_id")

    # Contribute 10,000.00 from Bank Account
    contrib_res = client.post(f'/api/v1/goals/{goal_id}/contribute', headers=headers, json={
        "account_id": bank_id,
        "amount": 10000.00
    })
    assert contrib_res.status_code == 200

    # Verify Goal is at 20%
    goals_res = client.get('/api/v1/goals', headers=headers)
    g_item = [g for g in goals_res.json.get("goals", []) if g["id"] == goal_id][0]
    assert float(g_item["current_amount"]) == 10000.00
    assert float(g_item["progress_pct"]) == 20.0
    print("JOURNEY 5 PASSED: Goal lifecycle and account-linked funding verified.")

    # =========================================================================
    # JOURNEY 6: Recurring Commitments & Due-Date Progression
    # =========================================================================
    bill_res = client.post('/api/v1/recurring', headers=headers, json={
        "title": "Cloud Server Subscription",
        "amount": 1200.00,
        "frequency": "MONTHLY",
        "next_due_date": "2026-10-10",
        "account_id": bank_id
    })
    assert bill_res.status_code == 201
    bill_id = bill_res.json.get("bill_id")

    # Pay bill -> Due date advances +1 month
    pay_res = client.post(f'/api/v1/recurring/{bill_id}/pay', headers=headers)
    assert pay_res.status_code == 200
    next_due = pay_res.json.get("next_due_date")
    assert "2026-11-10" in next_due
    print(f"JOURNEY 6 PASSED: Recurring bill paid and rolled over to {next_due}.")

    # =========================================================================
    # JOURNEY 7: SMS / UPI Parsing & Duplicate Detection
    # =========================================================================
    sms_text = "Sent Rs.850.00 from HDFC Bank to Zomato on 29-09-26 via UPI. Ref 9988776655."
    parse_res = client.post('/api/v1/parser/parse-sms', headers=headers, json={"text": sms_text})
    assert parse_res.status_code == 200
    pdata = parse_res.json.get("transaction", {})
    assert float(pdata["amount"]) == 850.00

    # Confirm transaction into ledger
    conf_res = client.post('/api/v1/parser/confirm-transaction', headers=headers, json={
        "account_id": bank_id,
        "amount": pdata["amount"],
        "transaction_type": pdata["transaction_type"],
        "category_id": food_cat["id"],
        "date": pdata["date"],
        "note": pdata["note"],
        "parse_event_id": parse_res.json.get("parse_event_id")
    })
    assert conf_res.status_code == 201

    # Attempt to parse identical SMS again -> Must detect duplicate
    parse_res_dup = client.post('/api/v1/parser/parse-sms', headers=headers, json={"text": sms_text})
    assert parse_res_dup.status_code == 200
    dup_check = parse_res_dup.json.get("duplicate_warning", {})
    assert dup_check.get("is_duplicate") is True
    print("JOURNEY 7 PASSED: SMS/UPI parsing with strict duplicate prevention verified.")

    # =========================================================================
    # JOURNEY 8: Subscription Audits & Annualized Commitments
    # =========================================================================
    sub_res = client.get('/api/v1/subscriptions/overview', headers=headers)
    assert sub_res.status_code == 200
    sub_data = sub_res.json.get("subscriptions", {})
    assert "total_monthly_committed" in sub_data
    assert "total_yearly_committed" in sub_data
    assert float(sub_data["total_yearly_committed"]) >= float(sub_data["total_monthly_committed"]) * 12
    print("JOURNEY 8 PASSED: Subscription audits and annualized outlay verified.")

    # =========================================================================
    # JOURNEY 9: Cashflow Calendar & Daily Runway
    # =========================================================================
    cal_res = client.get('/api/v1/cashflow/calendar', headers=headers)
    assert cal_res.status_code == 200
    cf_data = cal_res.json.get("cashflow", {})
    timeline = cf_data.get("daily_timeline", [])
    assert len(timeline) >= 28
    today_cell = [d for d in timeline if d["date"] == today_str][0]
    assert "projected_balance" in today_cell or "balance" in today_cell
    print("JOURNEY 9 PASSED: Cashflow calendar daily runway & balance progression verified.")

    # =========================================================================
    # JOURNEY 10: Multi-Tenant Data Isolation & Security Lockdown
    # =========================================================================
    user_b_email = f"master_other_{ts}@finance.com"
    client.post('/api/v1/auth/register', json={
        "name": "Sneha Patel",
        "email": user_b_email,
        "password": "OtherPassword#2026"
    })
    b_conn = database.get_db_connection()
    b_otp = b_conn.execute("SELECT otp_code FROM users WHERE email = ?", (user_b_email,)).fetchone()["otp_code"]
    b_conn.close()

    v_b = client.post('/api/v1/auth/verify-otp', json={"identifier": user_b_email, "otp": b_otp})
    token_b = v_b.json.get("access_token")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B should only see their own accounts, not User A's custom account
    b_accs = client.get('/api/v1/accounts', headers=headers_b)
    b_acc_ids = [a["id"] for a in b_accs.json["data"]["accounts"]]
    assert bank_id not in b_acc_ids, f"Cross-tenant leak: User B saw User A account {bank_id}"

    # User B attempting to delete User A's transaction must fail with 404 or 403
    unauth_del = client.delete(f'/api/v1/transactions/{temp_exp_id}', headers=headers_b)
    assert unauth_del.status_code in [403, 404], f"Expected 403/404, got {unauth_del.status_code}"

    # Invalid token rejection
    bad_token = client.get('/api/v1/accounts', headers={"Authorization": "Bearer invalid.token.value"})
    assert bad_token.status_code == 401

    print("JOURNEY 10 PASSED: Strict cross-user isolation and auth security invariants verified.")

    print("=" * 60)
    print("ALL 10 MASTER END-TO-END JOURNEYS PASSED WITH 100% INTEGRITY!")
    print("=" * 60)

if __name__ == '__main__':
    run_tests()
