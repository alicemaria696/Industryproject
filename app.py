from flask import Flask, request, jsonify
import mysql.connector
import jwt
import datetime
import os
import time
import secrets
import requests

app = Flask(__name__)

SECRET = os.getenv("SECRET_KEY", "ZEROTRUSTSECRETKEY")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "devuser")
DB_PASS = os.getenv("DB_PASS", "dev@user1")
DB_NAME = os.getenv("DB_NAME", "assessment_system")
DB_PORT = int(os.getenv("DB_PORT", 3306))

# Fast2SMS Configuration
FAST2SMS_API_KEY = os.getenv("FAST2SMS_API_KEY", "")
FAST2SMS_API_URL = "https://www.fast2sms.com/dev/bulkV2"

def get_db_connection():
    """Create a new database connection with retry logic"""
    max_retries = 5
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            connection = mysql.connector.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASS,
                database=DB_NAME,
                port=DB_PORT
            )
            print(f"✓ Database connected successfully on attempt {attempt + 1}")
            return connection
        except mysql.connector.Error as err:
            print(f"✗ Database connection failed (attempt {attempt + 1}/{max_retries}): {err}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise
    
    return None

def normalize_phone(phone):
    """Normalize phone number to +91 format for consistency with database"""
    phone = phone.strip()
    # Remove any existing +91 prefix
    if phone.startswith('+91'):
        phone = phone[3:]
    elif phone.startswith('91'):
        phone = phone[2:]
    # Remove leading 0 if present
    if phone.startswith('0'):
        phone = phone[1:]
    # Return with +91 prefix in the format stored in database
    phone = phone[-10:]  # Keep last 10 digits
    return f"+91{phone}"

def send_sms_via_fast2sms(phone, otp):
    """Send OTP via Fast2SMS API (India)"""
    if not FAST2SMS_API_KEY:
        print("⚠ Fast2SMS API key not configured. Skipping SMS delivery.")
        return {"success": False, "message": "API key not configured"}
    
    try:
        # Format phone number: ensure it's in international format with country code
        normalized_phone = normalize_phone(phone)
        # Fast2SMS expects format: 919XXXXXXXXX (without +)
        phone_to_send = normalized_phone.replace("+", "")
        
        print(f"DEBUG SMS: Phone to send: {phone_to_send}, Normalized: {normalized_phone}")
        
        # Fast2SMS API uses GET request with query parameters
        params = {
            "authorization": FAST2SMS_API_KEY,
            "route": "otp",
            "numbers": phone_to_send,
            "variables_values": otp,  # OTP value goes here
            "flash": "0"
        }
        
        print(f"DEBUG SMS: Sending GET request to Fast2SMS with params: {params}")
        print(f"DEBUG SMS: Full URL: {FAST2SMS_API_URL}?{('&').join([f'{k}={v}' for k,v in params.items()])}")
        
        response = requests.get(FAST2SMS_API_URL, params=params, timeout=10)
        
        print(f"DEBUG SMS: Response status code: {response.status_code}")
        print(f"DEBUG SMS: Response body: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"DEBUG SMS: API returned: {result}")
            
            # Check for success - Fast2SMS returns different formats
            is_success = (
                result.get("return") == True or 
                result.get("return") == "true" or
                result.get("return") == 1 or
                result.get("status") == "success" or
                result.get("success") == True or
                (result.get("return") and isinstance(result.get("return"), int) and result.get("return") > 0) or
                result.get("request_id")
            )
            
            if is_success:
                print(f"✓ SMS sent successfully to {phone_to_send} via Fast2SMS")
                return {"success": True, "message": "SMS sent successfully"}
            else:
                error_msg = result.get('message') or result.get('error') or result.get('msg') or 'Unknown error'
                print(f"✗ Fast2SMS API error: {error_msg}")
                return {"success": False, "message": str(error_msg)}
        else:
            print(f"✗ Fast2SMS API error (Status {response.status_code}): {response.text}")
            if response.status_code == 404:
                print("✗ 404 Error - Endpoint or parameters may be incorrect")
            return {"success": False, "message": f"API error: {response.status_code}"}
    
    except requests.exceptions.Timeout:
        print("✗ Fast2SMS API request timeout")
        return {"success": False, "message": "API request timeout"}
    except requests.exceptions.ConnectionError:
        print("✗ Fast2SMS API connection error")
        return {"success": False, "message": "API connection error"}
    except Exception as e:
        print(f"✗ Error sending SMS via Fast2SMS: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}

@app.route("/send-otp", methods=["POST"])
def send_otp():
    try:
        if not request.json:
            return jsonify({"error": "No JSON data provided"}), 400
        
        phone = request.json.get("phone", "").strip()
        
        # Validate phone number format
        if not phone or len(phone) < 10:
            return jsonify({"error": "Invalid phone number. Must be at least 10 digits."}), 400
        
        # Generate 6-digit numeric OTP
        otp = str(secrets.randbelow(1000000)).zfill(6)
        
        # Normalize phone number for consistency
        normalized_phone = normalize_phone(phone)
        print(f"DEBUG: Original phone: {phone}, Normalized phone: {normalized_phone}")

        db = get_db_connection()
        cursor = db.cursor()
        
        # Clear old OTPs for this phone (keep only active ones)
        cursor.execute(
            "DELETE FROM auth_otp_log WHERE phone=%s AND created_at < DATE_SUB(NOW(), INTERVAL 10 MINUTE)",
            (normalized_phone,)
        )
        
        # Insert new OTP with 5-minute expiry
        cursor.execute(
            "INSERT INTO auth_otp_log (phone, otp) VALUES (%s, %s)",
            (normalized_phone, otp)
        )
        db.commit()
        cursor.close()
        db.close()

        print(f"✓ OTP '{otp}' saved to database for {normalized_phone}")
        
        # Send OTP via Fast2SMS (non-blocking, doesn't affect response)
        sms_result = send_sms_via_fast2sms(normalized_phone, otp)
        
        response_message = f"OTP sent to {normalized_phone}"
        if sms_result["success"]:
            response_message += " via SMS"
        else:
            response_message += " (SMS delivery status: " + sms_result.get("message", "pending") + ")"
        
        return jsonify({
            "status": "OTP sent",
            "phone": phone,
            "message": response_message,
            "sms_delivery": sms_result["success"],
            "otp": otp  # Display OTP for testing
        }), 200
    
    except mysql.connector.Error as db_err:
        print(f"✗ Database error sending OTP: {db_err}")
        return jsonify({"error": f"Database error: {str(db_err)}"}), 500
    except Exception as e:
        print(f"✗ Error sending OTP: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/verify-otp", methods=["POST"])
def verify():
    try:
        if not request.json:
            return jsonify({"error": "No JSON data provided"}), 400
        
        phone = request.json.get("phone", "").strip()
        otp = request.json.get("otp", "").strip()

        if not phone or not otp:
            return jsonify({"error": "Phone and OTP are required"}), 400
        
        # Normalize phone number for consistency
        normalized_phone = normalize_phone(phone)
        print(f"DEBUG: Verifying OTP for original phone: {phone}, normalized: {normalized_phone}, OTP: {otp}")

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Check for valid OTP within 5-minute window
        cursor.execute("""
            SELECT * FROM auth_otp_log 
            WHERE phone=%s 
            AND otp=%s 
            AND created_at > DATE_SUB(NOW(), INTERVAL 5 MINUTE)
            ORDER BY created_at DESC 
            LIMIT 1
        """, (normalized_phone, otp))

        record = cursor.fetchone()

        if not record:
            print(f"DEBUG: No OTP record found for {normalized_phone}")
            cursor.close()
            db.close()
            return jsonify({"error": "Invalid or expired OTP"}), 401

        print(f"DEBUG: OTP record found, checking user in auth_identity...")
        # Query auth_identity for user
        cursor.execute("SELECT * FROM auth_identity WHERE phone=%s", (normalized_phone,))
        user = cursor.fetchone()
        
        cursor.close()
        db.close()

        if not user:
            print(f"DEBUG: User not found in auth_identity for phone {normalized_phone}")
            return jsonify({"error": "User not found. Please register first."}), 404
        
        print(f"DEBUG: User found - reg_id: {user.get('reg_id')}, role: {user.get('role')}")

        # Generate JWT token with SECRET from environment
        token = jwt.encode({
            "reg_id": user["reg_id"],
            "phone": phone,
            "role": user["role"],
            "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
        }, SECRET, algorithm="HS256")

        print(f"✓ OTP verified for {normalized_phone}, user: {user['reg_id']}")
        return jsonify({"token": token, "role": user["role"], "reg_id": user["reg_id"]}), 200
    
    except mysql.connector.Error as db_err:
        print(f"✗ Database error verifying OTP: {db_err}")
        return jsonify({"error": f"Database error: {str(db_err)}"}), 500
    except Exception as e:
        print(f"✗ Error verifying OTP: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
