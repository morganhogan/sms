import os
import requests
import random
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS

app = Flask(__name__)

# ✅ Configure CORS properly
CORS(app, 
     resources={r"/*": {"origins": "*"}},
     supports_credentials=True,
     methods=["GET", "POST", "OPTIONS", "PUT", "DELETE"],
     allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"]
)

# ✅ Add manual CORS headers for all responses
@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Accept,X-Requested-With')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS,PUT,DELETE')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

# 🔐 API Configuration
API_KEY = os.environ.get("MOBILESASA_API_KEY", "XNiKXQXpVBLHtjVpJ89dqqUcW6K0BPJHYJmOUpoPmM9NUQSF1qPn9UypVxBv")
SENDER_ID = "MOBILESASA"
API_URL = "https://api.mobilesasa.com/v1/send/message"

# In-memory OTP store (use Redis/Database in production)
otp_store = {}

def validate_phone(phone):
    """Validate Kenyan phone number format: 2547XXXXXXXX or 2541XXXXXXXX"""
    return bool(re.match(r'^254[71]\d{8}$', phone.strip()))

def generate_otp():
    """Generate 6-digit OTP"""
    return str(random.randint(100000, 999999))

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "online", 
        "message": "OTP Service is running",
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route('/api/send-otp', methods=['POST', 'OPTIONS'])
def send_otp():
    """Send OTP to phone number"""
    
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = make_response('', 200)
        return response
    
    # Validate request body
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": "Invalid JSON format"}), 400
    
    # Get and validate phone number
    phone = data.get('phone', '').strip()
    
    if not phone:
        return jsonify({"success": False, "message": "Phone number is required"}), 400
    
    if not validate_phone(phone):
        return jsonify({
            "success": False, 
            "message": "Invalid phone format. Use 2547XXXXXXXX (e.g., 254712345678)"
        }), 400
    
    # Generate and store OTP
    otp = generate_otp()
    otp_store[phone] = {
        "code": otp,
        "expires_at": datetime.now() + timedelta(minutes=5),
        "attempts": 0,
        "created_at": datetime.now().isoformat()
    }
    
    # Prepare SMS payload
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
    
    # Send SMS via MobileSasa API
    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        result = resp.json()
        
        # Check for success
        if result.get("status") is True or result.get("responseCode") == "0200":
            return jsonify({
                "success": True, 
                "message": "Code sent successfully!",
                "phone": phone
            }), 200
        else:
            error_msg = result.get("message", "Failed to send SMS")
            return jsonify({"success": False, "message": error_msg}), 500
            
    except requests.exceptions.Timeout:
        return jsonify({"success": False, "message": "SMS service timeout. Please try again."}), 502
    except requests.exceptions.ConnectionError:
        return jsonify({"success": False, "message": "Cannot connect to SMS service"}), 502
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/api/verify-otp', methods=['POST', 'OPTIONS'])
def verify_otp():
    """Verify OTP code"""
    
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = make_response('', 200)
        return response
    
    # Validate request body
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": "Invalid JSON format"}), 400
    
    # Get phone and code
    phone = data.get('phone', '').strip()
    user_code = data.get('code', '').strip()
    
    if not phone or not user_code:
        return jsonify({
            "success": False, 
            "message": "Phone number and code are required"
        }), 400
    
    # Check if OTP exists
    if phone not in otp_store:
        return jsonify({
            "success": False, 
            "message": "No code found. Please request a new one."
        }), 400
    
    stored = otp_store[phone]
    
    # Check if expired
    if datetime.now() > stored["expires_at"]:
        del otp_store[phone]
        return jsonify({
            "success": False, 
            "message": "Code expired. Please request a new one."
        }), 400
    
    # Check max attempts
    if stored["attempts"] >= 3:
        del otp_store[phone]
        return jsonify({
            "success": False, 
            "message": "Too many failed attempts. Please request a new code."
        }), 400
    
    # Increment attempts
    stored["attempts"] += 1
    
    # Verify code
    if stored["code"] == user_code:
        # Success - remove OTP
        del otp_store[phone]
        return jsonify({
            "success": True, 
            "message": "Verification successful!"
        }), 200
    else:
        # Failed - return remaining attempts
        remaining = 3 - stored["attempts"]
        if remaining > 0:
            msg = f"Incorrect code. {remaining} attempt(s) left."
        else:
            msg = "Incorrect code. No attempts left. Request a new code."
            del otp_store[phone]
        
        return jsonify({
            "success": False, 
            "message": msg
        }), 400

@app.route('/api/resend-otp', methods=['POST', 'OPTIONS'])
def resend_otp():
    """Resend OTP to phone number"""
    
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = make_response('', 200)
        return response
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
    except:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400
    
    phone = data.get('phone', '').strip()
    
    if not validate_phone(phone):
        return jsonify({"success": False, "message": "Invalid phone format"}), 400
    
    # Check if OTP exists and not too recent
    if phone in otp_store:
        stored = otp_store[phone]
        time_since_creation = (datetime.now() - datetime.fromisoformat(stored["created_at"])).total_seconds()
        
        if time_since_creation < 30:
            return jsonify({
                "success": False, 
                "message": "Please wait 30 seconds before requesting a new code."
            }), 429
    
    # Generate new OTP
    otp = generate_otp()
    otp_store[phone] = {
        "code": otp,
        "expires_at": datetime.now() + timedelta(minutes=5),
        "attempts": 0,
        "created_at": datetime.now().isoformat()
    }
    
    # Send SMS
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    payload = {
        "senderID": SENDER_ID,
        "phone": phone,
        "message": f"Your new verification code is: {otp}. Valid for 5 minutes."
    }
    
    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        result = resp.json()
        
        if result.get("status") is True or result.get("responseCode") == "0200":
            return jsonify({
                "success": True, 
                "message": "New code sent!"
            }), 200
        else:
            return jsonify({"success": False, "message": result.get("message", "Failed")}), 500
            
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "Method not allowed"}), 405

if __name__ == '__main__':
    # Get port from environment variable (Render) or default to 5000
    port = int(os.environ.get("PORT", 5000))
    
    print(f"🚀 Starting OTP Service on port {port}...")
    print(f"📱 Health check: http://localhost:{port}/")
    print(f"📤 Send OTP: http://localhost:{port}/api/send-otp")
    print(f"🔐 Verify OTP: http://localhost:{port}/api/verify-otp")
    
    # Run with threaded=True for better concurrency
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
