# EXPENSE TRACKER PRO 2.0
## PHASE 6 ARCHITECTURE: AUTOMATION & REAL-WORLD FINANCIAL INTELLIGENCE

### 1. Architectural Overview

Phase 6 elevates Expense Tracker Pro 2.0 from a passive tracking tool into an active, intelligent financial automation partner. The design strictly adheres to three architectural pillars:
1. **Zero Silent Writes**: Financial transactions are never created behind the user's back. Every automated extraction (SMS, OCR) presents a structured review card requiring explicit user confirmation before ledger persistence.
2. **Deterministic, Explainable Intelligence**: All alerts, forecasts, and recurring candidates are derived from mathematical formulas, statistical moving averages, and pattern detection—never fabricated AI hallucinations.
3. **Strict Data Isolation & Precision**: Multi-tenant database queries enforce `user_id` filtering with `ON DELETE CASCADE` foreign keys. Currency computations utilize `Decimal("0.01")` rounding to eliminate floating-point drift.

```
+---------------------------------------------------------------------------------------------------+
|                                      INGESTION & SENSORS LAYER                                    |
|   +-----------------------+     +-----------------------+     +-------------------------------+   |
|   | Smart SMS/UPI Parser  |     | Receipt OCR Engine    |     | Scheduled Cron & Evaluators   |   |
|   | (sms_parser_service)  |     | (ocr_service)         |     | (alerts_engine / push_delivery|   |
|   +-----------+-----------+     +-----------+-----------+     +---------------+---------------+   |
+---------------|-----------------------------|---------------------------------|-------------------+
                |                             |                                 |
                v                             v                                 v
+---------------------------------------------------------------------------------------------------+
|                                  USER REVIEW & CONFIRMATION GUARD                                 |
|   - Amount & Type Validation (Debit vs Credit)                                                    |
|   - Duplicate Transaction Risk Detection (+/- 2 day window, reference matching)                   |
|   - Category / Account Inference                                                                  |
|   - Interactive Review Sheet (templates/mobile_app.html)                                          |
+---------------------------------------------+-----------------------------------------------------+
                                              | (User Explicit Approval)
                                              v
+---------------------------------------------------------------------------------------------------+
|                                      TRANSACTION LEDGER CORE                                      |
|   - Atomic Multi-Account Balance Sync                                                             |
|   - Immutable Audit Logging in transaction_parse_events                                           |
+---------------------------------------------+-----------------------------------------------------+
                                              |
       +--------------------------------------+--------------------------------------+
       |                                      |                                      |
       v                                      v                                      v
+-----------------------+      +-------------------------------+      +-----------------------------+
| CASH-FLOW CALENDAR    |      | SUBSCRIPTION INTELLIGENCE     |      | SMART ALERTS & MENTOR       |
| (cashflow_calendar)   |      | (subscription_service)        |      | (alerts_engine / ai_mentor) |
| - Actual vs Committed |      | - 90-Day Repeating Patterns   |      | - 24h Deduplication Cache   |
| - Daily Runway Engine |      | - Annualized Cost Analysis    |      | - Preference Suppression    |
| - Minimum Bal Warning |      | - Overlapping Service Alerts  |      | - 4-Pillar Explainability   |
+-----------------------+      +-------------------------------+      +-----------------------------+
```

---

### 2. Module Specifications

#### 2.1 Smart SMS / UPI Parser (`sms_parser_service.py`)
- **Supported Institutions**: HDFC, SBI, ICICI, Axis, Kotak, PNB, Bank of Baroda, Canara, IDFC, Citibank, Yes Bank, Paytm Payments Bank, IndusInd, and UPI rails (Google Pay, PhonePe, Paytm, BHIM).
- **Core Entities Extracted**:
  - `amount`: Strict regex matching `INR`, `Rs.`, `₹` with decimal and comma support.
  - `transaction_type`: `EXPENSE` (debited, spent, paid, sent, dr) vs `INCOME` (credited, received, salary, deposited, cr).
  - `merchant_clean`: Sanitized merchant payee name stripping bank boilerplate tokens (`VPA`, `M/s`, `The`).
  - `date`: Full date resolution covering ISO (`YYYY-MM-DD`), standard Indian format (`DD-MM-YYYY`), and banking format (`DD-Mon-YY`).
  - `ref_number`: UPI Reference Number, UTR, or RRN identifier.
  - `bank_name` & `account_last4`: Identified institution and account suffix.
- **Safety Filters**:
  - Rejects authentication OTP messages, security PIN requests, and marketing notifications without financial action verbs.
  - Amount validation: Rejects SMS if amount is zero or absent.
- **Confidence Scoring**:
  - `HIGH`: Amount, type, date, and clean merchant reliably parsed (Score $\ge 80$).
  - `MEDIUM`: Financial amount and type found, but merchant or date inferred (Score $50-79$).
  - `LOW`: Ambiguous or missing fields; triggers manual review flag.

#### 2.2 Duplicate Transaction Detector (`sms_parser_service.py`)
- Searches user ledger across a symmetric $\pm 2$ day window around the transaction date.
- **Signals**:
  1. Exact reference number match (UPI Ref / UTR / RRN in transaction note).
  2. Identical amount and merchant substring match.
  3. Identical amount on the exact same date.
- Emits a non-blocking `DuplicateResult` warning displayed prominently on the mobile review card.

#### 2.3 Subscription Intelligence Engine (`subscription_service.py`)
- **Metric Computation**: Computes exact monthly-equivalent and annual-equivalent outlays across active recurring bills.
- **Candidate Discovery**: Queries historical `EXPENSE` transactions over the trailing 90 days. Detects charges occurring $\ge 2$ times with identical amounts or known subscription merchant keywords (`Netflix`, `Spotify`, `Amazon Prime`, `Hotstar`, `YouTube`, `Apple`, `Gym`, `Broadband`).
- **Overlapping Subscription Warning**: Detects dual subscriptions to the same brand or service family (e.g. paying for both *Netflix Mobile* and *Netflix Premium* simultaneously) and advises consolidation.
- **One-Tap Conversion**: `convert_candidate_to_recurring()` promotes discovered candidates directly into active tracked bills.

#### 2.4 Cash-Flow Calendar Service (`cashflow_calendar_service.py`)
- Generates a day-by-day financial projection timeline for any requested monthly window.
- **Layers**:
  - **ACTUAL**: Real past/present inflows and outflows recorded in the ledger.
  - **COMMITTED**: Future scheduled recurring bills due on specific calendar dates.
  - **PROJECTED**: Baseline daily discretionary spending velocity derived from the Forecast Engine.
- **Key Outputs**:
  - Running liquid balance trajectory.
  - Lowest projected balance date and trough amount.
  - Runway days remaining before safety threshold violation.
  - Low balance risk flag when balance is projected to breach Rs. 2,000 threshold.

#### 2.5 Smart Financial Alerts Engine (`alerts_engine.py`)
- **Deterministic Alert Types**:
  - `BUDGET_OVERRUN`: Projected month-end discretionary velocity exceeds allocated budget limit.
  - `BUDGET_80`: Actual spend pace breaches 80% of budget cap.
  - `UPCOMING_BILL`: Unpaid bill due within 3 calendar days.
  - `OVERDUE_BILL`: Unpaid bill whose scheduled due date has passed.
  - `UNUSUAL_SPENDING`: Category spending spike exceeding $\mu + 2\sigma$ above historical baseline.
  - `GOAL_BEHIND`: Savings goal running behind required monthly pacing.
- **Notification Fatigue Defense**:
  - 24-hour deduplication window: Alerts of the same type and user are suppressed if dispatched within the last 24 hours.
  - User Preference Gating: Honors granular user preferences (`budget_80`, `budget_100`, `bill_due`, `forecast`, `goals`, `weekly_summary`, `unusual_spending`, `all_off`).

#### 2.6 Real Web Push Delivery Service (`push_delivery_service.py`)
- Seamlessly delivers Web Push via RFC 8291/8292 standard payloads signed with VAPID keys.
- **Automatic Pruning**: Detects HTTP 404/410 responses from push endpoints (FCM, Mozilla, Apple) and automatically unregisters expired device tokens.
- **In-App Persistence**: Persists all notifications and financial alerts to `notifications` and `financial_alerts` tables, ensuring zero notification loss even when devices are offline.

---

### 3. Database Evolution (v2.0 Phase 6)

Four high-performance tables and preference extensions have been added across SQLite (development) and PostgreSQL (production):

```sql
-- 1. Ingested Transaction Parse Events
CREATE TABLE IF NOT EXISTS transaction_parse_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type VARCHAR(20) NOT NULL,
    raw_text TEXT,
    parsed_data_json TEXT,
    confidence VARCHAR(20),
    status VARCHAR(20) DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Discovered Subscription Candidates
CREATE TABLE IF NOT EXISTS subscription_candidates (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    frequency VARCHAR(20) DEFAULT 'MONTHLY',
    last_charged_date DATE,
    confidence VARCHAR(20),
    status VARCHAR(20) DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Deterministic Financial Alerts
CREATE TABLE IF NOT EXISTS financial_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    supporting_metric TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Notification Delivery Log
CREATE TABLE IF NOT EXISTS notification_delivery_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint TEXT,
    payload_json TEXT,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_alerts_user ON financial_alerts(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_sub_cand_user ON subscription_candidates(user_id, status);
CREATE INDEX IF NOT EXISTS idx_parse_user ON transaction_parse_events(user_id);
```

---

### 4. REST API Endpoint Catalog

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/parser/parse-sms` | JWT Bearer | Analyzes raw SMS/UPI text and returns structured proposal + duplicate warning |
| `POST` | `/api/v1/parser/confirm-transaction` | JWT Bearer | Verifies and commits user-confirmed transaction to official ledger |
| `GET` | `/api/v1/subscriptions/overview` | JWT Bearer | Returns monthly/annual subscription totals and duplicate warnings |
| `GET` | `/api/v1/subscriptions/candidates` | JWT Bearer | Lists recurring charges discovered from historical ledger |
| `POST` | `/api/v1/subscriptions/convert-candidate` | JWT Bearer | Promotes discovered candidate to official recurring bill |
| `GET` | `/api/v1/cashflow/calendar` | JWT Bearer | Returns daily actual/committed/projected timeline and liquidity status |
| `GET` | `/api/v1/goals/intelligence` | JWT Bearer | Returns required monthly pacing and projected finish dates for goals |
| `GET` | `/api/v1/alerts` | JWT Bearer | Evaluates financial rules and returns active unread alerts |
| `POST` | `/api/v1/alerts/<id>/dismiss` | JWT Bearer | Dismisses / marks an alert as read |
| `GET/POST`| `/api/v1/notifications/preferences` | JWT Bearer | Reads or updates granular notification suppression preferences |
