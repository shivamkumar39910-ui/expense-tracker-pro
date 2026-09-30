# FORECAST ENGINE 2.0 — COMPREHENSIVE ARCHITECTURAL AUDIT
**Date:** September 30, 2026  
**System:** Expense Tracker Pro 2.0 (Live Production Core)  
**Author:** Antigravity Senior Engineering Team  

---

## 1. Executive Summary
Expense Tracker Pro 2.0 currently features a deterministic personal expense forecasting engine ([`forecasting_engine.py`](forecasting_engine.py)), an AI Financial Mentor service ([`ai_mentor_service.py`](ai_mentor_service.py)), REST endpoints in [`api_v1.py`](api_v1.py), and an analytics/forecasting UI in [`templates/mobile_app.html`](templates/mobile_app.html).

While the existing system established a strong foundation by avoiding fake AI and relying on deterministic run-rate velocity and 3-month weighted moving averages, this comprehensive audit reveals key mathematical, architectural, and data-integrity limitations that must be upgraded to deliver a production-grade **Forecast Engine 2.0**.

---

## 2. Detailed Technical Audit Findings

### A. Existing Forecast Formulas
The current engine in [`forecasting_engine.py`](forecasting_engine.py) implements:
1. **MTD Spend**: Sum of `amount` where `transaction_type = 'EXPENSE'` and `date LIKE YYYY-MM%` and `date <= target_date`.
2. **Historical Baseline (WMA)**: Fixed weights $0.50 \times M_1 + 0.30 \times M_2 + 0.20 \times M_3$ over the preceding 3 calendar months. Fallback if sum is 0: `mtd_spend * (total_days / elapsed)`.
3. **Run-Rate Velocity**: $V = \frac{\text{Spend}_{MTD}}{\text{Days Elapsed}} \times \text{Total Days}$.
4. **Early-Month Alpha Smoothing**: $\alpha = \min(1.0, \max(0.1, \frac{\text{Days Elapsed}}{\text{Total Days}}))$.
5. **Final Projected Spend**:
   $$\text{Final} = (\alpha \times V) + ((1 - \alpha) \times B) + (R_{unpaid} \times (1 - \alpha))$$

> [!WARNING] **Critical Formula Flaw in Recurring Bills**:
> Line 97 multiplies $R_{unpaid}$ by $(1 - \alpha)$. As the month progresses towards day 28–30, $\alpha \to 1.0$, which means $(1 - \alpha) \to 0$. Consequently, upcoming unpaid bills due late in the month (e.g. day 29 or 30) are practically multiplied by 0 and erased from the forecast! Unpaid committed bills must be added as real upcoming liabilities or treated with proper accrual.

### B. Existing Forecast Data Sources
- **`transactions` table**: Filters by `user_id`, `transaction_type = 'EXPENSE'`, `date`.
  - Correctly excludes `TRANSFER` and `INCOME` transactions.
  - Relies on SQL `LIKE 'YYYY-MM%'` which does not leverage date range index comparisons efficiently.
- **`recurring_bills` table**: Queries `WHERE user_id = ? AND is_active = 1 AND due_day > current_day AND due_day <= total_days`.
  - Does NOT check whether a recurring bill was already paid in the current month (i.e. if a payment transaction was already logged for this cycle).
  - Assumes `due_day` is an integer; does not account for weekly bills that occur multiple times per month.
- **`budgets` table**: Queries monthly overall budget (`category_id IS NULL OR category_id = 0`).

### C. Existing Forecast Endpoints
- `GET /api/v1/forecast/month-end`:
  - Accepts optional `?date=YYYY-MM-DD`.
  - Calls `forecasting_engine.calculate_month_end_forecast(user_id, target_date=target_date)`.
  - Returns `success: True` and forecast dictionary.
- `GET /api/v1/insights/anomalies`: Calls `forecasting_engine.detect_spending_anomalies(user_id)`.
- `GET /api/v1/insights/mom`: Calls `ai_mentor_service.get_mom_analysis(user_id)`.
- `POST /api/v1/insights/ai-mentor`: Calls `ai_mentor_service.generate_ai_mentor_advice(user_id, prompt)`.
- `GET /api/v1/command-center/summary`: Embeds forecast snapshot.

### D. Existing Forecast UI
Located in [`templates/mobile_app.html`](templates/mobile_app.html) (Tab 4: `tab-forecast` and Home screen banner):
- Home Screen Banner: Shows projected spend, velocity per day, risk pill (`SAFE` / `WARNING` / `DANGER`), and warning message.
- Tab 4 Dedicated Screen:
  - Hero card with projected month-end expenditure, savings cushion, daily velocity, safe daily cap, and explanation narrative.
  - Next month early projection (WMA).
  - 3 action suggestion cards (Safe Daily Cap, Dining Out Pacing, Goal Acceleration).
  - SVG spending trajectory chart.
  - MoM comparison list.
  - Statistical anomalies list.
  - Donut chart and 6-month history.

### E. Existing AI Mentor Logic
In [`ai_mentor_service.py`](ai_mentor_service.py):
- Deterministic rule-based mentor that reads `calculate_month_end_forecast`, `detect_spending_anomalies`, `get_mom_analysis`, and `get_net_worth_summary`.
- Uses deterministic templates for budget warnings, top category concentration, and statistical anomalies.
- Responds to keywords like "afford", "save", "cut".
- Does not hallucinate numbers. However, recommendations are somewhat hardcoded (e.g. "Trimming 15% from Food saves ₹X").

### F. Existing Confidence Logic
- **Completely Missing**: The existing engine returns NO confidence rating (`HIGH`, `MEDIUM`, `LOW`) and NO explanation for prediction certainty. It presents a single point estimate regardless of whether the user has 6 months of stable history or signed up 1 hour ago.

### G. Existing Budget Logic
- Thresholds:
  - Projected $\le \text{Budget} \times 0.85$: `SAFE`
  - Projected $> \text{Budget} \times 0.85$ and $\le \text{Budget}$: `WARNING`
  - Projected $> \text{Budget}$: `DANGER`
  - No budget: `NO_BUDGET`
- Weakness: Does not handle negative remaining budget cleanly if already exceeded MTD; does not provide machine-readable `risk_level` (`LOW`, `MODERATE`, `HIGH`, `CRITICAL`) with deterministic machine-readable reasons.

### H. Existing Recurring Bill Integration
- Only checks `due_day > current_day`.
- Does not check if the bill was already paid in the ledger this month.
- Does not support weekly frequencies (which can recur up to 4 times a month).
- Formula attenuates unpaid bills by $(1 - \alpha)$.

### I. Existing Category Calculations
- Computes MTD category spending, but category projection is simply $\frac{\text{Spend}_{MTD}}{\text{Elapsed}} \times \text{Total Days}$.
- Ignores historical category baselines, category seasonality, or category-specific volatility.
- Can create absurd projections on Day 1–3 if a user bought one large item in a category.

### J. Existing Tests
- `test_api.py` (Test 12): Validates endpoint status 200, checks `risk_status == 'SAFE'`.
- No isolated tests for:
  - Day 0/1 edge cases.
  - Zero transaction / new user.
  - 1-month vs multi-month history.
  - Double counting of paid recurring bills.
  - Future data leakage.
  - Category projections.
  - Confidence scoring.
  - Backtesting accuracy.

### K. Existing Weaknesses & Gaps Summary
1. **Mathematical Flaw in Recurring Bill Overlay**: $(1 - \alpha) \times R_{unpaid}$ vanishes at month end.
2. **No Double-Counting Protection for Recurring Bills**: Paid bills are counted in MTD expenses AND might be re-counted if due date isn't updated.
3. **No Confidence Score**: Does not tell user if prediction is based on 6 months of data or 1 day.
4. **Pure Linear Velocity for Categories**: High early-month variance.
5. **Float Arithmetic**: Uses Python `float` instead of `Decimal` / SQL `NUMERIC`.
6. **No Backtesting Engine**: No MAE/RMSE evaluation on historical data.
7. **Future Data Leakage Risk**: No explicit date guard preventing transactions dated $> \text{target\_date}$ from leaking into historical baselines.
8. **UI Disconnect**: Some UI cards in Tab 4 have static text (e.g. ₹25k hardcoded in SVG trajectory text).

---

## 3. Plan for Forecast Engine 2.0

### What Can Be Reused:
- Database connection abstraction (`db_engine.get_db_connection()`).
- User isolation filtering (`WHERE user_id = ?`).
- Transaction exclusion of `TRANSFER` and `INCOME`.
- General concept of blending Historical Baseline (WMA) and Current Velocity with $\alpha$ smoothing.
- Frontend mobile layout and design tokens in `templates/mobile_app.html`.

### What Must Be Refactored:
- Recurring bill projection: Detect paid vs unpaid bills in current cycle; properly add upcoming commitments to remaining projected spend.
- Category forecasting: Blend historical category baseline with current velocity; provide confidence per category.
- Budget risk engine: Standardize risk levels (`LOW`, `MODERATE`, `HIGH`, `CRITICAL`), compute safe daily spend.
- AI Mentor recommendations: Dynamic, mathematically backed recommendations with supporting metrics and actions.

### What Must Be Replaced / Added:
- **`forecasting_engine.py`**: Upgrade to modular, Decimal-safe, multi-factor Forecast Engine 2.0.
- **`forecast_metrics.py`**: New backtesting module implementing MAE, RMSE, MAPE across historical months without future data leakage.
- **Confidence Scoring Engine**: Deterministic confidence computation based on data volume, volatility, and elapsed days.
- **New API Endpoint & Upgraded Endpoint**: Support standard `GET /api/v1/forecast/month-end` and provide comprehensive `GET /api/forecast` payload.
- **Automated Test Suite**: Full coverage of edge cases, user isolation, leakage prevention, and metrics.
