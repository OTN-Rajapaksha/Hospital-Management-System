from flask import Flask, request, render_template, redirect, url_for, flash
import sqlite3
from pathlib import Path

DB_PATH = Path("hospital.db")

app = Flask(__name__)
app.secret_key = "change-me-for-production"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def ensure_db():
    try:
        import hospital_app
        if not DB_PATH.exists():
            hospital_app.init_db()
        else:
            hospital_app.init_db()
    except Exception as e:
        print("Warning: could not initialize DB via hospital_app:", e)

@app.route("/")
def home():
    ensure_db()
    conn = get_db()
    doctors = conn.execute("SELECT * FROM Doctors ORDER BY full_name").fetchall()
    patients = conn.execute("SELECT * FROM Patients ORDER BY full_name").fetchall()
    # quick stats
    counts = conn.execute("""
        SELECT 
          (SELECT COUNT(*) FROM Patients) AS patients,
          (SELECT COUNT(*) FROM Doctors) AS doctors,
          (SELECT COUNT(*) FROM Appointments WHERE status!='Cancelled') AS appts
    """).fetchone()
    conn.close()
    return render_template("index.html", doctors=doctors, patients=patients, counts=counts)

# -------------------- Appointments --------------------
@app.route("/appointments")
def appointments():
    conn = get_db()
    appts = conn.execute("""
        SELECT a.appointment_id, p.full_name as patient, d.full_name as doctor,
               a.start_time, COALESCE(a.end_time,'') as end_time, a.status, COALESCE(a.notes,'') as notes
        FROM Appointments a
        JOIN Patients p ON a.patient_id = p.patient_id
        JOIN Doctors d ON a.doctor_id = d.doctor_id
        ORDER BY a.start_time DESC
    """).fetchall()
    conn.close()
    return render_template("appointments.html", appts=appts)

@app.route("/book", methods=["POST"])
def book():
    patient_id = request.form.get("patient_id")
    doctor_id = request.form.get("doctor_id")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time") or None
    room_id = request.form.get("room_id") or None
    notes = request.form.get("notes") or ""

    if not (patient_id and doctor_id and start_time):
        flash("Patient, Doctor and Start Time are required")
        return redirect(url_for("home"))

    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO Appointments(patient_id, doctor_id, room_id, start_time, end_time, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (patient_id, doctor_id, room_id, start_time, end_time, notes))
        conn.commit()
        flash("Appointment booked successfully")
    except sqlite3.IntegrityError as e:
        flash(f"Booking failed: {e}")
    finally:
        conn.close()

    return redirect(url_for("appointments"))

# -------------------- Patients --------------------
@app.route("/patients")
def patients():
    conn = get_db()
    rows = conn.execute("SELECT * FROM Patients ORDER BY full_name").fetchall()
    conn.close()
    return render_template("patients.html", rows=rows)

@app.route("/patients/new", methods=["GET", "POST"])
def patient_new():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        dob = request.form.get("date_of_birth", "").strip()
        gender = request.form.get("gender", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()

        if not full_name:
            flash("Full name is required.")
            return redirect(url_for("patient_new"))

        try:
            conn = get_db()
            conn.execute("""
                INSERT INTO Patients(full_name, date_of_birth, gender, phone, email)
                VALUES (?, ?, ?, ?, ?)
            """, (full_name, dob, gender, phone, email))
            conn.commit()
            flash("Patient added successfully.")
        except sqlite3.IntegrityError as e:
            flash(f"Could not add patient: {e}")
        finally:
            conn.close()
        return redirect(url_for("patients"))
    return render_template("patient_new.html")

@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
def patient_delete(patient_id):
    conn = get_db()
    conn.execute("DELETE FROM Patients WHERE patient_id = ?", (patient_id,))
    conn.commit()
    conn.close()
    flash("Patient deleted.")
    return redirect(url_for("patients"))

# -------------------- Doctors --------------------
@app.route("/doctors")
def doctors():
    conn = get_db()
    rows = conn.execute("SELECT * FROM Doctors ORDER BY full_name").fetchall()
    conn.close()
    return render_template("doctors.html", rows=rows)

@app.route("/doctors/new", methods=["GET", "POST"])
def doctor_new():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        specialization = request.form.get("specialization", "").strip()
        if not full_name or not specialization:
            flash("Doctor name and specialization are required.")
            return redirect(url_for("doctor_new"))
        conn = get_db()
        conn.execute("INSERT INTO Doctors(full_name, specialization) VALUES (?, ?)", (full_name, specialization))
        conn.commit()
        conn.close()
        flash("Doctor added successfully.")
        return redirect(url_for("doctors"))
    return render_template("doctor_new.html")

@app.route("/doctors/<int:doctor_id>/delete", methods=["POST"])
def doctor_delete(doctor_id):
    conn = get_db()
    conn.execute("DELETE FROM Doctors WHERE doctor_id = ?", (doctor_id,))
    conn.commit()
    conn.close()
    flash("Doctor deleted.")
    return redirect(url_for("doctors"))

# -------------------- Reports --------------------
@app.route("/reports")
def reports():
    conn = get_db()
    per_doc = conn.execute("""
        SELECT d.full_name AS doctor, COUNT(a.appointment_id) AS total
        FROM Doctors d
        LEFT JOIN Appointments a ON d.doctor_id = a.doctor_id AND a.status!='Cancelled'
        GROUP BY d.doctor_id
        ORDER BY total DESC, doctor ASC
    """).fetchall()

    # Counts
    counts = conn.execute("""
        SELECT 
          (SELECT COUNT(*) FROM Patients) AS patients,
          (SELECT COUNT(*) FROM Doctors) AS doctors,
          (SELECT COUNT(*) FROM Appointments WHERE status!='Cancelled') AS appts
    """).fetchone()

    # Utilization by room for today's date (if any data). Keep simple: top 10 rows by count across all
    by_room = conn.execute("""
        SELECT r.room_number AS room, COUNT(a.appointment_id) AS total
        FROM Rooms r
        LEFT JOIN Appointments a ON a.room_id = r.room_id AND a.status!='Cancelled'
        GROUP BY r.room_id
        ORDER BY total DESC, r.room_number
        LIMIT 10
    """).fetchall()
    conn.close()

    labels = [r["doctor"] for r in per_doc]
    values = [r["total"] for r in per_doc]

    room_labels = [r["room"] for r in by_room]
    room_values = [r["total"] for r in by_room]

    return render_template("reports.html",
                           per_doc=per_doc, counts=counts,
                           chart_labels=labels, chart_values=values,
                           room_labels=room_labels, room_values=room_values)

if __name__ == "__main__":
    ensure_db()
    app.run(debug=True)
