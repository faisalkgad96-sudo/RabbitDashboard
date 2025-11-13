import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from io import BytesIO

# ==========================
# PAGE SETUP
# ==========================
st.set_page_config(page_title="Neighbourhood Operations Dashboard", layout="wide")
st.title("📊 Neighbourhood Operations Dashboard — Corrected Active Scooter Logic")
st.markdown("""
Upload your Excel/CSV snapshot file (every 10 minutes).  
This version fixes per-neighborhood averages, removes 'No Neighborhood', and correctly calculates ratios.
""")

# ==========================
# FILE UPLOAD
# ==========================
uploaded = st.file_uploader("📂 Upload Excel or CSV file", type=["xlsx", "xls", "csv"])

if uploaded is not None:
    # Load data
    if uploaded.name.endswith(".csv"):
        df = pd.read_csv(uploaded, encoding="utf-8")
    else:
        df = pd.read_excel(uploaded)

    df.columns = df.columns.str.strip()

    # Key columns
    col_area = "Area"
    col_neigh = "Neighborhood"
    col_start = "Start Date - Local"
    col_sessions = "Sessions"
    col_rides = "Rides"
    col_active = "Active Vehicles"
    col_urgent = "Urgent Vehicles"

    # Time handling
    df[col_start] = pd.to_datetime(df[col_start], errors="coerce")
    df["_local_time"] = df[col_start]
    df["_hour"] = df["_local_time"].dt.hour
    df["_date"] = df["_local_time"].dt.date

    # ================
    # FILTERS
    # ================
    area_list = sorted(df[col_area].dropna().unique())
    selected_area = st.sidebar.selectbox("🏙️ Choose Area", area_list, index=0)
    date_range = st.sidebar.date_input("📅 Select Date Range", [df["_date"].min(), df["_date"].max()])

    df_filtered = df[
        (df[col_area] == selected_area)
        & (df["_date"] >= date_range[0])
        & (df["_date"] <= date_range[-1])
        & (df[col_neigh].str.lower() != "no neighborhood")
    ].copy()

    st.markdown(f"### 📍 Neighborhood Breakdown — {selected_area}")

    # ==========================
    # PER-NEIGHBORHOOD SUMMARY
    # ==========================
    neighborhood_summary = []
    for n in df_filtered[col_neigh].dropna().unique():
        sub = df_filtered[df_filtered[col_neigh] == n]
        total_rides = sub[col_rides].sum()
        total_sessions = sub[col_sessions].sum()
        total_active = sub[col_active].sum()
        snapshot_count = sub["_local_time"].nunique() if sub["_local_time"].nunique() > 0 else 1
        avg_active = total_active / snapshot_count
        ratio = total_rides / avg_active if avg_active != 0 else 0
        neighborhood_summary.append([n, total_rides, total_sessions, round(avg_active, 2), round(ratio, 2)])

    agg = pd.DataFrame(neighborhood_summary, columns=["Neighborhood", "Rides", "Sessions", "Active (avg)", "Ratio"])
    st.dataframe(agg, use_container_width=True)

    # ==========================
    # HOURLY HEATMAP (Sessions)
    # ==========================
    st.markdown("### 🔥 Hourly Operations Heatmap")

    hourly = (
        df_filtered.groupby([col_neigh, "_hour"])
        .agg({ col_sessions: "sum", col_active: "sum", col_urgent: "sum" })
        .reset_index()
    )

    snapshots = (
        df_filtered.groupby([col_neigh, "_hour"])["_local_time"]
        .nunique()
        .reset_index()
        .rename(columns={"_local_time": "Snapshots"})
    )

    hourly = hourly.merge(snapshots, on=[col_neigh, "_hour"], how="left")
    hourly["Active (avg)"] = (hourly[col_active] / hourly["Snapshots"]).round(2)
    hourly["Urgent (avg)"] = (hourly[col_urgent] / hourly["Snapshots"]).round(2)

    heatmap = alt.Chart(hourly).mark_rect().encode(
        x=alt.X("_hour:O", title="Hour of Day"),
        y=alt.Y(f"{col_neigh}:O", title="Neighborhood"),
        color=alt.Color(f"{col_sessions}:Q", title="Total Sessions", scale=alt.Scale(scheme="orangered")),
        tooltip=[col_neigh, "_hour", col_sessions, "Active (avg)", "Urgent (avg)"]
    ).properties(width=1000, height=400)

    st.altair_chart(heatmap, use_container_width=True)

    # ==========================
    # HOURLY ACTIVE + URGENT + RIDES TREND (with toggle)
    # ==========================
    st.markdown("### 📈 Hourly Active, Urgent & Rides Trend")

    hourly_summary = (
        df_filtered.groupby("_hour")
        .agg({ col_active: "sum", col_urgent: "sum", col_rides: "sum" })
        .reset_index()
    )

    hourly_summary["Snapshots"] = df_filtered.groupby("_hour")["_local_time"].nunique().values
    hourly_summary["Active (avg)"] = (hourly_summary[col_active] / hourly_summary["Snapshots"]).round(2)
    hourly_summary["Urgent (avg)"] = (hourly_summary[col_urgent] / hourly_summary["Snapshots"]).round(2)
    hourly_summary["Rides (avg)"]  = (hourly_summary[col_rides]  / hourly_summary["Snapshots"]).round(2)

    # MULTI-LINE TOGGLE
    metrics_available = ["Active (avg)", "Urgent (avg)", "Rides (avg)"]
    selected_metrics = st.multiselect(
        "Show lines:",
        metrics_available,
        default=metrics_available  # show all by default
    )

    melted = hourly_summary.melt(
        id_vars="_hour",
        value_vars=selected_metrics,
        var_name="Metric",
        value_name="Value"
    )

    trend_chart = alt.Chart(melted).mark_line(point=True).encode(
        x=alt.X("_hour:O", title="Hour of Day"),
        y=alt.Y("Value:Q", title="Average Count"),
        color=alt.Color("Metric:N", title="Metric", scale=alt.Scale(scheme="category10")),
        tooltip=["_hour", "Metric", "Value"]
    ).properties(width=1000, height=400)

    st.altair_chart(trend_chart, use_container_width=True)

    # ==========================
    # EXPORT TO EXCEL
    # ==========================
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        agg.to_excel(writer, index=False, sheet_name="Neighborhood Summary")
        hourly.to_excel(writer, index=False, sheet_name="Hourly Data")
        hourly_summary.to_excel(writer, index=False, sheet_name="Hourly Summary")

    st.download_button(
        label="📥 Download Data (Excel)",
        data=output.getvalue(),
        file_name="neighbourhood_operations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("👆 Upload a data file to begin.")

