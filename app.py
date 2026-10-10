import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
from ml_engine import train_and_explain
from assistant import ask_unisight
import os
if not os.path.exists("unisight.db"):
    import setup_data  # Automatically generates the database on first cloud boot!
    
st.set_page_config(
    page_title="UniSight | Institutional Decision-Making",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Polished CSS Styling
st.markdown("""
<style>
    .kpi-container {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 12px;
        margin-bottom: 20px;
    }
    .kpi-card {
        background: #0f192c;
        border: 1px solid #1c2e4e;
        border-radius: 8px;
        padding: 14px 10px;
        text-align: center;
    }
    .kpi-title {
        font-size: 0.72rem;
        color: #94a3b8;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        margin-bottom: 4px;
    }
    .kpi-val { font-size: 1.85rem; font-weight: 800; line-height: 1.2; }
    .val-cyan { color: #00f2fe; }
    .val-green { color: #38ef7d; }
    .val-orange { color: #fbbf24; }
    .val-red { color: #f87171; }
    .chart-box {
        background: #0f192c;
        border: 1px solid #1c2e4e;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Dynamic Data Loaders (Strictly Calculated from SQLite)
# -----------------------------------------------------------------------------
@st.cache_data
def get_dashboard_data():
    _, df_risk, stats = train_and_explain()
    conn = sqlite3.connect('file:unisight.db?mode=ro', uri=True)
    df_budget = pd.read_sql_query("SELECT * FROM department_budgets", conn)
    df_fac = pd.read_sql_query("SELECT * FROM facility_utilization", conn)
    df_monthly = pd.read_sql_query("SELECT month_name, ROUND(AVG(avg_attendance_pct), 1) as avg_att FROM monthly_attendance GROUP BY month_num, month_name ORDER BY month_num", conn)
    conn.close()
    return df_risk, stats, df_budget, df_fac, df_monthly

df_risk, stats, df_budget, df_fac, df_monthly = get_dashboard_data()

# Helper Functions for Persistent Governance Actions
def record_audit_event(actor: str, action: str, target: str, justification: str):
    conn = sqlite3.connect('unisight.db')
    cursor = conn.cursor()
    cursor.execute("SELECT entry_hash FROM audit_ledger ORDER BY entry_id DESC LIMIT 1")
    row = cursor.fetchone()
    prev_hash = row[0] if row else "GENESIS_HASH_000000000"

    timestamp = datetime.now().isoformat()
    raw_payload = f"{timestamp}|{actor}|{action}|{target}|{justification}|{prev_hash}"
    entry_hash = hashlib.sha256(raw_payload.encode()).hexdigest()

    cursor.execute("""
    INSERT INTO audit_ledger (timestamp, actor_role, action, target_token, justification, previous_hash, entry_hash)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, actor, action, target, justification, prev_hash, entry_hash))
    conn.commit()
    conn.close()

def save_intervention(token: str, dept: str, directive: str):
    conn = sqlite3.connect('unisight.db')
    conn.execute("""
    INSERT INTO student_interventions (token_id, department, directive, status, logged_at)
    VALUES (?, ?, ?, 'Open', ?)
    """, (token, dept, directive, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

# -----------------------------------------------------------------------------
# Sidebar: Role Governance
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🏛️ **UniSight**")
    st.caption("AI-Powered Institutional Intelligence Platform")
    st.divider()

    st.markdown("#### 🔐 Active Role Governance")
    user_role = st.selectbox(
        "Current Persona:",
        ["Executive Leadership (VC / Dean)", "Academic Department Head / Mentor"]
    )

    if user_role == "Executive Leadership (VC / Dean)":
        st.info("🔒 **Data Minimization Active:** Student PII is cryptographically masked. Macro aggregates enabled.")
    else:
        st.warning("⚠️ **Mentor Intervention Mode:** Authorized to access student mentoring profiles. Actions are audit-logged.")

    st.divider()
    st.markdown("#### 🏅 Institutional Compliance")
    st.markdown("""
    - **DPDP Act 2023:** Enforced (Cryptographic Tokens)
    - **Data Integrity:** Read-Only Governed SQL Layer
    - **Model Validation:** 75/25 Stratified Holdout
    """)

# -----------------------------------------------------------------------------
# Main Header
# -----------------------------------------------------------------------------
head_l, head_r = st.columns([4, 1])
with head_l:
    st.title("Institutional Decision Cockpit")
    st.caption("Unified predictive intelligence across Finance, Academics, Operations & Infrastructure.")
with head_r:
    st.write("")
    st.success("● SYSTEM LIVE")

# -----------------------------------------------------------------------------
# Row 1: Fully Dynamic KPI Bar
# -----------------------------------------------------------------------------
calc_budget_util = round(float(df_budget['spent_budget'].sum() / df_budget['allocated_budget'].sum()) * 100, 1)
calc_fac_util = round(float(df_fac['utilization_pct'].mean()), 1)

st.markdown(f"""
<div class="kpi-container">
    <div class="kpi-card">
        <div class="kpi-title">Avg. Attendance</div>
        <div class="kpi-val val-cyan">{stats['avg_attendance']}%</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-title">Students at Risk</div>
        <div class="kpi-val val-red">{stats['students_at_risk']}</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-title">Tuition Exposure</div>
        <div class="kpi-val val-orange">₹{stats['tuition_revenue_at_risk']/10000000:.2f} Cr</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-title">Budget Utilised</div>
        <div class="kpi-val val-green">{calc_budget_util}%</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-title">Facility Usage</div>
        <div class="kpi-val val-cyan">{calc_fac_util}%</div>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Row 2: Charts (Attendance Trend + Budget Utilization)
# -----------------------------------------------------------------------------
c_left, c_right = st.columns(2)

with c_left:
    st.markdown("<div class='chart-box'>", unsafe_allow_html=True)
    st.markdown("#### Attendance Trend & AI Forecast (%)")
    
    # Dynamic Trend from monthly_attendance table + 2-Month Regression Forecast
    hist_months = list(df_monthly['month_name'])
    hist_vals = list(df_monthly['avg_att'])
    
    slope = (hist_vals[-1] - hist_vals[0]) / max(len(hist_vals) - 1, 1)
    fc_nov = round(hist_vals[-1] + slope, 1)
    fc_dec = round(hist_vals[-1] + 2 * slope, 1)
    
    all_months = hist_months + ['Nov', 'Dec']
    actual_line = hist_vals + [None, None]
    forecast_line = [None] * (len(hist_months) - 1) + [hist_vals[-1], fc_nov, fc_dec]

    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(
        x=all_months, y=actual_line, mode='lines+markers', name='Actual',
        line=dict(color='#00d2ff', width=3), marker=dict(size=8, color='#00d2ff')
    ))
    fig_line.add_trace(go.Scatter(
        x=all_months, y=forecast_line, mode='lines+markers', name='AI Forecast',
        line=dict(color='#fbbf24', width=3, dash='dash'), marker=dict(size=8, color='#fbbf24')
    ))
    fig_line.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        height=270, margin=dict(l=10, r=10, t=10, b=10),
        yaxis=dict(range=[50, 100], gridcolor='#1c2e4e', zeroline=False),
        xaxis=dict(gridcolor='#1c2e4e'), font=dict(color='#94a3b8'),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_line, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

with c_right:
    st.markdown("<div class='chart-box'>", unsafe_allow_html=True)
    st.markdown("#### Budget Utilisation by Department (%)")
    
    fig_bar = px.bar(
        df_budget, x='department', y='utilization_pct', text='utilization_pct',
        color='department', color_discrete_sequence=['#00f2fe', '#38ef7d', '#60a5fa', '#f87171', '#c084fc']
    )
    fig_bar.update_traces(texttemplate='%{text:.0f}%', textposition='outside', marker=dict(line=dict(width=0)))
    fig_bar.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        height=270, margin=dict(l=10, r=10, t=10, b=10),
        yaxis=dict(range=[0, 100], gridcolor='#1c2e4e', zeroline=False),
        xaxis=dict(gridcolor='#1c2e4e'), font=dict(color='#94a3b8'), showlegend=False
    )
    st.plotly_chart(fig_bar, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Row 3: Actionable Workflow Tabs
# -----------------------------------------------------------------------------
tab_intervene, tab_chat, tab_ops, tab_dpdp = st.tabs([
    "🎯 Predictive Intervention Matrix",
    "💬 Executive AI Assistant (Text-to-SQL)",
    "🏢 Resource & Facility Utilization",
    "🛡️ DPDP Privacy & Audit Vault"
])

# TAB 1: Predictive Interventions + Holdout Metrics Expander
with tab_intervene:
    st.markdown("### Early Warning & Intervention System")
    
    # Statistical Validation Expander
    m = stats['metrics']
    with st.expander("📊 Technical Validation: Machine Learning Rigor (Holdout Test Set)", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Holdout ROC-AUC", f"{m['roc_auc']:.3f}")
        c2.metric("Precision", f"{m['precision']:.3f}")
        c3.metric("Recall", f"{m['recall']:.3f}")
        c4.metric("Split Ratio", f"{m['train_samples']} / {m['test_samples']}")
        st.caption("Evaluated on a 25% stratified holdout split with injected feature noise. Validates that the model generalises beyond simple rules.")

    f1, f2, f3 = st.columns([2, 2, 2])
    with f1:
        sel_dept = st.selectbox("Department Filter:", ["All Departments"] + list(df_risk['department'].unique()))
    with f2:
        risk_tier = st.selectbox("Risk Level:", ["All Levels", "Critical (> 80%)", "Elevated (55% - 80%)"])
    with f3:
        st.metric("Total Cohort at Risk", f"{len(df_risk)} Students", f"₹{stats['tuition_revenue_at_risk']/100000:.1f} L Exposure")

    filtered = df_risk.copy()
    if sel_dept != "All Departments":
        filtered = filtered[filtered['department'] == sel_dept]
    if risk_tier == "Critical (> 80%)":
        filtered = filtered[filtered['risk_probability'] >= 0.80]
    elif risk_tier == "Elevated (55% - 80%)":
        filtered = filtered[(filtered['risk_probability'] >= 0.55) & (filtered['risk_probability'] < 0.80)]

    view_table = filtered[['token_id', 'department', 'risk_probability', 'pending_tuition_fee', 'ai_explanation']].copy()
    view_table['risk_probability'] = view_table['risk_probability'].apply(lambda x: f"🔴 {x*100:.1f}%" if x >= 0.8 else f"🟠 {x*100:.1f}%")
    view_table['pending_tuition_fee'] = view_table['pending_tuition_fee'].apply(lambda x: f"₹{int(x):,}")
    view_table.columns = ['Token ID', 'Department', 'Failure Risk', 'Tuition Exposure', 'Explainable AI Root Cause']
    st.dataframe(view_table, use_container_width=True, height=260)

    # Persistent Mentoring Action
    st.markdown("#### ⚡ Dispatch Mentoring Intervention")
    act_col1, act_col2 = st.columns([3, 1])
    with act_col1:
        chosen_token = st.selectbox("Target Student Token:", filtered['token_id'])
    with act_col2:
        st.write("")
        st.write("")
        if st.button("🚀 Log & Dispatch Intervention", use_container_width=True, type="primary"):
            dept_name = filtered[filtered['token_id'] == chosen_token]['department'].values[0]
            save_intervention(chosen_token, dept_name, "Assigned to mentor for academic and fee counseling.")
            st.toast(f"Intervention recorded for {chosen_token} in student_interventions table!", icon="✅")
            st.success(f"Intervention committed to institutional database for {chosen_token}.")

# TAB 2: Text-to-SQL AI Assistant
with tab_chat:
    st.markdown("### 💬 UniSight Executive Assistant")
    st.caption("Ask freeform institutional questions. Read-only SQL queries run safely against analytical tables.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "Welcome. You can query departmental budgets, student risk exposures, and facility bottlenecks."}
        ]

    st.markdown("**Suggested Institutional Queries:**")
    q_col1, q_col2, q_col3 = st.columns(3)
    preset_q = None
    if q_col1.button("📊 Financial breakdown", use_container_width=True):
        preset_q = "Give me a financial breakdown of budget and tuition risk"
    if q_col2.button("📉 Lowest budget department?", use_container_width=True):
        preset_q = "Which department has the lowest budget utilization and what is its percentage?"
    if q_col3.button("🏢 Facilities under 50%?", use_container_width=True):
        preset_q = "Which facilities have utilization below 50%?"

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    with st.container():
        input_c1, input_c2 = st.columns([5, 1])
        with input_c1:
            typed_q = st.text_input(
                "Ask Executive Question:",
                placeholder="Ask about finances, risk numbers, or space bottlenecks...",
                label_visibility="collapsed"
            )
        with input_c2:
            ask_pressed = st.button("Query AI ➔", use_container_width=True, type="primary")

    active_prompt = preset_q or (typed_q if ask_pressed and typed_q else None)

    if active_prompt:
        st.session_state.chat_history.append({"role": "user", "content": active_prompt})
        with st.chat_message("user"):
            st.write(active_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Executing governed read-only SQL query..."):
                res = ask_unisight(active_prompt)
                st.write(f"**Executive Summary:** {res['answer']}")
                
                if res['columns'] and res['rows']:
                    df_out = pd.DataFrame(res['rows'], columns=res['columns'])
                    st.dataframe(df_out, use_container_width=True)
                
                with st.expander("🔍 Inspect Governed SQL"):
                    st.code(res['sql'], language="sql")
                
                st.session_state.chat_history.append({"role": "assistant", "content": res['answer']})

# TAB 3: Infrastructure Optimization
with tab_ops:
    st.markdown("### Campus Infrastructure Optimization")
    st.caption("Correlating physical asset capacity against actual student utilization.")

    fac_l, fac_r = st.columns([3, 2])
    with fac_l:
        fig_fac = px.bar(
            df_fac, x='facility_name', y='utilization_pct', color='utilization_pct',
            color_continuous_scale='tealrose', labels={'utilization_pct': 'Usage (%)', 'facility_name': 'Facility'}
        )
        fig_fac.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=300, font=dict(color='#94a3b8'))
        st.plotly_chart(fig_fac, use_container_width=True)

    with fac_r:
        st.markdown("#### ⚡ Dynamic Reallocation Directives")
        underutilized = df_fac[df_fac['utilization_pct'] < 50]
        for _, row in underutilized.iterrows():
            st.warning(f"• **{row['facility_name']} ({row['department']}):** Operating at **{row['utilization_pct']}%** capacity. Flagged for schedule consolidation.")

# TAB 4: DPDP Compliance & Hash-Chained Audit Ledger
with tab_dpdp:
    st.markdown("### 🛡️ India DPDP Act 2023 Compliance Vault")
    st.caption("Cryptographic pseudonymization separates personal identity from analytical models.")

    if user_role == "Academic Department Head / Mentor":
        st.markdown("#### 🔓 Mentor 'Break-Glass' Identity Resolution")
        
        conn = sqlite3.connect('file:unisight.db?mode=ro', uri=True)
        vault_df = pd.read_sql_query("SELECT * FROM dpdp_identity_vault LIMIT 8", conn)
        conn.close()

        lookup_tok = st.selectbox("Select Mentee Token to Resolve:", vault_df['token_id'])
        justification = st.text_input("Enter Required Compliance Justification:", value="Academic remedial counseling directive")

        if st.button("Unlock Contact Profile (Audited Action)"):
            record_audit_event("HOD_MENTOR", "DECRYPT_IDENTITY", lookup_tok, justification)
            matched = vault_df[vault_df['token_id'] == lookup_tok].iloc[0]
            
            st.success(f"""
            **Full Name:** {matched['full_name']}  
            **Department:** {matched['department']}  
            **Official Email:** {matched['email']}  
            **Parent Emergency Contact:** {matched['phone']}  
            
            *✓ Access event recorded with SHA-256 hash chaining.*
            """)
        
        # Display the real Audit Ledger from SQLite
        st.markdown("#### 📜 Verifiable Audit Ledger (Last 5 Events)")
        conn = sqlite3.connect('file:unisight.db?mode=ro', uri=True)
        ledger_df = pd.read_sql_query("SELECT timestamp, actor_role, action, target_token, entry_hash FROM audit_ledger ORDER BY entry_id DESC LIMIT 5", conn)
        conn.close()
        st.dataframe(ledger_df, use_container_width=True)
    else:
        st.info("🔒 **Executive Safeguard Active:** You are currently logged in as **Vice Chancellor / Executive**. Personal contact information is hidden to maintain data minimization.")