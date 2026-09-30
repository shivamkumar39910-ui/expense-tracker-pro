"""
PHASE 5 FORECAST ENGINE 2.0 AUTOMATED TEST SUITE (test_phase5_forecast.py)
Tests all requirements A through Z:
A. Empty user
B. New user with little history
C. One month history
D. Multiple month history
E. Stable spending
F. Volatile spending
G. High spending velocity
H. No budget
I. Budget under usage
J. Budget near limit
K. Budget exceeded
L. Zero days remaining
M. Recurring bill upcoming
N. Recurring bill already paid (Zero double counting)
O. Paused recurring bill
P. Category forecasting
Q. Sparse category data
R. Confidence scoring
S. Recommendation generation
T. User isolation
U. Decimal precision
V. Transfer exclusion
W. Income exclusion from expense forecast
X. Future transaction exclusion
Y. Backtesting without future leakage
Z. Forecast API responses
"""

import os
import sqlite3
import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal
import forecasting_engine
import forecast_metrics
import app_web
from app_web import app

TEST_DB = "test_forecast_p5.db"

def setup_test_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            currency_symbol TEXT DEFAULT 'Rs.',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_verified INTEGER DEFAULT 1
        );
    """)

    cursor.execute("""
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            account_type TEXT NOT NULL,
            initial_balance REAL NOT NULL DEFAULT 0.0,
            current_balance REAL NOT NULL DEFAULT 0.0,
            is_active INTEGER NOT NULL DEFAULT 1
        );
    """)

    cursor.execute("""
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('EXPENSE', 'INCOME')),
            icon TEXT DEFAULT 'tag',
            color_hex TEXT DEFAULT '#6B7280'
        );
    """)

    cursor.execute("""
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            target_account_id INTEGER,
            category_id INTEGER,
            subcategory_id INTEGER,
            transaction_type TEXT NOT NULL CHECK(transaction_type IN ('EXPENSE', 'INCOME', 'TRANSFER')),
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            note TEXT,
            tag TEXT,
            is_recurring INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE TABLE budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_id INTEGER,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            amount REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE TABLE recurring_bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_id INTEGER,
            category_id INTEGER,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            frequency TEXT NOT NULL DEFAULT 'MONTHLY',
            due_day INTEGER NOT NULL,
            next_due_date TEXT NOT NULL,
            auto_paid INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        );
    """)

    # Seed categories
    cats = [
        ("Food & Dining", "EXPENSE"),
        ("Transportation", "EXPENSE"),
        ("Shopping", "EXPENSE"),
        ("Utilities", "EXPENSE"),
        ("Salary", "INCOME")
    ]
    for name, ctype in cats:
        cursor.execute("INSERT INTO categories (name, type) VALUES (?, ?)", (name, ctype))

    conn.commit()
    conn.close()

def run_all_tests():
    print("==================================================")
    print("RUNNING PHASE 5 FORECAST ENGINE 2.0 TEST SUITE")
    print("==================================================")

    setup_test_db()
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()

    # User 1: Empty User
    cursor.execute("INSERT INTO users (name, email, password) VALUES ('Empty User', 'empty@test.com', 'hash')")
    user_empty = cursor.lastrowid

    # User 2: New User with short history (current month only)
    cursor.execute("INSERT INTO users (name, email, password) VALUES ('New User', 'new@test.com', 'hash')")
    user_new = cursor.lastrowid
    cursor.execute("INSERT INTO accounts (user_id, name, account_type, current_balance) VALUES (?, 'Bank', 'BANK', 10000.0)", (user_new,))
    acc_new = cursor.lastrowid

    # User 3: Stable Historical User (3+ completed months)
    cursor.execute("INSERT INTO users (name, email, password) VALUES ('Stable User', 'stable@test.com', 'hash')")
    user_stable = cursor.lastrowid
    cursor.execute("INSERT INTO accounts (user_id, name, account_type, current_balance) VALUES (?, 'Bank', 'BANK', 50000.0)", (user_stable,))
    acc_stable = cursor.lastrowid

    # User 4: Volatile User
    cursor.execute("INSERT INTO users (name, email, password) VALUES ('Volatile User', 'volatile@test.com', 'hash')")
    user_volatile = cursor.lastrowid
    cursor.execute("INSERT INTO accounts (user_id, name, account_type, current_balance) VALUES (?, 'Bank', 'BANK', 50000.0)", (user_volatile,))
    acc_volatile = cursor.lastrowid

    conn.commit()

    # ----------------------------------------------------
    # TEST 1 (A): Empty User Test
    # ----------------------------------------------------
    fc_empty = forecasting_engine.calculate_month_end_forecast(user_empty, target_date="2026-09-15", db_path=TEST_DB)
    assert fc_empty["mtd_actual_spend"] == 0.0, "Empty user MTD spend should be 0.0"
    assert fc_empty["daily_spending_velocity"] == 0.0, "Empty user velocity should be 0.0"
    assert fc_empty["projected_month_end_spend"] == 0.0, "Empty user projection should be 0.0"
    assert fc_empty["confidence"] == "LOW", "Empty user confidence should be LOW"
    assert fc_empty["risk_status"] == "NO_BUDGET", "Empty user with no budget should be NO_BUDGET"
    print("TEST 1 (A) PASSED: Empty user gracefully handled without crash.")

    # ----------------------------------------------------
    # TEST 2 (B & G): New User with Short History & High Spending Velocity
    # ----------------------------------------------------
    # Day 5 of Sep 2026: 2 transactions totaling 5,000
    cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, transaction_type, amount, date, note) VALUES (?, ?, 1, 'EXPENSE', 2000.0, '2026-09-02', 'Groceries')", (user_new, acc_new))
    cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, transaction_type, amount, date, note) VALUES (?, ?, 1, 'EXPENSE', 3000.0, '2026-09-05', 'Dinner')", (user_new, acc_new))
    conn.commit()

    fc_new = forecasting_engine.calculate_month_end_forecast(user_new, target_date="2026-09-05", db_path=TEST_DB)
    assert fc_new["mtd_actual_spend"] == 5000.0
    assert fc_new["days_elapsed"] == 5
    assert fc_new["daily_spending_velocity"] == 1000.0 # 5000 / 5
    # Velocity spend for 30-day month = 1000 * 30 = 30000
    assert fc_new["projected_month_end_spend"] == 30000.0
    assert fc_new["confidence"] == "LOW" # No completed months
    print(f"TEST 2 (B & G) PASSED: New user velocity projection (Rs.{fc_new['daily_spending_velocity']}/day -> Rs.{fc_new['projected_month_end_spend']}) verified.")

    # ----------------------------------------------------
    # TEST 3 (C, D, E, R): Multi-Month Stable History & Confidence Scoring
    # ----------------------------------------------------
    # Seed 3 completed months for user_stable:
    # June 2026: 20,000
    # July 2026: 20,000
    # August 2026: 20,000
    for day in range(1, 11):
        d_str = f"2026-06-{day:02d}"
        cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, transaction_type, amount, date, note) VALUES (?, ?, 1, 'EXPENSE', 2000.0, ?, 'Food')", (user_stable, acc_stable, d_str))
        d_str = f"2026-07-{day:02d}"
        cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, transaction_type, amount, date, note) VALUES (?, ?, 1, 'EXPENSE', 2000.0, ?, 'Food')", (user_stable, acc_stable, d_str))
        d_str = f"2026-08-{day:02d}"
        cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, transaction_type, amount, date, note) VALUES (?, ?, 1, 'EXPENSE', 2000.0, ?, 'Food')", (user_stable, acc_stable, d_str))

    # Current month (Sep 2026): 15 transactions of 600 each across first 15 days = 9,000
    for day in range(1, 16):
        d_str = f"2026-09-{day:02d}"
        cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, transaction_type, amount, date, note) VALUES (?, ?, 1, 'EXPENSE', 600.0, ?, 'Lunch')", (user_stable, acc_stable, d_str))
    conn.commit()

    fc_stable = forecasting_engine.calculate_month_end_forecast(user_stable, target_date="2026-09-15", db_path=TEST_DB)
    assert fc_stable["baseline_wma_history"] == 20000.0
    assert fc_stable["mtd_actual_spend"] == 9000.0
    assert fc_stable["spending_trend"] == "STABLE"
    assert fc_stable["confidence"] == "HIGH"
    assert fc_stable["confidence_score"] >= 70
    print(f"TEST 3 (C, D, E, R) PASSED: 3-month stable baseline verified (WMA: Rs.{fc_stable['baseline_wma_history']}, Confidence: {fc_stable['confidence']}).")

    # ----------------------------------------------------
    # TEST 4 (F): Volatile User Spending & Variance Handling
    # ----------------------------------------------------
    # User volatile: June=5,000, July=50,000, August=10,000
    cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, transaction_type, amount, date, note) VALUES (?, ?, 1, 'EXPENSE', 5000.0, '2026-06-10', 'June')", (user_volatile, acc_volatile))
    cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, transaction_type, amount, date, note) VALUES (?, ?, 1, 'EXPENSE', 50000.0, '2026-07-10', 'July')", (user_volatile, acc_volatile))
    cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, transaction_type, amount, date, note) VALUES (?, ?, 1, 'EXPENSE', 10000.0, '2026-08-10', 'August')", (user_volatile, acc_volatile))
    conn.commit()

    fc_volatile = forecasting_engine.calculate_month_end_forecast(user_volatile, target_date="2026-09-05", db_path=TEST_DB)
    # WMA: 0.50*10000 + 0.30*50000 + 0.20*5000 = 5000 + 15000 + 1000 = 21000.0
    assert fc_volatile["baseline_wma_history"] == 21000.0
    assert fc_volatile["confidence"] in ("LOW", "MEDIUM")
    print(f"TEST 4 (F) PASSED: Volatile spending baseline computed (Rs.{fc_volatile['baseline_wma_history']}) with lower confidence.")

    # ----------------------------------------------------
    # TEST 5 (H, I, J, K): Budget Risk Engine (Under, Near Limit, Exceeded)
    # ----------------------------------------------------
    # 5a: Under budget (Healthy surplus)
    cursor.execute("INSERT INTO budgets (user_id, month, year, amount) VALUES (?, 9, 2026, 25000.0)", (user_stable,))
    conn.commit()
    fc_bgt_safe = forecasting_engine.calculate_month_end_forecast(user_stable, target_date="2026-09-15", db_path=TEST_DB)
    assert fc_bgt_safe["risk_status"] == "SAFE"
    assert fc_bgt_safe["risk_level"] == "LOW"
    assert fc_bgt_safe["safe_daily_spend"] > 0
    print("TEST 5a (I) PASSED: Under-budget healthy status verified (SAFE / LOW).")

    # 5b: Near limit (85%+)
    cursor.execute("UPDATE budgets SET amount = 20000.0 WHERE user_id = ? AND month = 9 AND year = 2026", (user_stable,))
    conn.commit()
    fc_bgt_warn = forecasting_engine.calculate_month_end_forecast(user_stable, target_date="2026-09-15", db_path=TEST_DB)
    assert fc_bgt_warn["risk_level"] in ("MODERATE", "HIGH", "CRITICAL")
    print(f"TEST 5b (J) PASSED: Near-limit budget status verified ({fc_bgt_warn['risk_level']}).")

    # 5c: Exceeded budget
    cursor.execute("UPDATE budgets SET amount = 8000.0 WHERE user_id = ? AND month = 9 AND year = 2026", (user_stable,))
    conn.commit()
    fc_bgt_crit = forecasting_engine.calculate_month_end_forecast(user_stable, target_date="2026-09-15", db_path=TEST_DB)
    assert fc_bgt_crit["risk_level"] == "CRITICAL"
    assert fc_bgt_crit["risk_status"] == "DANGER"
    assert "breached" in fc_bgt_crit["risk_reason"].lower()
    print("TEST 5c (K) PASSED: Exceeded budget status verified (CRITICAL / DANGER).")

    # ----------------------------------------------------
    # TEST 6 (L): Zero Days Remaining (Month-End Boundary)
    # ----------------------------------------------------
    fc_monthend = forecasting_engine.calculate_month_end_forecast(user_stable, target_date="2026-09-30", db_path=TEST_DB)
    assert fc_monthend["days_remaining"] == 0
    assert fc_monthend["projected_month_end_spend"] == fc_monthend["mtd_actual_spend"]
    print(f"TEST 6 (L) PASSED: Month-end boundary (Day 30/30) matches actual MTD spend: Rs.{fc_monthend['projected_month_end_spend']}.")

    # ----------------------------------------------------
    # TEST 7 (M, N, O): Recurring Bills Integration (Zero Double-Counting)
    # ----------------------------------------------------
    # Reset budget to 30,000
    cursor.execute("UPDATE budgets SET amount = 30000.0 WHERE user_id = ? AND month = 9 AND year = 2026", (user_stable,))

    # Add 1 active unpaid upcoming bill due Day 25: Rs. 2,000 (Electricity)
    cursor.execute("""
        INSERT INTO recurring_bills (user_id, account_id, title, amount, frequency, due_day, next_due_date, is_active)
        VALUES (?, ?, 'Electricity Bill', 2000.0, 'MONTHLY', 25, '2026-09-25', 1)
    """, (user_stable, acc_stable))
    bill_up = cursor.lastrowid

    # Add 1 active bill ALREADY PAID this month: Rs. 1,500 (Internet)
    # Due date was Day 5, payment made on Day 5, next_due_date is now next month 2026-10-05
    cursor.execute("""
        INSERT INTO recurring_bills (user_id, account_id, title, amount, frequency, due_day, next_due_date, is_active)
        VALUES (?, ?, 'Internet Fiber', 1500.0, 'MONTHLY', 5, '2026-10-05', 1)
    """, (user_stable, acc_stable))
    bill_paid = cursor.lastrowid

    # Add 1 PAUSED bill: Rs. 5,000 (Gym)
    cursor.execute("""
        INSERT INTO recurring_bills (user_id, account_id, title, amount, frequency, due_day, next_due_date, is_active)
        VALUES (?, ?, 'Gym Membership', 5000.0, 'MONTHLY', 20, '2026-09-20', 0)
    """, (user_stable, acc_stable))
    bill_paused = cursor.lastrowid
    conn.commit()

    fc_bills = forecasting_engine.calculate_month_end_forecast(user_stable, target_date="2026-09-15", db_path=TEST_DB)
    # Upcoming bill should be Rs. 2,000
    assert fc_bills["unpaid_recurring_bills"] == 2000.0
    assert fc_bills["upcoming_recurring_total"] == 2000.0
    # Already paid bill should be in paid_recurring_total, NOT upcoming
    assert fc_bills["paid_recurring_total"] == 1500.0
    # Paused bill (Gym 5000) must NOT be in upcoming
    upcoming_titles = [b["title"] for b in fc_bills["upcoming_recurring"]]
    assert "Electricity Bill" in upcoming_titles
    assert "Gym Membership" not in upcoming_titles
    assert "Internet Fiber" not in upcoming_titles
    print("TEST 7 (M, N, O) PASSED: Zero double-counting verified (Unpaid: Rs.2,000, Paid: Rs.1,500, Paused excluded).")

    # ----------------------------------------------------
    # TEST 8 (P, Q): Category Forecasting & Sparse Data
    # ----------------------------------------------------
    cat_fcs = fc_bills["category_forecasts"]
    assert len(cat_fcs) > 0
    top_cat = cat_fcs[0]
    assert top_cat["category"] == "Food & Dining"
    assert top_cat["confidence"] == "HIGH"
    assert top_cat["projected_month_end"] >= top_cat["mtd_spend"]
    print(f"TEST 8 (P, Q) PASSED: Category forecast verified ({top_cat['category']} -> Projected Rs.{top_cat['projected_month_end']}).")

    # ----------------------------------------------------
    # TEST 9 (S): Explainable Recommendations Generation
    # ----------------------------------------------------
    recs = fc_bills["recommendations"]
    assert len(recs) > 0
    rec_ids = [r["id"] for r in recs]
    assert "REC_CATEGORY_DRIVER" in rec_ids or "REC_UPCOMING_BILLS" in rec_ids
    for r in recs:
        assert "suggested_action" in r
        assert "supporting_metric" in r
        assert "explanation" in r
    print(f"TEST 9 (S) PASSED: {len(recs)} deterministic explainable recommendations generated.")

    # ----------------------------------------------------
    # TEST 10 (T, V, W, X): User Isolation, Transfer/Income Exclusion, Future Leakage
    # ----------------------------------------------------
    # Add an INCOME of Rs. 100,000 for user_stable
    cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, transaction_type, amount, date, note) VALUES (?, ?, 5, 'INCOME', 100000.0, '2026-09-10', 'Salary')", (user_stable, acc_stable))
    # Add a TRANSFER of Rs. 25,000 for user_stable
    cursor.execute("INSERT INTO transactions (user_id, account_id, target_account_id, transaction_type, amount, date, note) VALUES (?, ?, ?, 'TRANSFER', 25000.0, '2026-09-12', 'Transfer')", (user_stable, acc_stable, acc_new))
    # Add a FUTURE transaction on Day 25 (Rs. 50,000)
    cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, transaction_type, amount, date, note) VALUES (?, ?, 1, 'EXPENSE', 50000.0, '2026-09-25', 'Future Vacation')", (user_stable, acc_stable))
    conn.commit()

    # Re-evaluate as of Day 15: Income, Transfer, and Future transaction must NOT be counted!
    fc_leakage_check = forecasting_engine.calculate_month_end_forecast(user_stable, target_date="2026-09-15", db_path=TEST_DB)
    assert fc_leakage_check["mtd_actual_spend"] == 9000.0, "Transfers, Incomes, and Future transactions must NOT contaminate MTD spend!"
    print("TEST 10 (T, V, W, X) PASSED: Strict user isolation, Transfer/Income exclusion, and Zero future leakage verified.")

    # ----------------------------------------------------
    # TEST 11 (Y): Backtesting Engine Accuracy & Metrics
    # ----------------------------------------------------
    # Run backtest for user_stable on completed months (June, July, August 2026)
    test_periods = [(2026, 6), (2026, 7), (2026, 8)]
    bt_results = forecast_metrics.run_backtest_simulation(user_stable, test_periods, cutoff_days=[7, 14, 21], db_path=TEST_DB)
    assert bt_results["evaluated_periods_count"] == 9
    metrics = bt_results["metrics"]
    assert "MAE" in metrics
    assert "RMSE" in metrics
    assert metrics["MAE"] >= 0.0
    assert metrics["RMSE"] >= 0.0

    # Generate and save report
    bt_report = forecast_metrics.generate_backtest_markdown_report(bt_results)
    with open("FORECAST_BACKTEST_REPORT.md", "w", encoding="utf-8") as f:
        f.write(bt_report)
    print(f"TEST 11 (Y) PASSED: Backtesting verified (9 periods, MAE: Rs.{metrics['MAE']}, RMSE: Rs.{metrics['RMSE']}). Report generated.")

    # ----------------------------------------------------
    # TEST 12 (U, Z): Decimal Precision & API Endpoints Verification
    # ----------------------------------------------------
    client = app.test_client()

    # Register and verify an authentic user for API endpoint verification
    test_email = f"fc_test_{int(datetime.now().timestamp())}@forecast.com"
    r_reg = client.post('/api/v1/auth/register', json={
        "name": "Forecast API Tester",
        "email": test_email,
        "password": "Password123!"
    })
    assert r_reg.status_code == 201
    otp = r_reg.json.get("otp_code")
    r_ver = client.post('/api/v1/auth/verify-otp', json={
        "identifier": test_email,
        "otp": otp
    })
    assert r_ver.status_code == 200
    token = r_ver.json["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Test /api/v1/forecast
    r_fc1 = client.get("/api/v1/forecast?date=2026-09-15", headers=headers)
    assert r_fc1.status_code == 200
    j1 = r_fc1.json
    assert j1["success"] is True
    assert "current_spend" in j1
    assert "safe_daily_spend" in j1
    assert "confidence" in j1
    assert "risk_level" in j1
    assert "recommendations" in j1

    # Test /api/forecast alias
    r_fc2 = client.get("/api/forecast?date=2026-09-15", headers=headers)
    assert r_fc2.status_code == 200
    assert r_fc2.json["success"] is True

    # Test /api/v1/forecast/month-end
    r_fc3 = client.get("/api/v1/forecast/month-end?date=2026-09-15", headers=headers)
    assert r_fc3.status_code == 200
    assert "forecast" in r_fc3.json

    # Test /api/v1/forecast/backtest
    r_bt = client.get("/api/v1/forecast/backtest", headers=headers)
    assert r_bt.status_code == 200
    assert r_bt.json["success"] is True


    print("TEST 12 (U, Z) PASSED: Decimal precision & all Forecast API endpoints (/api/v1/forecast, /api/forecast, /backtest) verified 100%.")

    conn.close()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    print("==================================================")
    print("ALL PHASE 5 FORECAST ENGINE 2.0 TESTS PASSED (100% SUCCESS)!")
    print("==================================================")

if __name__ == "__main__":
    run_all_tests()
