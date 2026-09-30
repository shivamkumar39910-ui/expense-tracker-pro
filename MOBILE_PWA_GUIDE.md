# EXPENSE TRACKER PRO 2.0 - MOBILE PWA USER & DEVELOPER GUIDE
**Document Version:** 2.0.0-PROD  
**Target Clients:** iOS Safari, Android Chrome, Desktop Edge / Chrome  
**PWA URL:** `https://expense-tracker-pro-ecl2.onrender.com/mobile`  

---

## 1. PWA ARCHITECTURE & CAPABILITIES

Expense Tracker Pro 2.0 is engineered as a mobile-first Progressive Web Application (PWA). It provides a native app experience inside the browser with zero store installation delays.

### Core PWA Highlights:
1. **App Shell Architecture:** Cached HTML/CSS/JS shell loads instantly (< 300ms) regardless of network speed.
2. **Standalone Display Mode:** Removes browser address bar and navigation controls, providing full-screen immersion.
3. **Ergonomic Bottom Navigation:** Thumb-reachable 5-destination navigation bar with elevated center Quick Add (+) action.
4. **Haptic Touch Response:** Subtle vibration feedback (`navigator.vibrate`) on keypresses and tab switches on supported hardware.
5. **Dark / OLED Black Themes:** Default battery-saving pure black OLED theme with instant light theme toggle.
6. **Offline Sync Queue:** Allows logging expenses without an active internet connection. Transactions queue in `localStorage` and automatically sync upon network restoration with a visual badge.

---

## 2. SERVICE WORKER & CACHING SPECIFICATION

- **Service Worker File:** `static/service-worker.js`
- **Cache Name:** `expense-tracker-pro-v2.0`
- **Caching Strategy:**
  - **Static Assets (CSS, Icons, Fonts, JS):** Cache-First with background revalidation.
  - **REST API Endpoints (`/api/v1/*`):** Network-First with graceful offline response fallback.
  - **Root Application Page (`/mobile`):** Stale-While-Revalidate to ensure instant cold starts.

---

## 3. INSTALLATION INSTRUCTIONS

### 3.1 On Android (Google Chrome)
1. Open Chrome and navigate to `https://expense-tracker-pro-ecl2.onrender.com/mobile`.
2. Tap the **Install App** banner at the top of the Home screen, or tap Chrome's three-dot menu `⋮` and select **Add to Home screen** / **Install app**.
3. Confirm the prompt. The app icon will appear on your device home screen and app drawer.

### 3.2 On iOS (Apple Safari)
1. Open Safari and navigate to `https://expense-tracker-pro-ecl2.onrender.com/mobile`.
2. Tap the **Share** button (box with upward arrow) in the bottom navigation bar.
3. Scroll down and select **Add to Home Screen**.
4. Tap **Add** in the top right corner. The app will launch as a full-screen native experience.

---

## 4. SCREEN DIRECTORY & GESTURE MAP

| Tab / Screen | Purpose & Controls |
| :--- | :--- |
| **Home (Command Center)** | Net worth breakdown, monthly cashflow, quick action pills, upcoming bill banner, predictive risk alerts. |
| **Ledger (Transactions)** | Complete transaction history, search bar, type filters (Expense, Income, Transfer), swipe-to-delete. |
| **Quick Add (+) FAB** | Numerical keypad, account selector, category pills, custom date toggle (Today, Yesterday, Custom). |
| **Forecast Engine 2.0** | Month-end projection, daily velocity gauge, historical WMA comparison, explainable tips. |
| **Profile & Tools Hub** | Multi-account management, budget caps, recurring bill manager, goals, CSV export, SMS parser, PIN lock. |
