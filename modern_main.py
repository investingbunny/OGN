"""Demonstration of the modernized stock analysis toolkit."""

import asyncio
from data_provider import DataProvider
import modern_ta as mta
import modern_kpis as mkpis
import modern_viz as mviz

async def main():
    # 1. Fetch data using modern DataProvider with PyArrow backend
    provider = DataProvider(use_pyarrow=True)
    ticker = "AAPL"
    print(f"Fetching data for {ticker}...")
    df = provider.fetch_ticker_data(ticker, "2023-01-01", "2024-01-01")

    if df.empty:
        print("No data found.")
        return

    # 2. Calculate Technical Indicators using vectorized operations
    print("Calculating technical indicators...")
    macd_df = mta.MACD(df)
    df = df.join(macd_df)

    df['RSI'] = mta.RSI(df)

    bb_df = mta.BollBnd(df)
    df = df.join(bb_df)

    # 3. Calculate Financial KPIs
    print("Calculating KPIs...")
    cagr = mkpis.CAGR(df)
    vol = mkpis.Volatility(df)
    sharpe = mkpis.Sharpe(df, rf=0.05)

    print(f"Results for {ticker}:")
    print(f"  CAGR: {cagr:.2%}")
    print(f"  Volatility: {vol:.2%}")
    print(f"  Sharpe Ratio: {sharpe:.2f}")

    # 4. Fibonacci Levels
    latest_high = df['High'].max()
    latest_low = df['Low'].min()
    fib = mta.fibonacci_levels(latest_high, latest_low)
    print(f"Fibonacci Levels: {fib}")

    # 5. Generate Interactive Visualization (Plotly)
    # This would typically be shown in a browser or Jupyter notebook.
    fig = mviz.create_interactive_chart(df, ticker)
    print("Interactive chart generated. (Use fig.show() in a local environment)")

if __name__ == "__main__":
    asyncio.run(main())
