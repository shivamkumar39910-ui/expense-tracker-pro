import sqlite3
from datetime import datetime, date

DATABASE_NAME = "expenses.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME, timeout=25.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

# ==================================================
# Database Setup & Schema Evolution (v2.0)
# ==================================================
def create_database():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # 1. Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            currency_symbol TEXT DEFAULT '₹',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Check for missing columns in users (backward compatibility)
    cursor.execute("PRAGMA table_info(users)")
    user_cols = [row[1] for row in cursor.fetchall()]
    if 'currency_symbol' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN currency_symbol TEXT DEFAULT '₹'")
    if 'created_at' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP")
        cursor.execute("UPDATE users SET created_at = datetime('now') WHERE created_at IS NULL")
    if 'phone' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    if 'is_verified' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
        # Mark existing users as verified so legacy logins still work
        cursor.execute("UPDATE users SET is_verified = 1 WHERE is_verified IS NULL OR is_verified = 0")
    if 'otp_code' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN otp_code TEXT")
    if 'otp_expires_at' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN otp_expires_at TIMESTAMP")
    if 'login_otp_code' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN login_otp_code TEXT")
    if 'login_otp_expires_at' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN login_otp_expires_at TIMESTAMP")
    if 'app_pin' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN app_pin TEXT")
    if 'is_pin_enabled' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN is_pin_enabled INTEGER DEFAULT 0")
    if 'privacy_mode' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN privacy_mode INTEGER DEFAULT 0")
    if 'currency_code' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN currency_code TEXT DEFAULT 'INR'")

    # 2. Accounts / Wallets Table
    # Types: CASH, BANK, CREDIT_CARD, SAVINGS, OTHER
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            account_type TEXT NOT NULL,
            initial_balance REAL NOT NULL DEFAULT 0.0,
            current_balance REAL NOT NULL DEFAULT 0.0,
            credit_limit REAL DEFAULT 0.0,
            color_hex TEXT DEFAULT '#4F46E5',
            icon TEXT DEFAULT 'wallet',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("PRAGMA table_info(accounts)")
    account_cols = [row[1] for row in cursor.fetchall()]
    if 'credit_limit' not in account_cols:
        cursor.execute("ALTER TABLE accounts ADD COLUMN credit_limit REAL DEFAULT 0.0")

    # 3. Categories Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('EXPENSE', 'INCOME')),
            icon TEXT DEFAULT 'tag',
            color_hex TEXT DEFAULT '#6B7280',
            is_default INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # 4. Subcategories Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subcategories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        )
    """)

    # 5. Transactions Table (v2.0 Ledger: EXPENSE, INCOME, TRANSFER)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            target_account_id INTEGER,
            category_id INTEGER,
            subcategory_id INTEGER,
            transaction_type TEXT NOT NULL CHECK(transaction_type IN ('EXPENSE', 'INCOME', 'TRANSFER')),
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            note TEXT,
            tag TEXT,
            is_recurring INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (target_account_id) REFERENCES accounts(id) ON DELETE SET NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
            FOREIGN KEY (subcategory_id) REFERENCES subcategories(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("PRAGMA table_info(transactions)")
    tx_cols = [row[1] for row in cursor.fetchall()]
    if 'client_uuid' not in tx_cols:
        cursor.execute("ALTER TABLE transactions ADD COLUMN client_uuid TEXT")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_uuid ON transactions(user_id, client_uuid) WHERE client_uuid IS NOT NULL;")

    # 6. Legacy Expenses Table (Retained for backwards compatibility)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            amount REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # 7. Budgets Table (v2.0: Category-specific or Overall)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_id INTEGER,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            amount REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("PRAGMA table_info(budgets)")
    budget_cols = [row[1] for row in cursor.fetchall()]
    if 'category_id' not in budget_cols:
        cursor.execute("ALTER TABLE budgets ADD COLUMN category_id INTEGER")
    if 'created_at' not in budget_cols:
        cursor.execute("ALTER TABLE budgets ADD COLUMN created_at TIMESTAMP")
        cursor.execute("UPDATE budgets SET created_at = datetime('now') WHERE created_at IS NULL")

    # 8. Recurring Bills Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurring_bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_id INTEGER,
            category_id INTEGER,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            frequency TEXT NOT NULL DEFAULT 'MONTHLY',
            due_day INTEGER NOT NULL,
            next_due_date TEXT NOT NULL,
            auto_paid INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
        )
    """)

    # 9. Financial Goals Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            target_amount REAL NOT NULL,
            current_amount REAL NOT NULL DEFAULT 0.0,
            target_date TEXT,
            color_hex TEXT DEFAULT '#10B981',
            icon TEXT DEFAULT 'target',
            is_completed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # 10. Notifications Table (Phase 10: Predictive Warning & Notification Alert System)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('WARNING', 'DANGER', 'INFO', 'SUCCESS')),
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            category_id INTEGER,
            action_route TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # 11. Performance Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_categories_user ON categories(user_id, type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(user_id, transaction_type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_budgets_user_period ON budgets(user_id, month, year);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_goals_user ON financial_goals(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_user ON recurring_bills(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);")

    conn.commit()
    conn.close()

    # Seed system defaults & migrate legacy data
    seed_default_categories()
    seed_default_accounts_and_migrate_legacy()

# ==================================================
# Default Category Seeding
# ==================================================
DEFAULT_EXPENSE_CATEGORIES = [
    {
        "name": "Food & Dining",
        "icon": "restaurant",
        "color": "#EF4444",
        "subcategories": ["Groceries", "Restaurants", "Cafe & Snacks", "Food Delivery"]
    },
    {
        "name": "Transportation",
        "icon": "directions_car",
        "color": "#F59E0B",
        "subcategories": ["Fuel", "Public Transit", "Taxi/Uber", "Vehicle Maintenance", "Parking"]
    },
    {
        "name": "Housing & Utilities",
        "icon": "home",
        "color": "#3B82F6",
        "subcategories": ["Rent/Mortgage", "Electricity", "Water", "Internet/WiFi", "Mobile Recharge"]
    },
    {
        "name": "Shopping",
        "icon": "shopping_bag",
        "color": "#EC4899",
        "subcategories": ["Clothing", "Electronics", "Home & Furniture", "Personal Care"]
    },
    {
        "name": "Entertainment",
        "icon": "movie",
        "color": "#8B5CF6",
        "subcategories": ["Streaming/OTT", "Movies", "Gaming", "Outings & Events"]
    },
    {
        "name": "Health & Medical",
        "icon": "local_hospital",
        "color": "#10B981",
        "subcategories": ["Medicines", "Doctor Consultations", "Health Insurance", "Fitness & Gym"]
    },
    {
        "name": "Education",
        "icon": "school",
        "color": "#06B6D4",
        "subcategories": ["Tuition", "Books & Supplies", "Courses & Certifications"]
    },
    {
        "name": "Financial & Investments",
        "icon": "trending_up",
        "color": "#6366F1",
        "subcategories": ["Mutual Funds", "Stocks", "EMI / Loans", "Insurance Premium"]
    },
    {
        "name": "Personal & Gifts",
        "icon": "card_giftcard",
        "color": "#D946EF",
        "subcategories": ["Donations", "Gifts", "Family Support", "Hobbies"]
    },
    {
        "name": "Others",
        "icon": "more_horiz",
        "color": "#64748B",
        "subcategories": ["Miscellaneous", "Unexpected Expenses"]
    }
]

DEFAULT_INCOME_CATEGORIES = [
    {
        "name": "Salary",
        "icon": "work",
        "color": "#10B981",
        "subcategories": ["Primary Job", "Bonus", "Overtime"]
    },
    {
        "name": "Business & Freelance",
        "icon": "laptop_mac",
        "color": "#3B82F6",
        "subcategories": ["Client Projects", "Sales", "Consulting"]
    },
    {
        "name": "Investments",
        "icon": "show_chart",
        "color": "#8B5CF6",
        "subcategories": ["Dividends", "Interest", "Capital Gains", "Rental Income"]
    },
    {
        "name": "Gifts & Grants",
        "icon": "redeem",
        "color": "#EC4899",
        "subcategories": ["Cash Gifts", "Rewards", "Tax Refund"]
    },
    {
        "name": "Other Income",
        "icon": "account_balance_wallet",
        "color": "#64748B",
        "subcategories": ["Cashbacks", "Refunds", "Miscellaneous"]
    }
]

def seed_default_categories():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if default categories already exist
    cursor.execute("SELECT count(*) FROM categories WHERE is_default = 1")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    # Seed Expense Categories
    for cat in DEFAULT_EXPENSE_CATEGORIES:
        cursor.execute("""
            INSERT INTO categories (user_id, name, type, icon, color_hex, is_default)
            VALUES (NULL, ?, 'EXPENSE', ?, ?, 1)
        """, (cat["name"], cat["icon"], cat["color"]))
        category_id = cursor.lastrowid
        for sub in cat["subcategories"]:
            cursor.execute("""
                INSERT INTO subcategories (category_id, name)
                VALUES (?, ?)
            """, (category_id, sub))

    # Seed Income Categories
    for cat in DEFAULT_INCOME_CATEGORIES:
        cursor.execute("""
            INSERT INTO categories (user_id, name, type, icon, color_hex, is_default)
            VALUES (NULL, ?, 'INCOME', ?, ?, 1)
        """, (cat["name"], cat["icon"], cat["color"]))
        category_id = cursor.lastrowid
        for sub in cat["subcategories"]:
            cursor.execute("""
                INSERT INTO subcategories (category_id, name)
                VALUES (?, ?)
            """, (category_id, sub))

    conn.commit()
    conn.close()

# ==================================================
# Default Accounts & Legacy Migration
# ==================================================
def seed_default_accounts_and_migrate_legacy():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch all registered users
    cursor.execute("SELECT id FROM users")
    users = cursor.fetchall()

    for user in users:
        user_id = user["id"]
        # Ensure user has default accounts: Cash and Primary Bank
        cursor.execute("SELECT count(*) FROM accounts WHERE user_id = ?", (user_id,))
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO accounts (user_id, name, account_type, initial_balance, current_balance, color_hex, icon)
                VALUES (?, 'Cash in Hand', 'CASH', 0.0, 0.0, '#10B981', 'payments')
            """, (user_id,))
            cash_account_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO accounts (user_id, name, account_type, initial_balance, current_balance, color_hex, icon)
                VALUES (?, 'Main Bank Account', 'BANK', 0.0, 0.0, '#3B82F6', 'account_balance')
            """, (user_id,))
        else:
            cursor.execute("SELECT id FROM accounts WHERE user_id = ? ORDER BY id ASC LIMIT 1", (user_id,))
            cash_account_id = cursor.fetchone()["id"]

        # Migrate legacy expenses into transactions if not yet migrated
        cursor.execute("SELECT count(*) FROM transactions WHERE user_id = ?", (user_id,))
        if cursor.fetchone()[0] == 0:
            cursor.execute("SELECT * FROM expenses WHERE user_id = ?", (user_id,))
            legacy_expenses = cursor.fetchall()
            for exp in legacy_expenses:
                # Find or map category
                cat_name = exp["category"].title() if exp["category"] else "Others"
                sub_name = exp["subcategory"].title() if exp["subcategory"] else "Miscellaneous"

                cursor.execute("""
                    SELECT id FROM categories 
                    WHERE (user_id = ? OR is_default = 1) AND type = 'EXPENSE' AND LOWER(name) LIKE ?
                    LIMIT 1
                """, (user_id, f"%{exp['category'].lower()}%"))
                cat_row = cursor.fetchone()
                cat_id = cat_row["id"] if cat_row else None

                sub_id = None
                if cat_id:
                    cursor.execute("SELECT id FROM subcategories WHERE category_id = ? AND LOWER(name) LIKE ? LIMIT 1",
                                   (cat_id, f"%{sub_name.lower()}%"))
                    sub_row = cursor.fetchone()
                    sub_id = sub_row["id"] if sub_row else None

                cursor.execute("""
                    INSERT INTO transactions (
                        user_id, account_id, transaction_type, amount, date, note, category_id, subcategory_id
                    ) VALUES (?, ?, 'EXPENSE', ?, ?, ?, ?, ?)
                """, (user_id, cash_account_id, exp["amount"], exp["date"], f"{cat_name} - {sub_name}", cat_id, sub_id))

                # Update account balance
                cursor.execute("""
                    UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?
                """, (exp["amount"], cash_account_id))

    conn.commit()
    conn.close()

# ==================================================
# Core Business Logic & CRUD Operations (v2.0)
# ==================================================

def create_user_default_data(user_id):
    """Creates initial accounts for newly registered users."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO accounts (user_id, name, account_type, initial_balance, current_balance, color_hex, icon)
        VALUES (?, 'Cash in Hand', 'CASH', 0.0, 0.0, '#10B981', 'payments')
    """, (user_id,))
    cursor.execute("""
        INSERT INTO accounts (user_id, name, account_type, initial_balance, current_balance, color_hex, icon)
        VALUES (?, 'Main Bank Account', 'BANK', 0.0, 0.0, '#3B82F6', 'account_balance')
    """, (user_id,))
    conn.commit()
    conn.close()

def get_user_accounts(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, account_type, initial_balance, current_balance, credit_limit, color_hex, icon, is_active
        FROM accounts
        WHERE user_id = ? AND is_active = 1
        ORDER BY id ASC
    """, (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def add_user_account(user_id, name, account_type, initial_balance=0.0, credit_limit=0.0, color_hex='#4F46E5', icon='account_balance'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO accounts (user_id, name, account_type, initial_balance, current_balance, credit_limit, color_hex, icon)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, name, account_type, initial_balance, initial_balance, credit_limit, color_hex, icon))
    account_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return account_id

def get_account_detail(user_id, account_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, account_type, initial_balance, current_balance, credit_limit, color_hex, icon, is_active, created_at
        FROM accounts
        WHERE id = ? AND user_id = ?
    """, (account_id, user_id))
    acc = cursor.fetchone()
    if not acc:
        conn.close()
        return None
    acc_data = dict(acc)

    # Calculate Total Inflow into this account
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0.0) as total_in
        FROM transactions
        WHERE user_id = ? AND (
            (transaction_type = 'INCOME' AND account_id = ?) OR
            (transaction_type = 'TRANSFER' AND target_account_id = ?)
        )
    """, (user_id, account_id, account_id))
    acc_data["total_inflow"] = float(cursor.fetchone()["total_in"])

    # Calculate Total Outflow from this account
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0.0) as total_out
        FROM transactions
        WHERE user_id = ? AND (
            (transaction_type = 'EXPENSE' AND account_id = ?) OR
            (transaction_type = 'TRANSFER' AND account_id = ?)
        )
    """, (user_id, account_id, account_id))
    acc_data["total_outflow"] = float(cursor.fetchone()["total_out"])

    conn.close()
    return acc_data

def reconcile_account_balance(user_id, account_id, actual_balance):
    """
    Reconciles account balance with real-world amount.
    Creates an adjustment transaction so transaction ledger and balances remain 100% consistent.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT current_balance, name FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
    acc = cursor.fetchone()
    if not acc:
        conn.close()
        return None

    cur_bal = float(acc["current_balance"])
    actual_balance = float(actual_balance)
    diff = round(actual_balance - cur_bal, 2)
    conn.close()

    if diff == 0:
        return {"status": "unchanged", "difference": 0.0, "new_balance": cur_bal}

    today_str = date.today().strftime("%Y-%m-%d")
    if diff > 0:
        # Balance was higher: Record positive adjustment
        tx_id = record_transaction(
            user_id=user_id,
            account_id=account_id,
            transaction_type='INCOME',
            amount=diff,
            date=today_str,
            note="Balance Reconcile Adjustment"
        )
    else:
        # Balance was lower: Record negative adjustment
        tx_id = record_transaction(
            user_id=user_id,
            account_id=account_id,
            transaction_type='EXPENSE',
            amount=abs(diff),
            date=today_str,
            note="Balance Reconcile Adjustment"
        )

    return {
        "status": "reconciled",
        "difference": diff,
        "new_balance": actual_balance,
        "adjustment_transaction_id": tx_id
    }

def record_transaction(user_id, account_id, transaction_type, amount, date,
                       target_account_id=None, category_id=None, subcategory_id=None,
                       note=None, tag=None, is_recurring=0, client_uuid=None):
    """
    Records an EXPENSE, INCOME, or TRANSFER atomically.
    CRITICAL FINANCIAL RULES:
    1. EXPENSE: Deducts from account_id.
    2. INCOME: Adds to account_id.
    3. TRANSFER: Deducts from account_id (source), Adds to target_account_id (dest).
       TRANSFERS DO NOT COUNT AS EXPENSES.
    4. Client UUID ensures idempotent offline-first sync.
    """
    amount = float(amount)
    if amount <= 0:
        raise ValueError("Transaction amount must be positive.")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check idempotency for offline sync
        if client_uuid:
            cursor.execute("SELECT id FROM transactions WHERE user_id = ? AND client_uuid = ?", (user_id, client_uuid))
            existing_row = cursor.fetchone()
            if existing_row:
                return existing_row["id"]

        # 1. Insert into transactions table
        cursor.execute("""
            INSERT INTO transactions (
                user_id, account_id, target_account_id, category_id, subcategory_id,
                transaction_type, amount, date, note, tag, is_recurring, client_uuid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, account_id, target_account_id, category_id, subcategory_id,
              transaction_type, amount, date, note, tag, is_recurring, client_uuid))
        tx_id = cursor.lastrowid

        # 2. Update Account Balances
        if transaction_type == 'EXPENSE':
            cursor.execute("UPDATE accounts SET current_balance = current_balance - ? WHERE id = ? AND user_id = ?",
                           (amount, account_id, user_id))
            # Keep legacy expenses table updated in sync for backwards compatibility
            cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
            c_row = cursor.fetchone()
            cat_name = c_row["name"] if c_row else "Expense"
            cursor.execute("INSERT INTO expenses (user_id, date, category, subcategory, amount) VALUES (?, ?, ?, ?, ?)",
                           (user_id, date, cat_name, note or "", amount))

        elif transaction_type == 'INCOME':
            cursor.execute("UPDATE accounts SET current_balance = current_balance + ? WHERE id = ? AND user_id = ?",
                           (amount, account_id, user_id))

        elif transaction_type == 'TRANSFER':
            if not target_account_id or target_account_id == account_id:
                raise ValueError("Valid distinct destination account required for transfer.")
            cursor.execute("UPDATE accounts SET current_balance = current_balance - ? WHERE id = ? AND user_id = ?",
                           (amount, account_id, user_id))
            cursor.execute("UPDATE accounts SET current_balance = current_balance + ? WHERE id = ? AND user_id = ?",
                           (amount, target_account_id, user_id))

        conn.commit()
        return tx_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def delete_user_transaction(user_id, transaction_id):
    """Reverses the balance impact atomically and removes the transaction."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, user_id))
        tx = cursor.fetchone()
        if not tx:
            return False

        amount = tx["amount"]
        t_type = tx["transaction_type"]
        acc_id = tx["account_id"]
        target_id = tx["target_account_id"]

        # Reverse balance change
        if t_type == 'EXPENSE':
            cursor.execute("UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?", (amount, acc_id))
        elif t_type == 'INCOME':
            cursor.execute("UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?", (amount, acc_id))
        elif t_type == 'TRANSFER':
            cursor.execute("UPDATE accounts SET current_balance = current_balance + ? WHERE id = ?", (amount, acc_id))
            if target_id:
                cursor.execute("UPDATE accounts SET current_balance = current_balance - ? WHERE id = ?", (amount, target_id))

        cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_net_worth_summary(user_id):
    """Calculates Net Worth, Total Assets (Cash+Bank+Savings) and Total Debt (Credit Card)."""
    accounts = get_user_accounts(user_id)
    total_assets = 0.0
    total_debt = 0.0

    for acc in accounts:
        bal = acc["current_balance"]
        if acc["account_type"] == 'CREDIT_CARD':
            if bal < 0:
                total_debt += abs(bal)
            else:
                total_debt += 0.0 # Positive credit card balance is excess payment
        else:
            total_assets += bal

    net_worth = total_assets - total_debt
    return {
        "net_worth": round(net_worth, 2),
        "total_assets": round(total_assets, 2),
        "total_debt": round(total_debt, 2),
        "accounts": accounts
    }

def get_monthly_cashflow_summary(user_id, month, year):
    """
    Returns Total Income, Total Expenses, and Net Savings for a given month.
    TRANSFERS ARE STRICTLY EXCLUDED.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Format month pattern: YYYY-MM%
    month_str = f"{year:04d}-{month:02d}%"

    cursor.execute("""
        SELECT transaction_type, SUM(amount) as total
        FROM transactions
        WHERE user_id = ? AND date LIKE ?
        GROUP BY transaction_type
    """, (user_id, month_str))
    rows = cursor.fetchall()
    conn.close()

    income = 0.0
    expenses = 0.0
    transfers = 0.0

    for r in rows:
        t = r["transaction_type"]
        tot = r["total"] or 0.0
        if t == 'INCOME':
            income = tot
        elif t == 'EXPENSE':
            expenses = tot
        elif t == 'TRANSFER':
            transfers = tot

    net_savings = income - expenses
    savings_rate = (net_savings / income * 100) if income > 0 else 0.0

    return {
        "month": month,
        "year": year,
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "transfers": round(transfers, 2),
        "net_savings": round(net_savings, 2),
        "savings_rate_pct": round(savings_rate, 1)
    }

# ==================================================
# Phase 10: Notifications & Predictive Alert Engine
# ==================================================

def create_notification(user_id, notif_type, title, message, category_id=None, action_route=None):
    """
    Inserts a notification if an unread notification with identical title doesn't already exist today.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT id FROM notifications 
        WHERE user_id = ? AND title = ? AND is_read = 0 AND date(created_at) = ?
    """, (user_id, title, today_str))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing["id"]

    cursor.execute("""
        INSERT INTO notifications (user_id, type, title, message, category_id, action_route, is_read)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (user_id, notif_type, title, message, category_id, action_route))
    notif_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return notif_id

def get_user_notifications(user_id, limit=30, unread_only=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT n.*, c.name as category_name, c.icon as category_icon, c.color_hex as category_color
        FROM notifications n
        LEFT JOIN categories c ON n.category_id = c.id
        WHERE n.user_id = ?
    """
    params = [user_id]
    if unread_only:
        query += " AND n.is_read = 0"
    query += " ORDER BY n.id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,))
    unread_cnt = cursor.fetchone()["cnt"]

    conn.close()
    return {
        "notifications": rows,
        "unread_count": unread_cnt
    }

def mark_notification_read(user_id, notif_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?", (notif_id, user_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def mark_all_notifications_read(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected

def generate_predictive_notifications(user_id):
    """
    Evaluates current month financial health and generates proactive alert cards:
    1. Overall Month-End Budget Overrun
    2. Category-Specific Budget Overrun (>85% or projected exceed)
    3. Low Liquidity Warning (< Rs 500 in liquid accounts)
    4. Upcoming Recurring Bills (due in <= 3 days)
    """
    import forecasting_engine
    today = date.today()

    # 1. Check Month-End Forecast vs Budget
    try:
        fc = forecasting_engine.calculate_month_end_forecast(user_id)
        if fc and fc.get("total_monthly_budget", 0) > 0:
            budget = fc["total_monthly_budget"]
            projected = fc["projected_month_end_spend"]
            if projected > budget:
                excess = round(projected - budget, 2)
                create_notification(
                    user_id=user_id,
                    notif_type="DANGER",
                    title="Budget Overrun Warning",
                    message=f"Spending velocity indicates month-end spend of Rs. {projected:,.2f}, which will exceed your Rs. {budget:,.2f} budget by Rs. {excess:,.2f}.",
                    action_route="tab-forecast"
                )
            elif (fc.get("mtd_actual_spend", 0) / budget) >= 0.85:
                pct = round((fc["mtd_actual_spend"] / budget) * 100, 1)
                create_notification(
                    user_id=user_id,
                    notif_type="WARNING",
                    title="Budget Threshold Alert",
                    message=f"You have consumed {pct}% of your monthly budget (Rs. {fc['mtd_actual_spend']:,.2f} spent of Rs. {budget:,.2f}).",
                    action_route="tab-budgets"
                )
    except Exception:
        pass

    # 2. Check Category-Specific Budgets
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        month_str = f"{today.year:04d}-{today.month:02d}%"
        cursor.execute("""
            SELECT b.id, b.category_id, b.amount as budget_amount, c.name as category_name,
                   COALESCE(SUM(t.amount), 0.0) as actual_spent
            FROM budgets b
            JOIN categories c ON b.category_id = c.id
            LEFT JOIN transactions t ON t.category_id = b.category_id 
                 AND t.user_id = b.user_id 
                 AND t.transaction_type = 'EXPENSE'
                 AND t.date LIKE ?
            WHERE b.user_id = ? AND b.month = ? AND b.year = ? AND b.category_id IS NOT NULL AND b.category_id > 0
            GROUP BY b.id, b.category_id, b.amount, c.name
        """, (month_str, user_id, today.month, today.year))
        cat_budgets = cursor.fetchall()
        for cb in cat_budgets:
            b_amt = float(cb["budget_amount"] or 0)
            spent = float(cb["actual_spent"] or 0)
            cat_name = cb["category_name"]
            if b_amt > 0:
                pct = (spent / b_amt) * 100
                if spent >= b_amt:
                    create_notification(
                        user_id=user_id,
                        notif_type="DANGER",
                        title=f"{cat_name} Budget Exceeded",
                        message=f"You have spent Rs. {spent:,.2f}, surpassing your Rs. {b_amt:,.2f} budget limit by Rs. {spent - b_amt:,.2f}.",
                        category_id=cb["category_id"],
                        action_route="tab-budgets"
                    )
                elif pct >= 85:
                    create_notification(
                        user_id=user_id,
                        notif_type="WARNING",
                        title=f"{cat_name} Near Limit",
                        message=f"You have used {round(pct, 1)}% (Rs. {spent:,.2f} of Rs. {b_amt:,.2f}) of your {cat_name} budget.",
                        category_id=cb["category_id"],
                        action_route="tab-budgets"
                    )
        conn.close()
    except Exception:
        pass

    # 3. Check Recurring Bills Due Soon (within 3 days)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, amount, next_due_date 
            FROM recurring_bills 
            WHERE user_id = ? AND is_active = 1 AND auto_paid = 0
        """, (user_id,))
        bills = cursor.fetchall()
        for b in bills:
            try:
                due_d = datetime.strptime(b["next_due_date"], "%Y-%m-%d").date()
                diff_days = (due_d - today).days
                if 0 <= diff_days <= 3:
                    when = "today" if diff_days == 0 else f"in {diff_days} day(s)"
                    create_notification(
                        user_id=user_id,
                        notif_type="WARNING",
                        title=f"Bill Due: {b['title']}",
                        message=f"Recurring payment of Rs. {float(b['amount']):,.2f} is due {when} ({b['next_due_date']}).",
                        action_route="tab-budgets"
                    )
            except Exception:
                pass
        conn.close()
    except Exception:
        pass

    # 4. Low Liquidity Warning
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, current_balance, account_type 
            FROM accounts 
            WHERE user_id = ? AND account_type IN ('CHECKING', 'SAVINGS', 'CASH', 'WALLET') AND is_active = 1
        """, (user_id,))
        accs = cursor.fetchall()
        for a in accs:
            bal = float(a["current_balance"] or 0)
            if bal < 500:
                create_notification(
                    user_id=user_id,
                    notif_type="WARNING",
                    title=f"Low Balance: {a['name']}",
                    message=f"Balance on your {a['name']} account has dropped to Rs. {bal:,.2f}.",
                    action_route="tab-home"
                )
        conn.close()
    except Exception:
        pass

# ==================================================
# Phase 11: Financial Goals Deepening
# ==================================================

def get_financial_goals(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM financial_goals 
        WHERE user_id = ? 
        ORDER BY is_completed ASC, id DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()

    goals = []
    for r in rows:
        target = float(r["target_amount"] or 0)
        curr = float(r["current_amount"] or 0)
        pct = round((curr / target * 100), 1) if target > 0 else 0.0
        rem = max(0.0, round(target - curr, 2))

        days_left = None
        if r["target_date"]:
            try:
                td = datetime.strptime(r["target_date"], "%Y-%m-%d").date()
                days_left = (td - date.today()).days
            except Exception:
                pass

        goals.append({
            "id": r["id"],
            "title": r["title"],
            "target_amount": target,
            "current_amount": curr,
            "target_date": r["target_date"],
            "days_left": days_left,
            "color_hex": r["color_hex"] or "#10B981",
            "icon": r["icon"] or "savings",
            "progress_pct": min(100.0, pct),
            "remaining_amount": rem,
            "is_completed": bool(r["is_completed"]) or (curr >= target)
        })
    return goals

def contribute_to_goal(user_id, goal_id, amount, account_id=None):
    """
    Contributes money to a goal. Optionally deducts from specified account balance and logs transaction.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM financial_goals WHERE id = ? AND user_id = ?", (goal_id, user_id))
    goal = cursor.fetchone()
    if not goal:
        conn.close()
        return None, "Goal not found"

    new_curr = float(goal["current_amount"] or 0) + amount
    target = float(goal["target_amount"] or 0)
    is_completed = 1 if new_curr >= target else 0

    cursor.execute("""
        UPDATE financial_goals 
        SET current_amount = ?, is_completed = ?
        WHERE id = ? AND user_id = ?
    """, (new_curr, is_completed, goal_id, user_id))
    conn.commit()
    conn.close()

    if account_id:
        record_transaction(
            user_id=user_id,
            account_id=account_id,
            transaction_type='EXPENSE',
            amount=amount,
            date=date.today().strftime("%Y-%m-%d"),
            note=f"Goal Contribution: {goal['title']}",
            tag="#goal"
        )

    if is_completed and not goal["is_completed"]:
        create_notification(
            user_id=user_id,
            notif_type="SUCCESS",
            title="Goal Achieved! 🎉",
            message=f"Congratulations! You reached your target of Rs. {target:,.2f} for '{goal['title']}'!",
            action_route="tab-budgets"
        )

    return {
        "id": goal_id,
        "new_current_amount": new_curr,
        "target_amount": target,
        "is_completed": bool(is_completed)
    }, None

def delete_financial_goal(user_id, goal_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM financial_goals WHERE id = ? AND user_id = ?", (goal_id, user_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

# ==================================================
# Phase 12: Offline Cache & Sync Queue Architecture
# ==================================================

def process_offline_sync_batch(user_id, batch_items):
    """
    Executes a list of queued operations generated while offline:
    Operation format:
    {
      "client_uuid": "...",
      "action": "CREATE_TRANSACTION" | "DELETE_TRANSACTION",
      "payload": { ... }
    }
    """
    results = []
    for item in batch_items:
        action = item.get("action")
        client_uuid = item.get("client_uuid")
        payload = item.get("payload", {})

        try:
            if action == 'CREATE_TRANSACTION':
                tx_id = record_transaction(
                    user_id=user_id,
                    account_id=payload.get("account_id"),
                    transaction_type=payload.get("transaction_type", "EXPENSE").upper(),
                    amount=payload.get("amount"),
                    date=payload.get("date"),
                    target_account_id=payload.get("target_account_id"),
                    category_id=payload.get("category_id"),
                    subcategory_id=payload.get("subcategory_id"),
                    note=payload.get("note"),
                    tag=payload.get("tag"),
                    client_uuid=client_uuid
                )
                results.append({"client_uuid": client_uuid, "status": "SYNCED", "server_id": tx_id})
            elif action == 'DELETE_TRANSACTION':
                srv_id = payload.get("id")
                if srv_id:
                    delete_user_transaction(user_id, srv_id)
                results.append({"client_uuid": client_uuid, "status": "SYNCED"})
        except Exception as e:
            results.append({"client_uuid": client_uuid, "status": "ERROR", "error": str(e)})

    return results

# ==================================================
# Phase 13: App PIN Lock & Security Shield Layer
# ==================================================

def set_user_app_pin(user_id, pin_code, enable=True):
    import hashlib
    pin_hash = hashlib.sha256(str(pin_code).strip().encode()).hexdigest()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET app_pin = ?, is_pin_enabled = ? WHERE id = ?", (pin_hash, 1 if enable else 0, user_id))
    conn.commit()
    conn.close()
    return True

def verify_user_app_pin(user_id, pin_code):
    import hashlib
    pin_hash = hashlib.sha256(str(pin_code).strip().encode()).hexdigest()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT app_pin, is_pin_enabled FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row["app_pin"]:
        return False
    return row["app_pin"] == pin_hash

def get_user_security_settings(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_pin_enabled, privacy_mode, app_pin FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"has_pin": False, "is_pin_enabled": False, "privacy_mode": False}
    return {
        "has_pin": bool(row["app_pin"]),
        "is_pin_enabled": bool(row["is_pin_enabled"]),
        "privacy_mode": bool(row["privacy_mode"])
    }

def update_user_security_settings(user_id, is_pin_enabled=None, privacy_mode=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    updates = []
    params = []
    if is_pin_enabled is not None:
        updates.append("is_pin_enabled = ?")
        params.append(1 if is_pin_enabled else 0)
    if privacy_mode is not None:
        updates.append("privacy_mode = ?")
        params.append(1 if privacy_mode else 0)
    if not updates:
        conn.close()
        return True
    params.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return True

# ==================================================
# Phase 16: Multi-Currency & Localization Engine
# ==================================================

CURRENCY_SYMBOL_MAP = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "AED": "د.إ",
    "CAD": "C$",
    "AUD": "A$",
    "SGD": "S$"
}

CURRENCY_RATES_TO_INR = {
    "INR": 1.0,
    "USD": 86.50,
    "EUR": 92.20,
    "GBP": 109.80,
    "JPY": 0.58,
    "AED": 23.55,
    "CAD": 63.40,
    "AUD": 56.10,
    "SGD": 65.10
}

def get_user_currency(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT currency_code, currency_symbol FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row["currency_code"]:
        return {
            "code": row["currency_code"],
            "symbol": row["currency_symbol"] or CURRENCY_SYMBOL_MAP.get(row["currency_code"], "₹")
        }
    return {"code": "INR", "symbol": "₹"}

def set_user_currency(user_id, currency_code):
    code = currency_code.upper().strip()
    symbol = CURRENCY_SYMBOL_MAP.get(code, "₹")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET currency_code = ?, currency_symbol = ? WHERE id = ?", (code, symbol, user_id))
    conn.commit()
    conn.close()
    return {"code": code, "symbol": symbol}

# ==================================================
# Phase 14: Data Export & Reports Engine
# ==================================================

def get_transactions_for_export(user_id, start_date=None, end_date=None, account_id=None, category_id=None, tx_type=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT t.id, t.date, t.transaction_type, t.amount, t.note, t.tag,
               a.name as account_name,
               dest.name as target_account_name,
               c.name as category_name,
               s.name as subcategory_name
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN accounts dest ON t.target_account_id = dest.id
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN subcategories s ON t.subcategory_id = s.id
        WHERE t.user_id = ?
    """
    params = [user_id]
    if start_date:
        query += " AND t.date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND t.date <= ?"
        params.append(end_date)
    if account_id:
        query += " AND (t.account_id = ? OR t.target_account_id = ?)"
        params.extend([account_id, account_id])
    if category_id:
        query += " AND t.category_id = ?"
        params.append(category_id)
    if tx_type and tx_type != 'ALL':
        query += " AND t.transaction_type = ?"
        params.append(tx_type.upper())

    query += " ORDER BY t.date DESC, t.id DESC"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# ==================================================
# Application Entry Point
# ==================================================
if __name__ == "__main__":
    create_database()
    print("Database v2.0 initialized and migrated successfully.")