# 📊 Trading Strategy Optimizer

![Daily Analysis](https://github.com/christophrichtersap/trading-depot-strategy/actions/workflows/daily-analysis.yml/badge.svg)

**Realistic backtesting framework for leveraged ETF strategies with full tax and cost modeling based on German tax law.**

![Strategy Comparison](examples/Nasdaq_100.png)

## 🎯 Features

- **🌍 Multi-Market Support**: Nasdaq 100, S&P 500, DAX 40, CSI 300, MSCI World
- **⚡ High-Performance**: ProcessPoolExecutor for parallel optimization
- **💰 Realistic Cost Modeling**: 
  - German capital gains tax (27.5% Abgeltungssteuer)
  - Tax-loss harvesting simulation
  - Broker fees (0.1%)
  - Slippage (0.2%)
  - Leveraged ETF costs (0.75% TER + 0.5% borrow spread)
- **📊 Strategy Logic**: 
  - SMA + buffer-based trend following
  - RSI momentum filters
  - Dynamic stop-loss protection
  - Risk-free rate during cash periods
- **📈 Professional Output**: Comparative charts with 1x, 2x, 3x leverage scenarios
- **🤖 Daily Auto-Run**: GitHub Actions workflow generates fresh analysis every day

## 📈 How It Works

The strategy tests combinations of:
- **SMA Periods**: 180-230 days
- **Buffer Zones**: 1-3% above/below SMA
- **Stop Losses**: 10-25% trailing stops

### Entry Logic
Price crosses above SMA + buffer with RSI confirmation → Buy leveraged position

### Exit Logic
- Price drops below SMA (trend reversal)
- Stop loss triggered (risk management)
→ Switch to cash position earning T-Bill rate

### Tax Treatment (German Law)
- **Capital Gains Tax**: 27.5% on realized profits
- **Tax-Loss Harvesting**: Losses offset future gains (Verlusttopf)
- **Wash Sale**: No restrictions (unlike US)
- Applied realistically on each trade exit

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Installation

```bash
# Clone the repository
git clone <repository>
cd finance

# Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install yfinance pandas numpy matplotlib
```

### Run Optimization

```bash
python main.py
```

**Interactive Market Selection:**
```
========================================
🌍 SELECT MARKET INDEX
========================================
 [1] Nasdaq 100
 [2] S&P 500
 [3] DAX 40
 [4] CSI 300
 [5] MSCI World
========================================
Enter number (default 1): 
```

Data is cached in `data_cache/` folder and refreshed automatically.

## 🤖 Automated Daily Analysis

GitHub Actions runs daily at 6 AM UTC, generating fresh markdown reports:

- `examples/Nasdaq_100.md`
- `examples/S&P_500.md`
- `examples/DAX_40.md`
- `examples/CSI_300.md`
- `examples/MSCI_World.md`

Each report includes best parameters, performance metrics, current position status, and chart.

## 📊 Output Example

```
============================================================
🏆 BEST PARAMETERS FOR Nasdaq 100
============================================================
SMA Period:     220 days
Buffer Zone:    2.0%
Stop Loss:      16%
============================================================

| Strategy     | Total Return | CAGR   | Max Drawdown |
|--------------|--------------|--------|--------------|
| Strategy 3x  | 131,760%     | 22.17% | -73.49%      |
| Strategy 2x  | 33,291%      | 17.58% | -57.53%      |
| Index 1x     | 7,504%       | 12.83% | -82.91%      |

Current Status: LONG | Profit: +40.39% | Days: 192
Analysis: SAFETY: 8.79% (cushion to stop loss)
Action: HOLD
```

Charts show comparative performance with 1x, 2x, 3x leverage scenarios and drawdown analysis.

## ⚙️ Configuration

### Available Markets

Edit `INDEX_MAP` in `main.py` to customize available indices:

```python
INDEX_MAP = {
    "1": {"Ticker": "^NDX", "Name": "Nasdaq 100", "Currency": "$"},
    "2": {"Ticker": "^GSPC", "Name": "S&P 500", "Currency": "$"},
    "3": {"Ticker": "^GDAXI", "Name": "DAX 40", "Currency": "€"},
    "4": {"Ticker": "000300.SS", "Name": "CSI 300", "Currency": "¥"},
    "5": {"Ticker": "URTH", "Name": "MSCI World", "Currency": "$"},
}
```

### Cost Configuration

All costs in `main.py`:

```python
# Financial Settings (Germany)
INITIAL_CAPITAL = 10000
TAX_RATE = 0.275            # 27.5% Abgeltungssteuer
TRANSACTION_FEE = 0.001     # 0.1% broker fee
SLIPPAGE = 0.002            # 0.2% execution slippage

# Leverage Costs (Annualized)
TER_LEV = 0.0075            # 0.75% ETF expense ratio
BORROW_SPREAD = 0.005       # 0.5% leverage interest cost
TER_1X = 0.0003             # 0.03% for 1x ETF

# Optimization Grid
SMA_RANGES = range(180, 230, 10)
BUFFER_RANGES = [1.0, 2.0, 3.0]
STOP_LOSS_RANGES = np.arange(0.10, 0.25, 0.02)
```

## 📁 File Structure

```
trading-depot-strategy/
├── .github/workflows/
│   └── daily-analysis.yml       # CI: Daily auto-run
├── data_cache/                  # Downloaded market data
│   ├── NDX_1990-01-01.csv
│   └── IRX_1990-01-01.csv
├── examples/                    # Generated reports
│   ├── Nasdaq_100.md
│   ├── Nasdaq_100.png
│   └── ...
├── main.py                      # Core backtester
├── README.md
└── .gitignore
```

## � Why This Matters

### Realistic vs. Theoretical Returns

Most backtests ignore taxes and real-world costs. This simulator models:

**✅ What's Included:**
- German capital gains tax (27.5%)
- Tax-loss harvesting (Verlusttopf)
- Broker fees + slippage
- Leveraged ETF costs (TER + borrow spread)
- Risk-free rate on cash

**❌ What's Still Missing:**
- Dividend withholding tax
- Currency conversion fees (for non-EUR indices)
- Account management fees
- Bid-ask spread variations

### Example: Nasdaq 100 (1990-2025)

| Metric | Strategy 3x | Strategy 2x | Hold 3x | Hold 1x |
|--------|------------|------------|---------|---------|
| Total Return | **131,760%** | 33,291% | 3,330% | 7,504% |
| CAGR | **22.17%** | 17.58% | 10.35% | 12.83% |
| Max Drawdown | -73.49% | -57.53% | **-99.98%** | -82.91% |
| Final (€10k) | **€13.2M** | €3.3M | €343k | €760k |

**Key Insight**: Active management with stop-loss dramatically reduces drawdown while maintaining high returns. The 3x buy-and-hold strategy nearly went to zero multiple times (-99.98%).

### Parallel Optimization
Distributes parameter combinations across CPU cores using ProcessPoolExecutor:
- Each worker process gets its own data copy
- Independent backtests run simultaneously
- Scales linearly with core count (12 cores = ~60 tests/sec)

## ⚠️ Disclaimer

This software is for **educational and research purposes only**.

**⚠️ NOT FINANCIAL ADVICE**

- Past performance does not guarantee future results
- Backtested results do not reflect real-world slippage, liquidity constraints, or market impact
- Trading leveraged ETFs involves substantial risk of loss
- 3x leveraged ETFs can lose 90%+ of value during market crashes
- Always test thoroughly with paper trading before risking real capital
- Consult a licensed financial advisor before making investment decisions

The authors assume no liability for financial losses incurred from using this software.

## 🐛 Troubleshooting

**Data download slow?**  
First run downloads 35 years of history (~30-60 sec). Cached afterwards.

**CSI 300 limited history?**  
Yahoo Finance only has CSI 300 data from 2021. Use A50 China ETF for longer backtest.

**Different tax rate?**  
Edit `TAX_RATE` in main.py (e.g., 0.15 for US long-term gains).

## 🙏 Acknowledgments

- Market data provided by Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance)
- Inspired by systematic trading research and quantitative finance methodologies
- Built with Python, pandas, numpy, and matplotlib