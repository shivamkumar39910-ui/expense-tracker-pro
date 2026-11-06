import time
import json
import urllib.request
import urllib.error

BASE_URL = "https://expense-tracker-pro-ecl2.onrender.com/api/v1"

def time_request(name, method, url, headers=None, body=None):
    if headers is None:
        headers = {}
    headers["Content-Type"] = "application/json"
    headers["User-Agent"] = "Benchmark/1.0"
    
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            duration = round((time.time() - t0) * 1000, 1)
            raw = resp.read().decode("utf-8")
            res_data = json.loads(raw) if raw else {}
            print(f"[{name}] {resp.status} - {duration}ms")
            return res_data, duration
    except urllib.error.HTTPError as e:
        duration = round((time.time() - t0) * 1000, 1)
        raw = e.read().decode("utf-8", errors="ignore")
        print(f"[{name}] HTTP {e.code} after {duration}ms: {raw[:200]}")
        return None, duration
    except Exception as e:
        duration = round((time.time() - t0) * 1000, 1)
        print(f"[{name}] FAILED after {duration}ms: {e}")
        return None, duration

print("=== STARTING LIVE PRODUCTION BENCHMARK ===")
# Register new benchmark user
email = f"perf_user_{int(time.time())}@finance.com"
res, d = time_request("POST /auth/register", "POST", f"{BASE_URL}/auth/register", body={
    "name": "Perf User",
    "email": email,
    "password": "password123",
    "confirm_password": "password123"
})

if res and res.get("success"):
    # Login directly
    res_login, _ = time_request("POST /auth/login", "POST", f"{BASE_URL}/auth/login", body={
        "identifier": email,
        "password": "password123"
    })
    
    if res_login and res_login.get("success"):
        token = res_login.get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Benchmark all endpoints
        time_request("GET /accounts", "GET", f"{BASE_URL}/accounts", headers=headers)
        time_request("GET /categories", "GET", f"{BASE_URL}/categories", headers=headers)
        time_request("GET /transactions", "GET", f"{BASE_URL}/transactions", headers=headers)
        time_request("GET /command-center/summary", "GET", f"{BASE_URL}/command-center/summary", headers=headers)
        time_request("GET /budgets", "GET", f"{BASE_URL}/budgets", headers=headers)
        time_request("GET /notifications", "GET", f"{BASE_URL}/notifications", headers=headers)
        time_request("GET /goals", "GET", f"{BASE_URL}/goals", headers=headers)
        time_request("GET /charts/breakdown", "GET", f"{BASE_URL}/charts/breakdown", headers=headers)
        time_request("GET /charts/history-6m", "GET", f"{BASE_URL}/charts/history-6m", headers=headers)

        # Create 1 expense
        res_post, _ = time_request("POST /transactions", "POST", f"{BASE_URL}/transactions", headers=headers, body={
            "account_id": 1,
            "category_id": 1,
            "transaction_type": "EXPENSE",
            "amount": 150.0,
            "date": "2026-11-06",
            "note": "Perf test expense"
        })
        if res_post and res_post.get("success"):
            tx_id = res_post.get("transaction_id")
            time_request(f"DELETE /transactions/{tx_id}", "DELETE", f"{BASE_URL}/transactions/{tx_id}", headers=headers)
    else:
        print("Login failed:", res_login)
else:
    print("Registration failed:", res)
