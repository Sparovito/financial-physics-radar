import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import numpy as np
import pandas as pd
import os
import sys

# Ensure the directory containing this file is in the Python path
# This fixes "ModuleNotFoundError: No module named 'logic'" on Railway
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from logic import MarketData, ActionPath, FourierEngine, MarketScanner

app = FastAPI(title="Financial Physics API")

# Abilita CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelli Dati (Pydantic)
class AnalysisRequest(BaseModel):
    ticker: str
    alpha: float = 200.0
    beta: float = 1.0
    top_k: int = 5
    forecast_days: int = 60
    start_date: Optional[str] = "2023-01-01"
    end_date: Optional[str] = None  # If set, truncate data to this date (simulate past)
    use_cache: bool = False # If True, try to use cached full history

# Global Cache for Full Ticker History (DataFrame)
# Key: Ticker, Value: Pandas Series (Full History)
TICKER_CACHE = {}

class ScanRequest(BaseModel):
    tickers: List[str]

@app.post("/scan")
async def scan_market(req: ScanRequest):
    try:
        print(f"📡 Radar Scan richiesto per {len(req.tickers)} titoli...")
        scanner = MarketScanner(req.tickers)
        results = scanner.scan()
        return {"status": "ok", "results": results}
    except Exception as e:
        print(f"Errore scan: {e}")
        return {"status": "error", "detail": str(e)}

@app.post("/analyze")
async def analyze_stock(req: AnalysisRequest):
    try:
        print(f"Ricevuta richiesta: {req.dict()}")
        
        # 1. Scarica Dati & Gestione Cache Avanzata
        px = None
        full_frozen_data = None
        
        # Check Cache
        use_cache_data = False
        if req.use_cache and req.ticker in TICKER_CACHE:
            cached_obj = TICKER_CACHE[req.ticker]
            cached_px = cached_obj["px"]
            
            # Verify Date Coverage
            if req.start_date:
                req_start_ts = pd.Timestamp(req.start_date)
                # If cached data starts significantly later than requested, it's insufficient
                if cached_px.index[0] > req_start_ts + pd.Timedelta(days=10):
                    print(f"⚠️ Cache miss (Storia insufficiente): Cached({cached_px.index[0].date()}) > Req({req.start_date})")
                    use_cache_data = False
                else:
                    use_cache_data = True
            else:
                use_cache_data = True

        if use_cache_data:
            print(f"⚡ CACHE HIT: Uso dati in memoria per {req.ticker}")
            cached_obj = TICKER_CACHE[req.ticker]
            px = cached_obj["px"]
            full_frozen_data = cached_obj.get("frozen", None)
        else:
            # Scarica storia COMPLETA
            print(f"🌐 API FETCH: Scarico dati freschi per {req.ticker}...")
            md = MarketData(req.ticker, start_date=req.start_date, end_date=None)
            px = md.fetch()
            
            # --- PRE-CALCOLO FROZEN HISTORY (Heavy Computation) ---
            print(f"🧊 Pre-calcolo Frozen History completa (può richiedere tempo)...")
            SAMPLE_EVERY = 1
            MIN_POINTS = 100
            
            f_kin, f_pot, f_dates = [], [], []
            n_total = len(px)
            
            for t in range(MIN_POINTS, n_total, SAMPLE_EVERY):
                px_t = px.iloc[:t+1]
                try:
                    mech_t = ActionPath(px_t, alpha=req.alpha, beta=req.beta)
                    # Save RAW DENSITY
                    f_kin.append(round(float(mech_t.kin_density.iloc[-1]), 2))
                    f_pot.append(round(float(mech_t.pot_density.iloc[-1]), 2))
                    f_dates.append(px.index[t].strftime('%Y-%m-%d'))
                except:
                    continue
            
            full_frozen_data = {
                "dates": f_dates,
                "kin": f_kin,
                "pot": f_pot
            }
            
            # Salva tutto in cache
            TICKER_CACHE[req.ticker] = {
                "px": px,
                "frozen": full_frozen_data
            }

        # --- SIMULATION TIME TRAVEL (Slicing istantaneo) ---
        if req.end_date:
            end_ts = pd.Timestamp(req.end_date)
            # Slice Prices
            px = px[px.index <= end_ts]
            
            # Slice Frozen Data
            # Troviamo l'indice fin dove arrivare nei dati frozen
            target_date_str = req.end_date
            
            # Filtro rapido liste (date frozen sono già sorted)
            trunc_dates = []
            trunc_kin = []
            trunc_pot = []
            
            # Ottimizzazione: bisect o semplice loop finché <= date
            # Dato che sono stringhe YYYY-MM-DD, confronto lessicografico funziona
            for i, d in enumerate(full_frozen_data["dates"]):
                if d <= target_date_str:
                    trunc_dates.append(d)
                    trunc_kin.append(full_frozen_data["kin"][i])
                    trunc_pot.append(full_frozen_data["pot"][i])
                else:
                    break # Stop appena superiamo la data
            
            frozen_dates = trunc_dates
            frozen_z_kin = trunc_kin
            frozen_z_pot = trunc_pot
            
            print(f"🕐 Simulating past: data truncated to {req.end_date}")
        else:
            # Dati completi
            frozen_dates = full_frozen_data["dates"]
            frozen_z_kin = full_frozen_data["kin"]
            frozen_z_pot = full_frozen_data["pot"]
        
        # 2. Calcola Minima Azione (Live su dati tranciati)
        mechanics = ActionPath(px, alpha=req.alpha, beta=req.beta)
        
        # 3. Calcola Fourier
        fourier = FourierEngine(px, top_k=req.top_k)
        future_idx, future_vals = fourier.reconstruct_scenario(future_horizon=req.forecast_days)
        
        # 4. Prepara Risposta JSON
        dates_historical = px.index.strftime('%Y-%m-%d').tolist()
        
        # Prezzi
        price_real = px.values.tolist()
        price_min_action = mechanics.px_star.values.tolist()
        fundamentals = mechanics.F.values.tolist()
        
        # Densità Energia
        kin_density = mechanics.kin_density.values.tolist()
        pot_density = mechanics.pot_density.values.tolist()
        cum_action = mechanics.cumulative_action.values.tolist()
        
        # Indicatori Tecnici
        slope_line = mechanics.dX.values.tolist()
        z_residuo_line = mechanics.z_residuo.values.tolist()
        
        # ROC (Rate of Change)
        ROC_PERIOD = 20
        roc = ((px - px.shift(ROC_PERIOD)) / px.shift(ROC_PERIOD) * 100).fillna(0)
        roc_line = roc.values.tolist()
        
        # Z-Score del ROC
        roll_roc_mean = roc.rolling(window=252, min_periods=20).mean()
        roll_roc_std = roc.rolling(window=252, min_periods=20).std()
        z_roc = ((roc - roll_roc_mean) / (roll_roc_std + 1e-6)).fillna(0)
        z_roc_line = z_roc.values.tolist()
        
        # 5. Backtest Strategy
        # Calculate ROLLING Z-Scores to avoid look-ahead bias (252-day window)
        ZSCORE_WINDOW = 252
        
        kin = mechanics.kin_density
        roll_kin_mean = kin.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
        roll_kin_std = kin.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
        z_kin_series = ((kin - roll_kin_mean) / (roll_kin_std + 1e-6)).fillna(0).values.tolist()
        
        slope = mechanics.dX
        roll_slope_mean = slope.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
        roll_slope_std = slope.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
        z_slope_series = ((slope - roll_slope_mean) / (roll_slope_std + 1e-6)).fillna(0).values.tolist()
        
        from logic import backtest_strategy
        
        # --- STRATEGIA 1: LIVE KINETIC (Originale) ---
        backtest_result = backtest_strategy(
            prices=price_real,
            z_kinetic=z_kin_series,
            z_slope=z_slope_series,
            dates=dates_historical,
            start_date=req.start_date,
            end_date=req.end_date
        )
        
        # --- STRATEGIA 2: FROZEN POTENTIAL (Richiesta User) ---
        # 1. Calcoliamo Z-Score della serie Frozen Potential (che è Raw Density)
        #    La serie frozen è più corta (parte da MIN_POINTS). Dobbiamo allinearla a Price.
        
        # Calculate padding size (difference in length)
        padding_size = len(price_real) - len(frozen_z_pot)
        
        # Prepend zeros/NaNs to align time series
        # Using 0 as neutral value for Z-score calc is safer than NaN for backtest logic
        aligned_frozen_pot = [0] * padding_size + frozen_z_pot
        
        # Ora è allineato
        frozen_pot_series = pd.Series(aligned_frozen_pot).fillna(0)
        
        # Calculate rolling stats
        roll_fpot_mean = frozen_pot_series.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
        roll_fpot_std = frozen_pot_series.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
        
        # Questo è lo Z-Score del Potenziale Frozen Point-in-Time
        z_frozen_pot_score = ((frozen_pot_series - roll_fpot_mean) / (roll_fpot_std + 1e-6)).fillna(0).values.tolist()
        
        # 2. Eseguiamo backtest sostituendo Kinetic con Frozen Potential
        #    Nota: Usiamo ancora z_slope Live per la direzione (Long/Short)
        backtest_result_frozen = backtest_strategy(
            prices=price_real,
            z_kinetic=z_frozen_pot_score, # Sostituiamo segnale trigger
            z_slope=z_slope_series,       # Manteniamo filtro direzionale
            dates=dates_historical,
            start_date=req.start_date,
            end_date=req.end_date
        )
        
        # Dati Futuri (Proiezione)
        # Nota: future_idx potrebbe contenere timestamp o interi, convertiamo
        try:
            dates_future = [d.strftime('%Y-%m-%d') for d in future_idx]
        except:
            # Fallback se non sono date
            dates_future = [str(d) for d in future_idx]
            
        future_scenario = future_vals.tolist()
        
        # Componenti Fourier
        fourier_comps = fourier.get_components()
        
        # [NEW] Market Metrics
        # 1. Avg Abs Kinetic
        avg_abs_kin = ((kin - roll_kin_mean) / (roll_kin_std + 1e-6)).fillna(0).abs().mean()
        
        # 2. Market Cap (Fast Info)
        try:
            # .fast_info is an object, access via attribute
            mkt_cap = md.ticker_obj.fast_info.market_cap
        except:
            try:
                # Fallback to key access just in case
                mkt_cap = md.ticker_obj.fast_info['market_cap']
            except:
                try:
                    # Fallback to .info
                    mkt_cap = md.ticker_obj.info.get('marketCap', 0)
                except:
                    mkt_cap = 0
        
        return {
            "status": "ok",
            "ticker": req.ticker,
            "avg_abs_kin": round(float(avg_abs_kin), 2),
            "market_cap": mkt_cap,
            "dates": dates_historical,
            "dates": dates_historical,
            "prices": price_real,
            "min_action": price_min_action,
            "fundamentals": fundamentals,
            "energy": {
                "kinetic": kin_density,
                "potential": pot_density,
                "cumulative": cum_action,
                "z_kinetic": z_kin_series,
                "z_slope": z_slope_series
            },
            "indicators": {
                "slope": slope_line,
                "z_residuo": z_residuo_line,
                "roc": roc_line,
                "z_roc": z_roc_line
            },
            "backtest": backtest_result,                  # Strategia Live
            "frozen_strategy": backtest_result_frozen,    # Strategia Frozen (NEW)
            "forecast": {
                "dates": dates_future,
                "values": future_scenario
            },
            "fourier_components": fourier_comps,
            "frozen": {
                "dates": frozen_dates,
                "z_kinetic": frozen_z_kin,
                "z_potential": frozen_z_pot
            }
        }

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Errore server: {tb}")
        raise HTTPException(status_code=500, detail=f"Errore Interno: {str(e)}\n\n{tb}")

@app.get("/health")
def health_check():
    return {"status": "running"}

# --- STATIC FILES SERVING (Fallback) ---

# Construct absolute path to frontend directory to avoid CWD issues
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

# 1. Mount Static Files (JS/CSS)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# 2. Serve Index at Root
@app.get("/")
async def read_index():
    return FileResponse(os.path.join(FRONTEND_DIR, 'index.html'))

# 3. Serve other files from frontend root (app.js, style.css)
# MUST BE LAST to avoid shadowing API routes
@app.get("/{filename}")
async def serve_frontend_file(filename: str):
    file_path = os.path.join(FRONTEND_DIR, filename)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
