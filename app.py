import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.express as px
from datetime import timedelta
import os

st.set_page_config(page_title="Performance Analytics", layout="wide")

st.title("Performance Analytics")
st.write("Upload an Excel file containing return data and benchmark data. Only new incremental information will be added to the database.")

# Ensure data directory exists
os.makedirs('data', exist_ok=True)
db_path = 'data/performance_data.db'

# Helper function for CSV downloads
@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=True).encode('utf-8')

# --- Database Management ---
with st.sidebar:
    st.header("Database Settings")
    if st.button("Clear Database", type="primary"):
        try:
            clear_conn = sqlite3.connect(db_path)
            cursor = clear_conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS funds")
            cursor.execute("DROP TABLE IF EXISTS benchmarks")
            cursor.execute("DROP TABLE IF EXISTS risk_free")
            cursor.execute("DROP TABLE IF EXISTS exposures")
            clear_conn.commit()
            clear_conn.close()
            
            if "uploaded_data" in st.session_state:
                del st.session_state["uploaded_data"]
                
            st.success("Database successfully cleared!")
            st.rerun()
        except Exception as e:
            st.error(f"Error clearing database: {e}")

# --- File Upload & Processing ---
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx", "xls"])

conn = sqlite3.connect(db_path)

def update_db_table(df_new, table_name, connection):
    df_new.index.name = 'Date'
    try:
        df_existing = pd.read_sql(f"SELECT * FROM {table_name}", connection, index_col='Date', parse_dates=['Date'])
        df_existing.index = pd.to_datetime(df_existing.index).normalize()
        df_final = df_new.combine_first(df_existing)
    except Exception:
        df_final = df_new
    df_final.to_sql(table_name, connection, if_exists='replace', index=True)

if uploaded_file is not None and "uploaded_data" not in st.session_state:
    try:
        xl = pd.ExcelFile(uploaded_file)
        
        returns_sheet = None
        bm_sheet = None
        rf_sheet = None
        exp_sheet = None
        
        for sheet in xl.sheet_names:
            if 'return' in sheet.lower():
                returns_sheet = sheet
            elif 'bm' in sheet.lower() or 'benchmark' in sheet.lower():
                bm_sheet = sheet
            elif 'rf' in sheet.lower() or 'risk free' in sheet.lower() or 'risk-free' in sheet.lower():
                rf_sheet = sheet
            elif 'exp' in sheet.lower() or 'exposure' in sheet.lower():
                exp_sheet = sheet
                
        if not returns_sheet or not bm_sheet:
            st.error("Could not find required sheets. Please ensure one sheet contains 'Returns' and another 'BM' or 'Benchmark' in their names.")
        else:
            df_returns = pd.read_excel(uploaded_file, sheet_name=returns_sheet, index_col=0, parse_dates=True)
            df_bm = pd.read_excel(uploaded_file, sheet_name=bm_sheet, index_col=0, parse_dates=True)
            
            df_returns.index = pd.to_datetime(df_returns.index).normalize()
            df_bm.index = pd.to_datetime(df_bm.index).normalize()
            
            update_db_table(df_returns, 'funds', conn)
            update_db_table(df_bm, 'benchmarks', conn)
            
            if rf_sheet:
                df_rf = pd.read_excel(uploaded_file, sheet_name=rf_sheet, index_col=0, parse_dates=True)
                df_rf.index = pd.to_datetime(df_rf.index).normalize()
                update_db_table(df_rf, 'risk_free', conn)

            if exp_sheet:
                df_exp = pd.read_excel(uploaded_file, sheet_name=exp_sheet, index_col=0, parse_dates=True)
                df_exp.index = pd.to_datetime(df_exp.index).normalize()
                update_db_table(df_exp, 'exposures', conn)
                
            st.session_state["uploaded_data"] = True
            st.success("Data successfully uploaded and categorized into the database!")
            
    except Exception as e:
        st.error(f"Error processing file: {e}")

# --- Analysis & Visualization ---
st.header("Performance Metrics")

try:
    try:
        df_funds = pd.read_sql("SELECT * FROM funds", conn, index_col='Date', parse_dates=['Date'])
        fund_cols = df_funds.columns.tolist()
    except Exception:
        df_funds = pd.DataFrame()
        fund_cols = []
        
    try:
        df_bms = pd.read_sql("SELECT * FROM benchmarks", conn, index_col='Date', parse_dates=['Date'])
        bm_cols = df_bms.columns.tolist()
    except Exception:
        df_bms = pd.DataFrame()
        bm_cols = []
        
    try:
        df_rfs = pd.read_sql("SELECT * FROM risk_free", conn, index_col='Date', parse_dates=['Date'])
        rf_cols = df_rfs.columns.tolist()
    except Exception:
        df_rfs = pd.DataFrame()
        rf_cols = []

    if df_funds.empty and df_bms.empty:
        st.info("No data available yet. Please upload an Excel file.")
        st.stop()

    df_merged = df_funds.copy()
    if not df_bms.empty:
        df_merged = df_merged.join(df_bms, how='outer')
    if not df_rfs.empty:
        df_merged = df_merged.join(df_rfs, how='outer')
        
    df_merged.index = pd.to_datetime(df_merged.index)
    df_merged = df_merged.sort_index()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_funds = st.multiselect("Select Funds to Analyze", options=fund_cols, default=[])
    with col2:
        selected_bms = st.multiselect("Select Benchmarks to Analyze", options=bm_cols, default=[])
    with col3:
        rf_options = ["None"] + rf_cols
        selected_rf = st.selectbox("Select Risk Free Rate", options=rf_options, index=0)
        
    selected_rf = None if selected_rf == "None" else selected_rf

    # Set up Top-Level Tabs
    tab_metrics, tab_growth, tab_risk, tab_exposures = st.tabs(["Metrics", "Growth & Drawdown", "Risk & Distribution", "Exposures"])

    if selected_funds or selected_bms:
        def determine_frequency(series):
            s_clean = series.dropna()
            if len(s_clean) < 2: return 'Monthly', 12
            median_days = s_clean.index.to_series().diff().dt.days.median()
            if median_days <= 5: return 'Daily', 252
            elif median_days <= 10: return 'Weekly', 52
            elif median_days <= 31: return 'Monthly', 12
            else: return 'Yearly', 1
        
        def calc_metrics(series, freq_factor, period_months=None, rf_series=None, bm_series=None):
            s = series.dropna()
            if period_months is not None:
                end_date = s.index[-1]
                if period_months == 'YTD':
                    start_date = pd.to_datetime(f"{end_date.year}-12-31") - pd.DateOffset(years=1)
                    s = s[s.index > start_date]
                    if len(s) < 1: return pd.Series(dtype='float64')
                else:
                    start_date = end_date - pd.DateOffset(months=period_months)
                    s = s[s.index >= start_date]
                    if len(s) < 2 or (end_date - s.index[0]).days < (period_months * 30 * 0.9): 
                         return pd.Series(dtype='float64')

            if s.empty: return pd.Series(dtype='float64')
            
            years = (s.index[-1] - s.index[0]).days / 365.25
            ann_ret = (1 + (1+s).cumprod().iloc[-1] - 1) ** (1/years) - 1 if years > 0 else np.nan
            vol = s.std() * np.sqrt(freq_factor)
            
            neg_returns = s[s < 0]
            downside_vol = np.sqrt((neg_returns**2).sum() / len(s)) * np.sqrt(freq_factor) if not neg_returns.empty else 0.0

            cum_ret = (1 + s).cumprod()
            peak = cum_ret.cummax()
            drawdown = (cum_ret - peak) / peak
            max_drawdown = drawdown.min()
            
            dd_end = drawdown.idxmin()
            if pd.notna(dd_end):
                dd_start = peak.loc[:dd_end].idxmax()
                recovery_df = drawdown.loc[dd_end:]
                recovery_dates = recovery_df[recovery_df == 0].index
                dd_recovery = recovery_dates[0] if len(recovery_dates) > 0 else pd.NaT
                dd_length = (dd_recovery - dd_start).days if pd.notna(dd_recovery) else (s.index[-1] - dd_start).days
            else:
                dd_start, dd_recovery, dd_length = pd.NaT, pd.NaT, np.nan
            
            sharpe = np.nan
            if rf_series is not None:
                 rf_s = rf_series.reindex(s.index).ffill().fillna(0)
                 rf_period_rate = rf_s.shift(1) / freq_factor
                 rf_period_rate.iloc[0] = rf_s.iloc[0] / freq_factor
                 ex_ret = s - rf_period_rate
                 sharpe = (ex_ret.mean() / ex_ret.std()) * np.sqrt(freq_factor) if ex_ret.std() != 0 else np.nan
            else:
                 sharpe = (s.mean() / s.std()) * np.sqrt(freq_factor) if s.std() != 0 else np.nan

            up_cap, down_cap, cap_ratio, beta, alpha, tracking_error, info_ratio, corr_falling = [np.nan]*8
            var_alpha = 0.05
            var_val = np.percentile(s, var_alpha * 100) if not s.empty else np.nan
            cvar_val = s[s <= var_val].mean() if pd.notna(var_val) and len(s[s <= var_val]) > 0 else np.nan

            if bm_series is not None:
                bm_s = bm_series.reindex(s.index).dropna()
                if not bm_s.empty:
                    common_idx = s.index.intersection(bm_s.index)
                    s_aligned, bm_aligned = s.loc[common_idx], bm_s.loc[common_idx]
                    up_months, down_months = bm_aligned > 0, bm_aligned <= 0
                    
                    if up_months.sum() > 0:
                        count_up = up_months.sum()
                        s_up_ret = (1 + s_aligned[up_months]).prod() ** (freq_factor / count_up) - 1
                        bm_up_ret = (1 + bm_aligned[up_months]).prod() ** (freq_factor / count_up) - 1
                        up_cap = s_up_ret / bm_up_ret if bm_up_ret != 0 else np.nan
                        
                    if down_months.sum() > 0:
                        count_down = down_months.sum()
                        s_down_ret = (1 + s_aligned[down_months]).prod() ** (freq_factor / count_down) - 1
                        bm_down_ret = (1 + bm_aligned[down_months]).prod() ** (freq_factor / count_down) - 1
                        down_cap = s_down_ret / bm_down_ret if bm_down_ret != 0 else np.nan
                        
                    if pd.notna(up_cap) and pd.notna(down_cap) and down_cap != 0:
                         cap_ratio = up_cap / np.abs(down_cap)
                         
                    active_returns = s_aligned - bm_aligned
                    tracking_error = active_returns.std() * np.sqrt(freq_factor)
                    annualized_active = active_returns.mean() * freq_factor
                    info_ratio = annualized_active / tracking_error if tracking_error != 0 else np.nan

                    if rf_series is not None:
                        rf_aligned = rf_period_rate.loc[common_idx].fillna(0)
                        s_adj, bm_adj = s_aligned - rf_aligned, bm_aligned - rf_aligned
                    else:
                        s_adj, bm_adj = s_aligned, bm_aligned
                        
                    cov_matrix = np.cov(s_adj, bm_adj)
                    if cov_matrix[1, 1] != 0:
                        beta = cov_matrix[0, 1] / cov_matrix[1, 1]
                        alpha = (s_adj.mean() - beta * bm_adj.mean()) * freq_factor

                    falling_idx = bm_aligned[bm_aligned < 0].index
                    if len(falling_idx) >= 2: corr_falling = s_aligned.loc[falling_idx].corr(bm_aligned.loc[falling_idx])

            return pd.Series({
                'Annualized Return': ann_ret, 'Volatility (Ann.)': vol, 'Downside Vol (Ann.)': downside_vol,
                'Max Drawdown': max_drawdown, 'Drawdown Start': dd_start.strftime('%Y-%m-%d') if pd.notna(dd_start) else 'N/A',
                'Drawdown End': dd_end.strftime('%Y-%m-%d') if pd.notna(dd_end) else 'N/A',
                'Drawdown Length (Days)': dd_length, 'Sharpe Ratio': sharpe, 'Value at Risk (5%)': var_val,
                'Conditional VaR (5%)': cvar_val, 'Beta': beta, 'Alpha (Ann.)': alpha, 'Tracking Error': tracking_error,
                'Information Ratio': info_ratio, 'Upside Capture': up_cap, 'Downside Capture': down_cap,
                'Capture Ratio': cap_ratio, 'Corr in Down Markets': corr_falling
            })
            
        def generate_metrics_df(period_months):
            metrics_list = []
            primary_bm = selected_bms[0] if selected_bms else None
            rf_series = df_merged[selected_rf] if selected_rf else None
            cols_to_analyze = selected_funds + selected_bms
            
            for col in cols_to_analyze:
                if df_merged[col].dropna().empty: continue
                freq_name, ann_factor = determine_frequency(df_merged[col])
                bm_series = df_merged[primary_bm] if primary_bm and col != primary_bm and primary_bm in df_merged.columns else None
                res = calc_metrics(df_merged[col], ann_factor, period_months, rf_series=rf_series, bm_series=bm_series)
                if not res.empty:
                    res.name = col
                    metrics_list.append(res)
                
            if not metrics_list: return None
            metrics_df = pd.DataFrame(metrics_list)
            
            def format_pct(x): return f"{float(x)*100:.2f}%" if pd.notnull(x) else "N/A"
            def format_dec(x): return f"{float(x):.2f}" if pd.notnull(x) else "N/A"

            pct_cols = ['Annualized Return', 'Volatility (Ann.)', 'Downside Vol (Ann.)', 'Max Drawdown', 'Value at Risk (5%)', 'Conditional VaR (5%)', 'Alpha (Ann.)', 'Tracking Error']
            for c in pct_cols:
                if c in metrics_df.columns: metrics_df[c] = metrics_df[c].apply(format_pct)
            
            dec_cols = ['Sharpe Ratio', 'Beta', 'Information Ratio', 'Upside Capture', 'Downside Capture', 'Capture Ratio', 'Corr in Down Markets', 'Drawdown Length (Days)']
            for c in dec_cols:
                if c in metrics_df.columns: metrics_df[c] = metrics_df[c].apply(format_dec)
                    
            return metrics_df

        with tab_metrics:
            time_horizon = st.radio(
                "Select Time Horizon",
                ["YTD", "1 Year", "3 Year", "5 Year", "10 Year", "ITD"],
                horizontal=True
            )

            if time_horizon == "YTD":
                df_metrics = generate_metrics_df('YTD')
                dl_key = "dl_ytd"
            elif time_horizon == "1 Year":
                df_metrics = generate_metrics_df(12)
                dl_key = "dl_1y"
            elif time_horizon == "3 Year":
                df_metrics = generate_metrics_df(36)
                dl_key = "dl_3y"
            elif time_horizon == "5 Year":
                df_metrics = generate_metrics_df(60)
                dl_key = "dl_5y"
            elif time_horizon == "10 Year":
                df_metrics = generate_metrics_df(120)
                dl_key = "dl_10y"
            else: # ITD
                df_metrics = generate_metrics_df(None)
                dl_key = "dl_itd"

            if df_metrics is not None and not df_metrics.empty:
                st.dataframe(df_metrics, use_container_width=True)
                st.download_button(
                    f"Download {time_horizon} Metrics",
                    convert_df_to_csv(df_metrics),
                    f"metrics_{time_horizon.replace(' ', '_').lower()}.csv",
                    "text/csv",
                    key=dl_key
                )
            else:
                st.info(f"Not enough data for {time_horizon} analysis.")

        with tab_growth:
            # --- Interactive Charting Section ---
            st.subheader("Interactive Charts")
            
            valid_dates = df_merged[selected_funds + selected_bms].dropna(how='all').index
            
            if not valid_dates.empty:
                min_date = valid_dates.min().to_pydatetime()
                max_date = valid_dates.max().to_pydatetime()

                start_date, end_date = st.slider(
                    "Select Date Range for Charts",
                    min_value=min_date, max_value=max_date, value=(min_date, max_date), format="YYYY-MM-DD", key="growth_slider"
                )

                mask = (df_merged.index >= pd.to_datetime(start_date)) & (df_merged.index <= pd.to_datetime(end_date))
                df_charting = df_merged.loc[mask]
            else:
                df_charting = df_merged.copy()

            # Cumulative Growth Chart (Base 100)
            index_df = pd.DataFrame(index=df_charting.index)
            cols_to_plot = selected_funds + selected_bms
            
            for col in cols_to_plot:
                s = df_charting[col].dropna()
                if not s.empty:
                    index_df[col] = 100 * (1 + s).cumprod()

            if not index_df.empty:
                index_df = index_df.ffill()
                plot_idx_df = index_df.reset_index().melt(id_vars='Date', var_name='Asset', value_name='Index Value')
                fig_idx = px.line(plot_idx_df, x='Date', y='Index Value', color='Asset',
                                title="Growth of 100", labels={'Index Value': 'Value (Base 100)'}, template="plotly_dark")
                st.plotly_chart(fig_idx, use_container_width=True)

            # Maximum Drawdown Chart
            dd_df = pd.DataFrame(index=df_charting.index)
            
            for col in cols_to_plot:
                s = df_charting[col].dropna()
                if not s.empty:
                    cum_ret = (1 + s).cumprod()
                    peak = cum_ret.cummax()
                    drawdown = (cum_ret - peak) / peak
                    dd_df[col] = drawdown

            if not dd_df.empty:
                plot_dd_df = dd_df.reset_index().melt(id_vars='Date', var_name='Asset', value_name='Drawdown')
                fig_dd = px.line(plot_dd_df, x='Date', y='Drawdown', color='Asset',
                                title="Historical Drawdown", labels={'Drawdown': 'Drawdown %'}, template="plotly_dark")
                fig_dd.update_layout(yaxis_tickformat='.1%')
                st.plotly_chart(fig_dd, use_container_width=True)

            # --- Export Underlying Data ---
            st.markdown("---")
            st.subheader("Export Raw Data")
            st.write("Download the underlying return data for your currently selected assets.")
            
            df_export = df_merged[selected_funds + selected_bms].dropna(how='all')
            if not df_export.empty:
                st.download_button(
                    label="Download Selected Data (CSV)",
                    data=convert_df_to_csv(df_export),
                    file_name="underlying_returns_data.csv",
                    mime="text/csv",
                    key="dl_raw"
                )

        with tab_risk:
            st.subheader("Risk & Distribution")
            if selected_funds:
                selected_fund_risk = st.selectbox("Select Fund for Risk Analytics", options=selected_funds)
                if selected_fund_risk:
                    s_fund = df_merged[selected_fund_risk].dropna()
                    if not s_fund.empty:
                        st.markdown(f"#### Monthly Returns Heatmap: {selected_fund_risk}")
                        df_hm = pd.DataFrame({'Return': s_fund})
                        df_hm['Year'] = df_hm.index.year.astype(str)
                        df_hm['Month'] = df_hm.index.month_name().str[:3]

                        pivot = df_hm.pivot_table(index='Year', columns='Month', values='Return', aggfunc='sum')
                        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                        pivot = pivot.reindex(columns=[m for m in months if m in pivot.columns])

                        fig_hm = px.imshow(pivot, text_auto=".2%", aspect="auto", color_continuous_scale="RdYlGn",
                                        labels=dict(color="Return"))
                        fig_hm.update_yaxes(type='category')
                        st.plotly_chart(fig_hm, use_container_width=True)

                        st.markdown("#### Distribution of Returns")
                        fig_hist = px.histogram(df_hm, x='Return', nbins=50, title=f"Return Distribution: {selected_fund_risk}",
                                                marginal="box", template="plotly_dark")
                        fig_hist.update_layout(xaxis_tickformat='.1%')
                        st.plotly_chart(fig_hist, use_container_width=True)

                        st.markdown("#### 12-Month Rolling Volatility")
                        freq_name, ann_factor = determine_frequency(s_fund)
                        # Assume 12 months roughly equivalent to ann_factor
                        rolling_vol = s_fund.rolling(window=int(ann_factor)).std() * np.sqrt(ann_factor)
                        rolling_vol = rolling_vol.dropna()
                        if not rolling_vol.empty:
                            df_vol = rolling_vol.reset_index()
                            df_vol.columns = ['Date', 'Rolling Volatility']
                            fig_vol = px.line(df_vol, x='Date', y='Rolling Volatility',
                                              title=f"12-Month Rolling Volatility (Ann.): {selected_fund_risk}", template="plotly_dark")
                            fig_vol.update_layout(yaxis_tickformat='.1%')
                            st.plotly_chart(fig_vol, use_container_width=True)
            else:
                st.info("Please select at least one fund to view risk analytics.")

        with tab_exposures:
            st.subheader("Exposures")
            try:
                df_exposures = pd.read_sql("SELECT * FROM exposures", conn, index_col='Date', parse_dates=['Date'])
                if not df_exposures.empty:
                    exp_cols = df_exposures.columns.tolist()

                    # Filter default exposures to only show ones related to selected funds
                    default_exps = []
                    if selected_funds:
                        for col in exp_cols:
                            if any(fund.lower() in col.lower() for fund in selected_funds):
                                default_exps.append(col)
                    # Fallback to all exposures if no matched ones are found (or none selected)
                    if not default_exps:
                        default_exps = exp_cols

                    selected_exps = st.multiselect("Select Exposures to Visualize", options=exp_cols, default=default_exps)
                    if selected_exps:
                        # Summary Table
                        st.markdown("#### Summary Statistics")
                        summary_df = df_exposures[selected_exps].agg(['mean', 'median', 'min', 'max']).T
                        # Format for readability
                        for col in summary_df.columns:
                            summary_df[col] = summary_df[col].apply(lambda x: f"{x:,.2f}")

                        st.dataframe(summary_df, use_container_width=True)

                        # Graph
                        st.markdown("#### Historical Chart")
                        plot_exp_df = df_exposures[selected_exps].reset_index().melt(id_vars='Date', var_name='Exposure Type', value_name='Value')
                        fig_exp = px.line(plot_exp_df, x='Date', y='Value', color='Exposure Type',
                                          title="Historical Exposures", template="plotly_dark")
                        st.plotly_chart(fig_exp, use_container_width=True)
                else:
                    st.info("No exposure data available in the database.")
            except Exception:
                st.info("No exposure data available in the database.")

    else:
        st.info("Select funds or benchmarks to view analytics.")

except Exception as e:
    st.error(f"Error calculating metrics: {e}")
finally:
    try:
        conn.close()
    except Exception:
        pass