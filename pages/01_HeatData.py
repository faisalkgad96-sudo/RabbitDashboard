import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import json
import requests
from io import BytesIO
import datetime

# ==============================
# CONSTANTS
# ==============================
MIN_CHART_HEIGHT = 400
PIXELS_PER_NEIGHBORHOOD = 30
MAX_DATE_RANGE_DAYS = 365

# Time interval definitions
TIME_INTERVALS = {
    "Morning Peak (6a-12p)": (6, 11),
    "Afternoon Peak (12p-6p)": (12, 17),
    "Evening/Night (6p-6a)": (18, 5)  # Wraps around midnight
}
INTERVAL_ORDER = ["Morning Peak (6a-12p)", "Afternoon Peak (12p-6p)", "Evening/Night (6p-6a)"]

GRANULARITY_OPTIONS = ["Hourly (0-23)", "3 Intervals"]

# ==============================
# PAGE CONFIG
# ==============================
st.set_page_config(
    page_title="Neighbourhood Fulfillment Dashboard", 
    layout="wide", 
    page_icon="📊"
)

# ==============================
# CUSTOM STYLING
# ==============================
st.markdown("""
<style>
    /* Use theme-aware styling instead of hardcoded colors */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
    }
    
    /* Reduce padding in columns for tighter layout */
    .stRadio > label {
        padding-right: 15px;
        margin-right: 0px; 
    }
    
    /* Ensure metrics inherit theme background */
    [data-testid="stMetric"] {
        background-color: transparent;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 Fulfillment Dashboard")

# ==============================
# HELPER FUNCTIONS
# ==============================

@st.cache_data(ttl=3600)
def fetch_heat_data(api_token, start_date_str, end_date_str, group_by="neighborhood"):
    """Fetches data from Rabbit API with error handling."""
    url = "https://dashboard.rabbit-api.app/export"
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    filters_payload = {
        "startDate": start_date_str,
        "endDate": end_date_str,
        "areas": [],
        "groupBy": group_by
    }

    payload = {
        "module": "HeatData",
        "filters": json.dumps(filters_payload)
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            st.error(f"❌ API Error {response.status_code}: {response.text}")
            return None

        content_type = response.headers.get("Content-Type", "")

        if "application/vnd.openxmlformats" in content_type:
            return pd.read_excel(BytesIO(response.content))
        elif "csv" in content_type:
            return pd.read_csv(BytesIO(response.content))
        else:
            return pd.DataFrame(response.json())
        
    except requests.exceptions.Timeout:
        st.error("❌ Request timed out. Please try again.")
        return None
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return None


def get_time_interval(hour):
    """Maps an hour (0-23) to a predefined time interval."""
    if 6 <= hour <= 11:
        return "Morning Peak (6a-12p)"
    elif 12 <= hour <= 17:
        return "Afternoon Peak (12p-6p)"
    else:
        return "Evening/Night (6p-6a)"


@st.cache_data(ttl=3600)
def process_data(df):
    """Standardizes column names and parses dates."""
    df_copy = df.copy()
    df_copy.columns = df_copy.columns.str.strip()
    
    # Required columns check
    required_cols = [
        "Area", "Neighborhood", "Start Date - Local",
        "Sessions", "Rides", "Active Vehicles", "Urgent Vehicles"
    ]
    
    missing_cols = [col for col in required_cols if col not in df_copy.columns]
    if missing_cols:
        st.error(f"❌ Missing columns: {missing_cols}")
        st.info(f"Available columns: {list(df_copy.columns)}")
        return None

    # Date processing
    df_copy["Start Date - Local"] = pd.to_datetime(
        df_copy["Start Date - Local"], 
        errors="coerce"
    )
    
    # Check for failed date parsing
    if df_copy["Start Date - Local"].isna().all():
        st.error("❌ Failed to parse dates. Please check date format.")
        return None
    
    df_copy["_hour"] = df_copy["Start Date - Local"].dt.hour
    df_copy["_date"] = df_copy["Start Date - Local"].dt.date.astype(str)
    df_copy["_time_interval"] = df_copy["_hour"].apply(get_time_interval)

    return df_copy


@st.cache_data(ttl=3600)
def calculate_metrics(df_grouped, time_column):
    """Calculates fulfillment, utilization, and average vehicle metrics."""
    agg_df = (
        df_grouped.groupby(["Neighborhood", time_column])
        .agg({
            "Sessions": "sum",
            "Active Vehicles": "sum",
            "Urgent Vehicles": "sum",
            "Rides": "sum",
            "Start Date - Local": "nunique" 
        })
        .rename(columns={"Start Date - Local": "Snapshots"})
        .reset_index()
    )

    # Calculate derived metrics
    agg_df["Neighborhood Fulfillment Rate"] = np.where(
        agg_df["Sessions"] > 0,
        agg_df["Rides"] / agg_df["Sessions"],
        0
    )
    agg_df["Missed Opportunity"] = agg_df["Sessions"] - agg_df["Rides"]
    agg_df["Active (Avg)"] = np.where(
        agg_df["Snapshots"] > 0, 
        agg_df["Active Vehicles"] / agg_df["Snapshots"], 
        0
    )
    agg_df["Urgent (Avg)"] = np.where(
        agg_df["Snapshots"] > 0, 
        agg_df["Urgent Vehicles"] / agg_df["Snapshots"], 
        0
    )
    agg_df["Utilization"] = np.where(
        agg_df["Active (Avg)"] > 0, 
        agg_df["Rides"] / agg_df["Active (Avg)"], 
        0
    )
    agg_df["Utilization"] = agg_df["Utilization"].replace([np.nan, np.inf], 0)
    
    return agg_df


def validate_date_range(start_date, end_date):
    """Validates that date range is sensible."""
    if start_date > end_date:
        return False, "Start date must be before end date."
    
    date_diff = (end_date - start_date).days
    if date_diff > MAX_DATE_RANGE_DAYS:
        return False, f"Date range too large. Maximum is {MAX_DATE_RANGE_DAYS} days."
    
    return True, ""


def add_granularity_control(chart_num, default_index=0):
    """Creates a consistent granularity radio button control."""
    return st.radio(
        f"Chart {chart_num} Granularity",
        GRANULARITY_OPTIONS,
        key=f"granularity_{chart_num}",
        index=default_index,
        horizontal=True
    )


def get_aggregation_for_granularity(granularity, df_hourly, df_interval):
    """Returns the appropriate aggregated dataframe and metadata based on granularity."""
    is_hourly = granularity == GRANULARITY_OPTIONS[0]
    return {
        "df": df_hourly if is_hourly else df_interval,
        "time_dim": "_hour" if is_hourly else "_time_interval",
        "time_title": "Hour of Day" if is_hourly else "Time Interval",
        "time_sort": None if is_hourly else INTERVAL_ORDER
    }


# ==============================
# SESSION STATE INITIALIZATION
# ==============================
if "data" not in st.session_state:
    st.session_state.data = None

# Default dates
today = datetime.date.today()
week_ago = today - datetime.timedelta(days=7)

# ==============================
# SIDEBAR: DATA SOURCE
# ==============================
with st.sidebar:
    st.header("Data Source")
    source_type = st.radio("Choose Source:", ["🔌 Live API", "📂 File Upload"])
    
    # Check for API token in secrets
    api_token = st.secrets.get("RABBIT_TOKEN") if hasattr(st, 'secrets') else None

    if source_type == "🔌 Live API":
        # Date inputs
        start_d = st.date_input("Start Date", value=week_ago, key="start_d")
        end_d = st.date_input("End Date", value=today, key="end_d")
        
        # Validate date range
        is_valid, error_msg = validate_date_range(start_d, end_d)
        if not is_valid:
            st.error(error_msg)
        
        if api_token is None:
            st.caption("Token not found in `secrets.toml`. Please enter manually.")
            st.warning("⚠️ Never share screenshots containing your API token!")
            api_token = st.text_input(
                "API Token", 
                value="", 
                type="password", 
                key="manual_token_input"
            )
            button_disabled = not api_token or not is_valid
        else:
            st.caption("✅ Using token from `secrets.toml`")
            button_disabled = not is_valid
        
        if st.button("Fetch Live Data", type="primary", disabled=button_disabled):
            with st.spinner("Fetching and processing data..."):
                raw_df = fetch_heat_data(
                    api_token, 
                    f"{start_d}T00:00:00.000Z", 
                    f"{end_d}T23:59:00.000Z"
                )
                if raw_df is not None:
                    if not raw_df.empty:
                        processed = process_data(raw_df)
                        if processed is not None:
                            st.session_state.data = processed
                            st.success(f"✅ Loaded {len(raw_df):,} rows!")
                            st.rerun()
                    else:
                        st.warning("Data fetched but is empty.")

    else:  # File Upload
        uploaded_file = st.file_uploader(
            "Upload Excel/CSV", 
            type=["xlsx", "xls", "csv"]
        )
        if uploaded_file:
            try:
                if uploaded_file.name.endswith(".csv"):
                    raw_df = pd.read_csv(uploaded_file)
                else:
                    raw_df = pd.read_excel(uploaded_file)
                
                processed = process_data(raw_df)
                if processed is not None:
                    st.session_state.data = processed
                    st.success(f"✅ Loaded {len(raw_df):,} rows from file!")
                    st.rerun()
                
            except Exception as e:
                st.error(f"❌ Error reading file: {e}")
    
    # Clear data button
    st.divider()
    if st.session_state.data is not None:
        if st.button("🗑️ Clear Data", type="secondary"):
            st.session_state.data = None
            st.rerun()

# ==============================
# MAIN DASHBOARD
# ==============================

if st.session_state.data is None:
    st.info("👈 Please fetch data via API or upload a file from the sidebar.")
    st.stop()

df = st.session_state.data

# ==============================
# FILTERS
# ==============================
st.divider()
c1, c2, c3 = st.columns([1, 2, 1])

areas = sorted(df["Area"].dropna().unique().tolist())
dates = sorted(df["_date"].dropna().unique().tolist())

with c1:
    selected_area = st.selectbox(
        "📍 Select Area", 
        areas, 
        index=0 if areas else 0
    )

with c2:
    selected_dates = st.multiselect(
        "📅 Select Dates", 
        dates, 
        default=dates[:1]  # Simplified default selection
    )

# Apply Filters
df_filtered = df[
    (df["Area"] == selected_area) & 
    (df["_date"].isin(selected_dates)) &
    (df["Neighborhood"].str.lower() != "no neighborhood")
]

if df_filtered.empty:
    st.warning("⚠️ No data available for the selected filters.")
    st.stop()

# ==============================
# DATA PREPARATION (GLOBAL)
# ==============================
df_hourly_agg = calculate_metrics(df_filtered, "_hour")
df_interval_agg = calculate_metrics(df_filtered, "_time_interval")

# Apply categorical ordering to intervals
df_interval_agg["_time_interval"] = pd.Categorical(
    df_interval_agg["_time_interval"], 
    categories=INTERVAL_ORDER, 
    ordered=True
)

# Scorecard metrics (period-level)
daily_active_avg = (
    df_filtered.groupby(["Neighborhood", "_date"])["Active Vehicles"]
    .mean()
    .reset_index()
    .rename(columns={"Active Vehicles": "Daily Active Avg"})
)
period_active_avg = (
    daily_active_avg.groupby("Neighborhood")["Daily Active Avg"]
    .mean()
    .reset_index()
    .rename(columns={"Daily Active Avg": "Active (Avg)"})
)
total_avg_active_scooters = period_active_avg["Active (Avg)"].sum()

# ==============================
# DOWNLOAD SECTION
# ==============================
with st.expander("📥 Download Data"):
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="Download Hourly Data (CSV)",
            data=df_hourly_agg.to_csv(index=False).encode('utf-8'),
            file_name=f'hourly_data_{selected_area}_{len(selected_dates)}days.csv',
            mime='text/csv',
        )
    with col2:
        st.download_button(
            label="Download Interval Data (CSV)",
            data=df_interval_agg.to_csv(index=False).encode('utf-8'),
            file_name=f'interval_data_{selected_area}_{len(selected_dates)}days.csv',
            mime='text/csv',
        )

st.markdown("---")

# ==============================
# TOP LEVEL METRICS
# ==============================
total_rides = df_filtered["Rides"].sum()
total_sessions = df_filtered["Sessions"].sum()
unique_neighborhoods = df_filtered["Neighborhood"].nunique()
total_missed_opportunity = total_sessions - total_rides

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric("Total Rides", f"{total_rides:,}")
m2.metric("Total Sessions", f"{total_sessions:,}")
m3.metric("Avg Active Scooters", f"{total_avg_active_scooters:,.1f}")
m4.metric("Total Missed Opp.", f"{total_missed_opportunity:,}")
m5.metric("Active Neighborhoods", unique_neighborhoods)

st.markdown("---")

# ==============================
# 1. NEIGHBORHOOD LEADERBOARD
# ==============================
st.subheader("📊 Neighborhood Leaderboard")

period_summary = df_filtered.groupby("Neighborhood").agg(
    Rides=("Rides", "sum"),
    Sessions=("Sessions", "sum"),
).reset_index()

agg = pd.merge(period_summary, period_active_avg, on="Neighborhood")
num_selected_days = len(df_filtered["_date"].unique())
agg["Rides per Day"] = agg["Rides"] / num_selected_days
agg["RPDPV"] = np.where(
    agg["Active (Avg)"] > 0, 
    agg["Rides per Day"] / agg["Active (Avg)"], 
    0
)
agg["Missed Opportunity"] = agg["Sessions"] - agg["Rides"]

st.dataframe(
    agg.sort_values("RPDPV", ascending=False),
    use_container_width=True,
    column_config={
        "RPDPV": st.column_config.ProgressColumn(
            "Rides/Day/Vehicle",
            help="Rides per Day per Average Active Vehicle",
            format="%.2f",
            min_value=0,
            max_value=agg["RPDPV"].max(),
        ),
        "Active (Avg)": st.column_config.NumberColumn(format="%.1f"),
        "Missed Opportunity": st.column_config.NumberColumn(format="%d")
    },
    hide_index=True,
    column_order=[
        "Neighborhood", "Rides", "Sessions", "Missed Opportunity", 
        "Rides per Day", "Active (Avg)", "RPDPV"
    ]
)

st.markdown("---")

# ==============================
# 2. FULFILLMENT RATE HEATMAP
# ==============================
c_gran_2, _ = st.columns([1, 3])
with c_gran_2:
    chart_granularity_2 = add_granularity_control(2)

agg_config_2 = get_aggregation_for_granularity(
    chart_granularity_2, 
    df_hourly_agg, 
    df_interval_agg
)

st.subheader("🔥 Fulfillment Heat Map")
st.caption(
    f"Color based on **Fulfillment Rate** across {agg_config_2['time_title']}. "
    "Higher rates (better performance) are lighter."
)

fulfillment_chart = alt.Chart(agg_config_2["df"]).mark_rect().encode(
    x=alt.X(
        f"{agg_config_2['time_dim']}:O", 
        title=agg_config_2['time_title'], 
        sort=agg_config_2['time_sort']
    ),
    y=alt.Y("Neighborhood:O", title=""),
    color=alt.Color(
        "Neighborhood Fulfillment Rate:Q",
        scale=alt.Scale(range=['red', 'white'], reverse=True),
        title="Fulfillment Rate (%)"
    ),
    tooltip=[
        "Neighborhood",
        alt.Tooltip(f"{agg_config_2['time_dim']}:O", title=agg_config_2['time_title']),
        alt.Tooltip("Neighborhood Fulfillment Rate:Q", format=".1%", title="Fulfillment Rate"),
        alt.Tooltip("Missed Opportunity:Q", title="Missed Opportunity"),
        alt.Tooltip("Rides:Q", title="Rides"),
        alt.Tooltip("Sessions:Q", title="Sessions"),
        alt.Tooltip("Urgent (Avg):Q", format=".1f", title="Urgent Vehicles (Avg)"),
        alt.Tooltip("Utilization:Q", format=".2f", title="Rides/Active Vehicle"),
        alt.Tooltip("Active (Avg):Q", format=".1f")
    ]
).properties(
    height=max(
        MIN_CHART_HEIGHT, 
        len(agg_config_2["df"]["Neighborhood"].unique()) * PIXELS_PER_NEIGHBORHOOD
    )
)

st.altair_chart(fulfillment_chart, use_container_width=True)
st.markdown("---")

# ==============================
# 3. MISSED OPPORTUNITY HEATMAP
# ==============================
c_gran_3, _ = st.columns([1, 3])
with c_gran_3:
    chart_granularity_3 = add_granularity_control(3)

agg_config_3 = get_aggregation_for_granularity(
    chart_granularity_3,
    df_hourly_agg,
    df_interval_agg
)

st.subheader("💔 Missed Opportunity (Sessions - Rides)")
st.caption(
    f"Color based on **absolute count** of unfulfilled sessions per {agg_config_3['time_title']}. "
    "Darker red = highest missed opportunities."
)

missed_opp_chart = alt.Chart(agg_config_3["df"]).mark_rect().encode(
    x=alt.X(
        f"{agg_config_3['time_dim']}:O",
        title=agg_config_3['time_title'],
        sort=agg_config_3['time_sort']
    ),
    y=alt.Y("Neighborhood:O", title=""),
    color=alt.Color(
        "Missed Opportunity:Q",
        scale=alt.Scale(scheme="reds", domainMin=0),
        title="Absolute Count"
    ),
    tooltip=[
        "Neighborhood",
        alt.Tooltip(f"{agg_config_3['time_dim']}:O", title=agg_config_3['time_title']),
        alt.Tooltip("Missed Opportunity:Q", title="Missed Opportunity"),
        alt.Tooltip("Neighborhood Fulfillment Rate:Q", format=".1%", title="Fulfillment Rate"),
        alt.Tooltip("Rides:Q", title="Rides"),
        alt.Tooltip("Sessions:Q", title="Sessions"),
        alt.Tooltip("Urgent (Avg):Q", format=".1f", title="Urgent Vehicles (Avg)"),
        alt.Tooltip("Active (Avg):Q", format=".1f")
    ]
).properties(
    height=max(
        MIN_CHART_HEIGHT,
        len(agg_config_3["df"]["Neighborhood"].unique()) * PIXELS_PER_NEIGHBORHOOD
    )
)

st.altair_chart(missed_opp_chart, use_container_width=True)
st.markdown("---")

# ==============================
# 4. FULFILLMENT TRENDLINES
# ==============================
c_gran_4, _ = st.columns([1, 3])
with c_gran_4:
    chart_granularity_4 = add_granularity_control(4)

agg_config_4 = get_aggregation_for_granularity(
    chart_granularity_4,
    df_hourly_agg,
    df_interval_agg
)

st.subheader("📈 Fulfillment Trendlines")
st.caption(
    f"Tracks Fulfillment Rate (%) for **each neighborhood** across {agg_config_4['time_title']}."
)

fulfillment_trend_chart = alt.Chart(agg_config_4["df"]).mark_line(point=True).encode(
    x=alt.X(
        f"{agg_config_4['time_dim']}:O",
        title=agg_config_4['time_title'],
        sort=agg_config_4['time_sort']
    ),
    y=alt.Y(
        "Neighborhood Fulfillment Rate:Q",
        title="Fulfillment Rate (%)",
        axis=alt.Axis(format=".1%")
    ),
    color=alt.Color("Neighborhood:N", title="Neighborhood"),
    tooltip=[
        "Neighborhood",
        alt.Tooltip(f"{agg_config_4['time_dim']}:O", title=agg_config_4['time_title']),
        alt.Tooltip("Neighborhood Fulfillment Rate:Q", format=".1%", title="Fulfillment Rate"),
        alt.Tooltip("Rides:Q", title="Rides"),
        alt.Tooltip("Sessions:Q", title="Sessions"),
    ]
).properties(height=450)

st.altair_chart(fulfillment_trend_chart, use_container_width=True)
st.markdown("---")

# ==============================
# 5. ACCUMULATIVE TREND
# ==============================
c_gran_5, _ = st.columns([1, 3])
with c_gran_5:
    chart_granularity_5 = add_granularity_control(5)

agg_config_5 = get_aggregation_for_granularity(
    chart_granularity_5,
    df_hourly_agg,
    df_interval_agg
)

st.subheader("📈 Accumulative Trend")
st.caption(
    f"Total Rides, Sessions, and **Avg Urgent Vehicles** across all neighborhoods by {agg_config_5['time_title']}."
)

dynamic_total = agg_config_5["df"].groupby(agg_config_5["time_dim"]).agg(
    Rides=("Rides", "sum"),
    Sessions=("Sessions", "sum"),
    Urgent_Vehicles=("Urgent (Avg)", "sum")
).reset_index()

dynamic_long = dynamic_total.melt(
    id_vars=[agg_config_5["time_dim"]],
    value_vars=["Rides", "Sessions", "Urgent_Vehicles"],
    var_name="Metric",
    value_name="Count"
)

line = alt.Chart(dynamic_long).mark_line(point=True, interpolate='monotone').encode(
    x=alt.X(
        f"{agg_config_5['time_dim']}:O",
        title=agg_config_5['time_title'],
        sort=agg_config_5['time_sort']
    ),
    y=alt.Y("Count:Q", title="Total Count"),
    color=alt.Color("Metric:N", title="Metric"),
    tooltip=[
        agg_config_5["time_dim"],
        "Metric",
        alt.Tooltip("Count", format=".1f")
    ]
).properties(height=350)

st.altair_chart(line, use_container_width=True)
