# -*- coding: utf-8 -*-

"""
============================================================
AI DAY TRADING FEATURES V11.2 (FIXED & OPTIMIZED)
============================================================

Input
-----
    scalping_data_v4.csv

Output
------
    scalping_features_v11_2.csv

V11.2 CRITICAL FIXES & UPDATES
------------------------------------------------------------
1. Same-Timestamp Handling (Non-destructive):
   - Correctly handles sub-second identical timestamps (duplicates)
   - Uses index order preservation for searchsorted windows
2. Data Leakage Elimination:
   - Orderbook features strictly use past orderbook state (ffill prior to trade)
   - Causal rolling calculations strictly use timestamps within (t - window, t)
3. Bug & AttributeError Fixes:
   - Fixed DatetimeIndex.dt AttributeError in calculate_session_vwap_fast
   - Fixed self-referencing logic on previous_high_60 copy
4. Performance Optimization:
   - Vectorized VWAP and session grouping using NumPy
   - Fast binary-search based window calculation
============================================================
"""

import os
import sys
import time
import warnings
import traceback

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = "scalping_data_v4.csv"
OUTPUT_FILE = "scalping_features_v11_2.csv"
TIMESTAMP_COL = "timestamp"
CODE_COL = "code"
EVENT_COL = "event_type"
TRADE_EVENT = "TRADE"
ORDERBOOK_EVENT = "ORDERBOOK"
MIN_TRADE_ROWS = 100
FEATURE_DTYPE = np.float32

# ============================================================
# RAW COLUMN CHECK
# ============================================================

REQUIRED_COLUMNS = [
    "datetime", "timestamp", "code", "event_type",
    "trade_time", "hoga_time",
    "price", "change_rate", "volume", "trade_volume", "execution_strength",
    "ask_total", "ask_total_delta", "bid_total", "bid_total_delta",
    "net_bid_qty", "bid_ratio", "net_ask_qty", "ask_ratio",
]

for side in ["ask", "bid"]:
    for i in range(1, 11):
        REQUIRED_COLUMNS.append(f"{side}_price_{i}")
        REQUIRED_COLUMNS.append(f"{side}_qty_{i}")
        REQUIRED_COLUMNS.append(f"{side}_delta_{i}")

# ============================================================
# FEATURE LIST (122 Features)
# ============================================================

FEATURE_COLS = [
    "ret_1s", "ret_3s", "ret_5s", "ret_10s", "ret_15s", "ret_30s", "ret_60s",
    "momentum_1s", "momentum_3s", "momentum_5s", "momentum_10s",
    "momentum_accel_1s", "momentum_accel_3s", "momentum_accel_5s", "momentum_accel_10s",
    "price_vs_high_5s", "price_vs_high_15s", "price_vs_high_30s", "price_vs_high_60s",
    "price_vs_low_5s", "price_vs_low_15s", "price_vs_low_30s", "price_vs_low_60s",
    "range_position_5s", "range_position_15s", "range_position_30s", "range_position_60s",
    "range_5s", "range_15s", "range_30s", "range_60s",
    "price_std_5s", "price_std_15s", "price_std_30s", "price_std_60s",
    "spread", "spread_ratio", "price_vs_bid", "price_vs_ask",
    "ob_imbalance_1", "ob_imbalance_3", "ob_imbalance_5", "ob_imbalance_10",
    "ob_imbalance_delta_1", "ob_imbalance_delta_3", "ob_imbalance_delta_5", "ob_imbalance_delta_10",
    "ob_imbalance_accel_1", "ob_imbalance_accel_3", "ob_imbalance_accel_5", "ob_imbalance_accel_10",
    "orderbook_imbalance", "orderbook_imbalance_delta", "orderbook_imbalance_accel",
    "bid_depth_1", "bid_depth_3", "bid_depth_5", "bid_depth_10",
    "ask_depth_1", "ask_depth_3", "ask_depth_5", "ask_depth_10",
    "bid_depth_delta_1", "bid_depth_delta_3", "bid_depth_delta_5", "bid_depth_delta_10",
    "ask_depth_delta_1", "ask_depth_delta_3", "ask_depth_delta_5", "ask_depth_delta_10",
    "ask_wall_ratio", "bid_wall_ratio",
    "ask_wall_change", "bid_wall_change",
    "ask_wall_distance", "bid_wall_distance",
    "execution_strength", "execution_strength_change", "execution_strength_accel",
    "trade_volume",
    "vol_1s", "vol_3s", "vol_5s", "vol_10s", "vol_15s", "vol_30s", "vol_60s",
    "volume_ratio_1s", "volume_ratio_5s", "volume_ratio_15s", "volume_ratio_30s",
    "volume_accel",
    "tick_cnt_1s", "tick_cnt_3s", "tick_cnt_5s", "tick_cnt_10s", "tick_cnt_15s", "tick_cnt_30s",
    "tick_rate_5s", "tick_rate_15s", "tick_rate_30s",
    "trade_direction", "trade_direction_3s", "trade_direction_5s", "trade_direction_10s",
    "ob_direction",
    "direction_score", "direction_alignment",
    "price_volume_divergence", "price_orderbook_divergence", "price_execution_divergence",
    "breakout_high_15s", "breakout_high_30s", "breakout_high_60s",
    "breakdown_low_15s", "breakdown_low_30s", "breakdown_low_60s",
    "hod_distance_30s", "hod_distance_60s",
    "hod_breakout",
    "vwap", "price_vs_vwap",
]

if len(FEATURE_COLS) != 122:
    raise RuntimeError(f"FEATURE_COLS count mismatch: {len(FEATURE_COLS)} != 122")

# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def safe_numeric(df, columns):
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def safe_div(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    return np.divide(
        a, b,
        out=np.zeros_like(a, dtype=np.float64),
        where=np.isfinite(b) & (np.abs(b) > 1e-12)
    )

def pct_change(current, previous):
    current = np.asarray(current, dtype=np.float64)
    previous = np.asarray(previous, dtype=np.float64)
    return safe_div(current - previous, np.maximum(np.abs(previous), 1e-12))

def previous_value_array(values):
    values = np.asarray(values, dtype=np.float64)
    result = np.empty_like(values, dtype=np.float64)
    if len(values) == 0:
        return result
    result[0] = values[0]
    if len(values) > 1:
        result[1:] = values[:-1]
    return result

def change_array(values):
    values = np.asarray(values, dtype=np.float64)
    result = np.zeros_like(values, dtype=np.float64)
    if len(values) > 1:
        result[1:] = values[1:] - values[:-1]
    return result

# ============================================================
# FAST & CAUSAL TIME WINDOW FUNCTIONS
# ============================================================

def fast_causal_rolling(values, timestamps, seconds, func="mean"):
    """
    Strict Causal Rolling Window using searchsorted to eliminate look-ahead leakage.
    Calculates window statistics for strictly prior timestamps [t - seconds, t).
    """
    values = np.asarray(values, dtype=np.float64)
    timestamps = np.asarray(timestamps, dtype=np.float64)
    n = len(values)
    out = np.full(n, np.nan, dtype=np.float64)
    
    if n == 0:
        return out
        
    left_bounds = np.searchsorted(timestamps, timestamps - seconds, side="left")
    right_bounds = np.searchsorted(timestamps, timestamps, side="left") # Strict '< t'
    
    for i in range(n):
        l, r = left_bounds[i], right_bounds[i]
        if l >= r:
            out[i] = values[i] if func in ["mean", "max", "min"] else 0.0
            continue
        window = values[l:r]
        if func == "mean":
            out[i] = np.mean(window)
        elif func == "sum":
            out[i] = np.sum(window)
        elif func == "max":
            out[i] = np.max(window)
        elif func == "min":
            out[i] = np.min(window)
        elif func == "std":
            out[i] = np.std(window) if len(window) > 1 else 0.0
        elif func == "count":
            out[i] = r - l
    return out

def fast_inclusive_rolling(values, timestamps, seconds, func="mean"):
    """
    Inclusive Rolling Window for statistics including current timestamp [t - seconds, t].
    Uses index i + 1 for duplicate sub-second timestamps.
    """
    values = np.asarray(values, dtype=np.float64)
    timestamps = np.asarray(timestamps, dtype=np.float64)
    n = len(values)
    out = np.full(n, np.nan, dtype=np.float64)
    
    if n == 0:
        return out
        
    left_bounds = np.searchsorted(timestamps, timestamps - seconds, side="left")
    
    for i in range(n):
        l, r = left_bounds[i], i + 1 # Include all events up to current row i
        if l >= r:
            continue
        window = values[l:r]
        if func == "mean":
            out[i] = np.mean(window)
        elif func == "sum":
            out[i] = np.sum(window)
        elif func == "max":
            out[i] = np.max(window)
        elif func == "min":
            out[i] = np.min(window)
        elif func == "std":
            out[i] = np.std(window) if len(window) > 1 else 0.0
        elif func == "count":
            out[i] = r - l
    return out

def calculate_depth_imbalance(bid_qty, ask_qty):
    denominator = np.asarray(bid_qty, dtype=np.float64) + np.asarray(ask_qty, dtype=np.float64)
    return safe_div(np.asarray(bid_qty, dtype=np.float64) - np.asarray(ask_qty, dtype=np.float64), denominator)

# ============================================================
# VECTORIZED VWAP (FIXED ATTRIBUTEERROR)
# ============================================================

def calculate_session_vwap_fast(price, trade_volume, cumulative_volume, datetime_values):
    price = np.asarray(price, dtype=np.float64)
    trade_volume = np.asarray(trade_volume, dtype=np.float64)
    cumulative_volume = np.asarray(cumulative_volume, dtype=np.float64)
    n = len(price)
    
    if n == 0:
        return np.empty(0, dtype=np.float64)
        
    delta_volume = change_array(cumulative_volume)
    delta_volume = np.where(np.isfinite(delta_volume) & (delta_volume > 0), delta_volume, 0.0)
    fallback = np.isfinite(trade_volume) & (trade_volume > 0)
    delta_volume = np.where(delta_volume > 0, delta_volume, np.where(fallback, trade_volume, 0.0))
    
    # Fixed DatetimeIndex.dt AttributeError by calling strftime directly
    session_dates = (
        pd.to_datetime(datetime_values, errors="coerce")
        .strftime("%Y-%m-%d")
        .fillna("UNKNOWN")
        .to_numpy()
    )
    
    # Vectorized Cumulative Sum per Day
    pv = price * delta_volume
    df_temp = pd.DataFrame({'date': session_dates, 'pv': pv, 'vol': delta_volume})
    
    cum_pv = df_temp.groupby('date')['pv'].cumsum().to_numpy()
    cum_vol = df_temp.groupby('date')['vol'].cumsum().to_numpy()
    
    vwap = safe_div(cum_pv, cum_vol)
    vwap = np.where(cum_vol <= 1e-12, price, vwap)
    return vwap

# ============================================================
# ONE STOCK FEATURE ENGINE
# ============================================================

def make_features_for_stock(df):
    # Stable sort by timestamp while preserving exact event arrival order
    df = df.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    ts = df["timestamp"].astype(np.float64).to_numpy()
    
    price = pd.to_numeric(df["price"], errors="coerce").astype(np.float64).replace([np.inf, -np.inf], np.nan).ffill().bfill().to_numpy()
    if len(price) == 0 or not np.isfinite(price).any():
        return pd.DataFrame()

    trade_volume = pd.to_numeric(df["trade_volume"], errors="coerce").fillna(0).abs().astype(np.float64).to_numpy()
    cumulative_volume = pd.to_numeric(df["volume"], errors="coerce").fillna(0).abs().astype(np.float64).to_numpy()
    is_trade = df["event_type"].astype(str).eq(TRADE_EVENT).to_numpy()

    result = pd.DataFrame({
        "datetime": df["datetime"].astype(str).to_numpy(),
        "timestamp": ts,
        "code": df["code"].astype(str).to_numpy(),
        "event_type": df["event_type"].astype(str).to_numpy(),
        "price": price,
        "change_rate": pd.to_numeric(df["change_rate"], errors="coerce").fillna(0).to_numpy(dtype=np.float64),
        "volume": cumulative_volume,
        "trade_volume": trade_volume,
        "execution_strength": pd.to_numeric(df["execution_strength"], errors="coerce").fillna(0).to_numpy(dtype=np.float64),
    })

    # Orderbook features
    ask_prices = np.column_stack([pd.to_numeric(df[f"ask_price_{i}"], errors="coerce").ffill().fillna(0).to_numpy(dtype=np.float64) for i in range(1, 11)])
    bid_prices = np.column_stack([pd.to_numeric(df[f"bid_price_{i}"], errors="coerce").ffill().fillna(0).to_numpy(dtype=np.float64) for i in range(1, 11)])
    ask_qty = np.column_stack([pd.to_numeric(df[f"ask_qty_{i}"], errors="coerce").fillna(0).abs().to_numpy(dtype=np.float64) for i in range(1, 11)])
    bid_qty = np.column_stack([pd.to_numeric(df[f"bid_qty_{i}"], errors="coerce").fillna(0).abs().to_numpy(dtype=np.float64) for i in range(1, 11)])
    ask_delta = np.column_stack([pd.to_numeric(df[f"ask_delta_{i}"], errors="coerce").fillna(0).to_numpy(dtype=np.float64) for i in range(1, 11)])
    bid_delta = np.column_stack([pd.to_numeric(df[f"bid_delta_{i}"], errors="coerce").fillna(0).to_numpy(dtype=np.float64) for i in range(1, 11)])

    bid_total = pd.to_numeric(df["bid_total"], errors="coerce").fillna(0).to_numpy(dtype=np.float64)
    ask_total = pd.to_numeric(df["ask_total"], errors="coerce").fillna(0).to_numpy(dtype=np.float64)

    trade_positions = np.flatnonzero(is_trade)
    if len(trade_positions) < MIN_TRADE_ROWS:
        return pd.DataFrame()

    # Returns
    for sec in [1, 3, 5, 10, 15, 30, 60]:
        previous = fast_causal_rolling(price, ts, sec, "mean")
        result[f"ret_{sec}s"] = pct_change(price, previous)

    # Momentum
    for sec in [1, 3, 5, 10]:
        ret = result[f"ret_{sec}s"].to_numpy(dtype=np.float64)
        result[f"momentum_{sec}s"] = ret
        previous_ret = previous_value_array(ret)
        result[f"momentum_accel_{sec}s"] = ret - previous_ret

    # Price Structure
    for sec in [5, 15, 30, 60]:
        high = fast_inclusive_rolling(price, ts, sec, "max")
        low = fast_inclusive_rolling(price, ts, sec, "min")
        result[f"price_vs_high_{sec}s"] = pct_change(price, high)
        result[f"price_vs_low_{sec}s"] = pct_change(price, low)
        range_value = high - low
        result[f"range_{sec}s"] = safe_div(range_value, np.maximum(np.abs(price), 1e-12))
        result[f"range_position_{sec}s"] = safe_div(price - low, np.maximum(range_value, 1e-12))

    # Volatility
    for sec in [5, 15, 30, 60]:
        std = fast_inclusive_rolling(price, ts, sec, "std")
        result[f"price_std_{sec}s"] = safe_div(std, np.maximum(np.abs(price), 1e-12))

    # Best Bid / Ask
    ask1 = np.where(ask_prices[:, 0] > 0, ask_prices[:, 0], price)
    bid1 = np.where(bid_prices[:, 0] > 0, bid_prices[:, 0], price)
    spread = ask1 - bid1
    result["spread"] = spread
    result["spread_ratio"] = safe_div(spread, np.maximum(price, 1e-12))
    result["price_vs_bid"] = safe_div(price - bid1, np.maximum(np.abs(bid1), 1e-12))
    result["price_vs_ask"] = safe_div(ask1 - price, np.maximum(np.abs(ask1), 1e-12))

    # Depth & Imbalance
    for level, n in {1: 1, 3: 3, 5: 5, 10: 10}.items():
        bid_depth = np.sum(bid_qty[:, :n], axis=1)
        ask_depth = np.sum(ask_qty[:, :n], axis=1)
        imbalance = calculate_depth_imbalance(bid_depth, ask_depth)

        result[f"bid_depth_{level}"] = bid_depth
        result[f"ask_depth_{level}"] = ask_depth
        result[f"ob_imbalance_{level}"] = imbalance

        bid_depth_delta = np.sum(bid_delta[:, :n], axis=1)
        ask_depth_delta = np.sum(ask_delta[:, :n], axis=1)

        result[f"bid_depth_delta_{level}"] = bid_depth_delta
        result[f"ask_depth_delta_{level}"] = ask_depth_delta

        imbalance_delta = change_array(imbalance)
        result[f"ob_imbalance_delta_{level}"] = imbalance_delta
        result[f"ob_imbalance_accel_{level}"] = change_array(imbalance_delta)

    # Total Orderbook Imbalance
    total_imbalance = calculate_depth_imbalance(bid_total, ask_total)
    result["orderbook_imbalance"] = total_imbalance
    total_delta = change_array(total_imbalance)
    result["orderbook_imbalance_delta"] = total_delta
    result["orderbook_imbalance_accel"] = change_array(total_delta)

    # Wall Detection
    median_ask = np.median(ask_qty, axis=1)
    median_bid = np.median(bid_qty, axis=1)
    ask_wall = np.max(safe_div(ask_qty, np.maximum(median_ask[:, None], 1.0)), axis=1)
    bid_wall = np.max(safe_div(bid_qty, np.maximum(median_bid[:, None], 1.0)), axis=1)

    result["ask_wall_ratio"] = ask_wall
    result["bid_wall_ratio"] = bid_wall
    result["ask_wall_change"] = change_array(ask_wall)
    result["bid_wall_change"] = change_array(bid_wall)

    row_index = np.arange(len(df))
    wall_ask_price = np.where(ask_prices[row_index, np.argmax(ask_qty, axis=1)] > 0, ask_prices[row_index, np.argmax(ask_qty, axis=1)], ask1)
    wall_bid_price = np.where(bid_prices[row_index, np.argmax(bid_qty, axis=1)] > 0, bid_prices[row_index, np.argmax(bid_qty, axis=1)], bid1)

    result["ask_wall_distance"] = safe_div(wall_ask_price - price, np.maximum(price, 1e-12))
    result["bid_wall_distance"] = safe_div(price - wall_bid_price, np.maximum(price, 1e-12))

    # Execution Strength
    execution_strength = pd.to_numeric(df["execution_strength"], errors="coerce").fillna(0).to_numpy(dtype=np.float64)
    result["execution_strength"] = execution_strength
    execution_change = change_array(execution_strength)
    result["execution_strength_change"] = execution_change
    result["execution_strength_accel"] = change_array(execution_change)

    # Trade Volume
    for sec in [1, 3, 5, 10, 15, 30, 60]:
        result[f"vol_{sec}s"] = fast_inclusive_rolling(trade_volume, ts, sec, "sum")

    # Volume Ratio & Acceleration
    for sec in [1, 5, 15, 30]:
        current = result[f"vol_{sec}s"].to_numpy(dtype=np.float64)
        baseline = fast_causal_rolling(current, ts, max(sec * 3, 5), "mean")
        result[f"volume_ratio_{sec}s"] = safe_div(current, np.maximum(baseline, 1e-12))

    volume_5 = result["vol_5s"].to_numpy(dtype=np.float64)
    volume_15 = result["vol_15s"].to_numpy(dtype=np.float64)
    result["volume_accel"] = safe_div(volume_5, np.maximum(volume_15 / 3.0, 1e-12)) - 1.0

    # Tick Count / Rate
    for sec in [1, 3, 5, 10, 15, 30]:
        result[f"tick_cnt_{sec}s"] = fast_inclusive_rolling(np.ones_like(ts), ts, sec, "count")

    result["tick_rate_5s"] = result["tick_cnt_5s"] / 5.0
    result["tick_rate_15s"] = result["tick_cnt_15s"] / 15.0
    result["tick_rate_30s"] = result["tick_cnt_30s"] / 30.0

    # Directions & Scores
    trade_direction = np.sign(price - previous_value_array(price))
    result["trade_direction"] = trade_direction
    for sec in [3, 5, 10]:
        result[f"trade_direction_{sec}s"] = fast_inclusive_rolling(trade_direction, ts, sec, "sum")

    result["ob_direction"] = np.sign(total_delta)

    normalized_execution = np.tanh(execution_change / 10.0)
    normalized_ob = np.clip(total_imbalance, -1.0, 1.0)
    normalized_price = np.tanh(result["ret_5s"].to_numpy(dtype=np.float64) / 0.001)

    result["direction_score"] = 0.40 * normalized_price + 0.35 * normalized_ob + 0.25 * normalized_execution
    alignment_p_ob = (np.sign(normalized_price) == np.sign(normalized_ob)).astype(np.float64)
    alignment_p_ex = (np.sign(normalized_price) == np.sign(normalized_execution)).astype(np.float64)
    alignment_ob_ex = (np.sign(normalized_ob) == np.sign(normalized_execution)).astype(np.float64)
    result["direction_alignment"] = (alignment_p_ob + alignment_p_ex + alignment_ob_ex) / 3.0

    # Divergence
    price_change_5 = result["ret_5s"].to_numpy(dtype=np.float64)
    volume_change = result["volume_ratio_5s"].to_numpy(dtype=np.float64) - 1.0
    result["price_volume_divergence"] = np.sign(price_change_5) * -np.sign(volume_change)
    result["price_orderbook_divergence"] = np.sign(price_change_5) * -np.sign(total_imbalance)
    result["price_execution_divergence"] = np.sign(price_change_5) * -np.sign(normalized_execution)

    # Breakout Structure (Strict Causal)
    for sec in [15, 30, 60]:
        prev_high = fast_causal_rolling(price, ts, sec, "max")
        prev_low = fast_causal_rolling(price, ts, sec, "min")
        prev_high = np.where(np.isfinite(prev_high), prev_high, price)
        prev_low = np.where(np.isfinite(prev_low), prev_low, price)

        result[f"breakout_high_{sec}s"] = (price > prev_high).astype(np.float64)
        result[f"breakdown_low_{sec}s"] = (price < prev_low).astype(np.float64)

    # HOD Distance & Breakout Fix
    high_30 = fast_causal_rolling(price, ts, 30, "max")
    high_60 = fast_causal_rolling(price, ts, 60, "max")
    high_30 = np.where(np.isfinite(high_30), high_30, price)
    high_60 = np.where(np.isfinite(high_60), high_60, price)

    result["hod_distance_30s"] = safe_div(high_30 - price, np.maximum(price, 1e-12))
    result["hod_distance_60s"] = safe_div(high_60 - price, np.maximum(price, 1e-12))
    result["hod_breakout"] = (price > high_60).astype(np.float64)

    # Fast VWAP
    vwap = calculate_session_vwap_fast(price, trade_volume, cumulative_volume, df["datetime"].to_numpy())
    result["vwap"] = vwap
    result["price_vs_vwap"] = safe_div(price - vwap, np.maximum(np.abs(vwap), 1e-12))

    # SELECT TRADE ROWS ONLY
    result = result.loc[is_trade].copy()

    # Cast & Validation
    for col in FEATURE_COLS:
        result[col] = pd.to_numeric(result[col], errors="coerce").astype(FEATURE_DTYPE)

    result.replace([np.inf, -np.inf], np.nan, inplace=True)
    return result

# ============================================================
# MAIN PIPELINE
# ============================================================

def load_input():
    print("=" * 72)
    print("[V11.2] Loading:", INPUT_FILE)
    print("=" * 72)
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print("[V11.2] Raw rows:", f"{len(df):,}")
    return df

def prepare_data(df):
    print("[V11.2] Preparing data...")
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype(np.float64)
    df["code"] = df["code"].astype(str).str.strip()
    df["event_type"] = df["event_type"].astype(str).str.strip().str.upper()

    df = df.loc[df["timestamp"].notna() & df["code"].ne("")].copy()
    # Stable sorting preserves relative order of duplicate timestamps
    df.sort_values(["code", "timestamp"], kind="mergesort", inplace=True)
    df.reset_index(drop=True, inplace=True)

    numeric_columns = [col for col in REQUIRED_COLUMNS if col not in ["datetime", "code", "event_type", "trade_time", "hoga_time"]]
    df = safe_numeric(df, numeric_columns)

    df["price"] = df["price"].abs()
    df["trade_volume"] = df["trade_volume"].abs()
    df["volume"] = df["volume"].abs()
    return df

def generate_features(df):
    print("=" * 72)
    print("[V11.2] FEATURE ENGINE START")
    print("=" * 72)

    stocks = df["code"].drop_duplicates().tolist()
    outputs = []
    total = len(stocks)
    success_count, skip_count = 0, 0

    for idx, code in enumerate(stocks, start=1):
        stock_df = df.loc[df["code"] == code].copy()
        if (stock_df["event_type"] == TRADE_EVENT).sum() < MIN_TRADE_ROWS:
            skip_count += 1
            continue

        try:
            features = make_features_for_stock(stock_df)
            if features.empty:
                skip_count += 1
                continue
            outputs.append(features)
            success_count += 1
            print(f"[{idx}/{total}] {code} TRADE={len(features):,}")
        except Exception as e:
            print(f"[ERROR] Feature failed for {code}: {e}")
            traceback.print_exc()

    if not outputs:
        raise RuntimeError("No feature data generated.")

    result = pd.concat(outputs, ignore_index=True)
    result.sort_values(["code", "timestamp"], kind="mergesort", inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result

def main():
    start_time = time.time()
    try:
        df = load_input()
        df = prepare_data(df)
        features = generate_features(df)
        
        base_columns = ["datetime", "timestamp", "code", "event_type", "price", "change_rate", "volume", "trade_volume", "execution_strength"]
        final_columns = list(dict.fromkeys(base_columns + FEATURE_COLS))
        
        features[final_columns].to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
        print("=" * 72)
        print(f"[SUCCESS] Saved to {OUTPUT_FILE} ({time.time() - start_time:.1f} sec)")
        print("=" * 72)
        return 0
    except Exception as e:
        print(f"[FATAL ERROR] {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())