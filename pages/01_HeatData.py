import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import json
import requests
from io import BytesIO

st.set_page_config(page_title="Neighbourhood HeatData Dashboard", layout="wide")
st.title("📊 Neighbourhood HeatData Dashboard")

st.markdown("""
Upload a CSV/Excel file **OR** fetch live data directly from the Rabbit backend API.
""")


def fetch_heat_data(start_date, end_date, group_by="neighborhood"):
    url = "https://dashboard.rabbit-api.app/export"

    token_value = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiI2NzM5MzI0OTg5MzA5MmRmYTMwZjhhYTgiLCJpYXQiOjE3NjMyNzk3NjksImV4cCI6MTc2NTg3MTc2OX0.Kh3RxvQmV5eQJmUsVluS04FFc1sUjfA7Fq3yGnVlfbk"

    headers = {
        "Authorization": f"Bearer {token_value}",
        "Content-Type": "application/json"
    }

    filters_payload = {
        "startDate": start_date,
        "endDate": end_date,
        "areas": [],
        "groupBy": group_by
    }

    payload = {
        "module": "HeatData",
        "filters": json.dumps(filters_payload)
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        st.error(f"❌ API Error {response.status_code}")
        st.code(response.text)
        return None

    content_type = response.headers.get("Content-Type", "")

    if "application/vnd.openxmlformats" in content_type:
        return pd.read_excel(BytesIO(response.content))

    if "csv" in content_type:
        return pd.read_csv(BytesIO(response.content))

    try:
        return pd.DataFrame(response.json())
    except:
        st.error("❌ Unknown API response format.")
        return None


st.subheader("🔌 Fetch Live HeatData from Rabbit API")

with st.expander("Fetch from API"):
    colA, colB = st.columns(2)
    api_start = colA.date_input("Start Date")
    api_end = colB.date_input("End Date")

    fetch_btn = st.button("⚡ Fetch Live Data")

df = None

if fetch_btn:
    with st.spinner("Fetching from Rabbit API..."):
        start_str = f"{api_start}T00:00:00.000Z"
        end_str = f"{api_end}T23:59:00.000Z"
        df = fetch_heat_data(start_str, end_str)


# ------------------------------
# FILE UPLOAD SECTION
# ------------------------------
if df is None:
    uploaded = st.file_uploader("📂 Upload Excel/CSV file", type=["xlsx", "xls", "csv"])
    if uploaded:
        if uploaded.name.endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            df = pd.read_excel(uploaded)

if df is None:
    st.info("Upload a file or fetch remote CSV to proceed.")
    st.stop()

df.columns = df.columns.str.strip()

required_cols = [
    "Area", "Neighborhood", "Start Date - Local",
    "Sessions", "Rides", "Active Vehicles", "Urgent Vehicles"
]

if not all(col in df.columns for col in required_cols):
    st.error("❌ Missing required columns in dataset.")
    st.write("Found columns:", list(df.columns))
    st.stop()


# ------------------------------
# DATA PREP
# ------------------------------
df["Start Date - Local"] = pd.to_datetime(df["Start Date - Local"], errors="coerce")
df["_local_time"] = df["Start Date - Local"]
df["_hour"] = df["_local_time"].dt.hour
df["_date"] = df["_local_time"].dt.date.astype(str)


# ------------------------------
# AREA + DATE FILTERS (Scorecard Style)
# ------------------------------
areas = sorted(df["Area"].dropna().unique().tolist())
dates = sorted(df["_date"].dropna().unique().tolist())

c1, c2 = st.columns([1, 1])

with c1:
    selected_area = st.selectbox(
        "Area (single select)",
        options=areas,
        index=0
    )

with c2:
    selected_dates = st.multiselect(
        "Day (multi-select)",
        options=dates,
        default=[dates[-1]] if dates else []
    )


# ------------------------------
# FILTER DATA
# ------------------------------
df_filtered = df[
    (df["Area"] == selected_area)
    & (df["_date"].isin(selected_dates))
    & (df["Neighborhood"].str.lower() != "no neighborhood")
]

st.subheader(f"📍 Neighborhood Breakdown — {selected_area}")


summary = []
for n in df_filtered["Neighborhood"].unique():
    sub = df_filtered[df_filtered["Neighborhood"] == n]

    rides = sub["Rides"].sum()
    sessions = sub["Sessions"].sum()
    active_total = sub["Active Vehicles"].sum()
    snapshots = sub["_local_time"].nunique() or 1

    avg_active = active_total / snapshots
    ratio = rides / avg_active if avg_active else 0

    summary.append([n, rides, sessions, round(avg_active, 2), round(ratio, 2)])

agg = pd.DataFrame(summary, columns=["Neighborhood", "Rides", "Sessions", "Active (avg)", "Ratio"])
st.dataframe(agg, use_container_width=True)


# ------------------------------
# HEATMAP
# ------------------------------
st.subheader("🔥 Hourly Operations Heatmap")

hourly = (
    df_filtered.groupby(["Neighborhood", "_hour"])
    .agg({
        "Sessions": "sum",
        "Active Vehicles": "sum",
        "Urgent Vehicles": "sum",
        "Rides": "sum"
    })
    .reset_index()
)

snapshots = (
    df_filtered.groupby(["Neighborhood", "_hour"])["_local_time"]
    .nunique().reset_index().rename(columns={"_local_time": "Snapshots"})
)

hourly = hourly.merge(snapshots, on=["Neighborhood", "_hour"], how="left")
hourly["Active (avg)"] = hourly["Active Vehicles"] / hourly["Snapshots"]

heatmap = alt.Chart(hourly).mark_rect().encode(
    x="_hour:O",
    y="Neighborhood:O",
    color=alt.Color("Sessions:Q", scale=alt.Scale(scheme="orangered")),
    tooltip=["Neighborhood", "_hour", "Sessions", "Active (avg)"]
).properties(width=900, height=400)

st.altair_chart(heatmap, use_container_width=True)


# ------------------------------
# UTILIZATION HEATMAP
# ------------------------------
st.subheader("🧠 Advanced Insights")

hourly["Utilization"] = (hourly["Rides"] / hourly["Active (avg)"]).replace([np.nan, np.inf], 0)

util = alt.Chart(hourly).mark_rect().encode(
    x="_hour:O",
    y="Neighborhood:O",
    color=alt.Color("Utilization:Q", scale=alt.Scale(scheme="tealblues")),
    tooltip=["Neighborhood", "_hour", "Utilization"]
).properties(width=900, height=400)

st.altair_chart(util, use_container_width=True)


# ------------------------------
# TOP / BOTTOM NEIGHBORHOODS
# ------------------------------
col1, col2 = st.columns(2)
with col1:
    st.subheader("🏆 Top 3 Neighborhoods")
    st.table(agg.sort_values("Ratio", ascending=False).head(3))

with col2:
    st.subheader("🐢 Bottom 3 Neighborhoods")
    st.table(agg.sort_values("Ratio").head(3))


# ------------------------------
# HOURLY DEMAND FORECAST
# ------------------------------
st.subheader("📈 Hourly Demand Forecast")

hourly_demand = df_filtered.groupby("_hour")["Rides"].sum().reset_index()
hourly_demand["Forecast"] = hourly_demand["Rides"].rolling(3, min_periods=1).mean()

base = alt.Chart(hourly_demand).mark_line(point=True).encode(
    x="_hour:O",
    y="Rides:Q"
)

forecast = alt.Chart(hourly_demand).mark_line(point=True, strokeDash=[5, 5], color="orange").encode(
    x="_hour:O",
    y="Forecast:Q"
)

st.altair_chart(base + forecast, use_container_width=True)
