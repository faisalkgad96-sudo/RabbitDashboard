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
MIN_CHART_HEIGHT = 500
PIXELS_PER_NEIGHBORHOOD = 40
MAX_DATE_RANGE_DAYS = 365

TIME_INTERVALS = {
    "Morning Peak (6a-12p)": (6, 11),
    "Afternoon Peak (12p-6p)": (12, 17),
    "Evening/Night (6p-6a)": (18, 5)
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
    [data-testid="stMetricValue"] {
        font-size: 2.2rem;
        font-weight: 600;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 1rem;
        font-weight: 500;
    }
    
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    h2 {
        margin-top: 2rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid rgba(128, 128, 128, 0.2);
    }
    
    h3 {
        margin-top: 1.5rem;
        margin-bottom: 0.8rem;
    }
    
    hr {
        margin-top: 2rem;
        margin-bottom: 2rem;
        border: none;
        height: 2px;
        background: linear-gradient(to right, transparent, rgba(128, 128, 128, 0.3), transparent);
    }
    
    .stRadio > label {
        padding-right: 15px;
        margin-right: 0px; 
    }
    
    [data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.05);
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid rgba(128, 128, 128, 0.1);
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 Neighborhood Fulfillment Dashboard")
st.markdown("### Real-time insights into fulfillment performance and vehicle utilization")

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
    
    required_cols = [
        "Area", "Neighborhood", "Start Date - Local",
        "Sessions", "Rides", "Active Vehicles", "Urgent Vehicles"
    ]
    
    missing_cols = [col for col in required_cols if col not in df_copy.columns]
    if missing_cols:
        st.error(f"❌ Missing columns: {missing_cols}")
        st.info(f"Available columns: {list(df_copy.columns)}")
        return None

    df_copy["Start Date - Local"] = pd.to_datetime(
        df_copy["Start Date - Local"], 
        errors="coerce"
    )
    
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
        "View by:",
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
# SESSION STATE
# ==============================
if "data" not in st.session_state:
    st.session_state.data = None

today = datetime.date.today()
week_ago = today - datetime.timedelta(days=7)

# ==============================
# SIDEBAR
# ==============================
with st.sidebar:
    st.header("⚙️ Data Configuration")
    
    source_type = st.radio(
        "Data Source:", 
        ["🔌 Live API", "📂 File Upload"],
        label_visibility="visible"
    )
    
    api_token = st.secrets.get("RABBIT_TOKEN") if hasattr(st, 'secrets') else None

    if source_type == "🔌 Live API":
        st.subheader("Date Range")
        start_d = st.date_input("Start Date", value=week_ago, key="start_d")
        end_d = st.date_input("End Date", value=today, key="end_d")
        
        is_valid, error_msg = validate_date_range(start_d, end_d)
        if not is_valid:
            st.error(error_msg)
        
        st.divider()
        
        if api_token is None:
            st.warning("⚠️ API Token Required")
            st.caption("Token not found in secrets. Enter manually below:")
            st.info("💡 Never share screenshots with your API token visible!")
            api_token = st.text_input(
                "API Token", 
                value="", 
                type="password", 
                key="manual_token_input"
            )
            button_disabled = not api_token or not is_valid
        else:
            st.success("✅ Using secured token")
            button_disabled = not is_valid
        
        if st.button("🚀 Fetch Data", type="primary", disabled=button_disabled, use_container_width=True):
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

    else:
        st.subheader("File Upload")
        uploaded_file = st.file_uploader(
            "Choose Excel or CSV file:", 
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
                    st.success(f"✅ Loaded {len(raw_df):,} rows!")
                    st.rerun()
                
            except Exception as e:
                st.error(f"❌ Error reading file: {e}")
    
    if st.session_state.data is not None:
        st.divider()
        st.subheader("Data Info")
        st.metric("Total Records", f"{len(st.session_state.data):,}")
        
        if st.button("🗑️ Clear Data", type="secondary", use_container_width=True):
            st.session_state.data = None
            st.rerun()

# ==============================
# MAIN DASHBOARD
# ==============================

if st.session_state.data is None:
    st.info("👈 **Get Started:** Configure your data source in the sidebar")
    st.markdown("""
    ### Welcome to the Fulfillment Dashboard
    
    This dashboard provides comprehensive insights into:
    - 🎯 Neighborhood performance metrics
    - 📊 Fulfillment rates and trends
    - 🚲 Vehicle utilization patterns
    - 💔 Missed opportunity analysis
    
    **To begin:** Select a data source from the sidebar (API or file upload)
    """)
    st.stop()

df = st.session_state.data

# ==============================
# FILTERS
# ==============================
st.markdown("---")
st.markdown("## 🔍 Filters")

col1, col2, col3 = st.columns([2, 3, 2])

areas = sorted(df["Area"].dropna().unique().tolist())
dates = sorted(df["_date"].dropna().unique().tolist())

with col1:
    selected_area = st.selectbox(
        "📍 Area", 
        areas, 
        index=0 if areas else 0
    )

with col2:
    selected_dates = st.multiselect(
        "📅 Date(s)", 
        dates, 
        default=dates[:1]
    )

with col3:
    st.markdown("##### Quick Actions")

df_filtered = df[
    (df["Area"] == selected_area) & 
    (df["_date"].isin(selected_dates)) &
    (df["Neighborhood"].str.lower() != "no neighborhood")
]

if df_filtered.empty:
    st.warning("⚠️ No data available for selected filters. Try different criteria.")
    st.stop()

# ==============================
# DATA PREPARATION
# ==============================
df_hourly_agg = calculate_metrics(df_filtered, "_hour")
df_interval_agg = calculate_metrics(df_filtered, "_time_interval")

df_interval_agg["_time_interval"] = pd.Categorical(
    df_interval_agg["_time_interval"], 
    categories=INTERVAL_ORDER, 
    ordered=True
)

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

# Download buttons
if selected_dates:
    with col3:
        with st.expander("📥 Download Data"):
            st.download_button(
                label="📊 Hourly Data",
                data=df_hourly_agg.to_csv(index=False).encode('utf-8'),
                file_name=f'hourly_{selected_area}.csv',
                mime='text/csv',
                use_container_width=True
            )
            st.download_button(
                label="⏰ Interval Data",
                data=df_interval_agg.to_csv(index=False).encode('utf-8'),
                file_name=f'interval_{selected_area}.csv',
                mime='text/csv',
                use_container_width=True
            )

st.markdown("---")

# ==============================
# KEY METRICS
# ==============================
st.markdown("## 📈 Performance Overview")

total_rides = df_filtered["Rides"].sum()
total_sessions = df_filtered["Sessions"].sum()
unique_neighborhoods = df_filtered["Neighborhood"].nunique()
total_missed_opportunity = total_sessions - total_rides
overall_fulfillment = (total_rides / total_sessions * 100) if total_sessions > 0 else 0

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric(
    "🚴 Total Rides", 
    f"{total_rides:,}",
    help="Total completed rides"
)
m2.metric(
    "📱 Total Sessions", 
    f"{total_sessions:,}",
    help="Total ride requests"
)
m3.metric(
    "🎯 Fulfillment Rate",
    f"{overall_fulfillment:.1f}%",
    help="Percentage converted to rides"
)
m4.metric(
    "💔 Missed Opps", 
    f"{total_missed_opportunity:,}",
    help="Sessions not converted",
    delta=f"-{(total_missed_opportunity/total_sessions*100):.1f}%" if total_sessions > 0 else None,
    delta_color="inverse"
)
m5.metric(
    "🏘️ Active Areas", 
    unique_neighborhoods,
    help="Neighborhoods with activity"
)

st.markdown("---")

# ==============================
# 1. LEADERBOARD
# ==============================
st.markdown("## 🏆 Neighborhood Performance Leaderboard")
st.caption("Rankings based on Rides Per Day Per Vehicle (RPDPV)")

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
agg["Fulfillment Rate"] = np.where(
    agg["Sessions"] > 0,
    agg["Rides"] / agg["Sessions"] * 100,
    0
)

st.dataframe(
    agg.sort_values("RPDPV", ascending=False),
    use_container_width=True,
    height=400,
    column_config={
        "Neighborhood": st.column_config.TextColumn("Neighborhood", width="medium"),
        "Rides": st.column_config.NumberColumn("Total Rides", format="%d"),
        "Sessions": st.column_config.NumberColumn("Total Sessions", format="%d"),
        "Fulfillment Rate": st.column_config.NumberColumn("Fulfillment %", format="%.1f%%"),
        "Missed Opportunity": st.column_config.NumberColumn("Missed Opps", format="%d"),
        "Rides per Day": st.column_config.NumberColumn("Rides/Day", format="%.1f"),
        "Active (Avg)": st.column_config.NumberColumn("Avg Vehicles", format="%.1f"),
        "RPDPV": st.column_config.ProgressColumn(
            "⭐ RPDPV",
            help="Efficiency score",
            format="%.2f",
            min_value=0,
            max_value=agg["RPDPV"].max(),
            width="large"
        ),
    },
    hide_index=True,
    column_order=[
        "Neighborhood", "RPDPV", "Fulfillment Rate", "Rides", "Sessions", 
        "Missed Opportunity", "Rides per Day", "Active (Avg)"
    ]
)

st.markdown("---")

# ==============================
# 2. FULFILLMENT HEATMAP
# ==============================
st.markdown("## 🔥 Fulfillment Rate Heatmap")

col_c, col_i = st.columns([2, 5])
with col_c:
    chart_granularity_2 = add_granularity_control(2)

agg_config_2 = get_aggregation_for_granularity(
    chart_granularity_2, 
    df_hourly_agg, 
    df_interval_agg
)

with col_i:
    st.info("📊 Lighter colors = higher fulfillment. Identify peak performance periods.")

fulfillment_chart = alt.Chart(agg_config_2["df"]).mark_rect(strokeWidth=1, stroke='white').encode(
    x=alt.X(
        f"{agg_config_2['time_dim']}:O", 
        title=agg_config_2['time_title'], 
        sort=agg_config_2['time_sort'],
        axis=alt.Axis(labelAngle=-45, labelFontSize=12)
    ),
    y=alt.Y(
        "Neighborhood:O", 
        title="Neighborhood",
        axis=alt.Axis(labelFontSize=12)
    ),
    color=alt.Color(
        "Neighborhood Fulfillment Rate:Q",
        scale=alt.Scale(
            domain=[0, 1],
            range=['#8B0000', '#FFD700', '#90EE90'],
        ),
        legend=alt.Legend(
            title="Fulfillment Rate",
            format=".0%",
            orient="right",
            titleFontSize=12
        )
    ),
    tooltip=[
        alt.Tooltip("Neighborhood:N", title="Neighborhood"),
        alt.Tooltip(f"{agg_config_2['time_dim']}:O", title=agg_config_2['time_title']),
        alt.Tooltip("Neighborhood Fulfillment Rate:Q", format=".1%", title="✅ Fulfillment"),
        alt.Tooltip("Rides:Q", format=",", title="🚴 Rides"),
        alt.Tooltip("Sessions:Q", format=",", title="📱 Sessions"),
        alt.Tooltip("Missed Opportunity:Q", format=",", title="💔 Missed"),
        alt.Tooltip("Active (Avg):Q", format=".1f", title="🚲 Vehicles"),
    ]
).properties(
    height=max(MIN_CHART_HEIGHT, len(agg_config_2["df"]["Neighborhood"].unique()) * PIXELS_PER_NEIGHBORHOOD)
).configure_view(strokeWidth=0)

st.altair_chart(fulfillment_chart, use_container_width=True)
st.markdown("---")

# ==============================
# 3. MISSED OPPORTUNITY
# ==============================
st.markdown("## 💔 Missed Opportunity Analysis")

col_c, col_i = st.columns([2, 5])
with col_c:
    chart_granularity_3 = add_granularity_control(3)

agg_config_3 = get_aggregation_for_granularity(
    chart_granularity_3,
    df_hourly_agg,
    df_interval_agg
)

with col_i:
    st.info("📊 Darker red = more missed opportunities. Priority areas for improvement.")

missed_chart = alt.Chart(agg_config_3["df"]).mark_rect(strokeWidth=1, stroke='white').encode(
    x=alt.X(
        f"{agg_config_3['time_dim']}:O",
        title=agg_config_3['time_title'],
        sort=agg_config_3['time_sort'],
        axis=alt.Axis(labelAngle=-45, labelFontSize=12)
    ),
    y=alt.Y("Neighborhood:O", title="Neighborhood", axis=alt.Axis(labelFontSize=12)),
    color=alt.Color(
        "Missed Opportunity:Q",
        scale=alt.Scale(scheme="reds", domainMin=0),
        legend=alt.Legend(title="Missed Opps", orient="right", titleFontSize=12)
    ),
    tooltip=[
        alt.Tooltip("Neighborhood:N", title="Neighborhood"),
        alt.Tooltip(f"{agg_config_3['time_dim']}:O", title=agg_config_3['time_title']),
        alt.Tooltip("Missed Opportunity:Q", format=",", title="💔 Missed"),
        alt.Tooltip("Neighborhood Fulfillment Rate:Q", format=".1%", title="✅ Fulfillment"),
        alt.Tooltip("Rides:Q", format=",", title="🚴 Rides"),
        alt.Tooltip("Sessions:Q", format=",", title="📱 Sessions"),
    ]
).properties(
    height=max(MIN_CHART_HEIGHT, len(agg_config_3["df"]["Neighborhood"].unique()) * PIXELS_PER_NEIGHBORHOOD)
).configure_view(strokeWidth=0)

st.altair_chart(missed_chart, use_container_width=True)
st.markdown("---")

# ==============================
# 4. FULFILLMENT TRENDS
# ==============================
st.markdown("## 📈 Fulfillment Trends by Neighborhood")

col_c, col_i = st.columns([2, 5])
with col_c:
    chart_granularity_4 = add_granularity_control(4)

agg_config_4 = get_aggregation_for_granularity(
    chart_granularity_4,
    df_hourly_agg,
    df_interval_agg
)

with col_i:
    st.info("📊 Compare fulfillment patterns. Look for consistent performers vs volatility.")

trend_chart = alt.Chart(agg_config_4["df"]).mark_line(
    point=alt.OverlayMarkDef(size=60, filled=True),
    strokeWidth=3
).encode(
    x=alt.X(
        f"{agg_config_4['time_dim']}:O",
        title=agg_config_4['time_title'],
        sort=agg_config_4['time_sort'],
        axis=alt.Axis(labelAngle=-45, labelFontSize=12)
    ),
    y=alt.Y(
        "Neighborhood Fulfillment Rate:Q",
        title="Fulfillment Rate",
        axis=alt.Axis(format=".0%", labelFontSize=12),
        scale=alt.Scale(domain=[0, 1])
    ),
    color=alt.Color("Neighborhood:N", legend=alt.Legend(titleFontSize=12)),
    tooltip=[
        alt.Tooltip("Neighborhood:N", title="Neighborhood"),
        alt.Tooltip(f"{agg_config_4['time_dim']}:O", title=agg_config_4['time_title']),
        alt.Tooltip("Neighborhood Fulfillment Rate:Q", format=".1%", title="✅ Fulfillment"),
        alt.Tooltip("Rides:Q", format=",", title="🚴 Rides"),
    ]
).properties(height=500).configure_view(strokeWidth=0)

st.altair_chart(trend_chart, use_container_width=True)
st.markdown("---")

# ==============================
# 5. AGGREGATE DEMAND
# ==============================
st.markdown("## 📊 Aggregate Demand Patterns")

col_c, col_i = st.columns([2, 5])
with col_c:
    chart_granularity_5 = add_granularity_control(5)

agg_config_5 = get_aggregation_for_granularity(
    chart_granularity_5,
    df_hourly_agg,
    df_interval_agg
)

with col_i:
    st.info("📊 Overall demand patterns and urgent vehicle needs. Spot peak times.")

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

demand_chart = alt.Chart(dynamic_long).mark_line(
    point=True, 
    strokeWidth=3,
    interpolate='monotone'
).encode(
    x=alt.X(
        f"{agg_config_5['time_dim']}:O",
        title=agg_config_5['time_title'],
        sort=agg_config_5['time_sort'],
        axis=alt.Axis(labelAngle=-45, labelFontSize=12)
    ),
    y=alt.Y("Count:Q", title="Total Count", axis=alt.Axis(labelFontSize=12)),
    color=alt.Color("Metric:N", legend=alt.Legend(titleFontSize=12)),
    tooltip=[
        alt.Tooltip(agg_config_5["time_dim"], title=agg_config_5['time_title']),
        alt.Tooltip("Metric:N", title="Metric"),
        alt.Tooltip("Count:Q", format=",.1f", title="Count")
    ]
).properties(height=450).configure_view(strokeWidth=0)

st.altair_chart(demand_chart, use_container_width=True)
