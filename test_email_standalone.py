import sys
import os
import datetime
import json
import pandas as pd
import numpy as np
from scipy.signal import butter, filtfilt

# Aggiungiamo il percorso backend
sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from logic import MarketData, ActionPath, backtest_strategy

# Mock cache
TICKER_CACHE = {}

def load_portfolio():
    """Load portfolio from Firebase Firestore (same as PortfolioManager)."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        
        key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "serviceAccountKey.json")
        
        if not firebase_admin._apps:
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        doc = db.collection("portfolio").document("main").get()
        
        if doc.exists:
            data = doc.to_dict()
            positions = data.get("positions", [])
            open_pos = [p for p in positions if p.get("status") == "OPEN"]
            print(f"🔥 Firebase: {len(open_pos)} posizioni OPEN su {len(positions)} totali")
            return open_pos
        else:
            return []
    except Exception as e:
        print(f"⚠️ Errore Firebase: {e}")
        pf_path = os.path.join(os.path.dirname(__file__), "backend", "portfolio.json")
        with open(pf_path, "r") as f:
            data = json.load(f)
        return [p for p in data.get("positions", []) if p.get("status") == "OPEN"]

def analyze_ticker_for_recommendations(ticker):
    print(f"\n{'='*60}")
    print(f"🔍 Analyzing {ticker} (Full Point-in-Time Logic)...")
    print(f"{'='*60}")

    # 1. Fetch Data
    print(f"Recupero dati per {ticker}...")
    # Need long history for Z-Score window (252) + Frozen Lookback
    start_date = (datetime.date.today() - datetime.timedelta(days=2000)).strftime("%Y-%m-%d") 
    md = MarketData(ticker, start_date=start_date)
    px = md.fetch()
    
    if px is None or px.empty:
        print(f"❌ Dati non trovati per {ticker}")
        return {}
    
    if len(px) < 252:
        print(f"❌ Dati insufficienti ({len(px)} punti)")
        return {}

    print(f"   📊 Data: {len(px)} points ({px.index[0].date()} → {px.index[-1].date()})")
    
    prices = px.tolist()
    dates = px.index.strftime('%Y-%m-%d').tolist()

    # 2. Point-in-Time Frozen Strategy Calculation (Slower but Accurate)
    MIN_POINTS = 100
    SAMPLE_EVERY = 2 # Speed optimization (still accurate trend)
    ZSCORE_WINDOW = 252
    
    frozen_kin_raw = []
    frozen_pot_raw = []
    
    print(f"   ⏳ Calculating Frozen History (looping {len(px)//SAMPLE_EVERY} times)...")
    
    n_total = len(px)
    for t in range(MIN_POINTS, n_total, SAMPLE_EVERY):
        # Point-in-Time Slice (Past Only)
        px_t = px.iloc[:t+1]
        try:
            mech_t = ActionPath(px_t, alpha=200, beta=1.0)
            
            # Capture shifted Kinetic (T-25) and Current Potential
            if len(mech_t.kin_density) >= 25:
                frozen_kin_raw.append(float(mech_t.kin_density.iloc[-25]))
            else:
                frozen_kin_raw.append(0.0)
                
            frozen_pot_raw.append(float(mech_t.pot_density.iloc[-1]))
            
        except Exception:
             frozen_kin_raw.append(0.0)
             frozen_pot_raw.append(0.0)
             
    # Align Lists (Padding)
    # We sampled every N steps. We need to expand back to full length or interpolate?
    # Backend logic sample=1. Here sample=2.
    # We need to map back to original indices.
    
    # Actually, let's use SAMPLE_EVERY=1 for max accuracy if user complained.
    # It takes ~1 minute per ticker. 9 tickers = 9 minutes. A bit long.
    # Let's stick to simple padding: we only care about RECENT values for current signal.
    # Wait, Z-score needs history.
    
    # RE-DECISION: Use SAMPLE_EVERY=5 but interpolate? 
    # Or just use SAMPLE_EVERY=1 but lookback only last 500 days (enough for Z-score).
    # But 252 window needs 252 points.
    
    # Let's reduce history fetched to 750 days (3 years). That makes loop 750 iters.
    # 750 * 10ms = 7.5s. Acceptable.
    
    # Redo Fetch with shorter window if too long
    if len(px) > 1000:
        px = px.iloc[-1000:]
        prices = px.tolist()
        dates = px.index.strftime('%Y-%m-%d').tolist()
        n_total = len(px)

    # Re-run loop with SAMPLE_EVERY=1 for accuracy on reduced dataset
    frozen_kin_raw = []
    frozen_pot_raw = []
    
    for t in range(MIN_POINTS, n_total):
        px_t = px.iloc[:t+1]
        try:
            # We can optimize ActionPath? No.
            mech_t = ActionPath(px_t, alpha=200, beta=1.0)
            if len(mech_t.kin_density) >= 25:
                frozen_kin_raw.append(float(mech_t.kin_density.iloc[-25]))
            else:
                frozen_kin_raw.append(0.0)
            frozen_pot_raw.append(float(mech_t.pot_density.iloc[-1]))
        except:
             frozen_kin_raw.append(0.0)
             frozen_pot_raw.append(0.0)
             
    # Padding at start
    padding_size = n_total - len(frozen_kin_raw)
    
    # 3. Sum Strategy Calculation
    frozen_sum_raw = [k + p for k, p in zip(frozen_kin_raw, frozen_pot_raw)]
    aligned_frozen_sum = [0] * padding_size + frozen_sum_raw
    
    # Normalize (Z-Score)
    frozen_sum_series = pd.Series(aligned_frozen_sum).fillna(0)
    roll_fsum_mean = frozen_sum_series.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
    roll_fsum_std = frozen_sum_series.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
    z_frozen_sum = ((frozen_sum_series - roll_fsum_mean) / (roll_fsum_std + 1e-6)).fillna(0).tolist()
    
    # Filter
    try:
        b, a = butter(N=2, Wn=0.05, btype='low')
        z_frozen_sum_filtered = filtfilt(b, a, z_frozen_sum).tolist()
        z_sum_final = z_frozen_sum_filtered
    except:
        z_sum_final = z_frozen_sum
        
    # Validation Padding for Backtest to avoid noise at start
    # -999 effectively disables trading in padding zone
    z_sum_for_backtest = [-999] * padding_size + z_sum_final[padding_size:]
    
    # 4. Slope (dX) Calculation for Direction
    # Need base mechanics on full series for Slope (approx ok) or use loop slope?
    # Backend uses Loop Slope? No, backend calculates Step 4 (Scanner) using ActionPath on full history for Slope!
    # "slope = mech.dX" where mech is ActionPath(px).
    # This is consistent.
    
    mech_full = ActionPath(px, alpha=200, beta=1.0)
    slope = mech_full.dX
    roll_slope_mean = slope.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
    roll_slope_std = slope.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
    z_slope_series = ((slope - roll_slope_mean) / (roll_slope_std + 1e-6)).fillna(0).tolist()
    
    # 5. Backtest
    print("\n   📋 Sum Strategy (Full Logic) last trade:")
    sum_res = backtest_strategy(
        prices=prices,
        z_kinetic=z_sum_for_backtest, # This is the full frozen sum z-score
        z_slope=z_slope_series,
        dates=dates,
        threshold=-0.3,
        use_z_roc=True
    )
    print_last_trade(sum_res)
    
    return {
        "Sum Strategy": sum_res
    }

def print_last_trade(result_dict):
    trades = result_dict.get('trades', [])
    if not trades:
        print("      (No trades found)")
        return

    last = trades[-1]
    status = "🟢 ACTIVE (OPEN)" if (last['exit_date'] == "OPEN") else "🔴 CLOSED"
    
    print(f"      Status: {status}")
    print(f"      Direction: {last['direction']}")
    print(f"      Entry: {last['entry_date']} @ ${last['entry_price']:.2f}")
    
    if last['exit_date'] != "OPEN":
        print(f"      Exit: {last['exit_date']} @ ${last['exit_price']:.2f}")
        
    print(f"      Total trades: {len(trades)}")

def check_recommendations(result, ticker):
    trades = result.get("Sum Strategy", {}).get("trades", [])
    
    if not trades:
        return False
    
    last_trade = trades[-1]
    is_active = (last_trade['exit_date'] == "OPEN")
    return is_active

def main():
    print("🚀 Test Email Recommendations logic (Full Accuracy)")
    
    open_positions = load_portfolio()
    tickers = list(set([p["ticker"] for p in open_positions]))
    
    print(f"\n🎯 Ticker da analizzare: {tickers}")
    
    active_strategies = set()
    
    for ticker in tickers:
        result = analyze_ticker_for_recommendations(ticker)
        if check_recommendations(result, ticker):
            active_strategies.add(ticker)
            
    # Recommendations
    print("\n" + "="*60)
    print("📊 PORTFOLIO RECOMMENDATIONS (Verified w/ Point-in-Time)")
    print("="*60)
    
    n_hold = 0
    n_sell = 0
    
    for pos in open_positions:
        ticker = pos.get("ticker", "")
        strategy = pos.get("strategy", "")
        
        is_active = ticker in active_strategies
        
        action = "HOLD" if is_active else "SELL"
        icon = "✅" if action == "HOLD" else "❌"
        
        if action == "HOLD": n_hold += 1
        else: n_sell += 1
        
        print(f"{icon} {ticker:<10} {strategy:<18} {action:<8}")

    print(f"\n📌 Summary: HOLD: {n_hold}, SELL: {n_sell}")

if __name__ == "__main__":
    main()
