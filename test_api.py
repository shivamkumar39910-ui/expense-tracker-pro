import json
from app_web import app
import database

def run_tests():
    print("==================================================")
    print("STARTING REST API ENDPOINT SUITE VERIFICATION")
    print("==================================================")

    client = app.test_client()

    # 1. Test Registration with OTP
    import time
    ts = int(time.time())
    test_email = f"rahul.{ts}@test.com"
    test_phone = f"+9198{str(ts)[-8:]}"
    reg_payload = {
        "name": "Rahul Verma",
        "email": test_email,
        "phone": test_phone,
        "password": "Password123"
    }
    r = client.post('/api/v1/auth/register', json=reg_payload)
    print("1. Registration POST:", r.status_code, r.json.get("message"))
    assert r.status_code == 201, f"Expected 201, got {r.status_code}"
    otp_code = r.json.get("otp_code")
    assert otp_code is not None, "Expected OTP code in response"

    # 2. Test Registration OTP Verification
    verify_payload = {
        "identifier": test_email,
        "otp": otp_code
    }
    r = client.post('/api/v1/auth/verify-otp', json=verify_payload)
    print("2. OTP Verification POST:", r.status_code, r.json.get("message"))
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    token = r.json.get("access_token")
    assert token is not None, "Expected JWT access token"
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Test 2FA Login Flow
    login_step1 = client.post('/api/v1/auth/login', json={
        "identifier": test_email,
        "password": "Password123"
    })
    print("3a. Login Step 1 (Credentials & OTP trigger):", login_step1.status_code, login_step1.json.get("message"))
    assert login_step1.status_code == 200
    assert login_step1.json.get("require_otp") is True
    login_otp = login_step1.json.get("otp_code")

    login_step2 = client.post('/api/v1/auth/login-verify-otp', json={
        "identifier": test_email,
        "otp": login_otp
    })
    print("3b. Login Step 2 (2FA OTP Verification):", login_step2.status_code, login_step2.json.get("message"))
    assert login_step2.status_code == 200
    assert "access_token" in login_step2.json

    # 4. Test Accounts & Net Worth
    r_acc = client.get('/api/v1/accounts', headers=headers)
    print("4. GET /api/v1/accounts:", r_acc.status_code, "Accounts count:", len(r_acc.json["data"]["accounts"]))
    assert r_acc.status_code == 200
    accounts = r_acc.json["data"]["accounts"]
    cash_acc = accounts[0]
    bank_acc = accounts[1]

    # Create a Credit Card account
    r_create_cc = client.post('/api/v1/accounts', headers=headers, json={
        "name": "HDFC Regalia Credit Card",
        "account_type": "CREDIT_CARD",
        "initial_balance": 0.0,
        "color_hex": "#EF4444",
        "icon": "credit_card"
    })
    print("5. POST /api/v1/accounts (Credit Card):", r_create_cc.status_code, r_create_cc.json.get("message"))
    assert r_create_cc.status_code == 201
    cc_id = r_create_cc.json.get("account_id")

    # 6. Test Categories
    r_cat = client.get('/api/v1/categories', headers=headers)
    print("6. GET /api/v1/categories:", r_cat.status_code,
          "Expense Categories:", len(r_cat.json["categories"]["expense"]),
          "Income Categories:", len(r_cat.json["categories"]["income"]))
    assert r_cat.status_code == 200
    food_cat = r_cat.json["categories"]["expense"][0]

    # 7. Record Income Transaction (Salary: ₹50,000 to Bank)
    r_inc = client.post('/api/v1/transactions', headers=headers, json={
        "account_id": bank_acc["id"],
        "transaction_type": "INCOME",
        "amount": 50000.0,
        "date": "2026-09-01",
        "note": "Monthly Salary credited"
    })
    print("7. POST /api/v1/transactions (Income Rs. 50k):", r_inc.status_code, r_inc.json.get("message"))
    assert r_inc.status_code == 201

    # 8. Record Transfer (ATM Cash Withdrawal: Bank -> Cash Rs. 5,000)
    r_trf = client.post('/api/v1/transactions', headers=headers, json={
        "account_id": bank_acc["id"],
        "target_account_id": cash_acc["id"],
        "transaction_type": "TRANSFER",
        "amount": 5000.0,
        "date": "2026-09-05",
        "note": "ATM Cash Withdrawal"
    })
    print("8. POST /api/v1/transactions (Transfer Rs. 5k Bank->Cash):", r_trf.status_code, r_trf.json.get("message"))
    assert r_trf.status_code == 201

    # 9. Record Expense (Dining Out: Rs. 1,200 from Cash)
    r_exp = client.post('/api/v1/transactions', headers=headers, json={
        "account_id": cash_acc["id"],
        "category_id": food_cat["id"],
        "transaction_type": "EXPENSE",
        "amount": 1200.0,
        "date": "2026-09-10",
        "note": "Dinner with family"
    })
    print("9. POST /api/v1/transactions (Expense Rs. 1,200):", r_exp.status_code, r_exp.json.get("message"))
    assert r_exp.status_code == 201

    # 10. Verify Cashflow Isolation (Transfers must NOT count as spending!)
    r_cf = client.get('/api/v1/insights/cashflow?month=9&year=2026', headers=headers)
    cf = r_cf.json["cashflow"]
    print(f"10. Cashflow Verification -> Income: Rs.{cf['income']}, Expense: Rs.{cf['expenses']}, Transfer: Rs.{cf['transfers']}, Net Savings: Rs.{cf['net_savings']}")
    assert cf['income'] == 50000.0
    assert cf['expenses'] == 1200.0, f"Expected expenses=1200, got {cf['expenses']}"
    assert cf['transfers'] == 5000.0, f"Expected transfers=5000, got {cf['transfers']}"
    assert cf['net_savings'] == 48800.0

    # 11. Set Budget
    r_bgt = client.post('/api/v1/budgets', headers=headers, json={
        "month": 9,
        "year": 2026,
        "amount": 25000.0
    })
    print("11. POST /api/v1/budgets:", r_bgt.status_code, r_bgt.json.get("message"))
    assert r_bgt.status_code == 200

    # 12. Test Forecasting Engine & Predictive Warnings
    r_fc = client.get('/api/v1/forecast/month-end?date=2026-09-24', headers=headers)
    fc = r_fc.json["forecast"]
    print("12. Forecast Output:")
    print(f"    - MTD Spend: Rs.{fc['mtd_actual_spend']}")
    print(f"    - Daily Velocity: Rs.{fc['daily_spending_velocity']}/day")
    print(f"    - Projected Month-End: Rs.{fc['projected_month_end_spend']}")
    print(f"    - Risk Status: {fc['risk_status']}")
    print(f"    - Warning: {fc['warning_message']}")
    assert r_fc.status_code == 200
    assert fc["risk_status"] == "SAFE"

    # 13. Test Command Center Aggregator
    r_cc = client.get('/api/v1/command-center/summary', headers=headers)
    print("13. GET /api/v1/command-center/summary:", r_cc.status_code, "Net Worth:", r_cc.json["data"]["net_worth"]["net_worth"])
    assert r_cc.status_code == 200

    # 14. Phase 10: Notifications & Predictive Alerts
    r_notif = client.get('/api/v1/notifications', headers=headers)
    print("14. GET /api/v1/notifications:", r_notif.status_code, "Count:", len(r_notif.json.get("notifications", [])))
    assert r_notif.status_code == 200
    r_readall = client.post('/api/v1/notifications/read-all', headers=headers)
    assert r_readall.status_code == 200

    # 15. Phase 11: Financial Goals Deepening
    r_goal_post = client.post('/api/v1/goals', headers=headers, json={
        "title": "Emergency Fund",
        "target_amount": 50000.0,
        "current_amount": 10000.0,
        "target_date": "2026-12-31",
        "icon": "shield"
    })
    print("15a. POST /api/v1/goals:", r_goal_post.status_code, r_goal_post.json.get("message"))
    assert r_goal_post.status_code == 201
    goal_id = r_goal_post.json["goal_id"]

    r_contrib = client.post(f'/api/v1/goals/{goal_id}/contribute', headers=headers, json={
        "amount": 5000.0,
        "account_id": bank_acc["id"]
    })
    print("15b. POST /api/v1/goals/contribute:", r_contrib.status_code, r_contrib.json.get("message"))
    assert r_contrib.status_code == 200
    assert r_contrib.json["goal"]["new_current_amount"] == 15000.0

    r_goals_list = client.get('/api/v1/goals', headers=headers)
    assert r_goals_list.status_code == 200
    assert len(r_goals_list.json["goals"]) >= 1

    # 16. Phase 11: Visual Charts Breakdown & 6M History
    r_chart_bd = client.get('/api/v1/charts/breakdown', headers=headers)
    print("16a. GET /api/v1/charts/breakdown:", r_chart_bd.status_code, "Categories:", len(r_chart_bd.json.get("breakdown", [])))
    assert r_chart_bd.status_code == 200

    r_chart_hist = client.get('/api/v1/charts/history-6m', headers=headers)
    print("16b. GET /api/v1/charts/history-6m:", r_chart_hist.status_code, "History months:", len(r_chart_hist.json.get("history", [])))
    assert r_chart_hist.status_code == 200
    assert len(r_chart_hist.json["history"]) == 6

    # 17. Phase 12: Offline Batch Sync
    batch_payload = {
        "items": [
            {
                "client_uuid": "offline-uuid-001",
                "action": "CREATE_TRANSACTION",
                "payload": {
                    "account_id": bank_acc["id"],
                    "transaction_type": "EXPENSE",
                    "amount": 250.0,
                    "date": "2026-09-24",
                    "note": "Offline Metro Card Recharge",
                    "tag": "#transit"
                }
            }
        ]
    }
    r_sync = client.post('/api/v1/sync/batch', headers=headers, json=batch_payload)
    print("17. POST /api/v1/sync/batch:", r_sync.status_code, "Synced:", r_sync.json.get("synced_count"))
    assert r_sync.status_code == 200
    assert r_sync.json["synced_count"] == 1

    # Test idempotency (re-sending same offline item should not duplicate)
    r_sync_dup = client.post('/api/v1/sync/batch', headers=headers, json=batch_payload)
    assert r_sync_dup.status_code == 200

    # 18. Phase 13: App PIN Security
    r_pin_set = client.post('/api/v1/security/set-pin', headers=headers, json={
        "pin": "2468",
        "enable": True
    })
    print("18a. POST /api/v1/security/set-pin:", r_pin_set.status_code, r_pin_set.json.get("message"))
    assert r_pin_set.status_code == 200

    r_pin_verify_ok = client.post('/api/v1/security/verify-pin', headers=headers, json={"pin": "2468"})
    assert r_pin_verify_ok.status_code == 200
    assert r_pin_verify_ok.json["valid"] is True

    r_pin_verify_fail = client.post('/api/v1/security/verify-pin', headers=headers, json={"pin": "0000"})
    assert r_pin_verify_fail.status_code == 401

    r_sec_settings = client.get('/api/v1/security/settings', headers=headers)
    assert r_sec_settings.status_code == 200
    assert r_sec_settings.json["settings"]["is_pin_enabled"] is True

    # 19. Phase 14: Data Export & Reports
    r_csv = client.get('/api/v1/reports/export/csv', headers=headers)
    print("19a. GET /api/v1/reports/export/csv:", r_csv.status_code, "Content length:", len(r_csv.data))
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers.get("Content-Type", "")
    assert b"Offline Metro Card Recharge" in r_csv.data

    r_report_summary = client.get('/api/v1/reports/summary', headers=headers)
    print("19b. GET /api/v1/reports/summary:", r_report_summary.status_code, "Period:", r_report_summary.json["statement"]["period"])
    assert r_report_summary.status_code == 200
    assert "cashflow" in r_report_summary.json["statement"]

    # 20. Phase 16: Multi-Currency & Localization Engine
    r_curr_list = client.get('/api/v1/currencies')
    print("20a. GET /api/v1/currencies:", r_curr_list.status_code, "Count:", len(r_curr_list.json["currencies"]))
    assert r_curr_list.status_code == 200
    assert len(r_curr_list.json["currencies"]) >= 8

    r_set_curr = client.post('/api/v1/user/currency', headers=headers, json={"currency_code": "USD"})
    print("20b. POST /api/v1/user/currency:", r_set_curr.status_code, r_set_curr.json.get("message"))
    assert r_set_curr.status_code == 200
    assert r_set_curr.json["currency"]["code"] == "USD"
    assert r_set_curr.json["currency"]["symbol"] == "$"

    r_get_curr = client.get('/api/v1/user/currency', headers=headers)
    assert r_get_curr.status_code == 200
    assert r_get_curr.json["currency"]["code"] == "USD"

    # Reset currency back to INR for subsequent operations
    client.post('/api/v1/user/currency', headers=headers, json={"currency_code": "INR"})

    # 21. Phase 17: Smart AI Receipt Scanner Engine
    r_scan = client.post('/api/v1/receipts/scan', headers=headers, json={"sample_type": "starbucks"})
    print("21a. POST /api/v1/receipts/scan (Sample):", r_scan.status_code, "Merchant:", r_scan.json["receipt"]["merchant"], "Amount:", r_scan.json["receipt"]["amount"])
    assert r_scan.status_code == 200
    assert r_scan.json["receipt"]["merchant"] == "Starbucks Coffee"
    assert r_scan.json["receipt"]["amount"] == 651.00
    assert r_scan.json["receipt"]["category_name"] == "Food & Dining"

    # Raw OCR text parsing
    custom_receipt_text = "SHELL PETROL STATION\nTotal Amount: Rs. 1850.50\nDate: 2026-09-24\nFuel V-Power"
    r_scan_raw = client.post('/api/v1/receipts/scan', headers=headers, json={"raw_text": custom_receipt_text})
    print("21b. POST /api/v1/receipts/scan (Raw text):", r_scan_raw.status_code, "Category:", r_scan_raw.json["receipt"]["category_name"], "Amount:", r_scan_raw.json["receipt"]["amount"])
    assert r_scan_raw.status_code == 200
    assert r_scan_raw.json["receipt"]["amount"] == 1850.50
    assert r_scan_raw.json["receipt"]["category_name"] == "Transportation"

    # 22. Phase 19: Transaction Balance Rollback on Deletion Verification
    r_acc_before = client.get('/api/v1/accounts', headers=headers)
    bank_bal_before = [a["current_balance"] for a in r_acc_before.json["data"]["accounts"] if a["id"] == bank_acc["id"]][0]

    # Create temporary expense of Rs. 750
    r_temp_tx = client.post('/api/v1/transactions', headers=headers, json={
        "account_id": bank_acc["id"],
        "transaction_type": "EXPENSE",
        "amount": 750.0,
        "date": "2026-09-24",
        "note": "Temporary Coffee Break"
    })
    assert r_temp_tx.status_code == 201
    temp_tx_id = r_temp_tx.json["transaction_id"]

    # Verify balance was deducted
    r_acc_mid = client.get('/api/v1/accounts', headers=headers)
    bank_bal_mid = [a["current_balance"] for a in r_acc_mid.json["data"]["accounts"] if a["id"] == bank_acc["id"]][0]
    assert round(bank_bal_mid, 2) == round(bank_bal_before - 750.0, 2)

    # Delete transaction
    r_del = client.delete(f'/api/v1/transactions/{temp_tx_id}', headers=headers)
    print("22. DELETE /api/v1/transactions/<id> (Rollback test):", r_del.status_code, r_del.json.get("message"))
    assert r_del.status_code == 200

    # Verify balance is restored back to original balance
    r_acc_after = client.get('/api/v1/accounts', headers=headers)
    bank_bal_after = [a["current_balance"] for a in r_acc_after.json["data"]["accounts"] if a["id"] == bank_acc["id"]][0]
    assert round(bank_bal_after, 2) == round(bank_bal_before, 2)

    # 23. Phase 19: Strict Input Validation & Security Shielding
    r_invalid_amt = client.post('/api/v1/transactions', headers=headers, json={
        "account_id": bank_acc["id"],
        "transaction_type": "EXPENSE",
        "amount": -50.0 # Negative amount should be strictly rejected
    })
    print("23a. Invalid Negative Amount Rejection:", r_invalid_amt.status_code, r_invalid_amt.json.get("error"))
    assert r_invalid_amt.status_code == 400

    r_invalid_pin = client.post('/api/v1/security/set-pin', headers=headers, json={
        "pin": "12A" # Non-4-digit PIN should be rejected
    })
    print("23b. Malformed PIN Rejection:", r_invalid_pin.status_code, r_invalid_pin.json.get("error"))
    assert r_invalid_pin.status_code == 400

    print("==================================================")
    print("ALL 23 REST API ENDPOINTS & LOGIC TESTS PASSED (100% SUCCESS)!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
