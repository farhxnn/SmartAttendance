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

# ------------------ CONFIG ------------------
CAMPUS_LAT = 28.72353
CAMPUS_LON = 77.22076
CAMPUS_RADIUS_METERS = 200

app = Flask(__name__)
app.secret_key = "dev_secret"
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

# ------------------ ROUTES ------------------

@app.route('/')
def home():
    return redirect(url_for('login'))

# --------- STUDENT SIGNUP (UPDATED) ----------
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
            db.child("users").child(email.replace('.', ',')).set({
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
            print(e)
            flash("Error during signup. Email may already be in use.")
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
            user_info = db.child("users").child(email.replace('.', ',')).get().val()
            session['role'] = user_info.get("role") if user_info else "student"
            return redirect(url_for('dashboard'))
        except Exception as e:
            print(e)
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
    user_info = db.child("users").child(session['user'].replace('.', ',')).get().val()
    name = user_info.get("name") if user_info else session['user']
    return render_template('dashboard.html', user=name, role=session.get('role'))

# --------- ADMIN DASHBOARD (UPDATED)----------
@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    teacher_email = session['user']
    subject = session.get('subject')
    records = []

    data = db.child("attendance").child(teacher_email.replace('.', ',')).child(subject).get().val()
    if data:
        records = list(data.values())

    qr_data = session.get("qr_data")
    return render_template('admin_dashboard.html', user=teacher_email, records=records, subject=subject, qr_data=qr_data)


# --------- VIEW ATTENDANCE REPORT ----------
@app.route('/view_attendance')
@admin_required
def view_attendance():
    teacher_email = session['user']
    subject = session.get('subject')
    all_records = db.child("attendance").child(teacher_email.replace('.', ',')).child(subject).get().val()
    daily_counts = defaultdict(int)
    if all_records:
        for record in all_records.values():
            record_date = datetime.fromisoformat(record['timestamp']).strftime('%Y-%m-%d')
            daily_counts[record_date] += 1
    sorted_daily_counts = sorted(daily_counts.items())
    chart_labels = [item[0] for item in sorted_daily_counts]
    chart_data = [item[1] for item in sorted_daily_counts]
    
    return render_template('view_attendance.html', subject=subject, chart_labels=chart_labels, chart_data=chart_data)


# --------- GENERATE QR CODE ----------
@app.route('/generate_qr')
@admin_required
def generate_qr():
    subject = request.args.get('subject')
    if not subject:
        flash("Subject is required.")
        return redirect(url_for('admin_dashboard'))

    teacher_email_db_key = session['user'].replace('.', ',')
    teacher_email_for_qr = session['user']
    qr_text = f"{teacher_email_for_qr}|{subject}"
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(qr_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
    session["qr_data"] = "data:image/png;base64," + qr_b64
    session["current_qr"] = qr_text

    return redirect(url_for('admin_dashboard'))

# --------- MARK ATTENDANCE VIA QR (UPDATED) ----------
@app.route('/mark_attendance_qr', methods=['POST'])
@student_required
def mark_attendance_qr():
    data = request.get_json()
    if not data or "qr_data" not in data or "latitude" not in data:
        return jsonify({"message": "Missing required data."}), 400

    qr_data = data.get("qr_data")
    lat = float(data.get("latitude"))
    lon = float(data.get("longitude"))

    if distance(lat, lon, CAMPUS_LAT, CAMPUS_LON) > CAMPUS_RADIUS_METERS:
        return jsonify({"message": "You are outside the campus. Attendance not marked."}), 403

    try:
        teacher_email, subject = qr_data.split("|")
        teacher_email_db = teacher_email.replace('.', ',')
    except (ValueError, TypeError):
        return jsonify({"message": "Invalid QR code format."}), 400

    try:
        student_email = session['user']
        student_email_db_key = student_email.replace('.', ',')
        
        user_details = db.child("users").child(student_email_db_key).get().val()
        if not user_details:
            return jsonify({"message": "Could not find your student profile."}), 404
            
        student_name = user_details.get("name", "N/A")
        student_sol_roll_no = user_details.get("sol_roll_no", "N/A")

        attendance_path = db.child("attendance").child(teacher_email_db).child(subject)
        existing_records = attendance_path.order_by_child('email').equal_to(student_email).get().val()

        if existing_records:
            for record in existing_records.values():
                record_date = datetime.fromisoformat(record['timestamp']).date()
                if record_date == datetime.today().date():
                     return jsonify({"message": "Attendance already marked for today's session."}), 400

        attendance_path.push({
            "name": student_name,
            "sol_roll_no": student_sol_roll_no,
            "email": student_email,
            "timestamp": datetime.now().isoformat(),
            "latitude": lat,
            "longitude": lon,
            "inside_campus": True
        })

        return jsonify({"message": "Attendance marked successfully!"})
    except Exception as e:
        print(f"Error during QR attendance marking: {e}")
        return jsonify({"message": "A server error occurred."}), 500

# --------- DOWNLOAD ATTENDANCE EXCEL (UPDATED)----------
@app.route('/download_attendance')
@admin_required
def download_attendance():
    teacher_email = session.get('user')
    subject = session.get('subject')

    teacher_email_db = teacher_email.replace('.', ',')
    data = db.child("attendance").child(teacher_email_db).child(subject).get().val()

    if not data:
        flash("No attendance records to download for this session.")
        return redirect(url_for('admin_dashboard'))

    df = pd.DataFrame(list(data.values()))
    
    # Reorder columns for a cleaner report
    if 'sol_roll_no' in df.columns and 'name' in df.columns:
        df = df[['sol_roll_no', 'name', 'timestamp', 'email', 'latitude', 'longitude']]

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

# ------------------ RUN APP ------------------
if __name__ == '__main__':
    app.run(debug=True)
