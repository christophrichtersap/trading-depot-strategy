import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import itertools
from concurrent.futures import ProcessPoolExecutor
import warnings
import datetime
import os
import sys
import shutil

warnings.simplefilter(action='ignore', category=FutureWarning)

# ==========================================
INDEX_MAP = {
    "1": {"Ticker": "EXXT.DE",    "Name": "Nasdaq 100",    "Currency": "$"},
    "2": {"Ticker": "SPY",    "Name": "S&P 500",    "Currency": "$"},
    "3": {"Ticker": "^GDAXI",    "Name": "DAX 40",    "Currency": "€"},
    "4": {"Ticker": "XCHA.DE",    "Name": "CSI 300",    "Currency": "$"},
    "5": {"Ticker": "XWD.TO",    "Name": "MSCI World",    "Currency": "$"},
    "6": {"Ticker": "EXW1.DE",    "Name": "EuroStoxx 50",    "Currency": "€"}
    
    
}

# FINANCIAL SETTINGS (GERMANY / REALISTIC)
INITIAL_CAPITAL = 10000
TAX_RATE = 0.275            
TRANSACTION_FEE = 0.001     # Broker Fee
SLIPPAGE        = 0.002     # 0.2% Slippage on trend changes (Realistic execution)

# Leverage Costs (Annualized)
TER_LEV = 0.0075            # ETF Expense Ratio
BORROW_SPREAD = 0.005       # Extra interest cost for leverage (0.5%)
TER_1X  = 0.0003  

# OPTIMIZATION GRID
SMA_RANGES = range(180, 230, 10)       
BUFFER_RANGES = [1.0, 2.0, 3.0]         
RSI_RANGES = [50]                       
STOP_LOSS_RANGES = np.arange(0.10, 0.25, 0.02) 

# OUTPUT DIRECTORY
OUTPUT_DIR = "examples"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# 2. WORKER FUNCTION
# ==========================================
def optimize_worker(packed_args):
    params, prices, ret_lev, ret_cash, init_cap, fee_total, tax_rate = packed_args
    sma_len, buffer_pct, rsi_min, sl_pct = params
    
    if len(prices) < sma_len: return {"Params": params, "Score": -999}

    p_series = pd.Series(prices)
    sma = p_series.rolling(window=sma_len).mean().to_numpy()
    floor = sma * (1 - buffer_pct / 100)
    
    delta = p_series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    rsi = (100 - (100 / (1 + rs))).to_numpy()
    
    curr_cap = float(init_cap)
    curr_pos = 1 
    peak = float(prices[sma_len])
    
    tax_basis = curr_cap 
    loss_pot = 0.0       
    max_equity = curr_cap
    max_dd = 0.0
    
    for i in range(sma_len, len(prices)):
        # Return
        r = float(ret_lev[i]) if curr_pos == 1 else float(ret_cash[i])
        curr_cap *= (1 + r)
        
        if curr_cap > max_equity: max_equity = curr_cap
        else:
            dd = (curr_cap - max_equity) / max_equity
            if dd < max_dd: max_dd = dd
        
        p = float(prices[i])
        next_pos = curr_pos
        
        if curr_pos == 1:
            if p > peak: peak = p
            if p < peak * (1 - sl_pct): next_pos = 0
            elif p < floor[i]: next_pos = 0
        elif curr_pos == 0:
            if p > sma[i] and rsi[i] > rsi_min:
                next_pos = 1
                peak = p
        
        if next_pos != curr_pos:
            # Apply Fee + Slippage
            curr_cap *= (1 - fee_total)
            
            # Tax Event (Only when selling to Cash)
            if curr_pos == 1 and next_pos == 0:
                profit = curr_cap - tax_basis
                if profit > 0:
                    taxable = profit - loss_pot
                    if taxable > 0:
                        curr_cap -= (taxable * tax_rate)
                        loss_pot = 0.0
                    else:
                        loss_pot -= profit
                else:
                    loss_pot += abs(profit)
            
            if next_pos == 1: tax_basis = curr_cap
            curr_pos = next_pos

    total_ret = (curr_cap - init_cap) / init_cap * 100
    max_dd_pct = max_dd * 100
    
    if curr_cap < 1000: score = -999.0
    else: score = total_ret / (abs(max_dd_pct) ** 1.5 + 1)
    
    return {"Params": params, "Score": score}

# ==========================================
# 3. SIMULATOR
# ==========================================
def run_simulation(params, prices, ret_lev, ret_cash, dates):
    sma_len, buffer_pct, rsi_min, sl_pct = params
    p_series = pd.Series(prices)
    sma = p_series.rolling(window=sma_len).mean().to_numpy()
    floor = sma * (1 - buffer_pct / 100)
    
    delta = p_series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    rsi = (100 - (100 / (1 + rs))).to_numpy()
    
    curr_cap = float(INITIAL_CAPITAL)
    curr_pos = 1 
    peak = float(prices[sma_len])
    basis = curr_cap
    loss_pot = 0.0
    curve = []
    trades = []
    entry_date = dates[sma_len]
    entry_val = curr_cap
    padding = [float(INITIAL_CAPITAL)] * sma_len
    
    # Combined Cost of switching
    total_switch_cost = TRANSACTION_FEE + SLIPPAGE

    for i in range(sma_len, len(prices)):
        r = float(ret_lev[i]) if curr_pos == 1 else float(ret_cash[i])
        curr_cap *= (1 + r)
        curve.append(curr_cap)
        
        p = float(prices[i])
        next_pos = curr_pos
        
        if curr_pos == 1:
            if p > peak: peak = p
            if p < peak * (1 - sl_pct): next_pos = 0
            elif p < floor[i]: next_pos = 0
        elif curr_pos == 0:
            if p > sma[i] and rsi[i] > rsi_min: next_pos = 1; peak = p
            
        if next_pos != curr_pos:
            trade_pnl = (curr_cap - entry_val) / entry_val * 100
            days = (dates[i] - entry_date).days
            
            curr_cap *= (1 - total_switch_cost)
            
            if curr_pos == 1 and next_pos == 0:
                profit = curr_cap - basis
                if profit > 0:
                    taxable = profit - loss_pot
                    if taxable > 0:
                        curr_cap -= (taxable * TAX_RATE)
                        loss_pot = 0.0
                    else:
                        loss_pot -= profit
                else:
                    loss_pot += abs(profit)
            if next_pos == 1: basis = curr_cap
            
            trades.append({
                "Entry": entry_date.date(), "Exit": dates[i].date(),
                "Phase": "LONG" if curr_pos == 1 else "CASH",
                "Profit": trade_pnl, "Days": days
            })
            curr_pos = next_pos
            entry_date = dates[i]
            entry_val = curr_cap

    curr_price = float(prices[-1])
    curr_sma = float(sma[-1])
    curr_floor = float(floor[-1])
    curr_days = (dates[-1] - entry_date).days
    curr_pnl = (curr_cap - entry_val) / entry_val * 100
    
    status = {"Phase": "LONG" if curr_pos == 1 else "CASH", "Profit": curr_pnl, "Days": curr_days}
    
    if curr_pos == 1:
        curr_stop = peak * (1 - sl_pct)
        dist_pct = (curr_price - max(curr_stop, curr_floor)) / curr_price * 100
        status["Msg"] = f"SAFETY: {dist_pct:.2f}%"
        status["Action"] = "HOLD"
    else:
        dist_pct = (curr_sma - curr_price) / curr_price * 100
        status["Msg"] = f"NEEDED: +{dist_pct:.2f}%"
        status["Action"] = "WAIT"
        
    return np.array(padding + curve), trades, status

# ==========================================
# 4. MAIN EXECUTION
# ==========================================
if __name__ == '__main__':
    # --- A. SELECTION ---
    env_choice = os.environ.get("TARGET_INDEX")
    if env_choice and env_choice in INDEX_MAP:
        selection = INDEX_MAP[env_choice]
    else:
        print("\n" + "="*40)
        print("🌍 SELECT MARKET INDEX")
        print("="*40)
        for k, v in INDEX_MAP.items(): print(f" [{k}] {v['Name']}")
        print("="*40)
        choice = input("Enter number (default 1): ").strip() or "1"
        selection = INDEX_MAP.get(choice, INDEX_MAP["1"])

    TICKER_INDEX = selection["Ticker"]
    ASSET_NAME = selection["Name"]
    CURRENCY_SYM = selection["Currency"]
    SAFE_NAME = ASSET_NAME.replace(" ", "_")
    
    print(f"\n🚀 Running for: {ASSET_NAME}")

    # --- B. DATA ---
    CACHE_DIR = "data_cache"
    if not os.environ.get("KEEP_CACHE") and os.path.exists(CACHE_DIR): shutil.rmtree(CACHE_DIR)
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    def get_clean_data(ticker):
        safe = ticker.replace('^', '').replace('.', '_')
        path = f"{CACHE_DIR}/{safe}.csv"
        if os.path.exists(path):
            try: 
                df = pd.read_csv(path, index_col=0, parse_dates=True)
                df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
                return df
            except: pass
        
        print(f"Downloading {ticker}...")
        df = yf.download(ticker, start="1990-01-01", progress=False, auto_adjust=True)
        # Handle Columns
        if isinstance(df.columns, pd.MultiIndex):
            # Extract Close if present
            try: df = df.xs('Close', axis=1, level=0)
            except: df = df.iloc[:, 0]
        elif isinstance(df, pd.DataFrame): 
            if 'Close' in df.columns: df = df['Close']
            else: df = df.iloc[:, 0]
            
        if isinstance(df, pd.DataFrame): df = df.iloc[:, 0]
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
        df.to_csv(path)
        return df

    try:
        p_idx = get_clean_data(TICKER_INDEX)
        p_rate = get_clean_data("^IRX")
    except: sys.exit("Data Error")

    common = p_idx.index.intersection(p_rate.index)
    p_idx, p_rate = p_idx.loc[common].dropna(), p_rate.loc[common]
    prices = p_idx.to_numpy().flatten()
    rates = p_rate.to_numpy().flatten()
    dates = p_idx.index.to_pydatetime()
    pct = p_idx.pct_change().fillna(0).to_numpy().flatten()

    # --- C. REALISTIC RETURN CALCULATION ---
    
    # Add Borrow Costs (Spread) to Drag
    # 3x uses 2x Borrowed Money + Equity.
    
    fee_lev = TER_LEV/252
    borrow_spread = BORROW_SPREAD/252
    
    ret_cash = np.nan_to_num((rates/100)/252, nan=0.0)
    
    # 1x Return
    ret_1x = pct - (TER_1X/252)
    
    # 2x Return = (2 * Asset) - (1 * (RiskFree + Spread)) - Fee
    ret_2x = (pct*2.0) - (ret_cash + borrow_spread) - fee_lev
    ret_2x = np.maximum(ret_2x, -0.999)
    
    # 3x Return = (3 * Asset) - (2 * (RiskFree + Spread)) - Fee
    ret_3x = (pct*3.0) - ((ret_cash + borrow_spread) * 2) - fee_lev
    ret_3x = np.maximum(ret_3x, -0.999)

    # --- D. OPTIMIZATION ---
    print("🔍 Running Dual Optimization...")
    param_list = list(itertools.product(SMA_RANGES, BUFFER_RANGES, RSI_RANGES, STOP_LOSS_RANGES))
    
    # Note: We pass TRANSACTION_FEE + SLIPPAGE as the total cost for switching in optimizer
    total_fee = TRANSACTION_FEE + SLIPPAGE
    
    args_3x = [(p, prices, ret_3x, ret_cash, INITIAL_CAPITAL, total_fee, TAX_RATE) for p in param_list]
    args_2x = [(p, prices, ret_2x, ret_cash, INITIAL_CAPITAL, total_fee, TAX_RATE) for p in param_list]
    
    with ProcessPoolExecutor() as executor: 
        results_3x = list(executor.map(optimize_worker, args_3x))
        results_2x = list(executor.map(optimize_worker, args_2x))
        
    best_3x = sorted(results_3x, key=lambda x: x['Score'], reverse=True)[0]['Params']
    best_2x = sorted(results_2x, key=lambda x: x['Score'], reverse=True)[0]['Params']

    # --- E. SIMULATION ---
    s3, t3, st3 = run_simulation(best_3x, prices, ret_3x, ret_cash, dates)
    s2, t2, st2 = run_simulation(best_2x, prices, ret_2x, ret_cash, dates)
    
    # Benchmarks
    h3 = np.cumprod(1 + ret_3x) * INITIAL_CAPITAL
    h2 = np.cumprod(1 + ret_2x) * INITIAL_CAPITAL
    h1 = np.cumprod(1 + ret_1x) * INITIAL_CAPITAL

    # --- F. PLOTTING ---
    min_len = min(len(dates), len(s3))
    d_plot = dates[:min_len]
    s3, s2, h3, h2, h1 = s3[:min_len], s2[:min_len], h3[:min_len], h2[:min_len], h1[:min_len]

    # Apply Deferred Tax to benchmarks for Chart "Net" estimate
    # Note: Chart is usually gross equity, but let's keep it comparable
    p_s3 = (s3/INITIAL_CAPITAL)*100
    p_s2 = (s2/INITIAL_CAPITAL)*100
    p_h1 = (h1/INITIAL_CAPITAL)*100
    p_h2 = (h2/INITIAL_CAPITAL)*100
    p_h3 = (h3/INITIAL_CAPITAL)*100

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    plt.subplots_adjust(hspace=0.05)

    ax1.plot(d_plot, p_s3, label=f'Strategy 3x', color='#EBB000', linewidth=2.5)
    ax1.plot(d_plot, p_s2, label=f'Strategy 2x', color='#FF8C00', linewidth=2.0)
    ax1.plot(d_plot, p_h1, label=f'Index 1x', color='black', linestyle='--', linewidth=1.5)
    ax1.plot(d_plot, p_h2, label=f'Hold 2x', color='#404040', alpha=0.5, linewidth=1)
    ax1.plot(d_plot, p_h3, label=f'Hold 3x', color='#A0A0A0', alpha=0.3, linewidth=1)

    ax1.set_yscale('log')
    ax1.set_title(f"Analysis: {ASSET_NAME} (Net of Tax & Fees)", fontsize=14, fontweight='bold')
    ax1.set_ylabel("Total Return (%)", fontsize=12)
    ax1.grid(True, which='both', alpha=0.2)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"{'+' if x-100>0 else ''}{x-100:,.0f}%"))
    ax1.legend(loc='upper left')

    def get_dd(c):
        pk = np.maximum.accumulate(c)
        with np.errstate(divide='ignore', invalid='ignore'): dd = (c - pk) / pk * 100
        return np.nan_to_num(dd)

    ax2.fill_between(d_plot, get_dd(h3), 0, color='gray', alpha=0.15)
    ax2.plot(d_plot, get_dd(h1), color='black', linestyle='--', linewidth=1, alpha=0.6)
    ax2.fill_between(d_plot, get_dd(s3), 0, color='#EBB000', alpha=0.3)
    ax2.plot(d_plot, get_dd(s3), color='#EBB000', linewidth=1.0)
    ax2.set_ylabel("Drawdown (%)")
    ax2.yaxis.set_major_formatter(mticker.PercentFormatter())
    
    img_filename = f"{SAFE_NAME}.png"
    img_path = os.path.join(OUTPUT_DIR, img_filename)
    plt.savefig(img_path, dpi=300, bbox_inches='tight')
    print(f"📊 Chart saved: {img_path}")

    # --- G. MARKDOWN REPORT ---
    def get_stats(arr, dts, is_bench=False):
        val = arr[-1]
        # Apply deferred tax if benchmark
        if is_bench and val > INITIAL_CAPITAL: val -= (val - INITIAL_CAPITAL) * TAX_RATE
        ret = (val - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
        years = (dts[-1] - dts[0]).days / 365.25
        cagr = ((val/INITIAL_CAPITAL)**(1/years) - 1) * 100 if val > 0 else -100
        pk = np.maximum.accumulate(arr)
        dd = np.min(np.nan_to_num((arr-pk)/pk)) * 100
        return ret, cagr, dd, val

    def get_period_indices(dates, years):
        cutoff = dates[-1] - datetime.timedelta(days=int(365.25*years))
        idx = np.searchsorted(dates, cutoff)
        return idx

    # Indices for periods
    idx_ytd = np.searchsorted(dates, datetime.datetime(dates[-1].year, 1, 1))
    idx_3y = get_period_indices(dates, 3)
    idx_5y = get_period_indices(dates, 5)

    # Helper to slice arrays
    def stats_period(arr, idx, is_bench=False):
        return get_stats(arr[idx:], dates[idx:], is_bench)

    # Full period stats
    r3, c3, d3, v3 = get_stats(s3, dates)
    r2, c2, d2, v2 = get_stats(s2, dates)
    rh1, ch1, dh1, vh1 = get_stats(h1, dates, True)
    rh2, ch2, dh2, vh2 = get_stats(h2, dates, True)
    rh3, ch3, dh3, vh3 = get_stats(h3, dates, True)

    # YTD stats
    r3_ytd, c3_ytd, _, _ = stats_period(s3, idx_ytd)
    r2_ytd, c2_ytd, _, _ = stats_period(s2, idx_ytd)
    rh1_ytd, ch1_ytd, _, _ = stats_period(h1, idx_ytd, True)
    rh2_ytd, ch2_ytd, _, _ = stats_period(h2, idx_ytd, True)
    rh3_ytd, ch3_ytd, _, _ = stats_period(h3, idx_ytd, True)

    # 3-year stats
    r3_3y, c3_3y, _, _ = stats_period(s3, idx_3y)
    r2_3y, c2_3y, _, _ = stats_period(s2, idx_3y)
    rh1_3y, ch1_3y, _, _ = stats_period(h1, idx_3y, True)
    rh2_3y, ch2_3y, _, _ = stats_period(h2, idx_3y, True)
    rh3_3y, ch3_3y, _, _ = stats_period(h3, idx_3y, True)

    # 5-year stats
    r3_5y, c3_5y, _, _ = stats_period(s3, idx_5y)
    r2_5y, c2_5y, _, _ = stats_period(s2, idx_5y)
    rh1_5y, ch1_5y, _, _ = stats_period(h1, idx_5y, True)
    rh2_5y, ch2_5y, _, _ = stats_period(h2, idx_5y, True)
    rh3_5y, ch3_5y, _, _ = stats_period(h3, idx_5y, True)

    p3_str = f"SMA {best_3x[0]} / Buf {best_3x[1]}% / SL {int(best_3x[3]*100)}%"
    p2_str = f"SMA {best_2x[0]} / Buf {best_2x[1]}% / SL {int(best_2x[3]*100)}%"

    md_content = f"""# 📈 Strategy Report: {ASSET_NAME}

**Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
**Index:** {TICKER_INDEX}
**Settings:** Tax {TAX_RATE*100}% | Spread {BORROW_SPREAD*100}% | Slip {SLIPPAGE*100}%

## 1. Performance (Net of Tax)
| Strategy | Best Parameters | Total Return | CAGR | YTD Return | 3Y Return | 5Y Return | YTD CAGR | 3Y CAGR | 5Y CAGR | Max Drawdown |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Strategy 3x | `{p3_str}` | **{r3:,.0f}%** | **{c3:.2f}%** | {r3_ytd:,.0f}% | {r3_3y:,.0f}% | {r3_5y:,.0f}% | {c3_ytd:.2f}% | {c3_3y:.2f}% | {c3_5y:.2f}% | {d3:.2f}% 
| Strategy 2x | `{p2_str}` | {r2:,.0f}% | {c2:.2f}% | {r2_ytd:,.0f}% | {r2_3y:,.0f}% | {r2_5y:,.0f}% | {c2_ytd:.2f}% | {c2_3y:.2f}% | {c2_5y:.2f}% | {d2:.2f}%
| Index 1x | - | {rh1:,.0f}% | {ch1:.2f}% | {rh1_ytd:,.0f}% | {rh1_3y:,.0f}% | {rh1_5y:,.0f}% | {ch1_ytd:.2f}% | {ch1_3y:.2f}% | {ch1_5y:.2f}% | {dh1:.2f}% 
| Index 2x | - | {rh2:,.0f}% | {ch2:.2f}% | {rh2_ytd:,.0f}% | {rh2_3y:,.0f}% | {rh2_5y:,.0f}% | {ch2_ytd:.2f}% | {ch2_3y:.2f}% | {ch2_5y:.2f}% | {dh2:.2f}%
| Index 3x | - | {rh3:,.0f}% | {ch3:.2f}% | {rh3_ytd:,.0f}% | {rh3_3y:,.0f}% | {rh3_5y:,.0f}% | {ch3_ytd:.2f}% | {ch3_3y:.2f}% | {ch3_5y:.2f}% | {dh3:.2f}% 

## 2. Current Status ({dates[-1].date()})
| Strategy | Phase | Profit | Days | Analysis | Action |
| :--- | :---: | :---: | :---: | :--- | :---: |
| Strategy 3x | {st3['Phase']} | {st3['Profit']:+.2f}% | {st3['Days']} | `{st3['Msg']}` | **{st3['Action']}** |
| Strategy 2x | {st2['Phase']} | {st2['Profit']:+.2f}% | {st2['Days']} | `{st2['Msg']}` | **{st2['Action']}** |

## 3. Visualization
![Chart]({img_filename})
"""
    
    md_filename = f"{SAFE_NAME}.md"
    md_path = os.path.join(OUTPUT_DIR, md_filename)
    with open(md_path, "w", encoding="utf-8") as f: f.write(md_content)
    print(f"✅ Report saved: {md_path}")
