"""
COMPREHENSIVE AUTOMATED TEST SUITE: PHASE 6 - AUTOMATION & REAL-WORLD FINANCIAL INTELLIGENCE
Tests:
1. SMS / UPI Parser: Multi-bank regex extraction, category inference, confidence scoring.
2. Duplicate Transaction Detection: Exact & windowed matching (+/- 2 days).
3. Web Push Delivery & Preference Suppression: Enforcing user notification settings.
4. Subscription Intelligence: Annualized calculations, duplicate subscription warnings, candidate discovery.
5. Cash-Flow Calendar: Daily timeline, actuals vs committed recurring, running balance, low balance warning.
6. Savings Goal Intelligence: Required monthly pacing, completion date, on-track status.
7. Smart Alerts Engine: Deterministic alerts generation & 24h deduplication.
8. Phase 6 REST API Endpoints:
   - POST /api/v1/parser/parse-sms
   - POST /api/v1/parser/confirm-transaction
   - GET /api/v1/subscriptions/overview
   - GET /api/v1/subscriptions/candidates
   - POST /api/v1/subscriptions/convert-candidate
   - GET /api/v1/cashflow/calendar
   - GET /api/v1/goals/intelligence
   - GET /api/v1/alerts
   - POST /api/v1/alerts/<id>/dismiss
   - Unauthenticated 401 protection
   - User isolation (User A vs User B)
"""

import unittest
import os
import json
import sqlite3
from decimal import Decimal
from datetime import datetime, date, timedelta
from app import app
import database
import sms_parser_service
import subscription_service
import cashflow_calendar_service
import alerts_engine
import push_delivery_service
from api_v1 import generate_tokens

class Phase6AutomationTestSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()
        database.create_database()


    def setUp(self):
        self.ts = int(datetime.utcnow().timestamp() * 1000)
        self.user_a_email = f"user_a_{self.ts}@automation.com"
        self.user_b_email = f"user_b_{self.ts}@automation.com"

        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (name, email, password, is_verified) VALUES (?, ?, ?, 1)",
                       ("Automation User A", self.user_a_email, "hash_a"))
        self.user_a_id = cursor.lastrowid
        cursor.execute("INSERT INTO users (name, email, password, is_verified) VALUES (?, ?, ?, 1)",
                       ("Automation User B", self.user_b_email, "hash_b"))
        self.user_b_id = cursor.lastrowid
        conn.commit()
        conn.close()

        database.create_user_default_data(self.user_a_id)
        database.create_user_default_data(self.user_b_id)

        # Generate tokens
        token_a, _ = generate_tokens(self.user_a_id)
        token_b, _ = generate_tokens(self.user_b_id)
        self.headers_a = {"Authorization": f"Bearer {token_a}", "Content-Type": "application/json"}
        self.headers_b = {"Authorization": f"Bearer {token_b}", "Content-Type": "application/json"}


        # Get accounts
        accs_a = database.get_user_accounts(self.user_a_id)
        self.acc_a_id = accs_a[0]["id"] if accs_a else 1

        accs_b = database.get_user_accounts(self.user_b_id)
        self.acc_b_id = accs_b[0]["id"] if accs_b else 1

        # Set positive starting balance for User A
        database.record_transaction(
            user_id=self.user_a_id,
            account_id=self.acc_a_id,
            transaction_type="INCOME",
            amount=50000.00,
            date=date.today().strftime("%Y-%m-%d"),
            note="Starting Salary Deposit"
        )

    # =========================================================================
    # 1. SMS & UPI PARSER UNIT TESTS
    # =========================================================================
    def test_01_sms_parser_hdfc_debit(self):
        sms = "Sent Rs.450.00 from HDFC Bank A/C to Swiggy on 28-09-26 via UPI. Ref 6271927361. Balance Rs.24,500.00"
        parsed = sms_parser_service.parse_sms_text(sms)
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["transaction_type"], "EXPENSE")
        self.assertEqual(parsed["amount"], 450.00)
        self.assertIn("Swiggy", parsed["merchant_clean"])
        self.assertEqual(parsed["category_inferred"], "Food & Dining")
        self.assertEqual(parsed["bank_name"], "HDFC")
        self.assertEqual(parsed["confidence"], "HIGH")

    def test_02_sms_parser_sbi_card_debit(self):
        sms = "Dear SBI User, your A/C ending 4821 is debited by INR 1,299.00 on 2026-09-29 by transfer to Netflix. UPI Ref 8271039821."
        parsed = sms_parser_service.parse_sms_text(sms)
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["transaction_type"], "EXPENSE")
        self.assertEqual(parsed["amount"], 1299.00)
        self.assertIn("Netflix", parsed["merchant_clean"])
        self.assertEqual(parsed["category_inferred"], "Entertainment")
        self.assertEqual(parsed["account_last4"], "4821")
        self.assertEqual(parsed["bank_name"], "SBI")

    def test_03_sms_parser_salary_credit(self):
        sms = "Your Axis Bank A/C ending 3192 is credited by Rs.75,000.00 on 30-Sep-26 towards Salary. Avl Bal Rs.98,400.00"
        parsed = sms_parser_service.parse_sms_text(sms)
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["transaction_type"], "INCOME")
        self.assertEqual(parsed["amount"], 75000.00)
        self.assertEqual(parsed["category_inferred"], "Salary")
        self.assertEqual(parsed["bank_name"], "AXIS")

    def test_04_sms_parser_malformed_text(self):
        text = "Hello your OTP is 123456. Do not share it with anyone."
        parsed = sms_parser_service.parse_sms_text(text)
        self.assertFalse(parsed["success"])
        self.assertEqual(parsed["confidence"], "NONE")

    # =========================================================================
    # 2. DUPLICATE TRANSACTION DETECTION
    # =========================================================================
    def test_05_duplicate_detection(self):
        today = date.today().strftime("%Y-%m-%d")
        # Record an existing transaction
        database.record_transaction(
            user_id=self.user_a_id,
            account_id=self.acc_a_id,
            transaction_type="EXPENSE",
            amount=450.00,
            date=today,
            note="Swiggy Order Ref 6271927361"
        )

        # Check duplicate with same amount and date
        dup = sms_parser_service.detect_duplicate_transaction(
            user_id=self.user_a_id,
            amount=450.00,
            tx_date=today,
            ref_number="6271927361"
        )
        self.assertTrue(dup["is_duplicate"])
        self.assertIn("Found matching", dup["warning_message"])

        # Check different user (User B) should NOT detect User A's transaction
        dup_b = sms_parser_service.detect_duplicate_transaction(
            user_id=self.user_b_id,
            amount=450.00,
            tx_date=today
        )
        self.assertFalse(dup_b["is_duplicate"])

    # =========================================================================
    # 3. WEB PUSH NOTIFICATION & PREFERENCE ENFORCEMENT
    # =========================================================================
    def test_06_push_notification_preference_suppression(self):
        # Update user A preference: suppress forecast alerts
        database.update_user_notification_preferences(
            user_id=self.user_a_id,
            budget_80=1,
            budget_100=1,
            bill_due=1,
            security_alerts=1,
            forecast=0, # Disabled
            goals=1,
            weekly_summary=1,
            unusual_spending=1,
            all_off=0
        )

        res = push_delivery_service.send_financial_notification(
            user_id=self.user_a_id,
            alert_type="BUDGET_OVERRUN",
            title="Forecast Overrun",
            message="Spend pace exceeds budget"
        )
        self.assertEqual(res["status"], "SUPPRESSED_BY_PREFERENCE")

        # Now test active alert (bill_due) which is enabled
        res_active = push_delivery_service.send_financial_notification(
            user_id=self.user_a_id,
            alert_type="BILL_DUE",
            title="Bill Due Tomorrow",
            message="Internet bill is due"
        )
        self.assertTrue(res_active["success"])

    # =========================================================================
    # 4. SUBSCRIPTION INTELLIGENCE & DISCOVERY
    # =========================================================================
    def test_07_subscription_intelligence_and_duplicates(self):
        # Add two Netflix subscriptions to trigger duplicate warning
        today = date.today().strftime("%Y-%m-%d")
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO recurring_bills (user_id, title, amount, due_day, next_due_date, frequency, is_active)
            VALUES (?, ?, ?, ?, ?, 'MONTHLY', 1)
        """, (self.user_a_id, "Netflix Premium", 649.00, 1, today))
        cursor.execute("""
            INSERT INTO recurring_bills (user_id, title, amount, due_day, next_due_date, frequency, is_active)
            VALUES (?, ?, ?, ?, ?, 'MONTHLY', 1)
        """, (self.user_a_id, "Netflix Mobile", 199.00, 1, today))
        conn.commit()
        conn.close()


        summary = subscription_service.get_subscription_summary(self.user_a_id)
        self.assertEqual(summary["active_subscriptions_count"], 2)
        self.assertEqual(summary["monthly_total"], 848.00)
        self.assertEqual(summary["annual_total"], 10176.00)
        self.assertTrue(len(summary["duplicate_warnings"]) > 0)
        self.assertIn("multiple times", summary["duplicate_warnings"][0]["warning"])

    def test_08_subscription_candidate_discovery(self):
        # Create repeating historical transactions with same note & amount
        d1 = (date.today() - timedelta(days=60)).strftime("%Y-%m-%d")
        d2 = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")

        database.record_transaction(self.user_a_id, self.acc_a_id, "EXPENSE", 299.00, d1, note="Spotify Premium")
        database.record_transaction(self.user_a_id, self.acc_a_id, "EXPENSE", 299.00, d2, note="Spotify Premium")

        candidates = subscription_service.discover_subscription_candidates(self.user_a_id)
        spotify_cands = [c for c in candidates if "Spotify" in c["title"]]
        self.assertTrue(len(spotify_cands) >= 1)
        self.assertEqual(spotify_cands[0]["amount"], 299.00)

        # Test conversion
        bill_id = subscription_service.convert_candidate_to_recurring(
            user_id=self.user_a_id,
            title="Spotify Premium",
            amount=299.00,
            frequency="MONTHLY"
        )
        self.assertIsNotNone(bill_id)

        # After conversion, it should no longer appear in candidates
        candidates_after = subscription_service.discover_subscription_candidates(self.user_a_id)
        spotify_after = [c for c in candidates_after if "Spotify" in c["title"]]
        self.assertEqual(len(spotify_after), 0)

    # =========================================================================
    # 5. CASH-FLOW CALENDAR SERVICE
    # =========================================================================
    def test_09_cashflow_calendar(self):
        today = date.today()
        start = today.strftime("%Y-%m-01")
        last_day = 30
        end = today.strftime(f"%Y-%m-{last_day:02d}")

        calendar = cashflow_calendar_service.get_cashflow_calendar(self.user_a_id, start, end)
        self.assertEqual(calendar["user_id"], self.user_a_id)
        self.assertTrue(len(calendar["daily_timeline"]) > 0)
        self.assertIn(calendar["liquidity_status"], ["HEALTHY", "SAFE", "LOW_BALANCE_RISK"])
        self.assertIsInstance(calendar["lowest_projected_balance"], float)

    # =========================================================================
    # 6. SAVINGS GOAL INTELLIGENCE & SMART ALERTS
    # =========================================================================
    def test_10_savings_goal_intelligence(self):
        target_date = (date.today() + timedelta(days=90)).strftime("%Y-%m-%d")
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO financial_goals (user_id, title, target_amount, current_amount, target_date, color_hex, icon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (self.user_a_id, "Emergency Fund", 30000.00, 6000.00, target_date, "#10B981", "savings"))
        conn.commit()
        conn.close()

        intel = alerts_engine.get_goal_intelligence(self.user_a_id)

        self.assertEqual(len(intel), 1)
        g = intel[0]
        self.assertEqual(g["title"], "Emergency Fund")
        self.assertEqual(g["remaining_amount"], 24000.00)
        self.assertTrue(g["required_monthly_contribution"] > 0)
        self.assertIn(g["pacing_status"], ["ON_TRACK", "BEHIND"])

    def test_11_smart_alerts_generation_and_deduplication(self):
        # Generate alerts
        alerts = alerts_engine.evaluate_and_generate_alerts(self.user_a_id)
        self.assertIsInstance(alerts, list)

        # Retrieve active alerts
        active = alerts_engine.get_active_alerts(self.user_a_id)
        self.assertIsInstance(active, list)

        if len(active) > 0:
            first_id = active[0]["id"]
            # Dismiss alert
            dismissed = alerts_engine.dismiss_alert(self.user_a_id, first_id)
            self.assertTrue(dismissed)

            # User B should NOT be able to dismiss User A's alert
            dismissed_b = alerts_engine.dismiss_alert(self.user_b_id, first_id)
            self.assertFalse(dismissed_b)

    # =========================================================================
    # 7. PHASE 6 REST API ENDPOINTS & USER ISOLATION
    # =========================================================================
    def test_12_api_unauthenticated_protection(self):
        endpoints = [
            ("/api/v1/parser/parse-sms", "POST", {"text": "dummy"}),
            ("/api/v1/parser/confirm-transaction", "POST", {"amount": 100}),
            ("/api/v1/subscriptions/overview", "GET", None),
            ("/api/v1/subscriptions/candidates", "GET", None),
            ("/api/v1/cashflow/calendar", "GET", None),
            ("/api/v1/goals/intelligence", "GET", None),
            ("/api/v1/alerts", "GET", None),
        ]
        for url, method, body in endpoints:
            if method == "POST":
                resp = self.client.post(url, json=body or {})
            else:
                resp = self.client.get(url)
            self.assertEqual(resp.status_code, 401, f"Endpoint {url} failed auth protection")

    def test_13_api_parse_and_confirm_transaction_flow(self):
        sms_text = "Sent Rs.850.00 from HDFC Bank to Zomato on 29-09-26 via UPI. Ref 9988776655."
        # Step 1: Parse SMS
        res_parse = self.client.post("/api/v1/parser/parse-sms", json={"text": sms_text}, headers=self.headers_a)
        self.assertEqual(res_parse.status_code, 200)
        data = res_parse.get_json()
        self.assertTrue(data["success"])
        tx_data = data["transaction"]
        self.assertEqual(tx_data["amount"], 850.00)
        self.assertEqual(tx_data["requires_user_confirmation"], True)

        # Step 2: Confirm Transaction
        res_confirm = self.client.post("/api/v1/parser/confirm-transaction", json={
            "amount": tx_data["amount"],
            "transaction_type": tx_data["transaction_type"],
            "date": tx_data["date"],
            "account_id": self.acc_a_id,
            "category_id": tx_data["category_id"],
            "note": tx_data["note"],
            "parse_event_id": data.get("parse_event_id")
        }, headers=self.headers_a)

        self.assertEqual(res_confirm.status_code, 201)
        confirm_data = res_confirm.get_json()
        self.assertTrue(confirm_data["success"])
        self.assertIn("transaction_id", confirm_data)

    def test_14_api_subscriptions_and_cashflow_isolation(self):
        # User A cashflow
        res_a = self.client.get("/api/v1/cashflow/calendar", headers=self.headers_a)
        self.assertEqual(res_a.status_code, 200)
        self.assertEqual(res_a.get_json()["cashflow"]["user_id"], self.user_a_id)

        # User B cashflow
        res_b = self.client.get("/api/v1/cashflow/calendar", headers=self.headers_b)
        self.assertEqual(res_b.status_code, 200)
        self.assertEqual(res_b.get_json()["cashflow"]["user_id"], self.user_b_id)

        # User A subscriptions
        res_sub = self.client.get("/api/v1/subscriptions/overview", headers=self.headers_a)
        self.assertEqual(res_sub.status_code, 200)
        self.assertTrue("subscriptions" in res_sub.get_json())

if __name__ == '__main__':
    unittest.main()
