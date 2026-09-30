import os
import re
import csv
import io
import secrets
import jwt
import calendar
from datetime import datetime, timedelta, date
from functools import wraps
from flask import Blueprint, request, jsonify, g, Response
from werkzeug.security import generate_password_hash, check_password_hash
import database
import forecasting_engine
import ai_mentor_service
import forecast_metrics
import sms_parser_service
import subscription_service
import cashflow_calendar_service
import alerts_engine
import push_delivery_service

api_v1 = Blueprint('api_v1', __name__)


JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "expense_tracker_pro_v2_jwt_secret_2026_super_secure")
JWT_ALGORITHM = "HS256"

# ==================================================
# JWT & Security Utilities
# ==================================================
def generate_tokens(user_id):
    now = datetime.utcnow()
    access_payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(days=7) # Long-lived for seamless mobile session
    }
    refresh_payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=60)
    }
    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return access_token, refresh_token

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "error": "Authorization token is missing or malformed"}), 401
        
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = int(payload.get("sub"))
            conn = database.get_db_connection()
            user = conn.execute("SELECT id, name, email, phone, currency_symbol, is_verified FROM users WHERE id = ?", (user_id,)).fetchone()
            conn.close()
            if not user:
                return jsonify({"success": False, "error": "User does not exist"}), 401
            g.user = dict(user)
            request.user = dict(user)
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "error": "Session token has expired. Please log in again."}), 401
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid authentication token: {str(e)}"}), 401

        return f(*args, **kwargs)
    return decorated

def generate_otp():
    """Generates a secure 6-digit numeric OTP."""
    return f"{secrets.randbelow(900000) + 100000}"

# In-memory security rate-limiter for brute force mitigation (Phase 0B)
FAILED_SECURITY_ATTEMPTS = {}

def check_security_rate_limit(action_key: str, max_attempts: int = 5, window_seconds: int = 900) -> bool:
    """Returns True if rate limited (locked out), False if allowed."""
    now = datetime.utcnow().timestamp()
    attempts = FAILED_SECURITY_ATTEMPTS.get(action_key, [])
    recent = [t for t in attempts if now - t < window_seconds]
    FAILED_SECURITY_ATTEMPTS[action_key] = recent
    return len(recent) >= max_attempts

def record_security_failed_attempt(action_key: str):
    now = datetime.utcnow().timestamp()
    attempts = FAILED_SECURITY_ATTEMPTS.get(action_key, [])
    attempts.append(now)
    FAILED_SECURITY_ATTEMPTS[action_key] = attempts

def clear_security_failed_attempts(action_key: str):
    FAILED_SECURITY_ATTEMPTS.pop(action_key, None)

# ==================================================
# 1. Authentication & 2FA OTP Endpoints
# ==================================================

@api_v1.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""

    if not name:
        return jsonify({"success": False, "error": "Name is required"}), 400
    if not email and not phone:
        return jsonify({"success": False, "error": "Email or Phone number is required"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400

    conn = database.get_db_connection()
    cursor = conn.cursor()

    # Check existing user
    if email:
        cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "error": "User with this email already exists"}), 400
    if phone:
        cursor.execute("SELECT id FROM users WHERE phone = ?", (phone,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "error": "User with this phone number already exists"}), 400

    otp = generate_otp()
    otp_expiry = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    hashed_pwd = generate_password_hash(password)

    cursor.execute("""
        INSERT INTO users (name, email, phone, password, is_verified, otp_code, otp_expires_at)
        VALUES (?, ?, ?, ?, 0, ?, ?)
    """, (name, email or f"{phone}@phone.local", phone, hashed_pwd, otp, otp_expiry))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Initialize default accounts for user
    database.create_user_default_data(user_id)

    # In production SMS/Email gateway is called here.
    # We log and return the simulated OTP for smooth development & testing.
    print(f"[SECURITY 2FA] Verification OTP for user {email or phone}: {otp}")

    return jsonify({
        "success": True,
        "message": "Registration initiated. Verification OTP sent.",
        "identifier": email or phone,
        "otp_code": otp # Returned for testing/auto-fill convenience
    }), 201

@api_v1.route('/auth/verify-otp', methods=['POST'])
def verify_registration_otp():
    data = request.get_json() or {}
    identifier = (data.get("identifier") or data.get("email") or data.get("phone") or "").strip().lower()
    otp = (data.get("otp") or data.get("otp_code") or "").strip()

    if not identifier or not otp:
        return jsonify({"success": False, "error": "Identifier and OTP code are required"}), 400

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, email, phone, currency_symbol, otp_code, otp_expires_at
        FROM users
        WHERE LOWER(email) = ? OR phone = ?
    """, (identifier, identifier))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({"success": False, "error": "User not found"}), 404

    user = dict(user)

    if check_security_rate_limit(f"otp_reg:{user['id']}", max_attempts=5, window_seconds=900):
        conn.close()
        return jsonify({"success": False, "error": "Too many failed attempts. Security lockout active for 15 minutes."}), 429

    # Check OTP expiry
    if user.get("otp_expires_at"):
        try:
            exp_str = str(user["otp_expires_at"])[:19]
            exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            if datetime.utcnow() > exp_dt:
                conn.close()
                return jsonify({"success": False, "error": "Verification OTP has expired. Please request a new code."}), 400
        except Exception:
            pass

    if user["otp_code"] != otp:
        record_security_failed_attempt(f"otp_reg:{user['id']}")
        conn.close()
        return jsonify({"success": False, "error": "Invalid OTP code. Please check and re-enter."}), 400

    clear_security_failed_attempts(f"otp_reg:{user['id']}")

    # Mark verified and clear OTP
    cursor.execute("""
        UPDATE users SET is_verified = 1, otp_code = NULL, otp_expires_at = NULL WHERE id = ?
    """, (user["id"],))
    conn.commit()
    conn.close()

    access_token, refresh_token = generate_tokens(user["id"])

    return jsonify({
        "success": True,
        "message": "Account verified successfully!",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "phone": user["phone"],
            "currency_symbol": user["currency_symbol"]
        }
    }), 200

@api_v1.route('/auth/login', methods=['POST'])
def login():
    """
    Step 1 of 2FA Login:
    Verifies credentials, generates fresh OTP, sends to user.
    """
    data = request.get_json() or {}
    identifier = (data.get("identifier") or data.get("email") or data.get("phone") or "").strip().lower()
    password = data.get("password") or ""

    if not identifier or not password:
        return jsonify({"success": False, "error": "Email/Phone and password are required"}), 400

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, email, phone, password, is_verified, currency_symbol
        FROM users
        WHERE LOWER(email) = ? OR phone = ?
    """, (identifier, identifier))
    user = cursor.fetchone()

    if not user or not check_password_hash(user["password"], password):
        conn.close()
        return jsonify({"success": False, "error": "Invalid email/phone or password"}), 401

    # Generate Login 2FA OTP
    otp = generate_otp()
    otp_expiry = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        UPDATE users SET login_otp_code = ?, login_otp_expires_at = ? WHERE id = ?
    """, (otp, otp_expiry, user["id"]))
    conn.commit()
    conn.close()

    print(f"[SECURITY 2FA] Login OTP for user {identifier}: {otp}")

    return jsonify({
        "success": True,
        "require_otp": True,
        "message": "Login 2FA OTP sent to your registered contact.",
        "identifier": identifier,
        "otp_code": otp # Returned for testing / development ease
    }), 200

@api_v1.route('/auth/login-verify-otp', methods=['POST'])
def login_verify_otp():
    """
    Step 2 of 2FA Login:
    Validates Login OTP and issues JWT tokens upon success.
    """
    data = request.get_json() or {}
    identifier = (data.get("identifier") or data.get("email") or data.get("phone") or "").strip().lower()
    otp = (data.get("otp") or data.get("otp_code") or "").strip()

    if not identifier or not otp:
        return jsonify({"success": False, "error": "Identifier and OTP are required"}), 400

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, email, phone, currency_symbol, login_otp_code, login_otp_expires_at
        FROM users
        WHERE LOWER(email) = ? OR phone = ?
    """, (identifier, identifier))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({"success": False, "error": "User not found"}), 404

    user = dict(user)

    if check_security_rate_limit(f"otp_login:{user['id']}", max_attempts=5, window_seconds=900):
        conn.close()
        return jsonify({"success": False, "error": "Too many failed login attempts. Security lockout active for 15 minutes."}), 429

    # Check Login OTP expiry
    if user.get("login_otp_expires_at"):
        try:
            exp_str = str(user["login_otp_expires_at"])[:19]
            exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            if datetime.utcnow() > exp_dt:
                conn.close()
                return jsonify({"success": False, "error": "Login 2FA OTP has expired. Please log in again."}), 400
        except Exception:
            pass

    if user["login_otp_code"] != otp:
        record_security_failed_attempt(f"otp_login:{user['id']}")
        conn.close()
        return jsonify({"success": False, "error": "Invalid 2FA OTP code"}), 400

    clear_security_failed_attempts(f"otp_login:{user['id']}")

    # Clear login OTP upon successful validation
    cursor.execute("UPDATE users SET login_otp_code = NULL, login_otp_expires_at = NULL WHERE id = ?", (user["id"],))
    conn.commit()
    conn.close()

    access_token, refresh_token = generate_tokens(user["id"])

    return jsonify({
        "success": True,
        "message": "Authentication successful!",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "phone": user["phone"],
            "currency_symbol": user["currency_symbol"]
        }
    }), 200

@api_v1.route('/auth/me', methods=['GET'])
@token_required
def get_current_user_profile():
    return jsonify({"success": True, "user": request.user}), 200

@api_v1.route('/auth/profile', methods=['GET', 'PUT', 'POST'])
@token_required
def update_user_profile():
    user_id = request.user["id"]
    conn = database.get_db_connection()
    cursor = conn.cursor()

    if request.method in ['PUT', 'POST']:
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        phone = (data.get("phone") or "").strip()

        if not name:
            conn.close()
            return jsonify({"success": False, "error": "Full Name is required"}), 400

        cursor.execute("UPDATE users SET name = ?, phone = ? WHERE id = ?", (name, phone or None, user_id))
        conn.commit()

    cursor.execute("SELECT id, name, email, phone, currency_symbol, currency_code FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    user_data = dict(row) if row else {"id": user_id, "name": request.user.get("name")}
    conn.close()

    return jsonify({
        "success": True,
        "message": "Profile updated successfully" if request.method in ['PUT', 'POST'] else "Profile retrieved successfully",
        "user": user_data
    }), 200

# ==================================================

# 2. Multi-Account & Wallets Endpoints
# ==================================================

@api_v1.route('/accounts', methods=['GET'])
@token_required
def list_accounts():
    user_id = request.user["id"]
    summary = database.get_net_worth_summary(user_id)
    return jsonify({"success": True, "data": summary}), 200

@api_v1.route('/accounts', methods=['POST'])
@token_required
def create_account():
    user_id = request.user["id"]
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    account_type = data.get("account_type", "BANK").upper()
    initial_balance = round(float(data.get("initial_balance", 0.0)), 2)
    color_hex = data.get("color_hex", "#4F46E5")
    icon = data.get("icon", "account_balance")

    if not name:
        return jsonify({"success": False, "error": "Account name is required"}), 400
    if account_type not in ['CASH', 'BANK', 'CREDIT_CARD', 'SAVINGS', 'OTHER']:
        return jsonify({"success": False, "error": "Invalid account type"}), 400

    account_id = database.add_user_account(
        user_id=user_id,
        name=name,
        account_type=account_type,
        initial_balance=initial_balance,
        credit_limit=round(float(data.get("credit_limit", 0.0)), 2),
        color_hex=color_hex,
        icon=icon
    )
    return jsonify({
        "success": True,
        "message": "Account created successfully",
        "account_id": account_id
    }), 201

@api_v1.route('/accounts/<int:acc_id>', methods=['GET'])
@token_required
def get_account_statement(acc_id):
    user_id = request.user["id"]
    detail = database.get_account_detail(user_id, acc_id)
    if not detail:
        return jsonify({"success": False, "error": "Account not found"}), 404

    # Fetch recent transactions for this account
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.transaction_type, t.amount, t.date, t.note,
               c.name as category_name, c.icon as category_icon, c.color_hex as category_color,
               a.name as account_name, ta.name as target_account_name
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN accounts ta ON t.target_account_id = ta.id
        WHERE t.user_id = ? AND (t.account_id = ? OR t.target_account_id = ?)
        ORDER BY t.date DESC, t.id DESC LIMIT 30
    """, (user_id, acc_id, acc_id))
    txs = [dict(r) for r in cursor.fetchall()]
    conn.close()

    detail["transactions"] = txs
    return jsonify({"success": True, "account": detail}), 200

@api_v1.route('/accounts/<int:acc_id>', methods=['PUT'])
@token_required
def update_account(acc_id):
    user_id = request.user["id"]
    data = request.get_json() or {}
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE accounts
        SET name = COALESCE(?, name),
            color_hex = COALESCE(?, color_hex),
            icon = COALESCE(?, icon),
            credit_limit = COALESCE(?, credit_limit)
        WHERE id = ? AND user_id = ?
    """, (data.get("name"), data.get("color_hex"), data.get("icon"), data.get("credit_limit"), acc_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Account updated successfully"}), 200

@api_v1.route('/accounts/<int:acc_id>/reconcile', methods=['POST'])
@token_required
def reconcile_account(acc_id):
    user_id = request.user["id"]
    data = request.get_json() or {}
    actual_bal = data.get("actual_balance")
    if actual_bal is None:
        return jsonify({"success": False, "error": "Actual balance is required"}), 400

    result = database.reconcile_account_balance(user_id, acc_id, actual_bal)
    if not result:
        return jsonify({"success": False, "error": "Account not found"}), 404
    return jsonify({"success": True, "data": result}), 200

# ==================================================
# 3. Categories & Subcategories Endpoints
# ==================================================

@api_v1.route('/categories', methods=['GET'])
@token_required
def get_categories():
    user_id = request.user["id"]
    conn = database.get_db_connection()
    cursor = conn.cursor()

    # Fetch Categories (System defaults + user custom)
    cursor.execute("""
        SELECT id, name, type, icon, color_hex, is_default
        FROM categories
        WHERE user_id IS NULL OR user_id = ?
        ORDER BY is_default DESC, name ASC
    """, (user_id,))
    cats = [dict(c) for c in cursor.fetchall()]

    for cat in cats:
        cursor.execute("SELECT id, name FROM subcategories WHERE category_id = ? ORDER BY name ASC", (cat["id"],))
        cat["subcategories"] = [dict(s) for s in cursor.fetchall()]

    conn.close()

    expenses = [c for c in cats if c["type"] == 'EXPENSE']
    incomes = [c for c in cats if c["type"] == 'INCOME']

    return jsonify({
        "success": True,
        "categories": {
            "expense": expenses,
            "income": incomes
        }
    }), 200

# ==================================================
# 4. Transactions Ledger (Expense, Income, Transfer)
# ==================================================

@api_v1.route('/transactions', methods=['GET'])
@token_required
def get_transactions():
    user_id = request.user["id"]
    t_type = request.args.get("type")
    account_id = request.args.get("account_id")
    category_id = request.args.get("category_id")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    search = request.args.get("search")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    query = """
        SELECT t.id, t.user_id, t.account_id, t.target_account_id, t.category_id, t.subcategory_id,
               t.transaction_type, t.amount, t.date, t.note, t.tag, t.is_recurring,
               a.name as account_name, a.color_hex as account_color,
               ta.name as target_account_name,
               c.name as category_name, c.icon as category_icon, c.color_hex as category_color,
               s.name as subcategory_name
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN accounts ta ON t.target_account_id = ta.id
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN subcategories s ON t.subcategory_id = s.id
        WHERE t.user_id = ?
    """
    params = [user_id]

    if t_type:
        query += " AND t.transaction_type = ?"
        params.append(t_type.upper())
    if account_id:
        query += " AND (t.account_id = ? OR t.target_account_id = ?)"
        params.extend([account_id, account_id])
    if category_id:
        query += " AND t.category_id = ?"
        params.append(category_id)
    if start_date:
        query += " AND t.date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND t.date <= ?"
        params.append(end_date)
    if search:
        query += " AND (t.note LIKE ? OR c.name LIKE ? OR s.name LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])

    query += " ORDER BY t.date DESC, t.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    transactions = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"success": True, "count": len(transactions), "transactions": transactions}), 200

@api_v1.route('/transactions', methods=['POST'])
@token_required
def create_transaction():
    user_id = request.user["id"]
    data = request.get_json() or {}

    try:
        tx_id = database.record_transaction(
            user_id=user_id,
            account_id=data.get("account_id"),
            transaction_type=data.get("transaction_type", "EXPENSE").upper(),
            amount=data.get("amount"),
            date=data.get("date", date.today().strftime("%Y-%m-%d")),
            target_account_id=data.get("target_account_id"),
            category_id=data.get("category_id"),
            subcategory_id=data.get("subcategory_id"),
            note=data.get("note"),
            tag=data.get("tag"),
            is_recurring=1 if data.get("is_recurring") else 0
        )
        return jsonify({"success": True, "message": "Transaction recorded", "transaction_id": tx_id}), 201
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to record transaction: {str(e)}"}), 500

@api_v1.route('/transactions/<int:tx_id>', methods=['DELETE'])
@token_required
def delete_transaction(tx_id):
    user_id = request.user["id"]
    success = database.delete_user_transaction(user_id, tx_id)
    if success:
        return jsonify({"success": True, "message": "Transaction deleted & balance restored"}), 200
    return jsonify({"success": False, "error": "Transaction not found"}), 404

@api_v1.route('/transactions/<int:tx_id>', methods=['GET'])
@token_required
def get_transaction_detail(tx_id):
    user_id = request.user["id"]
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.*, a.name as account_name, ta.name as target_account_name,
               c.name as category_name, s.name as subcategory_name
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN accounts ta ON t.target_account_id = ta.id
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN subcategories s ON t.subcategory_id = s.id
        WHERE t.id = ? AND t.user_id = ?
    """, (tx_id, user_id))
    tx = cursor.fetchone()
    conn.close()
    if not tx:
        return jsonify({"success": False, "error": "Transaction not found"}), 404
    return jsonify({"success": True, "transaction": dict(tx)}), 200

@api_v1.route('/transactions/<int:tx_id>', methods=['PUT'])
@token_required
def update_transaction(tx_id):
    user_id = request.user["id"]
    data = request.get_json() or {}

    # Atomically reverse previous transaction and insert new one
    try:
        success = database.delete_user_transaction(user_id, tx_id)
        if not success:
            return jsonify({"success": False, "error": "Transaction not found"}), 404

        new_tx_id = database.record_transaction(
            user_id=user_id,
            account_id=data.get("account_id"),
            transaction_type=data.get("transaction_type", "EXPENSE").upper(),
            amount=data.get("amount"),
            date=data.get("date"),
            target_account_id=data.get("target_account_id"),
            category_id=data.get("category_id"),
            subcategory_id=data.get("subcategory_id"),
            note=data.get("note"),
            tag=data.get("tag")
        )
        return jsonify({"success": True, "message": "Transaction updated successfully", "transaction_id": new_tx_id}), 200
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to update transaction: {str(e)}"}), 500

# ==================================================
# 5. Budgets Endpoints
# ==================================================

@api_v1.route('/budgets', methods=['GET'])
@token_required
def get_budgets():
    user_id = request.user["id"]
    today = date.today()
    month = int(request.args.get("month", today.month))
    year = int(request.args.get("year", today.year))

    conn = database.get_db_connection()
    cursor = conn.cursor()

    # Overall Monthly Budget
    cursor.execute("""
        SELECT amount FROM budgets
        WHERE user_id = ? AND month = ? AND year = ? AND (category_id IS NULL OR category_id = 0)
    """, (user_id, month, year))
    overall_row = cursor.fetchone()
    overall_budget = float(overall_row["amount"]) if overall_row else 0.0

    # Total MTD Expense
    pattern = f"{year:04d}-{month:02d}%"
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0.0) as total
        FROM transactions
        WHERE user_id = ? AND transaction_type = 'EXPENSE' AND date LIKE ?
    """, (user_id, pattern))
    total_spent = float(cursor.fetchone()["total"])

    utilization_pct = round((total_spent / overall_budget * 100), 1) if overall_budget > 0 else 0.0

    # Calculate Safe Daily Spending Cap
    days_in_month = calendar.monthrange(year, month)[1]
    days_remaining = max(1, days_in_month - today.day)
    remaining_budget = max(0.0, round(overall_budget - total_spent, 2))
    safe_daily_cap = round(remaining_budget / days_remaining, 2) if overall_budget > 0 else 0.0

    # Category-Specific Budgets
    cursor.execute("""
        SELECT b.id, b.category_id, b.amount, c.name as category_name, c.icon as category_icon, c.color_hex as category_color
        FROM budgets b
        JOIN categories c ON b.category_id = c.id
        WHERE b.user_id = ? AND b.month = ? AND b.year = ?
    """, (user_id, month, year))
    cat_budget_rows = cursor.fetchall()

    category_budgets = []
    for cb in cat_budget_rows:
        cid = cb["category_id"]
        limit_amt = float(cb["amount"])
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0.0) as cat_spent
            FROM transactions
            WHERE user_id = ? AND category_id = ? AND date LIKE ? AND transaction_type = 'EXPENSE'
        """, (user_id, cid, pattern))
        cat_spent = float(cursor.fetchone()["cat_spent"])
        cat_util = round((cat_spent / limit_amt * 100), 1) if limit_amt > 0 else 0.0

        category_budgets.append({
            "category_id": cid,
            "category_name": cb["category_name"],
            "category_icon": cb["category_icon"],
            "category_color": cb["category_color"],
            "budget_limit": limit_amt,
            "spent": cat_spent,
            "remaining": max(0.0, round(limit_amt - cat_spent, 2)),
            "utilization_pct": cat_util,
            "is_exceeded": cat_spent > limit_amt
        })

    conn.close()

    return jsonify({
        "success": True,
        "data": {
            "month": month,
            "year": year,
            "overall_budget": overall_budget,
            "total_spent": total_spent,
            "remaining": remaining_budget,
            "days_remaining": days_remaining,
            "safe_daily_cap": safe_daily_cap,
            "utilization_pct": utilization_pct,
            "is_exceeded": total_spent > overall_budget if overall_budget > 0 else False,
            "category_budgets": category_budgets
        }
    }), 200

@api_v1.route('/budgets', methods=['POST'])
@token_required
def set_budget():
    user_id = request.user["id"]
    data = request.get_json() or {}
    month = int(data.get("month", date.today().month))
    year = int(data.get("year", date.today().year))
    amount = float(data.get("amount", 0.0))
    category_id = data.get("category_id") # None for overall

    if amount <= 0:
        return jsonify({"success": False, "error": "Budget amount must be positive"}), 400

    conn = database.get_db_connection()
    cursor = conn.cursor()
    if category_id:
        cursor.execute("DELETE FROM budgets WHERE user_id = ? AND month = ? AND year = ? AND category_id = ?",
                       (user_id, month, year, category_id))
        cursor.execute("INSERT INTO budgets (user_id, category_id, month, year, amount) VALUES (?, ?, ?, ?, ?)",
                       (user_id, category_id, month, year, amount))
    else:
        cursor.execute("DELETE FROM budgets WHERE user_id = ? AND month = ? AND year = ? AND (category_id IS NULL OR category_id = 0)",
                       (user_id, month, year))
        cursor.execute("INSERT INTO budgets (user_id, category_id, month, year, amount) VALUES (?, NULL, ?, ?, ?)",
                       (user_id, month, year, amount))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Budget set successfully"}), 200

def calculate_next_recurrence_date(current_date_str: str, frequency: str = "MONTHLY", due_day: int = 1) -> str:
    """Calculates next recurrence date advancing weekly, monthly, or yearly."""
    try:
        curr_dt = datetime.strptime(str(current_date_str)[:10], "%Y-%m-%d").date()
    except Exception:
        curr_dt = date.today()

    freq = (frequency or "MONTHLY").upper()
    if freq == 'WEEKLY':
        new_date = curr_dt + timedelta(days=7)
    elif freq == 'YEARLY':
        try:
            new_date = curr_dt.replace(year=curr_dt.year + 1)
        except ValueError:
            new_date = curr_dt.replace(year=curr_dt.year + 1, day=28)
    else:  # Default MONTHLY
        month = curr_dt.month + 1
        year = curr_dt.year
        if month > 12:
            month = 1
            year += 1
        max_days = calendar.monthrange(year, month)[1]
        target_day = min(due_day if due_day > 0 else curr_dt.day, max_days)
        new_date = date(year, month, target_day)

    return new_date.strftime("%Y-%m-%d")

# ==================================================
# 5b. Recurring Bills & Subscriptions Endpoints (Phase 2 Tracker)
# ==================================================

@api_v1.route('/recurring', methods=['GET'])
@token_required
def get_recurring_bills():
    user_id = request.user["id"]
    today = date.today()
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"

    conn = database.get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT r.*, a.name as account_name, a.color_hex as account_color,
               c.name as category_name, c.icon as category_icon, c.color_hex as category_color
        FROM recurring_bills r
        LEFT JOIN accounts a ON r.account_id = a.id
        LEFT JOIN categories c ON r.category_id = c.id
        WHERE r.user_id = ?
    """
    params = [user_id]
    if not include_inactive:
        query += " AND r.is_active = 1"
    query += " ORDER BY r.next_due_date ASC, r.due_day ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    bills = []
    for r in rows:
        b = dict(r)
        due_str = b.get("next_due_date")
        if due_str:
            try:
                due_date_obj = datetime.strptime(str(due_str)[:10], "%Y-%m-%d").date()
                days_until = (due_date_obj - today).days
            except Exception:
                days_until = 0
        else:
            days_until = 0

        if b.get("is_active") == 0:
            status = "PAUSED"
        elif days_until < 0:
            status = "OVERDUE"
        elif days_until <= 3:
            status = "DUE_SOON"
        else:
            status = "UPCOMING"

        b["days_until_due"] = days_until
        b["status"] = status
        bills.append(b)

    return jsonify({"success": True, "count": len(bills), "bills": bills}), 200

@api_v1.route('/recurring', methods=['POST'])
@token_required
def create_recurring_bill():
    user_id = request.user["id"]
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    amount = round(float(data.get("amount", 0.0)), 2)
    frequency = data.get("frequency", "MONTHLY").upper()
    account_id = data.get("account_id")
    category_id = data.get("category_id")

    if not title or amount <= 0:
        return jsonify({"success": False, "error": "Title and positive amount required"}), 400

    specified_date = data.get("next_due_date")
    if specified_date:
        next_date = str(specified_date)[:10]
        try:
            due_day = datetime.strptime(next_date, "%Y-%m-%d").day
        except Exception:
            due_day = int(data.get("due_day", date.today().day))
    else:
        due_day = int(data.get("due_day", date.today().day))
        next_date = date.today().replace(day=min(due_day, 28)).strftime("%Y-%m-%d")

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO recurring_bills (user_id, account_id, category_id, title, amount, frequency, due_day, next_due_date, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (user_id, account_id, category_id, title, amount, frequency, due_day, next_date))
    bill_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": f"Recurring bill '{title}' tracked",
        "bill_id": bill_id,
        "next_due_date": next_date
    }), 201

@api_v1.route('/recurring/<int:bill_id>', methods=['PUT'])
@token_required
def update_recurring_bill(bill_id):
    user_id = request.user["id"]
    data = request.get_json() or {}
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recurring_bills WHERE id = ? AND user_id = ?", (bill_id, user_id))
    bill = cursor.fetchone()
    if not bill:
        conn.close()
        return jsonify({"success": False, "error": "Recurring bill not found"}), 404

    b = dict(bill)
    title = data.get("title", b["title"]).strip()
    amount = round(float(data.get("amount", b["amount"])), 2)
    frequency = data.get("frequency", b["frequency"]).upper()
    next_due_date = data.get("next_due_date", b["next_due_date"])
    account_id = data.get("account_id", b["account_id"])
    category_id = data.get("category_id", b["category_id"])
    is_active = int(data.get("is_active", b["is_active"]))

    cursor.execute("""
        UPDATE recurring_bills
        SET title = ?, amount = ?, frequency = ?, next_due_date = ?, account_id = ?, category_id = ?, is_active = ?
        WHERE id = ? AND user_id = ?
    """, (title, amount, frequency, next_due_date, account_id, category_id, is_active, bill_id, user_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Recurring bill updated"}), 200

@api_v1.route('/recurring/<int:bill_id>/pay', methods=['POST'])
@token_required
def pay_recurring_bill(bill_id):
    """
    Marks a recurring bill as paid:
    1. Generates an EXPENSE transaction in the ledger.
    2. Advances next_due_date to the next cycle (Weekly, Monthly, Yearly).
    """
    user_id = request.user["id"]
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recurring_bills WHERE id = ? AND user_id = ?", (bill_id, user_id))
    bill = cursor.fetchone()

    if not bill:
        conn.close()
        return jsonify({"success": False, "error": "Recurring bill not found"}), 404

    b = dict(bill)
    acc_id = b["account_id"]
    if not acc_id:
        accs = database.get_user_accounts(user_id)
        acc_id = accs[0]["id"] if accs else 1

    # Record the expense transaction
    tx_id = database.record_transaction(
        user_id=user_id,
        account_id=acc_id,
        transaction_type='EXPENSE',
        amount=b["amount"],
        date=date.today().strftime("%Y-%m-%d"),
        category_id=b["category_id"],
        note=f"Recurring Bill: {b['title']}",
        tag="#recurring"
    )

    # Advance next_due_date to next cycle
    new_due_date = calculate_next_recurrence_date(b["next_due_date"], b["frequency"], b["due_day"])
    cursor.execute("UPDATE recurring_bills SET next_due_date = ?, auto_paid = 1 WHERE id = ?", (new_due_date, bill_id))
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": f"Paid ₹{b['amount']:.2f} for {b['title']}. Next due date advanced to {new_due_date}.",
        "transaction_id": tx_id,
        "next_due_date": new_due_date
    }), 200

@api_v1.route('/recurring/<int:bill_id>', methods=['DELETE'])
@token_required
def delete_recurring_bill(bill_id):
    user_id = request.user["id"]
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM recurring_bills WHERE id = ? AND user_id = ?", (bill_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Recurring bill deleted"}), 200

# ==================================================
# 6. Forecasting & Predictive Warnings Engine
# ==================================================

@api_v1.route('/forecast/month-end', methods=['GET'])
@token_required
def get_month_end_forecast():
    user_id = request.user["id"]
    target_date = request.args.get("date")
    result = forecasting_engine.calculate_month_end_forecast(user_id, target_date=target_date)
    return jsonify({"success": True, "forecast": result}), 200

@api_v1.route('/forecast', methods=['GET'])
@token_required
def get_forecast_v2():
    user_id = request.user["id"]
    target_date = request.args.get("date")
    fc = forecasting_engine.calculate_month_end_forecast(user_id, target_date=target_date)
    return jsonify({
        "success": True,
        "current_spend": fc["mtd_actual_spend"],
        "budget": fc["budget"],
        "remaining_budget": fc["remaining_budget"],
        "projected_month_end": fc["projected_month_end_spend"],
        "safe_daily_spend": fc["safe_daily_spend"],
        "days_elapsed": fc["days_elapsed"],
        "days_remaining": fc["days_remaining"],
        "velocity": fc["daily_spending_velocity"],
        "budget_usage_percentage": fc["projected_budget_utilization_pct"],
        "risk_level": fc["risk_level"],
        "risk_reason": fc["risk_reason"],
        "confidence": fc["confidence"],
        "confidence_score": fc["confidence_score"],
        "confidence_reason": fc["confidence_reason"],
        "historical_baseline": fc["historical_baseline"],
        "category_forecasts": fc["category_forecasts"],
        "upcoming_recurring": fc["upcoming_recurring"],
        "recommendations": fc["recommendations"],
        "forecast": fc
    }), 200

@api_v1.route('/forecast/backtest', methods=['GET'])
@token_required
def get_forecast_backtest():
    user_id = request.user["id"]
    today = date.today()
    test_months = []
    y, m = today.year, today.month
    for _ in range(3):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        test_months.append((y, m))
    results = forecast_metrics.run_backtest_simulation(user_id, test_months)
    return jsonify({"success": True, "backtest": results}), 200


# ==================================================
# 7. Insights, Cashflow & Command Center Aggregator
# ==================================================

@api_v1.route('/insights/cashflow', methods=['GET'])
@token_required
def get_cashflow():
    user_id = request.user["id"]
    today = date.today()
    month = int(request.args.get("month", today.month))
    year = int(request.args.get("year", today.year))
    cashflow = database.get_monthly_cashflow_summary(user_id, month, year)
    return jsonify({"success": True, "cashflow": cashflow}), 200

@api_v1.route('/insights/anomalies', methods=['GET'])
@token_required
def get_anomalies():
    user_id = request.user["id"]
    anomalies = forecasting_engine.detect_spending_anomalies(user_id)
    return jsonify({"success": True, "anomalies": anomalies}), 200

@api_v1.route('/insights/mom', methods=['GET'])
@token_required
def get_mom():
    user_id = request.user["id"]
    mom_data = ai_mentor_service.get_mom_analysis(user_id)
    return jsonify({"success": True, "mom": mom_data}), 200

@api_v1.route('/insights/trends', methods=['GET'])
@token_required
def get_historical_trends():
    user_id = request.user["id"]
    trends = ai_mentor_service.get_six_month_trends(user_id)
    return jsonify({"success": True, "trends": trends}), 200

@api_v1.route('/ai-mentor/chat', methods=['POST'])
@token_required
def ai_mentor_chat():
    user_id = request.user["id"]
    data = request.get_json() or {}
    prompt_msg = data.get("message") or data.get("prompt")
    advice = ai_mentor_service.generate_ai_mentor_advice(user_id, user_prompt=prompt_msg)
    return jsonify({"success": True, "data": advice}), 200

@api_v1.route('/command-center/summary', methods=['GET'])
@token_required
def get_command_center_summary():
    """
    Super-fast aggregated payload for Home Command Center Dashboard:
    - Net Worth & Accounts
    - Cashflow this month
    - Forecast status & Predictive Warning
    - Recent 5 transactions
    """
    user_id = request.user["id"]
    today = date.today()

    net_worth = database.get_net_worth_summary(user_id)
    cashflow = database.get_monthly_cashflow_summary(user_id, today.month, today.year)
    forecast = forecasting_engine.calculate_month_end_forecast(user_id)

    # 5 Most Recent transactions
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.transaction_type, t.amount, t.date, t.note,
               a.name as account_name,
               c.name as category_name, c.icon as category_icon, c.color_hex as category_color
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ?
        ORDER BY t.date DESC, t.id DESC LIMIT 5
    """, (user_id,))
    recent_transactions = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({
        "success": True,
        "data": {
            "net_worth": net_worth,
            "cashflow": cashflow,
            "forecast": forecast,
            "recent_transactions": recent_transactions
        }
    }), 200

# ==================================================
# ==================================================
# 8. Financial Goals (Phase 11 Deepening)
# ==================================================

@api_v1.route('/goals', methods=['GET', 'POST'])
@token_required
def handle_goals():
    user_id = request.user["id"]
    if request.method == 'GET':
        goals = database.get_financial_goals(user_id)
        return jsonify({"success": True, "goals": goals}), 200

    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    target = float(data.get("target_amount", 0.0))
    current = float(data.get("current_amount", 0.0))
    target_date = data.get("target_date")
    color_hex = data.get("color_hex", "#10B981")
    icon = data.get("icon", "savings")

    if not title or target <= 0:
        return jsonify({"success": False, "error": "Goal title and positive target required"}), 400

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO financial_goals (user_id, title, target_amount, current_amount, target_date, color_hex, icon)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, title, target, current, target_date, color_hex, icon))
    goal_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({"success": True, "goal_id": goal_id, "message": "Goal created successfully"}), 201

@api_v1.route('/goals/<int:goal_id>/contribute', methods=['POST'])
@token_required
def contribute_goal(goal_id):
    user_id = request.user["id"]
    data = request.get_json() or {}
    amount = float(data.get("amount", 0.0))
    account_id = data.get("account_id")

    if amount <= 0:
        return jsonify({"success": False, "error": "Contribution amount must be greater than zero"}), 400

    result, err = database.contribute_to_goal(user_id, goal_id, amount, account_id)
    if err:
        return jsonify({"success": False, "error": err}), 404

    return jsonify({"success": True, "goal": result, "message": f"Contributed Rs. {amount:,.2f} to goal!"}), 200

@api_v1.route('/goals/<int:goal_id>', methods=['DELETE'])
@token_required
def delete_goal(goal_id):
    user_id = request.user["id"]
    success = database.delete_financial_goal(user_id, goal_id)
    if not success:
        return jsonify({"success": False, "error": "Goal not found"}), 404
    return jsonify({"success": True, "message": "Goal deleted successfully"}), 200

# ==================================================
# 9. Predictive Warning & Notifications (Phase 10)
# ==================================================

@api_v1.route('/notifications', methods=['GET'])
@token_required
def get_notifications():
    user_id = request.user["id"]
    # Trigger smart predictive alert generator
    database.generate_predictive_notifications(user_id)
    
    unread_only = request.args.get("unread_only", "false").lower() == "true"
    limit = int(request.args.get("limit", 30))
    data = database.get_user_notifications(user_id, limit=limit, unread_only=unread_only)
    return jsonify({
        "success": True,
        "unread_count": data["unread_count"],
        "notifications": data["notifications"]
    }), 200

@api_v1.route('/notifications/<int:notif_id>/read', methods=['POST'])
@token_required
def read_notification(notif_id):
    user_id = request.user["id"]
    database.mark_notification_read(user_id, notif_id)
    return jsonify({"success": True, "message": "Notification marked as read"}), 200

@api_v1.route('/notifications/read-all', methods=['POST'])
@token_required
def read_all_notifications():
    user_id = request.user["id"]
    database.mark_all_notifications_read(user_id)
    return jsonify({"success": True, "message": "All notifications marked as read"}), 200

# ==================================================
# 9b. Web Push Notifications & Preferences (Phase 3)
# ==================================================

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "BN9z-placeholder-public-vapid-key-for-webpush-2026")

@api_v1.route('/notifications/push/public-key', methods=['GET'])
@token_required
def get_push_public_key():
    return jsonify({
        "success": True,
        "public_key": VAPID_PUBLIC_KEY,
        "is_configured": bool(os.environ.get("VAPID_PRIVATE_KEY"))
    }), 200

@api_v1.route('/notifications/push/subscribe', methods=['POST'])
@token_required
def subscribe_push():
    user_id = request.user["id"]
    data = request.get_json() or {}
    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint:
        return jsonify({"success": False, "error": "Endpoint is required"}), 400

    database.save_push_subscription(user_id, endpoint, p256dh, auth)
    return jsonify({"success": True, "message": "Push notifications subscribed successfully"}), 201

@api_v1.route('/notifications/push/unsubscribe', methods=['POST'])
@token_required
def unsubscribe_push():
    user_id = request.user["id"]
    data = request.get_json() or {}
    endpoint = data.get("endpoint")
    if endpoint:
        database.delete_push_subscription(user_id, endpoint)
    return jsonify({"success": True, "message": "Push notifications unsubscribed"}), 200

@api_v1.route('/notifications/preferences', methods=['GET', 'POST'])
@token_required
def notification_preferences_endpoint():
    user_id = request.user["id"]
    if request.method == 'GET':
        prefs = database.get_user_notification_preferences(user_id)
        return jsonify({"success": True, "preferences": prefs}), 200

    data = request.get_json() or {}
    b80 = data.get("budget_80", 1)
    b100 = data.get("budget_100", 1)
    bill_due = data.get("bill_due", 1)
    sec = data.get("security_alerts", 1)
    forecast = data.get("forecast", 1)
    goals = data.get("goals", 1)
    weekly_summary = data.get("weekly_summary", 1)
    unusual_spending = data.get("unusual_spending", 1)
    all_off = data.get("all_off", 0)

    database.update_user_notification_preferences(
        user_id, b80, b100, bill_due, sec,
        forecast=forecast, goals=goals, weekly_summary=weekly_summary,
        unusual_spending=unusual_spending, all_off=all_off
    )
    prefs = database.get_user_notification_preferences(user_id)
    return jsonify({"success": True, "preferences": prefs, "message": "Notification preferences updated"}), 200


# ==================================================
# 10. Visual Charts & Trend Visualizations (Phase 11)
# ==================================================

@api_v1.route('/charts/breakdown', methods=['GET'])
@token_required
def get_chart_breakdown():
    """
    Returns category breakdown for current month (or specified month/year)
    for rendering donut/pie charts with percentage and category colors.
    """
    user_id = request.user["id"]
    today = date.today()
    month = int(request.args.get("month", today.month))
    year = int(request.args.get("year", today.year))
    pattern = f"{year:04d}-{month:02d}%"

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COALESCE(c.name, 'Uncategorized') as category_name,
               COALESCE(c.color_hex, '#6B7280') as color_hex,
               COALESCE(c.icon, 'category') as icon,
               SUM(t.amount) as total_amount,
               COUNT(t.id) as tx_count
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        GROUP BY c.id, c.name, c.color_hex, c.icon
        ORDER BY total_amount DESC
    """, (user_id, pattern))
    rows = cursor.fetchall()
    conn.close()

    total_expense = sum(float(r["total_amount"]) for r in rows)
    slices = []
    for r in rows:
        amt = float(r["total_amount"])
        pct = round((amt / total_expense * 100), 1) if total_expense > 0 else 0.0
        slices.append({
            "name": r["category_name"],
            "amount": amt,
            "percentage": pct,
            "color": r["color_hex"],
            "icon": r["icon"],
            "count": r["tx_count"]
        })

    return jsonify({
        "success": True,
        "total_expense": round(total_expense, 2),
        "month": month,
        "year": year,
        "breakdown": slices
    }), 200

@api_v1.route('/charts/history-6m', methods=['GET'])
@token_required
def get_chart_history_6m():
    """
    Returns 6 months historical comparison (Income vs Expense vs Savings)
    for rendering monthly bar/line charts.
    """
    user_id = request.user["id"]
    today = date.today()
    history = []

    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        
        summary = database.get_monthly_cashflow_summary(user_id, m, y)
        month_label = date(y, m, 1).strftime("%b %y")
        history.append({
            "label": month_label,
            "month": m,
            "year": y,
            "income": summary["income"],
            "expenses": summary["expenses"],
            "net_savings": summary["net_savings"],
            "savings_rate_pct": summary["savings_rate_pct"]
        })

    return jsonify({
        "success": True,
        "history": history
    }), 200

# ==================================================
# 11. Offline Batch Sync (Phase 12)
# ==================================================

@api_v1.route('/sync/batch', methods=['POST'])
@token_required
def sync_offline_batch():
    """
    Processes an array of offline queued transactions with client UUIDs.
    Returns sync status per operation.
    """
    user_id = request.user["id"]
    data = request.get_json() or {}
    items = data.get("items", [])

    if not isinstance(items, list):
        return jsonify({"success": False, "error": "Batch items must be a list"}), 400

    results = database.process_offline_sync_batch(user_id, items)
    synced_count = sum(1 for r in results if r.get("status") == "SYNCED")

    return jsonify({
        "success": True,
        "message": f"Processed {len(items)} offline items ({synced_count} synced successfully)",
        "results": results,
        "synced_count": synced_count
    }), 200

# ==================================================
# 12. App PIN & Security Settings (Phase 13)
# ==================================================

@api_v1.route('/security/settings', methods=['GET', 'POST'])
@token_required
def handle_security_settings():
    user_id = request.user["id"]
    if request.method == 'GET':
        settings = database.get_user_security_settings(user_id)
        return jsonify({"success": True, "settings": settings}), 200

    data = request.get_json() or {}
    is_pin_enabled = data.get("is_pin_enabled")
    privacy_mode = data.get("privacy_mode")

    database.update_user_security_settings(user_id, is_pin_enabled=is_pin_enabled, privacy_mode=privacy_mode)
    settings = database.get_user_security_settings(user_id)
    return jsonify({"success": True, "settings": settings, "message": "Security settings updated"}), 200

@api_v1.route('/security/set-pin', methods=['POST'])
@token_required
def set_app_pin():
    user_id = request.user["id"]
    data = request.get_json() or {}
    pin = str(data.get("pin", "")).strip()

    if not re.match(r'^\d{4}$', pin):
        return jsonify({"success": False, "error": "PIN must be exactly 4 digits"}), 400

    enable = data.get("enable", True)
    database.set_user_app_pin(user_id, pin, enable=enable)
    return jsonify({"success": True, "message": "App Security PIN set successfully"}), 200

@api_v1.route('/security/verify-pin', methods=['POST'])
@token_required
def verify_app_pin():
    user_id = request.user["id"]
    data = request.get_json() or {}
    pin = str(data.get("pin", "")).strip()

    if check_security_rate_limit(f"pin:{user_id}", max_attempts=5, window_seconds=900):
        return jsonify({
            "success": False,
            "valid": False,
            "error": "Too many incorrect PIN attempts. Security lockout active for 15 minutes."
        }), 429

    is_valid = database.verify_user_app_pin(user_id, pin)
    if not is_valid:
        record_security_failed_attempt(f"pin:{user_id}")
        return jsonify({"success": False, "valid": False, "error": "Incorrect PIN"}), 401

    clear_security_failed_attempts(f"pin:{user_id}")
    return jsonify({"success": True, "valid": True, "message": "PIN verified successfully"}), 200

# ==================================================
# 13. Reports & CSV Export Engine (Phase 14)
# ==================================================

@api_v1.route('/reports/export/csv', methods=['GET'])
@token_required
def export_transactions_csv():
    """
    Generates and streams a clean CSV export of user transactions
    matching any optional date, category, or account filters.
    """
    user_id = request.user["id"]
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    account_id = request.args.get("account_id")
    category_id = request.args.get("category_id")
    tx_type = request.args.get("tx_type")

    rows = database.get_transactions_for_export(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        account_id=account_id,
        category_id=category_id,
        tx_type=tx_type
    )

    output = io.StringIO()
    writer = csv.writer(output)
    # Header row
    writer.writerow(["ID", "Date", "Type", "Account", "Destination Account", "Category", "Subcategory", "Amount (INR)", "Note", "Tag"])

    for r in rows:
        writer.writerow([
            r["id"],
            r["date"],
            r["transaction_type"],
            r["account_name"] or "",
            r["target_account_name"] or "",
            r["category_name"] or "",
            r["subcategory_name"] or "",
            f"{r['amount']:.2f}",
            r["note"] or "",
            r["tag"] or ""
        ])

    csv_data = output.getvalue()
    output.close()

    filename = f"ExpenseTracker_Export_{date.today().strftime('%Y%m%d')}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@api_v1.route('/reports/summary', methods=['GET'])
@token_required
def get_reports_summary():
    """
    Returns aggregated figures, category distribution, and top expenses
    for monthly statement generation and print view.
    """
    user_id = request.user["id"]
    today = date.today()
    month = int(request.args.get("month", today.month))
    year = int(request.args.get("year", today.year))
    pattern = f"{year:04d}-{month:02d}%"

    cashflow = database.get_monthly_cashflow_summary(user_id, month, year)

    conn = database.get_db_connection()
    cursor = conn.cursor()

    # Category breakdown
    cursor.execute("""
        SELECT COALESCE(c.name, 'Other') as category_name,
               COALESCE(c.color_hex, '#6B7280') as color,
               SUM(t.amount) as total_amount,
               COUNT(t.id) as count
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        GROUP BY c.id, c.name, c.color_hex
        ORDER BY total_amount DESC
    """, (user_id, pattern))
    categories = [dict(r) for r in cursor.fetchall()]

    # Top 5 highest expenses
    cursor.execute("""
        SELECT t.id, t.date, t.amount, t.note, c.name as category_name, a.name as account_name
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.user_id = ? AND t.transaction_type = 'EXPENSE' AND t.date LIKE ?
        ORDER BY t.amount DESC LIMIT 5
    """, (user_id, pattern))
    top_expenses = [dict(r) for r in cursor.fetchall()]

    conn.close()

    month_name = date(year, month, 1).strftime("%B %Y")
    return jsonify({
        "success": True,
        "statement": {
            "period": month_name,
            "month": month,
            "year": year,
            "cashflow": cashflow,
            "categories": categories,
            "top_expenses": top_expenses,
            "generated_at": datetime.now().strftime("%d %b %Y, %I:%M %p")
        }
    }), 200

# ==================================================
# 14. Multi-Currency & Localization Engine (Phase 16)
# ==================================================

@api_v1.route('/currencies', methods=['GET'])
def get_supported_currencies():
    """
    Returns list of supported international currencies with live exchange rates,
    last updated timestamp, and user-facing display pairs (e.g. 1 USD = ₹86.50).
    """
    import fx_service
    currencies = fx_service.get_currencies_with_live_rates()
    return jsonify({"success": True, "currencies": currencies}), 200

@api_v1.route('/user/currency', methods=['GET'])
@token_required
def get_user_currency_endpoint():
    user_id = request.user["id"]
    curr = database.get_user_currency(user_id)
    return jsonify({"success": True, "currency": curr}), 200

@api_v1.route('/user/currency', methods=['POST'])
@token_required
def set_user_currency_endpoint():
    user_id = request.user["id"]
    data = request.get_json() or {}
    code = data.get("currency_code", "INR")
    updated = database.set_user_currency(user_id, code)
    return jsonify({"success": True, "currency": updated, "message": f"Currency updated to {updated['code']} ({updated['symbol']})"}), 200

# ==================================================
# 15. Smart AI Receipt Scanner Engine (Phase 17)
# ==================================================

# Known merchants and their default category mappings
MERCHANT_CATEGORY_RULES = [
    # Food & Dining
    (r'(?i)\b(starbucks|cafe|costa|ccd|blue tokai|barista|third wave)\b', "Food & Dining", "Coffee & Beverage"),
    (r'(?i)\b(mcdonald\'?s|kfc|burger king|subway|wendy\'?s|domino\'?s|pizza hut)\b', "Food & Dining", "Fast Food"),
    (r'(?i)\b(zomato|swiggy|eatsure|foodpanda)\b', "Food & Dining", "Online Food Delivery"),
    (r'(?i)\b(restaurant|bistro|diner|kitchen|dhaba|bar & grill|bakery)\b', "Food & Dining", "Restaurant Dining"),
    # Transportation
    (r'(?i)\b(uber|ola|rapido|blusmart|lyft|cab|taxi)\b', "Transportation", "Ride Hailing"),
    (r'(?i)\b(shell|bpcl|hpcl|indian oil|petrol|fuel|cng|diesel)\b', "Transportation", "Fuel"),
    (r'(?i)\b(metro|railway|irctc|flight|indigo|air india|fastag)\b', "Transportation", "Transit / Toll"),
    # Groceries
    (r'(?i)\b(blinkit|zepto|instamart|bigbasket|dunzo)\b', "Groceries", "Quick Commerce Grocery"),
    (r'(?i)\b(d-mart|dmart|reliance fresh|nature\'?s basket|spencer|supermarket|kirana|grocery)\b', "Groceries", "Supermarket"),
    # Shopping
    (r'(?i)\b(amazon|flipkart|myntra|ajio|meesho|tata cliq)\b', "Shopping", "Online Shopping"),
    (r'(?i)\b(zara|h&m|uniqlo|decathlon|westside|pantaloons|lifestyle)\b', "Shopping", "Apparel & Gear"),
    # Healthcare
    (r'(?i)\b(apollo|medplus|pharmeasy|1mg|tata 1mg|pharmacy|chemist|hospital|clinic|pathology|diagnostic)\b', "Healthcare", "Medical & Pharmacy"),
    # Entertainment
    (r'(?i)\b(pvr|inox|cinepolis|bookmyshow|movie|cinema|theater)\b', "Entertainment", "Movies & Events"),
    (r'(?i)\b(netflix|spotify|prime video|hotstar|disney|apple music|youtube premium)\b', "Entertainment", "Digital Subscriptions"),
    # Bills & Utilities
    (r'(?i)\b(airtel|jio|vodafone|vi|bsnl|broadband|wifi)\b', "Bills & Utilities", "Mobile & Internet"),
    (r'(r?i)\b(electricity|bescom|tata power|adani power|water board|igl|indane|hp gas)\b', "Bills & Utilities", "Utilities"),
]

SAMPLE_RECEIPTS = {
    "starbucks": {
        "text": "STARBUCKS COFFEE\nStore #4829 - Indiranagar, BLR\nDate: 2026-09-24 14:32\n1x Caffe Latte - Rs. 380.00\n1x Butter Croissant - Rs. 240.00\nCGST (2.5%): Rs. 15.50\nSGST (2.5%): Rs. 15.50\nTotal Amount: Rs. 651.00\nPayment: UPI / Card",
        "merchant": "Starbucks Coffee",
        "amount": 651.00,
        "date": "2026-09-24",
        "category": "Food & Dining",
        "subcategory": "Coffee & Beverage"
    },
    "shell_fuel": {
        "text": "SHELL PETROL STATION\nStation 082 - Ring Road\nDate: 2026-09-24 09:15\nFuel Type: V-Power Petrol\nLitres: 28.50 L\nRate: 104.20 / L\nTotal Bill Amount: Rs. 2969.70\nPaid via Credit Card",
        "merchant": "Shell Petrol Station",
        "amount": 2969.70,
        "date": "2026-09-24",
        "category": "Transportation",
        "subcategory": "Fuel"
    },
    "apollo_pharmacy": {
        "text": "APOLLO PHARMACY LTD\nBranch: Koramangala\nInvoice: AP-98432\nDate: 2026-09-23\nMedicines & Healthcare\n1x Multivitamin 30s - Rs. 450.00\n1x Pain Relief Gel - Rs. 185.00\nTotal Net Payable: Rs. 635.00",
        "merchant": "Apollo Pharmacy",
        "amount": 635.00,
        "date": "2026-09-23",
        "category": "Healthcare",
        "subcategory": "Medical & Pharmacy"
    },
    "blinkit_grocery": {
        "text": "BLINKIT ORDER #BK-78921\n10-Minute Delivery\nDate: 2026-09-24 18:20\nOrganic Milk 2L, Bread, Eggs, Fresh Vegetables\nTotal Order Value: Rs. 488.00\nPaid via UPI",
        "merchant": "Blinkit",
        "amount": 488.00,
        "date": "2026-09-24",
        "category": "Groceries",
        "subcategory": "Quick Commerce Grocery"
    }
}

@api_v1.route('/receipts/scan', methods=['POST'])
@token_required
def scan_receipt_endpoint():
    """
    Parses an uploaded receipt image, raw OCR text, or simulation preset.
    Uses ocr_service with honest error reporting if no OCR engine is configured.
    Enforces user confirmation before saving any transaction.
    """
    import ocr_service
    user_id = request.user["id"]
    
    data = {}
    if request.is_json:
        data = request.get_json() or {}
    else:
        data = request.form.to_dict()

    raw_text = data.get("raw_text", "").strip()
    sample_key = data.get("sample_type", "").strip().lower()

    if sample_key in SAMPLE_RECEIPTS:
        raw_text = SAMPLE_RECEIPTS[sample_key]["text"]

    # If an image file was uploaded
    if 'receipt_image' in request.files:
        file = request.files['receipt_image']
        if file and file.filename:
            image_bytes = file.read()
            if not raw_text:
                extracted_text, err = ocr_service.extract_text_from_image(image_bytes, file.filename)
                if err or not extracted_text:
                    return jsonify({
                        "success": False,
                        "ocr_available": ocr_service.is_ocr_engine_configured(),
                        "error": err or "Could not extract text from receipt image.",
                        "message": "Real-time image OCR requires Tesseract OCR or OCR_API_KEY environment variable. You can still paste receipt/SMS text directly or fill manually."
                    }), 422
                raw_text = extracted_text

    if not raw_text:
        return jsonify({
            "success": False,
            "error": "No receipt text or image provided to scan.",
            "message": "Please provide an image, sample preset, or paste bill/SMS text."
        }), 400

    parsed = ocr_service.parse_receipt_entities(raw_text)
    if not parsed.get("success"):
        return jsonify(parsed), 400

    r = parsed["receipt"]

    # Match category in user's categories
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories WHERE (user_id = ? OR user_id IS NULL) AND LOWER(name) = LOWER(?) LIMIT 1",
                   (user_id, r["category_name"]))
    cat_row = cursor.fetchone()
    cat_id = cat_row["id"] if cat_row else 1
    cat_name = cat_row["name"] if cat_row else r["category_name"]
    conn.close()

    return jsonify({
        "success": True,
        "receipt": {
            "merchant": r["merchant"],
            "amount": r["amount"],
            "date": r["date"],
            "date_inferred": r["date_inferred"],
            "category_id": cat_id,
            "category_name": cat_name,
            "subcategory": r["subcategory_name"],
            "note": f"Receipt from {r['merchant']}",
            "confidence": r["confidence_score"],
            "raw_snippet": raw_text[:200],
            "requires_user_confirmation": True
        },
        "message": f"Parsed receipt from {r['merchant']} (₹{r['amount']:.2f}). Please review and confirm."
    }), 200

# ==================================================
# 16. Automation & Real-World Intelligence Endpoints (Phase 6)
# ==================================================

@api_v1.route('/parser/parse-sms', methods=['POST'])
@token_required
def parse_sms_endpoint():
    """
    Parses SMS/UPI/Bank notification text, checks duplicate transaction risk,
    and returns a structured transaction proposal for user confirmation.
    """
    user_id = request.user["id"]
    data = request.get_json() or {}
    sms_text = (data.get("text") or "").strip()

    if not sms_text:
        return jsonify({"success": False, "error": "No text provided to parse."}), 400

    parsed = sms_parser_service.parse_sms_text(sms_text)
    if not parsed.get("success"):
        return jsonify(parsed), 422

    # Check for potential duplicates in ledger
    dup = sms_parser_service.detect_duplicate_transaction(
        user_id=user_id,
        amount=parsed["amount"],
        tx_date=parsed["date"],
        ref_number=parsed.get("ref_number")
    )

    # Match category in user's category list
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name FROM categories 
        WHERE (user_id = ? OR user_id IS NULL) AND LOWER(name) = LOWER(?)
        LIMIT 1
    """, (user_id, parsed["category_inferred"]))
    cat_row = cursor.fetchone()
    cat_id = cat_row["id"] if cat_row else 1
    cat_name = cat_row["name"] if cat_row else parsed["category_inferred"]

    # Select default account if not provided
    cursor.execute("SELECT id, name FROM accounts WHERE user_id = ? ORDER BY id ASC LIMIT 1", (user_id,))
    acc_row = cursor.fetchone()
    acc_id = acc_row["id"] if acc_row else 1
    acc_name = acc_row["name"] if acc_row else "Primary"

    # Log to transaction_parse_events table
    import json
    parse_event_id = None
    try:
        cursor.execute("""
            INSERT INTO transaction_parse_events (user_id, source_type, raw_text, parsed_data_json, confidence, status)
            VALUES (?, 'SMS', ?, ?, ?, 'PENDING')
        """, (user_id, sms_text, json.dumps(parsed), parsed["confidence"]))
        parse_event_id = cursor.lastrowid
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    return jsonify({
        "success": True,
        "parse_event_id": parse_event_id,
        "transaction": {
            "amount": parsed["amount"],
            "transaction_type": parsed["transaction_type"],
            "merchant": parsed["merchant"],
            "merchant_clean": parsed["merchant_clean"],
            "date": parsed["date"],
            "bank_name": parsed["bank_name"],
            "account_last4": parsed["account_last4"],
            "ref_number": parsed["ref_number"],
            "confidence": parsed["confidence"],
            "category_id": cat_id,
            "category_name": cat_name,
            "account_id": acc_id,
            "account_name": acc_name,
            "note": f"{parsed['merchant_clean']} ({parsed['bank_name']})" if parsed['bank_name'] else parsed['merchant_clean'],
            "requires_user_confirmation": True
        },
        "duplicate_warning": dup,
        "message": "Transaction parsed successfully. Please review and confirm before saving."
    }), 200


@api_v1.route('/parser/confirm-transaction', methods=['POST'])
@token_required
def confirm_parsed_transaction_endpoint():
    """
    Saves a user-confirmed parsed transaction into the official ledger.
    Guarantees user control: no transaction is saved without explicit review.
    """
    user_id = request.user["id"]
    data = request.get_json() or {}

    amount = data.get("amount")
    if amount is None:
        return jsonify({"success": False, "error": "Amount is required."}), 400

    account_id = data.get("account_id")
    if not account_id:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM accounts WHERE user_id = ? ORDER BY id ASC LIMIT 1", (user_id,))
        acc = cursor.fetchone()
        conn.close()
        account_id = acc["id"] if acc else 1

    tx_type = data.get("transaction_type", "EXPENSE").upper()
    tx_date = data.get("date", date.today().strftime("%Y-%m-%d"))
    category_id = data.get("category_id")
    note = data.get("note", "").strip()
    tag = data.get("tag", "SMS-Import")
    parse_event_id = data.get("parse_event_id")

    try:
        tx_id = database.record_transaction(
            user_id=user_id,
            account_id=account_id,
            transaction_type=tx_type,
            amount=amount,
            date=tx_date,
            category_id=category_id,
            note=note,
            tag=tag
        )

        if parse_event_id:
            try:
                conn = database.get_db_connection()
                conn.execute("""
                    UPDATE transaction_parse_events
                    SET status = 'CONFIRMED'
                    WHERE id = ? AND user_id = ?
                """, (parse_event_id, user_id))
                conn.commit()
                conn.close()
            except Exception:
                pass

        return jsonify({
            "success": True,
            "message": "Transaction verified and saved to ledger successfully.",
            "transaction_id": tx_id
        }), 201
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to record transaction: {str(e)}"}), 500


@api_v1.route('/subscriptions/overview', methods=['GET'])
@token_required
def subscriptions_overview_endpoint():
    """
    Returns monthly/yearly recurring totals, breakdown, upcoming dues, and duplicate warnings.
    """
    user_id = request.user["id"]
    summary = subscription_service.get_subscription_summary(user_id)
    return jsonify({
        "success": True,
        "subscriptions": summary
    }), 200


@api_v1.route('/subscriptions/candidates', methods=['GET'])
@token_required
def subscriptions_candidates_endpoint():
    """
    Scans historical transactions to detect recurring charges not yet tracked as recurring bills.
    """
    user_id = request.user["id"]
    candidates = subscription_service.discover_subscription_candidates(user_id)
    return jsonify({
        "success": True,
        "candidates": candidates
    }), 200


@api_v1.route('/subscriptions/convert-candidate', methods=['POST'])
@token_required
def convert_subscription_candidate_endpoint():
    """
    Converts a discovered recurring subscription candidate into an official recurring bill.
    """
    user_id = request.user["id"]
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    amount = data.get("amount")

    if not title or amount is None:
        return jsonify({"success": False, "error": "Title and amount are required."}), 400

    frequency = data.get("frequency", "MONTHLY").upper()
    due_date = data.get("due_date", date.today().strftime("%Y-%m-%d"))
    category_id = data.get("category_id")

    bill_id = subscription_service.convert_candidate_to_recurring(
        user_id=user_id,
        title=title,
        amount=amount,
        frequency=frequency,
        due_date=due_date,
        category_id=category_id
    )

    return jsonify({
        "success": True,
        "message": f"'{title}' converted to recurring bill successfully.",
        "bill_id": bill_id
    }), 201


@api_v1.route('/cashflow/calendar', methods=['GET'])
@token_required
def cashflow_calendar_endpoint():
    """
    Returns day-by-day cashflow timeline with actual, committed, and projected balances.
    """
    user_id = request.user["id"]
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    calendar_data = cashflow_calendar_service.get_cashflow_calendar(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date
    )
    return jsonify({
        "success": True,
        "cashflow": calendar_data
    }), 200


@api_v1.route('/goals/intelligence', methods=['GET'])
@token_required
def goals_intelligence_endpoint():
    """
    Returns pacing, required monthly savings, and projected completion date for goals.
    """
    user_id = request.user["id"]
    goals_data = alerts_engine.get_goal_intelligence(user_id)
    return jsonify({
        "success": True,
        "goals": goals_data
    }), 200


@api_v1.route('/alerts', methods=['GET'])
@token_required
def get_alerts_endpoint():
    """
    Evaluates current financial health and returns active alerts with 24h deduplication.
    """
    user_id = request.user["id"]
    alerts_engine.evaluate_and_generate_alerts(user_id)
    active_alerts = alerts_engine.get_active_alerts(user_id)
    return jsonify({
        "success": True,
        "alerts": active_alerts
    }), 200


@api_v1.route('/alerts/<int:alert_id>/dismiss', methods=['POST'])
@token_required
def dismiss_alert_endpoint(alert_id):
    """
    Dismisses / marks an alert as read.
    """
    user_id = request.user["id"]
    dismissed = alerts_engine.dismiss_alert(user_id, alert_id)
    if dismissed:
        return jsonify({"success": True, "message": "Alert dismissed."}), 200
    else:
        return jsonify({"success": False, "error": "Alert not found or already dismissed."}), 404

