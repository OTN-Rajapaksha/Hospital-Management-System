#!/usr/bin/env python3
"""
Hospital ADBMS Project – Single-File Starter (hospital_app.py)

This script sets up a normalized SQLite database for a Hospital Management System,
creates tables, indexes, and real SQL triggers, and exposes basic functionality
(booking appointments) plus a couple of BI-style queries.

You can run it directly:
  python hospital_app.py --init       # creates/initializes DB and seed data
  python hospital_app.py --report     # prints basic BI reports
  python hospital_app.py --book 1 1 2025-08-30 "Initial consultation"

The file is intentionally self-contained for easy submission as "first file".
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Iterable, Tuple

DB_PATH = Path("hospital.db")


# ---------- Low-level helpers ----------

def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def exec_many(conn: sqlite3.Connection, statements: Iterable[str]) -> None:
    cur = conn.cursor()
    for stmt in statements:
        cur.execute(stmt)
    conn.commit()


# ---------- Schema (3NF) ----------

DDL_TABLES: Tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS Patients (
        patient_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name    TEXT NOT NULL,
        date_of_birth TEXT,
        gender       TEXT CHECK (gender IN ('Male','Female','Other')),
        phone        TEXT,
        email        TEXT UNIQUE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS Doctors (
        doctor_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name    TEXT NOT NULL,
        specialization TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS Rooms (
        room_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        room_number  TEXT NOT NULL UNIQUE,
        room_type    TEXT NOT NULL  -- e.g., Consultation, ICU, Ward
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS Appointments (
        appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id     INTEGER NOT NULL,
        doctor_id      INTEGER NOT NULL,
        room_id        INTEGER,
        start_time     TEXT NOT NULL,  -- ISO8601 string
        end_time       TEXT,           -- optional if unknown
        notes          TEXT,
        status         TEXT NOT NULL DEFAULT 'Booked' CHECK (status IN ('Booked','Completed','Cancelled')),
        FOREIGN KEY (patient_id) REFERENCES Patients(patient_id) ON DELETE CASCADE,
        FOREIGN KEY (doctor_id)  REFERENCES Doctors(doctor_id)  ON DELETE CASCADE,
        FOREIGN KEY (room_id)    REFERENCES Rooms(room_id)      ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS AuditLog (
        log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        entity     TEXT NOT NULL,
        action     TEXT NOT NULL,
        details    TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """,
)

DDL_INDEXES: Tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_appt_doctor_time ON Appointments(doctor_id, start_time);",
    "CREATE INDEX IF NOT EXISTS idx_appt_patient_time ON Appointments(patient_id, start_time);",
)

# ---------- Triggers (Real SQL triggers in SQLite) ----------

DDL_TRIGGERS: Tuple[str, ...] = (
    # Log on appointment insert
    """
    CREATE TRIGGER IF NOT EXISTS trg_appointments_insert_log
    AFTER INSERT ON Appointments
    BEGIN
        INSERT INTO AuditLog(entity, action, details)
        VALUES ('Appointments', 'INSERT',
                'appointment_id=' || NEW.appointment_id ||
                ', patient_id=' || NEW.patient_id ||
                ', doctor_id='  || NEW.doctor_id ||
                ', start_time=' || NEW.start_time);
    END;
    """,
    # Prevent double-booking the same doctor at the same start_time
    """
    CREATE TRIGGER IF NOT EXISTS trg_no_double_book_doctor
    BEFORE INSERT ON Appointments
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM Appointments a
        WHERE a.doctor_id = NEW.doctor_id
          AND a.start_time = NEW.start_time
          AND a.status != 'Cancelled'
    )
    BEGIN
        SELECT RAISE(ABORT, 'Doctor already booked at this time');
    END;
    """,
    # Prevent double-booking the same room at the same start_time
    """
    CREATE TRIGGER IF NOT EXISTS trg_no_double_book_room
    BEFORE INSERT ON Appointments
    FOR EACH ROW
    WHEN NEW.room_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM Appointments a
        WHERE a.room_id = NEW.room_id
          AND a.start_time = NEW.start_time
          AND a.status != 'Cancelled'
    )
    BEGIN
        SELECT RAISE(ABORT, 'Room already booked at this time');
    END;
    """,
)


# ---------- Seed data ----------

SEED_SQL: Tuple[str, ...] = (
    "INSERT OR IGNORE INTO Patients(patient_id, full_name, date_of_birth, gender, phone, email) VALUES "
    "(1,'Alice Johnson','1995-04-10','Female','0771234567','alice@example.com'),"
    "(2,'Bob Perera','1989-09-12','Male','0717654321','bob@example.com');",
    "INSERT OR IGNORE INTO Doctors(doctor_id, full_name, specialization) VALUES "
    "(1,'Dr. Nimal Fernando','Cardiology'),"
    "(2,'Dr. Isuri Ranasinghe','Dermatology');",
    "INSERT OR IGNORE INTO Rooms(room_id, room_number, room_type) VALUES "
    "(1,'C101','Consultation'),(2,'C102','Consultation'),(3,'W201','Ward');",
)


def init_db() -> None:
    conn = connect()
    exec_many(conn, DDL_TABLES)
    exec_many(conn, DDL_INDEXES)
    exec_many(conn, DDL_TRIGGERS)
    exec_many(conn, SEED_SQL)
    conn.close()


# ---------- Application functionality ----------

def book_appointment(patient_id: int, doctor_id: int, start_time: str, end_time: str | None = None,
                     room_id: int | None = None, notes: str = "") -> int:
    """
    Creates an appointment. Returns new appointment_id.
    start_time/end_time should be ISO8601 (e.g., '2025-08-30 09:00').
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO Appointments(patient_id, doctor_id, room_id, start_time, end_time, notes)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (patient_id, doctor_id, room_id, start_time, end_time, notes)
    )
    appointment_id = cur.lastrowid
    conn.commit()
    conn.close()
    return appointment_id


def report_appointments_per_doctor() -> list[Tuple[str, int]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.full_name AS doctor, COUNT(a.appointment_id) as total_appointments
        FROM Doctors d
        LEFT JOIN Appointments a ON d.doctor_id = a.doctor_id AND a.status != 'Cancelled'
        GROUP BY d.doctor_id
        ORDER BY total_appointments DESC, doctor ASC;
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def report_daily_utilization(date_prefix: str) -> list[Tuple[str, int]]:
    """
    Simple BI: how many appointments per room on a given day.
    date_prefix: 'YYYY-MM-DD'
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT r.room_number, COUNT(a.appointment_id) AS count
        FROM Rooms r
        LEFT JOIN Appointments a ON a.room_id = r.room_id
            AND substr(a.start_time, 1, 10) = ?
            AND a.status != 'Cancelled'
        GROUP BY r.room_id
        ORDER BY r.room_number;
        """,
        (date_prefix,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# ---------- CLI ----------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Hospital ADBMS single-file app")
    p.add_argument("--init", action="store_true", help="Initialize database and seed data")
    p.add_argument("--book", nargs=4, metavar=("PATIENT_ID", "DOCTOR_ID", "START_TIME", "NOTES"),
                   help="Book an appointment, e.g., --book 1 1 '2025-08-30 09:00' 'Initial consult'")
    p.add_argument("--room", type=int, default=None, help="Room id (optional with --book)")
    p.add_argument("--end", type=str, default=None, help="End time (optional with --book)")
    p.add_argument("--report", action="store_true", help="Print reports")
    p.add_argument("--util", type=str, default=None, metavar="YYYY-MM-DD",
                   help="Daily utilization report for given date")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.init:
        init_db()
        print("✅ Database initialized and seeded at", DB_PATH.resolve())

    if args.book:
        patient_id = int(args.book[0])
        doctor_id = int(args.book[1])
        start_time = args.book[2]
        notes = args.book[3]
        appt_id = book_appointment(patient_id, doctor_id, start_time, end_time=args.end, room_id=args.room, notes=notes)
        print(f"✅ Appointment created with ID {appt_id}")

    if args.report:
        print("\n📊 Appointments by Doctor:")
        for doctor, count in report_appointments_per_doctor():
            print(f"  - {doctor}: {count}")

    if args.util:
        print(f"\n🏥 Room utilization on {args.util}:")
        for room_number, count in report_daily_utilization(args.util):
            print(f"  - Room {room_number}: {count}")

    # If no flags, show quick help
    if not any([args.init, args.book, args.report, args.util]):
        print(__doc__)


if __name__ == "__main__":
    main()
