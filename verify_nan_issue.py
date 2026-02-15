import yfinance as yf
import pandas as pd

tickers = ['AAPL', 'ITW', 'JNJ', 'MUV2.DE']
print(f"Downloading {tickers}...")

# Test 1: Current Logic (1d)
data = yf.download(tickers, period="1d", group_by='ticker', auto_adjust=True, progress=False, threads=True)
print("\n--- 1d Data Last Row ---")
for t in tickers:
    if t in data.columns:
        val = data[t]["Close"].iloc[-1]
        print(f"{t}: {val}")

# Test 2: 5d Data to see context
data5 = yf.download(tickers, period="5d", group_by='ticker', auto_adjust=True, progress=False, threads=True)
print("\n--- 5d Data Tail ---")
print(data5.tail())

print("\n--- Testing DropNA Fix ---")
for t in tickers:
    if t in data5.columns:
        series = data5[t]["Close"]
        # Filter out NaNs
        clean_series = series.dropna()
        if not clean_series.empty:
            val = clean_series.iloc[-1]
            print(f"{t} (Last Valid): {val}")
        else:
            print(f"{t}: All NaN")
