import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
from datetime import datetime

# 1. Page Config
st.set_page_config(page_title="Fleet Attendance Dashboard", layout="wide", page_icon="📊")

# 2. Custom CSS to match the dark theme aesthetics
st.markdown("""
<style>
    /* General App styling */
    .stApp {
        background-color: #0e1117;
        color: white;
    }
    
    /* Metric Cards Styling */
    div[data-testid="stMetric"] {
        background-color: #1e2029;
        border: 1px solid #333644;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    div[data-testid="stMetricLabel"] {
        color: #a0aec0;
        font-size: 0.9rem;
    }
    div[data-testid="stMetricValue"] {
        color: white;
        font-size: 2.2rem;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 Attendance View")

# ------------------------------
# DATA LOADING & PROCESSING
# ------------------------------

@st.cache_data(ttl=3600)
def load_data(uploaded_file):
    """Loads and parses the uploaded CSV/Excel file."""
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Numeric columns to enforce (handling potential strings)
        numeric_cols = [
            'Average Shift Active (Fleet)', 
            'Average Shift Urgent (Fleet)', 
            'Average Shift Operating (Fleet)', 
            'Battery Swap Count',
            'Check-in Difference Hours',
            'Check-out Difference Hours',
            'Check-in Overtime Hours',
            'Check-out Overtime Hours',
            'Check-in Permission Hours',
            'Check-out Permission Hours'
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # DateTime conversion for time calculation
        date_cols = ['Check-in Date (Local)', 'Check-out Date (Local)']
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')

        return df
        
    except Exception as e:
        st.error(f"Error parsing file: {e}")
        return pd.DataFrame()

def calculate_metrics(df):
    """Calculates summary metrics from the filtered dataframe."""
    if df.empty:
        return None
        
    # 1. Active Employees (Unique Names present in the list)
    active_employees = df['Name'].nunique()
    
    # 2. Totals
    total_operating_time = df['Average Shift Operating (Fleet)'].sum()
    total_swaps = df['Battery Swap Count'].sum()
    
    # 3. Averages (for the chart and scorecards)
    count = len(df) if len(df) > 0 else 1
    avg_active_time = df['Average Shift Active (Fleet)'].sum() / count
    avg_urgent_time = df['Average Shift Urgent (Fleet)'].sum() / count
    avg_operating_time = df['Average Shift Operating (Fleet)'].sum() / count
    
    avg_idle_time = max(0, avg_operating_time - avg_active_time - avg_urgent_time)

    return {
        "active_employees": active_employees,
        "total_operating_time": total_operating_time,
        "avg_active_time": avg_active_time,
        "total_swaps": int(total_swaps),
        "chart_data": {
            "Active": avg_active_time,
            "Urgent": avg_urgent_time,
            "Idle/Other": avg_idle_time
        }
    }

# ------------------------------
# MAIN APPLICATION LOGIC
# ------------------------------

# 1. File Uploader
uploaded_file = st.file_uploader("Upload Attendance Data", type=['csv', 'xlsx'])

if not uploaded_file:
    st.info("👆 Please upload the attendance data file to proceed.")
    st.stop()

# Load Data
df_raw = load_data(uploaded_file)

if df_raw.empty:
    st.warning("The uploaded file contains no data.")
    st.stop()

# 2. Filters (Area & Search)
st.markdown("### Filters")
col_filter_1, col_filter_2, col_filter_3 = st.columns([1, 1.5, 1])

with col_filter_1:
    # Get unique areas and sort them
    if "Area" in df_raw.columns:
        unique_areas = ["All Areas"] + sorted(df_raw["Area"].astype(str).unique().tolist())
    else:
        unique_areas = ["All Areas"]
        st.warning("Column 'Area' not found in dataset.")
        
    selected_area = st.selectbox("📍 Select Area", unique_areas)

with col_filter_2:
    search_term = st.text_input("🔍 Search Employee Name", "")

with col_filter_3:
    # Toggle for View Mode
    view_mode = st.radio("📅 View Mode", ["Daily (Detailed)", "Monthly (Summed)"], horizontal=True)

# Apply Filters
df_filtered = df_raw.copy()

if selected_area != "All Areas":
    df_filtered = df_filtered[df_filtered["Area"] == selected_area]

if search_term:
    if "Name" in df_filtered.columns:
        df_filtered = df_filtered[df_filtered["Name"].astype(str).str.contains(search_term, case=False)]

# 3. Metrics Calculation
metrics = calculate_metrics(df_filtered)

# 4. Top Scorecards
st.markdown("---")
m1, m2, m3, m4 = st.columns(4)

if metrics:
    m1.metric("Active Employees", metrics["active_employees"])
    m2.metric("Total Operating Time", f"{metrics['total_operating_time']:,.1f} h")
    m3.metric("Avg. Active Time", f"{metrics['avg_active_time']:.2f} h/shift")
    m4.metric("Total Battery Swaps", f"{metrics['total_swaps']:,}")
else:
    st.warning("No data matching filters.")

st.markdown("---")

# 5. Main Content: Attendance Details Grouped by Area
st.subheader(f"Attendance Details ({len(df_filtered)} Records)")

# Determine areas to iterate over
if selected_area != "All Areas":
    areas_to_show = [selected_area]
else:
    if "Area" in df_filtered.columns:
        areas_to_show = sorted(df_filtered["Area"].unique())
    else:
        areas_to_show = []

# Iterate through each area and create an expander
for area in areas_to_show:
    area_df = df_filtered[df_filtered["Area"] == area].copy()
    
    # Skip if empty (though unlikely given filtering)
    if area_df.empty:
        continue
        
    # --- Calculate Derived Columns (IN MINUTES) for ALL rows first ---
    
    # 1. Check In Difference Logic
    # Raw Data: Negative = Late, Positive = Early
    def calculate_check_in_diff(hours_diff):
        if hours_diff >= 0:
            return 0 # Early is ignored
        
        minutes_late = abs(hours_diff) * 60
        
        if minutes_late <= 15:
            return 0 # Grace period
        else:
            return minutes_late # Show total lateness

    area_df['Total Check In Difference'] = area_df['Check-in Difference Hours'].apply(calculate_check_in_diff)
    
    # 2. Check Out Difference Logic
    def calculate_base_check_out_diff(hours_diff):
        # If hours_diff is negative (late/overtime), ignore it
        if hours_diff < 0:
            return 0
        # If positive (early departure), return minutes
        return hours_diff * 60

    base_checkout_diff = area_df['Check-out Difference Hours'].apply(calculate_base_check_out_diff)
    checkout_permission_minutes = area_df['Check-out Permission Hours'] * 60
    area_df['Total Check Out Difference'] = base_checkout_diff + checkout_permission_minutes
    
    # Total Difference sum
    area_df['Total Difference'] = area_df['Total Check In Difference'] + area_df['Total Check Out Difference']
    
    # Overtime Minutes
    area_df['Overtime Minutes'] = (area_df['Check-in Overtime Hours'] + area_df['Check-out Overtime Hours']) * 60
    
    # Permissions in Minutes
    area_df['Total Check In Permission'] = area_df['Check-in Permission Hours'] * 60
    area_df['Total Check Out Permission'] = checkout_permission_minutes
    area_df['Total Permission'] = area_df['Total Check In Permission'] + area_df['Total Check Out Permission']
    
    # 10. Total Time = Total Difference - Total Permission
    area_df['Total Time'] = area_df['Total Difference'] - area_df['Total Permission']
    
    # 11. ADD NEW COLUMNS: Check In Count & Check Out Count
    area_df['Check In Count'] = area_df['Check-in Date (Local)'].notna().astype(int)
    area_df['Check Out Count'] = area_df['Check-out Date (Local)'].notna().astype(int)


    # --- Logic Split based on View Mode ---
    
    if view_mode == "Monthly (Summed)":
        # GROUP BY NAME and SUM everything
        
        agg_dict = {
            'Total Check In Difference': 'sum',
            'Total Check Out Difference': 'sum',
            'Total Difference': 'sum',
            'Overtime Minutes': 'sum', # <-- ADDED FOR AGGREGATION
            'Total Check In Permission': 'sum',
            'Total Check Out Permission': 'sum',
            'Total Permission': 'sum',
            'Total Time': 'sum',
            'Check In Count': 'sum',
            'Check Out Count': 'sum',
        }
        
        # Group and aggregate
        table_df = area_df.groupby('Name').agg(agg_dict).reset_index()
        
        # Select columns for Monthly View (Only 6 core columns + Overtime)
        cols_map = {
            'Name': 'Name',
            'Check In Count': 'Check In Count',
            'Check Out Count': 'Check Out Count',
            'Total Difference': 'Total Diff (min)',
            'Total Permission': 'Total Perm (min)',
            'Overtime Minutes': 'Overtime (min)', # <-- ADDED TO MAP
            'Total Time': 'Total Time (min)',
        }
        
        # Rename columns based on map
        table_df = table_df.rename(columns={k: v for k, v in cols_map.items() if k in table_df.columns})
        
        # Configure columns (No timestamps)
        column_config = {
            "Name": st.column_config.TextColumn("Name", width="medium"),
            "Check In Count": st.column_config.NumberColumn("Check In Count", format="%d"),
            "Check Out Count": st.column_config.NumberColumn("Check Out Count", format="%d"),
            "Total Diff (min)": st.column_config.NumberColumn("Total Diff (min)", format="%d"),
            "Total Perm (min)": st.column_config.NumberColumn("Total Perm (min)", format="%d"),
            "Overtime (min)": st.column_config.NumberColumn("Overtime (min)", format="%d"), # <-- ADDED TO CONFIG
            "Total Time (min)": st.column_config.NumberColumn("Total Time (min)", format="%d"),
        }
        
        # Define final column order (INCLUDES OVERTIME)
        final_column_order = [
            'Name', 'Check In Count', 'Check Out Count', 
            'Total Diff (min)', 'Overtime (min)', 'Total Perm (min)', 'Total Time (min)'
        ]
        
        # Filter table_df and column_config based on final order
        table_df = table_df[[c for c in final_column_order if c in table_df.columns]]
        column_config = {k: v for k, v in column_config.items() if k in final_column_order}

    else:
        # DAILY VIEW (Original Detailed Logic - EXCLUDE Counts)
        
        cols_map = {
            'Name': 'Name',
            'Check-in Date (Local)': 'Check In Time',
            'Check-out Date (Local)': 'Check Out Time',
            'Total Check In Difference': 'Check In Diff (min)',
            'Total Check Out Difference': 'Check Out Diff (min)',
            'Total Difference': 'Total Diff (min)',
            'Overtime Minutes': 'Overtime (min)',
            'Total Check In Permission': 'In Perm (min)',
            'Total Check Out Permission': 'Out Perm (min)',
            'Total Permission': 'Total Perm (min)',
            'Total Time': 'Total Time (min)',
        }
        
        available_cols = [c for c in cols_map.keys() if c in area_df.columns]
        table_df = area_df[available_cols].rename(columns=cols_map)
        
        # Formatting Time
        if 'Check In Time' in table_df.columns:
            table_df['Check In Time'] = table_df['Check In Time'].dt.strftime('%Y-%m-%d %I:%M:%S %p').fillna('-')
        if 'Check Out Time' in table_df.columns:
            table_df['Check Out Time'] = table_df['Check Out Time'].dt.strftime('%Y-%m-%d %I:%M:%S %p').fillna('-')

        column_config = {
            "Name": st.column_config.TextColumn("Name", width="medium"),
            "Check In Time": st.column_config.TextColumn("Check In Time", width="medium"),
            "Check Out Time": st.column_config.TextColumn("Check Out Time", width="medium"),
            "Check In Diff (min)": st.column_config.NumberColumn("Check In Diff (min)", format="%d"),
            "Check Out Diff (min)": st.column_config.NumberColumn("Check Out Diff (min)", format="%d"),
            "Total Diff (min)": st.column_config.NumberColumn("Total Diff (min)", format="%d"),
            "Overtime (min)": st.column_config.NumberColumn("Overtime (min)", format="%d"),
            "In Perm (min)": st.column_config.NumberColumn("In Perm (min)", format="%d"),
            "Out Perm (min)": st.column_config.NumberColumn("Out Perm (min)", format="%d"),
            "Total Perm (min)": st.column_config.NumberColumn("Total Perm (min)", format="%d"),
            "Total Time (min)": st.column_config.NumberColumn("Total Time (min)", format="%d"),
        }
        
        # Define final column order for Daily View
        final_column_order = [
            'Name', 'Check In Time', 'Check Out Time', 
            'Check In Diff (min)', 'Check Out Diff (min)', 'Total Diff (min)', 
            'Overtime (min)', 'In Perm (min)', 'Out Perm (min)', 'Total Perm (min)', 'Total Time (min)'
        ]
        
        table_df = table_df[[c for c in final_column_order if c in table_df.columns]]
        column_config = {k: v for k, v in column_config.items() if k in final_column_order}
    
    # Create expander with count in title
    with st.expander(f"{area} ({len(table_df)} Records)", expanded=False):
        st.dataframe(
            table_df,
            use_container_width=True,
            hide_index=True,
            column_config=column_config
        )