import pandas as pd
import numpy as np

def determine_frequency(series):
    s_clean = series.dropna()
    if len(s_clean) < 2: return 'Monthly', 12
    median_days = s_clean.index.to_series().diff().dt.days.median()
    if median_days <= 5: return 'Daily', 252
    elif median_days <= 10: return 'Weekly', 52
    elif median_days <= 31: return 'Monthly', 12
    else: return 'Yearly', 1

def calc_metrics(series, freq_factor, freq_name, period_months=None, rf_series=None, bm_series=None):
    """
    Vectorizable helper wrapper around core financial calculations.
    For simplicity and backward compatibility, we wrap individual series calculations.
    """
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

    years = len(s) / freq_factor

    ann_ret = (1 + (1+s).cumprod().iloc[-1] - 1) ** (1/years) - 1 if years > 0 else np.nan
    vol = s.std(ddof=1) * np.sqrt(freq_factor)

    if rf_series is not None:
        rf_s = rf_series.reindex(s.index).ffill().fillna(0)
        rf_period_rate = rf_s
    else:
        rf_period_rate = pd.Series(0.0, index=s.index)

    excess_for_mar = s - rf_period_rate
    neg_returns = excess_for_mar[excess_for_mar < 0]
    # Use N-1 for downside volatility as requested
    down_vol_denom = len(s) - 1 if len(s) > 1 else 1
    downside_vol = np.sqrt((neg_returns**2).sum() / down_vol_denom) * np.sqrt(freq_factor) if not neg_returns.empty else 0.0

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

    ex_ret = s - rf_period_rate
    sharpe = (ex_ret.mean() / ex_ret.std()) * np.sqrt(freq_factor) if ex_ret.std() != 0 else np.nan

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
                s_up_ret = (1 + s_aligned[up_months]).prod() - 1
                bm_up_ret = (1 + bm_aligned[up_months]).prod() - 1
                up_cap = s_up_ret / bm_up_ret if bm_up_ret != 0 else np.nan

            if down_months.sum() > 0:
                s_down_ret = (1 + s_aligned[down_months]).prod() - 1
                bm_down_ret = (1 + bm_aligned[down_months]).prod() - 1
                down_cap = s_down_ret / bm_down_ret if bm_down_ret != 0 else np.nan

            if pd.notna(up_cap) and pd.notna(down_cap) and down_cap != 0:
                 cap_ratio = up_cap / np.abs(down_cap)

            active_returns = s_aligned - bm_aligned
            tracking_error = active_returns.std(ddof=1) * np.sqrt(freq_factor)
            annualized_active = active_returns.mean() * freq_factor
            info_ratio = annualized_active / tracking_error if tracking_error != 0 else np.nan

            # CAPM Beta requires risk-free rate
            rf_aligned = rf_period_rate.loc[common_idx].fillna(0)
            s_adj, bm_adj = s_aligned - rf_aligned, bm_aligned - rf_aligned

            cov_matrix = np.cov(s_adj, bm_adj, ddof=1)
            if cov_matrix[1, 1] != 0:
                beta = cov_matrix[0, 1] / cov_matrix[1, 1]
                alpha = (s_adj.mean() - beta * bm_adj.mean()) * freq_factor

            falling_idx = bm_aligned[bm_aligned < 0].index
            if len(falling_idx) >= 2: corr_falling = s_aligned.loc[falling_idx].corr(bm_aligned.loc[falling_idx])

    return pd.Series({
        'Frequency': freq_name,
        'Annualized Return': ann_ret, 'Volatility (Ann.)': vol, 'Downside Vol (Ann.)': downside_vol,
        'Max Drawdown': max_drawdown, 'Drawdown Start': dd_start.strftime('%Y-%m-%d') if pd.notna(dd_start) else 'N/A',
        'Drawdown End': dd_end.strftime('%Y-%m-%d') if pd.notna(dd_end) else 'N/A',
        'Drawdown Length (Days)': dd_length, 'Sharpe Ratio': sharpe, 'VaR (5%)': var_val,
        'CVaR (5%)': cvar_val, 'Beta': beta, 'Alpha (Ann.)': alpha, 'Tracking Error': tracking_error,
        'Information Ratio': info_ratio, 'Upside Capture': up_cap, 'Downside Capture': down_cap,
        'Capture Ratio': cap_ratio, 'Corr in Down Markets': corr_falling
    })

def get_drawdown_table(df_merged, selected_assets):
    """
    Returns a DataFrame containing the maximum drawdown details.
    """
    dd_list = []
    for col in selected_assets:
        s = df_merged[col].dropna()
        if s.empty: continue

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

        dd_list.append({
            'Asset': col,
            'Max Drawdown': f"{max_drawdown*100:.2f}%" if pd.notna(max_drawdown) else "N/A",
            'Drawdown Start': dd_start.strftime('%Y-%m-%d') if pd.notna(dd_start) else 'N/A',
            'Drawdown End': dd_end.strftime('%Y-%m-%d') if pd.notna(dd_end) else 'N/A',
            'Drawdown Length (Days)': int(dd_length) if pd.notna(dd_length) else "N/A"
        })
    return pd.DataFrame(dd_list)

def generate_metrics_df(df_merged, selected_funds, selected_bms, selected_rf, period_months):
    metrics_list = []
    primary_bm = selected_bms[0] if selected_bms else None
    rf_series = df_merged[selected_rf] if selected_rf else None
    cols_to_analyze = selected_funds + selected_bms

    for col in cols_to_analyze:
        if df_merged[col].dropna().empty: continue
        freq_name, ann_factor = determine_frequency(df_merged[col])
        bm_series = df_merged[primary_bm] if primary_bm and col != primary_bm and primary_bm in df_merged.columns else None
        res = calc_metrics(df_merged[col], ann_factor, freq_name, period_months, rf_series=rf_series, bm_series=bm_series)
        if not res.empty:
            # Drop the drawdown details from the metrics tab dataframe
            res = res.drop(labels=['Drawdown Start', 'Drawdown End', 'Drawdown Length (Days)'], errors='ignore')
            res.name = col
            metrics_list.append(res)

    if not metrics_list: return None
    metrics_df = pd.DataFrame(metrics_list)

    # We will let the Streamlit formatting layer handle the string formatting so we can color-code the raw floats
    return metrics_df
