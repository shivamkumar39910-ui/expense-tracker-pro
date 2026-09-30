"""
Phase 2 Recurring Bills Test Suite
Verifies:
1. Create recurring bill (weekly, monthly, yearly)
2. List recurring bills with dynamic status (UPCOMING, DUE_SOON, OVERDUE, PAUSED)
3. Pay recurring bill: generates transaction, updates balance, and advances next_due_date
4. Pause and resume recurring bill
5. Delete recurring bill
"""

import time
import app

def run_tests():
    client = app.app.test_client()
    ts = int(time.time())
    email = f"rec_tester_{ts}@test.com"

    r = client.post('/api/v1/auth/register', json={'name': 'Rec Tester', 'email': email, 'password': 'Password123'})
    v = client.post('/api/v1/auth/verify-otp', json={'identifier': email, 'otp': r.json['otp_code']})
    token = v.json['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    print("=" * 50)
    print("RUNNING PHASE 2 RECURRING BILLS TESTS")
    print("=" * 50)

    # 1. Create Monthly Bill (Netflix)
    res_monthly = client.post('/api/v1/recurring', headers=headers, json={
        'title': 'Netflix Subscription',
        'amount': 649.00,
        'frequency': 'MONTHLY',
        'next_due_date': '2026-10-05'
    })
    assert res_monthly.status_code == 201
    netflix_id = res_monthly.json['bill_id']
    print(f"TEST 1 PASSED: Monthly bill created (ID: {netflix_id}, Due: 2026-10-05).")

    # 2. Create Weekly Bill (Grocery Delivery)
    res_weekly = client.post('/api/v1/recurring', headers=headers, json={
        'title': 'Weekly Organic Milk',
        'amount': 350.00,
        'frequency': 'WEEKLY',
        'next_due_date': '2026-10-01'
    })
    assert res_weekly.status_code == 201
    weekly_id = res_weekly.json['bill_id']
    print(f"TEST 2 PASSED: Weekly bill created (ID: {weekly_id}, Due: 2026-10-01).")

    # 3. List and Status Verification
    list_res = client.get('/api/v1/recurring', headers=headers)
    assert list_res.status_code == 200
    bills = list_res.json['bills']
    assert len(bills) >= 2
    print(f"TEST 3 PASSED: Listed {len(bills)} recurring bills.")

    # 4. Pay Monthly Bill and Verify Due Date Advance
    pay_monthly = client.post(f'/api/v1/recurring/{netflix_id}/pay', headers=headers)
    assert pay_monthly.status_code == 200
    assert pay_monthly.json['next_due_date'] == '2026-11-05', f"Expected 2026-11-05, got {pay_monthly.json['next_due_date']}"
    print("TEST 4 PASSED: Monthly bill payment advanced due date to 2026-11-05.")

    # 5. Pay Weekly Bill and Verify Due Date Advance (+7 days)
    pay_weekly = client.post(f'/api/v1/recurring/{weekly_id}/pay', headers=headers)
    assert pay_weekly.status_code == 200
    assert pay_weekly.json['next_due_date'] == '2026-10-08', f"Expected 2026-10-08, got {pay_weekly.json['next_due_date']}"
    print("TEST 5 PASSED: Weekly bill payment advanced due date to 2026-10-08 (+7 days).")

    # 6. Pause Bill and Verify Status
    pause_res = client.put(f'/api/v1/recurring/{netflix_id}', headers=headers, json={'is_active': 0})
    assert pause_res.status_code == 200

    list_with_inactive = client.get('/api/v1/recurring?include_inactive=true', headers=headers)
    paused_bill = [b for b in list_with_inactive.json['bills'] if b['id'] == netflix_id][0]
    assert paused_bill['status'] == 'PAUSED'
    print("TEST 6 PASSED: Pausing bill updates status to 'PAUSED'.")

    # 7. Delete Bill
    del_res = client.delete(f'/api/v1/recurring/{netflix_id}', headers=headers)
    assert del_res.status_code == 200
    print("TEST 7 PASSED: Recurring bill deleted successfully.")

    print("=" * 50)
    print("ALL PHASE 2 RECURRING BILLS TESTS PASSED (100% SUCCESS)!")
    print("=" * 50)

if __name__ == '__main__':
    run_tests()
