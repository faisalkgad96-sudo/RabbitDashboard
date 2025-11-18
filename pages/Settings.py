import streamlit as st
import pandas as pd
import os

st.set_page_config(layout="wide", page_title="Scorecard Settings")
st.title("⚙️ Scorecard Settings")

SETTINGS_DIR = "settings"
os.makedirs(SETTINGS_DIR, exist_ok=True)

# File paths
W_FILE = os.path.join(SETTINGS_DIR, "order_weights.csv")
C_FILE = os.path.join(SETTINGS_DIR, "case_scores.csv")
M_FILE = os.path.join(SETTINGS_DIR, "mobility.csv")
Q_FILE = os.path.join(SETTINGS_DIR, "quartiles.csv")

# Default values
DEFAULT_WEIGHTS = [1.0, 0.75, 0.5, 0.25, 0.25, 0.25, 0.25]
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
DEFAULT_QUARTILES = pd.DataFrame([
    ["Q1", 6, 26, "Low Performer"],
    ["Q2", 27, 47, "Mid Performer"],
    ["Q3", 48, 68, "Upper-Mid Performer"],
    ["Q4", 69, 90, "High Performer"],
], columns=["quartile", "min", "max", "label"])

# Loaders
def load_weights():
    if os.path.exists(W_FILE):
        try:
            df = pd.read_csv(W_FILE)
            return df["weight"].tolist()
        except:
            pass
    return DEFAULT_WEIGHTS

def load_case_scores():
    if os.path.exists(C_FILE):
        try:
            return pd.read_csv(C_FILE)
        except:
            pass
    rows = []
    for case, vals in DEFAULT_CASE_SCORES.items():
        rows.append([case, vals["moto"], vals["tric"]])
    return pd.DataFrame(rows, columns=["case", "moto", "tric"])

def load_mobility():
    if os.path.exists(M_FILE):
        try:
            return pd.read_csv(M_FILE)
        except:
            pass
    return pd.DataFrame(columns=["name", "mobility"])

def load_quartiles():
    if os.path.exists(Q_FILE):
        try:
            return pd.read_csv(Q_FILE)
        except:
            pass
    return DEFAULT_QUARTILES.copy()

# Load all
weights = load_weights()
case_scores_df = load_case_scores()
mobility_df = load_mobility()
quartiles_df = load_quartiles()

st.markdown("### Order Weights (position-based)")
w_df = pd.DataFrame({"weight": weights})
w_edit = st.data_editor(w_df, num_rows="dynamic", use_container_width=True)
if st.button("💾 Save Order Weights"):
    w_edit.to_csv(W_FILE, index=False)
    st.success("Order weights saved.")

st.markdown("---")
st.markdown("### Case Scores (Moto / Tric)")
case_edit = st.data_editor(case_scores_df, num_rows="dynamic", use_container_width=True)
if st.button("💾 Save Case Scores"):
    case_edit.to_csv(C_FILE, index=False)
    st.success("Case scores saved.")

st.markdown("---")
st.markdown("### Mobility Mapping (Username → Mobility Type)")

# Upload CSV option
uploaded_mobility = st.file_uploader("Upload mobility.csv", type=["csv"])

if uploaded_mobility:
    try:
        mobility_uploaded_df = pd.read_csv(uploaded_mobility)
        mobility_uploaded_df.to_csv(M_FILE, index=False)   # Save immediately
        mobility_df = mobility_uploaded_df.copy()
        st.success("Mobility CSV uploaded and saved successfully.")
    except Exception as e:
        st.error(f"Error reading uploaded file: {e}")

# Editable table
mobility_edit = st.data_editor(mobility_df, num_rows="dynamic", use_container_width=True)

if st.button("💾 Save Mobility Mapping"):
    mobility_edit.to_csv(M_FILE, index=False)
    st.success("Mobility mapping saved.")


st.markdown("---")
st.markdown("### Quartiles (Score Ranges)")
quart_edit = st.data_editor(quartiles_df, num_rows="dynamic", use_container_width=True)
if st.button("💾 Save Quartiles"):
    quart_edit.to_csv(Q_FILE, index=False)
    st.success("Quartiles saved.")

st.markdown("---")
st.success("All settings loaded.")
