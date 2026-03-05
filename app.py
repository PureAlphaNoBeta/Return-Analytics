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

# --- Database Management ---
with st.sidebar:
    st.header("Database Settings")
    if st.button("Clear Database", type="primary"):
        try:
            # Connect specifically to drop the table
            clear_conn = sqlite3.connect(db_path)
            cursor = clear_conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS performance")
            clear_conn.commit()
            clear_conn.close()
            
            # Reset session state
            if "uploaded_data" in st.session_state:
                del st.session_state["uploaded_data"]
                
            st.success("Database successfully cleared!")
            st.rerun() # Refresh the app to show the empty state
        except Exception as e:
            st.error(f"Error clearing database: {e}")

# --- File Upload & Processing ---
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx", "xls"])

conn = sqlite3.connect(db_path)

if uploaded_file is not None and "uploaded_data" not in st.session_state:
    try:
        xl = pd.ExcelFile(uploaded_file)
        
        # Identify sheets
        returns_sheet = None
        bm_sheet = None
        rf_sheet = None
        
        for sheet in xl.sheet_names:
            if 'return' in sheet.lower():
                returns_sheet = sheet
            elif 'bm' in sheet.lower() or 'benchmark' in sheet.lower():
                bm_sheet = sheet
            elif 'rf' in sheet.lower() or 'risk free' in sheet.lower() or 'risk-free' in sheet.lower():
                rf_sheet = sheet
                
        if not returns_sheet or not bm_sheet:
            st.error("Could not find required sheets. Please ensure one sheet contains 'Returns' and another 'BM' or 'Benchmark' in their names.")
        else:
            # Read sheets
            df_returns = pd.read_excel(uploaded_file, sheet_name=returns_sheet, index_col=0, parse_dates=True)
            df_bm = pd.read_excel(uploaded_file, sheet_name=bm_sheet, index_col=0, parse_dates=True)
            
            # Format index to strip time (just dates)
            df_returns.index = pd.to_datetime(df_returns.index).normalize()
            df_bm.index = pd.to_datetime(df_bm.index).normalize()
            
            df_rf = None
            if rf_sheet:
                df_rf = pd.read_excel(uploaded_file, sheet_name=rf_sheet, index_col=0, parse_dates=True)
                df_rf.index = pd.to_datetime(df_rf.index).normalize()
            
            # Combine all data into one DataFrame for storage
            df_combined = df_returns.copy()
            df_combined = df_combined.combine_first(df_bm)
            if df_rf is not None:
                df_combined = df_combined.combine_first(df_rf)
                
            df_combined.index.name = 'Date'
            
            try:
                # Read existing data from DB
                df_existing = pd.read_sql("SELECT * FROM performance", conn, index_col='Date', parse_dates=['Date'])
                df_existing.index = pd.to_datetime(df_existing.index).normalize()
                
                # Update with new data (new data overrides/adds to existing)
                df_final = df_combined.combine_first(df_existing)
            except Exception as e:
                # Table probably doesn't exist yet
                df_final = df_combined
                
            # Save back to database
            df_final.to_sql('performance', conn, if_exists='replace', index=True)
            st.session_state["uploaded_data"] = True
            st.success("Data successfully uploaded and merged into the database!")
            
    except Exception as e:
        st.error(f"Error processing file: {e}")

# --- Analysis & Visualization ---
st.header("Performance Metrics")

try:
    # Load merged data
    try:
        df_merged = pd.read_sql("SELECT * FROM performance", conn, index_col='Date', parse_dates=['Date'])
    except Exception:
        st.info("No data available yet. Please upload an Excel file.")
        st.stop()
        
    df_merged.index = pd.to_datetime(df_merged.index)
    df_merged = df_merged.sort_index()
    
    # User Selection
    all_cols = df_merged.columns.tolist()
    
    # Try to guess default RFs, but leave funds and BMs empty by default
    default_rfs = [c for c in all_cols if 'rf' in c.lower() or 'risk' in c.lower()]
    
    col1, col2, col3 = st.columns(3)
    with col1:
        # Default changed to [] so nothing auto-selects
        selected_funds = st.multiselect("Select Funds to Analyze", options=all_cols, default=[])
    with col2:
        # Default changed to [] so nothing auto-selects
        selected_bms = st.multiselect("Select Benchmarks to Analyze", options=all_cols, default=[])
    with col3:
        rf_options = ["None"] + all_cols
        default_rf_val = default_rfs[0] if default_rfs else "None"
        selected_rf = st.selectbox("Select Risk Free Rate", options=rf_options, index=rf_options.index(default_rf_val) if default_rf_val in rf_options else 0)
        
    selected_rf = None if selected_rf == "None" else selected_rf

    if selected_funds or selected_bms:
        # Helper to determine frequency per series
        def determine_frequency(series):
            # Drop NaNs to find the frequency of actual data points
            s_clean = series.dropna()
            if len(s_clean) < 2:
                return 'Monthly', 12 # Default
            
            # Calculate median days between observations
            median_days = s_clean.index.to_series().diff().dt.days.median()
            
            if median_days <= 5:
                return 'Daily', 252
            elif median_days <= 10:
                return 'Weekly', 52
            elif median_days <= 31:
                return 'Monthly', 12
            else:
                return 'Yearly', 1
        
        # Metric Calculation per series
        def calc_metrics(series, freq_factor, period_months=None, rf_series=None, bm_series=None):
            s = series.dropna()
            
            if period_months is not None:
                end_date = s.index[-1]
                if period_months == 'YTD':
                    start_date = pd.to_datetime(f"{end_date.year}-12-31") - pd.DateOffset(years=1)
                    s = s[s.index > start_date]
                    if len(s) < 1:
                        return pd.Series(dtype='float64')
                else:
                    # Filter for period
                    start_date = end_date - pd.DateOffset(months=period_months)
                    s = s[s.index >= start_date]
                    
                    # If the available data is less than the requested period, return empty
                    # We check if the difference between first and last date is close to period_months
                    if len(s) < 2 or (end_date - s.index[0]).days < (period_months * 30 * 0.9): # 10% tolerance
                         return pd.Series(dtype='float64')

            if s.empty:
                return pd.Series(dtype='float64')
            
            years = (s.index[-1] - s.index[0]).days / 365.25
            
            # Annualized Return (Geometric)
            if years > 0:
                ann_ret = (1 + (1+s).cumprod().iloc[-1] - 1) ** (1/years) - 1
            else:
                ann_ret = np.nan
                
            # Volatility
            vol = s.std() * np.sqrt(freq_factor)
            
            # Downside Volatility (RMS deviation of negative returns from 0)
            neg_returns = s[s < 0]
            if not neg_returns.empty:
                downside_vol = np.sqrt((neg_returns**2).sum() / len(s)) * np.sqrt(freq_factor)
            else:
                downside_vol = 0.0

            # Max Drawdown
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
                dd_start = pd.NaT
                dd_recovery = pd.NaT
                dd_length = np.nan
            
            # Sharpe Ratio
            sharpe = np.nan
            if rf_series is not None:
                 rf_s = rf_series.reindex(s.index).ffill().fillna(0)
                 # Convert annualized RF rate to period rate (using previous period's rate)
                 rf_period_rate = rf_s.shift(1) / freq_factor
                 # Fill the first NaN (from shift) with the first available period rate
                 rf_period_rate.iloc[0] = rf_s.iloc[0] / freq_factor
                 
                 # Excess return
                 ex_ret = s - rf_period_rate
                 sharpe = (ex_ret.mean() / ex_ret.std()) * np.sqrt(freq_factor) if ex_ret.std() != 0 else np.nan
            else:
                 sharpe = (s.mean() / s.std()) * np.sqrt(freq_factor) if s.std() != 0 else np.nan

            # Capture Ratios & New Metrics
            up_cap = np.nan
            down_cap = np.nan
            cap_ratio = np.nan
            beta = np.nan
            alpha = np.nan
            tracking_error = np.nan
            info_ratio = np.nan
            corr_falling = np.nan
            
            # VaR and CVaR
            var_alpha = 0.05
            var_val = np.percentile(s, var_alpha * 100) if not s.empty else np.nan
            cvar_val = s[s <= var_val].mean() if pd.notna(var_val) and len(s[s <= var_val]) > 0 else np.nan

            if bm_series is not None:
                bm_s = bm_series.reindex(s.index).dropna()
                if not bm_s.empty:
                    # Align series
                    common_idx = s.index.intersection(bm_s.index)
                    s_aligned = s.loc[common_idx]
                    bm_aligned = bm_s.loc[common_idx]
                    
                    up_months = bm_aligned > 0
                    down_months = bm_aligned <= 0
                    
                    # Geometric return approximation for capture (annualized based on VBA logic)
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
                         
                    # Tracking Error & Info Ratio
                    active_returns = s_aligned - bm_aligned
                    tracking_error = active_returns.std() * np.sqrt(freq_factor)
                    annualized_active = active_returns.mean() * freq_factor
                    info_ratio = annualized_active / tracking_error if tracking_error != 0 else np.nan

                    # Beta & Alpha
                    if rf_series is not None:
                        rf_aligned = rf_period_rate.loc[common_idx].fillna(0)
                        s_adj = s_aligned - rf_aligned
                        bm_adj = bm_aligned - rf_aligned
                    else:
                        s_adj = s_aligned
                        bm_adj = bm_aligned
                        
                    cov_matrix = np.cov(s_adj, bm_adj)
                    if cov_matrix[1, 1] != 0:
                        beta = cov_matrix[0, 1] / cov_matrix[1, 1]
                        alpha = (s_adj.mean() - beta * bm_adj.mean()) * freq_factor

                    # Correlation during falling markets
                    falling_idx = bm_aligned[bm_aligned < 0].index
                    if len(falling_idx) >= 2:
                        corr_falling = s_aligned.loc[falling_idx].corr(bm_aligned.loc[falling_idx])

            return pd.Series({
                'Annualized Return': ann_ret,
                'Volatility (Ann.)': vol,
                'Downside Vol (Ann.)': downside_vol,
                'Max Drawdown': max_drawdown,
                'Drawdown Start': dd_start.strftime('%Y-%m-%d') if pd.notna(dd_start) else 'N/A',
                'Drawdown End': dd_end.strftime('%Y-%m-%d') if pd.notna(dd_end) else 'N/A',
                'Drawdown Length (Days)': dd_length,
                'Sharpe Ratio': sharpe,
                'Value at Risk (5%)': var_val,
                'Conditional VaR (5%)': cvar_val,
                'Beta': beta,
                'Alpha (Ann.)': alpha,
                'Tracking Error': tracking_error,
                'Information Ratio': info_ratio,
                'Upside Capture': up_cap,
                'Downside Capture': down_cap,
                'Capture Ratio': cap_ratio,
                'Corr in Down Markets': corr_falling
            })
            
        def generate_metrics_df(period_months):
            metrics_list = []
            # Use first selected benchmark for capture ratio, if any
            primary_bm = selected_bms[0] if selected_bms else None
            rf_series = df_merged[selected_rf] if selected_rf else None
            
            cols_to_analyze = selected_funds + selected_bms
            
            for col in cols_to_analyze:
                if df_merged[col].dropna().empty: continue
                
                freq_name, ann_factor = determine_frequency(df_merged[col])
                
                bm_series = None
                # Don't calculate capture ratio against itself
                if primary_bm and col != primary_bm and primary_bm in df_merged.columns:
                    bm_series = df_merged[primary_bm]

                res = calc_metrics(df_merged[col], ann_factor, period_months, rf_series=rf_series, bm_series=bm_series)
                if not res.empty:
                    res.name = col
                    metrics_list.append(res)
                
            if not metrics_list: return None
            
            metrics_df = pd.DataFrame(metrics_list)
            
            # Formatting
            def format_pct(x):
                try: return f"{float(x)*100:.2f}%" if pd.notnull(x) else "N/A"
                except: return "N/A"

            def format_dec(x):
                try: return f"{float(x):.2f}" if pd.notnull(x) else "N/A"
                except: return "N/A"

            pct_cols = ['Annualized Return', 'Volatility (Ann.)', 'Downside Vol (Ann.)', 'Max Drawdown', 'Value at Risk (5%)', 'Conditional VaR (5%)', 'Alpha (Ann.)', 'Tracking Error']
            for c in pct_cols:
                if c in metrics_df.columns:
                    metrics_df[c] = metrics_df[c].apply(format_pct)
            
            dec_cols = ['Sharpe Ratio', 'Beta', 'Information Ratio', 'Upside Capture', 'Downside Capture', 'Capture Ratio', 'Corr in Down Markets', 'Drawdown Length (Days)']
            for c in dec_cols:
                if c in metrics_df.columns:
                    metrics_df[c] = metrics_df[c].apply(format_dec)
                    
            return metrics_df

        t_ytd, t_1y, t_3y, t_5y, t_10y, t_itd = st.tabs(["YTD", "1 Year", "3 Year", "5 Year", "10 Year", "ITD"])
        
        with t_ytd:
            df_ytd = generate_metrics_df('YTD')
            if df_ytd is not None and not df_ytd.empty: st.dataframe(df_ytd, use_container_width=True)
            else: st.info("Not enough data for YTD analysis.")

        with t_1y:
            df_1y = generate_metrics_df(12)
            if df_1y is not None and not df_1y.empty: st.dataframe(df_1y, use_container_width=True)
            else: st.info("Not enough data for 1-Year analysis.")

        with t_3y:
            df_3y = generate_metrics_df(36)
            if df_3y is not None and not df_3y.empty: st.dataframe(df_3y, use_container_width=True)
            else: st.info("Not enough data for 3-Year analysis.")
            
        with t_5y:
            df_5y = generate_metrics_df(60)
            if df_5y is not None and not df_5y.empty: st.dataframe(df_5y, use_container_width=True)
            else: st.info("Not enough data for 5-Year analysis.")
            
        with t_10y:
            df_10y = generate_metrics_df(120)
            if df_10y is not None and not df_10y.empty: st.dataframe(df_10y, use_container_width=True)
            else: st.info("Not enough data for 10-Year analysis.")
            
        with t_itd:
            df_itd = generate_metrics_df(None)
            if df_itd is not None and not df_itd.empty: st.dataframe(df_itd, use_container_width=True)
            else: st.info("No data available.")

        
        # --- Cumulative Growth Chart (Base 100) ---
        st.markdown("---")
        st.subheader("Cumulative Growth (Inception to Date)")
        
        index_df = pd.DataFrame(index=df_merged.index)
        cols_to_plot = selected_funds + selected_bms
        
        for col in cols_to_plot:
            s = df_merged[col].dropna()
            if not s.empty:
                # Calculate base 100 series starting from the asset's specific inception
                index_df[col] = 100 * (1 + s).cumprod()
                
        if not index_df.empty:
            # Forward fill to handle slightly misaligned dates nicely on the plot
            index_df = index_df.ffill()
            plot_idx_df = index_df.reset_index().melt(id_vars='Date', var_name='Asset', value_name='Index Value')
            
            fig_idx = px.line(plot_idx_df, x='Date', y='Index Value', color='Asset', 
                              title="Growth of 100 (ITD)", 
                              labels={'Index Value': 'Value (Base 100)'},
                              template="plotly_dark")
            st.plotly_chart(fig_idx, use_container_width=True)

        # --- Maximum Drawdown Chart ---
        st.markdown("---")
        st.subheader("Maximum Drawdown Over Time")
        
        dd_df = pd.DataFrame(index=df_merged.index)
        
        for col in cols_to_plot:
            s = df_merged[col].dropna()
            if not s.empty:
                cum_ret = (1 + s).cumprod()
                peak = cum_ret.cummax()
                drawdown = (cum_ret - peak) / peak
                dd_df[col] = drawdown
                
        if not dd_df.empty:
            # Reset index for plotly
            plot_dd_df = dd_df.reset_index().melt(id_vars='Date', var_name='Asset', value_name='Drawdown')
            fig_dd = px.line(plot_dd_df, x='Date', y='Drawdown', color='Asset', 
                             title="Historical Drawdown", 
                             labels={'Drawdown': 'Drawdown %'},
                             template="plotly_dark")
            # Format y-axis as percentage
            fig_dd.update_layout(yaxis_tickformat='.1%')
            st.plotly_chart(fig_dd, use_container_width=True)

    else:
        st.info("Select funds or benchmarks to view analytics.")

except Exception as e:
    st.error(f"Error calculating metrics: {e}")
finally:
    # Check if conn is connected before trying to close
    try:
        conn.close()
    except Exception:
        pass