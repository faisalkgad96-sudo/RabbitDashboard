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

fulfillment_chart = alt.Chart(agg_config_2["df"]).mark_rect(strokeWidth=2, stroke='#1a1a1a').encode(
    x=alt.X(
        f"{agg_config_2['time_dim']}:O", 
        title=agg_config_2['time_title'], 
        sort=agg_config_2['time_sort'],
        axis=alt.Axis(
            labelAngle=-45, 
            labelFontSize=13,
            titleFontSize=14,
            labelColor='white',
            titleColor='white'
        )
    ),
    y=alt.Y(
        "Neighborhood:O", 
        title="Neighborhood",
        axis=alt.Axis(
            labelFontSize=13,
            titleFontSize=14,
            labelColor='white',
            titleColor='white'
        )
    ),
    color=alt.Color(
        "Neighborhood Fulfillment Rate:Q",
        scale=alt.Scale(
            domain=[0, 0.5, 1],
            range=['#8B0000', '#FF8C00', '#00FF00'],
        ),
        legend=alt.Legend(
            title="Fulfillment Rate",
            format=".0%",
            orient="right",
            titleFontSize=13,
            labelFontSize=12,
            titleColor='white',
            labelColor='white',
            gradientLength=300
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
).configure_view(
    strokeWidth=0
).configure(
    background='#0e1117'
)

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

missed_chart = alt.Chart(agg_config_3["df"]).mark_rect(strokeWidth=2, stroke='#1a1a1a').encode(
    x=alt.X(
        f"{agg_config_3['time_dim']}:O",
        title=agg_config_3['time_title'],
        sort=agg_config_3['time_sort'],
        axis=alt.Axis(
            labelAngle=-45, 
            labelFontSize=13,
            titleFontSize=14,
            labelColor='white',
            titleColor='white'
        )
    ),
    y=alt.Y(
        "Neighborhood:O", 
        title="Neighborhood", 
        axis=alt.Axis(
            labelFontSize=13,
            titleFontSize=14,
            labelColor='white',
            titleColor='white'
        )
    ),
    color=alt.Color(
        "Missed Opportunity:Q",
        scale=alt.Scale(
            scheme="reds", 
            domainMin=0,
            reverse=False
        ),
        legend=alt.Legend(
            title="Missed Opps", 
            orient="right", 
            titleFontSize=13,
            labelFontSize=12,
            titleColor='white',
            labelColor='white',
            gradientLength=300
        )
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
).configure_view(
    strokeWidth=0
).configure(
    background='#0e1117'
)

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
    
    # Debug expander to see data stats
    with st.expander("🔍 Debug: View Data Summary"):
        st.write(f"**Total data points:** {len(agg_config_4['df'])}")
        st.write(f"**Unique neighborhoods:** {agg_config_4['df']['Neighborhood'].nunique()}")
        st.write(f"**Neighborhoods list:**")
        st.write(sorted(agg_config_4['df']['Neighborhood'].unique().tolist()))
        st.write(f"**Sample data:**")
        st.dataframe(agg_config_4['df'].head(10), use_container_width=True)

# Show neighborhood selector above chart
neighborhoods_in_chart = sorted(agg_config_4["df"]["Neighborhood"].unique())
st.markdown(f"**{len(neighborhoods_in_chart)} neighborhoods** in this view")

selected_neighborhoods = st.multiselect(
    "Filter by neighborhoods (leave empty to show all):",
    options=neighborhoods_in_chart,
    default=[],
    key="trend_neighborhood_filter"
)

# Filter data if neighborhoods are selected
if selected_neighborhoods:
    trend_data = agg_config_4["df"][agg_config_4["df"]["Neighborhood"].isin(selected_neighborhoods)]
else:
    trend_data = agg_config_4["df"]

# Create selection for interactivity
selection = alt.selection_point(fields=['Neighborhood'], bind='legend', on='click')

trend_chart = alt.Chart(trend_data).mark_line(
    point=alt.OverlayMarkDef(size=120, filled=True, opacity=1),
    strokeWidth=5,
    opacity=1
).encode(
    x=alt.X(
        f"{agg_config_4['time_dim']}:O",
        title=agg_config_4['time_title'],
        sort=agg_config_4['time_sort'],
        axis=alt.Axis(
            labelAngle=-45, 
            labelFontSize=13,
            titleFontSize=14,
            labelColor='white',
            titleColor='white',
            gridColor='rgba(128, 128, 128, 0.3)',
            grid=True
        )
    ),
    y=alt.Y(
        "Neighborhood Fulfillment Rate:Q",
        title="Fulfillment Rate",
        axis=alt.Axis(
            format=".0%", 
            labelFontSize=13,
            titleFontSize=14,
            labelColor='white',
            titleColor='white',
            gridColor='rgba(128, 128, 128, 0.3)',
            grid=True
        ),
        scale=alt.Scale(domain=[0, 1])
    ),
    color=alt.Color(
        "Neighborhood:N", 
        scale=alt.Scale(scheme='category20'),
        legend=alt.Legend(
            titleFontSize=12,
            labelFontSize=11,
            titleColor='white',
            labelColor='white',
            symbolSize=200,
            symbolStrokeWidth=3,
            title="Neighborhood (Click to filter)",
            orient='right',
            columns=1,
            labelLimit=200
        )
    ),
    opacity=alt.condition(selection, alt.value(1), alt.value(0.2)),
    strokeWidth=alt.condition(selection, alt.value(5), alt.value(2)),
    tooltip=[
        alt.Tooltip("Neighborhood:N", title="Neighborhood"),
        alt.Tooltip(f"{agg_config_4['time_dim']}:O", title=agg_config_4['time_title']),
        alt.Tooltip("Neighborhood Fulfillment Rate:Q", format=".1%", title="✅ Fulfillment"),
        alt.Tooltip("Rides:Q", format=",", title="🚴 Rides"),
        alt.Tooltip("Sessions:Q", format=",", title="📱 Sessions"),
    ]
).add_params(
    selection
).properties(
    width='container',
    height=550
).configure_view(
    strokeWidth=0
).configure(
    background='#0e1117'
)

st.caption("💡 **Tip:** Use the dropdown above to filter specific neighborhoods, or click legend items to highlight")

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

# Create selection for demand chart
demand_selection = alt.selection_point(fields=['Metric'], bind='legend', on='click')

demand_chart = alt.Chart(dynamic_long).mark_line(
    point=alt.OverlayMarkDef(size=150, filled=True, opacity=1),
    strokeWidth=6,
    interpolate='monotone',
    opacity=1
).encode(
    x=alt.X(
        f"{agg_config_5['time_dim']}:O",
        title=agg_config_5['time_title'],
        sort=agg_config_5['time_sort'],
        axis=alt.Axis(
            labelAngle=-45, 
            labelFontSize=13,
            titleFontSize=14,
            labelColor='white',
            titleColor='white',
            gridColor='rgba(128, 128, 128, 0.3)',
            grid=True
        )
    ),
    y=alt.Y(
        "Count:Q", 
        title="Total Count", 
        axis=alt.Axis(
            labelFontSize=13,
            titleFontSize=14,
            labelColor='white',
            titleColor='white',
            gridColor='rgba(128, 128, 128, 0.3)',
            grid=True
        )
    ),
    color=alt.Color(
        "Metric:N", 
        scale=alt.Scale(
            domain=['Rides', 'Sessions', 'Urgent_Vehicles'],
            range=['#00D9FF', '#FF6B9D', '#FFA500']  # Bright cyan, pink, orange
        ),
        legend=alt.Legend(
            titleFontSize=13,
            labelFontSize=12,
            titleColor='white',
            labelColor='white',
            symbolSize=250,
            symbolStrokeWidth=4,
            title="Metric (Click to filter)"
        )
    ),
    opacity=alt.condition(demand_selection, alt.value(1), alt.value(0.2)),
    strokeWidth=alt.condition(demand_selection, alt.value(6), alt.value(2)),
    tooltip=[
        alt.Tooltip(agg_config_5["time_dim"], title=agg_config_5['time_title']),
        alt.Tooltip("Metric:N", title="Metric"),
        alt.Tooltip("Count:Q", format=",.1f", title="Count")
    ]
).add_params(
    demand_selection
).properties(height=500).configure_view(
    strokeWidth=0
).configure(
    background='#0e1117'
)

st.caption("💡 **Tip:** Click on metric names in the legend to highlight specific metrics")

st.altair_chart(demand_chart, use_container_width=True)

st.markdown("---")

# ==============================
# 6. INSIGHTS & RECOMMENDATIONS
# ==============================
st.markdown("## 💡 Key Insights & Recommendations")
st.caption("AI-generated insights based on your data analysis")

# Create two tabs for Area-level and Neighborhood-level insights
tab1, tab2 = st.tabs(["🌍 Area-Level Insights", "🏘️ Neighborhood-Level Insights"])

with tab1:
    st.markdown("### Area Performance Summary")
    
    # Area-level calculations
    area_fulfillment = (total_rides / total_sessions * 100) if total_sessions > 0 else 0
    area_utilization = (total_rides / total_avg_active_scooters) if total_avg_active_scooters > 0 else 0
    
    # Determine peak times
    hourly_demand = df_filtered.groupby("_hour").agg(
        Total_Rides=("Rides", "sum"),
        Total_Sessions=("Sessions", "sum")
    ).reset_index()
    peak_hour = hourly_demand.loc[hourly_demand["Total_Sessions"].idxmax(), "_hour"]
    lowest_hour = hourly_demand.loc[hourly_demand["Total_Sessions"].idxmin(), "_hour"]
    
    # Time interval analysis
    interval_demand = df_filtered.groupby("_time_interval").agg(
        Total_Rides=("Rides", "sum"),
        Total_Sessions=("Sessions", "sum"),
        Fulfillment=("Rides", "sum")
    ).reset_index()
    interval_demand["Fulfillment_Rate"] = interval_demand["Total_Rides"] / interval_demand["Total_Sessions"]
    best_interval = interval_demand.loc[interval_demand["Fulfillment_Rate"].idxmax(), "_time_interval"]
    worst_interval = interval_demand.loc[interval_demand["Fulfillment_Rate"].idxmin(), "_time_interval"]
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📊 Overall Performance")
        
        # Performance assessment
        if area_fulfillment >= 80:
            performance_status = "🟢 **Excellent**"
            performance_desc = "The area is performing very well with strong fulfillment rates."
        elif area_fulfillment >= 65:
            performance_status = "🟡 **Good**"
            performance_desc = "The area is performing adequately but has room for improvement."
        else:
            performance_status = "🔴 **Needs Attention**"
            performance_desc = "The area is underperforming and requires immediate action."
        
        st.markdown(f"**Status:** {performance_status}")
        st.write(performance_desc)
        st.write(f"- Overall Fulfillment Rate: **{area_fulfillment:.1f}%**")
        st.write(f"- Average Utilization: **{area_utilization:.2f} rides/vehicle**")
        st.write(f"- Total Missed Opportunities: **{total_missed_opportunity:,}**")
        st.write(f"- Opportunity Cost: **{(total_missed_opportunity/total_sessions*100):.1f}%** of demand unmet")
        
        st.markdown("#### ⏰ Demand Patterns")
        st.write(f"- **Peak Hour:** {peak_hour}:00 (highest demand)")
        st.write(f"- **Quietest Hour:** {lowest_hour}:00 (lowest demand)")
        st.write(f"- **Best Time Interval:** {best_interval}")
        st.write(f"- **Weakest Time Interval:** {worst_interval}")
    
    with col2:
        st.markdown("#### 🎯 Strategic Recommendations")
        
        recommendations = []
        
        # Fulfillment-based recommendations
        if area_fulfillment < 70:
            recommendations.append({
                "priority": "🔴 HIGH",
                "action": "Increase Vehicle Supply",
                "detail": f"With {area_fulfillment:.1f}% fulfillment, you're losing {(100-area_fulfillment):.1f}% of potential revenue. Consider adding {int(total_missed_opportunity/num_selected_days/5)} vehicles."
            })
        
        # Utilization-based recommendations
        if area_utilization < 3:
            recommendations.append({
                "priority": "🟡 MEDIUM",
                "action": "Optimize Vehicle Distribution",
                "detail": f"Utilization is {area_utilization:.2f} rides/vehicle. Redistribute vehicles from low-demand to high-demand neighborhoods."
            })
        elif area_utilization > 8:
            recommendations.append({
                "priority": "🟢 OPPORTUNITY",
                "action": "Scale Up Operations",
                "detail": f"Excellent utilization ({area_utilization:.2f} rides/vehicle) indicates strong demand. Consider expanding fleet."
            })
        
        # Time-based recommendations
        worst_interval_data = interval_demand[interval_demand["_time_interval"] == worst_interval].iloc[0]
        worst_fulfillment = worst_interval_data["Fulfillment_Rate"] * 100
        
        if worst_fulfillment < 65:
            recommendations.append({
                "priority": "🟡 MEDIUM",
                "action": f"Address {worst_interval} Performance",
                "detail": f"Fulfillment drops to {worst_fulfillment:.1f}% during this period. Adjust rebalancing schedule or add temporary vehicles."
            })
        
        # Missed opportunity recommendations
        missed_opp_rate = (total_missed_opportunity / total_sessions * 100)
        if missed_opp_rate > 30:
            recommendations.append({
                "priority": "🔴 HIGH",
                "action": "Reduce Lost Revenue",
                "detail": f"You're missing {total_missed_opportunity:,} rides ({missed_opp_rate:.1f}% of demand). This represents significant lost revenue."
            })
        
        # Display recommendations
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                st.markdown(f"**{rec['priority']} - {rec['action']}**")
                st.write(rec['detail'])
                if i < len(recommendations):
                    st.write("")  # Spacing
        else:
            st.success("✅ Area is performing well! Continue monitoring for optimization opportunities.")
    
    # Add trend analysis
    st.markdown("---")
    st.markdown("#### 📈 Trend Analysis")
    
    # Calculate performance by day if multiple days selected
    if num_selected_days > 1:
        daily_performance = df_filtered.groupby("_date").agg(
            Rides=("Rides", "sum"),
            Sessions=("Sessions", "sum")
        ).reset_index()
        daily_performance["Fulfillment"] = daily_performance["Rides"] / daily_performance["Sessions"] * 100
        
        best_day = daily_performance.loc[daily_performance["Fulfillment"].idxmax()]
        worst_day = daily_performance.loc[daily_performance["Fulfillment"].idxmin()]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Best Day", best_day["_date"], f"{best_day['Fulfillment']:.1f}% fulfillment")
        col2.metric("Worst Day", worst_day["_date"], f"{worst_day['Fulfillment']:.1f}% fulfillment")
        col3.metric("Variance", f"{daily_performance['Fulfillment'].std():.1f}%", 
                   "High volatility" if daily_performance['Fulfillment'].std() > 10 else "Stable")

with tab2:
    st.markdown("### Neighborhood-Level Analysis")
    
    # Calculate comprehensive neighborhood metrics
    neighborhood_analysis = agg.copy()
    neighborhood_analysis["Utilization"] = np.where(
        neighborhood_analysis["Active (Avg)"] > 0,
        neighborhood_analysis["Rides"] / neighborhood_analysis["Active (Avg)"],
        0
    )
    neighborhood_analysis["Missed_Opp_Rate"] = np.where(
        neighborhood_analysis["Sessions"] > 0,
        neighborhood_analysis["Missed Opportunity"] / neighborhood_analysis["Sessions"] * 100,
        0
    )
    
    # Categorize neighborhoods
    def categorize_neighborhood(row):
        fulfillment = row["Fulfillment Rate"]
        utilization = row["Utilization"]
        
        if fulfillment >= 75 and utilization >= 5:
            return "⭐ Star Performer"
        elif fulfillment >= 75:
            return "🎯 High Fulfillment"
        elif utilization >= 5:
            return "🔥 High Demand"
        elif fulfillment < 60:
            return "🔴 Critical"
        else:
            return "🟡 Moderate"
    
    neighborhood_analysis["Category"] = neighborhood_analysis.apply(categorize_neighborhood, axis=1)
    
    # Show category breakdown
    st.markdown("#### 📊 Neighborhood Categories")
    category_counts = neighborhood_analysis["Category"].value_counts()
    
    col1, col2, col3, col4, col5 = st.columns(5)
    cols = [col1, col2, col3, col4, col5]
    
    for idx, (category, count) in enumerate(category_counts.items()):
        if idx < len(cols):
            cols[idx].metric(category, count, f"{count/len(neighborhood_analysis)*100:.0f}%")
    
    st.markdown("---")
    
    # Top performers and underperformers
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🏆 Top 5 Performers (by RPDPV)")
        top_performers = neighborhood_analysis.nlargest(5, "RPDPV")[
            ["Neighborhood", "RPDPV", "Fulfillment Rate", "Utilization", "Category"]
        ]
        st.dataframe(
            top_performers,
            use_container_width=True,
            hide_index=True,
            column_config={
                "RPDPV": st.column_config.NumberColumn("RPDPV", format="%.2f"),
                "Fulfillment Rate": st.column_config.NumberColumn("Fulfillment %", format="%.1f%%"),
                "Utilization": st.column_config.NumberColumn("Utilization", format="%.2f"),
            }
        )
        
        st.markdown("**Why they succeed:**")
        top_avg_fulfillment = top_performers["Fulfillment Rate"].mean()
        top_avg_util = top_performers["Utilization"].mean()
        st.write(f"- Average fulfillment: **{top_avg_fulfillment:.1f}%**")
        st.write(f"- Average utilization: **{top_avg_util:.2f} rides/vehicle**")
        st.write("- Consistent vehicle availability during peak hours")
    
    with col2:
        st.markdown("#### 🔴 Bottom 5 Performers (by RPDPV)")
        bottom_performers = neighborhood_analysis.nsmallest(5, "RPDPV")[
            ["Neighborhood", "RPDPV", "Fulfillment Rate", "Missed_Opp_Rate", "Category"]
        ]
        st.dataframe(
            bottom_performers,
            use_container_width=True,
            hide_index=True,
            column_config={
                "RPDPV": st.column_config.NumberColumn("RPDPV", format="%.2f"),
                "Fulfillment Rate": st.column_config.NumberColumn("Fulfillment %", format="%.1f%%"),
                "Missed_Opp_Rate": st.column_config.NumberColumn("Missed Opp %", format="%.1f%%"),
            }
        )
        
        st.markdown("**Areas for improvement:**")
        bottom_avg_fulfillment = bottom_performers["Fulfillment Rate"].mean()
        bottom_avg_missed = bottom_performers["Missed_Opp_Rate"].mean()
        st.write(f"- Average fulfillment: **{bottom_avg_fulfillment:.1f}%**")
        st.write(f"- Average missed rate: **{bottom_avg_missed:.1f}%**")
        st.write("- Need better vehicle distribution or increased supply")
    
    st.markdown("---")
    
    # Specific neighborhood insights
    st.markdown("#### 🔍 Detailed Neighborhood Insights")
    
    selected_neighborhood = st.selectbox(
        "Select a neighborhood for detailed analysis:",
        options=sorted(neighborhood_analysis["Neighborhood"].tolist()),
        key="insight_neighborhood_select"
    )
    
    if selected_neighborhood:
        nbh_data = neighborhood_analysis[neighborhood_analysis["Neighborhood"] == selected_neighborhood].iloc[0]
        
        # Get hourly data for this neighborhood
        nbh_hourly = df_hourly_agg[df_hourly_agg["Neighborhood"] == selected_neighborhood].copy()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"### {selected_neighborhood}")
            st.markdown(f"**Category:** {nbh_data['Category']}")
            st.metric("RPDPV Rank", f"#{neighborhood_analysis['RPDPV'].rank(ascending=False)[nbh_data.name]:.0f} of {len(neighborhood_analysis)}")
            
        with col2:
            st.metric("Fulfillment Rate", f"{nbh_data['Fulfillment Rate']:.1f}%")
            st.metric("Total Rides", f"{nbh_data['Rides']:,.0f}")
            st.metric("Avg Vehicles", f"{nbh_data['Active (Avg)']:.1f}")
            
        with col3:
            st.metric("RPDPV", f"{nbh_data['RPDPV']:.2f}")
            st.metric("Utilization", f"{nbh_data['Utilization']:.2f}")
            st.metric("Missed Opps", f"{nbh_data['Missed Opportunity']:,.0f}")
        
        # Performance assessment
        st.markdown("**Performance Assessment:**")
        
        if nbh_data["Fulfillment Rate"] >= 75:
            st.success(f"✅ {selected_neighborhood} has strong fulfillment rates. Continue current strategies.")
        elif nbh_data["Fulfillment Rate"] >= 60:
            st.warning(f"⚠️ {selected_neighborhood} has moderate performance. Room for improvement.")
        else:
            st.error(f"🔴 {selected_neighborhood} is underperforming. Immediate action needed.")
        
        # Specific recommendations
        st.markdown("**Recommendations:**")
        
        nbh_recommendations = []
        
        if nbh_data["Fulfillment Rate"] < 70:
            avg_shortage = nbh_data["Missed Opportunity"] / num_selected_days
            nbh_recommendations.append(
                f"🚲 Increase vehicle allocation by ~{int(avg_shortage/5)} units to address {nbh_data['Missed Opportunity']:,.0f} missed opportunities"
            )
        
        if nbh_data["Utilization"] > 7:
            nbh_recommendations.append(
                f"📈 High utilization ({nbh_data['Utilization']:.2f}) indicates strong demand. Consider this neighborhood for expansion"
            )
        elif nbh_data["Utilization"] < 2:
            nbh_recommendations.append(
                f"📉 Low utilization ({nbh_data['Utilization']:.2f}) suggests oversupply. Redistribute {int(nbh_data['Active (Avg)'] * 0.2)} vehicles to higher-demand areas"
            )
        
        # Find best and worst hours
        if not nbh_hourly.empty:
            best_hour = nbh_hourly.loc[nbh_hourly["Neighborhood Fulfillment Rate"].idxmax(), "_hour"]
            worst_hour = nbh_hourly.loc[nbh_hourly["Neighborhood Fulfillment Rate"].idxmin(), "_hour"]
            nbh_recommendations.append(
                f"⏰ Focus rebalancing efforts before {int(worst_hour)}:00 (weakest hour). Best performance at {int(best_hour)}:00"
            )
        
        if nbh_recommendations:
            for rec in nbh_recommendations:
                st.write(f"- {rec}")
        else:
            st.write("- ✅ Neighborhood is performing optimally. Maintain current operations.")

st.markdown("---")

# ==============================
# 7. SMART ALLOCATION MODEL
# ==============================
st.markdown("## 🎯 Smart Vehicle Allocation Model")
st.caption("Data-driven recommendations for optimal vehicle distribution based on demand patterns and historical performance")

# Configuration controls
col_config1, col_config2, col_config3 = st.columns([2, 2, 2])

with col_config1:
    allocation_granularity = st.radio(
        "Time Granularity:",
        ["Hourly (0-23)", "3 Intervals"],
        key="allocation_granularity",
        horizontal=True
    )

with col_config2:
    total_fleet_size = st.number_input(
        "Total Available Fleet:",
        min_value=1,
        value=int(total_avg_active_scooters),
        step=10,
        help="Total number of scooters you want to allocate"
    )

with col_config3:
    confidence_threshold = st.slider(
        "Confidence Threshold:",
        min_value=50,
        max_value=100,
        value=70,
        step=5,
        help="Minimum fulfillment rate to consider neighborhood reliable (%)"
    )

st.markdown("---")

# Select time period for allocation
is_hourly_alloc = allocation_granularity == "Hourly (0-23)"
alloc_agg_df = df_hourly_agg if is_hourly_alloc else df_interval_agg
time_dim_alloc = "_hour" if is_hourly_alloc else "_time_interval"
time_options = sorted(alloc_agg_df[time_dim_alloc].unique()) if is_hourly_alloc else INTERVAL_ORDER

selected_time_period = st.selectbox(
    f"Select {('Hour' if is_hourly_alloc else 'Interval')} for Allocation Analysis:",
    options=time_options,
    format_func=lambda x: f"Hour {x}:00" if is_hourly_alloc else x
)

# Filter data for selected time period
period_data = alloc_agg_df[alloc_agg_df[time_dim_alloc] == selected_time_period].copy()

if period_data.empty:
    st.warning(f"No data available for {selected_time_period}")
    st.stop()

# ==============================
# ALLOCATION ALGORITHM
# ==============================

# Step 1: Calculate demand metrics
period_data["Demand_Score"] = period_data["Sessions"]  # Raw demand
period_data["Missed_Rate"] = np.where(
    period_data["Sessions"] > 0,
    period_data["Missed Opportunity"] / period_data["Sessions"] * 100,
    0
)

# Step 2: Calculate reliability score (historical performance)
# Penalize neighborhoods with low fulfillment even if they look efficient
period_data["Reliability_Score"] = np.where(
    period_data["Neighborhood Fulfillment Rate"] >= (confidence_threshold/100),
    period_data["Neighborhood Fulfillment Rate"] * 100,
    period_data["Neighborhood Fulfillment Rate"] * 50  # Heavy penalty for unreliable neighborhoods
)

# Step 3: Calculate current efficiency (but don't over-weight it)
period_data["Current_Efficiency"] = np.where(
    period_data["Active (Avg)"] > 0,
    period_data["Rides"] / period_data["Active (Avg)"],
    0
)

# Step 4: Calculate unmet demand potential
# This accounts for neighborhoods that might perform better with more scooters
period_data["Unmet_Demand"] = period_data["Missed Opportunity"]
period_data["Demand_Density"] = np.where(
    period_data["Active (Avg)"] > 0,
    period_data["Sessions"] / period_data["Active (Avg)"],
    period_data["Sessions"]
)

# Step 5: Calculate elasticity indicator
# High sessions + low vehicles + decent fulfillment = likely to benefit from more scooters
# High sessions + low vehicles + poor fulfillment = risky (might have other issues)
period_data["Growth_Potential"] = np.where(
    (period_data["Demand_Density"] > period_data["Demand_Density"].median()) &
    (period_data["Neighborhood Fulfillment Rate"] >= (confidence_threshold/100)),
    period_data["Unmet_Demand"] * 1.5,  # Boost for high-demand reliable neighborhoods
    period_data["Unmet_Demand"]
)

# Step 6: Composite Allocation Score
# Weights: 40% demand, 25% reliability, 20% unmet demand, 15% growth potential
period_data["Allocation_Score"] = (
    (period_data["Demand_Score"] / period_data["Demand_Score"].max() * 40) +
    (period_data["Reliability_Score"] / 100 * 25) +
    (period_data["Unmet_Demand"] / period_data["Unmet_Demand"].max() * 20) +
    (period_data["Growth_Potential"] / period_data["Growth_Potential"].max() * 15)
)

# Step 7: Allocate vehicles proportionally based on composite score
total_score = period_data["Allocation_Score"].sum()
period_data["Recommended_Vehicles"] = np.floor(
    (period_data["Allocation_Score"] / total_score) * total_fleet_size
).astype(int)

# Step 8: Distribute remaining vehicles to highest-scoring neighborhoods
remaining = total_fleet_size - period_data["Recommended_Vehicles"].sum()
if remaining > 0:
    top_indices = period_data.nlargest(remaining, "Allocation_Score").index
    period_data.loc[top_indices, "Recommended_Vehicles"] += 1

# Step 9: Calculate expected impact
period_data["Current_Vehicles"] = period_data["Active (Avg)"]
period_data["Vehicle_Change"] = period_data["Recommended_Vehicles"] - period_data["Current_Vehicles"]
period_data["Expected_New_Rides"] = np.where(
    period_data["Recommended_Vehicles"] > period_data["Current_Vehicles"],
    (period_data["Vehicle_Change"] * period_data["Current_Efficiency"]).clip(
        lower=0, 
        upper=period_data["Missed Opportunity"]  # Can't exceed missed opportunity
    ),
    0
)

# Step 10: Flag risk categories
def categorize_allocation_risk(row):
    if row["Neighborhood Fulfillment Rate"] < (confidence_threshold/100):
        return "⚠️ High Risk"
    elif row["Current_Efficiency"] < 2:
        return "🟡 Medium Risk"
    else:
        return "✅ Low Risk"

period_data["Risk_Category"] = period_data.apply(categorize_allocation_risk, axis=1)

# ==============================
# DISPLAY ALLOCATION RESULTS
# ==============================

st.markdown(f"### 📊 Allocation Results for {selected_time_period}")

# Summary metrics
col1, col2, col3, col4 = st.columns(4)

total_expected_new_rides = period_data["Expected_New_Rides"].sum()
current_total_fulfillment = (period_data["Rides"].sum() / period_data["Sessions"].sum() * 100)
projected_total_rides = period_data["Rides"].sum() + total_expected_new_rides
projected_fulfillment = (projected_total_rides / period_data["Sessions"].sum() * 100)

col1.metric(
    "Current Fulfillment",
    f"{current_total_fulfillment:.1f}%"
)
col2.metric(
    "Projected Fulfillment",
    f"{projected_fulfillment:.1f}%",
    delta=f"+{projected_fulfillment - current_total_fulfillment:.1f}%"
)
col3.metric(
    "Expected New Rides",
    f"{int(total_expected_new_rides):,}",
    delta=f"+{(total_expected_new_rides/period_data['Rides'].sum()*100):.1f}%"
)
col4.metric(
    "Fleet Efficiency",
    f"{(projected_total_rides / total_fleet_size):.2f}",
    delta="rides/vehicle",
    help="Projected rides per vehicle across entire fleet"
)

st.markdown("---")

# Detailed allocation table
st.markdown("#### 📋 Recommended Vehicle Allocation by Neighborhood")

# Prepare display dataframe
display_df = period_data[[
    "Neighborhood", 
    "Sessions",
    "Rides",
    "Missed Opportunity",
    "Current_Vehicles",
    "Recommended_Vehicles",
    "Vehicle_Change",
    "Expected_New_Rides",
    "Neighborhood Fulfillment Rate",
    "Allocation_Score",
    "Risk_Category"
]].copy()

display_df = display_df.sort_values("Allocation_Score", ascending=False)
display_df["Fulfillment_Rate_Pct"] = display_df["Neighborhood Fulfillment Rate"] * 100

st.dataframe(
    display_df,
    use_container_width=True,
    height=500,
    column_config={
        "Neighborhood": st.column_config.TextColumn("Neighborhood", width="medium"),
        "Sessions": st.column_config.NumberColumn("Sessions", format="%d"),
        "Rides": st.column_config.NumberColumn("Rides", format="%d"),
        "Missed Opportunity": st.column_config.NumberColumn("Missed Opps", format="%d"),
        "Current_Vehicles": st.column_config.NumberColumn("Current Fleet", format="%.1f"),
        "Recommended_Vehicles": st.column_config.NumberColumn("Recommended", format="%d"),
        "Vehicle_Change": st.column_config.NumberColumn(
            "Change",
            format="%+d",
            help="Positive = add vehicles, Negative = remove vehicles"
        ),
        "Expected_New_Rides": st.column_config.NumberColumn("Expected +Rides", format="%d"),
        "Fulfillment_Rate_Pct": st.column_config.NumberColumn("Fulfillment %", format="%.1f%%"),
        "Allocation_Score": st.column_config.ProgressColumn(
            "Priority Score",
            format="%.1f",
            min_value=0,
            max_value=100,
            help="Composite score: demand, reliability, unmet need, growth potential"
        ),
        "Risk_Category": st.column_config.TextColumn("Risk Level"),
        "Neighborhood Fulfillment Rate": None  # Hide this column
    },
    hide_index=True,
    column_order=[
        "Neighborhood",
        "Allocation_Score",
        "Current_Vehicles",
        "Recommended_Vehicles",
        "Vehicle_Change",
        "Expected_New_Rides",
        "Sessions",
        "Rides",
        "Missed Opportunity",
        "Fulfillment_Rate_Pct",
        "Risk_Category"
    ]
)

# Download allocation plan
st.download_button(
    label="📥 Download Allocation Plan (CSV)",
    data=display_df.to_csv(index=False).encode('utf-8'),
    file_name=f'allocation_plan_{selected_time_period}.csv',
    mime='text/csv',
    use_container_width=False
)

st.markdown("---")

# Visualizations
col_viz1, col_viz2 = st.columns(2)

with col_viz1:
    st.markdown("#### 📊 Vehicle Reallocation Changes")
    
    # Create change visualization
    change_data = display_df[display_df["Vehicle_Change"] != 0].copy()
    change_data["Change_Type"] = change_data["Vehicle_Change"].apply(
        lambda x: "Increase" if x > 0 else "Decrease"
    )
    
    if not change_data.empty:
        change_chart = alt.Chart(change_data).mark_bar().encode(
            x=alt.X("Vehicle_Change:Q", title="Vehicle Change"),
            y=alt.Y("Neighborhood:N", sort="-x", title=""),
            color=alt.Color(
                "Change_Type:N",
                scale=alt.Scale(domain=["Increase", "Decrease"], range=["#00D9FF", "#FF6B9D"]),
                legend=None
            ),
            tooltip=[
                alt.Tooltip("Neighborhood:N"),
                alt.Tooltip("Vehicle_Change:Q", title="Change"),
                alt.Tooltip("Current_Vehicles:Q", format=".1f", title="Current"),
                alt.Tooltip("Recommended_Vehicles:Q", title="Recommended")
            ]
        ).properties(height=400).configure(background='#0e1117').configure_axis(
            labelColor='white',
            titleColor='white',
            gridColor='rgba(128, 128, 128, 0.2)'
        )
        
        st.altair_chart(change_chart, use_container_width=True)
    else:
        st.info("No changes recommended - current allocation is optimal")

with col_viz2:
    st.markdown("#### 🎯 Allocation Score vs Expected Impact")
    
    scatter_chart = alt.Chart(display_df).mark_circle(size=200, opacity=0.8).encode(
        x=alt.X("Allocation_Score:Q", title="Allocation Score", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("Expected_New_Rides:Q", title="Expected New Rides"),
        color=alt.Color(
            "Risk_Category:N",
            scale=alt.Scale(
                domain=["✅ Low Risk", "🟡 Medium Risk", "⚠️ High Risk"],
                range=["#00FF00", "#FFA500", "#FF0000"]
            ),
            legend=alt.Legend(title="Risk Level", titleColor='white', labelColor='white')
        ),
        size=alt.Size("Sessions:Q", scale=alt.Scale(range=[100, 1000]), legend=None),
        tooltip=[
            alt.Tooltip("Neighborhood:N"),
            alt.Tooltip("Allocation_Score:Q", format=".1f", title="Score"),
            alt.Tooltip("Expected_New_Rides:Q", title="Expected Rides"),
            alt.Tooltip("Sessions:Q", title="Total Sessions"),
            alt.Tooltip("Risk_Category:N", title="Risk")
        ]
    ).properties(height=400).configure(background='#0e1117').configure_axis(
        labelColor='white',
        titleColor='white',
        gridColor='rgba(128, 128, 128, 0.2)'
    )
    
    st.altair_chart(scatter_chart, use_container_width=True)

st.markdown("---")

# Action items and insights
st.markdown("#### 🎯 Key Actions Based on Allocation Model")

col_action1, col_action2 = st.columns(2)

with col_action1:
    st.markdown("**🚀 High Priority Actions:**")
    
    high_priority = display_df[
        (display_df["Vehicle_Change"] > 0) & 
        (display_df["Risk_Category"] == "✅ Low Risk")
    ].nlargest(3, "Allocation_Score")
    
    if not high_priority.empty:
        for _, row in high_priority.iterrows():
            st.success(
                f"**{row['Neighborhood']}**: Add {int(row['Vehicle_Change'])} vehicles "
                f"(Expected +{int(row['Expected_New_Rides'])} rides, Score: {row['Allocation_Score']:.1f})"
            )
    else:
        st.info("No high-confidence expansion opportunities identified")

with col_action2:
    st.markdown("**⚠️ Caution Areas:**")
    
    caution_areas = display_df[
        (display_df["Risk_Category"].isin(["⚠️ High Risk", "🟡 Medium Risk"])) &
        (display_df["Vehicle_Change"] > 0)
    ].nlargest(3, "Vehicle_Change")
    
    if not caution_areas.empty:
        for _, row in caution_areas.iterrows():
            st.warning(
                f"**{row['Neighborhood']}**: Model suggests +{int(row['Vehicle_Change'])} vehicles "
                f"but {row['Risk_Category']} (Fulfillment: {row['Fulfillment_Rate_Pct']:.1f}%)"
            )
        st.caption("💡 Investigate why these neighborhoods underperform before adding vehicles")
    else:
        st.success("All recommendations are low-risk!")

# Methodology explanation
with st.expander("🔍 How the Allocation Model Works"):
    st.markdown("""
    ### Allocation Algorithm Methodology
    
    The model uses a **multi-factor scoring system** to recommend optimal vehicle distribution:
    
    #### Scoring Components (Total: 100 points)
    
    1. **Demand Score (40 points)**
       - Raw session volume
       - Higher demand = higher priority
    
    2. **Reliability Score (25 points)**
       - Historical fulfillment rate
       - Neighborhoods below confidence threshold get 50% penalty
       - **Prevents over-allocating to unreliable areas**
    
    3. **Unmet Demand (20 points)**
       - Total missed opportunities
       - Actual unfulfilled demand
    
    4. **Growth Potential (15 points)**
       - Demand density + reliability
       - High sessions per vehicle + decent fulfillment = likely to benefit from more scooters
       - **Identifies neighborhoods that will actually use additional vehicles**
    
    #### Risk Categories
    
    - **✅ Low Risk**: Fulfillment ≥ {confidence_threshold}% and efficiency ≥ 2 rides/vehicle
    - **🟡 Medium Risk**: Low efficiency but acceptable fulfillment
    - **⚠️ High Risk**: Fulfillment < {confidence_threshold}% (investigate before adding vehicles)
    
    #### Why This Prevents False Positives
    
    A neighborhood might look great with:
    - Few vehicles (say 3)
    - High utilization (9 rides/vehicle)
    - Good RPDPV
    
    **BUT** if they only have 50% fulfillment, the model recognizes this is **unreliable performance**.
    
    The algorithm will either:
    - Give them fewer additional vehicles than pure demand would suggest
    - Flag them as high-risk for investigation
    
    This prevents wasting vehicles in areas with underlying issues (poor placement, low awareness, infrastructure problems, etc.)
    """)

st.markdown("---")

# Time-based allocation comparison
st.markdown("#### ⏰ Allocation Needs Across Time Periods")
st.caption("Compare how vehicle needs shift throughout the day")

# Calculate allocation for all time periods
all_time_allocations = []

for time_val in time_options:
    period_subset = alloc_agg_df[alloc_agg_df[time_dim_alloc] == time_val].copy()
    
    if not period_subset.empty:
        period_subset["Demand_Score"] = period_subset["Sessions"]
        period_subset["Reliability_Score"] = np.where(
            period_subset["Neighborhood Fulfillment Rate"] >= (confidence_threshold/100),
            period_subset["Neighborhood Fulfillment Rate"] * 100,
            period_subset["Neighborhood Fulfillment Rate"] * 50
        )
        period_subset["Unmet_Demand"] = period_subset["Missed Opportunity"]
        period_subset["Demand_Density"] = np.where(
            period_subset["Active (Avg)"] > 0,
            period_subset["Sessions"] / period_subset["Active (Avg)"],
            period_subset["Sessions"]
        )
        period_subset["Growth_Potential"] = np.where(
            (period_subset["Demand_Density"] > period_subset["Demand_Density"].median()) &
            (period_subset["Neighborhood Fulfillment Rate"] >= (confidence_threshold/100)),
            period_subset["Unmet_Demand"] * 1.5,
            period_subset["Unmet_Demand"]
        )
        period_subset["Allocation_Score"] = (
            (period_subset["Demand_Score"] / period_subset["Demand_Score"].max() * 40) +
            (period_subset["Reliability_Score"] / 100 * 25) +
            (period_subset["Unmet_Demand"] / period_subset["Unmet_Demand"].max() * 20) +
            (period_subset["Growth_Potential"] / period_subset["Growth_Potential"].max() * 15)
        )
        
        total_score = period_subset["Allocation_Score"].sum()
        period_subset["Recommended_Vehicles"] = np.floor(
            (period_subset["Allocation_Score"] / total_score) * total_fleet_size
        ).astype(int)
        
        period_subset["Time_Period"] = time_val
        all_time_allocations.append(period_subset[["Neighborhood", "Time_Period", "Recommended_Vehicles"]])

if all_time_allocations:
    all_time_df = pd.concat(all_time_allocations, ignore_index=True)
    
    # Create heatmap of recommendations across time
    heatmap_chart = alt.Chart(all_time_df).mark_rect(stroke='#1a1a1a', strokeWidth=2).encode(
        x=alt.X(
            "Time_Period:O",
            title="Time Period",
            sort=time_options,
            axis=alt.Axis(labelAngle=-45, labelFontSize=12, labelColor='white', titleColor='white')
        ),
        y=alt.Y(
            "Neighborhood:O",
            title="Neighborhood",
            axis=alt.Axis(labelFontSize=12, labelColor='white', titleColor='white')
        ),
        color=alt.Color(
            "Recommended_Vehicles:Q",
            scale=alt.Scale(scheme="blues"),
            legend=alt.Legend(
                title="Recommended Vehicles",
                titleColor='white',
                labelColor='white'
            )
        ),
        tooltip=[
            alt.Tooltip("Neighborhood:N"),
            alt.Tooltip("Time_Period:O", title="Time"),
            alt.Tooltip("Recommended_Vehicles:Q", title="Recommended Vehicles")
        ]
    ).properties(
        height=max(400, len(all_time_df["Neighborhood"].unique()) * 25)
    ).configure(
        background='#0e1117'
    ).configure_view(
        strokeWidth=0
    )
    
    st.altair_chart(heatmap_chart, use_container_width=True)
    st.caption("💡 Darker blue = more vehicles needed. Use this to plan rebalancing throughout the day.")
