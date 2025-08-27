from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, flash, url_for, session, jsonify, send_file
from firebase_config import auth, db
import math
from datetime import datetime, timedelta
import qrcode
import io
import base64
import pandas as pd
from functools import wraps
from collections import defaultdict
import os
import sys
import time  # Add time import for debugging

# ------------------ CONFIG ------------------
CAMPUS_LAT = 28.72353
CAMPUS_LON = 77.22076
CAMPUS_RADIUS_METERS = 200

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
app.permanent_session_lifetime = timedelta(days=7)

# ------------------ ADMIN CREDENTIALS ------------------
ADMINS = {
    "foryoursakeiamhere@gmail.com": {"password": "farhanadmin1", "subject": "English", "role": "admin"},
    "math_teacher@gmail.com": {"password": "math123", "subject": "Math", "role": "admin"}
}

# ------------------ DECORATORS ------------------
def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'student':
            if request.is_json:
                return jsonify({"message": "Student login required."}), 401
            else:
                flash("Student login required.")
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("Admin login required.")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# ------------------ HELPER ------------------
def distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def get_teacher_db_key(email):
    """Consistent helper to convert email to database key"""
    return email.replace('.', ',')

# ------------------ ROUTES ------------------

@app.route('/')
def home():
    return redirect(url_for('login'))

# --------- STUDENT SIGNUP ----------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        sol_roll_no = request.form.get('sol_roll_no')
        dob = request.form.get('dob')
        phone_no = request.form.get('phone_no')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for('signup'))

        try:
            auth.create_user_with_email_and_password(email, password)
            db.child("users").child(get_teacher_db_key(email)).set({
                "role": "student",
                "name": name,
                "sol_roll_no": sol_roll_no,
                "dob": dob,
                "phone_no": phone_no
            })
            auth.sign_in_with_email_and_password(email, password)
            session['user'] = email
            session['role'] = "student"
            session.permanent = True
            flash("Signup successful! You are now logged in.")
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f"Error during signup: {e}")
            return redirect(url_for('signup'))

    return render_template('signup.html')

# --------- STUDENT LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if email in ADMINS:
            flash("Please use the admin login page.")
            return redirect(url_for('admin_login'))

        try:
            auth.sign_in_with_email_and_password(email, password)
            session['user'] = email
            session.permanent = True
            user_info = db.child("users").child(get_teacher_db_key(email)).get().val()
            session['role'] = user_info.get("role") if user_info else "student"
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash("Invalid credentials. Try again.")
            return redirect(url_for('login'))

    return render_template('login.html')

# --------- ADMIN LOGIN ----------
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if email in ADMINS and password == ADMINS[email]["password"]:
            session['user'] = email
            session['role'] = 'admin'
            session['subject'] = ADMINS[email]["subject"]
            session.permanent = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid admin credentials.")
            return redirect(url_for('admin_login'))

    return render_template('admin_login.html')

# --------- STUDENT DASHBOARD ----------
@app.route('/dashboard')
@student_required
def dashboard():
    user_info = db.child("users").child(get_teacher_db_key(session['user'])).get().val()
    name = user_info.get("name") if user_info else session['user']
    return render_template('dashboard.html', user=name, role=session.get('role'))

# --------- ADMIN DASHBOARD (FIXED VERSION) ----------
@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    teacher_email = session['user']
    subject = session.get('subject')
    
    print(f"\n--- ADMIN DASHBOARD LOG [{datetime.now()}] ---", flush=True)
    print(f"Teacher: {teacher_email}, Subject: {subject}", flush=True)
    
    teacher_db_key = get_teacher_db_key(teacher_email)
    read_path = f"attendance/{subject}/{teacher_db_key}"
    print(f"Reading from Firebase path: {read_path}", flush=True)
    
    all_records = []
    todays_records = []
    
    try:
        # Add a small delay to ensure Firebase write has propagated
        time.sleep(0.5)
        
        # Fetch data with error handling
        firebase_ref = db.child("attendance").child(subject).child(teacher_db_key)
        all_data = firebase_ref.get().val()
        
        print(f"Raw Firebase response: {type(all_data)}, {all_data is not None}", flush=True)
        
        if all_data and isinstance(all_data, dict):
            print(f"SUCCESS: Found {len(all_data)} total records", flush=True)
            all_records = [record for record in all_data.values() if isinstance(record, dict)]
            
            today_str = datetime.now().strftime('%Y-%m-%d')
            print(f"Filtering for today's date: {today_str}", flush=True)
            
            for record in all_records:
                if 'timestamp' in record:
                    record_timestamp = record.get('timestamp', '')
                    print(f"Checking record timestamp: {record_timestamp[:10] if len(record_timestamp) >= 10 else record_timestamp}", flush=True)
                    if record_timestamp.startswith(today_str):
                        todays_records.append(record)
                        print(f"Added today's record: {record.get('name', 'Unknown')}", flush=True)
            
            print(f"Found {len(todays_records)} records for today", flush=True)
        else:
            print("INFO: No attendance data found or invalid format", flush=True)
            
    except Exception as e:
        print(f"ERROR: Exception in admin_dashboard: {e}", flush=True)
        flash(f"Could not fetch attendance records: {e}")

    print("--- END ADMIN DASHBOARD LOG ---\n", flush=True)
    
    qr_data = session.get("qr_data")
    
    return render_template('admin_dashboard.html', 
                           user=teacher_email, 
                           records=todays_records, 
                           all_records_count=len(all_records),
                           subject=subject, 
                           qr_data=qr_data)

# --------- VIEW ATTENDANCE REPORT ----------
@app.route('/view_attendance')
@admin_required
def view_attendance():
    teacher_email = session['user']
    subject = session.get('subject')
    teacher_db_key = get_teacher_db_key(teacher_email)
    
    all_records = db.child("attendance").child(subject).child(teacher_db_key).get().val()
    daily_counts = defaultdict(int)
    
    if all_records and isinstance(all_records, dict):
        for record in all_records.values():
            try:
                if isinstance(record, dict) and 'timestamp' in record:
                    record_date = datetime.fromisoformat(record['timestamp']).strftime('%Y-%m-%d')
                    daily_counts[record_date] += 1
            except (ValueError, TypeError, AttributeError, KeyError):
                continue
                
    sorted_daily_counts = sorted(daily_counts.items())
    chart_labels = [item[0] for item in sorted_daily_counts]
    chart_data = [item[1] for item in sorted_daily_counts]
    
    return render_template('view_attendance.html', subject=subject, chart_labels=chart_labels, chart_data=chart_data)

# --------- GENERATE QR CODE ----------
@app.route('/generate_qr')
@admin_required
def generate_qr():
    subject = session.get('subject') 
    if not subject:
        flash("Could not find subject for your session.")
        return redirect(url_for('admin_dashboard'))

    teacher_email = session['user']
    qr_text = f"{teacher_email}|{subject}"
    
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(qr_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
    
    session["qr_data"] = "data:image/png;base64," + qr_b64
    flash("QR code generated successfully!")
    return redirect(url_for('admin_dashboard'))

# --------- MARK ATTENDANCE VIA QR (FIXED VERSION) ----------
@app.route('/mark_attendance_qr', methods=['POST'])
@student_required
def mark_attendance_qr():
    print(f"\n--- MARK ATTENDANCE LOG [{datetime.now()}] ---", flush=True)
    
    data = request.get_json()
    if not data or "qr_data" not in data or "latitude" not in data or "longitude" not in data:
        print("ERROR: Missing required data in request", flush=True)
        return jsonify({"message": "Missing required location or QR data."}), 400

    try:
        lat = float(data.get("latitude"))
        lon = float(data.get("longitude"))
        print(f"Student location: {lat}, {lon}", flush=True)
    except (ValueError, TypeError):
        print("ERROR: Invalid latitude/longitude values", flush=True)
        return jsonify({"message": "Invalid location data."}), 400

    # Check campus proximity
    campus_distance = distance(lat, lon, CAMPUS_LAT, CAMPUS_LON)
    print(f"Distance from campus: {campus_distance:.2f}m (limit: {CAMPUS_RADIUS_METERS}m)", flush=True)
    
    if campus_distance > CAMPUS_RADIUS_METERS:
        print("ERROR: Student outside campus", flush=True)
        return jsonify({"message": "You are outside the campus. Attendance not marked."}), 403

    # Parse QR code
    try:
        qr_data = data.get("qr_data")
        teacher_email, subject = qr_data.split("|")
        teacher_db_key = get_teacher_db_key(teacher_email)
        print(f"QR parsed - Teacher: {teacher_email}, Subject: {subject}", flush=True)
    except (ValueError, TypeError, AttributeError):
        print("ERROR: Invalid QR code format", flush=True)
        return jsonify({"message": "Invalid QR code format."}), 400

    try:
        student_email = session['user']
        student_db_key = get_teacher_db_key(student_email)
        
        # Get student details
        user_details = db.child("users").child(student_db_key).get().val()
        if not user_details or "name" not in user_details or "sol_roll_no" not in user_details:
            print("ERROR: Incomplete student profile", flush=True)
            return jsonify({"message": "Your profile is incomplete. Cannot mark attendance."}), 404
            
        student_name = user_details["name"]
        student_sol_roll_no = user_details["sol_roll_no"]
        print(f"Student details - Name: {student_name}, Roll: {student_sol_roll_no}", flush=True)

        # Check for duplicate attendance today
        attendance_ref = db.child("attendance").child(subject).child(teacher_db_key)
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        existing_records = attendance_ref.get().val()
        if existing_records and isinstance(existing_records, dict):
            for record in existing_records.values():
                if (isinstance(record, dict) and 
                    record.get("email") == student_email and 
                    record.get("timestamp", "").startswith(today_str)):
                    print(f"WARNING: Duplicate attendance attempt for {student_email}", flush=True)
                    return jsonify({"message": f"Attendance already marked for {subject} today."}), 409

        # Create new attendance record
        new_record = {
            "name": student_name,
            "sol_roll_no": student_sol_roll_no,
            "email": student_email,
            "timestamp": datetime.now().isoformat(),
            "latitude": lat,
            "longitude": lon,
            "inside_campus": True,
            "subject": subject,  # Add subject for clarity
            "teacher_email": teacher_email  # Add teacher for tracking
        }
        
        # Push to Firebase
        push_result = attendance_ref.push(new_record)
        print(f"SUCCESS: Attendance record created with key: {push_result['name']}", flush=True)
        print(f"Record details: {new_record}", flush=True)

        print("--- END MARK ATTENDANCE LOG ---\n", flush=True)
        return jsonify({"message": f"Attendance marked successfully for {subject}!"})
        
    except Exception as e:
        print(f"ERROR: Exception during attendance marking: {e}", flush=True)
        return jsonify({"message": "A server error occurred while saving the record."}), 500

# --------- DOWNLOAD ATTENDANCE EXCEL ----------
@app.route('/download_attendance')
@admin_required
def download_attendance():
    teacher_email = session.get('user')
    subject = session.get('subject')
    teacher_db_key = get_teacher_db_key(teacher_email)
    
    data = db.child("attendance").child(subject).child(teacher_db_key).get().val()

    columns = ['sol_roll_no', 'name', 'timestamp', 'email', 'latitude', 'longitude']
    
    records_list = []
    if data and isinstance(data, dict):
        records_list = [v for v in data.values() if isinstance(v, dict)]

    df = pd.DataFrame(records_list)
    
    # Ensure all required columns exist
    for col in columns:
        if col not in df.columns:
            df[col] = None
    df = df[columns]

    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine='openpyxl')
    buffer.seek(0)

    return send_file(buffer, as_attachment=True,
                     download_name=f"{subject}_attendance_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for('login'))

# Add this route to your app.py for debugging
@app.route('/debug_attendance')
@admin_required  
def debug_attendance():
    """Debug route to inspect Firebase data structure"""
    teacher_email = session['user']
    subject = session.get('subject')
    teacher_db_key = teacher_email.replace('.', ',')
    
    debug_info = {
        'session_data': {
            'user': session.get('user'),
            'role': session.get('role'), 
            'subject': session.get('subject')
        },
        'paths_checked': [],
        'data_found': {}
    }
    
    # Check multiple possible paths where data might be stored
    possible_paths = [
        f"attendance/{subject}/{teacher_db_key}",
        f"attendance/{teacher_db_key}/{subject}", 
        f"attendance/{teacher_db_key}",
        "attendance"
    ]
    
    for path_parts in [path.split('/') for path in possible_paths]:
        try:
            ref = db.child(path_parts[0])
            current_path = path_parts[0]
            
            for part in path_parts[1:]:
                ref = ref.child(part)
                current_path += f"/{part}"
            
            data = ref.get().val()
            debug_info['paths_checked'].append(current_path)
            
            if data:
                debug_info['data_found'][current_path] = {
                    'type': str(type(data)),
                    'keys': list(data.keys()) if isinstance(data, dict) else None,
                    'count': len(data) if isinstance(data, (dict, list)) else None,
                    'sample': str(data)[:500] + '...' if len(str(data)) > 500 else str(data)
                }
        except Exception as e:
            debug_info['data_found'][current_path] = f"Error: {e}"
    
    # Also check the entire attendance structure
    try:
        all_attendance = db.child("attendance").get().val()
        debug_info['full_attendance_structure'] = str(all_attendance)[:1000] + '...' if all_attendance and len(str(all_attendance)) > 1000 else str(all_attendance)
    except Exception as e:
        debug_info['full_attendance_structure'] = f"Error: {e}"
    
    return jsonify(debug_info)

# Add this route to test Firebase writes directly
@app.route('/test_write')
@admin_required
def test_write():
    """Test Firebase write operation"""
    teacher_email = session['user']
    subject = session.get('subject')
    teacher_db_key = teacher_email.replace('.', ',')
    
    test_record = {
        'name': 'Test Student',
        'sol_roll_no': '23-1-11-000001',
        'email': 'test@example.com',
        'timestamp': datetime.now().isoformat(),
        'test_write': True
    }
    
    try:
        # Try writing to the expected path
        path = f"attendance/{subject}/{teacher_db_key}"
        result = db.child("attendance").child(subject).child(teacher_db_key).push(test_record)
        
        return jsonify({
            'success': True,
            'path': path,
            'result_key': result.get('name', 'No key returned'),
            'test_record': test_record
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'path': path
        })

# Enhanced JavaScript for the dashboard to show more debugging info
dashboard_debug_js = """
<script>
// Add this to your dashboard.html in the existing script section

// Enhanced error handling for the attendance marking
scanQrBtn.addEventListener("click", async function() {
    if (html5QrCode && html5QrCode.isScanning) {
        html5QrCode.stop().then(() => {
            qrReaderContainer.style.display = 'none';
            statusEl.textContent = "Scanner stopped.";
        });
        return;
    }
    
    try {
        const position = await getLocation();
        currentPosition = position;
        statusEl.textContent = "Location acquired. Please scan the QR code.";
        qrReaderContainer.style.display = 'block';

        if (!html5QrCode) {
            html5QrCode = new Html5Qrcode("qr-reader");
        }

        html5QrCode.start(
            { facingMode: "environment" },
            { fps: 10, qrbox: { width: 250, height: 250 } },
            (decodedText, decodedResult) => {
                console.log("QR Code scanned:", decodedText); // DEBUG LOG
                
                if (html5QrCode.isScanning) {
                    html5QrCode.stop();
                }
                statusEl.textContent = "QR Code detected. Verifying...";
                
                const requestData = { 
                    qr_data: decodedText,
                    latitude: currentPosition.coords.latitude,
                    longitude: currentPosition.coords.longitude
                };
                
                console.log("Sending request:", requestData); // DEBUG LOG
                
                fetch("/mark_attendance_qr", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(requestData)
                })
                .then(response => {
                    console.log("Response status:", response.status); // DEBUG LOG
                    return response.json();
                })
                .then(result => {
                    console.log("Response data:", result); // DEBUG LOG
                    statusEl.textContent = result.message;
                    qrReaderContainer.style.display = 'none';
                    
                    // If successful, show additional info
                    if (result.message.includes("successfully")) {
                        statusEl.innerHTML = result.message + "<br><small>Check browser console for details.</small>";
                    }
                })
                .catch(error => {
                    console.error("Fetch error:", error); // DEBUG LOG
                    statusEl.textContent = "Error marking attendance: " + error.message;
                });
            },
            (errorMessage) => {
                // This is called when no QR is found, can be ignored
            }
        ).catch((err) => {
            console.error("QR Scanner error:", err); // DEBUG LOG
            statusEl.textContent = "Could not start QR scanner.";
        });

    } catch (error) {
        console.error("Location error:", error); // DEBUG LOG
        statusEl.textContent = error;
    }
});
</script>
"""

# ------------------ RUN APP ------------------
if __name__ == '__main__':
    app.run(debug=True)