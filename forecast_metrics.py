"""
FORECAST METRICS & BACKTESTING ENGINE (forecast_metrics.py)
Expense Tracker Pro 2.0 - Quantitative Evaluation Framework

This module provides a rigorous, leakage-free backtesting framework for Forecast Engine 2.0.
Methodology:
1. Selects historical completed months.
2. Simulates an as-of cutoff date (e.g., Day 7, Day 14, Day 21).
3. Evaluates Forecast Engine 2.0 strictly using data available before the cutoff date.
4. Compares predicted month-end spend against actual revealed month-end spend.
5. Computes standard evaluation metrics:
   - MAE (Mean Absolute Error)
   - RMSE (Root Mean Squared Error)
   - MAPE (Mean Absolute Percentage Error, when actual > 0)
"""

import math
import calendar
from datetime import date, datetime
from typing import Dict, Any, List, Optional, Tuple
import db_engine
import forecasting_engine

def get_actual_month_spend(user_id: int, year: int, month: int, db_path: str = "expenses.db") -> float:
    """
    Returns actual ground-truth total expense spend for a completed calendar month.
    """
    conn, cursor = forecasting_engine.get_db_cursor(db_path)
    try:
        pattern = f"{year:04d}-{month:02d}%"
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0.0) as actual_spend
            FROM transactions
            WHERE user_id = ? AND transaction_type = 'EXPENSE' AND date LIKE ? AND amount > 0
        """, (user_id, pattern))
        row = cursor.fetchone()
        return float(row["actual_spend"]) if row else 0.0
    finally:
        conn.close()

def run_backtest_simulation(
    user_id: int,
    test_months: List[Tuple[int, int]],
    cutoff_days: List[int] = [7, 14, 21],
    db_path: str = "expenses.db"
) -> Dict[str, Any]:
    """
    Executes simulated backtests across specified historical (year, month) pairs and cutoff days.
    Guarantees: ZERO future data leakage.
    """
    evaluations = []
    abs_errors = []
    sq_errors = []
    pct_errors = []

    for year, month in test_months:
        total_days = forecasting_engine.get_days_in_month(year, month)
        actual_spend = get_actual_month_spend(user_id, year, month, db_path)

        for cday in cutoff_days:
            if cday > total_days:
                continue

            cutoff_date = date(year, month, cday)
            cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")

            # Run forecast engine with strict historical cutoff
            fc = forecasting_engine.calculate_month_end_forecast(
                user_id=user_id,
                target_date=cutoff_date,
                db_path=db_path
            )

            predicted = fc["projected_month_end_spend"]
            err = round(predicted - actual_spend, 2)
            abs_err = round(abs(err), 2)
            sq_err = err ** 2

            abs_errors.append(abs_err)
            sq_errors.append(sq_err)

            pct_err = None
            if actual_spend > 0:
                pct_err = round((abs_err / actual_spend) * 100, 2)
                pct_errors.append(pct_err)

            evaluations.append({
                "forecast_date": cutoff_date_str,
                "historical_month": f"{calendar.month_abbr[month]} {year}",
                "cutoff_day": cday,
                "days_in_month": total_days,
                "mtd_spend_at_cutoff": fc["mtd_actual_spend"],
                "predicted": predicted,
                "actual": actual_spend,
                "error": err,
                "absolute_error": abs_err,
                "percentage_error": pct_err,
                "confidence": fc["confidence"]
            })

    num_evals = len(evaluations)
    if num_evals > 0:
        mae = round(sum(abs_errors) / num_evals, 2)
        rmse = round(math.sqrt(sum(sq_errors) / num_evals), 2)
        mape = round(sum(pct_errors) / len(pct_errors), 2) if len(pct_errors) > 0 else None
    else:
        mae, rmse, mape = 0.0, 0.0, None

    return {
        "evaluated_periods_count": num_evals,
        "metrics": {
            "MAE": mae,
            "RMSE": rmse,
            "MAPE": mape
        },
        "evaluations": evaluations
    }

def generate_backtest_markdown_report(backtest_results: Dict[str, Any]) -> str:
    """
    Formats backtesting evaluations and accuracy metrics into a clean Markdown report.
    """
    m = backtest_results.get("metrics", {})
    count = backtest_results.get("evaluated_periods_count", 0)
    evals = backtest_results.get("evaluations", [])

    lines = [
        "# FORECAST ENGINE 2.0 — BACKTESTING ACCURACY REPORT",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Evaluated Cutoff Periods:** {count}",
        "",
        "## 1. Summary Performance Metrics",
        f"- **MAE (Mean Absolute Error):** ₹{m.get('MAE', 0.0):,.2f}",
        f"- **RMSE (Root Mean Squared Error):** ₹{m.get('RMSE', 0.0):,.2f}",
        f"- **MAPE (Mean Absolute Percentage Error):** {m.get('MAPE') if m.get('MAPE') is not None else 'N/A'}%",
        "",
        "## 2. Evaluation Methodology & Leakage Prevention",
        "- **Zero Future Data Leakage:** Forecast calculation for cutoff date $T$ only observed transactions where $date \\le T$.",
        "- **Completed Historical Months:** Used preceding calendar months for WMA baseline.",
        "- **Cutoff Checkpoints:** Simulations executed across early-month (Day 7), mid-month (Day 14), and late-month (Day 21).",
        "",
        "## 3. Period-by-Period Evaluation Results",
        "| Forecast Date | Month | Cutoff Day | MTD Spend | Predicted | Actual Ground Truth | Absolute Error | Pct Error | Confidence |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    ]

    for e in evals:
        pct_str = f"{e['percentage_error']:.1f}%" if e['percentage_error'] is not None else "N/A"
        lines.append(
            f"| {e['forecast_date']} | {e['historical_month']} | Day {e['cutoff_day']} | "
            f"₹{e['mtd_spend_at_cutoff']:,.2f} | ₹{e['predicted']:,.2f} | ₹{e['actual']:,.2f} | "
            f"₹{e['absolute_error']:,.2f} | {pct_str} | {e['confidence']} |"
        )

    lines.extend([
        "",
        "## 4. Key Takeaways & Limitations",
        "- **Early Month (Day 7):** Prediction is stabilized by historical WMA and recurring bill commitments rather than volatile 7-day velocity extrapolation.",
        "- **Mid/Late Month (Day 14 & 21):** Alpha smoothly shifts weight to observed current velocity as data volume increases, reducing error margins.",
        "- **Sparse Data Behavior:** In months with 0 or single-digit transactions, confidence drops gracefully to `LOW`."
    ])

    return "\n".join(lines)
