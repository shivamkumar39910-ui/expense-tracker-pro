# EXPENSE TRACKER PRO 2.0 - FINAL SYSTEM ARCHITECTURE
**Document Version:** 2.0.0-PROD  
**Generated:** 2026-09-30  
**Environment:** Render Cloud (Production) / Local Fallback  

---

## 1. ARCHITECTURAL OVERVIEW

Expense Tracker Pro 2.0 is designed as a secure, high-precision, personal finance management system. It bridges a modern mobile-first Progressive Web Application (PWA) frontend with a hardened Python/Flask backend and an enterprise-grade PostgreSQL database.

```
       +-------------------------------------------------------+
       |                  CLIENT LAYER (PWA)                  |
       |  - Responsive Mobile Shell (templates/mobile_app.html)|
       |  - Service Worker Caching & Offline Sync Badge        |
       |  - Keypad-Driven Fast Entry & Haptic Feedback         |
       |  - Cash-Flow Calendar & Visual Analytics              |
       +---------------------------+---------------------------+
                                   | HTTPS / REST JSON
                                   v
       +-------------------------------------------------------+
       |               API ROUTING & SECURITY LAYER            |
       |  - Flask Application (`app_web.py` / `app.py`)        |
       |  - Security Middleware (nosniff, SAMEORIGIN, CORS)    |
       |  - JWT Bearer Authentication & 5-Attempt Rate Limiting|
       |  - Versioned API Blueprint (`/api/v1/*` in `api_v1.py`)|
       +---------------------------+---------------------------+
                                   |
         +-------------------------+-------------------------+
         |                         |                         |
         v                         v                         v
+------------------+     +-------------------+     +------------------+
| FINANCIAL ENGINE |     | FORECAST 2.0      |     | AUTOMATION CORE  |
| - Double-Entry   |     | - WMA Trend Model |     | - SMS/UPI Parser |
|   Ledger Math    |     | - Velocity Drift  |     | - Duplicate Check|
| - Budgets & Caps |     | - Category Drift  |     | - Sub Audits     |
| - Goal Pacing    |     | - Zero Leakage    |     | - Alerts Engine  |
| - Live FX Cache  |     | - Explainable AI  |     | - Web Push VAPID |
+--------+---------+     +---------+---------+     +--------+---------+
         |                         |                        |
         +-------------------------+------------------------+
                                   |
                                   v
       +-------------------------------------------------------+
       |             UNIVERSAL DATABASE ABSTRACTION            |
       |             (`db_engine.py` & `database.py`)          |
       |  - Connection Pooling & Auto-Reconnection             |
       |  - Dialect Translation (? -> %s)                      |
       |  - Dict+Tuple Row Mapping & Decimal Precision Guard   |
       |  - Atomic Transactions & Rollback Support             |
       +---------------------------+---------------------------+
                                   |
                                   v
       +-------------------------------------------------------+
       |               DATA STORAGE LAYER (16 TABLES)          |
       |  - Production: Managed PostgreSQL (Render Cloud)      |
       |  - Development: SQLite WAL Mode (expenses.db)         |
       |  - Zero-Data-Loss Migration (`db_migration.py`)       |
       +-------------------------------------------------------+
```

---

## 2. CORE SUBSYSTEM SPECIFICATIONS

### 2.1 Universal Database Abstraction Layer (`db_engine.py`)
- **Dual-Dialect Translation:** Seamlessly translates standard parameter placeholders (`?`) into PostgreSQL parameter format (`%s`).
- **PostgresRowWrapper:** Implements full `Mapping` and sequence protocol, allowing access by string column name (`row["amount"]`) and numerical index (`row[0]`).
- **Decimal Precision Guarantee:** Automatically converts psycopg2 `Decimal` types to clean Python floats for REST JSON serialization while preserving internal exact math (`Decimal("0.01")`).
- **Fail-Safe Fallback:** If `DATABASE_URL` is omitted, the engine transparently connects to SQLite (`expenses.db`) in WAL mode with strict foreign key constraints enabled.

### 2.2 Security & Authentication System (`auth_service.py` & `api_v1.py`)
- **Registration OTP:** 6-digit cryptographically random OTP generated and sent to email/phone, expiring strictly after 10 minutes.
- **Two-Factor Authentication (2FA) Login:** Credentials verified in Step 1, requiring a temporary time-bound OTP in Step 2 before a signed JWT access token is granted.
- **SHA-256 App PIN Protection:** Users can set a 4-digit PIN for quick device unlock. Salted SHA-256 hashing prevents plaintext exposure.
- **Brute-Force Rate Limiting:** Enforces an in-memory sliding lockout window: 5 consecutive invalid OTP or PIN attempts trigger an immediate HTTP 429 Too Many Requests response with a 15-minute cooldown.

### 2.3 Financial Ledger & Invariant Guarantees (`database.py`)
- **Double-Entry Balance Math:** Every transaction update respects:
  $$\text{Current Balance} = \text{Initial Balance} + \sum \text{Income} - \sum \text{Expenses} + \sum \text{Transfers In} - \sum \text{Transfers Out}$$
- **Atomic Rollback on Deletion:** Deleting an expense, income, or transfer transaction atomically restores the respective account balances inside a single database transaction.
- **Transfer Isolation:** Account transfers adjust balances between accounts without distorting monthly income, expense totals, or budget utilization.

### 2.4 Forecast Engine 2.0 (`forecast_engine.py`)
- **Weighted Moving Average (WMA):** Historical baseline weights recent months more heavily (3x for M-1, 2x for M-2, 1x for M-3).
- **Daily Spending Velocity Projection:** Projects remaining month-end spend using actual month-to-date velocity adjusted for historical variances.
- **Unpaid Bill Inclusion Without Double Counting:** Unpaid recurring commitments due before month-end are integrated into the projection; already paid or paused commitments are excluded.
- **Zero Future Data Leakage:** Backtesting and forecast calculations accept an `as_of_date` parameter; strictly no transactions with `date > as_of_date` are factored into calculations.

### 2.5 Automation & Real-World Intelligence (`sms_parser_service.py`, `subscription_service.py`, `cashflow_calendar_service.py`, `alerts_engine.py`)
- **SMS/UPI Parsing:** Multi-bank regex patterns extract amount, transaction type (debit/credit), merchant, reference number, and account last 4 digits from SMS or clipboard text.
- **Duplicate Prevention:** Evaluates transaction amount, date window ($\pm 2$ days), reference number, and merchant name to prevent duplicate transaction recording.
- **Mandatory User Confirmation:** Parsed text generates a review proposal card; transactions are never committed to the ledger without explicit user approval.
- **Subscription Discovery:** Scans historical ledger records for recurring charge intervals (25–35 days) to identify untracked subscriptions and compute annualized commitments.
- **Cash-Flow Calendar:** Produces a daily timeline plotting opening balances, actual expenses, committed recurring bills, and projected closing runway.
- **Deterministic Alerts Engine:** Generates explainable, prioritized warnings for budget overruns (80% / 100%), upcoming bills, low liquidity, goal pacing, and unusual spending with a 24-hour deduplication window.

---

## 3. COMPONENT MAP & FILE STRUCTURE

```
EXPENCE_PROJECT/
├── app.py                         # Application entrypoint & Flask app factory
├── app_web.py                     # Web routing & CORS configuration
├── api_v1.py                      # Master REST API Blueprint (all v1 routes)
├── database.py                    # Database schema, ledger operations, and data models
├── db_engine.py                   # Universal database abstraction (PostgreSQL / SQLite)
├── db_migration.py                # PostgreSQL schema creation & SQLite migration engine
├── auth_service.py                # Cryptographic hashing, OTP, JWT & PIN security
├── forecast_engine.py             # Forecast Engine 2.0 implementation & backtesting
├── fx_service.py                  # Live FX rate fetching, 12h caching & fallback
├── sms_parser_service.py          # Bank SMS/UPI regex parsing & duplicate detection
├── subscription_service.py        # Subscription discovery & annualized outlays
├── cashflow_calendar_service.py   # Daily balance runway & calendar projections
├── alerts_engine.py               # Deterministic alerts & goal pacing intelligence
├── push_delivery_service.py       # Standards-compliant VAPID Web Push delivery
├── templates/
│   ├── mobile_app.html            # Flagship Mobile PWA Client Application
│   └── (legacy desktop templates)
├── static/
│   ├── manifest.json              # PWA manifest
│   ├── service-worker.js          # Service worker for offline caching
│   └── icons/                     # PWA home screen icons
├── test_api.py                    # Core REST API endpoint tests (23 tests)
├── test_db_security.py            # Database isolation & security tests (5 tests)
├── test_phase0_security_precision.py # Header, OTP expiry & precision tests (6 tests)
├── test_phase2_recurring.py       # Recurring bills lifecycle tests (7 tests)
├── test_phase3_webpush.py         # Push notifications & preferences tests (5 tests)
├── test_phase4_fx.py              # Foreign exchange live & fallback tests (4 tests)
├── test_phase5_forecast.py        # Forecast Engine 2.0 validation suite (12 tests)
├── test_phase6_automation.py      # SMS, subscriptions, calendar & alerts (14 tests)
└── test_master_end_to_end.py      # Master End-to-End 10-journey test suite (10 tests)
```
