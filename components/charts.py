import altair as alt
import pandas as pd

def dod_chart(df):
    data = df.groupby('Created Date').size().reset_index(name='records')
    data['Created Date'] = pd.to_datetime(data['Created Date']).dt.date
    chart = alt.Chart(data).mark_bar().encode(
        x=alt.X('Created Date:T', title='Created Date', timeUnit='yearmonthdate'),
        y=alt.Y('records:Q', title='Records')
    ).properties(height=260)
    return chart

def case_reasons_chart(df):
    data = df.groupby('Main Case').size().reset_index(name='count').sort_values('count',ascending=False)
    chart = alt.Chart(data.head(20)).mark_bar().encode(
        x=alt.X('count:Q'),
        y=alt.Y('Main Case:N', sort='-x')
    ).properties(height=260)
    return chart

def area_chart(df):
    data = df.groupby('Area').size().reset_index(name='count').sort_values('count',ascending=False)
    chart = alt.Chart(data.head(20)).mark_bar().encode(
        x=alt.X('count:Q'),
        y=alt.Y('Area:N', sort='-x')
    ).properties(height=260)
    return chart

def dual_line_times(df):
    data = df.groupby('Created Date').agg({'On Queue Time':'mean','Resolution Time':'mean'}).reset_index()
    data['Created Date'] = pd.to_datetime(data['Created Date']).dt.date
    data_m = data.melt(id_vars=['Created Date'], value_vars=['On Queue Time','Resolution Time'], var_name='metric', value_name='value')
    chart = alt.Chart(data_m).mark_line(point=True).encode(
        x=alt.X('Created Date:T', timeUnit='yearmonthdate'),
        y=alt.Y('value:Q'),
        color='metric:N'
    ).properties(height=220)
    return chart

def multi_case_trends(df):
    data = df.groupby(['Created Date','Main Case']).size().reset_index(name='count')
    data['Created Date'] = pd.to_datetime(data['Created Date']).dt.date
    chart = alt.Chart(data).mark_line().encode(
        x=alt.X('Created Date:T', timeUnit='yearmonthdate'),
        y='count:Q',
        color='Main Case:N',
        detail='Main Case:N'
    ).properties(height=220)
    return chart

def interval_heatmap(df):
    data = df.dropna(subset=['Interval','Created Date']).copy()
    data['Interval'] = data['Interval'].astype(int)
    table = data.groupby(['Created Date','Interval']).size().reset_index(name='count')
    table['Created Date'] = pd.to_datetime(table['Created Date']).dt.date
    chart = alt.Chart(table).mark_rect().encode(
        x=alt.X('Interval:O', title='Interval (hour bucket)'),
        y=alt.Y('Created Date:T', title='Date', sort='-x', timeUnit='yearmonthdate'),
        color='count:Q',
        tooltip=['Created Date','Interval','count']
    ).properties(height=200)
    return chart
