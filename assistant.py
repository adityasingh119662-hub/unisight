import os
import sqlite3
import re
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

try:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY.startswith("gsk_") else None
except Exception:
    groq_client = None

# Allowed tables for Text-to-SQL (Quarantines the Identity Vault and Audit Ledger)
ALLOWED_TABLES = {
    'department_budgets',
    'facility_utilization',
    'v_unified_student_intelligence',
    'attendance_records',
    'academic_records',
    'student_financials',
    'monthly_attendance'
}

RESTRICTED_KEYWORDS = {'drop', 'delete', 'update', 'insert', 'alter', 'truncate', 'attach', 'vacuum'}

DB_SCHEMA = """
Allowed Tables & Views:
1. department_budgets (department, allocated_budget, spent_budget, utilization_pct)
2. facility_utilization (facility_name, department, capacity, utilization_pct)
3. v_unified_student_intelligence (token_id, department, attendance_pct, internal_avg, pending_tuition_fee, is_at_risk)
4. monthly_attendance (month_name, month_num, department, avg_attendance_pct)
"""

def clean_sql(raw_output: str) -> str:
    match = re.search(r"```(?:sql)?\s*(.*?)\s*```", raw_output, re.DOTALL)
    cleaned = match.group(1).strip() if match else raw_output.strip()
    return cleaned.rstrip(';') + ';'

def validate_sql(sql_query: str) -> tuple[bool, str]:
    normalized = sql_query.lower()
    
    # Must be a SELECT query
    if not normalized.strip().startswith('select'):
        return False, "Security Violation: Only read-only SELECT queries are allowed."
    
    # Block destructive commands
    for word in RESTRICTED_KEYWORDS:
        if re.search(r'\b' + word + r'\b', normalized):
            return False, f"Security Violation: Restricted keyword '{word}' detected."
            
    # Block direct queries to Identity Vault and Audit Ledger
    if "dpdp_identity_vault" in normalized or "audit_ledger" in normalized:
        return False, "Access Denied: Querying identity vaults or audit trails is forbidden under DPDP Act governance."

    return True, sql_query

def execute_readonly_query(sql_query: str):
    is_valid, reason = validate_sql(sql_query)
    if not is_valid:
        return None, None, reason

    try:
        # Enforce SQLite Read-Only URI Mode
        conn = sqlite3.connect('file:unisight.db?mode=ro', uri=True)
        cursor = conn.cursor()
        cursor.execute(sql_query)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return columns, rows, None
    except Exception as e:
        return None, None, str(e)

def generate_dynamic_summary(question: str, sql: str, columns: list, rows: list) -> str:
    """Generates an executive summary based strictly on returned data."""
    if not rows:
        return "The query ran successfully, but returned no matching records."

    if groq_client:
        try:
            prompt = f"""
You are UniSight Executive Intelligence.
Question: {question}
SQL Query: {sql}
Results: Columns={columns}, Rows={rows[:5]}

Provide a concise 2-sentence executive summary.
Strict constraint: Use ONLY the numbers and names present in the results. Do not speculate or introduce external numbers.
"""
            res = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            return res.choices[0].message.content.strip()
        except Exception:
            pass

    # Deterministic fallback summary (strictly formats real row data)
    first_row = dict(zip(columns, rows[0]))
    if "utilization_pct" in first_row or "utilization" in str(first_row):
        dept = first_row.get('department', 'Specified unit')
        pct = first_row.get('utilization_pct', list(first_row.values())[1])
        return f"Database records confirm {dept} has a utilization rate of {pct}%, based on current ledger accounts."
    elif len(rows) == 1:
        details = ", ".join([f"{k}: {v}" for k, v in first_row.items()])
        return f"Query returned 1 verified record: {details}."
    else:
        return f"Retrieved {len(rows)} matching departmental records from the institutional store."

def ask_unisight(question: str) -> dict:
    q_lower = question.lower()
    
    # 1. Generate SQL
    if groq_client:
        try:
            prompt = f"Schema:\n{DB_SCHEMA}\n\nWrite one SQLite read-only SELECT query for: '{question}'. Return ONLY raw SQL."
            res = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            raw_sql = clean_sql(res.choices[0].message.content)
        except Exception:
            raw_sql = None
    else:
        raw_sql = None

    # Deterministic SQL generation if API is offline
    if not raw_sql:
        if "lowest budget" in q_lower or "least budget" in q_lower:
            raw_sql = "SELECT department, utilization_pct, spent_budget FROM department_budgets ORDER BY utilization_pct ASC LIMIT 1;"
        elif any(k in q_lower for k in ["financial", "finance", "budget"]):
            raw_sql = "SELECT department, allocated_budget, spent_budget, utilization_pct FROM department_budgets ORDER BY utilization_pct ASC;"
        elif "revenue" in q_lower or "fee" in q_lower or "tuition" in q_lower:
            raw_sql = "SELECT department, COUNT(token_id) AS at_risk_students, SUM(pending_tuition_fee) AS total_tuition_at_risk FROM v_unified_student_intelligence WHERE is_at_risk = 1 GROUP BY department;"
        elif "facility" in q_lower or "lab" in q_lower:
            raw_sql = "SELECT facility_name, department, utilization_pct FROM facility_utilization WHERE utilization_pct < 60 ORDER BY utilization_pct ASC;"
        else:
            raw_sql = "SELECT department, COUNT(token_id) AS at_risk_count, ROUND(AVG(attendance_pct), 1) AS avg_attendance FROM v_unified_student_intelligence WHERE is_at_risk = 1 GROUP BY department;"

    # 2. Execute Query
    cols, rows, error = execute_readonly_query(raw_sql)
    if error:
        return {"sql": raw_sql, "columns": [], "rows": [], "answer": f"Execution Blocked: {error}"}

    # 3. Dynamic Summary
    summary = generate_dynamic_summary(question, raw_sql, cols, rows)
    return {"sql": raw_sql, "columns": cols, "rows": rows, "answer": summary}