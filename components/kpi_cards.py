import streamlit as st
import math
def render_kpis(df):
    k1,k2,k3,k4,k5,k6,k7 = st.columns([1,1,1,1,1,1,1])
    num = int(df.shape[0]) if df is not None else 0
    med_on = df['On Queue Time'].median(skipna=True)
    med_hand = df['Handling Time'].median(skipna=True)
    avg_res = df['Resolution Time'].mean(skipna=True)
    avg_on = df['On Queue Time'].mean(skipna=True)
    avg_hand = df['Handling Time'].mean(skipna=True)
    def fmt(x):
        if x is None or (isinstance(x,float) and (math.isnan(x))):
            return '0'
        try:
            if abs(x) >= 1000:
                return f"{x/1000:.1f}K"
            if isinstance(x, float):
                s = f"{x:.2f}"
                if s.endswith('.00'):
                    s = s[:-3]
                return s
            return str(x)
        except:
            return str(x)
    k1.metric('Num Of Assignments', f"{num}")
    k2.metric('Med On Queue Time (min)', fmt(med_on))
    k3.metric('Med Handling Time (min)', fmt(med_hand))
    k4.metric('Avg Resolution Time (min)', fmt(avg_res))
    k5.metric('Avg On Queue (min)', fmt(avg_on))
    k6.metric('Avg Handling Time (min)', fmt(avg_hand))
    k7.metric('Resolution Time (min)', fmt(avg_res))
