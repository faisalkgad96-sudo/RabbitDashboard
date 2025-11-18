# pages/04_Scorecard_Area.py
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import os

st.set_page_config(layout="wide", page_title="Scorecard — Area View ")
st.title("🏆 Scorecard — Area View ")

# Settings
SETTINGS_DIR = "settings"
WEIGHTS_CSV = os.path.join(SETTINGS_DIR, "order_weights.csv")
CASE_SCORES_CSV = os.path.join(SETTINGS_DIR, "case_scores.csv")
MOBILITY_CSV = os.path.join(SETTINGS_DIR, "mobility.csv")
QUARTILES_CSV = os.path.join(SETTINGS_DIR, "quartiles.csv")

DEFAULT_ORDER_WEIGHTS = [1.0, 0.75, 0.5, 0.25, 0.25, 0.25, 0.25]
DEFAULT_CASE_SCORES = {
    "Low Battery": {"moto": 2, "tric": 0},
    "No Ride Photo": {"moto": 2, "tric": 0},
    "No Rides Today": {"moto": 2, "tric": 0},
    "Not Updating": {"moto": 3, "tric": 0},
    "Out Of Fence": {"moto": 3, "tric": 0},
    "Unlocked Without Ride": {"moto": 3, "tric": 0},
    "Vehicle Battery Unlocked": {"moto": 3, "tric": 0},
    "Vehicle Malfunction": {"moto": 2, "tric": 0},
    "Active": {"moto": 0, "tric": 0},
    "Deactivate": {"moto": 0, "tric": 0},
}
DEFAULT_MOBILITY = {}

# Helpers: settings loaders
def load_order_weights():
    if os.path.exists(WEIGHTS_CSV):
        try:
            df = pd.read_csv(WEIGHTS_CSV)
            if "weight" in df.columns:
                return df["weight"].astype(float).tolist()
            return df.iloc[:, 0].astype(float).tolist()
        except Exception:
            st.warning("Couldn't read order_weights.csv — using defaults.")
    return DEFAULT_ORDER_WEIGHTS


def load_case_scores():
    if os.path.exists(CASE_SCORES_CSV):
        try:
            df = pd.read_csv(CASE_SCORES_CSV)
            d = {}
            for _, r in df.iterrows():
                case = str(r.get("case") or r.get("Case") or r.get("CASE") or "").strip()
                if not case:
                    continue
                moto = r.get("moto", r.get("MOTO", 0))
                tric = r.get("tric", r.get("TRIC", 0))
                try:
                    moto = float(moto)
                except:
                    moto = 0.0
                try:
                    tric = float(tric)
                except:
                    tric = 0.0
                d[case] = {"moto": moto, "tric": tric}
            if d:
                return d
        except Exception:
            st.warning("Couldn't read case_scores.csv — using defaults.")
    return DEFAULT_CASE_SCORES


def load_mobility_map():
    if os.path.exists(MOBILITY_CSV):
        try:
            df = pd.read_csv(MOBILITY_CSV)
            cols_low = [c.lower() for c in df.columns]
            if "name" in cols_low and "mobility" in cols_low:
                name_col = df.columns[cols_low.index("name")]
                mob_col = df.columns[cols_low.index("mobility")]
                return df.set_index(name_col)[mob_col].astype(str).to_dict()
        except Exception:
            st.warning("Couldn't read mobility.csv — using defaults.")
    return DEFAULT_MOBILITY


def get_quartile(score, quartiles_df):
    """Return quartile label for a given score."""
    for _, row in quartiles_df.iterrows():
        try:
            if float(row["min"]) <= float(score) <= float(row["max"]):
                return str(row.get("label", "")).strip()
        except Exception:
            continue
    return "Unassigned"


# Helpers: cleaning & parsing
def clean_text_series(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().str.strip('"').str.strip("'")


def parse_cases_cell(x):
    if pd.isna(x):
        return []
    if isinstance(x, (list, tuple)):
        return [str(i).strip() for i in x if str(i).strip()]
    s = str(x)
    for sep in ["|", ";"]:
        s = s.replace(sep, ",")
    items = [p.strip().strip('"').strip("'") for p in s.split(",") if p.strip()]
    return items


def find_created_column(df: pd.DataFrame):
    if "Created At" in df.columns:
        return "Created At"
    candidates = ["created at", "created_at", "CreatedAt", "created", "Created"]
    cols_lower = {c.lower(): c for c in df.columns}
    if "created at" in cols_lower:
        return cols_lower["created at"]
    for cand in candidates:
        if cand in df.columns:
            return cand
    for c in df.columns:
        if "created" in c.lower() or "date" in c.lower() or "time" in c.lower():
            return c
    return None


def compute_task_score(case_list, mobility_type, case_scores, order_weights):
    if not isinstance(case_list, (list, tuple)):
        return 0.0
    mobility_key = "moto"
    if isinstance(mobility_type, str) and mobility_type.strip().lower().startswith("tr"):
        mobility_key = "tric"
    total = 0.0
    for pos, case_name in enumerate(case_list):
        if not case_name or not str(case_name).strip():
            continue
        weight = order_weights[pos] if pos < len(order_weights) else order_weights[-1]
        key = str(case_name).strip()
        lookup = case_scores.get(key)
        if lookup is None:
            for k in case_scores.keys():
                if k.strip().lower() == key.lower():
                    lookup = case_scores[k]
                    break
        if lookup is None:
            continue
        score_val = lookup.get(mobility_key, 0) or 0
        try:
            total += float(score_val) * float(weight)
        except:
            continue
    return float(total)


# Load settings
order_weights = load_order_weights()
case_scores = load_case_scores()
mobility_map = load_mobility_map()
st.sidebar.info("Settings folder: place order_weights.csv, case_scores.csv, mobility.csv (optional).")

# Load quartiles from settings/quartiles.csv or fallback to defaults
DEFAULT_QUARTILES = pd.DataFrame([
    ["Q1", 6, 26, "Low Performer"],
    ["Q2", 27, 47, "Mid Performer"],
    ["Q3", 48, 68, "Upper-Mid Performer"],
    ["Q4", 69, 90, "High Performer"],
], columns=["quartile", "min", "max", "label"])

if os.path.exists(QUARTILES_CSV):
    try:
        quartiles_df = pd.read_csv(QUARTILES_CSV)
    except:
        quartiles_df = DEFAULT_QUARTILES.copy()
else:
    quartiles_df = DEFAULT_QUARTILES.copy()

# Upload data
uploaded = st.file_uploader("Upload Scorecard Raw Data (.xlsx/.csv)", type=["xlsx", "xls", "csv"])
if not uploaded:
    st.stop()

try:
    if uploaded.name.lower().endswith(".csv"):
        try:
            df_raw = pd.read_csv(uploaded)
        except UnicodeDecodeError:
            uploaded.seek(0)
            df_raw = pd.read_csv(uploaded, encoding="latin1")
    else:
        df_raw = pd.read_excel(uploaded)
except Exception as e:
    st.error(f"Error loading file: {e}")
    st.stop()

st.success(f"Loaded {uploaded.name} — {len(df_raw)} rows")

# Auto-detect core columns
cols_lower = {c.lower(): c for c in df_raw.columns}
agent_col_guess = None
cases_col_guess = None
area_col_guess = None
status_col_guess = None

for cand in ["user name", "user", "username", "agent", "driver name", "full name"]:
    if cand in cols_lower:
        agent_col_guess = cols_lower[cand]
        break
for cand in ["cases at start", "cases", "casesatstart", "cases_at_start"]:
    if cand in cols_lower:
        cases_col_guess = cols_lower[cand]
        break
for cand in ["area", "zone", "location"]:
    if cand in cols_lower:
        area_col_guess = cols_lower[cand]
        break
for cand in ["status", "filter_success", "filtersuccess"]:
    if cand in cols_lower:
        status_col_guess = cols_lower[cand]
        break

# Fallback heuristics
if agent_col_guess is None:
    for c in df_raw.columns:
        if "name" in c.lower() and df_raw[c].astype(str).nunique() > 1:
            agent_col_guess = c
            break
if cases_col_guess is None:
    for c in df_raw.columns:
        if "case" in c.lower() or "cases" in c.lower():
            cases_col_guess = c
            break
if area_col_guess is None:
    for c in df_raw.columns:
        if "area" in c.lower() or "zone" in c.lower():
            area_col_guess = c
            break

if cases_col_guess is None or agent_col_guess is None:
    st.error("Could not detect Agent and/or Cases column automatically. Make sure headers exist.")
    st.stop()

created_col = find_created_column(df_raw)
if created_col is None:
    st.error("Could not detect a date/time column (Created At). Add a 'Created At' column or similar.")
    st.stop()

# Build unique lists for filters (cleaned)
agent_values = clean_text_series(df_raw[agent_col_guess]).replace("", np.nan).dropna().unique().tolist()
agent_values = sorted(agent_values)
area_values = []
if area_col_guess and area_col_guess in df_raw.columns:
    area_values = clean_text_series(df_raw[area_col_guess]).replace("", np.nan).dropna().unique().tolist()
    area_values = sorted(area_values)
cases_all = []
if cases_col_guess in df_raw.columns:
    parsed = df_raw[cases_col_guess].apply(parse_cases_cell).tolist()
    for li in parsed:
        for c in li:
            if c and str(c).strip():
                cases_all.append(str(c).strip())
cases_values = sorted(list(pd.Series(cases_all).dropna().unique())) if cases_all else []

# Main-page filters (single-select)
st.markdown("### Filters")
c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    agent_choice = st.selectbox("Agent (single select)", options=["All"] + agent_values, index=0)
with c2:
    area_choice = st.selectbox("Area (single select)", options=["All"] + area_values if area_values else ["All"], index=0)
with c3:
    case_choice = st.selectbox("Case (single select)", options=["All"] + cases_values if cases_values else ["All"], index=0)

# Preprocess & clean
df = df_raw.copy()
df["_agent_clean"] = clean_text_series(df[agent_col_guess])
df["_area_clean"] = clean_text_series(df[area_col_guess]) if area_col_guess and area_col_guess in df.columns else "Unknown"
df["_cases_list"] = df[cases_col_guess].apply(parse_cases_cell) if cases_col_guess and cases_col_guess in df.columns else [[] for _ in range(len(df))]
df["_created_raw"] = df[created_col]
df["_created_dt"] = pd.to_datetime(df["_created_raw"], errors="coerce")
if df["_created_dt"].isna().all():
    df["_created_dt"] = pd.to_datetime(df["_created_raw"].astype(str).str.slice(0, 19), errors="coerce")
df["_created_day"] = df["_created_dt"].dt.date

status_col = status_col_guess if (status_col_guess and status_col_guess in df.columns) else None
if status_col:
    df["_status_clean"] = clean_text_series(df[status_col]).str.lower()
    df["_is_success"] = df["_status_clean"].isin(["success", "completed", "ok", "done", "true", "1"])
else:
    df["_is_success"] = True

mobility_raw_col = None
for cand in ["vehicle", "mobility", "vehicle type", "vehicle_type"]:
    for c in df.columns:
        if c.lower() == cand:
            mobility_raw_col = c
            break
    if mobility_raw_col:
        break
df["_mobility_raw"] = clean_text_series(df[mobility_raw_col]) if mobility_raw_col else ""
def resolve_mobility_for_row(agent_name, raw_val):
    m = mobility_map.get(agent_name)
    if m:
        mm = str(m).strip().upper()
        if "TRIC" in mm or mm.startswith("TR"):
            return "TRIC"
        return "MOTO"
    v = str(raw_val).upper()
    if "TRIC" in v or "TRI" in v:
        return "TRIC"
    if "MOTO" in v or "MOT" in v or "BIKE" in v:
        return "MOTO"
    return "MOTO"
df["_mobility"] = df.apply(lambda r: resolve_mobility_for_row(r["_agent_clean"], r.get("_mobility_raw", "")), axis=1)

# Filter to successful rows
df_success = df[df["_is_success"]].copy()

# Apply UI filters
if agent_choice != "All":
    df_success = df_success[df_success["_agent_clean"] == agent_choice]
if area_choice != "All":
    df_success = df_success[df_success["_area_clean"] == area_choice]
if case_choice != "All":
    df_success = df_success[df_success["_cases_list"].apply(lambda lst: case_choice in lst)]

# Compute task scores
if not df_success.empty:
    df_success["_task_score"] = df_success.apply(lambda r: compute_task_score(r["_cases_list"], r["_mobility"], case_scores, order_weights), axis=1)
else:
    df_success["_task_score"] = pd.Series(dtype=float)

# Agent & area aggregates (no avg_score column)
if not df_success.empty:
    agent_agg = (
        df_success.groupby(["_area_clean", "_agent_clean"], dropna=False)
        .agg(total_score=pd.NamedAgg(column="_task_score", aggfunc="sum"),
             tasks=pd.NamedAgg(column="_task_score", aggfunc="count"))
        .reset_index()
    )
else:
    agent_agg = pd.DataFrame(columns=["_area_clean", "_agent_clean", "total_score", "tasks"])

if not agent_agg.empty:
    area_agg = (
        agent_agg.groupby("_area_clean", dropna=False)
        .agg(total_score=pd.NamedAgg(column="total_score", aggfunc="sum"),
             successful_tasks=pd.NamedAgg(column="tasks", aggfunc="sum"),
             agents_count=pd.NamedAgg(column="_agent_clean", aggfunc="nunique"),
             )
        .reset_index()
    )
else:
    area_agg = pd.DataFrame(columns=["_area_clean", "total_score", "successful_tasks", "agents_count"])

if not area_agg.empty:
    area_agg = area_agg.sort_values("total_score", ascending=False).reset_index(drop=True)

# TOP KPIs
st.markdown("---")
st.subheader("Area Summary — Overview")

total_score_all = float(area_agg["total_score"].sum()) if not area_agg.empty else 0.0
total_successful_tasks = int(area_agg["successful_tasks"].sum()) if not area_agg.empty else int(len(df_success))
distinct_agents = int(agent_agg["_agent_clean"].nunique()) if not agent_agg.empty else (1 if (agent_choice != "All" and not df_success.empty) else 0)

# Average Score (All Field Techs) calculated from agent_agg within current filters
if not agent_agg.empty:
    avg_all_score = float(agent_agg["total_score"].mean())
else:
    avg_all_score = 0.0

# Top Field Tech
if not agent_agg.empty:
    top_agent_row = agent_agg.sort_values("total_score", ascending=False).iloc[0]
    top_field_tech = top_agent_row["_agent_clean"]
else:
    top_field_tech = "—"

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Score (all areas)", f"{total_score_all:.2f}")
k2.metric("Successful Tasks (filtered)", f"{total_successful_tasks:,}")
k3.metric("Distinct Agents (seen)", f"{distinct_agents:,}")

# Top Field Tech metric (k4) and Average Score (k4_alt)
k4.metric("Top Field Tech", f"{top_field_tech}")

# Insert Average Score metric in the top row (as separate small text under KPIs)
st.markdown(f"<div style='margin-top:8px; font-size:14px'>Average Score (All Field Techs): <strong>{avg_all_score:.2f}</strong></div>", unsafe_allow_html=True)

# CSS to only target the 4th metric to wrap and allow full name
st.markdown(
    """
<style>
div[data-testid="column"]:nth-of-type(4) div[data-testid="stMetricValue"] {
    font-size: 18px !important;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: initial !important;
}
div[data-testid="column"]:nth-of-type(4) div[data-testid="stMetricLabel"] {
    font-size: 12px !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# GLOBAL AREA TIME-SERIES
st.markdown("---")
st.subheader("📈 Area Performance Over Time")
if "_created_day" not in df_success.columns or df_success["_created_day"].isna().all():
    st.info("Created At dates not available or could not be parsed for timeline chart.")
else:
    area_time = df_success.groupby(["_area_clean", "_created_day"])["_task_score"].sum().reset_index()
    area_time = area_time.rename(columns={"_area_clean": "Area", "_created_day": "Day", "_task_score": "TotalScore"})
    if not area_time.empty:
        sel_area = alt.selection_multi(fields=["Area"], bind="legend")
        area_line = (
            alt.Chart(area_time)
            .mark_line(point=True)
            .encode(
                x=alt.X("Day:T", title="Day", axis=alt.Axis(format="%Y-%m-%d")),
                y=alt.Y("TotalScore:Q", title="Total Score"),
                color=alt.Color("Area:N", title="Area"),
                opacity=alt.condition(sel_area, alt.value(1), alt.value(0.15)),
                tooltip=["Area", "Day", "TotalScore"]
            )
            .add_params(sel_area)
            .properties(height=420)
        )
        st.altair_chart(area_line, use_container_width=True)
    else:
        st.info("Not enough area-time data to plot.")

# AREA DETAILS
st.markdown("---")
st.subheader("Area details (expand a section to view agent ranks & charts)")
areas_to_show = area_agg["_area_clean"].tolist() if not area_agg.empty else ([area_choice] if area_choice != "All" else [])
if not areas_to_show:
    st.info("No area details to show for the current filters.")
else:
    for area_name in areas_to_show:
        row = area_agg[area_agg["_area_clean"] == area_name]
        if row.empty:
            df_area = df_success[df_success["_area_clean"] == area_name]
            total_score = df_area["_task_score"].sum() if not df_area.empty else 0.0
            successful_tasks = len(df_area)
            distinct_agents_count = df_area["_agent_clean"].nunique() if not df_area.empty else 0
        else:
            total_score = float(row["total_score"].iat[0])
            successful_tasks = int(row["successful_tasks"].iat[0])
            distinct_agents_count = int(row["agents_count"].iat[0])

        # Average Score (Area) computed from agent_agg for that area
        if not agent_agg.empty and area_name in agent_agg["_area_clean"].values:
            area_agents = agent_agg[agent_agg["_area_clean"] == area_name]
            avg_area_score = float(area_agents["total_score"].mean()) if not area_agents.empty else 0.0
        else:
            avg_area_score = 0.0

        with st.expander(f"{area_name} — Total Score: {total_score:.2f} — Tasks: {successful_tasks} — Agents: {distinct_agents_count}", expanded=False):
            a1, a2, a3, a4 = st.columns([1, 1, 1, 2])
            a1.metric("Total Score", f"{total_score:.2f}")
            a2.metric("Successful Tasks", f"{successful_tasks:,}")
            a3.metric("Distinct Agents", f"{distinct_agents_count:,}")
            a4.metric("Average Score (Area)", f"{avg_area_score:.2f}")

            # Agent ranking table with quartiles
            agents_in_area = agent_agg[agent_agg["_area_clean"] == area_name].sort_values("total_score", ascending=False)
            if agents_in_area.empty:
                st.info("No agent score data for this area under current filters.")
            else:

                # Build dataframe (Agent, Score, Tasks)
                agents_display = agents_in_area[["_agent_clean", "total_score", "tasks"]].rename(
                    columns={
                        "_agent_clean": "Agent",
                        "total_score": "Score",
                        "tasks": "Tasks",
                    }
                )

                # Clean Agent names
                agents_display["Agent"] = (
                    agents_display["Agent"]
                    .astype(str)
                    .str.strip()
                    .str.strip('"')
                    .str.strip("'")
                )

                # Load quartiles from settings folder
                try:
                    quartiles_df = pd.read_csv(os.path.join("settings", "quartiles.csv"))
                except:
                    quartiles_df = pd.DataFrame([
                        ["Q1", 6, 26, "Low Performer"],
                        ["Q2", 27, 47, "Mid Performer"],
                        ["Q3", 48, 68, "Upper-Mid Performer"],
                        ["Q4", 69, 90, "High Performer"],
                    ], columns=["quartile", "min", "max", "label"])

                # Function to classify quartile
                def get_quartile_label(score):
                    for _, row in quartiles_df.iterrows():
                        try:
                            if float(row["min"]) <= float(score) <= float(row["max"]):
                                return row.get("quartile", "") + " – " + str(row.get("label", ""))
                        except:
                            continue
                    return "Unassigned"

                # Add Quartile column
                agents_display["Quartile"] = agents_display["Score"].apply(get_quartile_label)

                # Reset index for display and hide index
                agents_display = agents_display.reset_index(drop=True)

                # Show table
                st.markdown("**Agent Ranking**")
                st.dataframe(
                    agents_display.style.format({"Score": "{:.2f}"}),
                    use_container_width=True,
                    height=280,
                    hide_index=True
                )

                # Agent bars
                st.markdown("**Agent Scores (bars)**")
                bar_df = agents_display.copy()

                if not bar_df.empty:
                    bar_chart = (
                        alt.Chart(bar_df)
                        .mark_bar()
                        .encode(
                            x=alt.X("Score:Q"),
                            y=alt.Y("Agent:N", sort="-x"),
                            color=alt.Color("Quartile:N", legend=alt.Legend(title="Quartile")),
                            tooltip=["Agent", "Score", "Tasks", "Quartile"]
                        )
                        .properties(height=min(300, 40 + 25 * len(bar_df)))
                    )
                    st.altair_chart(bar_chart, use_container_width=True)

            # Case mix pie
            st.markdown("**Case Mix (this area's successful tasks)**")
            df_area_tasks = df_success[df_success["_area_clean"] == area_name]
            all_cases = []
            for li in df_area_tasks["_cases_list"].tolist():
                all_cases.extend([c for c in li if c])
            if all_cases:
                case_counts = pd.Series(all_cases).value_counts().reset_index()
                case_counts.columns = ["Case", "Count"]
                pie = (
                    alt.Chart(case_counts)
                    .mark_arc()
                    .encode(theta=alt.Theta("Count:Q"), color=alt.Color("Case:N"), tooltip=["Case", "Count"])
                    .properties(height=300)
                )
                st.altair_chart(pie, use_container_width=True)
            else:
                st.info("No cases found for this area under current filters.")

            # Per-area agent time-series
            st.markdown("**📈 Agent Performance Over Time**")
            df_area_ts = df_success[df_success["_area_clean"] == area_name].copy()
            if ("_created_day" in df_area_ts.columns) and (not df_area_ts["_created_day"].isna().all()):
                agent_time = df_area_ts.groupby(["_agent_clean", "_created_day"])["_task_score"].sum().reset_index()
                agent_time = agent_time.rename(columns={"_agent_clean": "Agent", "_created_day": "Day", "_task_score": "TotalScore"})
                if not agent_time.empty:
                    sel_agent = alt.selection_multi(fields=["Agent"], bind="legend")
                    agent_line = (
                        alt.Chart(agent_time)
                        .mark_line(point=True)
                        .encode(
                            x=alt.X("Day:T", title="Day", axis=alt.Axis(format="%Y-%m-%d")),
                            y=alt.Y("TotalScore:Q", title="Total Score"),
                            color=alt.Color("Agent:N", title="Agent"),
                            opacity=alt.condition(sel_agent, alt.value(1), alt.value(0.15)),
                            tooltip=["Agent", "Day", "TotalScore"]
                        )
                        .add_params(sel_agent)
                        .properties(height=360)
                    )
                    st.altair_chart(agent_line, use_container_width=True)
                else:
                    st.info("Not enough agent time-series data for this area.")
            else:
                st.info("Created At dates not available or could not be parsed for agent timeline.")

            st.markdown("---")

# Downloads
st.markdown("---")
st.subheader("Download aggregated results (filtered)")
col_d1, col_d2 = st.columns(2)
with col_d1:
    csv_area = area_agg.to_csv(index=False).encode("utf-8")
    st.download_button("Download area_aggregates.csv", csv_area, file_name="area_aggregates.csv", mime="text/csv")
with col_d2:
    csv_agent = agent_agg.to_csv(index=False).encode("utf-8")
    st.download_button("Download agent_aggregates.csv", csv_agent, file_name="agent_aggregates.csv", mime="text/csv")

st.success("Area View ready.")
