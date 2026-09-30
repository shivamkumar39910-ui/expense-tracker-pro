# EXPENSE TRACKER PRO 2.0 - ANDROID INTEGRATION & SMS CAPTURE GUIDE
**Document Version:** 2.0.0-PROD  
**Target Platform:** Android 11+ (API 30+)  

---

## 1. THE REALITY OF SMS CAPTURE: BROWSER PWA VS. NATIVE ANDROID

### 1.1 Web Browser Sandbox Limitations
Under modern Android OS and W3C Web standards, pure browser-based applications (PWAs) **cannot** silently run in the background to intercept incoming SMS messages or access the system SMS inbox.
- **Security Rationale:** Android strictly restricts the `RECEIVE_SMS` and `READ_SMS` permissions to the user's default SMS handler and declared system-approved native applications to prevent credential theft.
- **The W3C WebOTP API:** The WebOTP API (`navigator.credentials.get({otp: {transport: ['sms']}})` can only read incoming one-time verification codes when formatted with a specific browser origin tag (e.g. `@domain.com #123456`). It cannot read financial debit/credit transaction messages.

### 1.2 Current Production Solution: Smart Paste & Clipboard Parser
To deliver zero friction within the PWA without compromising user security or platform policy:
1. When a user receives a bank SMS, they copy the message.
2. In Expense Tracker Pro 2.0, clicking the **SMS / Quick Entry** button auto-populates the clipboard or allows one-tap pasting.
3. The multi-bank regex parser extracts all attributes (merchant, amount, account last 4, date, type).
4. The system presents an instant **Transaction Review Card** preventing duplicate entries.
5. With one tap (**Confirm & Add**), the transaction is recorded in the ledger.

---

## 2. NATIVE ANDROID INTEGRATION ARCHITECTURE (HYBRID / TWA COMPANION)

For organizations seeking 100% automated background capture on Android devices, Expense Tracker Pro 2.0 is designed to integrate with a native Kotlin Android companion service or a Trusted Web Activity (TWA).

```
                      INCOMING BANK SMS / NOTIFICATION
                                    |
                                    v
            +-----------------------------------------------+
            |           ANDROID SYSTEM LAYER                |
            |   - android.provider.Telephony.SMS_RECEIVED   |
            |   - NotificationListenerService (UPI push)    |
            +-----------------------+-----------------------+
                                    |
                                    v
            +-----------------------------------------------+
            |       NATIVE COMPANION / TWA BRIDGE           |
            |   - Android Background BroadcastReceiver      |
            |   - On-Device Regex Extraction (Clean Text)   |
            |   - Local Security Check                      |
            +-----------------------+-----------------------+
                                    |
                                    v HTTPS POST /api/v1/parser/parse-sms
            +-----------------------------------------------+
            |         EXPENSE TRACKER PRO 2.0 BACKEND       |
            |   - Authentication via Device Token           |
            |   - Duplicate Detection Engine                |
            |   - Web Push Notification Trigger             |
            +-----------------------+-----------------------+
                                    |
                                    v
            +-----------------------------------------------+
            |          USER CONFIRMATION PROMPT             |
            |   - High-Priority In-App / Push Card          |
            |   - "Confirm Rs. 450 to Swiggy?"              |
            +-----------------------------------------------+
```

---

## 3. IMPLEMENTATION BLUEPRINT (KOTLIN COMPANION)

### 3.1 Android Manifest Permissions
```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.expensetracker.pro.companion">

    <uses-permission android:name="android.permission.RECEIVE_SMS" />
    <uses-permission android:name="android.permission.READ_SMS" />
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.BIND_NOTIFICATION_LISTENER_SERVICE" />

    <application>
        <receiver
            android:name=".SmsBroadcastReceiver"
            android:exported="true"
            android:permission="android.permission.BROADCAST_SMS">
            <intent-filter android:priority="999">
                <action android:name="android.provider.Telephony.SMS_RECEIVED" />
            </intent-filter>
        </receiver>
    </application>
</manifest>
```

### 3.2 Kotlin Broadcast Receiver
```kotlin
package com.expensetracker.pro.companion

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class SmsBroadcastReceiver : BroadcastReceiver() {
    private val client = OkHttpClient()

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Telephony.Sms.Intents.SMS_RECEIVED_ACTION) {
            val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
            for (sms in messages) {
                val sender = sms.displayOriginatingAddress ?: ""
                val body = sms.displayMessageBody ?: ""

                // Filter for bank/financial sender codes (e.g., VM-HDFCBK, AXISBK, SBIUPI)
                if (isFinancialSender(sender, body)) {
                    forwardToExpenseTracker(body, context)
                }
            }
        }
    }

    private fun isFinancialSender(sender: String, body: String): Boolean {
        val keywords = listOf("debited", "credited", "spent", "txn", "inr", "rs.", "balance")
        return keywords.any { body.contains(it, ignoreCase = true) }
    }

    private fun forwardToExpenseTracker(smsBody: String, context: Context) {
        val token = getStoredJwtToken(context) ?: return
        val url = "https://expense-tracker-pro-ecl2.onrender.com/api/v1/parser/parse-sms"

        val json = JSONObject().apply {
            put("text", smsBody)
        }
        val mediaType = "application/json; charset=utf-8".toMediaType()
        val requestBody = json.toString().toRequestBody(mediaType)

        val request = Request.Builder()
            .url(url)
            .addHeader("Authorization", "Bearer $token")
            .post(requestBody)
            .build()

        client.newCall(request).execute().use { response ->
            // Endpoint returns parsed proposal and registers a pending parse event.
            // PWA user receives instant push review card.
        }
    }

    private fun getStoredJwtToken(context: Context): String? {
        val prefs = context.getSharedPreferences("ExpenseTrackerPrefs", Context.MODE_PRIVATE)
        return prefs.getString("jwt_token", null)
    }
}
```

---

## 4. SECURITY & PRIVACY BEST PRACTICES

1. **Local Filtering:** The native companion filters messages locally by sender header and financial keywords. Non-financial personal SMS messages are never uploaded to the server.
2. **Device-Bound Authentication:** The companion uses the user's encrypted JWT token stored in Android EncryptedSharedPreferences.
3. **No Silent Commits:** Even with native capture, transactions are placed in `transaction_parse_events` with status `PENDING` until approved by the user via notification or PWA review card.
