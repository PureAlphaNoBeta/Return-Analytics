import pandas as pd
import numpy as np
from metrics import calc_metrics, determine_frequency

def test_determine_frequency():
    dates = pd.date_range(start='2020-01-01', periods=12, freq='ME')
    s = pd.Series(np.random.randn(12), index=dates)
    freq, factor = determine_frequency(s)
    assert freq == 'Monthly'
    assert factor == 12

def test_calc_metrics_basic():
    dates = pd.date_range(start='2020-01-01', periods=24, freq='ME')
    # Use standard 1% return each month
    s = pd.Series([0.01] * 24, index=dates)

    res = calc_metrics(s, freq_factor=12)
    # Expected Annualized Return: (1.01^12) - 1 approx 0.1268
    expected_cagr = (1.01**12) - 1
    np.testing.assert_almost_equal(res['Annualized Return'], expected_cagr, decimal=4)
    # Volatility should be 0 since return is constant
    np.testing.assert_almost_equal(res['Volatility (Ann.)'], 0.0, decimal=4)

def test_calc_metrics_downside():
    dates = pd.date_range(start='2020-01-01', periods=4, freq='ME')
    # Returns with some negative ones
    s = pd.Series([0.05, -0.02, 0.03, -0.04], index=dates)

    res = calc_metrics(s, freq_factor=12)

    # Negative returns: -0.02, -0.04
    # Root Mean Square of neg over total len (4)
    expected_downside_vol = np.sqrt(((-0.02)**2 + (-0.04)**2) / 4) * np.sqrt(12)
    np.testing.assert_almost_equal(res['Downside Vol (Ann.)'], expected_downside_vol, decimal=4)

def test_calc_metrics_capture():
    dates = pd.date_range(start='2020-01-01', periods=4, freq='ME')
    s = pd.Series([0.05, -0.02, 0.04, -0.05], index=dates)
    bm = pd.Series([0.02, -0.01, 0.03, -0.02], index=dates)

    res = calc_metrics(s, freq_factor=12, bm_series=bm)

    # Up months: 0, 2
    # s up ret: (1.05 * 1.04) - 1 = 0.092
    # bm up ret: (1.02 * 1.03) - 1 = 0.0506
    expected_up_cap = ((1.05 * 1.04) - 1) / ((1.02 * 1.03) - 1)
    np.testing.assert_almost_equal(res['Upside Capture'], expected_up_cap, decimal=4)

    # Down months: 1, 3
    # s down ret: (0.98 * 0.95) - 1 = -0.069
    # bm down ret: (0.99 * 0.98) - 1 = -0.0298
    expected_down_cap = ((0.98 * 0.95) - 1) / ((0.99 * 0.98) - 1)
    np.testing.assert_almost_equal(res['Downside Capture'], expected_down_cap, decimal=4)
