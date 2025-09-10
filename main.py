import pandas as pd
import datetime  # full module
import polars as pl
import polars_talib as plta
import json
import requests

# from datetime import datetime, timedelta
import time
import traceback
import sys
from FyresIntegration import *
from datetime import datetime, timedelta

# https://api-t1.fyers.in/api/v3/generate-authcode?client_id=9Z1CPDN4XR-100&redirect_uri=https://www.google.co.in/&response_type=code&state=sample_state

def normalize_time_to_timeframe(current_time, timeframe_minutes):
    """
    Normalize time to the specified timeframe interval.
    
    Args:
        current_time: datetime object (current time)
        timeframe_minutes: int (timeframe in minutes, e.g., 5 for 5-minute intervals)
    
    Returns:
        datetime: normalized time rounded down to the nearest timeframe interval
    """
    # Calculate how many complete timeframe intervals have passed
    intervals_passed = current_time.minute // timeframe_minutes
    
    # Calculate the normalized minute (round down to nearest timeframe)
    normalized_minute = intervals_passed * timeframe_minutes
    
    # Create normalized time (set seconds and microseconds to 0)
    normalized_time = current_time.replace(
        minute=normalized_minute, 
        second=0, 
        microsecond=0
    )
    
    return normalized_time



def get_api_credentials_Fyers():
    credentials_dict_fyers = {}
    try:
        df = pd.read_csv('FyersCredentials.csv')
        for index, row in df.iterrows():
            title = row['Title']
            value = row['Value']
            credentials_dict_fyers[title] = value
    except pd.errors.EmptyDataError:
        print("The CSV FyersCredentials.csv file is empty or has no data.")
    except FileNotFoundError:
        print("The CSV FyersCredentials.csv file was not found.")
    except Exception as e:
        print("An error occurred while reading the CSV FyersCredentials.csv file:", str(e))
    return credentials_dict_fyers

#get equity symbols
def get_equity_symbols():
    url = "https://public.fyers.in/sym_details/NSE_CM_sym_master.json"
    response = requests.get(url)
    data = response.json()
    df = pd.DataFrame.from_dict(data, orient='index')
    return df



def delete_file_contents(file_name):
    try:
        # Open the file in write mode, which truncates it (deletes contents)
        with open(file_name, 'w') as file:
            file.truncate(0)
        print(f"Contents of {file_name} have been deleted.")
    except FileNotFoundError:
        print(f"File {file_name} not found.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

          

def write_to_order_logs(message):
    with open('OrderLog.txt', 'a') as file:  # Open the file in append mode
        file.write(message + '\n')

def _parse_time_cell(value):
    try:
        import pandas as pd
        if pd.isna(value):
            return None
    except Exception:
        pass

    s = str(value).strip()
    if not s:
        return None
    if s.endswith('.0'):
        s = s[:-2]
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except Exception:
            continue
    try:
        import pandas as pd
        return pd.to_datetime(s).time()
    except Exception:
        return None

def _parse_date_ddmmyyyy(value):
    s = str(value).strip() if value is not None else ""
    if s.endswith('.0'):
        s = s[:-2]
    try:
        return datetime.strptime(s, '%d-%m-%Y')
    except Exception:
        try:
            import pandas as pd
            return pd.to_datetime(s, dayfirst=True)
        except Exception:
            return None


def get_user_settings():
    global result_dict, instrument_id_list, Equity_instrument_id_list, Future_instrument_id_list, FyerSymbolList
    from datetime import datetime
    import pandas as pd

    delete_file_contents("OrderLog.txt")

    try:
        csv_path = 'TradeSettings.csv'
        df = pd.read_csv(csv_path)
        df.columns = df.columns.str.strip()

        result_dict = {}
        FyerSymbolList = []

        for index, row in df.iterrows():
            try:
                # --- Read raw values from CSV (no forced casting as per your preference) ---
                symbol     = str(row.get('Symbol', '')).strip()
                expiry     = row.get('EXPIERY')  # 'dd-mm-YYYY' expected
                ExpType    = str(row.get('ExpType', '')).strip()
                OptionType = str(row.get('OptionType', '')).strip().upper()
                Strike     = row.get('Strike')
                qty_raw    = row.get('Quantity', 0)
                start_raw  = row.get("StartTime")
                stop_raw   = row.get("Stoptime")

                print(f"symbol: {symbol}")
                print(f"ExpType: {ExpType}")
                print(f"OptionType: {OptionType}")
                print(f"Strike: {Strike}")
                print(f"expiry: {expiry}")

                # --- Start/Stop time: robust parsing with defaults ---
                start_time_str = str(start_raw).strip() if pd.notna(start_raw) else "09:15"
                stop_time_str  = str(stop_raw).strip()  if pd.notna(stop_raw)  else "15:30"
                try:
                    start_time = datetime.strptime(start_time_str, "%H:%M").time()
                except Exception:
                    start_time = datetime.strptime("09:15", "%H:%M").time()
                try:
                    stop_time = datetime.strptime(stop_time_str, "%H:%M").time()
                except Exception:
                    stop_time = datetime.strptime("15:30", "%H:%M").time()

                # --- Quantity: you already like using int() here (kept) ---
                Quantity = int(qty_raw)

                # --- Strike: normalize '24750.0' -> '24750' and keep as string ---
                if pd.notna(Strike):
                    if isinstance(Strike, (int, float)):
                        if float(Strike).is_integer():
                            Strike = str(int(Strike))
                        else:
                            Strike = str(Strike).strip()
                    else:
                        Strike = str(Strike).strip()
                else:
                    Strike = ""

                # --- Build Fyers symbol for Weekly/Monthly options (only if expiry present) ---
                fyers_symbol = None
                if pd.notna(expiry):
                    expiry_str = str(expiry).strip()
                    if ExpType == "Monthly":
                        # e.g., '29-05-2025' -> '25MAY'
                        expiry_date = datetime.strptime(expiry_str, '%d-%m-%Y')
                        new_date_string = expiry_date.strftime('%y%b').upper()
                        fyers_symbol = f"NSE:{symbol}{new_date_string}{Strike}{OptionType}"
                        print(f"fyers_symbol: {fyers_symbol}")
                    elif ExpType == "Weekly":
                        # e.g., '16-09-2025' -> YYMDD (25 9 16) => NIFTY2591624750CE
                        expiry_date = datetime.strptime(expiry_str, "%d-%m-%Y")
                        year_yy = expiry_date.strftime('%y')            # '25'
                        month_m = str(int(expiry_date.strftime('%m')))  # '9' (no leading zero)
                        day_dd = expiry_date.strftime('%d')            # '16'
                        expiry_formatted = f"{year_yy}{month_m}{day_dd}"
                        print(f"Weekly expiry from CSV: {expiry_formatted}")
                        fyers_symbol = f"NSE:{symbol}{expiry_formatted}{Strike}{OptionType}"
                        print(f"fyers_symbol: {fyers_symbol}")
                else:
                    print(f"[WARN] Row {index}: missing EXPIERY; skipping symbol construction.")

                # --- Unique key (allows multiple rows per underlying) ---
                unique_key = f"{symbol}_{OptionType}_{Strike}"

                # --- Build symbol_dict (no extra casting for your fields) ---
                symbol_dict = {
                    "Symbol": symbol,
                    "unique_key": unique_key,
                    "Expiry": expiry,
                    "ExpType": ExpType,
                    "OptionType": OptionType,
                    "Strike": Strike,

                    "Quantity": Quantity,
                    "FyresSymbol": fyers_symbol,
                    "FyresLtp": None,
                    "Trade": None,

                    "StartTime": start_time,
                    "StopTime": stop_time,

                    # keep raw values as you prefer; you already cast where needed later
                    "EntryBuffer": row.get('EntryBuffer'),
                    "EmaPeriod": row.get('EmaPeriod'),
                    "Timeframe": row.get('Timeframe'),

                    # ---- Signal state ----
                    "CrossOverStatus": None,         # None | "AwaitRed" | "RedLocked" | "Triggered"
                    "CrossOverTime": None,
                    "BarsLeft": 0,
                    "LastEvaluatedTime": None,
                    "LastRedTime": None,

                    # ---- Levels ----
                    "EntryPrice": None,
                    "StoplossValue": None,
                    "CandleLength": None,
                    "TargetPrice": None,

                    # ---- Trade state ----
                    "EntryExecutedPrice": None,
                    "RemainingQty": 0,
                    "PartialBooked": False,

                    # TP configuration: exit quantity/2 at target (min 1)
                    "TP1QTY": max(1, Quantity // 2),
                    "TP1Price": None,   # you use TargetPrice as trigger; this is optional actual fill log
                    "SquareOffExecuted": False,
                }

                print("EntryBuffer: ", symbol_dict["EntryBuffer"])
                print("type(symbol_dict['EntryBuffer']): ", type(symbol_dict["EntryBuffer"]))
                print("EmaPeriod: ", symbol_dict["EmaPeriod"])
                print("type(symbol_dict['EmaPeriod']): ", type(symbol_dict["EmaPeriod"]))
                print("Timeframe: ", symbol_dict["Timeframe"])
                print("type(symbol_dict['Timeframe']): ", type(symbol_dict["Timeframe"]))

                result_dict[symbol_dict["unique_key"]] = symbol_dict
                if fyers_symbol:
                    FyerSymbolList.append(fyers_symbol)

            except Exception as row_e:
                print(f"[Row {index}] Skipped due to error: {row_e}")

        print("result_dict: ", result_dict)
        print("-" * 50)

    except Exception as e:
        print("Error happened in fetching symbol", str(e))


# def get_user_settings():
#     global result_dict, instrument_id_list, Equity_instrument_id_list, Future_instrument_id_list, FyerSymbolList
#     fyers_symbol=None
#     from datetime import datetime
#     import pandas as pd

#     delete_file_contents("OrderLog.txt")

#     try:
#         csv_path = 'TradeSettings.csv'
#         df = pd.read_csv(csv_path)
#         df.columns = df.columns.str.strip()

#         result_dict = {}
        
#         FyerSymbolList = []

#         for index, row in df.iterrows():
#             symbol = row['Symbol']
#             expiry = row['EXPIERY']  # Format: 29-05-2025
#             ExpType=row['ExpType']
#             OptionType=row['OptionType']
#             Strike=row['Strike']
#             print(f"symbol: {symbol}")
#             print(f"ExpType: {ExpType}")
#             print(f"OptionType: {OptionType}")
#             print(f"Strike: {Strike}")
#             print(f"expiry: {expiry}")

#             if ExpType == "Monthly":
#                 expiry_date = datetime.strptime(expiry, '%d-%m-%Y')
#     # Format as '25JUN'
#                 new_date_string = expiry_date.strftime('%y%b').upper()
#                 fyers_symbol = f"NSE:{symbol}{new_date_string}{Strike}{OptionType}"
#                 print(f"fyers_symbol: {fyers_symbol}")
#             if ExpType == "Weekly":
#                 # For weekly options, construct symbol as SYMBOL + YY + M + DD + STRIKE + OPTIONTYPE
#                 # Example: NIFTY2590225000CE for 2025-09-02
#                 try:
#                     expiry_date = datetime.strptime(expiry, "%d-%m-%Y")
#                     year_yy = expiry_date.strftime('%y')              # e.g., '25'
#                     month_m = str(int(expiry_date.strftime('%m')))     # e.g., '9' (no leading zero)
#                     day_dd = expiry_date.strftime('%d')                # e.g., '02'
#                     expiry_formatted = f"{year_yy}{month_m}{day_dd}"
#                     print(f"Weekly expiry from CSV: {expiry_formatted}")
#                     # Final desired format: NIFTY2590225000CE (no 'NSE:' prefix)
#                     fyers_symbol = f"NSE:{symbol}{expiry_formatted}{Strike}{OptionType}"
#                     print(f"fyers_symbol: {fyers_symbol}")
#                 except ValueError as e:
#                     print(f"Invalid expiry date format: {expiry}. Error: {e}")

#             # Create a unique key per row to support duplicate symbols (e.g., CE and PE rows for NIFTY)
#             unique_key = f"{symbol}_{OptionType}_{Strike}"

#             symbol_dict = {
#                 "Symbol": symbol, "unique_key": unique_key,
#                 "Expiry": expiry,"ExpType":row['ExpType'],"OptionType":row['OptionType']
#                 ,"Strike":row['Strike'],
#                 "Quantity": int(row['Quantity']),# Add tick size to symbol dictionary
#                 "FyresSymbol":fyers_symbol,"FyresLtp":None,"Trade":None,
#                 "StartTime": datetime.strptime(row["StartTime"], "%H:%M").time(),
#                 "StopTime": datetime.strptime(row["Stoptime"], "%H:%M").time(),
#                 "EntryBuffer":row['EntryBuffer'],"EmaPeriod":row['EmaPeriod'],"Timeframe":row['Timeframe'],
#                 "CrossOverStatus": None,            # None | "CrossoverDetected" | "AwaitRed" | "RedLocked" | "PendingTrigger"
#                 "CrossOverTime": None,              # datetime of the green crossover bar’s close
#                 "BarsLeft": 0,                      # countdown from 4
#                 "LastEvaluatedTime": None,   # <-- used in prints/gating
#                 "LastRedTime": None,                # datetime of the last qualifying red candle we’re using
#                 "EntryPrice": None,
#                 "StoplossValue": None,
#                 "CandleLength": None,
#                 "TargetPrice": None,
#                 "Trade": None,               # None | "BUY"
#                 "EntryExecutedPrice": None,  # actual LTP you got filled at
#                 "RemainingQty": 0,
#                 "PartialBooked": False,
#                 "TP1QTY": max(1, int(row['Quantity'])) if str(row.get('Quantity','')).isdigit() else 0,
#                 "TP1Price": None        # TP1 price (actual LTP)

                
            
#             }
#             print("EntryBuffer: ",symbol_dict["EntryBuffer"])
#             print("type(symbol_dict['EntryBuffer']): ",type(symbol_dict["EntryBuffer"]))
#             print("EmaPeriod: ",symbol_dict["EmaPeriod"])
#             print("type(symbol_dict['EmaPeriod']): ",type(symbol_dict["EmaPeriod"]))
#             print("Timeframe: ",symbol_dict["Timeframe"])
#             print("type(symbol_dict['Timeframe']): ",type(symbol_dict["Timeframe"]))
#             result_dict[symbol_dict["unique_key"]] = symbol_dict
#             FyerSymbolList.append(symbol_dict["FyresSymbol"])
#         print("result_dict: ", result_dict)
#         print("-" * 50)
       

#     except Exception as e:
#         print("Error happened in fetching symbol", str(e))



def UpdateData():
    global result_dict

    for symbol, ltp in shared_data.items(): 
        for key, value in result_dict.items():
            if value.get('FyresSymbol') == symbol:
                value['FyresLtp'] = float(ltp)
                print(f"Updated {symbol} with LTP: {ltp}")
                break  # Optional: skip if you assume each symbol is unique
           



def convert_to_polars(df):
    # Make a copy to avoid modifying the original dataframe
    df_copy = df.copy()
    
    # Convert timezone-aware datetime to timezone-naive
    if 'date' in df_copy.columns and df_copy['date'].dtype.name.startswith('datetime'):
        df_copy['date'] = df_copy['date'].dt.tz_localize(None)
    
    # Reset index to preserve date information as a column
    if df_copy.index.name and df_copy.index.name != 'index':
        df_copy = df_copy.reset_index()
    
    # Ensure numeric columns are properly typed
    numeric_columns = ['open', 'high', 'low', 'close', 'volume']
    for col in numeric_columns:
        if col in df_copy.columns:
            df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')
    
    # Convert to polars
    polars_df = pl.from_pandas(df_copy)
    
    # Ensure close column exists and is numeric
    if 'close' in polars_df.columns:
        polars_df = polars_df.with_columns([
            pl.col("close").cast(pl.Float64)
        ])
    
    return polars_df


def main_strategy():
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=10)

        start_time_str = start_date.strftime("%b %d %Y 090000")
        end_time_str = end_date.strftime("%b %d %Y 153000")

        now = datetime.now()
        now_time = now.time()
        UpdateData()
        time.sleep(1)
        fetch_start = time.time()

        for unique_key, params in result_dict.items():
            # initialize loop-specific variables to avoid UnboundLocalError
            symbol_name = params["FyresSymbol"]
            
            # FIRST: Check if we're past stop time and have an open trade - CLOSE IT IMMEDIATELY
            if (now_time >= params.get("StopTime") and 
                not params.get("SquareOffExecuted", False) and 
                params.get("Trade") == "Entry" and
                params.get("FyresLtp") is not None and
                params.get("RemainingQty", 0) > 0):
                
                print(f"[{params['Symbol']}] Stop time reached. Executing square-off.")
                params["SquareOffExecuted"] = True
                params["Trade"] = None
                params["CrossOverStatus"] = None
                params["CrossOverTime"] = None
                params["BarsLeft"] = 0
                params["LastRedTime"] = None
                params["EntryPrice"] = params["StoplossValue"] = params["CandleLength"] = params["TargetPrice"] = None
                place_order(symbol=params["FyresSymbol"],quantity=params["RemainingQty"],type=1,side=-1,price=params["FyresLtp"])
                write_to_order_logs(f"[{params['Symbol']}] Square-off executed. SELL {params['RemainingQty']} @ {params['FyresLtp']}")
                continue  # Skip further processing after closing trade
            
            # SECOND: If outside trading hours, skip strategy processing
            if not (params["StartTime"] <= now_time <= params["StopTime"]):
                continue
            
            fyersData=fetchOHLC(symbol_name,params["Timeframe"])
            # print("fyersData columns: ", fyersData.columns.tolist())
            # print("fyersData shape: ", fyersData.shape)
            
            fyersData_polars=convert_to_polars(fyersData)
            # print("fyersData_polars columns: ", fyersData_polars.columns)
            # print("fyersData_polars shape: ", fyersData_polars.shape)

            # Calculate EMA using the 'close' column
            try:
                fyersData_polars = fyersData_polars.with_columns([
                    pl.col("close").ta.ema(
                        timeperiod=int(params["EmaPeriod"])
                    ).alias("ema")
                ])
                print(f"EMA calculated successfully with period {params['EmaPeriod']}")
            except Exception as e:
                print(f"Error calculating EMA: {e}")
                # Fallback: add a column with NaN values
                fyersData_polars = fyersData_polars.with_columns([
                    pl.lit(None).alias("ema")
                ])
            
          
            
            fyersData_polars.write_csv("fyersData_polars.csv")
            Last4Candles=fyersData_polars.tail(4)
            dates_list = Last4Candles["date"].to_list()
            closes_list = Last4Candles["close"].to_list()
            opens_list = Last4Candles["open"].to_list()
            highs_list = Last4Candles["high"].to_list()
            lows_list = Last4Candles["low"].to_list()
            ema_list = Last4Candles["ema"].to_list()

            lastcandletime = dates_list[-1]
            SecondLastCandleTime = dates_list[-2]
            ThirdLastCandleTime = dates_list[-3]
            FourthLastCandleTime = dates_list[-4]

            # print("lastcandletime: ", lastcandletime)i
            # print("ThirdLastCandleTime: ", ThirdLastCandleTime)
            # print("FourthLastCandleTime: ", FourthLastCandleTime)
            
            lastcandleclose = closes_list[-1]
            SecondLastCandleClose = closes_list[-2]
            ThirdLastCandleClose = closes_list[-3]
            FourthLastCandleClose = closes_list[-4]

            lastcandleopen = opens_list[-1]
            SecondLastCandleOpen = opens_list[-2]
            ThirdLastCandleOpen = opens_list[-3]
            FourthLastCandleOpen = opens_list[-4]

            lastcandlehigh = highs_list[-1]
            SecondLastCandleHigh = highs_list[-2]
            ThirdLastCandleHigh = highs_list[-3]
            FourthLastCandleHigh = highs_list[-4]

            lastcandlelow = lows_list[-1]
            SecondLastCandleLow = lows_list[-2]
            ThirdLastCandleLow = lows_list[-3]
            FourthLastCandleLow = lows_list[-4]

            lastcandleema = ema_list[-1]
            SecondLastCandleEma = ema_list[-2]
            ThirdLastCandleEma = ema_list[-3]
            FourthLastCandleEma = ema_list[-4]

            # print("lastcandleclose: ", lastcandleclose)
            # print("SecondLastCandleClose: ", SecondLastCandleClose)
            # print("ThirdLastCandleClose: ", ThirdLastCandleClose)
            # print("FourthLastCandleClose: ", FourthLastCandleClose)
            print(
                "\n"
                f"── {symbol_name} ─────────────────────────────────────\n"
                f"Time: {datetime.now()} | TF: {params.get('Timeframe')}m\n"
                f"State: {params.get('CrossOverStatus')} | BarsLeft: {params.get('BarsLeft')} | Trade: {params.get('Trade')}\n"
                f"CrossOverTime: {params.get('CrossOverTime')} | LastRedTime: {params.get('LastRedTime')} | LastEval: {params.get('LastEvaluatedTime')}\n"
                f"Closed Candle @ {SecondLastCandleTime}  "
                f"O:{SecondLastCandleOpen:.2f} H:{SecondLastCandleHigh:.2f} L:{SecondLastCandleLow:.2f} "
                f"C:{SecondLastCandleClose:.2f}  EMA:{SecondLastCandleEma:.2f}\n"
                f"Levels → Entry:{params.get('EntryPrice')}  SL:{params.get('StoplossValue')}  "
                f"TP:{params.get('TargetPrice')}  Buf:{params.get('EntryBuffer')}\n"
                f"LTP:{params.get('FyresLtp')}  EntryExec:{params.get('EntryExecutedPrice')}  "
                f"RemQty:{params.get('RemainingQty')}  PartialBooked:{params.get('PartialBooked')}\n"
            )

            print("-"*50)

            # ---- DETECT GREEN EMA CROSSOVER (second-last closed bar) ----
            if (
                SecondLastCandleClose > SecondLastCandleOpen and
                SecondLastCandleClose > SecondLastCandleEma and
                ThirdLastCandleClose  < ThirdLastCandleEma and
                params.get("CrossOverStatus") is None
            ):
                print(f"Green Candle Crossover Detected {symbol_name} at {lastcandletime}")
                params["CrossOverStatus"] = "AwaitRed"           # start 4-bar window
                params["CrossOverTime"]   = lastcandletime       # marks bar after which we start counting
                params["BarsLeft"]        = 4
                params["LastRedTime"]     = None
                params["LastEvaluatedTime"] = None               # to avoid double-counting same bar
                # clear levels
                params["EntryPrice"] = None
                params["StoplossValue"] = None
                params["CandleLength"] = None
                params["TargetPrice"] = None

            # ---- WITHIN 4-BAR WINDOW: SEARCH FOR A VALID RED (close > EMA) ----
            # Evaluate only when a newer closed bar appears after the crossover bar
            if params.get("CrossOverStatus") == "AwaitRed" and params.get("CrossOverTime") is not None:
                if lastcandletime > params["CrossOverTime"]:
                    # ensure we process each completed bar once
                    if params.get("LastEvaluatedTime") is None or SecondLastCandleTime > params["LastEvaluatedTime"]:
                        # decrement window on each new processed closed bar
                        if params.get("BarsLeft") is None:
                            params["BarsLeft"] = 4
                        if params["BarsLeft"] > 0:
                            # candidate red?
                            if SecondLastCandleClose < SecondLastCandleOpen:
                                if SecondLastCandleClose > SecondLastCandleEma:
                                    # lock levels from this red candle
                                    print(f"Red Candle Detected {symbol_name} at {SecondLastCandleTime}")
                                    try:
                                        entry_buf = float(params.get("EntryBuffer", 0.0))
                                    except:
                                        entry_buf = 0.0
                                    params["EntryPrice"]    = SecondLastCandleHigh + entry_buf
                                    params["StoplossValue"] = SecondLastCandleLow
                                    params["CandleLength"]  = SecondLastCandleHigh - SecondLastCandleLow
                                    params["TargetPrice"]   = SecondLastCandleClose + params["CandleLength"]
                                    params["CrossOverStatus"] = "RedLocked"
                                    params["LastRedTime"]   = SecondLastCandleTime
                                else:
                                    # red but invalid (close below EMA) -> reset
                                    print(f"Invalidated (red close < EMA) after crossover on {symbol_name} at {SecondLastCandleTime}")
                                    params["CrossOverStatus"] = None
                                    params["CrossOverTime"]   = None
                                    params["BarsLeft"]        = 0
                                    params["LastRedTime"]     = None
                                    params["EntryPrice"] = params["StoplossValue"] = params["CandleLength"] = params["TargetPrice"] = None

                            # after evaluating this bar, tick the window
                            params["BarsLeft"] -= 1

                            # if we ran out of bars and still no valid red -> reset
                            if params["BarsLeft"] <= 0 and params["CrossOverStatus"] == "AwaitRed":
                                print(f"No valid red within 4 bars. Resetting {symbol_name}.")
                                params["CrossOverStatus"] = None
                                params["CrossOverTime"]   = None
                                params["BarsLeft"]        = 0
                                params["LastRedTime"]     = None
                                params["EntryPrice"] = params["StoplossValue"] = params["CandleLength"] = params["TargetPrice"] = None

                        # mark processed bar
                        params["LastEvaluatedTime"] = SecondLastCandleTime

            # ---- AFTER A RED IS LOCKED: MANAGE NEXT CLOSED BARS UNTIL TRIGGER ----
            elif params.get("CrossOverStatus") == "RedLocked" and params.get("LastRedTime") is not None and params.get("Trade") is None:
                # process only a newer closed bar after the last red we used
                if SecondLastCandleTime > params["LastRedTime"] and (params.get("LastEvaluatedTime") is None or SecondLastCandleTime > params["LastEvaluatedTime"]):
                    # case 1: next closed bar also red AND close > EMA -> roll forward to this newer red
                    if SecondLastCandleClose < SecondLastCandleOpen and SecondLastCandleClose > SecondLastCandleEma:
                        print(f"Updating red reference {symbol_name} at {SecondLastCandleTime}")
                        try:
                            entry_buf = float(params.get("EntryBuffer", 0.0))
                        except:
                            entry_buf = 0.0
                        params["EntryPrice"]    = SecondLastCandleHigh + entry_buf
                        params["StoplossValue"] = SecondLastCandleLow
                        params["CandleLength"]  = SecondLastCandleHigh - SecondLastCandleLow
                        params["TargetPrice"]   = SecondLastCandleClose + params["CandleLength"]
                        params["LastRedTime"]   = SecondLastCandleTime

                    # case 2: any close below EMA -> reset
                    elif SecondLastCandleClose < SecondLastCandleEma:
                        print(f"Invalidated (close < EMA) after red on {symbol_name} at {SecondLastCandleTime}. Resetting.")
                        params["CrossOverStatus"] = None
                        params["CrossOverTime"]   = None
                        params["BarsLeft"]        = 0
                        params["LastRedTime"]     = None
                        params["EntryPrice"] = params["StoplossValue"] = params["CandleLength"] = params["TargetPrice"] = None
                        

                    # case 3: green bar before trigger -> reset (your rule)
                    elif SecondLastCandleClose > SecondLastCandleOpen:
                        print(f"Green candle after red without trigger. Resetting {symbol_name} at {SecondLastCandleTime}.")
                        params["CrossOverStatus"] = None
                        params["CrossOverTime"]   = None
                        params["BarsLeft"]        = 0
                        params["LastRedTime"]     = None
                        params["EntryPrice"] = params["StoplossValue"] = params["CandleLength"] = params["TargetPrice"] = None

                    # else: doji/neutral above EMA -> keep waiting for LTP trigger
                    params["LastEvaluatedTime"] = SecondLastCandleTime
            
            if (
                params["Trade"] is None 
                and params["EntryPrice"] is not None and params["EntryPrice"] > 0 
                and params["FyresLtp"] is not None 
                and params["FyresLtp"] >= params["EntryPrice"]
                ):
                print(f"Triggering trade {symbol_name} at {SecondLastCandleTime}")
                params["Trade"] = "Entry"
                params["CrossOverStatus"] = "Triggered"
                params["EntryExecutedPrice"] = params["FyresLtp"]
                params["StoplossValue"] = params["StoplossValue"]
                params["CandleLength"] = params["CandleLength"]
                params["TargetPrice"] = params["TargetPrice"]
                params["RemainingQty"] = params["Quantity"]
                params["PartialBooked"] = False
                params["TP1QTY"] = params["TP1QTY"]
                params["TP1Price"] = params["TP1Price"]
                place_order(symbol=params["FyresSymbol"],quantity=params["Quantity"],type=1,side=1,price=params["FyresLtp"])
                write_to_order_logs(f"[{symbol_name}] BUY {params['Quantity']} @ {params['FyresLtp']}")

            
            # --- PARTIAL TAKE PROFIT: exit half when target hits (only once) ---
            if (params["Trade"] == "Entry" 
                and params["FyresLtp"] is not None and params["TargetPrice"] is not None 
                and params["FyresLtp"] >= params["TargetPrice"] 
                and not params["PartialBooked"]):

                params["PartialBooked"] = True
                params["RemainingQty"] = params["Quantity"] - params["TP1QTY"]
                print(f"[TP1] {symbol_name}: SOLD {params['TP1QTY']} @ {params['FyresLtp']}. Remaining {params['RemainingQty']}")
                place_order(symbol=params["FyresSymbol"],quantity=params["TP1QTY"],type=1,side=-1,price=params["FyresLtp"])
                write_to_order_logs(f"[TP1] {symbol_name}: SELL {params['TP1QTY']} @ {params['FyresLtp']}")
            

            # --- STOPLOSS: exit all remaining if price hits SL ---
            if (params["Trade"] == "Entry" 
                and params["FyresLtp"] is not None and params["StoplossValue"] is not None 
                and params["FyresLtp"] <= params["StoplossValue"] 
                ):

                sell_qty = params["RemainingQty"]
                # place_market_sell(symbol_name, sell_qty)
                
                params["Trade"] = None
                params["PartialBooked"] = False
                print(f"[SL]  {symbol_name}: EXIT ALL {sell_qty} @ {params['FyresLtp']}")
                place_order(symbol=params["FyresSymbol"],quantity=sell_qty,type=1,side=-1,price=params["FyresLtp"])

                write_to_order_logs(f"[SL] {symbol_name}: EXIT ALL  {sell_qty} @ {params['FyresLtp']}")
                params["RemainingQty"] = 0

                # full reset of signal levels (prevents stale re-triggers)
                params["CrossOverStatus"] = None
                params["CrossOverTime"]   = None
                params["BarsLeft"]        = 0
                params["LastRedTime"]     = None
                params["EntryPrice"] = params["StoplossValue"] = params["CandleLength"] = params["TargetPrice"] = None

                


                

            

            
    except Exception as e:
        print("Error in main strategy:", str(e))
        traceback.print_exc()

if __name__ == "__main__":
    # # Initialize settings and credentials
    #   # <-- Add this line
    credentials_dict_fyers = get_api_credentials_Fyers()
    redirect_uri = credentials_dict_fyers.get('redirect_uri')
    client_id = credentials_dict_fyers.get('client_id')
    secret_key = credentials_dict_fyers.get('secret_key')
    grant_type = credentials_dict_fyers.get('grant_type')
    response_type = credentials_dict_fyers.get('response_type')
    state = credentials_dict_fyers.get('state')
    TOTP_KEY = credentials_dict_fyers.get('totpkey')
    FY_ID = credentials_dict_fyers.get('FY_ID')
    PIN = credentials_dict_fyers.get('PIN')
        # Automated login and initialization steps
    automated_login(client_id=client_id, redirect_uri=redirect_uri, secret_key=secret_key, FY_ID=FY_ID,
                                        PIN=PIN, TOTP_KEY=TOTP_KEY)
    get_user_settings()

    # websocket connection
    fyres_websocket(FyerSymbolList)
    time.sleep(4)


    while True:
            now =   datetime.now()   
            print(f"\nStarting main strategy at {datetime.now()}")
            main_strategy()
            time.sleep(1)
         
    
