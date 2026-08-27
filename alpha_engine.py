import datetime
import json
import itertools
import urllib.request
import logging
import os
import time
import numpy as np
import pandas as pd
import statsmodels.api as sm
import yfinance as yf
from statsmodels.tsa.stattools import coint

# =====================================================================
# ⚙️ SYSTEM CONFIGURATION PANEL (Pulls Securely From GitHub Environment)
# =====================================================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

ENTRY_Z = 2.3                    # Adjusted signal boundary based on your current setup
MAX_P_VALUE_GATE = 0.05          # High statistical confidence threshold
MIN_SHARPE_GATE = 0.65           # Elevated backtest quality baseline
MAX_DD_LIMIT = -20.0             # Strict historical drawdown threshold
LOOKBACK_HOURS = 120             # Trailing lookback window for spread analysis
MAX_HALF_LIFE_DAYS = 6.0         # Maximum allowed mean reversion half-life (in days)
MAX_VOLUME_ANOMALY = 3.5         # Filters out breakout stocks trading at >3.5x typical volume

INITIAL_CAPITAL = 10000
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# =====================================================================
# TELEMETRY DISPATCH HOOK (High-Conviction Design Layout)
# =====================================================================
def dispatch_discord_alert(data):
    if not DISCORD_WEBHOOK_URL: return
    
    emoji = "🔥 HIGH-CONVICTION SHORT" if "SHORT" in data["Action State"] else "🔥 HIGH-CONVICTION LONG"
    color_hex = 16720436 if "SHORT" in data["Action State"] else 3394611

    payload = {
        "username": "Quant Alpha Alpha-Force",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2822/2822841.png",
        "embeds": [{
            "title": f"[{emoji}] Cointegrated Structural Execution Signal",
            "description": f"An elite institutional structural dislocation has passed all high-conviction quality filter blocks within the **{data['Sub-Industry']}** matrix.",
            "color": color_hex,
            "fields": [
                {"name": "Target Pair Asset Config", "value": f"`{data['Pair Name']}`", "inline": True},
                {"name": "Dynamic Beta (Hedge)", "value": f"{data['Beta']:.4f}", "inline": True},
                {"name": "Intraday Entry Z-Score", "value": f"**{data['Current Intraday Z-Score']:.2f}**", "inline": False},
                {"name": "Relationship Half-Life", "value": f"`{data['Half-Life Days']:.1f} Trading Days`", "inline": True},
                {"name": "Cointegration P-Value (2Y)", "value": f"{data['Cointegration P-Value']:.4f}", "inline": True},
                {"name": "Historical Sharpe Ratio", "value": f"{data['Historical Sharpe Ratio']:.2f}", "inline": True},
                {"name": "Context Spot Values", "value": f"`{data['Stock A']}`: ${data['Price A']:.2f} | `{data['Stock B']}`: ${data['Price B']:.2f}", "inline": False}
            ],
            "footer": {"text": "Quant System Alpha Engine • Multi-Timeframe Validated"},
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }]
    }

    try:
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req) as response:
            if response.status in [200, 204]:
                logging.info(f"High-conviction alert broadcasted for {data['Pair Name']}")
    except Exception as err:
        logging.error(f"Discord telemetry payload delivery failed: {err}")

# =====================================================================
# CORE PIPELINES & ADVANCED FILTER VALIDATORS
# =====================================================================
def harvest_sp500_homogeneity():
    """Scrapes S&P 500 constituents and extracts tight GICS Sub-Industries."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        tables = pd.read_html(r.read())
    df = tables[0].rename(columns={"Symbol": "Ticker", "GICS Sub-Industry": "Sub-Industry"})
    df["Ticker"] = df["Ticker"].str.replace(".", "-", regex=False)
    
    # Drop rows missing Sub-Industry metadata to protect pair homogeneity logic
    return df[["Ticker", "Sub-Industry"]].dropna(subset=["Sub-Industry"])

def fetch_market_data_chunked(tickers, period, interval, chunk_size=100, pause_seconds=1.0):
    """Download market data safely, retry failures, and report incomplete coverage."""
    price_dfs = []
    volume_dfs = []
    failed_tickers = set()

    def extract_frames(raw, requested_tickers):
        """Normalize yfinance output into ticker-column price and volume frames."""
        if raw is None or raw.empty:
            return pd.DataFrame(), pd.DataFrame()

        if isinstance(raw.columns, pd.MultiIndex):
            available_fields = set(raw.columns.get_level_values(0))
            price_col = "Adj Close" if "Adj Close" in available_fields else "Close"
            prices = raw[price_col].copy()
            volumes = raw["Volume"].copy() if "Volume" in available_fields else pd.DataFrame()
        else:
            price_col = "Adj Close" if "Adj Close" in raw.columns else "Close"
            prices = raw[[price_col]].copy()
            prices.columns = requested_tickers
            volumes = raw[["Volume"]].copy() if "Volume" in raw.columns else pd.DataFrame()
            if not volumes.empty:
                volumes.columns = requested_tickers

        if isinstance(prices, pd.Series):
            prices = prices.to_frame(name=requested_tickers[0])
        if isinstance(volumes, pd.Series):
            volumes = volumes.to_frame(name=requested_tickers[0])

        prices.columns = [
            str(c).replace("'", "").replace("(", "").replace(")", "")
            .replace(",", "").strip()
            for c in prices.columns
        ]
        if not volumes.empty:
            volumes.columns = [
                str(c).replace("'", "").replace("(", "").replace(")", "")
                .replace(",", "").strip()
                for c in volumes.columns
            ]

        return prices, volumes

    def download_with_retries(requested_tickers, label):
        """Use serialized yfinance downloads to avoid SQLite cache contention."""
        for attempt in range(1, 4):
            try:
                raw = yf.download(
                    requested_tickers,
                    period=period,
                    interval=interval,
                    progress=False,
                    group_by="column",
                    threads=False,
                    timeout=30,
                )
                if not raw.empty:
                    return raw
                logging.warning(
                    f"{label}, attempt {attempt}/3 returned no data."
                )
            except Exception as err:
                logging.warning(
                    f"{label}, attempt {attempt}/3 failed: {err}"
                )

            if attempt < 3:
                time.sleep(attempt * 3)

        return pd.DataFrame()

    ticker_chunks = [
        tickers[i:i + chunk_size]
        for i in range(0, len(tickers), chunk_size)
    ]
    logging.info(
        f"Downloading {interval} data across {len(ticker_chunks)} chunk(s)..."
    )

    for idx, chunk in enumerate(ticker_chunks):
        raw = download_with_retries(chunk, f"Chunk {idx + 1}")
        prices, volumes = extract_frames(raw, chunk)

        if not prices.empty:
            price_dfs.append(prices)
        if not volumes.empty:
            volume_dfs.append(volumes)

        returned_tickers = {
            ticker
            for ticker in chunk
            if ticker in prices.columns and prices[ticker].notna().any()
        }
        missing_tickers = [
            ticker for ticker in chunk if ticker not in returned_tickers
        ]

        if missing_tickers:
            logging.warning(
                f"Chunk {idx + 1} missing {interval} data for "
                f"{', '.join(missing_tickers)}; retrying individually."
            )

        for ticker in missing_tickers:
            retry_raw = download_with_retries(
                [ticker], f"Individual retry for {ticker}"
            )
            retry_prices, retry_volumes = extract_frames(retry_raw, [ticker])

            if (
                ticker in retry_prices.columns
                and retry_prices[ticker].notna().any()
            ):
                price_dfs.append(retry_prices[[ticker]])
                if ticker in retry_volumes.columns:
                    volume_dfs.append(retry_volumes[[ticker]])
                logging.info(f"Recovered missing {interval} data for {ticker}.")
            else:
                failed_tickers.add(ticker)
                logging.error(
                    f"Final {interval} download failure for {ticker} "
                    "after three individual attempts."
                )

        time.sleep(pause_seconds)

    # Preserve missing observations instead of forward-filling stale prices.
    # Pair calculations will use only timestamps where both stocks have data.
    merged_prices = (
        pd.concat(price_dfs, axis=1)
        if price_dfs else pd.DataFrame()
    )
    merged_volumes = (
        pd.concat(volume_dfs, axis=1)
        if volume_dfs else pd.DataFrame()
    )

    # Keep the latest copy so an individually recovered ticker replaces an
    # all-null column returned by the original batch.
    if not merged_prices.empty:
        merged_prices = merged_prices.loc[
            :, ~merged_prices.columns.duplicated(keep="last")
        ]
    if not merged_volumes.empty:
        merged_volumes = merged_volumes.loc[
            :, ~merged_volumes.columns.duplicated(keep="last")
        ]

    unresolved = sorted(
        ticker for ticker in tickers
        if (
            ticker not in merged_prices.columns
            or not merged_prices[ticker].notna().any()
        )
    )
    unresolved = sorted(set(unresolved) | failed_tickers)

    if unresolved:
        logging.warning(
            f"{interval} download completed with degraded coverage: "
            f"{len(unresolved)}/{len(tickers)} ticker(s) unavailable - "
            f"{', '.join(unresolved)}"
        )
    else:
        logging.info(
            f"{interval} download coverage verified: "
            f"{len(tickers)}/{len(tickers)} tickers available."
        )

    return merged_prices, merged_volumes

def verify_multi_window_cointegration(df, t1, t2):
    """Filter 1: Validates that cointegration persists across multiple historical horizons."""
    try:
        pair_df = df[[t1, t2]].dropna()
        if len(pair_df) < 150: return False, 1.0
        
        # Window A: Full 2-Year Horizon
        _, p_2y, _ = coint(pair_df[t1], pair_df[t2])
        if p_2y > MAX_P_VALUE_GATE: return False, p_2y
        
        # Window B: 1-Year Mid Horizon
        _, p_1y, _ = coint(pair_df[t1].tail(252), pair_df[t2].tail(252))
        if p_1y > 0.10: return False, p_2y 
        
        return True, p_2y
    except Exception:
        return False, 1.0

def calculate_ou_half_life(spreads_series):
    """Filter 3: Models the spread via an Ornstein-Uhlenbeck process to extract reversion half-life velocity."""
    try:
        df_ou = pd.DataFrame({"X": spreads_series})
        df_ou["X_lag"] = df_ou["X"].shift(1)
        df_ou["dX"] = df_ou["X"] - df_ou["X_lag"]
        df_ou = df_ou.dropna()
        
        X_mat = sm.add_constant(df_ou["X_lag"])
        model = sm.OLS(df_ou["dX"], X_mat).fit()
        beta_coeff = model.params.iloc[1]
        
        if beta_coeff >= 0: 
            return 999.0 
            
        theta = -np.log(1 + beta_coeff)
        half_life_hours = np.log(2) / theta
        return half_life_hours / 7.0 
    except Exception:
        return 999.0

def audit_macro_historical_profile(df, t1, t2):
    pair_df = df[[t1, t2]].dropna().copy()
    if len(pair_df) < 150: return None
    y, x = pair_df[t1].values, pair_df[t2].values
    X_mat = np.vstack([np.ones(len(x)), x]).T
    try:
        beta = np.linalg.lstsq(X_mat, y, rcond=None)[0][1]
    except Exception:
        return None
        
    spreads = pair_df[t1] - (beta * pair_df[t2])
    rolling_mean = spreads.shift(1).rolling(window=60).mean()
    rolling_std = spreads.shift(1).rolling(window=60).std()
    pair_df["z"] = np.where(rolling_std != 0, (spreads - rolling_mean) / rolling_std, 0)
    
    pos_vector, curr = np.zeros(len(pair_df)), 0
    for i, z in enumerate(pair_df["z"].values):
        if abs(z) >= 3.5: curr = 0
        elif curr == 0 and z <= -2.0: curr = 1
        elif curr == 0 and z >= 2.0: curr = -1
        elif (curr == 1 and z >= 0) or (curr == -1 and z <= 0): curr = 0
        pos_vector[i] = curr
        
    pair_df["position"] = pos_vector

    # Match the historical P&L to the live regression hedge:
    # one share of t1 hedged with beta shares of t2. Normalize by gross
    # notional so returns are comparable across pairs with different betas.
    spread_pnl = pair_df[t1].diff() - (beta * pair_df[t2].diff())
    gross_notional = (
        pair_df[t1].shift(1).abs()
        + (beta * pair_df[t2].shift(1)).abs()
    )
    hedged_return = np.where(
        gross_notional > 0,
        spread_pnl / gross_notional,
        0.0,
    )
    turnover = pair_df["position"].diff().fillna(
        pair_df["position"].abs()
    ).abs()
    pair_df["strat_ret"] = (
        pair_df["position"].shift(1).fillna(0) * hedged_return
        - (turnover * 0.0007)
    )
    
    vol = pair_df["strat_ret"].std() * np.sqrt(252)
    sharpe = (pair_df["strat_ret"].mean() * 252) / vol if vol != 0 else 0
    fund = INITIAL_CAPITAL * (1 + pair_df["strat_ret"]).cumprod()
    max_dd = ((fund - fund.cummax()) / fund.cummax()).min() * 100
    
    return {"Sharpe": sharpe, "Max DD": max_dd}

# =====================================================================
# MAIN AUTOMATED PROCESSING LOOP
# =====================================================================
if __name__ == "__main__":
    logging.info("Initializing elite execution tier sweep...")
    
    sp500_meta = harvest_sp500_homogeneity()
    sub_industry_map = sp500_meta.set_index("Ticker")["Sub-Industry"].to_dict()
    sub_industry_list = sorted(sp500_meta["Sub-Industry"].dropna().unique())
    all_tickers = sp500_meta["Ticker"].unique().tolist()
    
    # 1. Bulk-download daily historical macro data in rate-controlled batches
    logging.info("Harvesting 2-year daily historical matrix...")
    daily_macro_data, _ = fetch_market_data_chunked(all_tickers, period="2y", interval="1d", chunk_size=100, pause_seconds=1.0)
    
    # 2. Bulk-download 3-month hourly intraday data in rate-controlled batches
    logging.info("Harvesting 3-month hourly intraday matrix...")
    intraday_prices, intraday_volumes = fetch_market_data_chunked(all_tickers, period="3mo", interval="1h", chunk_size=100, pause_seconds=1.0)
    
    if daily_macro_data.empty or intraday_prices.empty:
        logging.error("Failed to harvest market data matrix blocks. Exiting.")
        exit(1)

    logging.info("Beginning in-memory multi-timeframe structural sweep...")

    # Use the newest timestamp available across the intraday matrix as the
    # freshness standard. A pair is eligible only when both legs have prices
    # at this timestamp.
    intraday_rows_with_data = intraday_prices.dropna(how="all")
    if intraday_rows_with_data.empty:
        logging.error("Intraday matrix contains no usable price rows. Exiting.")
        exit(1)
    latest_intraday_timestamp = intraday_rows_with_data.index.max()
    logging.info(
        f"Latest intraday price timestamp: {latest_intraday_timestamp}"
    )

    # 3. Process pairs rapidly in memory without making extra network requests
    for sub_ind in sub_industry_list:
        tickers = [t for t in daily_macro_data.columns if sub_industry_map.get(t) == sub_ind and t in intraday_prices.columns]
        if len(tickers) < 2: continue 
            
        for t1, t2 in itertools.combinations(tickers, 2):
            try:
                # Filter 1: Check Multi-Timeframe Cointegration Persistence
                is_stable, p_val = verify_multi_window_cointegration(daily_macro_data, t1, t2)
                if not is_stable: continue
                
                # Filter 2: Backtest Quality Assurance Filters
                macro = audit_macro_historical_profile(daily_macro_data, t1, t2)
                if not macro or macro["Sharpe"] < MIN_SHARPE_GATE or macro["Max DD"] < MAX_DD_LIMIT: continue
                
                df_intra_p = intraday_prices[[t1, t2]].dropna()
                df_intra_v = intraday_volumes[[t1, t2]].dropna() if (t1 in intraday_volumes.columns and t2 in intraday_volumes.columns) else pd.DataFrame()

                # Do not generate a signal when either leg is missing the
                # newest market observation. Both prices must come from the
                # same latest intraday timestamp.
                if (
                    df_intra_p.empty
                    or df_intra_p.index[-1] != latest_intraday_timestamp
                ):
                    pair_timestamp = (
                        df_intra_p.index[-1] if not df_intra_p.empty else "none"
                    )
                    logging.warning(
                        f"    [SKIPPED] {t1}/{t2} - stale or mismatched "
                        f"prices (pair: {pair_timestamp}, "
                        f"latest: {latest_intraday_timestamp})"
                    )
                    continue

                if len(df_intra_p) < (LOOKBACK_HOURS + 5): continue
                
                # Check current live spread parameters
                w = df_intra_p.tail(LOOKBACK_HOURS)
                beta = np.linalg.lstsq(np.vstack([np.ones(len(w)), w[t2].values]).T, w[t1].values, rcond=None)[0][1]
                
                intra_spreads = df_intra_p[t1].values - (beta * df_intra_p[t2].values)
                z_val = (intra_spreads[-1] - np.mean(intra_spreads[-LOOKBACK_HOURS:-1])) / np.std(intra_spreads[-LOOKBACK_HOURS:-1])
                half_life_days = calculate_ou_half_life(
                    intra_spreads[-LOOKBACK_HOURS:]
                )

                # SYSTEM DIAGNOSTIC LOGGER: Include decision context for every
                # pair that reaches the existing audit visibility threshold.
                if abs(z_val) > 1.0:
                    logging.info(
                        f"Audit: {t1} vs {t2} | Z: {z_val:.2f} | "
                        f"Gate: {ENTRY_Z} | CoC: {is_stable} | "
                        f"Half-Life: {half_life_days:.1f} days | "
                        f"Historical Sharpe: {macro['Sharpe']:.2f} | "
                        f"Spot: {t1} ${df_intra_p[t1].iloc[-1]:.2f}, "
                        f"{t2} ${df_intra_p[t2].iloc[-1]:.2f}"
                    )

                action = None
                if z_val >= ENTRY_Z: action = "SHORT SPREAD"
                elif z_val <= -ENTRY_Z: action = "LONG SPREAD"
                
                if action:
                    # Filter 3: Ornstein-Uhlenbeck Mean Reversion Velocity Verification
                    if half_life_days > MAX_HALF_LIFE_DAYS:
                        logging.info(f"    [SKIPPED] {t1}/{t2} - Reversion half-life too slow: {half_life_days:.1f} days (Max: {MAX_HALF_LIFE_DAYS})")
                        continue
                    
                    # Filter 4: Volume Outlier / Breakout Trend Safeguard
                    if not df_intra_v.empty:
                        latest_vol_t1 = df_intra_v[t1].iloc[-1]
                        mean_vol_t1 = df_intra_v[t1].tail(48).mean() 
                        latest_vol_t2 = df_intra_v[t2].iloc[-1]
                        mean_vol_t2 = df_intra_v[t2].tail(48).mean()
                        
                        vol_ratio_t1 = latest_vol_t1 / mean_vol_t1 if mean_vol_t1 > 0 else 1.0
                        vol_ratio_t2 = latest_vol_t2 / mean_vol_t2 if mean_vol_t2 > 0 else 1.0
                        
                        if vol_ratio_t1 > MAX_VOLUME_ANOMALY or vol_ratio_t2 > MAX_VOLUME_ANOMALY:
                            logging.info(f"    [SKIPPED] {t1}/{t2} - Breakout volume anomaly detected (Vol A: {vol_ratio_t1:.1f}x, Vol B: {vol_ratio_t2:.1f}x)")
                            continue
                        
                    # Filter 5: Tail Risk Volatility Check
                    ret_1d_t1 = abs(df_intra_p[t1].iloc[-1] / df_intra_p[t1].iloc[-8] - 1)
                    ret_1d_t2 = abs(df_intra_p[t2].iloc[-1] / df_intra_p[t2].iloc[-8] - 1)
                    if ret_1d_t1 > 0.08 or ret_1d_t2 > 0.08:
                        logging.info(f"    [SKIPPED] {t1}/{t2} - Single-leg volatility shock too high (>{max(ret_1d_t1, ret_1d_t2)*100:.1f}%)")
                        continue 

                    # All 5 institutional filters passed -> Dispatch alert
                    dispatch_discord_alert({
                        "Pair Name": f"{t1} vs {t2}", "Stock A": t1, "Stock B": t2, "Sub-Industry": sub_ind,
                        "Cointegration P-Value": p_val, "Historical Sharpe Ratio": macro["Sharpe"],
                        "Current Intraday Z-Score": z_val, "Action State": action, "Beta": beta,
                        "Price A": df_intra_p[t1].iloc[-1], "Price B": df_intra_p[t2].iloc[-1],
                        "Half-Life Days": half_life_days
                    })
            except Exception as loop_ex:
                logging.exception(
                    f"Pair-processing failure for {t1}/{t2}: {loop_ex}"
                )
                continue
                
    logging.info("High-conviction strategy loop completed.")
