import pandas as pd
import numpy as np

# Generate dummy exposure data for Fund A and Fund B
dates = pd.date_range(start="2020-01-31", periods=24, freq="ME")

data = {
    "Date": dates,
    "Fund A Net": np.random.uniform(20, 40, size=24),
    "Fund A Gross": np.random.uniform(100, 150, size=24),
    "Fund B Net": np.random.uniform(10, 30, size=24),
    "Fund B Gross": np.random.uniform(80, 120, size=24),
}

df = pd.DataFrame(data)

with pd.ExcelWriter("dummy_multi_fund_data.xlsx") as writer:
    # Just put some dummy return data too
    returns_data = {
        "Date": dates,
        "Fund A": np.random.normal(0.01, 0.02, size=24),
        "Fund B": np.random.normal(0.005, 0.015, size=24)
    }
    pd.DataFrame(returns_data).to_excel(writer, sheet_name="Returns", index=False)

    # Needs benchmark too
    bm_data = {
        "Date": dates,
        "SP500": np.random.normal(0.008, 0.015, size=24)
    }
    pd.DataFrame(bm_data).to_excel(writer, sheet_name="BM", index=False)

    # Save the exposures
    df.to_excel(writer, sheet_name="Exposures", index=False)

print("Generated dummy_multi_fund_data.xlsx")
