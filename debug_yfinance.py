import yfinance as yf
import time

print("--- Testing Single Ticker (SPY) ---")
try:
    t = yf.Ticker("SPY")
    hist = t.history(period="1d")
    print("Single fetch result:")
    print(hist)
except Exception as e:
    print(f"Single fetch failed: {e}")

print("\n--- Testing Batch Download (AAPL, MSFT) ---")
try:
    data = yf.download(["AAPL", "MSFT"], period="1d", group_by='ticker', progress=True)
    print("Batch fetch result:")
    print(data)
except Exception as e:
    print(f"Batch fetch failed: {e}")
