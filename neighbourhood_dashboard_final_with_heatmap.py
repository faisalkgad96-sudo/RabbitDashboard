import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from io import BytesIO

# ==========================
# PAGE SETUP
# ==========================
st.set_page_config(page_title="Neighbourhood Operations Dashboard", layout="wide")
st.title("📊 Neighbourhood HeatData Dashboard")
st.markdown("""
Upload the heatdata file as it is """)


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
    col_area   = "Area"
    col_neigh  = "Neighborhood"
    col_start  = "Start Date - Local"
    col_rides  = "Rides"
    col_sessions = "Sessions"
    col_active = "Active Vehicles"
    col_urgent = "Urgent Vehicles"

    # Time processing
    df[col_start] = pd.to_datetime(df[col_start], errors="coerce")
    df["_local_time"] = df[col_start]
    df["_hour"] = df["_local_time"].dt.hour
    df["_date"] = df["_local_time"].dt.date

    # ==========================
    # FILTERS
    # ==========================
    area_list = sorted(df[col_area].dropna().unique())
    selected_area = st.sidebar.selectbox("🏙️ Choose Area", area_list)
    date_range = st.sidebar.date_input("📅 Select Date Range", [df["_date"].min(), df["_date"].max()])

    df_filtered = df[
        (df[col_area] == selected_area)
        & (df["_date"] >= date_range[0])
        & (df["_date"] <= date_range[-1])
        & (df[col_neigh].str.lower() != "no neighborhood")
    ].copy()

    # ==========================
    # NEIGHBORHOOD SUMMARY
    # ==========================
    st.markdown(f"### 📍 Neighborhood Breakdown — {selected_area}")

    neighborhood_summary = []
    for n in df_filtered[col_neigh].dropna().unique():
        sub = df_filtered[df_filtered[col_neigh] == n]

        total_rides = sub[col_rides].sum()
        total_sessions = sub[col_sessions].sum()
        total_active = sub[col_active].sum()
        snapshots = sub["_local_time"].nunique()
        snapshots = snapshots if snapshots > 0 else 1

        avg_active = total_active / snapshots
        ratio = total_rides / avg_active if avg_active != 0 else 0

        neighborhood_summary.append([
            n,
            total_rides,
            total_sessions,
            round(avg_active, 2),
            round(ratio, 2)
        ])

    agg = pd.DataFrame(neighborhood_summary, columns=[
        "Neighborhood", "Rides", "Sessions", "Active (avg)", "Ratio"
    ])

    st.dataframe(agg, use_container_width=True)


    # ==========================
    # HOURLY HEATMAP (SESSIONS)
    # ==========================
    st.markdown("### 🔥 Hourly Operations Heatmap")

    # IMPORTANT: include rides in hourly groupby
    hourly = (
        df_filtered.groupby([col_neigh, "_hour"])
        .agg({
            col_sessions: "sum",
            col_rides: "sum",
            col_active: "sum",
            col_urgent: "sum"
        })
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
        x=alt.X("_hour:O", title="Hour"),
        y=alt.Y(f"{col_neigh}:O", title="Neighborhood"),
        color=alt.Color(col_sessions + ":Q", title="Sessions", scale=alt.Scale(scheme="orangered")),
        tooltip=[col_neigh, "_hour", col_sessions, "Active (avg)", "Urgent (avg)"]
    ).properties(width="container", height=400)

    st.altair_chart(heatmap, use_container_width=True)

    
    # ==========================
    # TREND CHART — ACTIVE + URGENT + RIDES (SUM)
    # ==========================
    st.markdown("### 📈 Hourly Active, Urgent & Rides Trend")

    hourly_summary = (
        df_filtered.groupby("_hour")
        .agg({
            col_active: "sum",
            col_urgent: "sum",
            col_rides: "sum"   # ← rides sum added
        })
        .reset_index()
    )

    hourly_summary["Snapshots"] = df_filtered.groupby("_hour")["_local_time"].nunique().values
    hourly_summary["Active (avg)"] = (hourly_summary[col_active] / hourly_summary["Snapshots"]).round(2)
    hourly_summary["Urgent (avg)"] = (hourly_summary[col_urgent] / hourly_summary["Snapshots"]).round(2)
    hourly_summary["Rides (sum)"]  = hourly_summary[col_rides]

    melted = hourly_summary.melt(
        id_vars="_hour",
        value_vars=["Active (avg)", "Urgent (avg)", "Rides (sum)"],
        var_name="Metric",
        value_name="Value"
    )

    trend_chart = alt.Chart(melted).mark_line(point=True).encode(
        x=alt.X("_hour:O", title="Hour"),
        y="Value:Q",
        color="Metric:N",
        tooltip=["_hour", "Metric", "Value"]
    ).properties(width="container", height=400)

    st.altair_chart(trend_chart, use_container_width=True)


    # ==========================
    # EXPORT SECTION
    # ==========================
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        agg.to_excel(writer, index=False, sheet_name="Neighborhood Summary")
        hourly.to_excel(writer, index=False, sheet_name="Hourly Data")
        hourly_summary.to_excel(writer, index=False, sheet_name="Hourly Summary")

    st.download_button(
        label="📥 Download Data (Excel)",
        data=output.getvalue(),
        file_name="neighborhood_operations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


    # ==========================
    # 🚀 ADVANCED INSIGHTS
    # ==========================
    st.markdown("---")
    st.markdown("## 🧠 Advanced Insights & Optimization Tools")

    # 1️⃣ UTILIZATION HEATMAP
    st.markdown("### 🔥 Hourly Utilization Heatmap")

    hourly["Utilization"] = (
        hourly[col_rides] / hourly["Active (avg)"]
    ).replace([np.nan, np.inf], 0)

    util_heatmap = alt.Chart(hourly).mark_rect().encode(
        x=alt.X("_hour:O", title="Hour"),
        y=alt.Y(f"{col_neigh}:O", title="Neighborhood"),
        color=alt.Color("Utilization:Q", title="Rides per Active Scooter",
                        scale=alt.Scale(scheme="tealblues")),
        tooltip=[col_neigh, "_hour", "Utilization", "Active (avg)", col_rides]
    ).properties(width="container", height=400)

    st.altair_chart(util_heatmap, use_container_width=True)

    # 3️⃣ TOP / BOTTOM NEIGHBORHOODS
    st.markdown("### 🏆 Top & Bottom Performing Neighborhoods")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔥 Top 3 (Ratio)")
        st.table(agg.sort_values("Ratio", ascending=False).head(3))

    with col2:
        st.subheader("❄️ Bottom 3 (Ratio)")
        st.table(agg.sort_values("Ratio", ascending=True).head(3))

    # 4️⃣ HOURLY DEMAND FORECAST
    st.markdown("### 📈 Hourly Ride Demand Forecast")

    hourly_demand = (
        df_filtered.groupby("_hour")[col_rides]
        .sum()
        .reset_index()
        .sort_values("_hour")
    )
    hourly_demand["Forecast"] = hourly_demand[col_rides].rolling(3, min_periods=1).mean()

    base = alt.Chart(hourly_demand).mark_line(point=True, color="#0077b6").encode(
        x=alt.X("_hour:O", title="Hour"),
        y=alt.Y(col_rides + ":Q", title="Rides"),
        tooltip=["_hour", col_rides]
    )
    forecast = alt.Chart(hourly_demand).mark_line(
        point=True, strokeDash=[5,5], color="orange"
    ).encode(
        x="_hour:O",
        y="Forecast:Q",
        tooltip=["_hour", "Forecast"]
    )

    st.altair_chart(base + forecast, use_container_width=True)

    # 9️⃣ FLEET SIMULATION
    st.markdown("### ⚙️ Fleet Optimization Simulator")

    fleet_multiplier = st.slider("Adjust Fleet Size (%)", 50, 200, 100, step=10)

    agg["Adjusted Active (avg)"] = agg["Active (avg)"] * (fleet_multiplier / 100)
    agg["Projected Rides"] = agg["Ratio"] * agg["Adjusted Active (avg)"]
    agg["Projected Ratio"] = (
        agg["Projected Rides"] / agg["Adjusted Active (avg)"]
    ).replace([np.nan, np.inf], 0)

    st.dataframe(
        agg[[
            "Neighborhood",
            "Active (avg)",
            "Adjusted Active (avg)",
            "Rides",
            "Projected Rides",
            "Projected Ratio"
        ]],
        use_container_width=True
    )

    st.success(
        f"🚀 Total projected rides with fleet = {fleet_multiplier}%: "
        f"**{int(agg['Projected Rides'].sum()):,} rides**"
    )

else:
    st.info("👆 Upload a data file to begin.")
