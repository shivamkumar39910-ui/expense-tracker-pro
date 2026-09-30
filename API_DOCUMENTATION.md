# EXPENSE TRACKER PRO 2.0 - REST API DOCUMENTATION
**Base URL:** `/api/v1`  
**Authentication Scheme:** `Authorization: Bearer <JWT_ACCESS_TOKEN>`  
**Content-Type:** `application/json`  

---

## 1. AUTHENTICATION & SECURITY ENDPOINTS

### 1.1 Register User
- **Method & Route:** `POST /api/v1/auth/register`
- **Request Body:**
  ```json
  {
    "name": "Arjun Sharma",
    "email": "arjun@finance.com",
    "phone": "+919876543210",
    "password": "SecurePassword#2026"
  }
  ```
- **Response (201 Created):**
  ```json
  {
    "success": true,
    "message": "Registration initiated. Verification OTP sent.",
    "user_id": 14,
    "otp_code": "849201"
  }
  ```

### 1.2 Verify Registration OTP
- **Method & Route:** `POST /api/v1/auth/verify-otp`
- **Request Body:**
  ```json
  {
    "identifier": "arjun@finance.com",
    "otp": "849201"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "message": "Account verified successfully!",
    "access_token": "<JWT_TOKEN>",
    "user": {
      "id": 14,
      "name": "Arjun Sharma",
      "email": "arjun@finance.com",
      "currency_symbol": "₹"
    }
  }
  ```

### 1.3 Login (Step 1 - Trigger 2FA)
- **Method & Route:** `POST /api/v1/auth/login`
- **Request Body:**
  ```json
  {
    "identifier": "arjun@finance.com",
    "password": "SecurePassword#2026"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "step": "2FA_REQUIRED",
    "message": "Login 2FA OTP sent to your registered contact.",
    "otp_code": "519302"
  }
  ```

### 1.4 Login (Step 2 - Verify 2FA OTP)
- **Method & Route:** `POST /api/v1/auth/login-verify-otp`
- **Request Body:**
  ```json
  {
    "identifier": "arjun@finance.com",
    "otp": "519302"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "message": "Authentication successful!",
    "access_token": "<JWT_TOKEN>",
    "user": {
      "id": 14,
      "name": "Arjun Sharma",
      "email": "arjun@finance.com",
      "has_pin": true
    }
  }
  ```

### 1.5 Set 4-Digit Security PIN
- **Method & Route:** `POST /api/v1/security/set-pin`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Request Body:**
  ```json
  {
    "pin": "8421"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "message": "App Security PIN set successfully"
  }
  ```

---

## 2. ACCOUNTS & DOUBLE-ENTRY LEDGER

### 2.1 List User Accounts
- **Method & Route:** `GET /api/v1/accounts`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "data": {
      "accounts": [
        {
          "id": 1,
          "name": "Primary Bank",
          "account_type": "BANK",
          "current_balance": 65500.00,
          "color_hex": "#4F46E5",
          "icon": "account_balance"
        }
      ],
      "total_net_worth": 65500.00
    }
  }
  ```

### 2.2 Create Account
- **Method & Route:** `POST /api/v1/accounts`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Request Body:**
  ```json
  {
    "name": "Emergency Savings",
    "account_type": "SAVINGS",
    "initial_balance": 15000.00,
    "color_hex": "#10B981",
    "icon": "savings"
  }
  ```
- **Response (201 Created):**
  ```json
  {
    "success": true,
    "account_id": 3,
    "message": "Account created successfully"
  }
  ```

### 2.3 Record Transaction
- **Method & Route:** `POST /api/v1/transactions`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Request Body:**
  ```json
  {
    "account_id": 1,
    "target_account_id": 2,
    "category_id": 1,
    "amount": 2500.00,
    "transaction_type": "EXPENSE",
    "date": "2026-09-30",
    "note": "Supermarket Groceries"
  }
  ```
- **Response (201 Created):**
  ```json
  {
    "success": true,
    "transaction_id": 42,
    "message": "Transaction recorded"
  }
  ```

### 2.4 Delete Transaction (Atomic Rollback)
- **Method & Route:** `DELETE /api/v1/transactions/<id>`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "message": "Transaction deleted & balance restored"
  }
  ```

---

## 3. BUDGETS & FINANCIAL PLANNING

### 3.1 Get Monthly & Category Budgets
- **Method & Route:** `GET /api/v1/budgets?month=9&year=2026`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "data": {
      "month": 9,
      "year": 2026,
      "overall_budget": 50000.00,
      "total_spent": 38200.00,
      "remaining": 11800.00,
      "days_remaining": 1,
      "safe_daily_cap": 11800.00,
      "utilization_pct": 76.4,
      "category_budgets": [
        {
          "category_id": 1,
          "category_name": "Food & Dining",
          "budget_limit": 10000.00,
          "spent": 8500.00,
          "remaining": 1500.00,
          "utilization_pct": 85.0,
          "is_exceeded": false
        }
      ]
    }
  }
  ```

### 3.2 Set Budget
- **Method & Route:** `POST /api/v1/budgets`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Request Body:**
  ```json
  {
    "month": 9,
    "year": 2026,
    "amount": 10000.00,
    "category_id": 1
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "message": "Budget set successfully"
  }
  ```

---

## 4. FORECAST ENGINE 2.0

### 4.1 Month-End Projection & Risk Assessment
- **Method & Route:** `GET /api/v1/forecast?month=9&year=2026`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "data": {
      "mtd_spent": 38200.00,
      "projected_month_end": 44100.00,
      "daily_velocity": 1273.33,
      "confidence": "HIGH",
      "risk_status": "MODERATE",
      "budget_limit": 50000.00,
      "projected_budget_utilization": 88.2,
      "unpaid_commitments_projected": 3200.00,
      "recommendations": [
        {
          "type": "PACE_ADJUSTMENT",
          "title": "Daily Spend Cap",
          "message": "Limit remaining discretionary spend to ₹1,200/day to stay within budget."
        }
      ]
    }
  }
  ```

---

## 5. RECURRING BILLS & SUBSCRIPTIONS

### 5.1 List Recurring Bills
- **Method & Route:** `GET /api/v1/recurring?include_inactive=false`
- **Headers:** `Authorization: Bearer <TOKEN>`

### 5.2 Create Recurring Bill
- **Method & Route:** `POST /api/v1/recurring`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Request Body:**
  ```json
  {
    "title": "Netflix Premium",
    "amount": 649.00,
    "frequency": "MONTHLY",
    "next_due_date": "2026-10-15",
    "account_id": 1
  }
  ```

### 5.3 Pay Recurring Bill
- **Method & Route:** `POST /api/v1/recurring/<id>/pay`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "message": "Bill marked as paid",
    "next_due_date": "2026-11-15",
    "transaction_id": 55
  }
  ```

---

## 6. AUTOMATION & INTELLIGENCE

### 6.1 Parse SMS / UPI Text
- **Method & Route:** `POST /api/v1/parser/parse-sms`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Request Body:**
  ```json
  {
    "text": "Sent Rs.850.00 from HDFC Bank to Zomato on 29-09-26 via UPI. Ref 9988776655."
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "parse_event_id": 12,
    "transaction": {
      "amount": 850.00,
      "transaction_type": "EXPENSE",
      "merchant": "ZOMATO",
      "merchant_clean": "Zomato",
      "date": "2026-09-29",
      "ref_number": "9988776655",
      "bank_name": "HDFC",
      "confidence": "HIGH",
      "category_id": 1,
      "category_name": "Food & Dining",
      "requires_user_confirmation": true
    },
    "duplicate_warning": {
      "is_duplicate": false,
      "matching_transaction": null,
      "reason": null
    }
  }
  ```

### 6.2 Confirm Parsed Transaction
- **Method & Route:** `POST /api/v1/parser/confirm-transaction`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Request Body:**
  ```json
  {
    "account_id": 1,
    "category_id": 1,
    "amount": 850.00,
    "transaction_type": "EXPENSE",
    "date": "2026-09-29",
    "note": "Zomato (HDFC)",
    "parse_event_id": 12
  }
  ```
- **Response (201 Created):**
  ```json
  {
    "success": true,
    "transaction_id": 58,
    "message": "Transaction verified and saved to ledger."
  }
  ```

### 6.3 Subscriptions Overview & Audit
- **Method & Route:** `GET /api/v1/subscriptions/overview`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "subscriptions": {
      "active_subscriptions_count": 3,
      "total_monthly_committed": 2499.00,
      "total_yearly_committed": 29988.00,
      "duplicate_warnings": []
    }
  }
  ```

### 6.4 Cashflow Calendar & Runway
- **Method & Route:** `GET /api/v1/cashflow/calendar?year=2026&month=9`
- **Headers:** `Authorization: Bearer <TOKEN>`
- **Response (200 OK):**
  ```json
  {
    "success": true,
    "cashflow": {
      "user_id": 14,
      "liquidity_status": "HEALTHY",
      "lowest_projected_balance": 48200.00,
      "daily_timeline": [
        {
          "date": "2026-09-30",
          "day": 30,
          "is_today": true,
          "opening_balance": 65500.00,
          "actual_income": 0.0,
          "actual_expense": 850.00,
          "committed_bills": 0.0,
          "projected_balance": 64650.00
        }
      ]
    }
  }
  ```
