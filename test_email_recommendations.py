import sys
import os
import json

# Ensure backend directory is in path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

def get_portfolio_tickers():
    try:
        with open("backend/portfolio.json", "r") as f:
            data = json.load(f)
            return list(set([p["ticker"] for p in data.get("positions", [])]))
    except Exception as e:
        print(f"⚠️ Could not load portfolio: {e}")
        return []

def test_recommendations():
    print("🧪 Starting Optimized Market Scan Test...")
    
    # 1. Identify Tickers to Scan
    pf_tickers = get_portfolio_tickers()
    test_tickers = list(set(pf_tickers + ["AAPL"]))
    print(f"🎯 Scanning specific tickers: {test_tickers}")
    
    # 2. Monkeypatch load_tickers to speed up test
    import backend.scanner
    
    # Mock function
    def mock_load_tickers():
        # Return a dummy map just to satisfy the keys loop
        return {t: "Test Category" for t in test_tickers}
        
    # Apply patch
    original_load = backend.scanner.load_tickers
    backend.scanner.load_tickers = mock_load_tickers
    
    print("-" * 40)
    
    try:
        # 3. Run scan with email disabled
        results = backend.scanner.run_market_scan(send_email=False)
        
        print("-" * 40)
        print("📊 Scan Results Summary:")
        print(f"   Buy Today: {len(results.get('buy_today', []))}")
        print(f"   Portfolio Positions Checked: {len(results.get('portfolio', []))}")
        print("\n🔵 PORTFOLIO STATUS DETAILS:")
        for p in results.get('portfolio', []):
            icon = "✅" if p['action'] == "HOLD" else "❌"
            print(f"   {icon} {p['ticker']} ({p['strategy']}): {p['action']}")
            
        print("-" * 40)
    finally:
        # Restore (good practice)
        backend.scanner.load_tickers = original_load

if __name__ == "__main__":
    test_recommendations()
