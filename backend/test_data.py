import yfinance as yf
import sys
import ssl

# --- FIX SSL (Nuclear Option) ---
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context
# -------------------------------

print("--- TEST CONNESSIONE DATI (SSL BYPASS) ---")
TICKER = "SPY"
print(f"Tentativo download {TICKER}...")

try:
    data = yf.download(TICKER, period="1mo", progress=True)
    
    if data.empty:
        print("❌ Download vuoto (Il problema persiste).")
    else:
        print(f"✅ SUCCESSO! Scaricate {len(data)} righe.")
        print(data.head())
        
except Exception as e:
    print(f"❌ ERRORE: {e}")

print("\n-----------------------------")
