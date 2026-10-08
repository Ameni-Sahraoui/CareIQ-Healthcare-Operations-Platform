from __future__ import annotations

from pathlib import Path
import json
import os
import sqlite3
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("CAREIQ_DB_PATH", str(ROOT / "data" / "careiq.sqlite")))
METRICS_PATH = ROOT / "artifacts" / "model_metrics.json"
FORECAST_METRICS_PATH = ROOT / "artifacts" / "forecast_metrics.json"
MANIFEST_PATH = ROOT / "artifacts" / "manifest.json"
AUDIT_PATH = ROOT / "artifacts" / "consistency_audit.json"

st.set_page_config(page_title="CareIQ", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    :root { --navy:#0B2942; --blue:#176B87; --teal:#0E8A7A; --mist:#F4F8FA; --ink:#17212B; --muted:#667788; --line:#D8E4EA; --amber:#C47A08; }
    .stApp { background: linear-gradient(180deg,#FAFCFD 0%,#F3F7F9 100%); }
    [data-testid="stSidebar"] { background:#0B2942; }
    [data-testid="stSidebar"] * { color:#F6FBFD; }
    .block-container { padding-top:1.2rem; padding-bottom:3rem; max-width:1600px; }
    h1,h2,h3 { color:#0B2942; letter-spacing:-0.02em; }
    .brand { font-size:1.8rem; font-weight:850; color:#FFF; line-height:1.0; }
    .brand-sub { font-size:.82rem; color:#BFD6E3; line-height:1.35; margin:.35rem 0 1rem; }
    .page-title { font-size:2.05rem; font-weight:850; color:#0B2942; line-height:1.1; }
    .page-subtitle { color:#667788; font-size:1rem; margin:.25rem 0 .8rem; }
    .safety { background:#FFF7E8; border-left:5px solid #C47A08; border-radius:10px; padding:.72rem .95rem; color:#563900; margin:.45rem 0 1rem; font-size:.92rem; }
    .info { background:#EAF5F7; border-left:5px solid #176B87; border-radius:10px; padding:.72rem .95rem; color:#15394A; margin:.45rem 0 1rem; }
    .panel { background:#FFF; border:1px solid #D8E4EA; border-radius:14px; padding:1rem 1.1rem; box-shadow:0 5px 18px rgba(15,35,55,.05); margin-bottom:.8rem; }
    .badge { display:inline-block; padding:.22rem .58rem; border-radius:999px; background:#DFF4EF; color:#075F54; font-size:.76rem; font-weight:750; margin-right:.3rem; }
    .badge2 { display:inline-block; padding:.22rem .58rem; border-radius:999px; background:#E6EEF5; color:#174A67; font-size:.76rem; font-weight:750; margin-right:.3rem; }
    [data-testid="stMetric"] { background:#FFF; border:1px solid #D8E4EA; border-radius:12px; padding:.72rem .85rem; box-shadow:0 3px 12px rgba(15,35,55,.04); }
    [data-testid="stDataFrame"] { border:1px solid #D8E4EA; border-radius:10px; overflow:hidden; }
    footer { visibility:hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=120)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as connection:
        return pd.read_sql_query(sql, connection, params=params)


@st.cache_data(ttl=300)
def load_json(path: str) -> dict:
    file = Path(path)
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}


def page_header(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="page-title">{title}</div><div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="safety"><b>Operational analytics prototype.</b> All data are fictional and synthetic. CareIQ is not a medical diagnostic or treatment system, does not recommend clinical care, and must not replace healthcare professionals or local operational governance.</div>',
        unsafe_allow_html=True,
    )


def pct(value: float) -> str:
    return "—" if pd.isna(value) else f"{value:.1%}"


def minutes(value: float) -> str:
    return "—" if pd.isna(value) else f"{value:,.1f} min"


def latest_operational_date() -> str:
    return str(query("SELECT MAX(activity_date) AS d FROM DEPARTMENT_DAILY").iloc[0, 0])


def department_options() -> pd.DataFrame:
    return query(
        """
        SELECT d.department_id, d.department_name, d.department_group, f.facility_name, f.province,
               d.department_name || ' · ' || f.facility_name || ' · ' || f.province AS label
        FROM DEPARTMENT d JOIN FACILITY f ON d.facility_id=f.facility_id
        ORDER BY f.province, f.facility_name, d.department_name
        """
    )


def executive_overview() -> None:
    page_header("Executive Overview", "Network-level demand, access, capacity, patient-flow and service-experience intelligence.")
    kpi = query(
        """
        SELECT COUNT(*) AS total,
               AVG(CASE WHEN status='No-Show' THEN 1.0 WHEN status IN ('Completed','Cancelled') THEN 0.0 END) AS no_show_rate,
               AVG(CASE WHEN status='Cancelled' THEN 1.0 WHEN status IN ('Completed','No-Show') THEN 0.0 END) AS cancellation_rate,
               SUM(CASE WHEN status='Scheduled' THEN 1 ELSE 0 END) AS upcoming
        FROM APPOINTMENT
        """
    ).iloc[0]
    operations = query(
        """
        SELECT AVG(total_wait_minutes) AS avg_wait,
               AVG(wait_target_exceeded) AS wait_exceeded,
               AVG(overall_score) AS satisfaction
        FROM WAIT_TIME w
        LEFT JOIN SATISFACTION s ON w.appointment_id=s.appointment_id
        """
    ).iloc[0]
    daily = query("SELECT AVG(CASE WHEN scheduled_appointments>0 THEN utilization_ratio END) AS utilization, SUM(capacity_pressure_label) AS pressure_days FROM DEPARTMENT_DAILY").iloc[0]
    cols = st.columns(7)
    cols[0].metric("Appointments", f"{int(kpi.total):,}")
    cols[1].metric("Upcoming", f"{int(kpi.upcoming):,}")
    cols[2].metric("No-show rate", pct(float(kpi.no_show_rate)))
    cols[3].metric("Cancellation rate", pct(float(kpi.cancellation_rate)))
    cols[4].metric("Average wait", minutes(float(operations.avg_wait)))
    cols[5].metric("Capacity utilization", pct(float(daily.utilization)))
    cols[6].metric("Satisfaction", f"{float(operations.satisfaction):.2f}/5")
    st.markdown(f'<span class="badge">Synthetic data</span><span class="badge2">Operational date {latest_operational_date()}</span>', unsafe_allow_html=True)

    left, right = st.columns([1.15, 1])
    with left:
        trend = query(
            """
            SELECT appointment_date, COUNT(*) AS appointments,
                   SUM(CASE WHEN status='No-Show' THEN 1 ELSE 0 END) AS no_shows,
                   SUM(CASE WHEN status='Cancelled' THEN 1 ELSE 0 END) AS cancellations
            FROM APPOINTMENT
            GROUP BY appointment_date ORDER BY appointment_date
            """
        )
        trend["appointment_date"] = pd.to_datetime(trend["appointment_date"])
        monthly = trend.set_index("appointment_date").resample("MS").sum().reset_index()
        fig = px.line(monthly, x="appointment_date", y=["appointments", "no_shows", "cancellations"], title="Monthly appointment demand and non-completion")
        fig.update_layout(xaxis_title="Month", yaxis_title="Appointments", legend_title="Measure", margin=dict(l=10, r=10, t=55, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        pressure = query(
            """
            SELECT d.department_group, AVG(CASE WHEN dd.scheduled_appointments>0 THEN dd.utilization_ratio END) AS utilization,
                   AVG(dd.staffing_gap_rate) AS staffing_gap,
                   AVG(dd.p90_wait_minutes) AS p90_wait,
                   AVG(dd.capacity_pressure_label) AS pressure_rate
            FROM DEPARTMENT_DAILY dd JOIN DEPARTMENT d ON dd.department_id=d.department_id
            GROUP BY d.department_group ORDER BY pressure_rate DESC
            """
        )
        fig = px.scatter(pressure, x="utilization", y="p90_wait", size="pressure_rate", color="staffing_gap", text="department_group", title="Operational pressure by service group")
        fig.update_traces(textposition="top center")
        fig.update_layout(xaxis_tickformat=".0%", xaxis_title="Average utilization", yaxis_title="P90 wait (minutes)", margin=dict(l=10, r=10, t=55, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Highest forecast capacity pressure")
    queue = query(
        """
        SELECT p.entity_id, d.department_name, f.facility_name, f.province,
               substr(p.entity_id, length(d.department_id)+2) AS forecast_date,
               p.probability, p.risk_band, p.decision_support
        FROM PREDICTION p
        JOIN DEPARTMENT d ON p.entity_id LIKE d.department_id || '_%'
        JOIN FACILITY f ON d.facility_id=f.facility_id
        WHERE p.entity_type='DepartmentDayForecast'
        ORDER BY p.probability DESC LIMIT 20
        """
    )
    st.dataframe(queue.drop(columns="entity_id"), use_container_width=True, hide_index=True)


def patient_flow_page() -> None:
    page_header("Patient Flow", "Appointment-to-discharge flow, queue time, throughput and bottleneck intelligence.")
    stage = query(
        """
        SELECT stage_order, stage_name, COUNT(*) AS events,
               AVG(queue_minutes) AS avg_queue,
               AVG(duration_minutes) AS avg_service,
               MAX(queue_minutes) AS max_queue
        FROM PATIENT_FLOW GROUP BY stage_order, stage_name ORDER BY stage_order
        """
    )
    fig = go.Figure()
    fig.add_bar(x=stage["stage_name"], y=stage["avg_queue"], name="Average queue")
    fig.add_bar(x=stage["stage_name"], y=stage["avg_service"], name="Average service")
    fig.update_layout(barmode="group", title="Average queue and service time by flow stage", xaxis_title="Operational stage", yaxis_title="Minutes", margin=dict(l=10, r=10, t=55, b=80))
    st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns([1.05, 1])
    with left:
        bottleneck = query(
            """
            SELECT f.facility_name, d.department_name, pf.stage_name,
                   AVG(pf.queue_minutes) AS avg_queue_minutes,
                   COUNT(*) AS stage_events
            FROM PATIENT_FLOW pf
            JOIN APPOINTMENT a ON pf.appointment_id=a.appointment_id
            JOIN DEPARTMENT d ON a.department_id=d.department_id
            JOIN FACILITY f ON a.facility_id=f.facility_id
            GROUP BY f.facility_name, d.department_name, pf.stage_name
            HAVING COUNT(*) >= 30
            ORDER BY avg_queue_minutes DESC LIMIT 25
            """
        )
        st.subheader("Bottleneck queue")
        st.dataframe(bottleneck, use_container_width=True, hide_index=True)
    with right:
        appointments = query("SELECT appointment_id FROM PATIENT_FLOW GROUP BY appointment_id ORDER BY appointment_id DESC LIMIT 1000")["appointment_id"].tolist()
        selected = st.selectbox("Inspect a synthetic completed appointment", appointments)
        flow = query(
            """
            SELECT stage_order, stage_name, stage_start, stage_end, queue_minutes, duration_minutes
            FROM PATIENT_FLOW WHERE appointment_id=? ORDER BY stage_order
            """,
            (selected,),
        )
        flow["stage_start"] = pd.to_datetime(flow["stage_start"])
        flow["stage_end"] = pd.to_datetime(flow["stage_end"])
        fig = px.timeline(flow, x_start="stage_start", x_end="stage_end", y="stage_name", color="queue_minutes", title=f"Operational journey · {selected}")
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(margin=dict(l=10, r=10, t=55, b=10))
        st.plotly_chart(fig, use_container_width=True)


def capacity_page() -> None:
    page_header("Capacity", "Department utilization, staffing pressure, overtime and high-pressure day detection.")
    days = st.slider("Recent days", 14, 120, 45)
    frame = query(
        """
        SELECT dd.*, d.department_name, f.facility_name
        FROM DEPARTMENT_DAILY dd
        JOIN DEPARTMENT d ON dd.department_id=d.department_id
        JOIN FACILITY f ON dd.facility_id=f.facility_id
        WHERE date(dd.activity_date) >= date((SELECT MAX(activity_date) FROM DEPARTMENT_DAILY), ?) AND dd.scheduled_appointments > 0
        """,
        (f"-{days} days",),
    )
    summary = frame.groupby(["department_id", "department_name", "facility_name", "province", "department_group"], as_index=False).agg(
        utilization=("utilization_ratio", "mean"),
        staffing_gap=("staffing_gap_rate", "mean"),
        p90_wait=("p90_wait_minutes", "mean"),
        pressure_days=("capacity_pressure_label", "sum"),
        overtime=("overtime_hours", "sum"),
    )
    fig = px.scatter(summary, x="utilization", y="staffing_gap", size="pressure_days", color="p90_wait", hover_name="department_name", hover_data=["facility_name", "province", "overtime"], title="Department capacity and staffing pressure")
    fig.update_layout(xaxis_tickformat=".0%", yaxis_tickformat=".0%", xaxis_title="Average utilization", yaxis_title="Average staffing gap", margin=dict(l=10, r=10, t=55, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(summary.sort_values(["pressure_days", "utilization"], ascending=False).head(30), use_container_width=True, hide_index=True)


def demand_forecast_page() -> None:
    page_header("Demand Forecast", "Daily, weekly and monthly operational demand forecasting with uncertainty intervals.")
    departments = department_options()
    label = st.selectbox("Department", departments["label"].tolist())
    department_id = departments.loc[departments["label"] == label, "department_id"].iloc[0]
    types = query("SELECT DISTINCT appointment_type FROM DEMAND_FORECAST WHERE department_id=? ORDER BY appointment_type", (department_id,))["appointment_type"].tolist()
    appointment_type = st.selectbox("Appointment type", ["All types"] + types)
    granularity = st.radio("Granularity", ["Daily", "Weekly", "Monthly"], horizontal=True)

    actual = query(
        """
        SELECT appointment_date AS date, appointment_type, COUNT(*) AS value
        FROM APPOINTMENT
        WHERE department_id=? AND date(appointment_date) <= date((SELECT MAX(activity_date) FROM DEPARTMENT_DAILY))
        GROUP BY appointment_date, appointment_type
        """,
        (department_id,),
    )
    forecast = query("SELECT forecast_date AS date, appointment_type, forecast_count AS value, lower_bound, upper_bound FROM DEMAND_FORECAST WHERE department_id=?", (department_id,))
    if appointment_type != "All types":
        actual = actual[actual["appointment_type"] == appointment_type]
        forecast = forecast[forecast["appointment_type"] == appointment_type]
    actual["date"] = pd.to_datetime(actual["date"])
    forecast["date"] = pd.to_datetime(forecast["date"])
    actual_group = actual.groupby("date", as_index=False)["value"].sum()
    forecast_group = forecast.groupby("date", as_index=False)[["value", "lower_bound", "upper_bound"]].sum()
    rule = {"Daily": "D", "Weekly": "W-MON", "Monthly": "MS"}[granularity]
    if granularity != "Daily":
        actual_group = actual_group.set_index("date").resample(rule).sum().reset_index()
        forecast_group = forecast_group.set_index("date").resample(rule).sum().reset_index()
    actual_group = actual_group.tail(180 if granularity == "Daily" else 80)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=actual_group["date"], y=actual_group["value"], name="Actual synthetic demand", mode="lines"))
    fig.add_trace(go.Scatter(x=forecast_group["date"], y=forecast_group["value"], name="Forecast", mode="lines"))
    fig.add_trace(go.Scatter(x=pd.concat([forecast_group["date"], forecast_group["date"][::-1]]), y=pd.concat([forecast_group["upper_bound"], forecast_group["lower_bound"][::-1]]), fill="toself", fillcolor="rgba(23,107,135,0.15)", line=dict(color="rgba(255,255,255,0)"), hoverinfo="skip", name="Uncertainty interval"))
    fig.update_layout(title=f"{granularity} demand · {label}", xaxis_title="Date", yaxis_title="Appointments", margin=dict(l=10, r=10, t=55, b=10))
    st.plotly_chart(fig, use_container_width=True)
    metrics = load_json(str(FORECAST_METRICS_PATH))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selected model", metrics.get("selected_model", "—"))
    selected = metrics.get("candidate_metrics", {}).get(metrics.get("selected_model", ""), {}).get("holdout", {})
    c2.metric("Temporal holdout MAE", f"{selected.get('mae', float('nan')):.3f}" if selected else "—")
    c3.metric("Temporal holdout WAPE", pct(selected.get("wape", float("nan"))) if selected else "—")
    c4.metric("Interval coverage", pct(metrics.get("holdout_interval_coverage", float("nan"))))


def risk_page() -> None:
    page_header("No-Show Risk", "Upcoming no-show and cancellation risk for operational outreach and schedule management.")
    tab1, tab2, tab3 = st.tabs(["No-show", "Cancellation", "Explainability"])
    with tab1:
        risk = query(
            """
            SELECT p.entity_id AS appointment_id, a.scheduled_at, d.department_name, f.facility_name,
                   a.appointment_type, a.booking_channel, p.probability, p.risk_band,
                   p.top_factor_1, p.top_factor_2, p.top_factor_3, p.decision_support
            FROM PREDICTION p
            JOIN APPOINTMENT a ON p.entity_id=a.appointment_id
            JOIN DEPARTMENT d ON a.department_id=d.department_id
            JOIN FACILITY f ON a.facility_id=f.facility_id
            WHERE p.task_name='no_show' AND p.entity_type='Appointment'
            ORDER BY p.probability DESC
            """
        )
        st.dataframe(risk.head(100), use_container_width=True, hide_index=True)
        fig = px.histogram(risk, x="probability", color="risk_band", nbins=30, title="Upcoming no-show risk distribution")
        fig.update_layout(xaxis_tickformat=".0%", xaxis_title="Predicted operational probability", yaxis_title="Appointments")
        st.plotly_chart(fig, use_container_width=True)
    with tab2:
        risk = query(
            """
            SELECT p.entity_id AS appointment_id, a.scheduled_at, d.department_name, f.facility_name,
                   a.appointment_type, a.booking_channel, p.probability, p.risk_band,
                   p.top_factor_1, p.top_factor_2, p.top_factor_3, p.decision_support
            FROM PREDICTION p
            JOIN APPOINTMENT a ON p.entity_id=a.appointment_id
            JOIN DEPARTMENT d ON a.department_id=d.department_id
            JOIN FACILITY f ON a.facility_id=f.facility_id
            WHERE p.task_name='cancellation' AND p.entity_type='Appointment'
            ORDER BY p.probability DESC
            """
        )
        st.dataframe(risk.head(100), use_container_width=True, hide_index=True)
        fig = px.histogram(risk, x="probability", color="risk_band", nbins=30, title="Upcoming cancellation risk distribution")
        fig.update_layout(xaxis_tickformat=".0%", xaxis_title="Predicted operational probability", yaxis_title="Appointments")
        st.plotly_chart(fig, use_container_width=True)
    with tab3:
        task = st.selectbox("Prediction task", ["no_show", "cancellation", "wait_time_risk", "capacity_pressure"])
        explain = query("SELECT feature_name, importance_value, importance_rank FROM GLOBAL_EXPLANATION WHERE task_name=? ORDER BY importance_rank LIMIT 15", (task,))
        fig = px.bar(explain.sort_values("importance_value"), x="importance_value", y="feature_name", orientation="h", title=f"Global SHAP importance · {task}")
        fig.update_layout(xaxis_title="Mean absolute contribution", yaxis_title="Feature", margin=dict(l=10, r=10, t=55, b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('<div class="info">SHAP describes model contribution, not causation. A feature can be predictive without being an appropriate intervention target.</div>', unsafe_allow_html=True)


def waiting_page() -> None:
    page_header("Waiting-Time Intelligence", "Average, median and P90 waiting time, target exceedance and predicted waiting-time risk.")
    waits = query(
        """
        SELECT w.*, d.department_name, d.department_group, f.facility_name, f.province
        FROM WAIT_TIME w
        JOIN APPOINTMENT a ON w.appointment_id=a.appointment_id
        JOIN DEPARTMENT d ON a.department_id=d.department_id
        JOIN FACILITY f ON a.facility_id=f.facility_id
        """
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Average wait", minutes(waits["total_wait_minutes"].mean()))
    c2.metric("Median wait", minutes(waits["total_wait_minutes"].median()))
    c3.metric("P90 wait", minutes(waits["total_wait_minutes"].quantile(.9)))
    c4.metric("Target exceeded", pct(waits["wait_target_exceeded"].mean()))
    left, right = st.columns(2)
    with left:
        fig = px.histogram(waits.sample(min(20000, len(waits)), random_state=42), x="total_wait_minutes", color="department_group", nbins=60, title="Waiting-time distribution")
        fig.update_layout(xaxis_title="Total wait minutes", yaxis_title="Appointments")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        summary = waits.groupby("department_group", as_index=False).agg(avg_wait=("total_wait_minutes", "mean"), p90_wait=("total_wait_minutes", lambda s: s.quantile(.9)), target_exceeded=("wait_target_exceeded", "mean"))
        fig = px.bar(summary.sort_values("p90_wait"), x="p90_wait", y="department_group", orientation="h", color="target_exceeded", title="P90 wait by service group")
        fig.update_layout(xaxis_title="P90 minutes", yaxis_title="Service group")
        st.plotly_chart(fig, use_container_width=True)
    st.subheader("Upcoming waiting-time risk")
    future = query(
        """
        SELECT p.entity_id AS appointment_id, a.scheduled_at, d.department_name, f.facility_name,
               p.probability, p.risk_band, p.decision_support
        FROM PREDICTION p JOIN APPOINTMENT a ON p.entity_id=a.appointment_id
        JOIN DEPARTMENT d ON a.department_id=d.department_id JOIN FACILITY f ON a.facility_id=f.facility_id
        WHERE p.task_name='wait_time_risk' ORDER BY p.probability DESC LIMIT 100
        """
    )
    st.dataframe(future, use_container_width=True, hide_index=True)


def department_performance_page() -> None:
    page_header("Department Performance", "Balanced operational comparison across demand, utilization, waiting, completion and experience.")
    performance = query(
        """
        SELECT dd.department_id, d.department_name, d.department_group, f.facility_name, f.province,
               SUM(dd.scheduled_appointments) AS appointments,
               AVG(CASE WHEN dd.scheduled_appointments>0 THEN dd.utilization_ratio END) AS utilization,
               AVG(dd.p90_wait_minutes) AS p90_wait,
               AVG(dd.satisfaction_score) AS satisfaction,
               SUM(dd.no_shows)*1.0/NULLIF(SUM(dd.scheduled_appointments),0) AS no_show_rate,
               SUM(dd.cancellations)*1.0/NULLIF(SUM(dd.scheduled_appointments),0) AS cancellation_rate,
               AVG(dd.staffing_gap_rate) AS staffing_gap
        FROM DEPARTMENT_DAILY dd
        JOIN DEPARTMENT d ON dd.department_id=d.department_id
        JOIN FACILITY f ON dd.facility_id=f.facility_id
        GROUP BY dd.department_id, d.department_name, d.department_group, f.facility_name, f.province
        """
    )
    fig = px.scatter(performance, x="utilization", y="satisfaction", size="appointments", color="p90_wait", hover_name="department_name", hover_data=["facility_name", "province", "no_show_rate", "cancellation_rate", "staffing_gap"], title="Utilization versus patient experience")
    fig.update_layout(xaxis_tickformat=".0%", xaxis_title="Average utilization", yaxis_title="Mean satisfaction", margin=dict(l=10, r=10, t=55, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(performance.sort_values(["p90_wait", "staffing_gap"], ascending=False), use_container_width=True, hide_index=True)


def patient_experience_page() -> None:
    page_header("Patient Experience", "Synthetic satisfaction and service-experience patterns without clinical inference.")
    experience = query(
        """
        SELECT s.*, w.total_wait_minutes, d.department_group, d.department_name, f.facility_name, f.province
        FROM SATISFACTION s JOIN APPOINTMENT a ON s.appointment_id=a.appointment_id
        JOIN WAIT_TIME w ON s.appointment_id=w.appointment_id
        JOIN DEPARTMENT d ON a.department_id=d.department_id JOIN FACILITY f ON a.facility_id=f.facility_id
        """
    )
    left, right = st.columns(2)
    with left:
        sample = experience.sample(min(15000, len(experience)), random_state=42)
        fig = px.scatter(sample, x="total_wait_minutes", y="overall_score", color="department_group", opacity=.45, title="Waiting time and satisfaction")
        fig.update_layout(xaxis_title="Wait minutes", yaxis_title="Overall score (1–5)")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        feedback = experience.groupby("feedback_category", as_index=False).agg(surveys=("satisfaction_id", "count"), score=("overall_score", "mean"))
        fig = px.bar(feedback, x="feedback_category", y="surveys", color="score", title="Feedback category distribution")
        fig.update_layout(xaxis_title="Feedback category", yaxis_title="Synthetic surveys")
        st.plotly_chart(fig, use_container_width=True)
    province = experience.groupby("province", as_index=False).agg(overall_score=("overall_score", "mean"), wait_score=("wait_experience_score", "mean"), surveys=("satisfaction_id", "count"), avg_wait=("total_wait_minutes", "mean"))
    st.dataframe(province, use_container_width=True, hide_index=True)


def what_if_page() -> None:
    page_header("What-If Simulator", "Operational sensitivity analysis for capacity, staffing and schedule smoothing. Results are simulations, not causal evidence.")
    departments = department_options()
    label = st.selectbox("Department for simulation", departments["label"].tolist())
    department_id = departments.loc[departments["label"] == label, "department_id"].iloc[0]
    capacity_change = st.slider("Appointment capacity change", -30, 50, 10, format="%d%%") / 100.0
    staffing_change = st.slider("Staffing-hours change", -25, 40, 10, format="%d%%") / 100.0
    smoothing = st.slider("Demand shifted from peak days", 0, 30, 10, format="%d%%") / 100.0
    baseline = query(
        """
        SELECT
            (SELECT SUM(forecast_count) FROM DEMAND_FORECAST WHERE department_id=? AND horizon_days<=30) AS demand,
            d.appointment_slots_daily AS daily_slots,
            (SELECT AVG(staffing_gap_rate) FROM DEPARTMENT_DAILY WHERE department_id=d.department_id AND date(activity_date) >= date((SELECT MAX(activity_date) FROM DEPARTMENT_DAILY), '-90 days')) AS staffing_gap,
            (SELECT AVG(average_wait_minutes) FROM DEPARTMENT_DAILY WHERE department_id=d.department_id AND date(activity_date) >= date((SELECT MAX(activity_date) FROM DEPARTMENT_DAILY), '-90 days')) AS avg_wait
        FROM DEPARTMENT d WHERE d.department_id=?
        """,
        (department_id, department_id),
    ).iloc[0]
    baseline_demand = float(baseline.demand or 0)
    baseline_slots_30 = float(baseline.daily_slots or 1) * 30
    baseline_utilization = baseline_demand / max(baseline_slots_30, 1)
    adjusted_demand_peak = baseline_demand * (1 - 0.35 * smoothing)
    adjusted_slots = baseline_slots_30 * (1 + capacity_change)
    adjusted_staff_gap = max(0.0, min(1.0, float(baseline.staffing_gap or 0) - 0.55 * staffing_change))
    adjusted_utilization = adjusted_demand_peak / max(adjusted_slots, 1)
    baseline_wait = float(baseline.avg_wait or 20)
    pressure_ratio = adjusted_utilization / max(baseline_utilization, .05)
    adjusted_wait = max(3.0, baseline_wait * pressure_ratio * (1 + adjusted_staff_gap - float(baseline.staffing_gap or 0)))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("30-day forecast demand", f"{baseline_demand:,.1f}")
    c2.metric("Estimated utilization", pct(adjusted_utilization), delta=f"{(adjusted_utilization-baseline_utilization):+.1%}")
    c3.metric("Estimated average wait", minutes(adjusted_wait), delta=f"{adjusted_wait-baseline_wait:+.1f} min", delta_color="inverse")
    c4.metric("Estimated staffing gap", pct(adjusted_staff_gap), delta=f"{adjusted_staff_gap-float(baseline.staffing_gap or 0):+.1%}", delta_color="inverse")
    st.markdown('<div class="info"><b>Interpretation:</b> This deterministic sensitivity model illustrates how changing operational assumptions could affect utilization and waiting. It is not a causal estimate, staffing prescription or clinical recommendation.</div>', unsafe_allow_html=True)


def model_lab_page() -> None:
    page_header("Model Lab", "Temporal validation, model comparison, forecasting performance and responsible interpretation.")
    metric = query("SELECT * FROM MODEL_METRIC")
    task = st.selectbox("Task", sorted(metric["task_name"].unique()))
    selected = metric[(metric["task_name"] == task) & (metric["split_name"].isin(["temporal_cv_mean", "temporal_holdout"]))]
    pivot = selected.pivot_table(index=["model_name", "split_name"], columns="metric_name", values="metric_value").reset_index()
    st.dataframe(pivot, use_container_width=True, hide_index=True)
    if "pr_auc" in selected["metric_name"].unique():
        chart = selected[(selected["metric_name"] == "pr_auc")]
        fig = px.bar(chart, x="model_name", y="metric_value", color="split_name", barmode="group", title=f"PR-AUC comparison · {task}")
        fig.update_layout(yaxis_title="PR-AUC", xaxis_title="Model")
        st.plotly_chart(fig, use_container_width=True)
    registry = query("SELECT * FROM MODEL_REGISTRY ORDER BY task_name")
    st.subheader("Selected model registry")
    st.dataframe(registry, use_container_width=True, hide_index=True)
    forecast = load_json(str(FORECAST_METRICS_PATH))
    st.subheader("Demand forecast temporal holdout")
    forecast_rows = []
    for name, details in forecast.get("candidate_metrics", {}).items():
        row = {"model": name, **details.get("holdout", {})}
        forecast_rows.append(row)
    st.dataframe(pd.DataFrame(forecast_rows), use_container_width=True, hide_index=True)
    st.markdown('<div class="safety"><b>Model boundary:</b> These models estimate operational events only. They must not be used to infer diagnosis, clinical need, treatment priority, or individual health status.</div>', unsafe_allow_html=True)


def data_quality_page() -> None:
    page_header("Data Quality", "Governed validation across keys, dates, flow sequencing, durations, labels and synthetic-data controls.")
    results = query("SELECT * FROM DATA_QUALITY_RESULT ORDER BY status DESC, severity DESC, entity_name")
    c1, c2, c3 = st.columns(3)
    c1.metric("Checks", f"{len(results):,}")
    c2.metric("Passed", f"{(results['status']=='PASS').sum():,}")
    c3.metric("Failed", f"{(results['status']=='FAIL').sum():,}")
    st.dataframe(results, use_container_width=True, hide_index=True)
    audit = load_json(str(AUDIT_PATH))
    st.markdown(f'<div class="info"><b>End-to-end audit:</b> {audit.get("overall_status","—")} · {audit.get("checks_passed",0)} passed · {audit.get("checks_failed",0)} failed.</div>', unsafe_allow_html=True)


def responsible_ai_page() -> None:
    page_header("Responsible AI", "Privacy, fairness, transparency, human oversight and prohibited-use safeguards.")
    st.markdown(
        """
        ### Non-clinical scope
        CareIQ is designed for appointment operations, capacity planning, patient flow, waiting-time management and service-quality analysis. It must never be used to diagnose disease, recommend treatment, prescribe medication, prioritize clinical care or replace professional judgment.

        ### Synthetic and de-identified design
        The packaged dataset is entirely synthetic. Patient identifiers are fictional system IDs; records are not official Canadian healthcare statistics and do not describe real facilities, providers or patients.

        ### Human oversight
        Risk scores and recommendations are prompts for operational review. Managers should examine local context, validate data quality, document decisions and involve privacy, equity, labour and clinical-governance stakeholders where appropriate.

        ### Fairness
        Age band, rurality, language and accessibility fields are retained for monitoring, but protected demographic fields are excluded from the predictive feature sets in the default implementation. Group-level error and calibration differences should still be reviewed before deployment.

        ### Explainability and causality
        SHAP values show how model inputs influence a prediction. They do not establish causation and should not be translated automatically into interventions.

        ### Inappropriate uses
        Do not use CareIQ for individual health profiling, insurance eligibility, clinical triage, denial of service, staff discipline, automated scheduling decisions without review, or any purpose inconsistent with applicable privacy and human-rights requirements.
        """
    )
    metrics = load_json(str(METRICS_PATH))
    fairness_rows = []
    for task, details in metrics.get("tasks", {}).items():
        for row in details.get("fairness_monitoring", []):
            fairness_rows.append({"task": task, **row})
    if fairness_rows:
        st.subheader("Synthetic fairness-monitoring output")
        st.dataframe(pd.DataFrame(fairness_rows), use_container_width=True, hide_index=True)


def research_methodology_page() -> None:
    page_header("Research Methodology", "Research framing, analytical architecture, validation strategy and limitations.")
    st.markdown(
        """
        ### Research question
        **How can predictive analytics and business intelligence improve healthcare operational decision-making while maintaining transparency, responsible AI and a strict non-clinical scope?**

        ### Analytical pipeline
        `Synthetic source generation → validation and cleaning → governed relational model → appointment and department-day feature stores → temporal model validation → forecasting → SHAP explanations → operational decision support → monitoring → Power BI exports`

        ### Model design
        No-show, cancellation, waiting-time risk and capacity-pressure classifiers compare Logistic Regression, Random Forest and XGBoost. Model selection is based on expanding temporal cross-validation PR-AUC, followed by a later temporal holdout. Demand forecasting compares a seven-day seasonal baseline, histogram gradient boosting, random forest regression and XGBoost regression on lag/calendar features.

        ### Evaluation
        Classification reports ROC-AUC, PR-AUC, precision, recall, F1, Brier score and confusion-matrix counts. Forecasting reports MAE, RMSE, WAPE and empirical uncertainty-interval coverage. Metrics are generated from the executable synthetic pipeline; they are not manually entered.

        ### Decision support
        Recommendations contain evidence, interpretation, an operational suggestion and a limitation. Suggestions focus on confirmation outreach, wait-list management, capacity review, staffing coverage, queue sequencing and schedule smoothing.

        ### Limitations
        Synthetic-data performance does not establish real-world performance. Operational relationships may shift across institutions, regions, policy settings and time. Forecast intervals are residual-based rather than full probabilistic forecasts. Simulation outputs are sensitivity analyses, not causal estimates.
        """
    )
    manifest = load_json(str(MANIFEST_PATH))
    st.subheader("Build lineage")
    st.json({key: manifest.get(key) for key in ["dataset_version", "model_version", "selected_models", "forecast_model", "consistency_audit_status"]})


st.sidebar.markdown('<div class="brand">CareIQ</div><div class="brand-sub">Healthcare Operations & Patient Experience Intelligence<br><b>From Healthcare Data to Better Operational Decisions.</b></div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="safety" style="font-size:.78rem;margin:.2rem 0 1rem"><b>Synthetic operational prototype.</b><br>Not for diagnosis, treatment, prescribing or clinical decision-making.</div>', unsafe_allow_html=True)

PAGES = {
    "Executive Overview": executive_overview,
    "Patient Flow": patient_flow_page,
    "Capacity": capacity_page,
    "Demand Forecast": demand_forecast_page,
    "No-Show Risk": risk_page,
    "Waiting-Time Intelligence": waiting_page,
    "Department Performance": department_performance_page,
    "Patient Experience": patient_experience_page,
    "What-If Simulator": what_if_page,
    "Model Lab": model_lab_page,
    "Data Quality": data_quality_page,
    "Responsible AI": responsible_ai_page,
    "Research Methodology": research_methodology_page,
}

page = st.sidebar.radio("Navigate", list(PAGES.keys()))
manifest = load_json(str(MANIFEST_PATH))
st.sidebar.caption(f"Dataset: {manifest.get('dataset_name','not built')}\n\nAudit: {manifest.get('consistency_audit_status','not run')}")

if not DB_PATH.exists():
    st.error("CareIQ database not found. Run `python -m careiq.bootstrap --mode demo` first.")
else:
    PAGES[page]()
