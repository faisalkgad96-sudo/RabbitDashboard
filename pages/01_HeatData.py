import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import json
import requests
from io import BytesIO
import datetime # Import datetime for date operations

# 1. Page Config
st.set_page_config(page_title="Neighbourhood Fulfillment Dashboar", layout="wide", page_icon="📊")

# 2. Custom CSS to clean up UI and FIX the metric background
st.markdown("""
<style>
    /* FIX: Removed explicit light background from .stMetric 
    to prevent white background on dark mode.
    The primary fix is added below targeting the deep container.
    */
    .stMetric {
        /* Only keep structural styling, let Streamlit handle the default background color */
        padding: 10px;
        border-radius: 10px;
    }
    
    /* CRITICAL FIX: Target the specific metric container class (emotion cache) 
    and force a dark background color that matches the app's dark theme. 
    This overrides any accidental light styling.
    */
    .st-emotion-cache-1kyxaut { 
        background-color: #262730; /* Dark background color */
        border-radius: 0.5rem; 
        padding: 1rem;
    }

    /* Style for the local radio buttons */
    .stRadio > label {
        padding-right: 15px;
        margin-right: 0px; 
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 Fulfillment Dashboard")

# ------------------------------
# HELPER FUNCTIONS (Cached)
# ------------------------------

@st.cache_data(ttl=3600) # Cache data for 1 hour
def fetch_heat_data(api_token, start_date_str, end_date_str, group_by="neighborhood"):
    """Fetches data from Rabbit API."""
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
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            st.error(f"❌ API Error {response.status_code}: {response.text}")
            return None

        content_type = response.headers.get("Content-Type", "")

        if "application/vnd.openxmlformats" in content_type:
            # Read Excel content from response
            return pd.read_excel(BytesIO(response.content))
        if "csv" in content_type:
            # Read CSV content from response
            return pd.read_csv(BytesIO(response.content))
        
        # Assume JSON if no specific file type is identified
        return pd.DataFrame(response.json())
        
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return None

def get_time_interval(hour):
    """Maps an hour (0-23) to a predefined time interval."""
    # Morning Peak: 6 AM to 11:59 AM (Hours 6 through 11)
    if 6 <= hour <= 11:
        return "Morning Peak (6a-12p)"
    # Afternoon Peak: 12 PM to 5:59 PM (Hours 12 through 17)
    elif 12 <= hour <= 17:
        return "Afternoon Peak (12p-6p)"
    # Evening/Night: 6 PM to 5:59 AM (Hours 18 through 5)
    else:
        return "Evening/Night (6p-6a)"

@st.cache_data(ttl=3600)
def process_data(df):
    """Standardizes column names and parses dates, ensuring DataFrame persistence."""
    
    # Use a deep copy to ensure the function is pure for caching purposes
    df_copy = df.copy() 
    
    df_copy.columns = df_copy.columns.str.strip()
    
    # Check required columns
    required_cols = [
        "Area", "Neighborhood", "Start Date - Local",
        "Sessions", "Rides", "Active Vehicles", "Urgent Vehicles"
    ]
    
    if not all(col in df_copy.columns for col in required_cols):
        st.error(f"❌ Missing columns. Found: {list(df_copy.columns)}")
        return None

    # Date processing
    df_copy["Start Date - Local"] = pd.to_datetime(df_copy["Start Date - Local"], errors="coerce")
    df_copy["_hour"] = df_copy["Start Date - Local"].dt.hour
    df_copy["_date"] = df_copy["Start Date - Local"].dt.date.astype(str)
    
    # Create the time interval column 
    df_copy["_time_interval"] = df_copy["_hour"].apply(get_time_interval)

    return df_copy

def calculate_metrics(df_grouped, time_column):
    """Calculates fulfillment, utilization, and average vehicle metrics for an aggregated dataframe."""
    
    # Group and aggregate base metrics
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
    
    # Averages require dividing by the number of snapshots (unique timestamps)
    agg_df["Active (Avg)"] = np.where(agg_df["Snapshots"] > 0, agg_df["Active Vehicles"] / agg_df["Snapshots"], 0)
    agg_df["Urgent (Avg)"] = np.where(agg_df["Snapshots"] > 0, agg_df["Urgent Vehicles"] / agg_df["Snapshots"], 0)
    
    # Utilization: Rides / Active Vehicle Average
    agg_df["Utilization"] = np.where(agg_df["Active (Avg)"] > 0, agg_df["Rides"] / agg_df["Active (Avg)"], 0)
    agg_df["Utilization"] = agg_df["Utilization"].replace([np.nan, np.inf], 0)
    
    return agg_df

# ------------------------------
# SESSION STATE INITIALIZATION
# ------------------------------
if "data" not in st.session_state:
    st.session_state.data = None

# Set default dates for the input field to prevent initial errors
today = datetime.date.today()
week_ago = today - datetime.timedelta(days=7)

# ------------------------------
# SIDEBAR: DATA SOURCE
# ------------------------------
with st.sidebar:
    st.header("Data Source")
    source_type = st.radio("Choose Source:", ["🔌 Live API", "📂 File Upload"])
    
    # Determine if API token is available from secrets
    api_token = None
    try:
        if "RABBIT_TOKEN" in st.secrets:
            api_token = st.secrets["RABBIT_TOKEN"]
    except Exception:
        # Ignore exception if st.secrets is unavailable
        pass 

    if source_type == "🔌 Live API":
        
        # --- START DATE AND END DATE INPUTS ---
        start_d = st.date_input("Start Date", value=week_ago, key="start_d")
        end_d = st.date_input("End Date", value=today, key="end_d")
        
        if api_token is None:
            # If token is NOT in secrets, ask the user for it
            st.caption("Token not found in `secrets.toml`. Please enter manually.")
            api_token = st.text_input("API Token", value="", type="password", key="manual_token_input")
            
            if st.button("Fetch Live Data", type="primary"):
                if not api_token:
                    st.warning("Please enter an API Token.")
                else:
                    with st.spinner("Fetching and processing data..."):
                        # Fetch raw data using cached function
                        raw_df = fetch_heat_data(
                            api_token, 
                            f"{start_d}T00:00:00.000Z", 
                            f"{end_d}T23:59:00.000Z"
                        )
                        if raw_df is not None and not raw_df.empty:
                            # Process data using cached function
                            st.session_state.data = process_data(raw_df)
                            st.success("Data loaded successfully!")
                            st.rerun()
                        elif raw_df is not None and raw_df.empty:
                            st.warning("Data fetched, but it is empty.")
                        
        else:
            # If token IS in secrets, show only the dates and a load button
            st.caption("Using token secured in `secrets.toml`.")
            
            if st.button("Load Data", type="primary"):
                with st.spinner("Fetching and processing data..."):
                    # Fetch raw data using cached function
                    raw_df = fetch_heat_data(
                        api_token, 
                        f"{start_d}T00:00:00.000Z", 
                        f"{end_d}T23:59:00.000Z"
                    )
                    if raw_df is not None and not raw_df.empty:
                        # Process data using cached function
                        st.session_state.data = process_data(raw_df)
                        st.success("Data loaded successfully!")
                        st.rerun()
                    elif raw_df is not None and raw_df.empty:
                        st.warning("Data fetched, but it is empty.")
                        

    else:
        uploaded_file = st.file_uploader("Upload Excel/CSV", type=["xlsx", "xls", "csv"])
        if uploaded_file:
            # Streamlit caches file uploads using a hash of the file content
            # We use the hash as an argument to the cached function to ensure uniqueness
            file_hash = uploaded_file.file_id # This provides a unique ID for the file content
            
            try:
                if uploaded_file.name.endswith(".csv"):
                    raw_df = pd.read_csv(uploaded_file)
                else:
                    raw_df = pd.read_excel(uploaded_file)
                
                # Process data using cached function, passing file_hash to ensure unique cache key
                # Note: We must pass the data frame content to process_data to ensure caching works on the data itself
                @st.cache_data(ttl=3600)
                def process_uploaded_data(df, file_id):
                    return process_data(df)

                st.session_state.data = process_uploaded_data(raw_df, file_hash)
                st.success(f"Loaded {len(raw_df)} rows from file.")
                st.rerun()
                
            except Exception as e:
                st.error(f"Error reading file: {e}")

# ------------------------------
# MAIN DASHBOARD
# ------------------------------

if st.session_state.data is None:
    st.info("👈 Please fetch data via API or upload a file from the sidebar.")
    st.stop()

df = st.session_state.data

# --- Filters ---
st.divider()
c1, c2, c3 = st.columns([1, 2, 1])

areas = sorted(df["Area"].dropna().unique().tolist())
dates = sorted(df["_date"].dropna().unique().tolist())

# --- Set the multiselect default to only the first date found ---
default_selection = dates[0] if dates else []

with c1:
    # Set area default based on what's in the data
    default_area = areas[0] if areas else None
    selected_area = st.selectbox("📍 Select Area", areas, index=areas.index(default_area) if default_area in areas else 0)

with c2:
    selected_dates = st.multiselect("📅 Select Dates", dates, default=[default_selection] if default_selection else [])

# Apply Filters
df_filtered = df[
    (df["Area"] == selected_area) & 
    (df["_date"].isin(selected_dates)) &
    (df["Neighborhood"].str.lower() != "no neighborhood")
]

if df_filtered.empty:
    st.warning("No data available for the selected filters.")
    st.stop()

# ------------------------------------------
# Data Preparation for Charts (Global Aggregation)
# ------------------------------------------

# 1. Aggregation for both modes is done once here.
# These calls will automatically be cached by Streamlit's data cache if they are the same
df_hourly_agg = calculate_metrics(df_filtered, "_hour")
df_interval_agg = calculate_metrics(df_filtered, "_time_interval")

# Define the category order for the interval axis and apply it
interval_order = ["Morning Peak (6a-12p)", "Afternoon Peak (12p-6p)", "Evening/Night (6p-6a)"]
df_interval_agg["_time_interval"] = pd.Categorical(df_interval_agg["_time_interval"], categories=interval_order, ordered=True)

# ------------------------------------------

# --- Scorecard Metric Pre-Calculations (Period-level, always the same) ---
daily_active_avg = df_filtered.groupby(["Neighborhood", "_date"])["Active Vehicles"].mean().reset_index()
daily_active_avg = daily_active_avg.rename(columns={"Active Vehicles": "Daily Active Avg"})
period_active_avg = daily_active_avg.groupby("Neighborhood")["Daily Active Avg"].mean().reset_index()
period_active_avg = period_active_avg.rename(columns={"Daily Active Avg": "Active (Avg)"})
total_avg_active_scooters = period_active_avg["Active (Avg)"].sum()
# --- End Scorecard Metric Pre-Calculations ---


# Add a download button for the currently selected aggregated data
st.download_button(
    label=f"⬇️ Download Hourly Data (CSV)",
    data=df_hourly_agg.to_csv(index=False).encode('utf-8'),
    file_name=f'hourly_heatmap_data_{selected_area}_{len(selected_dates)}_days.csv',
    mime='text/csv',
    key='download_hourly_data'
)
st.download_button(
    label=f"⬇️ Download Interval Data (CSV)",
    data=df_interval_agg.to_csv(index=False).encode('utf-8'),
    file_name=f'interval_heatmap_data_{selected_area}_{len(selected_dates)}_days.csv',
    mime='text/csv',
    key='download_interval_data'
)

st.markdown("---")


# --- Top Level Metrics ---
total_rides = df_filtered["Rides"].sum()
total_sessions = df_filtered["Sessions"].sum()
unique_neighborhoods = df_filtered["Neighborhood"].nunique()
total_missed_opportunity = total_sessions - total_rides 


# Use 5 columns to display all metrics
m1, m2, m3, m4, m5 = st.columns(5) 

m1.metric("Total Rides", f"{total_rides:,}")
m2.metric("Total Sessions", f"{total_sessions:,}")
m3.metric("Avg Active Scooters (Summed Avg)", f"{total_avg_active_scooters:,.1f}") 
m4.metric("Total Missed Opp.", f"{total_missed_opportunity:,}") 
m5.metric("Active Neighborhoods", unique_neighborhoods)

st.markdown("---")

# ==========================================
# 1. NEIGHBORHOOD LEADERBOARD 
# (Always period-level)
# ==========================================
st.subheader("📊 Neighborhood Leaderboard")

# --- RPDPV LOGIC ---
period_summary = df_filtered.groupby("Neighborhood").agg(
    Rides=("Rides", "sum"),
    Sessions=("Sessions", "sum"),
).reset_index()
agg = pd.merge(period_summary, period_active_avg, on="Neighborhood")
num_selected_days = len(df_filtered["_date"].unique())
agg["Rides per Day"] = agg["Rides"] / num_selected_days
agg["RPDPV"] = np.where(agg["Active (Avg)"] > 0, agg["Rides per Day"] / agg["Active (Avg)"], 0)
agg["Missed Opportunity"] = agg["Sessions"] - agg["Rides"]
# --- END RPDPV LOGIC ---

# Interactive Dataframe
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
        "Missed Opportunity": st.column_config.NumberColumn(
            "Missing Opportunity",
            help="Total Sessions minus Total Rides (Absolute Count)",
            format="%d"
        )
    },
    hide_index=True,
    column_order=["Neighborhood", "Rides", "Sessions", "Missed Opportunity", "Rides per Day", "Active (Avg)", "RPDPV"]
)

st.markdown("---")

# ==========================================
# 2. DYNAMIC FULFILLMENT RATE HEATMAP
# ==========================================

# --- Local Granularity Control for Chart 2 ---
c_granularity_2, c_filler_2 = st.columns([1, 3])
with c_granularity_2:
    chart_granularity_2 = st.radio(
        "Chart 2 Granularity", 
        ["Hourly (0-23)", "3 Intervals"], 
        key="granularity_2", 
        index=0,
        horizontal=True
    )
    
# Local dynamic variable definition
is_hourly_2 = chart_granularity_2 == "Hourly (0-23)"
main_agg_df_2 = df_hourly_agg if is_hourly_2 else df_interval_agg
time_dim_2 = "_hour" if is_hourly_2 else "_time_interval"
time_title_2 = "Hour of Day" if is_hourly_2 else "Time Interval"
time_sort_2 = None if is_hourly_2 else interval_order

st.subheader(f"🔥 Fulfillment Heat Map")
st.caption(f"Color is based on the **Fulfillment Rate for each individual neighborhood across the {time_title_2}**. Higher rates (better performance) are lighter (closer to white).")

# Altair Chart - Uses local variables
fulfillment_chart = alt.Chart(main_agg_df_2).mark_rect().encode(
    x=alt.X(f"{time_dim_2}:O", title=time_title_2, sort=time_sort_2), 
    y=alt.Y("Neighborhood:O", title=""),
    # Color scale uses high-contrast red-white ramp (low=dark red, high=white)
    color=alt.Color(
        "Neighborhood Fulfillment Rate:Q", 
        scale=alt.Scale(range=['red', 'white'], reverse=True), 
        title="Fulfillment Rate (%)"
    ),
    tooltip=[
        "Neighborhood", 
        alt.Tooltip(f"{time_dim_2}:O", title=time_title_2),
        alt.Tooltip("Neighborhood Fulfillment Rate:Q", format=".1%", title="Fulfillment Rate"), 
        alt.Tooltip("Missed Opportunity:Q", title="Missed Opportunity (Sessions - Rides)"),
        alt.Tooltip("Rides:Q", title="Rides"), 
        alt.Tooltip("Sessions:Q", title="Sessions"), 
        alt.Tooltip("Urgent (Avg):Q", format=".1f", title="Urgent Vehicles (Avg)"),
        alt.Tooltip("Utilization:Q", format=".2f", title="Rides/Active Vehicle"),
        alt.Tooltip("Active (Avg):Q", format=".1f")
    ]
).properties(height=max(400, len(main_agg_df_2["Neighborhood"].unique()) * 30)) 

st.altair_chart(fulfillment_chart, use_container_width=True)

st.markdown("---")

# ==========================================
# 3. DYNAMIC MISSED OPPORTUNITY HEATMAP
# ==========================================

# --- Local Granularity Control for Chart 3 ---
c_granularity_3, c_filler_3 = st.columns([1, 3])
with c_granularity_3:
    chart_granularity_3 = st.radio(
        "Chart 3 Granularity", 
        ["Hourly (0-23)", "3 Intervals"], 
        key="granularity_3", 
        index=0,
        horizontal=True
    )
    
# Local dynamic variable definition
is_hourly_3 = chart_granularity_3 == "Hourly (0-23)"
main_agg_df_3 = df_hourly_agg if is_hourly_3 else df_interval_agg
time_dim_3 = "_hour" if is_hourly_3 else "_time_interval"
time_title_3 = "Hour of Day" if is_hourly_3 else "Time Interval"
time_sort_3 = None if is_hourly_3 else interval_order

st.subheader(f"💔 Missed Opportunity (Sessions - Rides)")
st.caption(f"Color is based on the **absolute count** of unfulfilled sessions per {time_title_3}. Darker red means **highest** missed opportunities.")

# Altair Chart for Missed Opportunity - Uses local variables
missed_opp_chart = alt.Chart(main_agg_df_3).mark_rect().encode(
    x=alt.X(f"{time_dim_3}:O", title=time_title_3, sort=time_sort_3),
    y=alt.Y("Neighborhood:O", title=""),
    color=alt.Color(
        "Missed Opportunity:Q", 
        scale=alt.Scale(scheme="reds", domainMin=0), 
        title="Absolute Count"
    ),
    tooltip=[
        "Neighborhood", 
        alt.Tooltip(f"{time_dim_3}:O", title=time_title_3),
        alt.Tooltip("Missed Opportunity:Q", title="Missed Opportunity (Sessions - Rides)"), 
        alt.Tooltip("Neighborhood Fulfillment Rate:Q", format=".1%", title="Fulfillment Rate"), 
        alt.Tooltip("Rides:Q", title="Rides"), 
        alt.Tooltip("Sessions:Q", title="Sessions"), 
        alt.Tooltip("Urgent (Avg):Q", format=".1f", title="Urgent Vehicles (Avg)"),
        alt.Tooltip("Active (Avg):Q", format=".1f")
    ]
).properties(height=max(400, len(main_agg_df_3["Neighborhood"].unique()) * 30)) 

st.altair_chart(missed_opp_chart, use_container_width=True)

st.markdown("---")

# ==========================================
# 4. DYNAMIC FULFILLMENT TRENDLINES
# ==========================================

# --- Local Granularity Control for Chart 4 ---
c_granularity_4, c_filler_4 = st.columns([1, 3])
with c_granularity_4:
    chart_granularity_4 = st.radio(
        "Chart 4 Granularity", 
        ["Hourly (0-23)", "3 Intervals"], 
        key="granularity_4", 
        index=0,
        horizontal=True
    )
    
# Local dynamic variable definition
is_hourly_4 = chart_granularity_4 == "Hourly (0-23)"
main_agg_df_4 = df_hourly_agg if is_hourly_4 else df_interval_agg
time_dim_4 = "_hour" if is_hourly_4 else "_time_interval"
time_title_4 = "Hour of Day" if is_hourly_4 else "Time Interval"
time_sort_4 = None if is_hourly_4 else interval_order

st.subheader("📈 Fulfillment Trendlines")
st.caption(f"Tracks the Fulfillment Rate (%) for **each individual neighborhood** across the {time_title_4} dimension.")

# Altair Chart: Multi-line for Fulfillment Rate - Uses local variables
fulfillment_trend_chart = alt.Chart(main_agg_df_4).mark_line(point=True).encode(
    x=alt.X(f"{time_dim_4}:O", title=time_title_4, sort=time_sort_4), 
    y=alt.Y(
        "Neighborhood Fulfillment Rate:Q", 
        title="Fulfillment Rate (%)", 
        axis=alt.Axis(format=".1%")
    ),
    color=alt.Color("Neighborhood:N", title="Neighborhood"),
    tooltip=[
        "Neighborhood", 
        alt.Tooltip(f"{time_dim_4}:O", title=time_title_4),
        alt.Tooltip("Neighborhood Fulfillment Rate:Q", format=".1%", title="Fulfillment Rate"), 
        alt.Tooltip("Rides:Q", title="Rides"), 
        alt.Tooltip("Sessions:Q", title="Sessions"), 
    ]
).properties(height=450)

st.altair_chart(fulfillment_trend_chart, use_container_width=True)


# ==========================================
# 5. DYNAMIC DEMAND CURVE (BOTTOM) - ACCUMULATIVE TREND
# ==========================================

# --- Local Granularity Control for Chart 5 ---
c_granularity_5, c_filler_5 = st.columns([1, 3])
with c_granularity_5:
    chart_granularity_5 = st.radio(
        "Chart 5 Granularity", 
        ["Hourly (0-23)", "3 Intervals"], 
        key="granularity_5", 
        index=0,
        horizontal=True
    )

# Local dynamic variable definition
is_hourly_5 = chart_granularity_5 == "Hourly (0-23)"
main_agg_df_5 = df_hourly_agg if is_hourly_5 else df_interval_agg
time_dim_5 = "_hour" if is_hourly_5 else "_time_interval"
time_title_5 = "Hour of Day" if is_hourly_5 else "Time Interval"
time_sort_5 = None if is_hourly_5 else interval_order
    
st.subheader(f"📈 Accumulative Trend")
st.caption(f"Total Rides and Sessions, plus the **Total Average Urgent Vehicles** across all selected neighborhoods by {time_title_5}.")

# Data prep for multi-line chart - Group by the selected time dimension
dynamic_total = main_agg_df_5.groupby(time_dim_5).agg(
    Rides=("Rides", "sum"),
    Sessions=("Sessions", "sum"),
    Urgent_Vehicles=("Urgent (Avg)", "sum") # Summing the neighborhood-time averages
).reset_index()

# Convert the data to long format for Altair multi-line chart
dynamic_long = dynamic_total.melt(
    id_vars=[time_dim_5],
    value_vars=["Rides", "Sessions", "Urgent_Vehicles"],
    var_name="Metric",
    value_name="Count"
)

# Altair Chart: Multi-line
line = alt.Chart(dynamic_long).mark_line(point=True, interpolate='monotone').encode(
    x=alt.X(f"{time_dim_5}:O", title=time_title_5, sort=time_sort_5), 
    y=alt.Y("Count:Q", title="Total Count"),
    color=alt.Color("Metric:N", title="Metric"),
    tooltip=[time_dim_5, "Metric", alt.Tooltip("Count", format=".1f")] 
).properties(height=350)

st.altair_chart(line, use_container_width=True)
