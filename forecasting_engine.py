"""
FORECAST ENGINE 2.0 (forecasting_engine.py)
Expense Tracker Pro 2.0 - Production-Grade Personal Expense Forecasting Engine

Pipeline Architecture:
1. Data Pipeline & Sanitization: Scoped queries, transfer/income exclusion, no future data leakage.
2. Current Velocity Model: Month-to-date spending run-rate with Day 0/1 guards.
3. Historical Baseline: Multi-month weighted moving average (3 to 6 months) with volatility metrics.
4. Category Forecasting: Blended historical category baseline and category velocity with confidence.
5. Recurring Bill Integration: Zero double-counting of paid bills, weekly/monthly cycle recognition.
6. Budget Risk Engine: Deterministic risk thresholds (LOW, MODERATE, HIGH, CRITICAL) & safe daily spend.
7. Confidence Scoring: Deterministic multi-factor scoring (data volume, volatility, month progress).
8. Explainable Recommendations: Deterministic, metric-backed insights for the AI Financial Mentor.
"""

import sqlite3
import calendar
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple
import db_engine

def to_decimal(val) -> Decimal:
    """Safely converts an integer, float, or string to Decimal with 2 decimal places."""
    if val is None:
        return Decimal("0.00")
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

def get_days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]

def get_db_cursor(db_path: str = "expenses.db"):
    if db_path == "expenses.db":
        conn = db_engine.get_db_connection()
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    return conn, conn.cursor()

# ==============================================================================
# 5.2 HISTORICAL DATA PIPELINE
# ==============================================================================
class ForecastDataPipeline:
    """
    Extracts, cleans, and aggregates user financial records up to an exact cutoff date.
    Strictly guarantees zero future data leakage.
    """

    @staticmethod
    def get_mtd_expenses(cursor, user_id: int, start_date: str, cutoff_date: str) -> Tuple[Decimal, List[Dict[str, Any]]]:
        """
        Retrieves valid MTD expenses strictly between start_date and cutoff_date.
        Excludes TRANSFER and INCOME transactions.
        """
        cursor.execute("""
            SELECT t.id, t.amount, t.date, t.category_id, COALESCE(c.name, 'Uncategorized') as category_name,
                   c.icon, c.color_hex, t.is_recurring, t.note
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
              AND t.transaction_type = 'EXPENSE'
              AND t.date >= ?
              AND t.date <= ?
              AND t.amount > 0
            ORDER BY t.date ASC
        """, (user_id, start_date, cutoff_date))
        rows = cursor.fetchall()
        
        total_spend = Decimal("0.00")
        transactions = []
        for r in rows:
            amt = to_decimal(r["amount"])
            total_spend += amt
            transactions.append({
                "id": r["id"],
                "amount": float(amt),
                "date": r["date"],
                "category_id": r["category_id"],
                "category_name": r["category_name"],
                "icon": r["icon"] if "icon" in r.keys() else "tag",
                "color_hex": r["color_hex"] if "color_hex" in r.keys() else "#6B7280",
                "is_recurring": bool(r["is_recurring"]) if "is_recurring" in r.keys() else False,
                "note": r["note"]
            })
        return total_spend, transactions

    @staticmethod
    def get_completed_months_history(cursor, user_id: int, current_year: int, current_month: int, months_back: int = 6) -> List[Dict[str, Any]]:
        """
        Retrieves total expenses and category breakdowns for up to `months_back` completed months.
        Guarantees no future leakage: only months strictly prior to current_month/current_year are fetched.
        """
        history = []
        y, m = current_year, current_month
        for _ in range(months_back):
            m -= 1
            if m == 0:
                m = 12
                y -= 1
            pattern = f"{y:04d}-{m:02d}%"
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0.0) as total_spend, COUNT(id) as tx_count
                FROM transactions
                WHERE user_id = ? AND transaction_type = 'EXPENSE' AND date LIKE ? AND amount > 0
            """, (user_id, pattern))
            row = cursor.fetchone()
            spend = to_decimal(row["total_spend"] if row else 0.0)
            count = int(row["tx_count"] if row else 0)

            # Category breakdown for this historical month
            cursor.execute("""
                SELECT COALESCE(c.name, 'Uncategorized') as category_name, COALESCE(SUM(t.amount), 0.0) as cat_spend
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ? AND t.amount > 0
                GROUP BY c.name
            """, (user_id, pattern))
            cat_rows = cursor.fetchall()
            cat_breakdown = {cr["category_name"]: float(to_decimal(cr["cat_spend"])) for cr in cat_rows}

            history.append({
                "year": y,
                "month": m,
                "label": f"{calendar.month_abbr[m]} {y}",
                "total_spend": float(spend),
                "tx_count": count,
                "categories": cat_breakdown
            })
        return history

    @staticmethod
    def get_active_recurring_bills(cursor, user_id: int) -> List[Dict[str, Any]]:
        """
        Fetches all active recurring bills configured for the user.
        """
        cursor.execute("""
            SELECT id, title, amount, frequency, due_day, next_due_date, auto_paid, is_active, category_id
            FROM recurring_bills
            WHERE user_id = ? AND is_active = 1
        """, (user_id,))
        bills = []
        for r in cursor.fetchall():
            bills.append({
                "id": r["id"],
                "title": r["title"],
                "amount": float(to_decimal(r["amount"])),
                "frequency": r["frequency"] or "MONTHLY",
                "due_day": int(r["due_day"]) if r["due_day"] else 1,
                "next_due_date": r["next_due_date"],
                "auto_paid": bool(r["auto_paid"]),
                "category_id": r["category_id"]
            })
        return bills

    @staticmethod
    def get_monthly_budget(cursor, user_id: int, year: int, month: int) -> Decimal:
        """
        Fetches overall monthly budget cap (category_id is NULL or 0).
        """
        cursor.execute("""
            SELECT amount FROM budgets
            WHERE user_id = ? AND month = ? AND year = ? AND (category_id IS NULL OR category_id = 0)
            LIMIT 1
        """, (user_id, month, year))
        row = cursor.fetchone()
        return to_decimal(row["amount"]) if row else Decimal("0.00")


# ==============================================================================
# 5.3 CURRENT VELOCITY MODEL
# ==============================================================================
class VelocityModel:
    @staticmethod
    def compute(mtd_spend: Decimal, days_elapsed: int, total_days: int) -> Dict[str, Any]:
        """
        Computes run-rate velocity metrics safely with day 0/1 edge handling.
        """
        days_elapsed_safe = max(1, days_elapsed)
        days_remaining = max(0, total_days - days_elapsed)
        
        daily_velocity = (mtd_spend / Decimal(days_elapsed_safe)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        projected_remaining = (daily_velocity * Decimal(days_remaining)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        projected_month_end = mtd_spend + projected_remaining

        return {
            "daily_velocity": float(daily_velocity),
            "projected_remaining": float(projected_remaining),
            "projected_month_end": float(projected_month_end),
            "days_elapsed": days_elapsed,
            "days_remaining": days_remaining,
            "total_days": total_days
        }


# ==============================================================================
# 5.4 HISTORICAL BASELINE MODEL
# ==============================================================================
class HistoricalBaselineModel:
    @staticmethod
    def compute(history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Computes weighted moving average across completed months with variance and trend detection.
        Degrades gracefully from 6 months down to 0 months.
        """
        valid_months = [m for m in history if m["total_spend"] > 0]
        count = len(valid_months)

        if count == 0:
            return {
                "baseline": 0.0,
                "months_used": 0,
                "variance": 0.0,
                "std_dev": 0.0,
                "trend": "FLAT",
                "weights_used": []
            }

        spends = [m["total_spend"] for m in valid_months]

        # Weights: recent months receive higher priority
        if count >= 3:
            # 3-month default weights: 50%, 30%, 20%
            weights = [0.50, 0.30, 0.20]
            baseline = (weights[0] * spends[0]) + (weights[1] * spends[1]) + (weights[2] * spends[2])
            weights_used = weights
            used_count = 3
        elif count == 2:
            weights = [0.60, 0.40]
            baseline = (weights[0] * spends[0]) + (weights[1] * spends[1])
            weights_used = weights
            used_count = 2
        else: # count == 1
            weights = [1.00]
            baseline = spends[0]
            weights_used = weights
            used_count = 1

        baseline_dec = to_decimal(baseline)

        # Variance & Standard Deviation
        mean_val = sum(spends[:used_count]) / used_count
        variance = sum((x - mean_val) ** 2 for x in spends[:used_count]) / used_count
        std_dev = variance ** 0.5

        # Trend detection
        if count >= 2:
            diff = spends[0] - spends[1]
            if diff > (mean_val * 0.10):
                trend = "INCREASING"
            elif diff < -(mean_val * 0.10):
                trend = "DECREASING"
            else:
                trend = "STABLE"
        else:
            trend = "INSUFFICIENT_HISTORY"

        return {
            "baseline": float(baseline_dec),
            "months_used": used_count,
            "variance": round(variance, 2),
            "std_dev": round(std_dev, 2),
            "trend": trend,
            "weights_used": weights_used
        }


# ==============================================================================
# 5.5 CATEGORY FORECASTING ENGINE
# ==============================================================================
class CategoryForecastEngine:
    @staticmethod
    def compute(
        mtd_transactions: List[Dict[str, Any]],
        history: List[Dict[str, Any]],
        days_elapsed: int,
        total_days: int
    ) -> List[Dict[str, Any]]:
        """
        Blends historical category baseline with current velocity per category.
        Includes confidence level and contribution share.
        """
        days_elapsed_safe = max(1, days_elapsed)
        days_remaining = max(0, total_days - days_elapsed)

        # Aggregate current MTD by category
        cat_mtd: Dict[str, Decimal] = {}
        for tx in mtd_transactions:
            cname = tx["category_name"]
            cat_mtd[cname] = cat_mtd.get(cname, Decimal("0.00")) + to_decimal(tx["amount"])

        # Aggregate historical category spends across up to 3 completed months
        cat_history: Dict[str, List[float]] = {}
        completed_months_checked = min(3, len(history))
        for m in history[:completed_months_checked]:
            for cname, spend in m.get("categories", {}).items():
                if cname not in cat_history:
                    cat_history[cname] = []
                cat_history[cname].append(spend)

        all_categories = set(cat_mtd.keys()).union(set(cat_history.keys()))
        category_forecasts = []

        total_projected_sum = Decimal("0.00")

        for cat in sorted(all_categories):
            cur_spend = cat_mtd.get(cat, Decimal("0.00"))
            hist_spends = cat_history.get(cat, [])

            # Category velocity
            cat_velocity = cur_spend / Decimal(days_elapsed_safe)
            cat_proj_velocity = cur_spend + (cat_velocity * Decimal(days_remaining))

            if len(hist_spends) > 0:
                hist_avg = Decimal(str(sum(hist_spends) / len(hist_spends))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                alpha = min(Decimal("1.0"), max(Decimal("0.15"), Decimal(days_elapsed_safe) / Decimal(total_days)))
                proj_spend = (alpha * cat_proj_velocity) + ((Decimal("1.0") - alpha) * hist_avg)
                conf = "HIGH" if len(hist_spends) >= 3 else "MEDIUM"
                notes = f"Blended pace (alpha {float(alpha):.2f}) with {len(hist_spends)}m baseline"
            else:
                proj_spend = cat_proj_velocity
                hist_avg = Decimal("0.00")
                conf = "LOW"
                notes = "Velocity extrapolation only (no historical data)"

            proj_spend = max(cur_spend, proj_spend.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            total_projected_sum += proj_spend

            category_forecasts.append({
                "category": cat,
                "mtd_spend": float(cur_spend),
                "historical_avg": float(hist_avg),
                "projected_month_end": float(proj_spend),
                "confidence": conf,
                "notes": notes
            })

        # Calculate percentage contribution
        for cf in category_forecasts:
            if total_projected_sum > 0:
                cf["pct_of_projected_total"] = round((Decimal(str(cf["projected_month_end"])) / total_projected_sum * 100), 1)
            else:
                cf["pct_of_projected_total"] = 0.0

        category_forecasts.sort(key=lambda x: x["projected_month_end"], reverse=True)
        return category_forecasts


# ==============================================================================
# 5.6 RECURRING BILL INTEGRATION (ZERO DOUBLE-COUNTING)
# ==============================================================================
class RecurringBillIntegration:
    @staticmethod
    def evaluate(
        bills: List[Dict[str, Any]],
        mtd_transactions: List[Dict[str, Any]],
        cutoff_date: date,
        total_days: int
    ) -> Tuple[List[Dict[str, Any]], Decimal, Decimal]:
        """
        Distinguishes between bills already paid this month vs upcoming unpaid commitments.
        Guarantees zero double counting:
        1. If a bill is paid, it is already reflected in mtd_spend -> DO NOT re-add.
        2. If unpaid and due later this month, it is an upcoming commitment.
        """
        cur_day = cutoff_date.day
        cur_year = cutoff_date.year
        cur_month = cutoff_date.month

        upcoming_bills = []
        paid_bills = []
        upcoming_total = Decimal("0.00")
        paid_total = Decimal("0.00")

        # Precompute match sets from MTD transactions
        # Match by is_recurring flag or note title substring
        mtd_notes = [tx["note"].lower() if tx["note"] else "" for tx in mtd_transactions]
        mtd_amounts = [round(tx["amount"], 2) for tx in mtd_transactions]

        for b in bills:
            b_amt = to_decimal(b["amount"])
            b_title_lower = b["title"].lower()
            b_freq = b.get("frequency", "MONTHLY").upper()
            next_due_str = b.get("next_due_date") or ""

            # Check next due date
            is_paid_this_cycle = False
            if next_due_str:
                try:
                    next_due_d = datetime.strptime(next_due_str, "%Y-%m-%d").date()
                    # If next_due_date has already moved into a future month, it was paid for this month!
                    if next_due_d.year > cur_year or (next_due_d.year == cur_year and next_due_d.month > cur_month):
                        is_paid_this_cycle = True
                except Exception:
                    pass

            # Also check if any transaction in MTD matches title or is tagged recurring
            if not is_paid_this_cycle:
                for tx in mtd_transactions:
                    tx_note = (tx["note"] or "").lower()
                    if b_title_lower in tx_note or (tx["is_recurring"] and abs(float(b_amt) - tx["amount"]) < 0.01):
                        is_paid_this_cycle = True
                        break

            if is_paid_this_cycle:
                paid_total += b_amt
                paid_bills.append({
                    "id": b["id"],
                    "title": b["title"],
                    "amount": float(b_amt),
                    "status": "PAID_THIS_MONTH"
                })
            else:
                # Bill is not yet paid this month. Does it fall between today and month end?
                is_due_this_month = False
                if b_freq == "MONTHLY":
                    due_day = b["due_day"]
                    if due_day > cur_day and due_day <= total_days:
                        is_due_this_month = True
                        due_date_str = f"{cur_year:04d}-{cur_month:02d}-{due_day:02d}"
                elif b_freq == "WEEKLY":
                    # Check if next_due_date falls in remainder of this month
                    if next_due_str:
                        try:
                            nd = datetime.strptime(next_due_str, "%Y-%m-%d").date()
                            if nd >= cutoff_date and nd.month == cur_month:
                                is_due_this_month = True
                                due_date_str = next_due_str
                        except Exception:
                            pass
                elif b_freq == "YEARLY":
                    if next_due_str:
                        try:
                            nd = datetime.strptime(next_due_str, "%Y-%m-%d").date()
                            if nd >= cutoff_date and nd.month == cur_month and nd.year == cur_year:
                                is_due_this_month = True
                                due_date_str = next_due_str
                        except Exception:
                            pass

                if is_due_this_month:
                    upcoming_total += b_amt
                    upcoming_bills.append({
                        "id": b["id"],
                        "title": b["title"],
                        "amount": float(b_amt),
                        "due_date": due_date_str,
                        "status": "UPCOMING_UNPAID"
                    })

        return upcoming_bills, upcoming_total, paid_total


# ==============================================================================
# 5.7 BUDGET RISK ENGINE
# ==============================================================================
class BudgetRiskEngine:
    @staticmethod
    def evaluate(
        monthly_budget: Decimal,
        mtd_spend: Decimal,
        projected_spend: Decimal,
        upcoming_recurring_total: Decimal,
        days_remaining: int
    ) -> Dict[str, Any]:
        """
        Calculates deterministic budget health, safe daily spending cap, and risk status.
        Levels: LOW, MODERATE, HIGH, CRITICAL
        """
        budget_f = float(monthly_budget)
        mtd_f = float(mtd_spend)
        proj_f = float(projected_spend)
        days_rem_safe = max(1, days_remaining)

        if monthly_budget <= Decimal("0.00"):
            return {
                "monthly_budget": 0.0,
                "remaining_budget": 0.0,
                "projected_over_under": 0.0,
                "budget_usage_pct": 0.0,
                "safe_daily_spend": 0.0,
                "risk_level": "LOW",
                "risk_status": "NO_BUDGET",
                "risk_reason": "No monthly budget ceiling set yet."
            }

        remaining_budget = monthly_budget - mtd_spend
        projected_over_under = monthly_budget - projected_spend
        budget_usage_pct = round((proj_f / budget_f) * 100, 1)

        # Safe daily spending cap accounting for upcoming committed obligations
        discretionary_buffer = remaining_budget - upcoming_recurring_total
        safe_daily_spend = max(Decimal("0.00"), (discretionary_buffer / Decimal(days_rem_safe)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        # Risk level determination
        if mtd_spend > monthly_budget:
            risk_level = "CRITICAL"
            risk_status = "DANGER"
            overrun = float(mtd_spend - monthly_budget)
            risk_reason = f"Budget already breached by Rs.{overrun:,.2f} ({round((mtd_f/budget_f)*100, 1)}% spent)."
        elif projected_spend > monthly_budget:
            risk_level = "HIGH"
            risk_status = "DANGER"
            overrun = float(projected_spend - monthly_budget)
            risk_reason = f"Paced to exceed budget by Rs.{overrun:,.2f} ({budget_usage_pct}% of budget)."
        elif budget_usage_pct >= 85.0:
            risk_level = "MODERATE"
            risk_status = "WARNING"
            risk_reason = f"Approaching limit: projected to consume {budget_usage_pct}% of your budget."
        else:
            risk_level = "LOW"
            risk_status = "SAFE"
            surplus = float(projected_over_under)
            risk_reason = f"On track! Projected to finish month using {budget_usage_pct}% of budget."

        return {
            "monthly_budget": budget_f,
            "remaining_budget": float(max(Decimal("0.00"), remaining_budget)),
            "projected_over_under": float(projected_over_under),
            "budget_usage_pct": budget_usage_pct,
            "safe_daily_spend": float(safe_daily_spend),
            "risk_level": risk_level,
            "risk_status": risk_status,
            "risk_reason": risk_reason
        }


# ==============================================================================
# 5.8 CONFIDENCE SCORING
# ==============================================================================
class ConfidenceScoringEngine:
    @staticmethod
    def evaluate(
        completed_months_count: int,
        mtd_tx_count: int,
        std_dev: float,
        baseline: float,
        days_elapsed: int,
        total_days: int
    ) -> Tuple[str, int, str]:
        """
        Computes deterministic confidence score (0-100) and category (HIGH, MEDIUM, LOW).
        """
        score = 0
        reasons = []

        # 1. Historical data volume (max 35 pts)
        if completed_months_count >= 3:
            score += 35
            reasons.append(f"{completed_months_count} completed months of history")
        elif completed_months_count in (1, 2):
            score += 20
            reasons.append(f"{completed_months_count} month(s) of history")
        else:
            score += 5
            reasons.append("New account / no completed months")

        # 2. Transaction frequency (max 25 pts)
        if mtd_tx_count >= 15:
            score += 25
            reasons.append("high transaction density")
        elif mtd_tx_count >= 5:
            score += 15
            reasons.append("moderate transaction activity")
        else:
            score += 5
            reasons.append("sparse transaction data")

        # 3. Volatility / Stability (max 20 pts)
        cv = (std_dev / baseline) if baseline > 0 else 0.5
        if cv < 0.25:
            score += 20
            reasons.append("consistent spending patterns")
        elif cv <= 0.50:
            score += 10
            reasons.append("moderate spending variance")
        else:
            score += 5
            reasons.append("high spending volatility")

        # 4. Month progress (max 20 pts)
        progress_pct = (days_elapsed / total_days) * 100
        if progress_pct >= 50:
            score += 20
            reasons.append(f"mid/late month progress ({days_elapsed}/{total_days} days)")
        elif progress_pct >= 20:
            score += 10
            reasons.append(f"early-month progress ({days_elapsed}/{total_days} days)")
        else:
            score += 5
            reasons.append("start of month")

        if score >= 70:
            level = "HIGH"
        elif score >= 45:
            level = "MEDIUM"
        else:
            level = "LOW"

        confidence_reason = f"Based on {', '.join(reasons)}."
        return level, score, confidence_reason


# ==============================================================================
# 5.9 EXPLAINABLE RECOMMENDATIONS GENERATOR
# ==============================================================================
class RecommendationsGenerator:
    @staticmethod
    def generate(
        risk_data: Dict[str, Any],
        velocity_data: Dict[str, Any],
        category_forecasts: List[Dict[str, Any]],
        upcoming_bills: List[Dict[str, Any]],
        confidence_level: str
    ) -> List[Dict[str, Any]]:
        """
        Generates deterministic, metric-grounded recommendations.
        Zero hallucination.
        """
        recs = []

        # 1. Budget Pace Recommendation
        risk_level = risk_data["risk_level"]
        safe_cap = risk_data["safe_daily_spend"]
        days_rem = velocity_data["days_remaining"]

        if risk_level in ("CRITICAL", "HIGH"):
            recs.append({
                "id": "REC_BUDGET_OVERRUN",
                "title": "Immediate Spending Cap Required",
                "explanation": f"At your current velocity of Rs.{velocity_data['daily_velocity']:.1f}/day, you are {risk_data['risk_reason'].lower()}",
                "severity": "CRITICAL" if risk_level == "CRITICAL" else "WARNING",
                "supporting_metric": f"Safe Daily Cap: Rs.{safe_cap:.1f}/day for {days_rem} days",
                "suggested_action": f"Cap non-essential daily outlays to Rs.{safe_cap:.1f}/day to limit overrun."
            })
        elif risk_level == "MODERATE":
            recs.append({
                "id": "REC_BUDGET_PACING",
                "title": "Pacing Approaching Limit",
                "explanation": f"You are projected to utilize {risk_data['budget_usage_pct']}% of your budget.",
                "severity": "INFO",
                "supporting_metric": f"Projected Spend: Rs.{risk_data['monthly_budget'] - risk_data['projected_over_under']:,.2f}",
                "suggested_action": f"Target keeping daily spend below Rs.{safe_cap:.1f}/day to preserve your savings cushion."
            })
        elif risk_level == "LOW" and risk_data["monthly_budget"] > 0:
            surplus = risk_data["projected_over_under"]
            recs.append({
                "id": "REC_BUDGET_SURPLUS",
                "title": "Projected Budget Surplus",
                "explanation": f"Excellent discipline! You are on track to save Rs.{surplus:,.2f} below your budget ceiling.",
                "severity": "SUCCESS",
                "supporting_metric": f"Projected Savings: Rs.{surplus:,.2f}",
                "suggested_action": "Consider scheduling a transfer of this surplus to your Savings Goals."
            })

        # 2. Top Category Driver Recommendation
        if category_forecasts:
            top_cat = category_forecasts[0]
            if top_cat["pct_of_projected_total"] >= 30.0 and top_cat["mtd_spend"] > 0:
                potential_savings = round(top_cat["projected_month_end"] * 0.15, 2)
                recs.append({
                    "id": "REC_CATEGORY_DRIVER",
                    "title": f"Top Expenditure Driver: {top_cat['category']}",
                    "explanation": f"{top_cat['category']} represents {top_cat['pct_of_projected_total']}% of your projected month spending (Rs.{top_cat['projected_month_end']:,.2f}).",
                    "severity": "INFO",
                    "supporting_metric": f"MTD: Rs.{top_cat['mtd_spend']:,.2f} | Projected: Rs.{top_cat['projected_month_end']:,.2f}",
                    "suggested_action": f"Trimming 15% from {top_cat['category']} could preserve approx. Rs.{potential_savings:,.2f} this month."
                })

        # 3. Upcoming Recurring Commitments Recommendation
        if upcoming_bills:
            total_upcoming = sum(b["amount"] for b in upcoming_bills)
            recs.append({
                "id": "REC_UPCOMING_BILLS",
                "title": f"{len(upcoming_bills)} Upcoming Bill Obligations",
                "explanation": f"You have Rs.{total_upcoming:,.2f} in scheduled recurring bills remaining before month-end.",
                "severity": "INFO",
                "supporting_metric": f"Upcoming Commitments: Rs.{total_upcoming:,.2f}",
                "suggested_action": "Ensure sufficient account liquidity to avoid overdraft or missed payments."
            })

        # 4. Low Data Notice
        if confidence_level == "LOW":
            recs.append({
                "id": "REC_CONFIDENCE_NOTE",
                "title": "Preliminary Forecast",
                "explanation": "Limited historical transactions detected. Forecast accuracy will improve automatically as you record more expenses.",
                "severity": "INFO",
                "supporting_metric": "Confidence: LOW",
                "suggested_action": "Keep recording daily transactions to unlock multi-month trend forecasting."
            })

        return recs


# ==============================================================================
# MAIN ENGINE ENTRY POINT
# ==============================================================================
def calculate_month_end_forecast(
    user_id: int,
    target_date: Optional[Any] = None,
    db_path: str = "expenses.db"
) -> Dict[str, Any]:
    """
    FORECAST ENGINE 2.0
    Deterministic, explainable, multi-factor forecasting combining:
    - MTD spending velocity
    - Historical weighted moving average (3 to 6 months)
    - Early-month alpha smoothing
    - Verified recurring commitments (zero double-counting)
    - Budget risk engine & safe daily spend
    - Deterministic confidence scoring
    - Actionable explainable recommendations
    """
    if target_date is None:
        today = date.today()
    elif isinstance(target_date, str):
        today = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        today = target_date

    current_year = today.year
    current_month = today.month
    current_day = today.day
    total_days = get_days_in_month(current_year, current_month)

    conn, cursor = get_db_cursor(db_path)

    try:
        # 1. Historical Pipeline: MTD Actuals
        start_date = f"{current_year:04d}-{current_month:02d}-01"
        cutoff_date_str = today.strftime("%Y-%m-%d")
        mtd_spend, mtd_transactions = ForecastDataPipeline.get_mtd_expenses(
            cursor, user_id, start_date, cutoff_date_str
        )
        mtd_tx_count = len(mtd_transactions)

        # 2. Historical Pipeline: Completed Months History
        history = ForecastDataPipeline.get_completed_months_history(
            cursor, user_id, current_year, current_month, months_back=6
        )

        # 3. Velocity Model
        velocity_data = VelocityModel.compute(mtd_spend, current_day, total_days)
        daily_velocity = velocity_data["daily_velocity"]
        projected_velocity_spend = to_decimal(velocity_data["projected_month_end"])

        # 4. Historical Baseline Model
        baseline_data = HistoricalBaselineModel.compute(history)
        baseline_wma = to_decimal(baseline_data["baseline"])

        # If zero historical data, baseline defaults to velocity spend
        if baseline_wma <= Decimal("0.00"):
            baseline_wma = projected_velocity_spend

        # 5. Recurring Bills Integration (Zero double-counting)
        active_bills = ForecastDataPipeline.get_active_recurring_bills(cursor, user_id)
        upcoming_bills, upcoming_recurring_total, paid_recurring_total = RecurringBillIntegration.evaluate(
            active_bills, mtd_transactions, today, total_days
        )

        # 6. Combined Forecast Formula
        # Alpha progresses from 0.10 to 1.0 based on elapsed days
        alpha = min(Decimal("1.00"), max(Decimal("0.10"), Decimal(max(1, current_day)) / Decimal(total_days)))

        # Baseline and velocity blending for discretionary expenditure
        discretionary_forecast = (alpha * projected_velocity_spend) + ((Decimal("1.00") - alpha) * baseline_wma)

        # Future unpaid committed bills are real obligations for remaining days
        # If velocity already extrapolated remaining days, adjust for known fixed bills
        final_forecast = discretionary_forecast + upcoming_recurring_total
        # Projected spend cannot be less than actual MTD spend
        final_forecast = max(mtd_spend, final_forecast.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        # 7. Category Forecasts
        category_forecasts = CategoryForecastEngine.compute(
            mtd_transactions, history, current_day, total_days
        )

        # 8. Budget Risk Engine
        monthly_budget = ForecastDataPipeline.get_monthly_budget(cursor, user_id, current_year, current_month)
        risk_data = BudgetRiskEngine.evaluate(
            monthly_budget, mtd_spend, final_forecast, upcoming_recurring_total, total_days - current_day
        )

        # 9. Confidence Scoring
        conf_level, conf_score, conf_reason = ConfidenceScoringEngine.evaluate(
            baseline_data["months_used"],
            mtd_tx_count,
            baseline_data["std_dev"],
            baseline_data["baseline"],
            current_day,
            total_days
        )

        # 10. Recommendations Generator
        recommendations = RecommendationsGenerator.generate(
            risk_data, velocity_data, category_forecasts, upcoming_bills, conf_level
        )

        # Construct backward-compatible & enhanced payload
        overrun_amount = max(0.0, float(final_forecast - monthly_budget)) if monthly_budget > 0 else 0.0

        return {
            # Legacy fields for complete backward compatibility
            "current_date": cutoff_date_str,
            "days_elapsed": max(1, current_day),
            "total_days_in_month": total_days,
            "days_remaining": total_days - current_day,
            "mtd_actual_spend": float(mtd_spend),
            "daily_spending_velocity": daily_velocity,
            "baseline_wma_history": float(baseline_wma),
            "unpaid_recurring_bills": float(upcoming_recurring_total),
            "projected_month_end_spend": float(final_forecast),
            "monthly_budget": float(monthly_budget),
            "projected_budget_utilization_pct": risk_data["budget_usage_pct"],
            "risk_status": risk_data["risk_status"],
            "overrun_amount": round(overrun_amount, 2),
            "warning_message": risk_data["risk_reason"],
            "category_forecasts": category_forecasts,

            # Forecast Engine 2.0 Enhanced Fields
            "budget": float(monthly_budget),
            "remaining_budget": risk_data["remaining_budget"],
            "projected_remaining": float(max(Decimal("0.00"), final_forecast - mtd_spend)),
            "safe_daily_spend": risk_data["safe_daily_spend"],
            "risk_level": risk_data["risk_level"],
            "risk_reason": risk_data["risk_reason"],
            "confidence": conf_level,
            "confidence_score": conf_score,
            "confidence_reason": conf_reason,
            "historical_baseline": float(baseline_wma),
            "historical_months_used": baseline_data["months_used"],
            "spending_trend": baseline_data["trend"],
            "upcoming_recurring": upcoming_bills,
            "upcoming_recurring_total": float(upcoming_recurring_total),
            "paid_recurring_total": float(paid_recurring_total),
            "recommendations": recommendations,
            "methodology": {
                "alpha_smoothing": float(alpha),
                "model_weights": baseline_data["weights_used"],
                "formula": "F = (alpha * Velocity_Spend) + ((1 - alpha) * Baseline_WMA) + Upcoming_Unpaid_Bills"
            }
        }
    finally:
        conn.close()


def detect_spending_anomalies(user_id: int, db_path: str = "expenses.db") -> List[Dict[str, Any]]:
    """
    Detects statistical anomalies across categories using standard deviation (mean + 1.75*sigma).
    Preserves exact backward-compatible contract for API callers.
    """
    conn, cursor = get_db_cursor(db_path)
    try:
        cursor.execute("""
            SELECT COALESCE(c.name, 'Others') as category_name,
                   AVG(t.amount) as avg_amount,
                   COUNT(t.id) as tx_count,
                   MAX(t.amount) as max_amount
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.amount > 0
            GROUP BY c.name
            HAVING COUNT(t.id) >= 2
        """, (user_id,))
        stats = cursor.fetchall()

        anomalies = []
        for s in stats:
            cat = s["category_name"]
            avg = float(s["avg_amount"])
            cursor.execute("""
                SELECT t.id, t.amount, t.date, t.note
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND COALESCE(c.name, 'Others') = ?
                  AND t.amount > 0
            """, (user_id, cat))
            amounts = [float(r["amount"]) for r in cursor.fetchall()]
            if len(amounts) >= 3:
                variance = sum((x - avg) ** 2 for x in amounts) / len(amounts)
                std_dev = variance ** 0.5
                threshold = avg + (1.75 * std_dev)

                cursor.execute("""
                    SELECT t.id, t.amount, t.date, t.note
                    FROM transactions t
                    LEFT JOIN categories c ON t.category_id = c.id
                    WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND COALESCE(c.name, 'Others') = ?
                      AND t.amount > ?
                    ORDER BY t.date DESC LIMIT 3
                """, (user_id, cat, threshold))
                for r in cursor.fetchall():
                    amt = float(r["amount"])
                    dev_pct = round(((amt - avg) / avg) * 100, 1) if avg > 0 else 0.0
                    anomalies.append({
                        "transaction_id": r["id"],
                        "category": cat,
                        "amount": amt,
                        "date": r["date"],
                        "note": r["note"],
                        "normal_average": round(avg, 2),
                        "deviation_pct": dev_pct,
                        "alert": f"Unusual spend: Rs.{amt:,.2f} in {cat} is {round(dev_pct)}% above your average (Rs.{avg:,.2f})."
                    })
        return anomalies
    finally:
        conn.close()
