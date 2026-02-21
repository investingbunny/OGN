"""Modern Visualization module for stock analysis.

This module provides interactive charts using Plotly, replacing static
Matplotlib plots.
"""

from typing import Optional, List
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_interactive_chart(
    df: pd.DataFrame,
    ticker: str,
    indicators: Optional[List[str]] = None
) -> go.Figure:
    """Creates an interactive Plotly chart with candlesticks and indicators.

    Args:
        df: Pandas DataFrame with OHLCV data and indicators.
        ticker: Ticker symbol for the title.
        indicators: List of indicators to include (e.g., ['RSI', 'MACD', 'BB']).
            If None, includes all indicators present in the DataFrame.

    Returns:
        go.Figure: Interactive Plotly figure.
    """
    # Filter indicators based on presence in columns and the indicators list
    available_cols = set(df.columns)

    show_rsi = "RSI" in available_cols and (indicators is None or "RSI" in indicators)
    show_macd = "MACD" in available_cols and (indicators is None or "MACD" in indicators)
    show_bb = ("BB_Upper" in available_cols and "BB_Lower" in available_cols) and \
              (indicators is None or "BB" in indicators)

    # Create subplots
    rows = 1
    if show_rsi:
        rows += 1
    if show_macd:
        rows += 1

    row_heights = [0.6] + [0.2] * (rows - 1)

    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=row_heights
    )

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            name=f"{ticker} OHLC"
        ),
        row=1, col=1
    )

    # Overlays (Bollinger Bands)
    if show_bb:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['BB_Upper'],
                name='BB Upper',
                line=dict(color='rgba(173, 216, 230, 0.4)')
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['BB_Lower'],
                name='BB Lower',
                line=dict(color='rgba(173, 216, 230, 0.4)'),
                fill='tonexty'
            ),
            row=1, col=1
        )

    current_row = 2
    if show_macd:
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], name='MACD'), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD_Signal'], name='Signal'), row=current_row, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], name='Hist'), row=current_row, col=1)
        current_row += 1

    if show_rsi:
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name='RSI'), row=current_row, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=current_row, col=1)

    fig.update_layout(
        title=f"{ticker} Analysis",
        xaxis_rangeslider_visible=False,
        height=400 + 200 * rows,
        template="plotly_dark"
    )

    return fig
