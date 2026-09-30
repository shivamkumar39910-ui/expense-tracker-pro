# FORECAST ENGINE 2.0 — ARCHITECTURAL SPECIFICATION & SYSTEM DESIGN
**Document Version:** 2.0.0  
**Project:** Expense Tracker Pro 2.0  
**Status:** Implemented, Tested & Production-Verified  
**Component:** `forecasting_engine.py` & `forecast_metrics.py`  

---

## 1. System Overview & Philosophy

Forecast Engine 2.0 is a deterministic, explainable, multi-factor forecasting system engineered specifically for consumer personal finance. It replaces naive single-formula run-rate extrapolations with a layered quantitative pipeline:

$$\text{Transactions} \xrightarrow{\text{Data Pipeline}} \text{Velocity + Baseline WMA + Recurring Overlay} \xrightarrow{\text{Risk & Confidence}} \text{Explainable Recommendations}$$

### Core Operating Principles:
1. **Zero Hallucination**: No synthetic AI numbers, no arbitrary guesses. Every figure is directly derived from authenticated user records.
2. **Strict User Data Isolation**: Every SQL query is strictly scoped to `user_id`. Cross-user data leakage is architecturally prohibited.
3. **Zero Future Data Leakage**: All calculations accept an optional `target_date` cutoff $T$. Transactions where $date > T$ are strictly filtered out.
4. **Zero Double-Counting of Recurring Bills**: Bills paid in the current cycle are excluded from future committed liabilities.
5. **Decimal Financial Precision**: Arithmetic uses PostgreSQL `NUMERIC` / Python `Decimal` quantization to prevent IEEE 754 floating-point drift.

---

## 2. Mathematical Model & Formula Hierarchy

### 2.1 Month-to-Date (MTD) Actual Expenses
Let $T$ be the evaluation date ($1 \le d \le N$, where $N$ is the number of days in the month):
$$\text{Spend}_{MTD} = \sum_{\substack{t \in \text{Transactions} \\ \text{type} = \text{'EXPENSE'} \\ \text{date} \in [\text{Month Start}, T]}} \text{amount}(t)$$
*Note: Transactions of type `INCOME` and `TRANSFER` are strictly excluded.*

### 2.2 Current Velocity Model
$$\text{Daily Velocity } (V) = \frac{\text{Spend}_{MTD}}{\max(1, d)}$$
$$\text{Projected Velocity Spend } (S_v) = \text{Spend}_{MTD} + V \times (N - d)$$
- **Boundary Handling**: At $d = N$ (month-end), remaining days = 0, so $S_v = \text{Spend}_{MTD}$. At $d = 1$ with zero transactions, $V = 0.0$.

### 2.3 Historical Baseline Model (Weighted Moving Average)
Evaluates up to 6 completed preceding calendar months:
- If 3+ months available:
  $$B = 0.50 \times M_1 + 0.30 \times M_2 + 0.20 \times M_3$$
  *(where $M_1$ is the most recent completed month)*
- If 2 months available:
  $$B = 0.60 \times M_1 + 0.40 \times M_2$$
- If 1 month available:
  $$B = 1.00 \times M_1$$
- If 0 months available:
  $$B = S_v \quad (\text{graceful fallback to velocity model})$$

### 2.4 Time-Varying Alpha Smoothing ($\alpha$)
As days elapse in the current month, confidence in observed current-month velocity increases, while reliance on historical averages decreases:
$$\alpha = \min\left(1.00, \max\left(0.10, \frac{\max(1, d)}{N}\right)\right)$$
$$\text{Discretionary Forecast } (F_{\text{disc}}) = (\alpha \times S_v) + ((1 - \alpha) \times B)$$

### 2.5 Recurring Bills Overlay (Committed Spending)
Let $R$ be the set of active recurring bills. Each bill $r \in R$ is evaluated:
- **Paid Status Detection**: If bill payment transaction exists in current month MTD or $r.\text{next\_due\_date}$ is already in a future month $\implies r$ is `PAID_THIS_MONTH`.
- **Upcoming Status Detection**: If not paid and $r.\text{due\_day} > d$ (or weekly/yearly due date $\in (T, \text{Month End}]) \implies r$ is `UPCOMING_UNPAID`.
$$\text{Upcoming Obligations } (U) = \sum_{r \in \text{Upcoming}} \text{amount}(r)$$

### 2.6 Final Consolidated Month-End Projection
$$\text{Projected Month-End Spend } (F) = \max(\text{Spend}_{MTD}, F_{\text{disc}} + U)$$

---

## 3. Budget Risk Engine & Safe Daily Cap

### 3.1 Risk Levels & Deterministic Thresholds
Given monthly budget limit $C$:
| Condition | Risk Level | Legacy Status | Risk Reason Description |
| :--- | :---: | :---: | :--- |
| $C \le 0$ | `LOW` | `NO_BUDGET` | No monthly budget ceiling configured. |
| $\text{Spend}_{MTD} > C$ | `CRITICAL` | `DANGER` | Budget already breached MTD. |
| $F > C$ | `HIGH` | `DANGER` | Projected month-end spend exceeds budget limit. |
| $F \ge 0.85 \times C$ | `MODERATE` | `WARNING` | Projected to consume $\ge 85\%$ of budget ceiling. |
| $F < 0.85 \times C$ | `LOW` | `SAFE` | Healthy pacing; surplus savings projected. |

### 3.2 Safe Daily Spending Cap
Accounts for upcoming committed liabilities:
$$\text{Safe Daily Cap} = \max\left(0.00, \frac{(C - \text{Spend}_{MTD} - U)}{\max(1, N - d)}\right)$$

---

## 4. Multi-Factor Confidence Scoring

Evaluated on a deterministic 100-point scale:
1. **History Volume (35 pts)**: $\ge 3$ completed months (+35), 1-2 months (+20), 0 months (+5).
2. **Transaction Density (25 pts)**: $\ge 15$ MTD transactions (+25), 5-14 (+15), $< 5$ (+5).
3. **Volatility Coefficient ($CV = \frac{\sigma}{\mu}$) (20 pts)**: $CV < 0.25$ (+20), $0.25 \le CV \le 0.50$ (+10), $> 0.50$ (+5).
4. **Month Progression (20 pts)**: $\ge 50\%$ month elapsed (+20), $20-49\%$ (+10), $< 20\%$ (+5).

- Score $\ge 70 \implies$ **`HIGH`**
- Score $45 - 69 \implies$ **`MEDIUM`**
- Score $< 45 \implies$ **`LOW`**

---

## 5. API Endpoints

### 5.1 `GET /api/v1/forecast` & `GET /api/forecast`
- **Authentication**: JWT Bearer token required.
- **Parameters**: `?date=YYYY-MM-DD` (optional, defaults to current date).
- **Response**:
```json
{
  "success": true,
  "current_spend": 1200.0,
  "budget": 25000.0,
  "remaining_budget": 23800.0,
  "projected_month_end": 1500.0,
  "safe_daily_spend": 780.0,
  "days_elapsed": 24,
  "days_remaining": 6,
  "velocity": 50.0,
  "budget_usage_percentage": 6.0,
  "risk_level": "LOW",
  "risk_reason": "On track! Projected to finish month using 6.0% of budget.",
  "confidence": "HIGH",
  "confidence_score": 85,
  "confidence_reason": "Based on 3 completed months of history, consistent spending patterns.",
  "historical_baseline": 18450.0,
  "category_forecasts": [...],
  "upcoming_recurring": [...],
  "recommendations": [...]
}
```

### 5.2 `GET /api/v1/forecast/backtest`
- **Authentication**: JWT Bearer token required.
- **Function**: Executes leakage-free simulation across preceding 3 completed months at Day 7, 14, and 21. Returns MAE, RMSE, MAPE and period-by-period evaluation table.
