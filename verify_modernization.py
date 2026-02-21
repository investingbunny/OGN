"""Test script to verify modernization parity and correctness."""

import pandas as pd
import numpy as np
import modern_ta as mta
import modern_kpis as mkpis
import math

def legacy_RSI(DF, n):
    "Legacy RSI implementation (for parity testing)"
    df = DF.copy()
    df['delta'] = df['Close'] - df['Close'].shift(1)
    df['gain'] = np.where(df['delta'] >= 0, df['delta'], 0)
    df['loss'] = np.where(df['delta'] < 0, abs(df['delta']), 0)
    avg_gain = []
    avg_loss = []
    gain = df['gain'].tolist()
    loss = df['loss'].tolist()
    for i in range(len(df)):
        if i < n:
            avg_gain.append(np.nan)
            avg_loss.append(np.nan)
        elif i == n:
            val_g = df['gain'].rolling(n).mean().tolist()[n]
            val_l = df['loss'].rolling(n).mean().tolist()[n]
            avg_gain.append(val_g)
            avg_loss.append(val_l)
        elif i > n:
            avg_gain.append(((n-1)*avg_gain[i-1] + gain[i])/n)
            avg_loss.append(((n-1)*avg_loss[i-1] + loss[i])/n)
    df['avg_gain'] = np.array(avg_gain)
    df['avg_loss'] = np.array(avg_loss)
    df['RS'] = df['avg_gain']/df['avg_loss']
    df['RSI'] = 100 - (100/(1+df['RS']))
    return df['RSI']

def test_rsi_parity():
    print("Testing RSI Parity...")
    data = {
        'Close': [100, 102, 101, 105, 107, 108, 106, 110, 112, 115, 114, 113, 116, 118, 120, 122, 121, 119, 123, 125]
    }
    df = pd.DataFrame(data)

    legacy_res = legacy_RSI(df, 14)
    modern_res = mta.RSI(df, 14)

    diff = (legacy_res - modern_res).abs().dropna()
    if not diff.empty:
        max_diff = diff.max()
        print(f"Max difference in RSI: {max_diff}")
        assert max_diff < 1e-10, "RSI Parity Failed!"
    print("RSI Parity Passed.")

def test_kpi_calculations():
    print("Testing KPI Calculations...")
    data = {
        'Close': [100.0, 110.0, 121.0, 133.1]
    }
    df = pd.DataFrame(data)

    cagr = mkpis.CAGR(df, trading_days=252)
    expected_cagr = (133.1/100)**(252/len(df)) - 1
    print(f"CAGR: {cagr}, Expected: {expected_cagr}")
    assert abs(cagr - expected_cagr) < 1e-5

    # Volatility
    vol = mkpis.Volatility(df, trading_days=252)
    daily_ret = df['Close'].pct_change().dropna()
    print(f"Daily returns:\n{daily_ret}")
    print(f"Volatility: {vol}")
    assert vol < 1e-10
    print("KPI Calculations Passed.")

if __name__ == "__main__":
    try:
        test_rsi_parity()
        test_kpi_calculations()
        print("\nAll tests passed successfully!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
