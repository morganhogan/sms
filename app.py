import os
import requests
import random
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allows frontend to call this backend

# 🔐 SECURITY: Key is now pulled from Render's Environment Variables
# In Render Dashboard, add: MOBILESASA_API_KEY
API_KEY = os.environ.get("MOBILESASA_API_KEY", "XNiKXQXpVBLHtjVpJ89dqqUcW6K0BPJHYJmOUpoPmM9NUQSF1qPn9UypVxBv")
SENDER_ID = "MOBILESASA"
API_URL = "https://api.mobilesasa.com/v1/send/message"

# ⚠️ In-memory store (Will clear if Render puts the app to sleep on Free Tier)
otp_store = {}

def validate_phone(phone):
    # Validates Kenyan format 2547XXXXXXXX or 2541XXXXXXXX
    return bool(re.match(r'^254[71]\d{8}$', phone.strip()))

def generate_otp():
    return str(random.randint(100000, 999999))

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "online", "message": "OTP Service is running"}), 200

@app.route('/api/send-otp', methods=['POST'])
def send_otp():
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
        
    phone = data.get('phone', '').strip()
    
    if not validate_phone(phone):
        return jsonify({"success": False, "message": "Invalid phone format. Use 2547XXXXXXXX"}), 400
    
    otp = generate_otp()
    otp_store[phone] = {
        "code": otp,
        "expires_at": datetime.now() + timedelta(minutes=5),
        "attempts": 0
    }
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    payload = {
        "senderID": SENDER_ID,
        "phone": phone,
        "message": f"Your verification code is: {otp}. Valid for 5 minutes. Do not share."
    }
    
    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        result = resp.json()
        
        # Check both possible success indicators from MobileSasa
        if result.get("status") is True or result.get("responseCode") == "0200":
            return jsonify({"success": True, "message": "Code sent!"})
        else:
            return jsonify({"success": False, "message": result.get("message", "Failed to send")}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    phone = data.get('phone', '').strip()
    user_code = data.get('code', '').strip()
    
    if phone not in otp_store:
        return jsonify({"success": False, "message": "No code found. Request a new one."}), 400
    
    stored = otp_store[phone]
    
    if stored["attempts"] >= 3:
        del otp_store[phone]
        return jsonify({"success": False, "message": "Too many attempts. Request a new code."}), 400
    
    if datetime.now() > stored["expires_at"]:
        del otp_store[phone]
        return jsonify({"success": False, "message": "Code expired. Request a new one."}), 400
    
    stored["attempts"] += 1
    
    if stored["code"] == user_code:
        del otp_store[phone]
        return jsonify({"success": True, "message": "Verification successful!"})
    else:
        remaining = 3 - stored["attempts"]
        msg = "Incorrect code." + (f" {remaining} attempt(s) left." if remaining > 0 else " Request a new code.")
        if remaining <= 0:
            del otp_store[phone]
        return jsonify({"success": False, "message": msg}), 400

if __name__ == '__main__':
    # Bind to PORT provided by Render, or default to 5000 for local testing
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)