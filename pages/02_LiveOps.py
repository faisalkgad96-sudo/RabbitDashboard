import streamlit as st
import pandas as pd

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
# FILE UPLOAD
# -------------------------------------------------
uploaded = st.file_uploader("📂 Upload Raw Live Ops File (xlsx/csv)", type=["xlsx", "xls", "csv"])

if uploaded:
    df = pd.read_excel(uploaded) if uploaded.name.endswith((".xlsx", ".xls")) else pd.read_csv(uploaded)
    st.session_state["df"] = df


# -------------------------------------------------
# LOAD SESSION DATA
# -------------------------------------------------
if "df" not in st.session_state:
    st.warning("Upload a raw Live Ops file to continue.")
    st.stop()


df = st.session_state["df"].copy()



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
            Ride_Image=("Main Case", lambda s: (s == "Ride Image").sum()),
            Handling=("Handling Time", "mean"),
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
