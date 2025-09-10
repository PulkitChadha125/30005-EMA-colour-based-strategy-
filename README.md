# 30005 EMA Colour-Based Strategy

This project implements an automated options trading strategy using the Fyers API v3. It fetches OHLC data, computes EMA using Polars + polars_talib, detects a green-candle EMA crossover, then waits up to 4 bars for a qualifying red candle above EMA to lock entry levels. Orders are placed via Fyers once price crosses the computed entry level, with stop-loss and partial take-profit management.

## Features
- Real-time quotes via Fyers WebSocket
- Historical OHLC via Fyers REST (history)
- Data processing with Pandas/Polars
- EMA calculation using `polars_talib`
- Signal lifecycle: AwaitRed → RedLocked → Triggered
- Order placement and basic trade management

## Repository layout
- `main.py` – strategy loop and signal logic
- `FyresIntegration.py` – Fyers API login, history, websockets, and order helpers
- `TradeSettings.csv` – per-instrument strategy configuration
- `FyersCredentials.csv` – API credentials and login parameters
- `requirements.txt` – Python dependencies
- `pyinstallercommand.txt` – optional packaging notes

## Prerequisites
- Windows with PowerShell 7+ (or any OS with Python 3.12+)
- Python 3.12 recommended
- A funded Fyers account with API v3 access

## Quick start
1) Create & activate virtual environment
```powershell
python -m venv .venv
.venv\Scripts\activate
```

2) Install dependencies
```powershell
pip install -r requirements.txt
```

3) Configure credentials in `FyersCredentials.csv`
```
Title,Value
redirect_uri,https://your-redirect
client_id,APPID-100
secret_key,SECRET
grant_type,authorization_code
response_type,code
state,sample
totpkey,BASE32_TOTP
FY_ID,AB1234
PIN,1234
```

4) Configure instruments in `TradeSettings.csv`
Minimum required columns (headers must match exactly):
```
Symbol,EXPIERY,ExpType,OptionType,Strike,Quantity,EntryBuffer,EmaPeriod,Timeframe,StartTime,Stoptime
NIFTY,16-09-2025,Weekly,CE,24750,75,1,14,1,09:25,23:30
```
- `ExpType`: `Weekly` or `Monthly`
- `OptionType`: `CE` or `PE`
- `Timeframe`: minutes for OHLC resolution
- `EntryBuffer`: price buffer added to entry level

5) Run the strategy
```powershell
python main.py
```

## How it works (high level)
- Login: `automated_login(...)` retrieves an access token via TOTP + PIN
- Data: `fetchOHLC(symbol, timeframe)` returns recent bars; converted to Polars
- EMA: `pl.col("close").ta.ema(timeperiod=EmaPeriod)`
- Signal: Detects green close above EMA, then within 4 bars seeks a red bar whose close remains above EMA; locks entry=high+buffer and SL=low
- Execution: Triggers when LTP ≥ entry; places buy; handles partial TP and stop loss

## Logs & outputs
- `OrderLog.txt`: human-readable order events
- Optional CSV dump: `fyersData_polars.csv` (last processed data with EMA)

## Packaging (optional)
If you use PyInstaller, see `pyinstallercommand.txt` for baseline commands. Ensure you activate the venv first.

## Common issues & tips
- If you see parsing errors like `strptime() argument 1 must be str, not float`, ensure CSV cells are proper strings (e.g., `09:25`, `16-09-2025`) without Excel-introduced decimals.
- Make sure system time and timezone are correct; the code expects IST for some conversions.
- Verify `client_id` ends with `-100` for API v3 app IDs.

## Safety
This strategy places real orders. Test thoroughly in a paper or sandbox environment before using on live funds. You are responsible for compliance and risk.

## License
Proprietary/private by default. Add a license here if you plan to open-source.
