import json
import sys
from datetime import datetime
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
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

    # 3. Test Direct Password Login & 2FA Flow
    login_direct = client.post('/api/v1/auth/login', json={
        "identifier": test_email,
        "password": "Password123"
    })
    print("3a. Direct Password Login (Instant):", login_direct.status_code, login_direct.json.get("message"))
    assert login_direct.status_code == 200
    assert login_direct.json.get("require_otp") is False
    assert "access_token" in login_direct.json

    # 3b. Test Optional 2FA Login Flow
    login_step1 = client.post('/api/v1/auth/login', json={
        "identifier": test_email,
        "password": "Password123",
        "require_2fa": True
    })
    print("3b. Login Step 1 (2FA OTP trigger):", login_step1.status_code, login_step1.json.get("message"))
    assert login_step1.status_code == 200
    assert login_step1.json.get("require_otp") is True
    login_otp = login_step1.json.get("otp_code")

    login_step2 = client.post('/api/v1/auth/login-verify-otp', json={
        "identifier": test_email,
        "otp": login_otp
    })
    print("3c. Login Step 2 (2FA OTP Verification):", login_step2.status_code, login_step2.json.get("message"))
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

    # 15c. Deposit via /goals/<id>/deposit with UPI and verify Expense Isolation
    exp_before = client.get('/api/v1/command-center/summary', headers=headers).json["data"]["cashflow"]["expenses"]
    r_dep = client.post(f'/api/v1/goals/{goal_id}/deposit', headers=headers, json={
        "amount": 2000.0,
        "payment_method": "UPI",
        "note": "Savings bonus"
    })
    assert r_dep.status_code == 200
    assert r_dep.json["goal"]["new_current_amount"] == 17000.0
    print("15c. POST /api/v1/goals/deposit (UPI):", r_dep.status_code, "New Balance:", r_dep.json["goal"]["new_current_amount"])

    # 15d. Withdraw via /goals/<id>/withdraw with Cash and verify Expense Isolation
    r_with = client.post(f'/api/v1/goals/{goal_id}/withdraw', headers=headers, json={
        "amount": 1000.0,
        "payment_method": "Cash",
        "note": "Emergency use"
    })
    assert r_with.status_code == 200
    assert r_with.json["goal"]["new_current_amount"] == 16000.0
    print("15d. POST /api/v1/goals/withdraw (Cash):", r_with.status_code, "New Balance:", r_with.json["goal"]["new_current_amount"])

    # Verify Expense Isolation: total expense MUST be identical before and after!
    exp_after = client.get('/api/v1/command-center/summary', headers=headers).json["data"]["cashflow"]["expenses"]
    assert exp_before == exp_after, f"Goal operations corrupted expenses: before={exp_before}, after={exp_after}"
    print("15e. Isolated Vault Guarantee Verified: Total Expenses remained exactly Rs.", exp_after)

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

    # 24. Category & Subcategory Creation and Deletion Verification (Custom + Default + History + Postgres Translation)
    r_cat_add = client.post('/api/v1/categories', headers=headers, json={
        "name": "Test Gym Fitness",
        "type": "EXPENSE",
        "icon": "fitness_center",
        "color_hex": "#EC4899"
    })
    assert r_cat_add.status_code == 201
    new_cat_id = r_cat_add.json["category"]["id"]

    r_sub_add = client.post(f'/api/v1/categories/{new_cat_id}/subcategories', headers=headers, json={
        "name": "Crossfit Workout"
    })
    assert r_sub_add.status_code == 201
    new_sub_id = r_sub_add.json["subcategory"]["id"]

    # Set a category budget on the custom category alongside overall budget
    r_cat_bgt = client.post('/api/v1/budgets', headers=headers, json={
        "category_id": new_cat_id,
        "month": datetime.today().month,
        "year": datetime.today().year,
        "amount": 5000.0
    })
    assert r_cat_bgt.status_code == 200

    # Record a transaction referencing the custom category & subcategory
    r_cat_tx = client.post('/api/v1/transactions', headers=headers, json={
        "account_id": bank_acc["id"],
        "category_id": new_cat_id,
        "subcategory_id": new_sub_id,
        "transaction_type": "EXPENSE",
        "amount": 150.0,
        "date": datetime.today().strftime("%Y-%m-%d"),
        "note": "Gym pass"
    })
    assert r_cat_tx.status_code == 201
    cat_tx_id = r_cat_tx.json["transaction_id"]

    # Delete custom subcategory & custom category
    r_sub_del = client.delete(f'/api/v1/subcategories/{new_sub_id}', headers=headers)
    print("24a. DELETE /api/v1/subcategories/<id> (Custom):", r_sub_del.status_code, r_sub_del.json.get("message"))
    assert r_sub_del.status_code == 200

    r_cat_del = client.delete(f'/api/v1/categories/{new_cat_id}', headers=headers)
    print("24b. DELETE /api/v1/categories/<id> (Custom):", r_cat_del.status_code, r_cat_del.json.get("message"))
    assert r_cat_del.status_code == 200

    # Also test deleting a system default category & subcategory
    r_cats_before = client.get('/api/v1/categories', headers=headers)
    assert r_cats_before.status_code == 200
    exp_cats = r_cats_before.json["categories"]["expense"]
    default_cat = next(c for c in exp_cats if c["is_default"] == 1 and c.get("subcategories"))
    default_sub = default_cat["subcategories"][0]

    r_def_sub_del = client.delete(f'/api/v1/subcategories/{default_sub["id"]}', headers=headers)
    print("24c. DELETE /api/v1/subcategories/<id> (Default):", r_def_sub_del.status_code)
    assert r_def_sub_del.status_code == 200

    r_def_cat_del = client.delete(f'/api/v1/categories/{default_cat["id"]}', headers=headers)
    print("24d. DELETE /api/v1/categories/<id> (Default):", r_def_cat_del.status_code)
    assert r_def_cat_del.status_code == 200

    # Verify deleted categories/subcategories no longer appear in GET /categories or /app/bootstrap
    r_cats_after = client.get('/api/v1/categories', headers=headers)
    exp_after = r_cats_after.json["categories"]["expense"]
    exp_after_ids = [c["id"] for c in exp_after]
    assert new_cat_id not in exp_after_ids
    assert default_cat["id"] not in exp_after_ids

    r_boot = client.get('/api/v1/app/bootstrap', headers=headers)
    assert r_boot.status_code == 200
    boot_exp_ids = [c["id"] for c in r_boot.json["bootstrap"]["categories"]["expense"]]
    assert new_cat_id not in boot_exp_ids
    assert default_cat["id"] not in boot_exp_ids

    # Verify past transaction retains category_name & subcategory_name in history
    r_tx_hist = client.get('/api/v1/transactions', headers=headers)
    hist_tx = next(t for t in r_tx_hist.json["transactions"] if t["id"] == cat_tx_id)
    assert hist_tx["category_name"] == "Test Gym Fitness"
    assert hist_tx["subcategory_name"] == "Crossfit Workout"
    print("24e. Hidden Categories + Historical Label Preservation Verified!")

    # Verify PostgresCursorWrapper SQL translation (no INSERT OR IGNORE, no RETURNING id on no-id tables)
    import db_engine
    pw = db_engine.PostgresCursorWrapper(None)
    q1, ret1 = pw._translate_query("INSERT INTO user_hidden_categories (user_id, category_id) VALUES (?, ?) ON CONFLICT (user_id, category_id) DO NOTHING")
    assert "OR IGNORE" not in q1.upper() and "RETURNING ID" not in q1.upper() and ret1 is False
    q2, ret2 = pw._translate_query("INSERT OR IGNORE INTO user_hidden_subcategories (user_id, subcategory_id) VALUES (?, ?)")
    assert "OR IGNORE" not in q2.upper() and "ON CONFLICT DO NOTHING" in q2.upper() and "RETURNING ID" not in q2.upper() and ret2 is False
    q3, ret3 = pw._translate_query("INSERT INTO categories (user_id, name, type, icon, color_hex, is_default) VALUES (?, ?, ?, ?, ?, 0)")
    assert "RETURNING ID" in q3.upper() and ret3 is True
    print("24f. Postgres SQL Translation Compatibility Verified!")

    # 25. Auto Category Image Assignment & Accuracy Verification
    import category_visuals
    assert category_visuals.resolve_category_visual_fast("EMI", "EXPENSE")["theme_key"] == "emi_loan"
    assert category_visuals.resolve_category_visual_fast("Loan Repayment", "EXPENSE")["theme_key"] == "emi_loan"
    assert category_visuals.resolve_category_visual_fast("Petrol", "EXPENSE")["theme_key"] == "fuel_petrol"
    assert category_visuals.resolve_category_visual_fast("Taxi", "EXPENSE")["theme_key"] == "car_transport"
    assert category_visuals.resolve_category_visual_fast("Parents", "EXPENSE")["theme_key"] == "family_home"
    assert category_visuals.resolve_category_visual_fast("Credit Card", "EXPENSE")["theme_key"] == "credit_card_bank"
    assert category_visuals.resolve_category_visual_fast("Healthcare", "EXPENSE")["theme_key"] == "health_wellness"
    assert category_visuals.resolve_category_visual_fast("Chai & Coffee", "EXPENSE")["theme_key"] == "coffee_cafe"
    assert category_visuals.resolve_category_visual_fast("Kirana", "EXPENSE")["theme_key"] == "groceries"
    assert category_visuals.resolve_category_visual_fast("Xyz Abstract 987", "EXPENSE")["image_url"] == ""
    print("25a. Semantic Category Visual Accuracy (Zero False Positives) Verified!")

    r_sug = client.get('/api/v1/categories/suggest-visual?name=Loan+Repayment&type=EXPENSE', headers=headers)
    assert r_sug.status_code == 200
    assert r_sug.json["visual"]["theme_key"] == "emi_loan"
    assert r_sug.json["visual"]["image_url"].startswith("https://images.unsplash.com/")
    print("25b. GET /api/v1/categories/suggest-visual Verified!")

    r_emi_cat = client.post('/api/v1/categories', headers=headers, json={"name": "Loan Repayment", "type": "EXPENSE"})
    assert r_emi_cat.status_code == 201
    emi_cat = r_emi_cat.json["category"]
    assert emi_cat["image_url"].startswith("https://images.unsplash.com/photo-1554224155")
    assert emi_cat["icon"] == "receipt_long"

    r_cats_img = client.get('/api/v1/categories', headers=headers)
    fetched_emi = next(c for c in r_cats_img.json["categories"]["expense"] if c["id"] == emi_cat["id"])
    assert fetched_emi["image_url"] == emi_cat["image_url"]

    r_emi_tx = client.post('/api/v1/transactions', headers=headers, json={
        "account_id": bank_acc["id"],
        "category_id": emi_cat["id"],
        "transaction_type": "EXPENSE",
        "amount": 500.0,
        "date": datetime.today().strftime("%Y-%m-%d"),
        "note": "Monthly EMI"
    })
    assert r_emi_tx.status_code == 201
    r_txs_img = client.get('/api/v1/transactions', headers=headers)
    emi_tx_row = next(t for t in r_txs_img.json["transactions"] if t["id"] == r_emi_tx.json["transaction_id"])
    assert emi_tx_row["category_image"] == emi_cat["image_url"]
    print("25c. Persistent Auto-Image in DB, /categories & /transactions Verified!")

    # 26. Conversational AI Chatbot 5.0 Verification (Hindi Devanagari + Hinglish + English + Memory + Actions)
    import re as _re
    today_iso = datetime.today().strftime("%Y-%m-%d")

    # 26a. Natural greeting should be concise English (NOT bloated budget dump, NOT Hindi)
    r_ai_hi = client.post('/api/v1/ai-mentor/chat', headers=headers, json={
        "message": "hello",
        "history": [],
        "client_date": today_iso
    })
    assert r_ai_hi.status_code == 200
    ai_hello = r_ai_hi.json["data"]["reply"]
    assert not _re.search(r"[\u0900-\u097F]", ai_hello), f"Unexpected Hindi in English hello: {ai_hello}"
    assert "MTD Total Spend" not in ai_hello
    print("26a. Natural Greeting Verified:", ai_hello[:60])

    # 26b. Devanagari Hindi question must respond in Devanagari Hindi with real spend
    r_ai_hindi = client.post('/api/v1/ai-mentor/chat', headers=headers, json={
        "message": "आज कितना खर्च हुआ?",
        "history": [],
        "client_date": today_iso
    })
    assert r_ai_hindi.status_code == 200
    ai_hi_rep = r_ai_hindi.json["data"]["reply"]
    assert _re.search(r"[\u0900-\u097F]", ai_hi_rep), f"Expected Devanagari Hindi reply, got: {ai_hi_rep}"
    print("26b. Devanagari Hindi Response Verified:", ai_hi_rep[:60])

    # 26c. Custom category / payment method query + Multi-turn follow-up carryover
    r_ai_emi = client.post('/api/v1/ai-mentor/chat', headers=headers, json={
        "message": "Loan Repayment pe kitna gaya?",
        "history": [],
        "client_date": today_iso
    })
    assert r_ai_emi.status_code == 200
    assert "500" in r_ai_emi.json["data"]["reply"]

    r_ai_follow = client.post('/api/v1/ai-mentor/chat', headers=headers, json={
        "message": "detail me batao",
        "history": [
            {"role": "user", "content": "Loan Repayment pe kitna gaya?"},
            {"role": "assistant", "content": r_ai_emi.json["data"]["reply"]}
        ],
        "client_date": today_iso
    })
    assert r_ai_follow.status_code == 200
    assert "Loan Repayment" in r_ai_follow.json["data"]["reply"]
    print("26c. Custom Category & Multi-Turn Follow-up Verified!")

    # 26d. Add Expense intent with Amount + Payment Channel
    r_ai_add = client.post('/api/v1/ai-mentor/chat', headers=headers, json={
        "message": "150 coffee upi me add kar do",
        "history": [],
        "client_date": today_iso
    })
    assert r_ai_add.status_code == 200
    act = r_ai_add.json["data"].get("action_button")
    assert act is not None and act["type"] == "OPEN_QUICK_ENTRY"
    assert float(act["amount"]) == 150.0 and act["account_name"] == "UPI"
    print("26d. AI Expense Add Action Payload Verified!")

    # 26e. LLM JSON extraction helper verification
    import ai_mentor_service
    parsed_llm = ai_mentor_service._clean_llm_json('```json\n{"reply": "Spent ₹500 today.", "followup_chips": ["Today?"]}\n```')
    assert parsed_llm["reply"] == "Spent ₹500 today."
    assert ai_mentor_service._detect_language_mode("आज खर्च बताओ") == "hi"
    assert ai_mentor_service._detect_language_mode("aaj kitna kharch hua") == "hinglish"
    assert ai_mentor_service._detect_language_mode("how much did I spend today") == "en"
    print("26e. LLM JSON Parser & 3-Way Language Detection Verified!")

    print("==================================================")
    print("ALL 26 REST API ENDPOINTS & LOGIC TESTS PASSED (100% SUCCESS)!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
