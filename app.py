from flask import Flask, request, jsonify
import mysql.connector
import bcrypt
import os
import time

app = Flask(__name__)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "devuser")
DB_PASS = os.getenv("DB_PASS", "dev@user1")
DB_NAME = os.getenv("DB_NAME", "assessment_system")
DB_PORT = int(os.getenv("DB_PORT", 3306))

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

@app.route("/register", methods=["POST"])
def register():
    try:
        data = request.json

        reg_id = data["reg_id"]
        phone = data["phone"]
        password = data["password"]
        role = data["role"]
        
        # Normalize phone number for consistency
        normalized_phone = normalize_phone(phone)
        print(f"DEBUG: Registering user with phone: {phone} → normalized: {normalized_phone}")

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        db = get_db_connection()
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO auth_identity (reg_id, phone, role)
            VALUES (%s,%s,%s)
        """, (reg_id, normalized_phone, role))

        auth_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO auth_credentials (auth_id, password_hash)
            VALUES (%s,%s)
        """, (auth_id, hashed))

        db.commit()
        
        
        if role.upper() in ['S', 'STUDENT']:
            cursor.execute("""
                INSERT INTO student (reg_id, name, email, department, class_, password)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (reg_id, reg_id, f"{reg_id}@student.local", "General", "Unassigned", hashed))
        elif role.upper() in ['T', 'TEACHER']:
            cursor.execute("""
                INSERT INTO teacher (reg_id, name, email, department, password)
                VALUES (%s, %s, %s, %s, %s)
            """, (reg_id, reg_id, f"{reg_id}@teacher.local", "General", hashed))
        elif role.upper() in ['A', 'ADMIN']:
            cursor.execute("""
                INSERT INTO user (reg_id, name, password, role)
                VALUES (%s, %s, %s, %s)
            """, (reg_id, reg_id, hashed, 'A'))
        
        db.commit()
        cursor.close()
        db.close()

        print(f"✓ User registered: {reg_id} ({normalized_phone}) with role {role}")
        return jsonify({"status": "success", "message": "User registered successfully"})
    
    except Exception as e:
        print(f"✗ Error during registration: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
