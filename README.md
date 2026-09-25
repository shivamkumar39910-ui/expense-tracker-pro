# 💰 Expense Tracker Pro — Full-Stack Expense Management System

**Expense Tracker Pro** is a full-stack financial management platform with analytics, Month-over-Month comparison, statistical anomaly detection, expense forecasting, AI recommendations, CSRF security, database performance indexing, and production deployment readiness.

---

## 🌟 Core Features Overview

1. **Authentication & Profile Management**:
   - Werkzeug password hashing & verification.
   - User profile customization (Name & Email updates with duplicate checks).
   - Password change authorization.

2. **Budget Management**:
   - Set and update monthly budgets.
   - Live budget progress bar, spent tracking, remaining balance, and status alerts (*Under Budget*, *Exceeded*, *No Budget*).

3. **Synchronized Analytics Dashboard (Phase 1 & Phase 2)**:
   - Synchronized Search, Category, Exact Date, Quick Range (*This Month*, *Last Month*, *Last 30 Days*), and Custom Date filters.
   - Real-time stat cards: Total Expense, Transactions Count, Avg Transaction, Daily Average Spend, Categories, Highest Category.
   - 4 Interactive Chart.js Visualizations:
     - 🍩 Expense Distribution (Doughnut)
     - 📈 Monthly Expense Trend (Bar)
     - 📊 Top Spending Categories (Horizontal Bar)
     - 📅 Daily Spending Trend (Line)

4. **Month-over-Month (MoM) Comparison**:
   - Tracks current month spending vs. previous month spending with percentage growth/decrease indicators.

5. **Smart Insights & AI Financial Mentor (Phase 3 & Phase 6)**:
   - Data-backed financial warnings (budget proximity, high category concentration >40%, spending acceleration).
   - Natural language executive financial summary and personalized budget recommendations.

6. **Statistical Anomaly Detection (Phase 4)**:
   - Z-score & standard deviation outlier radar flagging spiking transactions significantly above personal averages.

7. **Expense Forecasting Model (Phase 5)**:
   - Weighted Moving Average (WMA) with Trend Damping model forecasting next month's total spend and expected risk bounds.

8. **Security & Database Hardening (Phase 7 & Phase 8)**:
   - Foreign key constraint enforcement (`PRAGMA foreign_keys = ON;`).
   - Query performance indexes on `user_id`, `date`, `month/year`, and `email`.
   - CSRF protection, environment-based secret keys, secure cookies, brute-force rate limiting, and parameter-isolated ownership checks.

9. **UI/UX & Dark Mode (Phase 9)**:
   - Theme Switcher (Light Mode / Dark Mode) with `localStorage` persistence.
   - Global Toast Notification System (`showToast`).

---

## 🚀 Local Development Setup

1. **Clone & Navigate**:
   ```bash
   cd EXPENCE_PROJECT
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Application**:
   ```bash
   python app_web.py
   ```
   Open your browser at `http://127.0.0.1:5000`.

---

## 🌐 Production Deployment (Render / Railway)

### Deploying to Render
1. Push your repository to GitHub.
2. Log into [Render](https://render.com) and click **New +** -> **Web Service**.
3. Connect your repository. Render will automatically detect `render.yaml` and `Procfile`.
4. Configure Environment Variables:
   - `SECRET_KEY`: (Auto-generated or set your secret string)
   - `FLASK_ENV`: `production`
5. Click **Deploy Web Service**.

### Production Entrypoint
Under Gunicorn:
```bash
gunicorn app_web:app
```
