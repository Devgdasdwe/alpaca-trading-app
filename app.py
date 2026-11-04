"""
Alpaca Paper Trading Bot - Streamlit Web App
============================================
Educational / paper-trading only.
NOT financial advice. Use at your own risk.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# -------------------------------------------------
# Page config
# -------------------------------------------------
st.set_page_config(
    page_title="Alpaca Auto Trader",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def init_clients(api_key: str, secret_key: str, paper: bool = True):
    """Create trading + data clients."""
    trading = TradingClient(api_key, secret_key, paper=paper)
    data = StockHistoricalDataClient(api_key, secret_key)
    return trading, data


def get_account(trading: TradingClient):
    return trading.get_account()


def get_positions(trading: TradingClient):
    positions = trading.get_all_positions()
    if not positions:
        return pd.DataFrame()
    rows = []
    for p in positions:
        rows.append({
            "Symbol": p.symbol,
            "Qty": float(p.qty),
            "Avg Entry": float(p.avg_entry_price),
            "Current Price": float(p.current_price),
            "Market Value": float(p.market_value),
            "Unrealized P/L": float(p.unrealized_pl),
            "Unrealized P/L %": float(p.unrealized_plpc) * 100,
        })
    return pd.DataFrame(rows)


def get_recent_orders(trading: TradingClient, limit: int = 20):
    req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit)
    orders = trading.get_orders(filter=req)
    if not orders:
        return pd.DataFrame()
    rows = []
    for o in orders:
        rows.append({
            "Symbol": o.symbol,
            "Side": o.side.value,
            "Qty": float(o.qty) if o.qty else None,
            "Type": o.type.value,
            "Status": o.status.value,
            "Submitted": o.submitted_at,
            "Filled Avg": float(o.filled_avg_price) if o.filled_avg_price else None,
        })
    return pd.DataFrame(rows)


def place_market_order(trading: TradingClient, symbol: str, qty: float, side: str):
    order_data = MarketOrderRequest(
        symbol=symbol.upper(),
        qty=qty,
        side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY
    )
    return trading.submit_order(order_data)


def get_bars(data_client: StockHistoricalDataClient, symbol: str, days: int = 60):
    end = datetime.now()
    start = end - timedelta(days=days)
    req = StockBarsRequest(
        symbol_or_symbols=symbol.upper(),
        timeframe=TimeFrame.Day,
        start=start,
        end=end
    )
    bars = data_client.get_stock_bars(req)
    df = bars.df
    if df.empty:
        return pd.DataFrame()
    # Reset multi-index if present
    if isinstance(df.index, pd.MultiIndex):
        df = df.reset_index(level=0, drop=True)
    df = df.reset_index()
    return df


def calculate_sma_signals(df: pd.DataFrame, fast: int = 10, slow: int = 30):
    """Simple Moving Average crossover signals."""
    if len(df) < slow + 5:
        return df, None
    df = df.copy()
    df["SMA_Fast"] = df["close"].rolling(window=fast).mean()
    df["SMA_Slow"] = df["close"].rolling(window=slow).mean()
    df["Signal"] = 0
    # Golden cross (buy) / Death cross (sell)
    df.loc[df["SMA_Fast"] > df["SMA_Slow"], "Signal"] = 1
    df.loc[df["SMA_Fast"] < df["SMA_Slow"], "Signal"] = -1
    df["Position"] = df["Signal"].diff()
    return df, df["Position"].iloc[-1] if not df.empty else None


# -------------------------------------------------
# Sidebar – Credentials & Settings
# -------------------------------------------------
st.sidebar.title("🔐 Alpaca Connection")
st.sidebar.markdown("Use **Paper** keys only while testing.")

api_key = st.sidebar.text_input("API Key ID", type="password", help="From Alpaca Paper dashboard")
secret_key = st.sidebar.text_input("Secret Key", type="password")
paper_mode = st.sidebar.checkbox("Paper Trading Mode", value=True)

st.sidebar.divider()
st.sidebar.subheader("Strategy Settings")
default_symbol = st.sidebar.text_input("Default Symbol", value="SPY")
fast_sma = st.sidebar.number_input("Fast SMA", min_value=5, max_value=50, value=10)
slow_sma = st.sidebar.number_input("Slow SMA", min_value=10, max_value=200, value=30)
trade_qty = st.sidebar.number_input("Shares per trade", min_value=1, value=5)

st.sidebar.divider()
st.sidebar.caption("⚠️ Educational use only. Not financial advice. Paper trade first.")

# -------------------------------------------------
# Main App
# -------------------------------------------------
st.title("📈 Alpaca Auto Trader")
st.caption("Paper trading bot • Moving Average Crossover strategy")

if not api_key or not secret_key:
    st.info("👈 Enter your **Alpaca Paper API keys** in the sidebar to get started.")
    st.markdown("""
    ### Quick Setup
    1. Create a free account at [alpaca.markets](https://alpaca.markets)
    2. Switch to **Paper Trading** dashboard
    3. Generate API keys
    4. Paste them in the sidebar
    """)
    st.stop()

# Connect
try:
    trading_client, data_client = init_clients(api_key, secret_key, paper=paper_mode)
    account = get_account(trading_client)
except Exception as e:
    st.error(f"Connection failed: {e}")
    st.stop()

# -------------------------------------------------
# Account Overview
# -------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Equity", f"${float(account.equity):,.2f}")
col2.metric("Cash", f"${float(account.cash):,.2f}")
col3.metric("Buying Power", f"${float(account.buying_power):,.2f}")
col4.metric("Status", account.status.value)

if paper_mode:
    st.success("✅ Connected to **Paper Trading** account")
else:
    st.warning("⚠️ Connected to **LIVE** account — real money at risk!")

# -------------------------------------------------
# Tabs
# -------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["📊 Positions & Orders", "🛒 Manual Trade", "🤖 Auto Strategy", "📈 Chart & Signals"])

with tab1:
    st.subheader("Open Positions")
    positions_df = get_positions(trading_client)
    if positions_df.empty:
        st.info("No open positions.")
    else:
        st.dataframe(positions_df.style.format({
            "Avg Entry": "${:.2f}",
            "Current Price": "${:.2f}",
            "Market Value": "${:.2f}",
            "Unrealized P/L": "${:.2f}",
            "Unrealized P/L %": "{:.2f}%",
        }), use_container_width=True)

    st.subheader("Recent Orders")
    orders_df = get_recent_orders(trading_client)
    if orders_df.empty:
        st.info("No recent orders.")
    else:
        st.dataframe(orders_df, use_container_width=True)

with tab2:
    st.subheader("Place Manual Market Order")
    with st.form("manual_order"):
        c1, c2, c3 = st.columns(3)
        symbol = c1.text_input("Symbol", value=default_symbol).upper()
        qty = c2.number_input("Quantity", min_value=1, value=1)
        side = c3.selectbox("Side", ["buy", "sell"])
        submitted = st.form_submit_button("Submit Order", type="primary")

        if submitted:
            try:
                order = place_market_order(trading_client, symbol, qty, side)
                st.success(f"Order submitted! ID: {order.id} | {side.upper()} {qty} {symbol}")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Order failed: {e}")

with tab3:
    st.subheader("🤖 Moving Average Crossover Bot")
    st.markdown(f"""
    **Strategy rules**
    - Fast SMA ({fast_sma}) crosses **above** Slow SMA ({slow_sma}) → **BUY**
    - Fast SMA crosses **below** Slow SMA → **SELL**
    - Trades {trade_qty} shares of the selected symbol
    """)

    symbol_auto = st.text_input("Symbol to trade", value=default_symbol).upper()
    run_once = st.button("▶️ Run Strategy Once", type="primary")

    if run_once:
        with st.spinner(f"Analyzing {symbol_auto}..."):
            try:
                bars = get_bars(data_client, symbol_auto, days=max(slow_sma * 3, 90))
                if bars.empty:
                    st.error("No market data returned. Check symbol or market hours.")
                else:
                    df, last_signal = calculate_sma_signals(ba
