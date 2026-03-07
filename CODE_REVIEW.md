# Financial Code Review & Analysis Report

This document provides a detailed breakdown of the financial logic, mathematical implementations, and data handling mechanisms present in the Performance Analytics dashboard (`app.py`), from the perspective of a quantitative financial engineer.

---

## 1. Calculation Analysis

The dashboard processes financial time-series data using `pandas` and `numpy`. Below is a step-by-step breakdown of every major calculation performed within the `calc_metrics` function:

*   **Frequency Factor (`freq_factor`):**
    *   Determined by observing the median number of days between dates in the index: `s_clean.index.to_series().diff().dt.days.median()`.
    *   Maps to factors: $\le5$ days = Daily (252), $\le10$ days = Weekly (52), $\le31$ days = Monthly (12), else Yearly (1).

*   **Annualized Return (CAGR):**
    *   Calculated based on actual days between the first and last observation: `years = (s.index[-1] - s.index[0]).days / 365.25`.
    *   Formula: $CAGR = \left( \prod (1 + R_t) \right)^{\frac{1}{\text{years}}} - 1$.

*   **Volatility (Annualized):**
    *   Uses sample standard deviation, scaled by the square root of the frequency factor.
    *   Formula: $\sigma_{\text{ann}} = \sigma_{\text{periodic}} \times \sqrt{\text{freq\_factor}}$.

*   **Downside Volatility (Annualized):**
    *   Filters for negative returns ($R_t < 0$) and calculates the root mean square of these negative returns over the *entire* sample size $N$, then scales it.
    *   Formula: $\sigma_{\text{down}} = \sqrt{ \frac{\sum (R_{t} | R_t < 0)^2}{N} } \times \sqrt{\text{freq\_factor}}$.

*   **Maximum Drawdown & Recovery:**
    *   Calculates a cumulative return index: $C_t = \prod (1 + R_t)$.
    *   Calculates a running peak: $P_t = \max(C_1, \dots, C_t)$.
    *   Drawdown series: $D_t = \frac{C_t - P_t}{P_t}$. Max Drawdown is the minimum value of this series.
    *   Drawdown Length is calculated in literal days from the historical peak to the first date where the drawdown returns to 0 (recovery).

*   **Sharpe Ratio:**
    *   If a risk-free rate is provided, it calculates the excess return ($R_t - RF_t$). The Sharpe is the mean of the excess return divided by the standard deviation of the excess return, annualized.
    *   Formula: $S = \frac{\mu_{\text{excess}}}{\sigma_{\text{excess}}} \times \sqrt{\text{freq\_factor}}$.

*   **Value at Risk (VaR) & Conditional VaR (CVaR):**
    *   **VaR (5%):** Uses historical simulation by taking the 5th percentile of the return series: `np.percentile(s, 5)`.
    *   **CVaR (5%):** Takes the mean of all returns that fall below or equal to the VaR threshold.

*   **Alpha & Beta (vs. Benchmark):**
    *   Only computed over dates where both fund and benchmark exist (`common_idx`).
    *   Covariance matrix is calculated between the asset returns (adjusted for risk-free rate if provided) and benchmark returns.
    *   Formula: $\beta = \frac{\text{Cov}(R_a, R_b)}{\text{Var}(R_b)}$.
    *   Formula: $\alpha = \left( \mu_a - \beta \times \mu_b \right) \times \text{freq\_factor}$.

*   **Tracking Error & Information Ratio:**
    *   Active returns: $R_{\text{active}} = R_a - R_b$.
    *   Tracking Error: $\text{TE} = \sigma(R_{\text{active}}) \times \sqrt{\text{freq\_factor}}$.
    *   Information Ratio: $\text{IR} = \frac{\mu(R_{\text{active}}) \times \text{freq\_factor}}{\text{TE}}$.

*   **Upside & Downside Capture:**
    *   Separates months into up-markets ($R_b > 0$) and down-markets ($R_b \le 0$).
    *   Calculates an annualized compound return for these specific subsets.
    *   Formula implemented: $\text{Up Return} = \left( \prod (1 + R_{a, up}) \right)^{\frac{\text{freq\_factor}}{N_{up}}} - 1$.
    *   Capture Ratio: $\frac{\text{Upside Capture}}{|\text{Downside Capture}|}$.

---

## 2. Financial Critique & Validation

While the dashboard provides a broad overview, several of the mathematical implementations deviate from strict industry-standard practices, which can introduce significant distortions:

### Flaws & Potential Errors

**1. Upside/Downside Capture Annualization (Critical Flaw)**
*   **The Issue:** The code annualizes the compound return of the up/down periods by raising it to the power of `(freq_factor / count_up)`.
*   **Why it's wrong:** If a fund has 5 up-months in a year, raising the 5-month compound return to the power of $12 / 5$ (2.4) heavily distorts the metric. In industry standard, capture is usually the simple ratio of the compound return of the fund during up-months over the compound return of the benchmark during those *same exact* up-months. There is no need to artificially annualize a subset of months.
*   **Correction:** Simply use: `s_up_ret = (1 + s_aligned[up_months]).prod() - 1` and `bm_up_ret = (1 + bm_aligned[up_months]).prod() - 1`, then divide.

**2. Downside Volatility MAR (Minor Flaw)**
*   **The Issue:** The code uses a hardcoded Minimum Acceptable Return (MAR) of 0 (`s < 0`).
*   **Why it's wrong:** Standard Sortino/Downside Deviation calculations often allow the user to define a MAR (e.g., the risk-free rate or a target hurdle rate). Using absolute 0 can penalize strategies where the risk-free rate is high.

**3. Risk-Free Rate Scaling & Shifting (Data/Logic Issue)**
*   **The Issue:** `rf_period_rate = rf_s.shift(1) / freq_factor`.
*   **Why it's wrong:**
    1. *Shifting:* Shifting the rate by 1 period assumes the rate is reported at the *end* of the period for the *next* period. If the user uploads a time-series where the rate corresponds to the current period's yield, shifting it misaligns the data.
    2. *Scaling:* Dividing by `freq_factor` (`rf_s / 12`) assumes the uploaded risk-free rate is an *annualized yield* (e.g., 5% stated as 0.05). If the user uploads actual realized monthly returns of a cash proxy (e.g., 0.4% per month), dividing by 12 heavily understates the risk-free rate.
*   **Correction:** The application should explicitly require the user to input the risk-free rate as a *per-period actual return*, removing the need to divide by `freq_factor` and shift.

**4. Annualized Return (CAGR) Time Base (Edge Case)**
*   **The Issue:** `years = (s.index[-1] - s.index[0]).days / 365.25`.
*   **Why it's wrong:** Using exact days between the first and last observation is acceptable for daily data, but flawed for monthly data. If the series goes from Jan 31 to Dec 31 (11 months geometrically, 334 days), the formula divides by ~0.91 years, slightly skewing the annualization.
*   **Correction:** For monthly data, it is more robust to use the count of periods: `years = len(s) / freq_factor`.

---

## 3. Time-Series & Data Alignment

The script handles the complexities of asynchronous hedge fund data remarkably well using Pandas and SQLite.

### Mechanisms Used

*   **Ingestion & Asynchronous Updates (`combine_first`):**
    When a user uploads a new Excel file, the `update_db_table` function reads the existing SQLite table into a DataFrame. It then uses `df_new.combine_first(df_existing)`. This is an elegant way to handle asynchronous data because it prioritizes the newly uploaded data, but fills in any missing historical dates or missing columns with the existing database data.
*   **Time Interval Alignment (`join(how='outer')`):**
    When pulling data for analysis, the funds, benchmarks, and risk-free tables are merged using an `outer` join: `df_merged.join(df_bms, how='outer')`. This guarantees that if Fund A reports on the 15th, and Fund B reports on the 31st, the master index expands to include both dates, inserting `NaN` where data does not exist for a specific asset.
*   **Index Normalization (`normalize()`):**
    All dates are passed through `pd.to_datetime().normalize()`. This strips any time-of-day information (setting the time to 00:00:00). This prevents alignment bugs where one system exports "2023-01-31 23:59:59" and another exports "2023-01-31 00:00:00".
*   **Missing Values & Risk-Free Alignment (`ffill()`):**
    The risk-free rate is reindexed to match the fund's specific timeline using `rf_series.reindex(s.index).ffill()`. Because risk-free rates (like the 3-Month T-Bill) might not be published on the exact same day as a fund's NAV, forward-filling ensures that the most recently available rate is applied to the fund's return date.
*   **Benchmark Synchronization (`intersection`):**
    For relative metrics like Alpha, Beta, and Tracking Error, calculations *must* be done over exactly identical periods. The code handles this by finding the intersection of valid dates: `common_idx = s.index.intersection(bm_s.index)`, ensuring the covariance matrix is built purely on matched, synchronous data points.
