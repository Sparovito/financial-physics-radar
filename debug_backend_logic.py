import sys
import os

# Adjust path to find backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from main import PortfolioManager

pm = PortfolioManager()
tickers = ["AAPL"]
print(f"Testing batch fetch for: {tickers}")
try:
    prices = pm.get_batch_prices(tickers)
    print("Prices returned:", prices)
except Exception as e:
    print(f"CRITICAL ERROR: {e}")

print("\nTesting single fetch fallback logic:")
try:
    single = pm.get_price("AAPL")
    print("Single price returned:", single)
except Exception as e:
    print(f"CRITICAL ERROR SINGLE: {e}")
