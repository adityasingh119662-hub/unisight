import sqlite3
import pandas as pd
import numpy as np
import xgboost as xgb
import shap
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score, accuracy_score

FEATURE_COLS = [
    'attendance_pct',
    'consecutive_absences',
    'internal_avg',
    'lab_score',
    'missed_tests',
    'missed_assignments',
    'pending_tuition_fee'
]

def load_data():
    conn = sqlite3.connect('unisight.db')
    df = pd.read_sql_query("SELECT * FROM v_unified_student_intelligence", conn)
    conn.close()
    return df

def generate_plain_explanation(row_features, shap_row):
    reasons = []
    if shap_row['attendance_pct'] > 0.05:
        reasons.append(f"attendance is {row_features['attendance_pct']:.0f}%")
    if shap_row['missed_tests'] > 0.05 and row_features['missed_tests'] > 0:
        reasons.append(f"{int(row_features['missed_tests'])} internal test(s) missed")
    if shap_row['internal_avg'] > 0.05:
        reasons.append(f"internal exam average is low ({row_features['internal_avg']:.0f}/100)")
    if shap_row['pending_tuition_fee'] > 0.05 and row_features['pending_tuition_fee'] > 50000:
        reasons.append(f"pending fee balance of ₹{int(row_features['pending_tuition_fee']):,}")

    if not reasons:
        return "Combined marginal vulnerabilities across academic and attendance records."
    return f"Risk factors: {', and '.join(reasons[:2])}."

def train_and_explain():
    df = load_data()
    X = df[FEATURE_COLS]
    y = df['is_at_risk']

    # Stratified Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    model = xgb.XGBClassifier(
        n_estimators=80,
        max_depth=3,
        learning_rate=0.07,
        random_state=42,
        eval_metric='logloss'
    )
    model.fit(X_train, y_train)

    # Evaluate on Holdout Test Set
    test_probs = model.predict_proba(X_test)[:, 1]
    test_preds = (test_probs >= 0.50).astype(int)

    metrics = {
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "roc_auc": round(float(roc_auc_score(y_test, test_probs)), 3),
        "precision": round(float(precision_score(y_test, test_preds, zero_division=0)), 3),
        "recall": round(float(recall_score(y_test, test_preds, zero_division=0)), 3),
        "f1": round(float(f1_score(y_test, test_preds, zero_division=0)), 3),
        "accuracy": round(float(accuracy_score(y_test, test_preds)), 3)
    }

    # Generate Inference Across the Cohort
    all_probs = model.predict_proba(X)[:, 1]
    df['risk_probability'] = np.round(all_probs, 3)

    # Compute SHAP Values
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)
    df_shap = pd.DataFrame(shap_values, columns=FEATURE_COLS)

    df_risk = df[df['risk_probability'] >= 0.55].copy()
    explanations = [
        generate_plain_explanation(X.loc[idx], df_shap.loc[idx])
        for idx in df_risk.index
    ]
    df_risk['ai_explanation'] = explanations

    stats = {
        "total_students": len(df),
        "students_at_risk": len(df_risk),
        "avg_attendance": round(float(df['attendance_pct'].mean()), 1),
        "tuition_revenue_at_risk": int(df_risk['pending_tuition_fee'].sum()),
        "metrics": metrics
    }

    return model, df_risk, stats

if __name__ == "__main__":
    _, df_risk, stats = train_and_explain()
    m = stats['metrics']
    print("\n" + "="*50)
    print("📈 VALIDATED MODEL METRICS (HOLDOUT TEST SET)")
    print("="*50)
    print(f"Train/Test Samples : {m['train_samples']} / {m['test_samples']}")
    print(f"Holdout ROC-AUC    : {m['roc_auc']}")
    print(f"Holdout Precision  : {m['precision']}")
    print(f"Holdout Recall     : {m['recall']}")
    print(f"Holdout F1 Score   : {m['f1']}")
    print(f"Total Cohort Risk  : {stats['students_at_risk']} students")
    print(f"Revenue Exposure   : ₹{stats['tuition_revenue_at_risk']:,}")
    print("="*50)