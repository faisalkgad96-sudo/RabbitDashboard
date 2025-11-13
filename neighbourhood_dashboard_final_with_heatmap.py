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
st.markdown(
    "Upload your Excel/CSV snapshot file (every 10 minutes).  "
    "This version fixes per-neighborhood averages, removes 'No Neighborhood', and correctly calculates ratios."
)

# ==========================
# FILE UPLOAD
# ==========================
uploaded = st.file_uploader("📂 Upload Excel or CSV file", type=["xlsx", "xls", "csv"])

if uploaded is not None:
    # --------------------------
    # Load data
    # --------------------------
    if uploaded.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded, encoding="utf-8")
    else:
        df = pd.read_excel(uploaded)

    df.columns = df.columns.str.strip()

    # --------------------------
    # Key columns (adjust if your sheet uses slightly different names)
    # --------------------------
    col_area = "Area"
    col_neigh = "Neighborhood"
    col_start = "Start Date - Local"
    col_sessions = "Sessions"
    col_rides = "Rides"
    col_active = "Active Vehicles"
    col_urgent = "Urgent Vehicles"

    # --------------------------
    # Parse times and basic cleaning
    # --------------------------
    df[col_start] = pd.to_datetime(df[col_start], errors="coerce")
    df["_local_time"] = df[col_start]
    df["_hour"] = df["_local_time"].dt.hour
    df["_date"] = df["_local_time"].dt.date

    # --------------------------
    # Sidebar filters
    # --------------------------
    area_list = sorted(df[col_area].dropna().unique())
    selected_area = st.sidebar.selectbox("🏙️ Choose Area", area_list, index=0)
    date_range = st.sidebar.date_input(
        "📅 Select Date Range", [df["_date"].min(), df["_date"].max()]
    )

    # filter and drop 'No Neighborhood' (case-insensitive)
    df_filtered = df[
        (df[col_area] == selected_area)
        & (df["_date"] >= date_range[0])
        & (df["_date"] <= date_range[-1])
        & (~df[col_neigh].fillna("").str.lower().isin(["no neighborhood", "no_neighborhood", ""]))
    ].copy()

    # --------------------------
    # ORIGINAL DASHBOARD: Neighborhood Breakdown
    # --------------------------
    st.markdown(f"### 📍 Neighborhood Breakdown — {selected_area}")

    neighborhood_summary = []
    neigh_values = df_filtered[col_neigh].dropna().unique()

    for n in neigh_values:
        sub = df_filtered[df_filtered[col_neigh] == n]
        total_rides = sub[col_rides].sum()
        total_sessions = sub[col_sessions].sum()
        total_active = sub[col_active].sum()
        # snapshot count is the number of unique timestamps for that neighborhood (concurrent snapshots)
        snapshot_count = sub["_local_time"].nunique() if sub["_local_time"].nunique() > 0 else 1
        avg_active = total_active / snapshot_count
        ratio = total_rides / avg_active if avg_active != 0 else 0
        neighborhood_summary.append([n, total_rides, total_sessions, avg_active, ratio])

    agg = pd.DataFrame(
        neighborhood_summary, columns=["Neighborhood", "Rides", "Sessions", "Active (avg)", "Ratio"]
    )

    # format rounding
    agg["Active (avg)"] = agg["Active (avg)"].round(2)
    agg["Ratio"] = agg["Ratio"].round(2)

    # display table without showing the dataframe index
    st.markdown(agg.to_html(index=False), unsafe_allow_html=True)

    # --------------------------
    # ORIGINAL DASHBOARD: Hourly Heatmap (Sessions)
    # --------------------------
    st.markdown("### 🔥 Hourly Operations Heatmap")

    hourly = (
        df_filtered.groupby([col_neigh, "_hour"])
        .agg({col_rides: "sum", col_sessions: "sum", col_active: "sum", col_urgent: "sum"})
        .reset_index()
    )

    # snapshots per (neigh, hour)
    snapshots = (
        df_filtered.groupby([col_neigh, "_hour"])["_local_time"]
        .nunique()
        .reset_index()
        .rename(columns={"_local_time": "Snapshots"})
    )

    hourly = hourly.merge(snapshots, on=[col_neigh, "_hour"], how="left")

    # Compute averages per hour (active and urgent)
    hourly["Active (avg)"] = (hourly[col_active] / hourly["Snapshots"]).replace([np.inf, np.nan], 0).round(2)
    hourly["Urgent (avg)"] = (hourly[col_urgent] / hourly["Snapshots"]).replace([np.inf, np.nan], 0).round(2)

    heatmap = (
        alt.Chart(hourly)
        .mark_rect()
        .encode(
            x=alt.X("_hour:O", title="Hour of Day"),
            y=alt.Y(f"{col_neigh}:O", title="Neighborhood"),
            color=alt.Color(f"{col_sessions}:Q", title="Total Sessions", scale=alt.Scale(scheme="orangered")),
            tooltip=[col_neigh, "_hour", col_sessions, "Active (avg)", "Urgent (avg)"],
        )
        .properties(height=420)
    )
    st.altair_chart(heatmap, use_container_width=True)

    # --------------------------
    # ORIGINAL DASHBOARD: Hourly Active & Urgent Trend (add Rides + toggle)
    # --------------------------
    st.markdown("### 📈 Hourly Active, Urgent & Rides Trend")

    hourly_summary = (
        df_filtered.groupby("_hour")
        .agg({col_active: "sum", col_urgent: "sum", col_rides: "sum"})
        .reset_index()
    )

    # snapshots per hour (across all neighborhoods in selected area & date range)
    snapshots_hour = df_filtered.groupby("_hour")["_local_time"].nunique().reindex(range(24), fill_value=0)
    # ensure length matches hours present in hourly_summary; merge using _hour
    hourly_summary = hourly_summary.merge(
        snapshots_hour.reset_index().rename(columns={"_local_time": "Snapshots"}), on="_hour", how="left"
    )

    # compute averages
    hourly_summary["Active (avg)"] = (hourly_summary[col_active] / hourly_summary["Snapshots"]).replace(
        [np.inf, np.nan], 0
    ).round(2)
    hourly_summary["Urgent (avg)"] = (hourly_summary[col_urgent] / hourly_summary["Snapshots"]).replace(
        [np.inf, np.nan], 0
    ).round(2)
    hourly_summary["Rides (avg)"] = (hourly_summary[col_rides] / hourly_summary["Snapshots"]).replace(
        [np.inf, np.nan], 0
    ).round(2)

    # Toggle UI to show/hide lines
    metrics_available = ["Active (avg)", "Urgent (avg)", "Rides (avg)"]
    selected_metrics = st.multiselect("Show lines:", metrics_available, default=metrics_available)

    # melt only the selected metrics
    if len(selected_metrics) == 0:
        st.info("Select at least one metric to display on the trend chart.")
    else:
        melted = hourly_summary.melt(id_vars="_hour", value_vars=selected_metrics, var_name="Metric", value_name="Value")

        trend_chart = (
            alt.Chart(melted)
            .mark_line(point=True)
            .encode(
                x=alt.X("_hour:O", title="Hour of Day"),
                y=alt.Y("Value:Q", title="Average Count"),
                color=alt.Color("Metric:N", title="Metric", scale=alt.Scale(scheme="category10")),
                tooltip=["_hour", "Metric", "Value"],
            )
            .properties(height=420)
        )
        st.altair_chart(trend_chart, use_container_width=True)

    # --------------------------
    # ORIGINAL DASHBOARD: Export to Excel
    # --------------------------
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        agg.to_excel(writer, index=False, sheet_name="Neighborhood Summary")
        hourly.to_excel(writer, index=False, sheet_name="Hourly Data")
        hourly_summary.to_excel(writer, index=False, sheet_name="Hourly Summary")

    st.download_button(
        label="📥 Download Data (Excel)",
        data=output.getvalue(),
        file_name="neighbourhood_operations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # --------------------------
    # ADVANCED INSIGHTS SECTION (below original dashboard)
    # --------------------------
    st.markdown("---")
    st.markdown("## 🧠 Advanced Insights & Optimization Tools")

    # 1) Utilization heatmap (Rides per active scooter)
    st.markdown("### 🔥 Utilization Heatmap (Rides per Active Scooter)")
    hourly["Utilization"] = (hourly[col_rides] / hourly["Active (avg)"]).replace([np.inf, np.nan], 0).round(2)

    util_heatmap = (
        alt.Chart(hourly)
        .mark_rect()
        .encode(
            x=alt.X("_hour:O", title="Hour of Day"),
            y=alt.Y(f"{col_neigh}:O", title="Neighborhood"),
            color=alt.Color("Utilization:Q", title="Rides per Active Scooter", scale=alt.Scale(scheme="tealblues")),
            tooltip=[col_neigh, "_hour", "Utilization", "Active (avg)", col_rides],
        )
        .properties(height=420)
    )
    st.altair_chart(util_heatmap, use_container_width=True)

    # 3) Top / Bottom neighborhoods by Ratio
    st.markdown("### 🏆 Top & Bottom Performing Neighborhoods")
    top3 = agg.sort_values("Ratio", ascending=False).head(3)
    bottom3 = agg.sort_values("Ratio", ascending=True).head(3)
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top 3 (by Ratio)")
        st.markdown(top3.to_html(index=False), unsafe_allow_html=True)
    with c2:
        st.subheader("Bottom 3 (by Ratio)")
        st.markdown(bottom3.to_html(index=False), unsafe_allow_html=True)

    # 4) Hourly demand forecast (simple rolling mean)
    st.markdown("### 📈 Hourly Demand Forecast")
    hourly_demand = df_filtered.groupby("_hour")[col_rides].sum().reindex(range(24), fill_value=0).reset_index()
    hourly_demand.columns = ["_hour", "Total Rides"]
    hourly_demand["Forecast"] = hourly_demand["Total Rides"].rolling(window=3, min_periods=1).mean().round(2)

    base = (
        alt.Chart(hourly_demand)
        .mark_line(point=True, color="#00b4d8")
        .encode(x=alt.X("_hour:O", title="Hour of Day"), y=alt.Y("Total Rides:Q", title="Total Rides"), tooltip=["_hour", "Total Rides"])
    )
    forecast = (
        alt.Chart(hourly_demand)
        .mark_line(point=True, strokeDash=[5, 5], color="orange")
        .encode(x=alt.X("_hour:O"), y=alt.Y("Forecast:Q"), tooltip=["_hour", "Forecast"])
    )
    st.altair_chart(base + forecast, use_container_width=True)

    # 9) Fleet simulation (per neighborhood)
    st.markdown("### ⚙️ Fleet Optimization Simulation")
    st.write("Adjust fleet size (%) to simulate projected rides and ratios per neighborhood.")

    fleet_multiplier = st.slider("Adjust Fleet Size (%)", 50, 200, 100, 10)

    agg_sim = agg.copy()
    agg_sim["Adjusted Active (avg)"] = (agg_sim["Active (avg)"] * fleet_multiplier / 100).round(2)
    agg_sim["Projected Rides"] = (agg_sim["Ratio"] * agg_sim["Adjusted Active (avg)"]).round(2)
    agg_sim["Projected Ratio"] = (agg_sim["Projected Rides"] / agg_sim["Adjusted Active (avg)"]).replace([np.inf, np.nan], 0).round(2)

    st.markdown(agg_sim.to_html(index=False), unsafe_allow_html=True)
    st.success(f"Total projected rides (all neighborhoods): {int(agg_sim['Projected Rides'].sum()):,}")

else:
    st.info("👆 Upload a data file to begin.")


