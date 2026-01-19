#!/usr/bin/env python3
"""Diagnostic script to test yfinance market cap fetching"""

import yfinance as yf

tickers_to_test = ['SPY', 'AAPL', 'NVDA', 'BTC-USD', 'GC=F']

for symbol in tickers_to_test:
    print(f"\n{'='*50}")
    print(f"Testing: {symbol}")
    print('='*50)
    
    ticker = yf.Ticker(symbol)
    
    # Test fast_info
    print("\n--- fast_info ---")
    try:
        fi = ticker.fast_info
        print(f"Type: {type(fi)}")
        print(f"Available keys/attrs: {[k for k in dir(fi) if not k.startswith('_')]}")
        try:
            print(f"market_cap: {fi.market_cap}")
        except Exception as e:
            print(f"market_cap ERROR: {e}")
        try:
            print(f"shares_outstanding: {fi.shares_outstanding}")
        except Exception as e:
            print(f"shares_outstanding ERROR: {e}")
        try:
            print(f"last_price: {fi.last_price}")
        except Exception as e:
            print(f"last_price ERROR: {e}")
    except Exception as e:
        print(f"fast_info FAILED: {e}")
    
    # Test info
    print("\n--- info (slow, may fail) ---")
    try:
        info = ticker.info
        print(f"marketCap: {info.get('marketCap', 'NOT FOUND')}")
        print(f"totalAssets: {info.get('totalAssets', 'NOT FOUND')}")
        print(f"sharesOutstanding: {info.get('sharesOutstanding', 'NOT FOUND')}")
    except Exception as e:
        print(f"info FAILED: {e}")
