import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt
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
            # Load ZigZag Series
            zigzag_series = cached_obj.get("zigzag", None)
            # [NEW] Volume loading
            volume_series = cached_obj.get("volume", None)
            if volume_series is None:
                volume_series = pd.Series([0]*len(px), index=px.index)
            
            # [NEW] Load Market Cap
            mkt_cap = cached_obj.get("mkt_cap", 0)

            # [NEW] Slice by Requested Start Date (if provided)
            if req.start_date:
                start_ts = pd.Timestamp(req.start_date)
                # Handle timezone if necessary (copying logic from cache check if distinct, 
                # but simple comparison usually works if both naive/aware or if pandas handles it)
                if px.index.tz is not None and start_ts.tz is None:
                    start_ts = start_ts.tz_localize(px.index.tz)
                
                px = px[px.index >= start_ts]
                if volume_series is not None:
                    volume_series = volume_series[volume_series.index >= start_ts]
                if zigzag_series is not None:
                    zigzag_series = zigzag_series[zigzag_series.index >= start_ts]
                
                # [NEW] Slice Frozen Data Lists by Start Date (String Comparison)
                if full_frozen_data:
                    start_date_str = req.start_date
                    # Lists are sorted by date. Find index where date >= start_date
                    idx_start = 0
                    for i, d in enumerate(full_frozen_data["dates"]):
                        if d >= start_date_str:
                            idx_start = i
                            break
                    
                    # Store sliced temporary copy (don't mutate cache directly if shared, but here we read)
                    # Actually we typically pass full_frozen_data to the response construction
                    # We should filter it here for the current request context
                    full_frozen_data = {
                        "dates": full_frozen_data["dates"][idx_start:],
                        "kin": full_frozen_data["kin"][idx_start:],
                        "pot": full_frozen_data["pot"][idx_start:],
                        "z_sum": full_frozen_data.get("z_sum", [])[idx_start:] 
                    }
        else:
            # Scarica storia COMPLETA
            print(f"🌐 API FETCH: Scarico dati freschi per {req.ticker}...")
            md = MarketData(req.ticker, start_date=req.start_date, end_date=None)
            px = md.fetch()
            
            # Extract Volume immediately
            if hasattr(md, 'df_full') and 'Volume' in md.df_full.columns:
                volume_series = md.df_full['Volume']
            else:
                volume_series = pd.Series([0]*len(px), index=px.index)

            # [NEW] Calculate Market Cap Logic (Moved here to avoid UnboundLocalError)
            mkt_cap = None
            try:
                mkt_cap = md.ticker_obj.fast_info.market_cap
            except:
                pass
            
            if mkt_cap is None:
                try:
                    info = md.ticker_obj.info
                    mkt_cap = info.get('marketCap') or info.get('totalAssets')
                except:
                    pass
            
            if mkt_cap is None:
                try:
                    shares = md.ticker_obj.fast_info.shares
                    price = md.ticker_obj.fast_info.last_price
                    if shares and price:
                        mkt_cap = shares * price
                except:
                    pass
            
            if mkt_cap is None:
                mkt_cap = 0
            
            print(f"📊 {req.ticker} Market Cap = {mkt_cap}")

            # [NEW] Calculate Cumulative Direction (ZigZag) - HOURLY AGGREGATED
            try:
                # Fetch hourly data for more granular ZigZag
                print(f"📊 Fetching hourly data for ZigZag...")
                hourly_data = md.ticker_obj.history(period="2y", interval="1h")
                
                if not hourly_data.empty and 'Open' in hourly_data.columns and 'Close' in hourly_data.columns:
                    # Calculate hourly direction (+1, -1, 0)
                    hourly_diff = hourly_data['Close'] - hourly_data['Open']
                    hourly_signs = hourly_diff.apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
                    
                    # Group by date and sum all hourly directions
                    hourly_signs.index = pd.to_datetime(hourly_signs.index).date
                    daily_net = hourly_signs.groupby(hourly_signs.index).sum()
                    
                    # Align with px dates and cumsum
                    zigzag_values = []
                    cumsum = 0
                    for date in px.index:
                        date_key = date.date()
                        if date_key in daily_net.index:
                            cumsum += daily_net[date_key]
                        zigzag_values.append(cumsum)
                    
                    zigzag_series = pd.Series(zigzag_values, index=px.index)
                    print(f"✅ ZigZag calcolato su {len(hourly_data)} candele orarie")
                else:
                    # Fallback to daily if hourly not available
                    print("⚠️ Hourly data not available, using daily fallback")
                    d_open = md.df_full['Open']
                    d_close = md.df_full['Close']
                    diff = d_close - d_open
                    signs = diff.apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
                    zigzag_series = signs.cumsum()
            except Exception as e:
                print(f"⚠️ Errore calcolo ZigZag: {e}")
                zigzag_series = pd.Series([0]*len(px), index=px.index)
            
            # --- PRE-CALCOLO FROZEN HISTORY (Heavy Computation) ---
            print(f"🧊 Pre-calcolo Frozen History completa (può richiedere tempo)...")
            SAMPLE_EVERY = 1
            MIN_POINTS = 100
            
            f_kin, f_pot, f_sum, f_dates = [], [], [], []
            n_total = len(px)
            
            for t in range(MIN_POINTS, n_total, SAMPLE_EVERY):
                px_t = px.iloc[:t+1]
                try:
                    mech_t = ActionPath(px_t, alpha=req.alpha, beta=req.beta)
                    
                    # 1. Kinetic Frozen (Shifted T-25 for prediction comparison)
                    lag_idx = -25
                    if len(mech_t.kin_density) >= 25:
                        val_kin = round(float(mech_t.kin_density.iloc[lag_idx]), 2)
                    else:
                        val_kin = 0.0
                    f_kin.append(val_kin)
                    
                    # 2. Potential Frozen (Current T)
                    val_pot = round(float(mech_t.pot_density.iloc[-1]), 2)
                    f_pot.append(val_pot)
                    
                    # 3. [NEW] Frozen Sum Index (Sum of Current Kin & Current Pot)
                    # We use Current Kin (iloc[-1]) for this index, not the shifted one
                    curr_kin_raw = float(mech_t.kin_density.iloc[-1])
                    curr_pot_raw = float(mech_t.pot_density.iloc[-1])
                    val_sum = curr_kin_raw + curr_pot_raw
                    f_sum.append(val_sum)
                    
                    f_dates.append(px.index[t].strftime('%Y-%m-%d'))
                except:
                    continue
            
            # [NEW] Normalize Frozen Sum Index (Rolling Z-Score 252)
            f_sum_series = pd.Series(f_sum)
            roll_fsum_mean = f_sum_series.rolling(window=252, min_periods=20).mean()
            roll_fsum_std = f_sum_series.rolling(window=252, min_periods=20).std()
            z_frozen_sum = ((f_sum_series - roll_fsum_mean) / (roll_fsum_std + 1e-6)).fillna(0).tolist()
            
            # [NEW] Apply Zero-Phase Low-Pass Filter (Butterworth)
            # This smooths the signal without introducing lag
            try:
                # Filter parameters: order=2, cutoff=0.05 (normalized frequency)
                # Lower cutoff = more smoothing. Range [0.01, 0.1] typical.
                b, a = butter(N=2, Wn=0.05, btype='low')
                z_frozen_sum_filtered = filtfilt(b, a, z_frozen_sum).tolist()
                z_frozen_sum = z_frozen_sum_filtered
            except Exception as e:
                print(f"⚠️ Filter failed (keeping raw): {e}")
            
            # Round for JSON
            z_frozen_sum = [round(x, 2) for x in z_frozen_sum]
            
            full_frozen_data = {
                "dates": f_dates,
                "kin": f_kin,
                "pot": f_pot,
                "z_sum": z_frozen_sum
            }
            
            # Salva tutto in cache
            TICKER_CACHE[req.ticker] = {
                "px": px,
                "frozen": full_frozen_data,
                "zigzag": zigzag_series,
                "volume": volume_series,
                "mkt_cap": mkt_cap
            }

        # --- SIMULATION TIME TRAVEL (Slicing istantaneo) ---
        if req.end_date:
            end_ts = pd.Timestamp(req.end_date)
            # Slice Prices
            px = px[px.index <= end_ts]
            
            # Slice Frozen Data
            # Troviamo l'indice fin dove arrivare nei dati frozen
            target_date_str = req.end_date
            
            # Slice ZigZag (Series)
            if zigzag_series is not None:
                zigzag_series = zigzag_series[zigzag_series.index <= end_ts]
                
            # Slice Volume
            if volume_series is not None:
                volume_series = volume_series[volume_series.index <= end_ts]
            
            # Filtro rapido liste (date frozen sono già sorted)
            trunc_dates = []
            trunc_kin = []
            trunc_dates = []
            trunc_kin = []
            trunc_pot = []
            trunc_z_sum = []
            
            # Ottimizzazione: bisect o semplice loop finché <= date
            # Dato che sono stringhe YYYY-MM-DD, confronto lessicografico funziona
            for i, d in enumerate(full_frozen_data["dates"]):
                if d <= target_date_str:
                    trunc_dates.append(d)
                    trunc_kin.append(full_frozen_data["kin"][i])
                    trunc_pot.append(full_frozen_data["pot"][i])
                    trunc_z_sum.append(full_frozen_data["z_sum"][i])
                else:
                    break # Stop appena superiamo la data
            
            frozen_dates = trunc_dates
            frozen_z_kin = trunc_kin
            frozen_z_pot = trunc_pot
            frozen_z_sum = trunc_z_sum
            
            print(f"🕐 Simulating past: data truncated to {req.end_date}")
        else:
            # Dati completi
            frozen_dates = full_frozen_data["dates"]
            frozen_z_kin = full_frozen_data["kin"]
            frozen_z_pot = full_frozen_data["pot"]
            frozen_z_sum = full_frozen_data["z_sum"]
        
        # Prepare ZigZag List
        zigzag_line = zigzag_series.values.tolist() if zigzag_series is not None else []
        
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
            z_slope=z_slope_series,       # Non usato (use_z_roc=True)
            dates=dates_historical,
            start_date=req.start_date,
            end_date=req.end_date,
            use_z_roc=True  # Direzione basata su Z-ROC (causale)
        )
        
        # --- STRATEGIA 3: FROZEN SUM (Nuovo Indicatore Filtrato) ---
        # Allineiamo frozen_z_sum (già filtrato con Butterworth) alla lunghezza di price_real
        padding_sum = len(price_real) - len(frozen_z_sum)
        aligned_frozen_sum = [-999] * padding_sum + frozen_z_sum  # -999 = no data, prevents false entry
        
        backtest_result_frozen_sum = backtest_strategy(
            prices=price_real,
            z_kinetic=aligned_frozen_sum,  # Segnale: Frozen Sum Z (Filtrato)
            z_slope=z_slope_series,        # Non usato (use_z_roc=True)
            dates=dates_historical,
            start_date=req.start_date,
            end_date=req.end_date,
            threshold=-0.3,  # Entry/Exit a -0.3 invece di 0
            use_z_roc=True   # Direzione basata su Z-ROC (causale)
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
        
        # Market Cap already loaded from cache or calculated above
        # (Legacy block removed)
        
        return {
            "status": "ok",
            "ticker": req.ticker,
            "avg_abs_kin": round(float(avg_abs_kin), 2),
            "market_cap": mkt_cap,
            "dates": dates_historical,
            "prices": price_real,
            "dates": dates_historical,
            "prices": price_real,
            "volume": volume_series.reindex(px.index).fillna(0).tolist(),
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
                "z_roc": z_roc_line,
                "zigzag": zigzag_line   # [NEW] Cumulative Direction
            },
            "backtest": backtest_result,                  # Strategia Live
            "frozen_strategy": backtest_result_frozen,    # Strategia Frozen Pot
            "frozen_sum_strategy": backtest_result_frozen_sum,  # [NEW] Frozen Sum
            "forecast": {
                "dates": dates_future,
                "values": future_scenario
            },
            "fourier_components": fourier_comps,
            "frozen": {
                "dates": frozen_dates,
                "z_kinetic": frozen_z_kin,
                "dates": frozen_dates,
                "z_kinetic": frozen_z_kin,
                "z_potential": frozen_z_pot,
                "z_sum": frozen_z_sum
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

# --- TRADE INTEGRITY VERIFICATION ---
class VerifyIntegrityRequest(BaseModel):
    ticker: str
    strategy: str = "FROZEN"  # LIVE, FROZEN, or SUM
    alpha: float = 200.0
    beta: float = 1.0
    start_date: Optional[str] = None
    end_date: Optional[str] = None

@app.post("/verify-integrity")
async def verify_trade_integrity(req: VerifyIntegrityRequest):
    """
    Verifica l'integrità dei trade simulando il tempo dal passato al presente.
    Rileva quando i trade cambiano retroattivamente (look-ahead bias).
    """
    try:
        from logic import backtest_strategy
        from datetime import datetime, timedelta
        
        print(f"🔍 Verifica integrità per {req.ticker} - Strategia: {req.strategy}")
        
        # Get full cached data
        if req.ticker not in TICKER_CACHE:
            md = MarketData(req.ticker)
            px = md.get_price()
            TICKER_CACHE[req.ticker] = px
        
        full_px = TICKER_CACHE[req.ticker].copy()
        
        # Determine date range
        all_dates = full_px.index.tolist()
        start_idx = 252 * 2  # Start after 2 years of data for Z-Score
        step_every = 5  # Check every 5 days to speed up
        
        # Track trades across time
        trade_history = {}  # entry_date -> {first_seen_data, changes: []}
        corrupted_trades = []
        
        for end_idx in range(start_idx, len(all_dates), step_every):
            end_date = all_dates[end_idx].strftime('%Y-%m-%d')
            
            # Simulate analysis at this point in time
            truncated_px = full_px.iloc[:end_idx+1]
            
            # Calculate path and Z-scores
            path = ActionPath(alpha=req.alpha, beta=req.beta)
            path.calculate(truncated_px)
            
            kinetic = path.kinetic_density
            potential = path.potential_density
            
            # Calculate Z-scores
            z_kin_series = (kinetic - kinetic.rolling(252).mean()) / kinetic.rolling(252).std()
            z_pot_series = (potential - potential.rolling(252).mean()) / potential.rolling(252).std()
            z_slope_series = z_kin_series.diff(5) / 5
            
            dates_historical = [d.strftime('%Y-%m-%d') for d in truncated_px.index]
            price_real = truncated_px.tolist()
            
            # Run backtest based on strategy
            if req.strategy == "LIVE":
                z_signal = z_kin_series.tolist()
                threshold = 0.0
                use_z_roc = False
            elif req.strategy == "FROZEN":
                z_signal = z_pot_series.tolist()
                threshold = 0.0
                use_z_roc = True
            else:  # SUM
                # Simplified SUM calculation
                z_sum = (z_kin_series + z_pot_series).tolist()
                z_signal = z_sum
                threshold = -0.3
                use_z_roc = True
            
            backtest_result = backtest_strategy(
                prices=price_real,
                z_kinetic=z_signal,
                z_slope=z_slope_series.tolist(),
                dates=dates_historical,
                threshold=threshold,
                use_z_roc=use_z_roc
            )
            
            current_trades = backtest_result['trades']
            
            # Compare with previously seen trades
            for trade in current_trades:
                entry_date = trade['entry_date']
                
                if entry_date not in trade_history:
                    # First time seeing this trade - store it
                    trade_history[entry_date] = {
                        'first_seen': trade.copy(),
                        'first_seen_at': end_date,
                        'changes': []
                    }
                else:
                    # Already seen - check for changes
                    original = trade_history[entry_date]['first_seen']
                    changes = []
                    
                    if original['direction'] != trade['direction']:
                        changes.append(f"Dir: {original['direction']}→{trade['direction']}")
                    
                    # Only flag exit_date change if original was not OPEN
                    if original['exit_date'] != trade['exit_date'] and original['exit_date'] != 'OPEN':
                        changes.append(f"Exit: {original['exit_date']}→{trade['exit_date']}")
                    
                    if abs(original['entry_price'] - trade['entry_price']) > 0.01:
                        changes.append(f"Price: {original['entry_price']}→{trade['entry_price']}")
                    
                    if changes:
                        trade_history[entry_date]['changes'].extend(changes)
        
        # Collect corrupted trades
        for entry_date, data in trade_history.items():
            if data['changes']:
                corrupted_trades.append({
                    'entry_date': entry_date,
                    'original': data['first_seen'],
                    'first_seen_at': data['first_seen_at'],
                    'changes': list(set(data['changes']))  # Unique changes
                })
        
        # Sort by entry date
        corrupted_trades.sort(key=lambda x: x['entry_date'], reverse=True)
        
        print(f"✅ Verifica completata: {len(corrupted_trades)} trade corrotti trovati")
        
        return {
            "status": "ok",
            "ticker": req.ticker,
            "strategy": req.strategy,
            "total_trades": len(trade_history),
            "corrupted_count": len(corrupted_trades),
            "corrupted_trades": corrupted_trades
        }
        
    except Exception as e:
        import traceback
        print(f"❌ Errore verifica integrità: {e}")
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}

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
