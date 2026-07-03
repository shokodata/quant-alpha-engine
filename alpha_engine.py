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
# ⚙️ SYSTEM CONFIGURATION PANEL (Pulls Securely From GitHub Environment)
# =====================================================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

ENTRY_Z = 2.8
MAX_P_VALUE_GATE = 0.05
MIN_SHARPE_GATE = 0.9
MAX_DD_LIMIT = -25.0
LOOKBACK_HOURS = 120
INITIAL_CAPITAL = 10000

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# =====================================================================
# TELEMETRY DISPATCH HOOK
# =====================================================================
def dispatch_discord_alert(data):
    if not DISCORD_WEBHOOK_URL: return
    
    emoji = "RED ALERT" if "SHORT" in data["Action State"] else "GREEN ALERT"
    color_hex = 16730955 if "SHORT" in data["Action State"] else 2732384

    payload = {
        "username": "Quant Alpha Dispatch",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2822/2822841.png",
        "embeds": [{
            "title": f"[{emoji}] Arbitrage Execution Alert",
            "description": f"High-conviction structural dislocation inside the **{data['Sector']}** framework.",
            "color": color_hex,
            "fields": [
                {"name": "Configuration", "value": f"`{data['Pair Name']}`", "inline": True},
                {"name": "Beta", "value": f"{data['Beta']:.4f}", "inline": True},
                {"name": "Live Z-Score", "value": f"**{data['Current Intraday Z-Score']:.2f}**", "inline": False},
                {"name": "P-Value", "value": f"{data['Cointegration P-Value']:.4f}", "inline": True},
                {"name": "Sharpe", "value": f"{data['Historical Sharpe Ratio']:.2f}", "inline": True},
                {"name": "Context Prices", "value": f"`{data['Stock A']}`: ${data['Price A']:.2f} | `{data['Stock B']}`: ${data['Price B']:.2f}", "inline": False}
            ],
            "footer": {"text": "S&P 500 GitHub Streamlined Instance"},
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
                logging.info(f"Alert broadcasted for {data['Pair Name']}")
    except Exception as err:
        logging.error(f"Discord delivery failed: {err}")

# =====================================================================
# ALGOS & CORE PIPELINES
# =====================================================================
def harvest_sp500_sectors():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        tables = pd.read_html(r.read())
    df = tables[0].rename(columns={"Symbol": "Ticker", "GICS Sector": "Sector"})
    df["Ticker"] = df["Ticker"].str.replace(".", "-", regex=False)
    df["Sector"] = df["Sector"].replace({"Information Technology": "Technology", "Communication Services": "Communications"})
    return df[["Ticker", "Sector"]]

def audit_macro_historical_profile(df, t_a, t_b):
    pair_df = df[[t_a, t_b]].dropna().copy()
    if len(pair_df) < 150: return None
    y, x = pair_df[t_a].values, pair_df[t_b].values
    X_mat = np.vstack([np.ones(len(x)), x]).T
    try:
        beta = np.linalg.lstsq(X_mat, y, rcond=None)[0][1]
    except:
        return None
        
    spreads = pair_df[t_a] - (beta * pair_df[t_b])
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
    pair_df["strat_ret"] = pair_df["position"].shift(1) * (pair_df[t_a].pct_change() - pair_df[t_b].pct_change())
    pair_df["strat_ret"] = pair_df["strat_ret"].fillna(0)
    pair_df.loc[pair_df["position"].diff().fillna(0).abs() > 0, "strat_ret"] -= 0.0007
    
    vol = pair_df["strat_ret"].std() * np.sqrt(252)
    sharpe = (pair_df["strat_ret"].mean() * 252) / vol if vol != 0 else 0
    fund = INITIAL_CAPITAL * np.exp(np.cumsum(pair_df["strat_ret"]))
    max_dd = ((fund - fund.cummax()) / fund.cummax()).min() * 100
    
    return {"Sharpe": sharpe, "Max DD": max_dd}

if __name__ == "__main__":
    logging.info("Starting automated market system sweep...")
    
    sp500_meta = harvest_sp500_sectors()
    sectors_map = sp500_meta.set_index("Ticker")["Sector"].to_dict()
    sector_list = sorted(sp500_meta["Sector"].unique())
    
    daily_macro_data = yf.download(sp500_meta["Ticker"].tolist(), period="2y", interval="1d", progress=False)
    if isinstance(daily_macro_data.columns, pd.MultiIndex):
        daily_macro_data = (daily_macro_data["Adj Close"] if "Adj Close" in daily_macro_data.columns.levels[0] else daily_macro_data["Close"]).ffill()
    else:
        daily_macro_data = (daily_macro_data["Adj Close"] if "Adj Close" in daily_macro_data.columns else daily_macro_data["Close"]).ffill()
    
    for sector in sector_list:
        tickers = [t for t in daily_macro_data.columns if sectors_map.get(t) == sector]
        if not tickers: continue
        
        try:
            raw_intraday = yf.download(tickers, period="3mo", interval="1h", progress=False)
            if isinstance(raw_intraday.columns, pd.MultiIndex):
                intraday = (raw_intraday["Adj Close"] if "Adj Close" in raw_intraday.columns.levels[0] else raw_intraday["Close"]).ffill()
            else:
                intraday = (raw_intraday["Adj Close"] if "Adj Close" in raw_intraday.columns else raw_intraday["Close"]).ffill()
        except:
            continue
            
        for t1, t2 in itertools.combinations(tickers, 2):
            try:
                clean_p = daily_macro_data[[t1, t2]].dropna()
                if len(clean_p) < 150: continue
                
                _, p_val, _ = coint(clean_p[t1], clean_p[t2])
                if p_val > MAX_P_VALUE_GATE: continue
                
                macro = audit_macro_historical_profile(daily_macro_data, t1, t2)
                if not macro or macro["Sharpe"] < MIN_SHARPE_GATE or macro["Max DD"] < MAX_DD_LIMIT: continue
                
                if t1 not in intraday.columns or t2 not in intraday.columns: continue
                df_intra = intraday[[t1, t2]].dropna()
                if len(df_intra) < (LOOKBACK_HOURS + 5): continue
                
                w = df_intra.tail(LOOKBACK_HOURS)
                beta = np.linalg.lstsq(np.vstack([np.ones(len(w)), w[t2].values]).T, w[t1].values, rcond=None)[0][1]
                
                spreads = df_intra[t1].values - (beta * df_intra[t2].values)
                z_val = (spreads[-1] - np.mean(spreads[-LOOKBACK_HOURS:-1])) / np.std(spreads[-LOOKBACK_HOURS:-1])
                
                action = None
                if z_val >= ENTRY_Z: action = "SHORT SPREAD"
                elif z_val <= -ENTRY_Z: action = "LONG SPREAD"
                
                # Direct alert dispatch without any tracking file filters
                if action:
                    dispatch_discord_alert({
                        "Pair Name": f"{t1} vs {t2}", "Stock A": t1, "Stock B": t2, "Sector": sector,
                        "Cointegration P-Value": p_val, "Historical Sharpe Ratio": macro["Sharpe"],
                        "Current Intraday Z-Score": z_val, "Action State": action, "Beta": beta,
                        "Price A": df_intra[t1].iloc[-1], "Price B": df_intra[t2].iloc[-1]
                    })
            except:
                continue
                
    logging.info("Sweep complete. Process terminated cleanly.")
