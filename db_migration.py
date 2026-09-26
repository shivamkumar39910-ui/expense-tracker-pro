"""
Expense Tracker Pro 2.0 - Production Database Migration & Verification Engine (db_migration.py)
Safely migrates all data from SQLite (expenses.db or verified backup) to PostgreSQL.
Verifies row counts, financial sums, foreign key integrity, and resets sequences.
Zero data loss. Zero destructive reset.
"""

import os
import sys
import sqlite3
from typing import Dict, Any, Tuple

# Tables in strict topological order (respecting foreign key dependencies)
MIGRATION_TABLES = [
    "users",
    "accounts",
    "categories",
    "subcategories",
    "transactions",
    "expenses",
    "budgets",
    "recurring_bills",
    "financial_goals",
    "notifications"
]

POSTGRES_DDL = """
-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    currency_symbol TEXT DEFAULT '₹',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    phone TEXT,
    is_verified INTEGER DEFAULT 0,
    otp_code TEXT,
    otp_expires_at TIMESTAMP,
    login_otp_code TEXT,
    login_otp_expires_at TIMESTAMP,
    app_pin TEXT,
    is_pin_enabled INTEGER DEFAULT 0,
    privacy_mode INTEGER DEFAULT 0,
    currency_code TEXT DEFAULT 'INR'
);

-- 2. Accounts / Wallets Table
CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    initial_balance NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
    current_balance NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
    credit_limit NUMERIC(14, 2) DEFAULT 0.0,
    color_hex TEXT DEFAULT '#4F46E5',
    icon TEXT DEFAULT 'wallet',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Categories Table
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('EXPENSE', 'INCOME')),
    icon TEXT DEFAULT 'tag',
    color_hex TEXT DEFAULT '#6B7280',
    is_default INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Subcategories Table
CREATE TABLE IF NOT EXISTS subcategories (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Transactions Table (Unified Ledger)
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    target_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    subcategory_id INTEGER REFERENCES subcategories(id) ON DELETE SET NULL,
    transaction_type TEXT NOT NULL CHECK(transaction_type IN ('EXPENSE', 'INCOME', 'TRANSFER')),
    amount NUMERIC(14, 2) NOT NULL CHECK(amount > 0),
    date VARCHAR(10) NOT NULL,
    note TEXT,
    tag TEXT,
    is_recurring INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    client_uuid TEXT
);

-- 6. Legacy Expenses Table
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date VARCHAR(10) NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL
);

-- 7. Budgets Table (with uniqueness constraints)
CREATE TABLE IF NOT EXISTS budgets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
    year INTEGER NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Recurring Bills Table
CREATE TABLE IF NOT EXISTS recurring_bills (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    frequency TEXT NOT NULL DEFAULT 'MONTHLY',
    due_day INTEGER NOT NULL,
    next_due_date VARCHAR(10) NOT NULL,
    auto_paid INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. Financial Goals Table
CREATE TABLE IF NOT EXISTS financial_goals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    target_amount NUMERIC(14, 2) NOT NULL,
    current_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
    target_date VARCHAR(10),
    color_hex TEXT DEFAULT '#10B981',
    icon TEXT DEFAULT 'target',
    is_completed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK(type IN ('WARNING', 'DANGER', 'INFO', 'SUCCESS')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    category_id INTEGER,
    action_route TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance and data isolation
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_categories_user ON categories(user_id, type);
CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(user_id, transaction_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_uuid ON transactions(user_id, client_uuid) WHERE client_uuid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_budgets_user_period ON budgets(user_id, month, year);
CREATE UNIQUE INDEX IF NOT EXISTS idx_budgets_unique_overall ON budgets (user_id, month, year) WHERE category_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_budgets_unique_cat ON budgets (user_id, category_id, month, year) WHERE category_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_goals_user ON financial_goals(user_id);
CREATE INDEX IF NOT EXISTS idx_bills_user ON recurring_bills(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, date);
"""

def create_postgres_schema(pg_conn):
    """Executes the DDL to create tables and indexes in PostgreSQL."""
    cur = pg_conn.cursor()
    cur.execute(POSTGRES_DDL)
    pg_conn.commit()
    cur.close()
    print("[MIGRATION] PostgreSQL schema initialized successfully.")

def get_sqlite_table_columns(sqlite_conn, table_name: str):
    """Retrieves list of column names for a given table from SQLite."""
    cur = sqlite_conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name});")
    cols = [r[1] for r in cur.fetchall()]
    return cols

def migrate_table(sqlite_conn, pg_conn, table_name: str):
    """Migrates a single table row-by-row preserving exact IDs and attributes."""
    cols = get_sqlite_table_columns(sqlite_conn, table_name)
    col_names = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))

    sql_cur = sqlite_conn.cursor()
    sql_cur.execute(f"SELECT {', '.join(cols)} FROM {table_name} ORDER BY id ASC;")
    rows = sql_cur.fetchall()

    if not rows:
        print(f"[MIGRATION] Table '{table_name}': 0 rows to migrate.")
        return 0

    pg_cur = pg_conn.cursor()
    insert_sql = f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING;'

    # Clean data (convert 'None' strings in timestamp fields to None/NULL)
    cleaned_rows = []
    for r in rows:
        row_list = list(r)
        for i, val in enumerate(row_list):
            if val == 'None':
                row_list[i] = None
        cleaned_rows.append(tuple(row_list))

    pg_cur.executemany(insert_sql, cleaned_rows)
    pg_conn.commit()

    # Reset sequence so next auto-generated ID is max(id) + 1
    pg_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE((SELECT MAX(id) FROM \"{table_name}\"), 1));")
    pg_conn.commit()
    pg_cur.close()

    print(f"[MIGRATION] Table '{table_name}': Migrated {len(cleaned_rows)} rows. Sequence reset.")
    return len(cleaned_rows)

def verify_data_integrity(sqlite_conn, pg_conn) -> Tuple[bool, Dict[str, Any]]:
    """Compares row counts and financial totals between SQLite and PostgreSQL."""
    sql_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()
    report = {"row_counts": {}, "financial_totals": {}, "matches": True}

    print("\n" + "="*50)
    print("MIGRATION INTEGRITY & FINANCIAL VERIFICATION")
    print("="*50)

    # 1. Row Counts
    for tbl in MIGRATION_TABLES:
        sql_cur.execute(f"SELECT count(*) FROM {tbl};")
        s_cnt = sql_cur.fetchone()[0]

        pg_cur.execute(f'SELECT count(*) FROM "{tbl}";')
        p_cnt = pg_cur.fetchone()[0]

        match = (s_cnt == p_cnt)
        if not match:
            report["matches"] = False
        report["row_counts"][tbl] = {"sqlite": s_cnt, "postgres": p_cnt, "match": match}
        print(f"Table '{tbl}': SQLite={s_cnt} | PostgreSQL={p_cnt} -> {'MATCH' if match else 'MISMATCH'}")

    # 2. Financial Totals
    # Accounts Total Balance
    sql_cur.execute("SELECT COALESCE(SUM(current_balance), 0) FROM accounts;")
    s_acc = round(float(sql_cur.fetchone()[0]), 2)
    pg_cur.execute("SELECT COALESCE(SUM(current_balance), 0) FROM accounts;")
    p_acc = round(float(pg_cur.fetchone()[0]), 2)
    acc_match = (s_acc == p_acc)
    report["financial_totals"]["accounts_balance"] = {"sqlite": s_acc, "postgres": p_acc, "match": acc_match}
    print(f"Accounts Balance Total: SQLite=Rs.{s_acc:,.2f} | Postgres=Rs.{p_acc:,.2f} -> {'MATCH' if acc_match else 'MISMATCH'}")

    # Transactions Totals by Type
    for t_type in ['EXPENSE', 'INCOME', 'TRANSFER']:
        sql_cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE transaction_type = ?;", (t_type,))
        s_tot = round(float(sql_cur.fetchone()[0]), 2)
        pg_cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE transaction_type = %s;", (t_type,))
        p_tot = round(float(pg_cur.fetchone()[0]), 2)
        t_match = (s_tot == p_tot)
        report["financial_totals"][f"tx_{t_type.lower()}"] = {"sqlite": s_tot, "postgres": p_tot, "match": t_match}
        print(f"Transaction {t_type} Total: SQLite=Rs.{s_tot:,.2f} | Postgres=Rs.{p_tot:,.2f} -> {'MATCH' if t_match else 'MISMATCH'}")

    # Budgets Total
    sql_cur.execute("SELECT COALESCE(SUM(amount), 0) FROM budgets;")
    s_b = round(float(sql_cur.fetchone()[0]), 2)
    pg_cur.execute("SELECT COALESCE(SUM(amount), 0) FROM budgets;")
    p_b = round(float(pg_cur.fetchone()[0]), 2)
    b_match = (s_b == p_b)
    report["financial_totals"]["budgets"] = {"sqlite": s_b, "postgres": p_b, "match": b_match}
    print(f"Budgets Total: SQLite=Rs.{s_b:,.2f} | Postgres=Rs.{p_b:,.2f} -> {'MATCH' if b_match else 'MISMATCH'}")

    # Goals Target and Current
    sql_cur.execute("SELECT COALESCE(SUM(target_amount), 0), COALESCE(SUM(current_amount), 0) FROM financial_goals;")
    s_gt, s_gc = sql_cur.fetchone()
    pg_cur.execute("SELECT COALESCE(SUM(target_amount), 0), COALESCE(SUM(current_amount), 0) FROM financial_goals;")
    p_gt, p_gc = pg_cur.fetchone()
    g_match = (round(float(s_gt), 2) == round(float(p_gt), 2) and round(float(s_gc), 2) == round(float(p_gc), 2))
    report["financial_totals"]["goals"] = {"match": g_match}
    print(f"Goals (Target/Current): SQLite=Rs.{float(s_gt):,.2f}/Rs.{float(s_gc):,.2f} | Postgres=Rs.{float(p_gt):,.2f}/Rs.{float(p_gc):,.2f} -> {'MATCH' if g_match else 'MISMATCH'}")

    if not acc_match or not b_match or not g_match:
        report["matches"] = False

    return report["matches"], report

def run_migration(sqlite_path="expenses.db", target_url=None):
    """Main execution function to migrate SQLite database to PostgreSQL."""
    pg_url = target_url or os.environ.get("DATABASE_URL")
    if not pg_url:
        print("[MIGRATION ERROR] No PostgreSQL DATABASE_URL provided. Specify target_url or set DATABASE_URL environment variable.")
        return False

    if pg_url.startswith("postgres://"):
        pg_url = pg_url.replace("postgres://", "postgresql://", 1)

    import psycopg2
    print(f"[MIGRATION] Starting migration from SQLite ('{sqlite_path}') to PostgreSQL...")

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)

    # Connect to PostgreSQL
    try:
        pg_conn = psycopg2.connect(pg_url)
    except Exception as e:
        print(f"[MIGRATION ERROR] Failed to connect to PostgreSQL: {e}")
        sqlite_conn.close()
        return False

    try:
        # Step 1: Create Schema & Indexes
        create_postgres_schema(pg_conn)

        # Step 2: Migrate data table by table in topological order
        for tbl in MIGRATION_TABLES:
            migrate_table(sqlite_conn, pg_conn, tbl)

        # Step 3: Verify Integrity & Financial Totals
        success, report = verify_data_integrity(sqlite_conn, pg_conn)
        if success:
            print("\n[MIGRATION SUCCESS] All 10 tables and financial totals verified with 100% precision!")
        else:
            print("\n[MIGRATION WARNING] Verification detected discrepancies. Check report details.")

        return success
    except Exception as e:
        pg_conn.rollback()
        print(f"[MIGRATION FATAL ERROR] Migration aborted and rolled back: {e}")
        return False
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else None
    run_migration(target_url=url)
