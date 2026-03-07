import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import timedelta
import os
import db_utils
from metrics import generate_metrics_df, get_drawdown_table, determine_frequency

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

# Ensure tables exist
db_utils.init_db(db_path)

# --- Database Management ---
with st.sidebar:
    st.header("Database Settings")
    if st.button("Clear Database", type="primary"):
        try:
            db_utils.clear_db(db_path)
            if "uploaded_data" in st.session_state:
                del st.session_state["uploaded_data"]
            st.success("Database successfully cleared!")
            st.rerun()
        except Exception as e:
            st.error(f"Error clearing database: {e}")

# --- File Upload & Processing ---
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx", "xls"])

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
            
            db_utils.update_db_table(df_returns, 'funds', db_path)
            db_utils.update_db_table(df_bm, 'benchmarks', db_path)
            
            if rf_sheet:
                df_rf = pd.read_excel(uploaded_file, sheet_name=rf_sheet, index_col=0, parse_dates=True)
                df_rf.index = pd.to_datetime(df_rf.index).normalize()
                db_utils.update_db_table(df_rf, 'risk_free', db_path)

            if exp_sheet:
                df_exp = pd.read_excel(uploaded_file, sheet_name=exp_sheet, index_col=0, parse_dates=True)
                df_exp.index = pd.to_datetime(df_exp.index).normalize()
                db_utils.update_db_table(df_exp, 'exposures', db_path)
                
            st.session_state["uploaded_data"] = True
            st.success("Data successfully uploaded and categorized into the database!")
            
    except Exception as e:
        st.error(f"Error processing file: {e}")

# --- Analysis & Visualization ---
st.header("Performance Metrics")

try:
    df_funds = db_utils.get_data_by_category('funds', db_path)
    fund_cols = df_funds.columns.tolist() if not df_funds.empty else []

    df_bms = db_utils.get_data_by_category('benchmarks', db_path)
    bm_cols = df_bms.columns.tolist() if not df_bms.empty else []

    df_rfs = db_utils.get_data_by_category('risk_free', db_path)
    rf_cols = df_rfs.columns.tolist() if not df_rfs.empty else []

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
    tab_metrics, tab_growth, tab_risk, tab_exposures = st.tabs(["Metrics", "Total Return & Drawdown", "Risk & Distribution", "Exposures"])

    if selected_funds or selected_bms:
        with tab_metrics:
            time_horizon = st.radio(
                "Select Time Horizon",
                ["YTD", "1 Year", "3 Year", "5 Year", "10 Year", "ITD"],
                horizontal=True
            )

            if time_horizon == "YTD":
                df_metrics = generate_metrics_df(df_merged, selected_funds, selected_bms, selected_rf, 'YTD')
                dl_key = "dl_ytd"
            elif time_horizon == "1 Year":
                df_metrics = generate_metrics_df(df_merged, selected_funds, selected_bms, selected_rf, 12)
                dl_key = "dl_1y"
            elif time_horizon == "3 Year":
                df_metrics = generate_metrics_df(df_merged, selected_funds, selected_bms, selected_rf, 36)
                dl_key = "dl_3y"
            elif time_horizon == "5 Year":
                df_metrics = generate_metrics_df(df_merged, selected_funds, selected_bms, selected_rf, 60)
                dl_key = "dl_5y"
            elif time_horizon == "10 Year":
                df_metrics = generate_metrics_df(df_merged, selected_funds, selected_bms, selected_rf, 120)
                dl_key = "dl_10y"
            else: # ITD
                df_metrics = generate_metrics_df(df_merged, selected_funds, selected_bms, selected_rf, None)
                dl_key = "dl_itd"

            if df_metrics is not None and not df_metrics.empty:
                # Format the display, keep raw values
                format_dict = {
                    'Annualized Return': '{:.2%}', 'Volatility (Ann.)': '{:.2%}', 'Downside Vol (Ann.)': '{:.2%}',
                    'Max Drawdown': '{:.2%}', 'VaR (5%)': '{:.2%}', 'CVaR (5%)': '{:.2%}', 'Alpha (Ann.)': '{:.2%}',
                    'Tracking Error': '{:.2%}', 'Sharpe Ratio': '{:.2f}', 'Beta': '{:.2f}', 'Information Ratio': '{:.2f}',
                    'Upside Capture': '{:.2f}', 'Downside Capture': '{:.2f}', 'Capture Ratio': '{:.2f}', 'Corr in Down Markets': '{:.2f}'
                }

                # Create a styling object using Streamlit's style capabilities
                styled_df = df_metrics.style.format(format_dict, na_rep='N/A')

                # Apply background gradient map for visual heatmap
                # Higher is Better (Positive values are green, negative are red)
                higher_is_better = ['Annualized Return', 'Sharpe Ratio', 'Alpha (Ann.)', 'Capture Ratio', 'Upside Capture', 'Information Ratio', 'Max Drawdown', 'VaR (5%)', 'CVaR (5%)']

                # Lower is Better (Positive/high values are red, low/negative are green)
                lower_is_better = ['Downside Capture', 'Corr in Down Markets']

                for col in higher_is_better:
                    if col in df_metrics.columns:
                        styled_df = styled_df.background_gradient(subset=[col], cmap='RdYlGn', vmin=df_metrics[col].min(), vmax=df_metrics[col].max())

                for col in lower_is_better:
                    if col in df_metrics.columns:
                        styled_df = styled_df.background_gradient(subset=[col], cmap='RdYlGn_r', vmin=df_metrics[col].min(), vmax=df_metrics[col].max())

                st.dataframe(styled_df, use_container_width=True)

                # Keep original float format for CSV download to avoid Excel errors
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

            # --- Drawdown Section ---
            st.markdown("---")
            st.subheader("Drawdown Analysis")

            # Display Drawdown Table
            st.markdown("#### Maximum Drawdown Details")
            dd_table = get_drawdown_table(df_charting, cols_to_plot)
            if not dd_table.empty:
                st.dataframe(dd_table, use_container_width=True, hide_index=True)

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
                df_exposures = db_utils.get_data_by_category('exposures', db_path)
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