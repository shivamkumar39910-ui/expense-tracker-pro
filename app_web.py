from flask import Flask, render_template, request, redirect, session, flash, abort
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import threading
import webbrowser
import sqlite3
import math
import secrets
import os
import re
from api_v1 import api_v1

# ==================================================
# Phase 7 — Security Hardening Setup
# ==================================================

app = Flask(__name__)
CORS(app)
app.register_blueprint(api_v1, url_prefix='/api/v1')
app.secret_key = os.environ.get("SECRET_KEY", "expense_tracker_secure_production_secret_key_2026")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# CSRF Protection Helpers
def get_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]

app.jinja_env.globals["csrf_token"] = get_csrf_token

def validate_csrf():
    token = request.form.get("csrf_token")
    return token and token == session.get("csrf_token")

# Validation Helpers
def is_valid_email(email):
    return re.match(r"^[^@]+@[^@]+\.[^@]+$", email) is not None

def is_valid_password(password):
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return False, "Password must contain both letters and numbers."
    return True, ""

# Login Rate Limiting (Prevent Brute Force)
LOGIN_ATTEMPTS = {}

def is_rate_limited(ip):
    attempts = LOGIN_ATTEMPTS.get(ip, [])
    now = datetime.now().timestamp()
    recent = [t for t in attempts if now - t < 900]
    LOGIN_ATTEMPTS[ip] = recent
    return len(recent) >= 5

def record_failed_login(ip):
    now = datetime.now().timestamp()
    attempts = LOGIN_ATTEMPTS.get(ip, [])
    attempts.append(now)
    LOGIN_ATTEMPTS[ip] = attempts

# ==================================================
# Phase 6 — AI Financial Mentor Engine
# ==================================================

def generate_ai_recommendations(total, spent, budget, usage_percentage, highest_category, highest_amount, mom_change, tx_count, avg_transaction, daily_avg):
    summary = f"Executive Summary: Total spending is ₹{total:,.2f} across {tx_count} transactions (Avg ₹{avg_transaction:,.2f}/tx). "
    if budget > 0:
        summary += f"Monthly budget utilization is {usage_percentage}% ({'Exceeded' if spent > budget else 'Under Budget'}). "
    if highest_category != "None":
        summary += f"Primary spend concentration is in '{highest_category.title()}' (₹{highest_amount:,.2f})."

    recommendations = []
    if total > 0 and highest_category != "None":
        pct = (highest_amount / total) * 100
        if pct >= 35:
            rec_save = round(highest_amount * 0.15, 2)
            recommendations.append({
                "title": f"Smart Reallocation: {highest_category.title()}",
                "tag": "Budget Optimization",
                "text": f"'{highest_category.title()}' represents {pct:.1f}% of total expenses. Reducing non-essentials by 15% would save ~₹{rec_save:,.2f} this month."
            })

    if total > 0:
        suggested_budget = round(total * 1.10, -2)
        recommendations.append({
            "title": "Smart Recommended Budget Target",
            "tag": "Personalized Target",
            "text": f"Based on your daily average spending of ₹{daily_avg:,.2f}/day, a recommended budget cap is ₹{suggested_budget:,.2f}/month."
        })

    if mom_change > 10:
        recommendations.append({
            "title": "Spending Surge Explanation",
            "tag": "Trend Insight",
            "text": f"Spending is pacing {mom_change}% higher than last month. Review category concentrations to maintain budget alignment."
        })
    elif mom_change < -5:
        recommendations.append({
            "title": "Positive Momentum Explanation",
            "tag": "Savings Victory",
            "text": f"Disciplined spending reduced costs by {abs(mom_change)}% compared to last month. Keep up the good work!"
        })

    return {
        "summary": summary,
        "recommendations": recommendations
    }

def login_required():
    if "user_id" not in session:
        return False
    return True

def get_connection():
    import db_engine
    return db_engine.get_db_connection()


# Import database initializer to run safe index migrations on start
from database import create_database
try:
    create_database()
except Exception as e:
    pass

@app.errorhandler(404)
def not_found(e):
    return render_template("base.html"), 404

@app.errorhandler(500)
def server_error(e):
    return "An internal server error occurred. Please try again later.", 500

# ==================================================
# Mobile App Route (Expense Tracker Pro 2.0)
# ==================================================

@app.route("/mobile")
@app.route("/app")
def mobile_app():
    return render_template("mobile_app.html")

# ==================================================
# Legacy Web Prototype Home Route
# ==================================================

@app.route("/")
def home():
    return render_template("mobile_app.html")

# ==================================================
# Authentication Routes
# ==================================================

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Password Match Check
        if password != confirm_password:
            return "Passwords do not match."

        hashed_password = generate_password_hash(password)

        # Database Connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        )

        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return "Email already registered."

        # Insert New User
        cursor.execute("""
            INSERT INTO users (name, email, password)
            VALUES (?, ?, ?)
        """, (name, email, hashed_password))

        conn.commit()

        # Get New User ID
        user_id = cursor.lastrowid

        # Create Session
        session["user_id"] = user_id
        session["user_name"] = name

        conn.close()

        # Redirect to Home Page
        return redirect("/")

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()

        password = request.form["password"]

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, email, password
            FROM users
            WHERE email = ?
        """, (email,))

        user = cursor.fetchone()

        conn.close()

        # Email Not Found
        if user is None:
            return "Email not registered."

        # Password Check
        if not check_password_hash(user[3], password):
            return "Incorrect password."

        # Login Successful
        session["user_id"] = user[0]
        session["user_name"] = user[1]

        return redirect("/")

    return render_template("login.html")

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")

@app.route("/profile")
def profile():

    if not login_required():
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    user_id = session["user_id"]

    cursor.execute("""
        SELECT name, email
        FROM users
        WHERE id = ?
    """, (user_id,))

    user = cursor.fetchone()

    cursor.execute("""
        SELECT SUM(amount)
        FROM expenses
        WHERE user_id = ?
    """, (user_id,))

    total_expense = cursor.fetchone()[0]

    if total_expense is None:
        total_expense = 0

    cursor.execute("""
        SELECT COUNT(*)
        FROM expenses
        WHERE user_id = ?
    """, (user_id,))

    total_transactions = cursor.fetchone()[0]    

    conn.close()

    return render_template(
    "profile.html",
    user=user,
    total_expense=total_expense,
    total_transactions=total_transactions
)

@app.route("/set-budget", methods=["GET", "POST"])
def set_budget():

    if not login_required():
        return redirect("/login")

    if request.method == "POST":

        budget_amount = request.form.get("budget")

        if not budget_amount:
            flash("❌ Please enter a budget amount.", "error")
            return redirect("/set-budget")

        try:
            budget_amount = float(budget_amount)

            if budget_amount <= 0:
                flash("❌ Budget must be greater than 0.", "error")
                return redirect("/set-budget")

        except ValueError:
            flash("❌ Please enter a valid amount.", "error")
            return redirect("/set-budget")

        user_id = session["user_id"]

        today = datetime.now()
        current_month = today.month
        current_year = today.year

        conn = get_connection()
        cursor = conn.cursor()

        # Check if budget already exists for this month
        cursor.execute("""
            SELECT id
            FROM budgets
            WHERE user_id = ?
            AND month = ?
            AND year = ?
        """, (user_id, current_month, current_year))

        existing_budget = cursor.fetchone()

        if existing_budget:

            # Update existing budget
            cursor.execute("""
                UPDATE budgets
                SET amount = ?
                WHERE id = ?
            """, (budget_amount, existing_budget[0]))

        else:

            # Create new budget
            cursor.execute("""
                INSERT INTO budgets (user_id, month, year, amount)
                VALUES (?, ?, ?, ?)
            """, (user_id, current_month, current_year, budget_amount))

        conn.commit()
        conn.close()

        flash("✅ Budget saved successfully!", "success")
        return redirect("/analysis")

    return render_template("set_budget.html")

@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():

    if not login_required():
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    user_id = session["user_id"]

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()

        # Check if email already belongs to another user
        cursor.execute("""
            SELECT id
            FROM users
            WHERE email = ?
            AND id != ?
        """, (email, user_id))

        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return "Email already registered."

        # Update current user's profile
        cursor.execute("""
            UPDATE users
            SET name = ?, email = ?
            WHERE id = ?
        """, (name, email, user_id))

        conn.commit()
        conn.close()

        return redirect("/profile")

    # GET Request
    cursor.execute("""
        SELECT name, email
        FROM users
        WHERE id = ?
    """, (user_id,))

    user = cursor.fetchone()

    conn.close()

    return render_template("edit_profile.html", user=user)

@app.route("/change-password", methods=["GET", "POST"])
def change_password():

    if not login_required():
        return redirect("/login")

    if request.method == "POST":

        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if new_password != confirm_password:
            return "New passwords do not match."

        conn = get_connection()
        cursor = conn.cursor()

        user_id = session["user_id"]

        cursor.execute("""
            SELECT password
            FROM users
            WHERE id = ?
        """, (user_id,))

        stored_password = cursor.fetchone()[0]

        if not check_password_hash(stored_password, current_password):
            conn.close()
            return "Current password is incorrect."

        hashed_password = generate_password_hash(new_password)

        cursor.execute("""
            UPDATE users
            SET password = ?
            WHERE id = ?
        """, (hashed_password, user_id))

        conn.commit()
        conn.close()

        return redirect("/profile")

    return render_template("change_password.html")

# ==================================================
# Expense Routes
# ==================================================

@app.route("/add", methods=["GET", "POST"])
def add():

    if not login_required():
        return redirect("/login")

    if request.method == "POST":

        user_id = session["user_id"]

        category = request.form["category"].lower().strip()
        subcategory = request.form["subcategory"].lower().strip()
        amount = request.form["amount"]

        date = datetime.now().strftime("%Y-%m-%d")
        
        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO expenses
            (user_id, date, category, subcategory, amount)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            date,
            category,
            subcategory,
            amount
        ))

        conn.commit()

        conn.close()

        return render_template("add.html", msg="Expense Added ✅")

    return render_template("add.html")

# ==================================================
# Phase 4 — Statistical Anomaly Detection Engine
# ==================================================

def detect_anomalies(transactions):
    anomalies = []
    if len(transactions) < 3:
        return anomalies

    amounts = [t["amount"] for t in transactions]
    mean_val = sum(amounts) / len(amounts)

    # Variance and Standard Deviation
    variance = sum((x - mean_val) ** 2 for x in amounts) / len(amounts)
    std_dev = math.sqrt(variance)

    # Threshold: Mean + 2 * StdDev (or 1.8 * Mean if std_dev is small)
    threshold = mean_val + (2.0 * std_dev if std_dev > 0 else 1.5 * mean_val)

    for t in transactions:
        if t["amount"] > threshold and t["amount"] > 300:
            anomalies.append({
                "id": t["id"],
                "date": t["date"],
                "category": t["category"],
                "subcategory": t["subcategory"],
                "amount": t["amount"],
                "mean": round(mean_val, 2),
                "threshold": round(threshold, 2),
                "reason": f"Spike of ₹{t['amount']:,.2f} is significantly above average transaction size (₹{mean_val:,.2f})."
            })

    anomalies.sort(key=lambda x: x["amount"], reverse=True)
    return anomalies[:5]

# ==================================================
# Phase 5 — Expense Prediction & Forecasting Model
# ==================================================

def forecast_next_month_expense(monthly_total, current_spent):
    months = list(monthly_total.values())
    if not months:
        estimate = float(current_spent) if current_spent > 0 else 0.0
        return {
            "forecast": round(estimate, 2),
            "lower_bound": round(estimate * 0.85, 2),
            "upper_bound": round(estimate * 1.15, 2),
            "trend": "Stable",
            "model_type": "Baseline Estimate",
            "confidence": "Low (Under 2 Months History)"
        }

    k = len(months)
    if k >= 3:
        wma = (0.5 * months[-1]) + (0.3 * months[-2]) + (0.2 * months[-3])
        trend_delta = months[-1] - months[-2]
        forecast_raw = max(0, wma + (0.4 * trend_delta))
        trend_direction = "Increasing" if trend_delta > 0 else ("Decreasing" if trend_delta < 0 else "Stable")
        confidence = "High (3-Month WMA)"
    elif k == 2:
        wma = (0.6 * months[-1]) + (0.4 * months[-2])
        trend_delta = months[-1] - months[-2]
        forecast_raw = max(0, wma + (0.3 * trend_delta))
        trend_direction = "Increasing" if trend_delta > 0 else "Decreasing"
        confidence = "Medium (2-Month WMA)"
    else:
        forecast_raw = months[0]
        trend_direction = "Stable"
        confidence = "Moderate (1-Month Base)"

    forecast = round(forecast_raw, 2)
    return {
        "forecast": forecast,
        "lower_bound": round(forecast * 0.85, 2),
        "upper_bound": round(forecast * 1.15, 2),
        "trend": trend_direction,
        "model_type": "Weighted Moving Average with Trend Damping",
        "confidence": confidence
    }

@app.route("/analysis")
def analysis():

    if not login_required():
        return redirect("/login")

    conn = get_connection()

    cursor = conn.cursor()

    user_id = session["user_id"]

    today = datetime.now()

    current_month = today.month
    current_year = today.year

    cursor.execute("""
        SELECT id, date, category, subcategory, amount
        FROM expenses
        WHERE user_id = ?
    """, (user_id,))

    rows = cursor.fetchall()

    # Current Month Expense
    cursor.execute("""
        SELECT SUM(amount)
        FROM expenses
        WHERE user_id = ?
        AND CAST(strftime('%m', date) AS INTEGER)=?
        AND CAST(strftime('%Y', date) AS INTEGER)=?
    """,(user_id,current_month,current_year))

    spent = cursor.fetchone()[0]

    if spent is None:
        spent = 0.0

    # Previous Month Expense for MoM Comparison
    if current_month == 1:
        prev_month = 12
        prev_year = current_year - 1
    else:
        prev_month = current_month - 1
        prev_year = current_year

    cursor.execute("""
        SELECT SUM(amount)
        FROM expenses
        WHERE user_id = ?
        AND CAST(strftime('%m', date) AS INTEGER)=?
        AND CAST(strftime('%Y', date) AS INTEGER)=?
    """, (user_id, prev_month, prev_year))

    prev_month_spent = cursor.fetchone()[0]
    if prev_month_spent is None:
        prev_month_spent = 0.0

    if prev_month_spent > 0:
        mom_change = round(((spent - prev_month_spent) / prev_month_spent) * 100, 1)
    else:
        mom_change = 0.0


# Budget
    cursor.execute("""
        SELECT amount
        FROM budgets
        WHERE user_id=?
        AND month=?
        AND year=?
    """,(user_id,current_month,current_year))

    budget_row = cursor.fetchone()

    if budget_row:
        budget = budget_row[0]
    else:
        budget = 0


    remaining = budget - spent
    if budget > 0:
        usage_percentage = round((spent / budget) * 100, 1)
    else:
        usage_percentage = 0

    if budget == 0:
        status = "No Budget"

    elif spent > budget:
        status = "Exceeded"

    else:
        status = "Under Budget"


        print("----------------")
        print("Budget :",budget)
        print("Spent :",spent)
        print("Remaining :",remaining)
        print("Status :",status)
        print("----------------")

    conn.close()

    data = []
    transactions = []

    category_total = {}
    monthly_total = {}

    all_categories = set()
    all_dates = set()

    for row in rows:

        expense_id = row[0]
        date = row[1]
        category = row[2]
        subcategory = row[3]
        amount = row[4]

        data.append({
            "id": expense_id,
            "date": date,
            "category": category,
            "subcategory": subcategory,
            "amount": amount
        })

        transactions.append({
            "id": expense_id,
            "date": date,
            "category": category.title(),
            "subcategory": subcategory.title(),
            "amount": amount
        })

        category_total[category] = category_total.get(category, 0) + amount

        all_categories.add(category.title())
        all_dates.add(date)

        date_obj = datetime.strptime(date, "%Y-%m-%d")

        month = date_obj.strftime("%b %Y")
        monthly_total[month] = monthly_total.get(month, 0) + amount
    transactions.reverse()
    # Total Expense
    total = sum(item["amount"] for item in data)

    # Ascending Order (Small → Large)
    sorted_data = dict(
        sorted(
            category_total.items(),
            key=lambda x: x[1]
        )
    )

    category_count = len(category_total)

    if category_total:
        highest_category = max(category_total, key=category_total.get)
        highest_amount = category_total[highest_category]
    else:
        highest_category = "None"
        highest_amount = 0

    tx_count = len(transactions)
    avg_transaction = round(total / tx_count, 2) if tx_count > 0 else 0
    unique_dates_count = len(all_dates)
    daily_avg = round(total / unique_dates_count, 2) if unique_dates_count > 0 else 0
    amounts = [t["amount"] for t in transactions]
    max_transaction = max(amounts) if amounts else 0
    min_transaction = min(amounts) if amounts else 0

    # Phase 3 Smart Insights Engine Generator
    smart_insights = []
    if budget > 0:
        if spent > budget:
            over_amount = spent - budget
            smart_insights.append({
                "type": "danger",
                "icon": "🚨",
                "title": "Budget Exceeded",
                "message": f"You have exceeded your monthly budget by ₹{over_amount:,.2f} ({usage_percentage}% used)."
            })
        elif usage_percentage >= 80:
            smart_insights.append({
                "type": "warning",
                "icon": "⚠️",
                "title": "Approaching Budget Limit",
                "message": f"You have used {usage_percentage}% of your monthly budget. Only ₹{(budget - spent):,.2f} remaining."
            })
        else:
            smart_insights.append({
                "type": "success",
                "icon": "✅",
                "title": "Healthy Budget Progress",
                "message": f"You are well within your monthly budget ({usage_percentage}% used)."
            })
    else:
        smart_insights.append({
            "type": "info",
            "icon": "💡",
            "title": "Set a Monthly Budget",
            "message": "Setting a monthly budget unlocks overspending warnings and progress tracking."
        })

    if total > 0 and highest_category != "None":
        pct = round((highest_amount / total) * 100, 1)
        if pct >= 40:
            smart_insights.append({
                "type": "warning",
                "icon": "⚡",
                "title": "High Category Concentration",
                "message": f"Category '{highest_category.title()}' represents {pct}% of your total expenses (₹{highest_amount:,.2f})."
            })
        else:
            smart_insights.append({
                "type": "info",
                "icon": "🏆",
                "title": "Top Spending Category",
                "message": f"Your largest spending category is '{highest_category.title()}' at ₹{highest_amount:,.2f} ({pct}%)."
            })

    if prev_month_spent > 0:
        if mom_change > 15:
            smart_insights.append({
                "type": "danger",
                "icon": "📈",
                "title": "Spending Surge Alert",
                "message": f"Your spending this month is {mom_change}% higher than last month (₹{prev_month_spent:,.2f})."
            })
        elif mom_change < -10:
            smart_insights.append({
                "type": "success",
                "icon": "🎉",
                "title": "Monthly Expense Reduction",
                "message": f"Great progress! You spent {abs(mom_change)}% less compared to last month."
            })

    if tx_count >= 3:
        smart_insights.append({
            "type": "info",
            "icon": "📊",
            "title": "Average Transaction Size",
            "message": f"Your average transaction size is ₹{avg_transaction:,.2f} across {tx_count} recorded transactions."
        })

    # Run AI Recommendation Engine
    ai_insights = generate_ai_recommendations(
        total, spent, budget, usage_percentage,
        highest_category, highest_amount, mom_change,
        tx_count, avg_transaction, daily_avg
    )

    # Run Anomaly Detection and Prediction Engines
    anomalies = detect_anomalies(transactions)
    forecast = forecast_next_month_expense(monthly_total, spent)

    return render_template(
        "analysis.html",
        total=total,
        data=sorted_data,
        usage_percentage=usage_percentage,
        category_count=category_count,
        highest_category=highest_category,
        highest_amount=highest_amount,
        monthly_data=monthly_total,
        transactions=transactions,
        all_categories=sorted(all_categories),
        all_dates=sorted(all_dates, reverse=True),
        transaction_count=tx_count,
        avg_transaction=avg_transaction,
        daily_avg=daily_avg,
        max_transaction=max_transaction,
        min_transaction=min_transaction,
        budget=budget,
        spent=spent,
        remaining=remaining,
        status=status,
        prev_month_spent=prev_month_spent,
        mom_change=mom_change,
        smart_insights=smart_insights,
        anomalies=anomalies,
        forecast=forecast,
        ai_insights=ai_insights,
    )

@app.route("/delete/<int:expense_id>")
def delete(expense_id):

    if not login_required():
        return redirect("/login")

    conn = get_connection()

    cursor = conn.cursor()

    user_id = session["user_id"]

    cursor.execute("""
        DELETE FROM expenses
        WHERE id = ? AND user_id = ?
    """, (expense_id, user_id))

    conn.commit()

    conn.close()

    return redirect("/analysis")

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):

    if not login_required():
        return redirect("/login")

    if request.method == "POST":

        category = request.form["category"].lower().strip()
        subcategory = request.form["subcategory"].lower().strip()
        amount = float(request.form["amount"])

        conn = get_connection()
        cursor = conn.cursor()

        user_id = session["user_id"]

        cursor.execute("""
            UPDATE expenses
            SET category = ?, subcategory = ?, amount = ?
            WHERE id = ? AND user_id = ?
        """, (
            category,
            subcategory,
            amount,
            id,
            user_id
        ))
            

        conn.commit()
        conn.close()

        return redirect("/analysis")

    conn = get_connection()

    cursor = conn.cursor()

    user_id = session["user_id"]

    cursor.execute("""
        SELECT id, date, category, subcategory, amount
        FROM expenses
        WHERE id = ? AND user_id = ?
    """, (id, user_id))

    row = cursor.fetchone()

    conn.close()

    if row is None:
        return "Expense not found"

    expense = {
        "id": row[0],
        "date": row[1],
        "category": row[2],
        "subcategory": row[3],
        "amount": row[4]
    }

    return render_template("edit.html", expense=expense)

# ==================================================
# Utility Functions
# ==================================================

# Auto Open Browser locally
def open_browser():
    webbrowser.open("http://127.0.0.1:5000")

# ==================================================
# Application Entry Point
# ==================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Only open browser if running locally on desktop
    if not os.environ.get("RENDER") and not os.environ.get("DYNO"):
        threading.Timer(1.5, open_browser).start()
    app.run(host="0.0.0.0", port=port, debug=False)