import pandas as pd
import numpy as np
import datetime

dates = pd.date_range(start="2020-01-01", end="2023-12-31", freq="ME")
np.random.seed(42)

returns_data = {
    "Fund A": np.random.normal(0.01, 0.05, len(dates)),
    "Fund B": np.random.normal(0.005, 0.03, len(dates))
}
df_returns = pd.DataFrame(returns_data, index=dates)

bm_data = {
    "S&P 500": np.random.normal(0.008, 0.04, len(dates))
}
df_bm = pd.DataFrame(bm_data, index=dates)

rf_data = {
    "Risk Free": np.random.normal(0.001, 0.0005, len(dates))
}
df_rf = pd.DataFrame(rf_data, index=dates)

exp_data = {
    "Fund A Net Exposure": np.random.normal(50, 10, len(dates)),
    "Fund A Gross Exposure": np.random.normal(150, 20, len(dates)),
    "Fund B Net Exposure": np.random.normal(30, 5, len(dates)),
    "Fund B Gross Exposure": np.random.normal(100, 10, len(dates))
}
df_exp = pd.DataFrame(exp_data, index=dates)

with pd.ExcelWriter("dummy_data_v3.xlsx") as writer:
    df_returns.to_excel(writer, sheet_name="Returns")
    df_bm.to_excel(writer, sheet_name="Benchmark")
    df_rf.to_excel(writer, sheet_name="Risk Free")
    df_exp.to_excel(writer, sheet_name="Exposures")
