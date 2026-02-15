import yfinance as yf
import pandas as pd

print("--- TESTING 1 TICKER ---")
df1 = yf.download(["AAPL"], period="1d", group_by='ticker', auto_adjust=True, progress=False)
print("Columns:", df1.columns)
if isinstance(df1.columns, pd.MultiIndex):
    print("MultiIndex Levels:", df1.columns.levels)
else:
    print("Flat Index")

if "Close" in df1.columns:
    print("Found 'Close' in columns")
if "AAPL" in df1.columns:
    print("Found 'AAPL' in columns")

print("\n--- TESTING 2 TICKERS ---")
df2 = yf.download(["AAPL", "SPY"], period="1d", group_by='ticker', auto_adjust=True, progress=False)
print("Columns:", df2.columns)
if isinstance(df2.columns, pd.MultiIndex):
    print("MultiIndex Levels:", df2.columns.levels)

print("\n--- SIMULATING BACKEND LOGIC ---")
tickers = ["AAPL"]
data = df1
prices = {}
if len(tickers) == 1:
    ticker = tickers[0]
    # Current broken logic simulation:
    if not data.empty and "Close" in data.columns:
        print(f"Logic 1 (Close in cols): MATCH -> {data['Close'].iloc[-1]}")
    elif not data.empty and ticker in data.columns: # Improved logic?
        print(f"Logic 2 (Ticker in cols): MATCH -> checking sub-columns")
        try:
            val = data[ticker]["Close"].iloc[-1]
            print(f"Got price via ticker index: {val}")
        except:
             print("Failed accessing [Timer][Close]")
    else:
        print("Logic FAILED: neither Close nor Ticker found at top level easily?")
