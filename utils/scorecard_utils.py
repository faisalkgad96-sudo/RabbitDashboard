import pandas as pd
import os

# ------------------------------------------------------------
# LOAD CSV HELPERS
# ------------------------------------------------------------

def _safe_read_csv(path):
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


# ------------------------------------------------------------
# ORDER WEIGHTS
# ------------------------------------------------------------
def load_weights(path):
    """
    Load position-based score weights.
    Expected CSV columns: position, weight
    """
    df = _safe_read_csv(path)
    if df is None:
        # default fallback
        return [1.0, 0.75, 0.5, 0.25, 0.25, 0.25]

    df = df.sort_values("position")
    return df["weight"].tolist()


# ------------------------------------------------------------
# CASE SCORES BY MOBILITY
# ------------------------------------------------------------
def load_case_scores(path):
    """
    Load case → score mapping per mobility type.
    Expected CSV:
        case, moto, tric
    """
    df = _safe_read_csv(path)
    if df is None:
        # Default mapping
        return {
            "MOTO": {},
            "TRIC": {},
        }

    df = df.fillna(0)

    # mobility columns = anything except "case"
    mobility_types = [c for c in df.columns if c.lower() != "case"]

    mapping = {}
    for m in mobility_types:
        mapping[m.upper()] = dict(zip(df["case"], df[m]))

    return mapping


# ------------------------------------------------------------
# MOBILITY TABLE
# ------------------------------------------------------------
def load_mobility_table(path):
    """
    Load name → mobility mapping.
    Expected CSV:
        name, mobility
    """
    df = _safe_read_csv(path)
    if df is None:
        return {}

    df["name"] = df["name"].astype(str).str.lower()
    df["mobility"] = df["mobility"].astype(str).str.upper()

    return dict(zip(df["name"], df["mobility"]))


# ------------------------------------------------------------
# SCORE COMPUTATION
# ------------------------------------------------------------
def compute_score_row(row, case_scores, order_weights):
    """
    Compute a score for a single row.
    Row must include:
        row["Cases"]
        row["Mobility"]
    """
    mobility = row.get("Mobility", "MOTO")
    cases_raw = row.get("Cases", "")

    if pd.isna(cases_raw):
        return 0

    # explode comma-separated cases list
    if isinstance(cases_raw, str):
        cases = [c.strip() for c in cases_raw.split(",") if c.strip()]
    elif isinstance(cases_raw, list):
        cases = cases_raw
    else:
        return 0

    weights = order_weights
    m = mobility.upper()
    total = 0

    for idx, case in enumerate(cases):
        w = weights[idx] if idx < len(weights) else weights[-1]
        case_score = case_scores.get(m, {}).get(case, 0)
        total += w * case_score

    return total
