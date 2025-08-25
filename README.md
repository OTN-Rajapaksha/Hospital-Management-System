# Hospital ADBMS – Flask Web App

## Quick start
```bash
# 1) (Optional) create venv
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate

# 2) Install deps
pip install -r requirements.txt

# 3) Make sure hospital_app.py is alongside this folder or in PYTHONPATH
#    If you downloaded it separately, place it in the project root.

# 4) Initialize DB (optional; app will try to init on first run)
python -c "import hospital_app; hospital_app.init_db()"

# 5) Run web app
python app.py
```

## Notes
- Uses SQLite + real SQL triggers from `hospital_app.py`.
- Pages:
  - `/` Home + booking form
  - `/appointments` Appointment list
  - `/patients` Patients list
  - `/doctors` Doctors list
  - `/reports` Simple BI: appointments per doctor
