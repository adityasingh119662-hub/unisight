import sqlite3
import random
import hashlib
from datetime import datetime
import numpy as np
import pandas as pd
from faker import Faker

fake = Faker('en_IN')
np.random.seed(42)
random.seed(42)

TOTAL_STUDENTS = 1200
DEPTS = ['CSE', 'ECE', 'MECH', 'CIVIL', 'MBA']
DEPT_WEIGHTS = [0.35, 0.25, 0.15, 0.15, 0.10]

print("⏳ Generating statistically realistic data and governance tables...")

# 1. DPDP Identity Vault
vault_data = []
for i in range(1, TOTAL_STUDENTS + 1):
    # HMAC-like pseudo-hash token instead of simple incremental ID
    raw_id = f"STUDENT_2026_{i:04d}"
    token = f"STU_{hashlib.sha256(raw_id.encode()).hexdigest()[:8].upper()}"
    name = fake.name()
    email = f"{name.lower().replace(' ', '.')[:12]}@univ.edu.in"
    phone = f"+91 9{random.randint(100000000, 999999999)}"
    dept = np.random.choice(DEPTS, p=DEPT_WEIGHTS)
    vault_data.append((token, name, email, phone, dept))

df_vault = pd.DataFrame(vault_data, columns=['token_id', 'full_name', 'email', 'phone', 'department'])

# 2. Silo: Attendance System
attendance_data = []
for _ in range(TOTAL_STUDENTS):
    att_pct = np.clip(np.random.normal(81.5, 9.5), 45.0, 99.0)
    consec_absent = int(max(0, np.random.poisson(1.2 if att_pct > 75 else 4.0)))
    attendance_data.append((round(att_pct, 1), consec_absent))

# 3. Silo: Academics & LMS
academic_data = []
for (att, consec) in attendance_data:
    # Noisy correlation with attendance
    score_base = 0.65 * att + np.random.normal(20, 10)
    internal_avg = np.clip(score_base, 30.0, 98.0)
    lab_score = np.clip(internal_avg + np.random.normal(-2, 6), 25.0, 100.0)
    missed_tests = int(np.clip(np.random.poisson(0.5 if att > 75 else 2.2), 0, 5))
    missed_assignments = int(np.clip(np.random.poisson(0.8 if att > 75 else 3.1), 0, 8))
    academic_data.append((round(internal_avg, 1), round(lab_score, 1), missed_tests, missed_assignments))

# 4. Silo: Finance
finance_data = []
for (att, _), (internal, _, _, _) in zip(attendance_data, academic_data):
    # Fee dues correlated with disengagement, but with natural noise
    prob_unpaid = 0.65 if (att < 65 or internal < 50) else 0.12
    pending_fee = random.choice([45000, 75000, 95000, 120000]) if random.random() < prob_unpaid else 0
    finance_data.append(pending_fee)

# 5. Non-Trivial Probabilistic Ground Truth Label (Anti-Target Leakage)
outcomes = []
for (att, consec), (internal, lab, tests, assigns), fee in zip(attendance_data, academic_data, finance_data):
    # Latent failure risk equation with Gaussian noise
    z = (
        - 0.08 * (att - 75.0)
        - 0.06 * (internal - 60.0)
        + 0.55 * tests
        + 0.35 * assigns
        + (0.4 if fee > 50000 else -0.2)
        + np.random.normal(0, 1.2)  # Injected noise creates overlapping distributions
    )
    prob_failure = 1.0 / (1.0 + np.exp(-z))
    outcomes.append(1 if prob_failure > 0.55 else 0)

# Build DataFrames
df_att = pd.DataFrame({
    'token_id': df_vault['token_id'],
    'attendance_pct': [x[0] for x in attendance_data],
    'consecutive_absences': [x[1] for x in attendance_data]
})

df_acad = pd.DataFrame({
    'token_id': df_vault['token_id'],
    'internal_avg': [x[0] for x in academic_data],
    'lab_score': [x[1] for x in academic_data],
    'missed_tests': [x[2] for x in academic_data],
    'missed_assignments': [x[3] for x in academic_data],
    'is_at_risk': outcomes
})

df_fin = pd.DataFrame({
    'token_id': df_vault['token_id'],
    'pending_tuition_fee': finance_data
})

# 6. Monthly Trend History (for Real Forecasts)
months_data = []
for m_num, m_name in enumerate(['Jul', 'Aug', 'Sep', 'Oct'], 1):
    base_att = 85.5 - (m_num * 1.8)
    for d in DEPTS:
        months_data.append((m_name, m_num, d, round(base_att + np.random.normal(0, 1.2), 1)))

df_monthly = pd.DataFrame(months_data, columns=['month_name', 'month_num', 'department', 'avg_attendance_pct'])

# 7. Department Budgets & Facilities
df_budget = pd.DataFrame([
    ('CSE', 35000000, 27300000, 78.0),
    ('ECE', 25000000, 16000000, 64.0),
    ('MECH', 22000000, 15620000, 71.0),
    ('CIVIL', 20000000, 11600000, 58.0),
    ('MBA', 18000000, 14940000, 83.0),
], columns=['department', 'allocated_budget', 'spent_budget', 'utilization_pct'])

df_facilities = pd.DataFrame([
    ('CSE Cloud Lab', 'CSE', 80, 89.0),
    ('Robotics & AI Center', 'ECE', 60, 74.0),
    ('CAD/CAM Lab 1', 'MECH', 60, 68.0),
    ('Fluid Mechanics Lab', 'CIVIL', 50, 38.0),
    ('MBA Case Study Hall', 'MBA', 120, 84.0),
    ('Central Seminar Hall', 'ALL', 350, 42.0),
    ('Digital Library Block', 'ALL', 200, 86.0),
], columns=['facility_name', 'department', 'capacity', 'utilization_pct'])

# 8. Save Tables into SQLite
conn = sqlite3.connect('unisight.db')

df_vault.to_sql('dpdp_identity_vault', conn, if_exists='replace', index=False)
df_att.to_sql('attendance_records', conn, if_exists='replace', index=False)
df_acad.to_sql('academic_records', conn, if_exists='replace', index=False)
df_fin.to_sql('student_financials', conn, if_exists='replace', index=False)
df_monthly.to_sql('monthly_attendance', conn, if_exists='replace', index=False)
df_budget.to_sql('department_budgets', conn, if_exists='replace', index=False)
df_facilities.to_sql('facility_utilization', conn, if_exists='replace', index=False)

# Governance Tables
conn.execute("""
CREATE TABLE IF NOT EXISTS audit_ledger (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    actor_role TEXT,
    action TEXT,
    target_token TEXT,
    justification TEXT,
    previous_hash TEXT,
    entry_hash TEXT
);
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS student_interventions (
    intervention_id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_id TEXT,
    department TEXT,
    directive TEXT,
    status TEXT,
    logged_at TEXT
);
""")

# Unified Analytical View (Excludes PII Vault)
conn.execute("""
CREATE VIEW IF NOT EXISTS v_unified_student_intelligence AS
SELECT 
    v.token_id,
    v.department,
    a.attendance_pct,
    a.consecutive_absences,
    ac.internal_avg,
    ac.lab_score,
    ac.missed_tests,
    ac.missed_assignments,
    f.pending_tuition_fee,
    ac.is_at_risk
FROM dpdp_identity_vault v
JOIN attendance_records a ON v.token_id = a.token_id
JOIN academic_records ac ON v.token_id = ac.token_id
JOIN student_financials f ON v.token_id = f.token_id;
""")

conn.commit()
conn.close()

print(f"✅ Database initialized: {sum(outcomes)} students flagged as high-risk across {TOTAL_STUDENTS} records.")