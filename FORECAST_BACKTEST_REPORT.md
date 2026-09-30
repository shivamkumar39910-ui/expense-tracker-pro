# FORECAST ENGINE 2.0 — BACKTESTING ACCURACY REPORT
**Generated:** 2026-09-30 17:44:01
**Evaluated Cutoff Periods:** 9

## 1. Summary Performance Metrics
- **MAE (Mean Absolute Error):** ₹13,915.00
- **RMSE (Root Mean Squared Error):** ₹17,319.33
- **MAPE (Mean Absolute Percentage Error):** 69.58%

## 2. Evaluation Methodology & Leakage Prevention
- **Zero Future Data Leakage:** Forecast calculation for cutoff date $T$ only observed transactions where $date \le T$.
- **Completed Historical Months:** Used preceding calendar months for WMA baseline.
- **Cutoff Checkpoints:** Simulations executed across early-month (Day 7), mid-month (Day 14), and late-month (Day 21).

## 3. Period-by-Period Evaluation Results
| Forecast Date | Month | Cutoff Day | MTD Spend | Predicted | Actual Ground Truth | Absolute Error | Pct Error | Confidence |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 2026-06-07 | Jun 2026 | Day 7 | ₹14,000.00 | ₹60,000.00 | ₹20,000.00 | ₹40,000.00 | 200.0% | LOW |
| 2026-06-14 | Jun 2026 | Day 14 | ₹20,000.00 | ₹42,857.12 | ₹20,000.00 | ₹22,857.12 | 114.3% | LOW |
| 2026-06-21 | Jun 2026 | Day 21 | ₹20,000.00 | ₹28,571.42 | ₹20,000.00 | ₹8,571.42 | 42.9% | MEDIUM |
| 2026-07-07 | Jul 2026 | Day 7 | ₹14,000.00 | ₹29,483.87 | ₹20,000.00 | ₹9,483.87 | 47.4% | MEDIUM |
| 2026-07-14 | Jul 2026 | Day 14 | ₹20,000.00 | ₹30,967.73 | ₹20,000.00 | ₹10,967.73 | 54.8% | MEDIUM |
| 2026-07-21 | Jul 2026 | Day 21 | ₹20,000.00 | ₹26,451.61 | ₹20,000.00 | ₹6,451.61 | 32.3% | HIGH |
| 2026-08-07 | Aug 2026 | Day 7 | ₹14,000.00 | ₹29,483.87 | ₹20,000.00 | ₹9,483.87 | 47.4% | MEDIUM |
| 2026-08-14 | Aug 2026 | Day 14 | ₹20,000.00 | ₹30,967.73 | ₹20,000.00 | ₹10,967.73 | 54.8% | MEDIUM |
| 2026-08-21 | Aug 2026 | Day 21 | ₹20,000.00 | ₹26,451.61 | ₹20,000.00 | ₹6,451.61 | 32.3% | HIGH |

## 4. Key Takeaways & Limitations
- **Early Month (Day 7):** Prediction is stabilized by historical WMA and recurring bill commitments rather than volatile 7-day velocity extrapolation.
- **Mid/Late Month (Day 14 & 21):** Alpha smoothly shifts weight to observed current velocity as data volume increases, reducing error margins.
- **Sparse Data Behavior:** In months with 0 or single-digit transactions, confidence drops gracefully to `LOW`.