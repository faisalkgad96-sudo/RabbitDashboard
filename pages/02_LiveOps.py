import streamlit as st
import pandas as pd
import json
import requests
from io import BytesIO

from utils.processing import parse_and_compute_all
from components.kpi_cards import render_kpis
from components.charts import (
    dod_chart,
    case_reasons_chart,
    area_chart,
    dual_line_times,
    multi_case_trends,
    interval_heatmap
)

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
st.set_page_config(layout="wide")
st.title("📟 Live Ops Dashboard")

# -------------------------------------------------
# DEFAULT API TOKEN (used if user leaves token empty)
# -------------------------------------------------
DEFAULT_RABBIT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiI2NzM5MzI0OTg5MzA5MmRmYTMwZjhhYTgiLCJpYXQiOjE3NjMyNzk3NjksImV4cCI6MTc2NTg3MTc2OX0.Kh3RxvQmV5eQJmUsVluS04FFc1sUjfA7Fq3yGnVlfbk"


# -------------------------------------------------
# 🔐 Live Ops API Fetch Function
# -------------------------------------------------
def fetch_liveops_data(start_date, end_date, token_value):
    url = "https://dashboard.rabbit-api.app/export"

    headers = {
        "Authorization": f"Bearer {token_value}",
        "Content-Type": "application/json"
    }

    filters_json = json.dumps({
        "vehicle": {},
        "area": [],
        "startDateCreation": f"{start_date}T00:00:00+02:00",
        "endDateCreation": f"{end_date}T23:59:59+02:00"
    })

    payload = {
        "module": "Tasks",
        "fields": "area,mainCase,created,createdLocal,resolved,assignedToName,assignedToAt,mainCaseResolvedAt,assignedCount",
        "filters": filters_json
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        st.error(f"❌ API Error {response.status_code}")
        st.code(response.text)
        return None

    content_type = response.headers.get("Content-Type", "")

    # Excel
    if "spreadsheetml" in content_type:
        return pd.read_excel(BytesIO(response.content))

    # CSV
    if "csv" in content_type:
        return pd.read_csv(BytesIO(response.content))

    # JSON
    try:
        return pd.DataFrame(response.json())
    except:
        return None


# -------------------------------------------------
# FETCH FROM API
# -------------------------------------------------
with st.expander("📡 Fetch Live Ops Data from Rabbit API"):
    col1, col2, col3 = st.columns([1, 1, 1])

    api_start = col1.date_input("Start Date")
    api_end = col2.date_input("End Date")
    token_input = col3.text_input("API Token (optional — leave blank to use app token)", type="password")

    api_btn = st.button("⚡ Fetch Live Ops Data")

df = None

if api_btn:
    token_val = token_input.strip() if token_input else DEFAULT_RABBIT_TOKEN

    with st.spinner("Fetching live data…"):
        df = fetch_liveops_data(str(api_start), str(api_end), token_val)

    if df is not None:
        st.session_state["df"] = df
        st.success("✅ Live Ops data fetched successfully!")
    else:
        st.error("❌ Could not fetch API data.")


# -------------------------------------------------
# FILE UPLOAD FALLBACK
# -------------------------------------------------
with st.expander("📂 Upload Raw Live Ops File (xlsx/csv)"):
    uploaded = st.file_uploader("Upload file", type=["xlsx", "xls", "csv"])

if uploaded:
    df = pd.read_excel(uploaded) if uploaded.name.endswith(".xlsx") else pd.read_csv(uploaded)
    st.session_state["df"] = df


# -------------------------------------------------
# LOAD SESSION DATA
# -------------------------------------------------
if "df" not in st.session_state:
    st.warning("Upload a file, fetch from API, or use the app landing uploader to continue.")
    st.stop()

df = st.session_state["df"].copy()


# -------------------------------------------------
# COLUMN NORMALIZATION
# (map API → dashboard expected names)
# -------------------------------------------------
rename_map = {
    "area": "Area",
    "mainCase": "Main Case",
    "created": "Created At",
    "createdLocal": "Created At (Local)",
    "resolved": "Resolved At",
    "assignedToName": "Assigned To Name",
    "assignedToAt": "Assigned To At",
    "mainCaseResolvedAt": "First Pending At",
    "assignedCount": "Num Of Assignments",
}

df.rename(columns=rename_map, inplace=True, errors="ignore")

# -------------------------------------------------
# APPLY TIME CALCULATIONS
# -------------------------------------------------
df = parse_and_compute_all(df)


# -------------------------------------------------
# FILTERS BLOCK (original)
# -------------------------------------------------
with st.expander("Filters", expanded=True):
    c1, c2, c3, c4 = st.columns(4)

    area_opts = sorted(df["Area"].dropna().unique()) if "Area" in df.columns else []
    main_opts = sorted(df["Main Case"].dropna().unique()) if "Main Case" in df.columns else []
    assigned_opts = sorted(df["Assigned To Name"].dropna().unique()) if "Assigned To Name" in df.columns else []

    selected_area = c1.multiselect("Area", options=area_opts)
    selected_main = c2.multiselect("Main Case", options=main_opts)
    selected_assigned = c3.multiselect("Assigned To Name", options=assigned_opts)
    selected_dates = c4.date_input("Created Date Range", [])


# APPLY FILTERS
df_f = df.copy()

if selected_area:
    df_f = df_f[df_f["Area"].isin(selected_area)]

if selected_main:
    df_f = df_f[df_f["Main Case"].isin(selected_main)]

if selected_assigned:
    df_f = df_f[df_f["Assigned To Name"].isin(selected_assigned)]

if isinstance(selected_dates, list) and len(selected_dates) == 2:
    start, end = selected_dates
    df_f = df_f[
        (pd.to_datetime(df_f["Created Date"]) >= pd.to_datetime(start))
        & (pd.to_datetime(df_f["Created Date"]) <= pd.to_datetime(end))
    ]


# -------------------------------------------------
# KPI CARDS
# -------------------------------------------------
render_kpis(df_f)

st.markdown("---")


# -------------------------------------------------
# TOP CHARTS ROW
# -------------------------------------------------
colA, colB, colC = st.columns([2, 1, 1])

with colA:
    st.subheader("Task.DOD")
    st.altair_chart(dod_chart(df_f), use_container_width=True)

with colB:
    st.subheader("Case Reasons")
    st.altair_chart(case_reasons_chart(df_f), use_container_width=True)

with colC:
    st.subheader("By Area")
    st.altair_chart(area_chart(df_f), use_container_width=True)

st.markdown("---")


# -------------------------------------------------
# LINE CHARTS
# -------------------------------------------------
lineA, lineB = st.columns(2)

with lineA:
    st.subheader("On Queue Time vs Resolution Time")
    st.altair_chart(dual_line_times(df_f), use_container_width=True)

with lineB:
    st.subheader("Case Reasons Trends")
    st.altair_chart(multi_case_trends(df_f), use_container_width=True)

st.markdown("---")


# -------------------------------------------------
# INTERVAL HEATMAP
# -------------------------------------------------
st.subheader("Assigned Per Interval")
st.altair_chart(interval_heatmap(df_f), use_container_width=True)

st.markdown("---")


# -------------------------------------------------
# SIDE-BY-SIDE SUMMARY TABLES
# -------------------------------------------------
st.markdown("### Summary Tables")

left, right = st.columns([1, 1], gap="large")

with left:
    st.markdown("#### Main Case Summary")

    case_table = (
        df_f.groupby("Main Case")
        .agg(
            Count=("Main Case", "size"),
            OnQueue=("On Queue Time", "mean"),
            Handling=("Handling Time", "mean"),
            Resolution=("Resolution Time", "mean"),
        )
        .reset_index()
        .sort_values("Count", ascending=False)
    )

    st.dataframe(
        case_table.style.format({
            "OnQueue": "{:.2f}",
            "Handling": "{:.2f}",
            "Resolution": "{:.2f}",
        }),
        use_container_width=False,
        width=600,
        height=450,
    )

with right:
    st.markdown("#### Assigned Summary (Top 20)")

    assigned_table = (
        df_f.groupby("Assigned To Name")
        .agg(
            Count=("Assigned To Name", "size"),
            Handling=("Handling Time", "mean")
        )
        .reset_index()
        .sort_values("Count", ascending=False)
        .head(20)
    )

    st.dataframe(
        assigned_table.style.format({
            "Handling": "{:.2f}",
        }),
        use_container_width=False,
        width=600,
        height=450,
    )
