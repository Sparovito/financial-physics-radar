import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import numpy as np
import pandas as pd
from logic import MarketData, ActionPath, FourierEngine, MarketScanner

app = FastAPI(title="Financial Physics API")

# Abilita CORS per permettere al frontend (file locale) di chiamare l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from typing import List

# Modelli Dati (Pydantic)
class AnalysisRequest(BaseModel):
    ticker: str
    alpha: float = 200.0
    beta: float = 1.0
    top_k: int = 5
    forecast_days: int = 60
    start_date: Optional[str] = "2023-01-01"

class ScanRequest(BaseModel):
    tickers: List[str]

from logic import MarketData, ActionPath, FourierEngine, MarketScanner

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
        md = MarketData(req.ticker, start_date=req.start_date)
        px = md.fetch() # Pandas Series
        
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
                "cumulative": cum_action
            },
            "indicators": {
                "slope": slope_line,
                "z_residuo": z_residuo_line
            },
            "forecast": {
                "dates": dates_future,
                "values": future_scenario
            },
            "fourier_components": fourier_comps
        }

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Errore server: {tb}")
        raise HTTPException(status_code=500, detail=f"Errore Interno: {str(e)}\n\n{tb}")

@app.get("/health")
def health_check():
    return {"status": "running"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
