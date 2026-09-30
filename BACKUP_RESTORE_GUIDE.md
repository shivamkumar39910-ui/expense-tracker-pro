# EXPENSE TRACKER PRO 2.0 - BACKUP & RESTORE GUIDE
**Document Version:** 2.0.0-PROD  
**Database Engines:** PostgreSQL (Render Cloud Managed) & SQLite (Local Fallback)  

---

## 1. BACKUP STRATEGY OVERVIEW

Expense Tracker Pro 2.0 utilizes a multi-tiered disaster recovery strategy to protect financial data against data corruption, accidental deletion, or hosting outages.

```
+-------------------------------------------------------------+
|                      PRODUCTION (RENDER)                    |
|  - Continuous WAL Archiving & Daily Automated Backups       |
|  - Point-In-Time Recovery (PITR) Enabled                    |
|  - Manual Snapshots prior to schema modifications           |
+------------------------------+------------------------------+
                               |
                               v pg_dump / CLI export
+-------------------------------------------------------------+
|                      COLD ARCHIVE / DISASTER RECOVERY       |
|  - JSON / CSV User Data Exports                             |
|  - Verified SQLite Snapshot (`expenses.db.backup`)          |
|  - Standby Schema Replay via `db_migration.py`              |
+-------------------------------------------------------------+
```

---

## 2. PRODUCTION POSTGRESQL BACKUP (RENDER)

### 2.1 Automated Managed Backups
- Render provides daily automated snapshots of the managed PostgreSQL database (`expense-tracker-db`).
- Backups are retained in secure cloud storage with encryption at rest.

### 2.2 Manual On-Demand Snapshot (`pg_dump`)
To create an immediate local snapshot of the live production database:
```bash
pg_dump "$DATABASE_URL" -Fc -f "expense_tracker_backup_$(date +%Y%m%d_%H%M%S).dump"
```
Or for plain SQL schema + data:
```bash
pg_dump "$DATABASE_URL" --clean --if-exists > "expense_tracker_backup_$(date +%Y%m%d_%H%M%S).sql"
```

---

## 3. PRODUCTION RESTORE PLAYBOOK

### 3.1 Restoring to a Standby PostgreSQL Instance
1. Provision a new PostgreSQL instance or clean target database.
2. Set the `DATABASE_URL` environment variable.
3. Re-run schema initialization:
   ```bash
   python -c "import database; database.create_database()"
   ```
4. Restore data from custom dump:
   ```bash
   pg_restore -d "$DATABASE_URL" --no-owner --clean "expense_tracker_backup.dump"
   ```
5. Verify row counts and financial totals:
   ```bash
   python -c "import db_migration, db_engine; conn = db_engine.get_db_connection(); db_migration.verify_data_integrity(None, conn)"
   ```

---

## 4. LOCAL SQLITE BACKUP & MIGRATION TO POSTGRESQL

### 4.1 SQLite Online Backup
To create a transactionally safe hot backup of `expenses.db`:
```python
import sqlite3

def backup_sqlite(source="expenses.db", target="expenses_backup.db"):
    src_conn = sqlite3.connect(source)
    dst_conn = sqlite3.connect(target)
    with dst_conn:
        src_conn.backup(dst_conn, pages=100)
    dst_conn.close()
    src_conn.close()
    print("SQLite backup completed successfully.")
```

### 4.2 SQLite to PostgreSQL Migration via `db_migration.py`
The built-in migration engine safely migrates all 16 tables in strict topological order:
```bash
python db_migration.py
```
**Migration Verification Checklist:**
- [x] Zero duplicate user records.
- [x] Exact balance and currency symbol preservation.
- [x] Foreign key dependencies maintained (`ON DELETE CASCADE`).
- [x] Auto-increment sequences reset to `MAX(id) + 1`.
- [x] All 86 automated tests pass after migration.
