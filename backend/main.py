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
        
        # 1. Scarica Dati
        md = MarketData(req.ticker, start_date=req.start_date, end_date=req.end_date)
        px = md.fetch() # Pandas Series
        
        # If end_date is set, truncate data to simulate being in the past
        if req.end_date:
            end_ts = pd.Timestamp(req.end_date)
            px = px[px.index <= end_ts]
            print(f"🕐 Simulating past: data truncated to {req.end_date}, {len(px)} points remaining")
        
        # 2. Calcola Minima Azione
        mechanics = ActionPath(px, alpha=req.alpha, beta=req.beta)
        
        # 3. Calcola Fourier
        fourier = FourierEngine(px, top_k=req.top_k)
        future_idx, future_vals = fourier.reconstruct_scenario(future_horizon=req.forecast_days)
        
        # 4. Prepara Risposta JSON
        # Convertiamo tutto in liste/stringhe per JSON
        
        # Date (unificate nel formato YYYY-MM-DD)
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
        
        # ROC (Rate of Change) - ISTANTANEO, no look-ahead bias
        # ROC = (price[t] - price[t-n]) / price[t-n] * 100
        ROC_PERIOD = 20  # 20 giorni lookback
        roc = ((px - px.shift(ROC_PERIOD)) / px.shift(ROC_PERIOD) * 100).fillna(0)
        roc_line = roc.values.tolist()
        
        # Z-Score del ROC (rolling per consistenza)
        roll_roc_mean = roc.rolling(window=252, min_periods=20).mean()
        roll_roc_std = roc.rolling(window=252, min_periods=20).std()
        z_roc = ((roc - roll_roc_mean) / (roll_roc_std + 1e-6)).fillna(0)
        z_roc_line = z_roc.values.tolist()
        
        # 6. FROZEN Z-SCORES (Point-in-Time) - Expanding Window
        # Calculate what z_kin would have been at each point using ONLY data up to that point
        # SAMPLE_EVERY=1 ensures daily precision (slower but accurate)
        SAMPLE_EVERY = 1
        MIN_POINTS = 100  # Minimum data points needed
        
        frozen_z_kin = []
        frozen_z_pot = []
        frozen_dates = []
        
        n = len(px)
        for t in range(MIN_POINTS, n, SAMPLE_EVERY):
            # Truncate data to day t (only past data)
            px_t = px.iloc[:t+1]
            
            try:
                # Recalculate mechanics with truncated data
                mech_t = ActionPath(px_t, alpha=req.alpha, beta=req.beta)
                kin_t = mech_t.kin_density
                pot_t = mech_t.pot_density
                
                # Save RAW DENSITY (Frozen at time t) instead of Z-Score
                # This ensures we compare apples-to-apples with the main Energy chart
                raw_kin_t = kin_t.iloc[-1]
                raw_pot_t = pot_t.iloc[-1]
                
                frozen_z_kin.append(round(float(raw_kin_t), 2))
                frozen_z_pot.append(round(float(raw_pot_t), 2))
                frozen_dates.append(px.index[t].strftime('%Y-%m-%d'))
            except:
                continue
        
        print(f"📊 Frozen Z-Scores calculated: {len(frozen_dates)} points")
        
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
        backtest_result = backtest_strategy(
            prices=price_real,
            z_kinetic=z_kin_series,
            z_slope=z_slope_series,
            dates=dates_historical
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
        
        return {
            "status": "ok",
            "ticker": req.ticker,
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
            "forecast": {
                "dates": dates_future,
                "values": future_scenario
            },
            "fourier_components": fourier_comps,
            "frozen": {
                "dates": frozen_dates,
                "z_kinetic": frozen_z_kin,
                "z_potential": frozen_z_pot
            },
            "backtest": backtest_result
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
