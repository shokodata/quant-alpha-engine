import datetime
import json
import itertools
import urllib.request
import logging
import os
import numpy as np
import pandas as pd
import statsmodels.api as sm
import yfinance as yf
from statsmodels.tsa.stattools import coint

# =====================================================================
# ⚙️ HIGH-CONVICTION CONFIGURATION PANEL
# =====================================================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

ENTRY_Z = 3.0                      # Tightened signal boundary for extreme dislocation
MAX_P_VALUE_GATE = 0.05            # High statistical confidence threshold
MIN_SHARPE_GATE = 0.65             # Elevated backtest quality baseline
MAX_DD_LIMIT = -20.0               # Strict historical drawdown threshold
LOOKBACK_HOURS = 120               # Trailing lookback window for spread analysis
MAX_HALF_LIFE_DAYS = 5.0           # Maximum allowed mean reversion half-life (in days)
MAX_VOLUME_ANOMALY = 3.5           # Filters out breakout stocks trading at >3.5x typical volume

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
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
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
    return df[["Ticker", "Sub-Industry"]]

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
        if p_1y > 0.10: return False, p_2y # Allow slightly looser bound on shorter window
        
        return True, p_2y
    except:
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
            return 999.0 # Diverging spread
            
        theta = -np.log(1 + beta_coeff)
        half_life_hours = np.log(2) / theta
        return half_life_hours / 7.0 # Convert 7-hour market execution sessions to trading days
    except:
        return 999.0

def audit_macro_historical_profile(df, t1, t2):
    pair_df = df[[t1, t2]].dropna().copy()
    if len(pair_df) < 150: return None
    y, x = pair_df[t1].values, pair_df[t2].values
    X_mat = np.vstack([np.ones(len(x)), x]).T
    try:
        beta = np.linalg.lstsq(X_mat, y, rcond=None)[0][1]
    except:
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
    pair_df["strat_ret"] = pair_df["position"].shift(1) * (pair_df[t1].pct_change() - pair_df[t2].pct_change())
    pair_df["strat_ret"] = pair_df["strat_ret"].fillna(0)
    pair_df.loc[pair_df["position"].diff().fillna(0).abs() > 0, "strat_ret"] -= 0.0007
    
    vol = pair_df["strat_ret"].std() * np.sqrt(252)
    sharpe = (pair_df["strat_ret"].mean() * 252) / vol if vol != 0 else 0
    fund = INITIAL_CAPITAL * np.exp(np.cumsum(pair_df["strat_ret"]))
    max_dd = ((fund - fund.cummax()) / fund.cummax()).min() * 100
    
    return {"Sharpe": sharpe, "Max DD": max_dd}

# =====================================================================
# MAIN AUTOMATED PROCESSING LOOP
# =====================================================================
if __name__ == "__main__":
    logging.info("Initializing elite execution tier sweep...")
    
    sp500_meta = harvest_sp500_homogeneity()
    sub_industry_map = sp500_meta.set_index("Ticker")["Sub-Industry"].to_dict()
    sub_industry_list = sorted(sp500_meta["Sub-Industry"].unique())
    
    # Extract historical daily baseline metrics
    daily_raw = yf.download(sp500_meta["Ticker"].tolist(), period="2y", interval="1d", progress=False)
    if isinstance(daily_raw.columns, pd.MultiIndex):
        daily_macro_data = (daily_raw["Adj Close"] if "Adj Close" in daily_raw.columns.levels[0] else daily_raw["Close"]).ffill()
    else:
        daily_macro_data = (daily_raw["Adj Close"] if "Adj Close" in daily_raw.columns else daily_raw["Close"]).ffill()
    
    for sub_ind in sub_industry_list:
        tickers = [t for t in daily_macro_data.columns if sub_industry_map.get(t) == sub_ind]
        if len(tickers) < 2: continue # Requires a combination pair to match
        
        try:
            # VITAL PERFORMANCE UPGRADE: Pull both Price AND Volume parameters in a single batch
            raw_intraday = yf.download(tickers, period="3mo", interval="1h", progress=False)
            if isinstance(raw_intraday.columns, pd.MultiIndex):
                intraday_prices = (raw_intraday["Adj Close"] if "Adj Close" in raw_intraday.columns.levels[0] else raw_intraday["Close"]).ffill()
                intraday_volumes = raw_intraday["Volume"].ffill()
            else:
                continue
        except:
            continue
            
        for t1, t2 in itertools.combinations(tickers, 2):
            try:
                # Filter 1: Check Multi-Timeframe Cointegration Persistence
                is_stable, p_val = verify_multi_window_cointegration(daily_macro_data, t1, t2)
                if not is_stable: continue
                
                # Filter 2: Backtest Quality Assurance Filters
                macro = audit_macro_historical_profile(daily_macro_data, t1, t2)
                if not macro or macro["Sharpe"] < MIN_SHARPE_GATE or macro["Max DD"] < MAX_DD_LIMIT: continue
                
                if t1 not in intraday_prices.columns or t2 not in intraday_prices.columns: continue
                df_intra_p = intraday_prices[[t1, t2]].dropna()
                df_intra_v = intraday_volumes[[t1, t2]].dropna()
                if len(df_intra_p) < (LOOKBACK_HOURS + 5): continue
                
                # Check current live spread parameters
                w = df_intra_p.tail(LOOKBACK_HOURS)
                beta = np.linalg.lstsq(np.vstack([np.ones(len(w)), w[t2].values]).T, w[t1].values, rcond=None)[0][1]
                
                intra_spreads = df_intra_p[t1].values - (beta * df_intra_p[t2].values)
                z_val = (intra_spreads[-1] - np.mean(intra_spreads[-LOOKBACK_HOURS:-1])) / np.std(intra_spreads[-LOOKBACK_HOURS:-1])
                
                action = None
                if z_val >= ENTRY_Z: action = "SHORT SPREAD"
                elif z_val <= -ENTRY_Z: action = "LONG SPREAD"
                
                if action:
                    # Filter 3: Ornstein-Uhlenbeck Mean Reversion Velocity Verification
                    half_life_days = calculate_ou_half_life(intra_spreads[-LOOKBACK_HOURS:])
                    if half_life_days > MAX_HALF_LIFE_DAYS: continue
                    
                    # Filter 4: Volume Outlier / Breakout Trend Safeguard
                    # Ensures we aren't stepping in front of a heavy institutional price run
                    latest_vol_t1 = df_intra_v[t1].iloc[-1]
                    mean_vol_t1 = df_intra_v[t1].tail(48).mean() # Rolling 2-week baseline
                    latest_vol_t2 = df_intra_v[t2].iloc[-1]
                    mean_vol_t2 = df_intra_v[t2].tail(48).mean()
                    
                    vol_ratio_t1 = latest_vol_t1 / mean_vol_t1 if mean_vol_t1 > 0 else 1.0
                    vol_ratio_t2 = latest_vol_t2 / mean_vol_t2 if mean_vol_t2 > 0 else 1.0
                    
                    if vol_ratio_t1 > MAX_VOLUME_ANOMALY or vol_ratio_t2 > MAX_VOLUME_ANOMALY:
                        logging.info(f"Skipped {t1}/{t2} due to breakout volume anomaly.")
                        continue
                        
                    # Filter 5: Tail Risk Volatility Check
                    # Drop pairs if a single asset leg experiences unbacked daily volatility shocks
                    ret_1d_t1 = abs(df_intra_p[t1].iloc[-1] / df_intra_p[t1].iloc[-8] - 1)
                    ret_1d_t2 = abs(df_intra_p[t2].iloc[-1] / df_intra_p[t2].iloc[-8] - 1)
                    if ret_1d_t1 > 0.08 or ret_1d_t2 > 0.08: continue # Drop pairs experiencing >8% daily shocks

                    # All 5 institutional filters passed -> Dispatch alert
                    dispatch_discord_alert({
                        "Pair Name": f"{t1} vs {t2}", "Stock A": t1, "Stock B": t2, "Sub-Industry": sub_ind,
                        "Cointegration P-Value": p_val, "Historical Sharpe Ratio": macro["Sharpe"],
                        "Current Intraday Z-Score": z_val, "Action State": action, "Beta": beta,
                        "Price A": df_intra_p[t1].iloc[-1], "Price B": df_intra_p[t2].iloc[-1],
                        "Half-Life Days": half_life_days
                    })
            except:
                continue
                
    logging.info("High-conviction strategy loop completed safely.")
