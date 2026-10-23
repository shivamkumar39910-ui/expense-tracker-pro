"""
Expense Tracker Pro - Admin Data Inspector & CLI Viewer (admin_viewer.py)
Allows the administrator/owner to view all registered users, their balances,
and transactions directly from terminal or export to CSV.
Works with both local SQLite (expenses.db) and Cloud PostgreSQL (Supabase/Render).
"""

import sys
import os
import csv
from datetime import datetime

# Ensure utf-8 output on Windows consoles
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import db_engine

def print_banner():
    print("=" * 70)
    print("       EXPENSE TRACKER PRO - ADMIN DATA INSPECTOR")
    print(f"       Active Database: {db_engine.get_db_type().upper()}")
    print("=" * 70)

def get_stats():
    conn = db_engine.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM transactions")
    tx_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM accounts")
    acc_count = cursor.fetchone()[0]
    
    conn.close()
    return user_count, tx_count, acc_count

def list_users(limit=25):
    conn = db_engine.get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT u.id, u.name, u.email, COALESCE(u.phone, 'N/A') as phone, 
               u.created_at,
               (SELECT COUNT(*) FROM transactions t WHERE t.user_id = u.id) as tx_count,
               (SELECT COALESCE(SUM(current_balance), 0) FROM accounts a WHERE a.user_id = u.id) as total_balance
        FROM users u
        ORDER BY u.id DESC
        LIMIT ?
    """
    if db_engine.is_postgres():
        query = query.replace("?", "%s")
        
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    print("\n--- RECENT REGISTERED USERS ---")
    print(f"{'ID':<5} | {'NAME':<18} | {'EMAIL':<30} | {'PHONE':<15} | {'TXs':<5} | {'BALANCE':<10}")
    print("-" * 95)
    for r in rows:
        uid = r['id'] if hasattr(r, '__getitem__') else r[0]
        name = (r['name'] or '')[:18]
        email = (r['email'] or '')[:30]
        phone = (r['phone'] or 'N/A')[:15]
        txs = r['tx_count']
        bal = f"₹{float(r['total_balance']):,.2f}"
        print(f"{uid:<5} | {name:<18} | {email:<30} | {phone:<15} | {txs:<5} | {bal:<10}")

def inspect_user(user_id):
    conn = db_engine.get_db_connection()
    cursor = conn.cursor()
    
    u_query = "SELECT * FROM users WHERE id = ?"
    if db_engine.is_postgres():
        u_query = u_query.replace("?", "%s")
    cursor.execute(u_query, (user_id,))
    raw_user = cursor.fetchone()
    
    if not raw_user:
        print(f"[!] User with ID {user_id} not found.")
        conn.close()
        return

    user = dict(raw_user)
    print(f"\n--- USER DETAILS: {user['name']} (ID: {user['id']}) ---")
    print(f"Email: {user.get('email')}")
    print(f"Phone: {user.get('phone') or 'N/A'}")
    print(f"Created: {user.get('created_at') or 'N/A'}")
    print(f"Verified: {'Yes' if user.get('is_verified') else 'No'}")
    
    # Accounts
    a_query = "SELECT id, name, account_type, current_balance FROM accounts WHERE user_id = ?"
    if db_engine.is_postgres():
        a_query = a_query.replace("?", "%s")
    cursor.execute(a_query, (user_id,))
    accounts = cursor.fetchall()
    print("\nAccounts/Wallets:")
    if accounts:
        for a in accounts:
            a_dict = dict(a)
            print(f"  - [{a_dict['account_type']}] {a_dict['name']}: ₹{float(a_dict['current_balance']):,.2f}")
    else:
        print("  (No accounts registered)")

    # Recent Transactions
    t_query = "SELECT id, amount, transaction_type, COALESCE(note, '') as note, date FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 10"
    if db_engine.is_postgres():
        t_query = t_query.replace("?", "%s")
    cursor.execute(t_query, (user_id,))
    txs = cursor.fetchall()
    print(f"\nRecent Transactions ({len(txs)}):")
    if txs:
        for t in txs:
            t_dict = dict(t)
            print(f"  - {t_dict['date']} | {t_dict['transaction_type'].upper():<7} | ₹{float(t_dict['amount']):,.2f} | {t_dict['note']}")
    else:
        print("  (No transactions logged yet)")
    
    conn.close()

def export_users_csv(filename="users_export.csv"):
    conn = db_engine.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, phone, created_at, is_verified FROM users ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    
    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Name", "Email", "Phone", "Created At", "Is Verified"])
        for r in rows:
            r_dict = dict(r)
            writer.writerow([r_dict['id'], r_dict['name'], r_dict['email'], r_dict.get('phone', ''), r_dict.get('created_at', ''), r_dict.get('is_verified', '')])
            
    print(f"\n[SUCCESS] Exported {len(rows)} users to {filename} successfully!")

if __name__ == "__main__":
    print_banner()
    u_cnt, t_cnt, a_cnt = get_stats()
    print(f"Total Users: {u_cnt} | Total Accounts: {a_cnt} | Total Transactions: {t_cnt}")
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--export":
            export_users_csv()
        elif arg.isdigit():
            inspect_user(int(arg))
    else:
        list_users(limit=15)
        print("\nCommands:")
        print("  python admin_viewer.py          -> View recent users")
        print("  python admin_viewer.py <user_id> -> Deep inspect a specific user")
        print("  python admin_viewer.py --export  -> Export users to users_export.csv")
