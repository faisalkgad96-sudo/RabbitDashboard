import pandas as pd
import numpy as np

def _dedupe_column_labels(columns):
    """Make labels unique so df[col] is a Series (duplicate labels break pd.to_datetime)."""
    counts = {}
    out = []
    for c in columns:
        if c not in counts:
            counts[c] = 0
            out.append(c)
        else:
            counts[c] += 1
            out.append(f"{c}__{counts[c]}")
    return out

def _parse_iso(col):
    # Guard: duplicate column names make df[col] a DataFrame and trip pandas assemble logic.
    if isinstance(col, pd.DataFrame):
        col = col.iloc[:, 0]
    dt = pd.to_datetime(col, utc=True, errors='coerce')
    try:
        return dt.dt.tz_convert(None)
    except Exception:
        return dt

def calculate_interval(created_ts):
    cutoff = pd.Timestamp('2025-04-25')
    ts = pd.Timestamp(created_ts)
    hour = ts.hour
    if ts.normalize() >= cutoff.normalize():
        return hour + 3 if hour < 21 else hour - 21
    else:
        return hour + 2 if hour < 22 else hour - 22

def parse_and_compute_all(df):
    df = df.rename(columns=lambda c: c.strip() if isinstance(c, str) else c)
    rename_map = {
        "First Assigned To Name": "Assigned To Name",
        "First Assigned To At": "Assigned To At",
        "Assigned Count": "Num Of Assignments",
        "Assigned To": "Assigned To Name",
        "Assigned Name": "Assigned To Name"
    }
    df = df.rename(columns=rename_map)
    df.columns = _dedupe_column_labels(list(df.columns))
    for col in ["Assigned To Name","Assigned To At","Num Of Assignments"]:
        if col not in df.columns:
            df[col] = np.nan
    timestamp_cols = ["Created At","Resolved At","Assigned To At","First Pending At","Created At (Local)"]
    for col in timestamp_cols:
        if col in df.columns:
            df[col] = _parse_iso(df[col])
        else:
            df[col] = pd.NaT
    # Use canonical `Created At` (UTC-normalized) for duration-based metrics
    created_for_durations = df["Created At"]

    # Date / interval bucketing always follows local creation time only
    created_for_bucketing = df["Created At (Local)"]

    df['Resolution Time'] = (df['Resolved At'] - created_for_durations).dt.total_seconds() / 60
    df['On Queue Time'] = (df['Assigned To At'] - created_for_durations).dt.total_seconds() / 60
    fp = df['First Pending At'].fillna(df['Resolved At'])
    df['Handling Time'] = (fp - df['Assigned To At']).dt.total_seconds() / 60
    df['Interval'] = created_for_bucketing.apply(lambda x: calculate_interval(x) if pd.notnull(x) else np.nan)
    df['Created Date'] = created_for_bucketing.dt.date
    return df
