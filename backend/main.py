import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
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
import json
import uuid
from datetime import datetime, timezone
import yfinance as yf

# Ensure the directory containing this file is in the Python path
# This fixes "ModuleNotFoundError: No module named 'logic'" on Railway
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from logic import MarketData, ActionPath, FourierEngine, MarketScanner

app = FastAPI(title="Financial Physics API")

# --- SCHEDULER ---
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler(timezone="Europe/Rome")

def scheduled_scan_job():
    """Runs daily at 18:30 Rome time."""
    import sys
    import traceback
    print("⏰ Scheduled scan triggered!", flush=True)
    try:
        from scanner import run_market_scan
        print("🚀 Starting run_market_scan...", flush=True)
        run_market_scan(send_email=True)
        print("✅ run_market_scan completed.", flush=True)
    except Exception as e:
        print(f"❌ ERROR in scheduled_scan_job: {e}", flush=True)
        traceback.print_exc()
        sys.stdout.flush()

# Schedule: Every day at 16:30 Rome time
scheduler.add_job(
    scheduled_scan_job,
    CronTrigger(hour=16, minute=30, timezone="Europe/Rome"),
    id="daily_scan",
    replace_existing=True
)

@app.get("/debug-time")
def debug_time():
    """Returns server time info for debugging scheduler."""
    now_utc = datetime.now(timezone.utc)
    try:
        import pytz
        rome = pytz.timezone("Europe/Rome")
        now_rome = datetime.now(rome)
        return {
            "utc_time": now_utc.isoformat(),
            "rome_time": now_rome.isoformat(),
            "server_local_time": datetime.now().isoformat(),
            "scheduler_timezone": str(scheduler.timezone)
        }
    except Exception as e:
        return {"error": str(e), "utc_time": now_utc.isoformat()}

@app.get("/scheduler-status")
def scheduler_status():
    """Returns detailed APScheduler status for debugging."""
    import pytz
    rome = pytz.timezone("Europe/Rome")
    now_rome = datetime.now(rome)
    
    jobs_info = []
    for job in scheduler.get_jobs():
        jobs_info.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": str(job.next_run_time) if job.next_run_time else "NOT SCHEDULED",
            "trigger": str(job.trigger)
        })
    
    return {
        "scheduler_running": scheduler.running,
        "scheduler_state": str(scheduler.state),
        "current_rome_time": now_rome.isoformat(),
        "timezone": str(scheduler.timezone),
        "jobs": jobs_info
    }

@app.on_event("startup")
def start_scheduler():
    scheduler.start()
    # Log scheduler state after start
    jobs = scheduler.get_jobs()
    print(f"🕡 Scheduler attivato. Running: {scheduler.running}. Jobs: {len(jobs)}", flush=True)
    for job in jobs:
        print(f"   Job '{job.id}': next run at {job.next_run_time}", flush=True)

@app.on_event("shutdown")
def shutdown_scheduler():
    scheduler.shutdown()

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
def analyze_stock(req: AnalysisRequest):
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
            
            # CRITICAL FIX: Ensure 'frozen' data exists (avoid crash after verify integrity invalidation)
            if use_cache_data and cached_obj.get("frozen") is None:
                print(f"⚠️ Cache partial miss (Dati Frozen mancanti). Ricalcolo...")
                use_cache_data = False

            # [NEW] Check for STALE DATA (if older than 2 days)
            if use_cache_data:
                last_dt = cached_px.index[-1]
                now_dt = datetime.now()
                # Consider weekend gaps (e.g. 4 days max tolerance if holiday?). 
                # If market is active, > 1 day is stale. 
                # Let's say > 3 days is definitely stale even with weekend.
                delta_days = (now_dt - last_dt).days
                if delta_days > 3:
                     print(f"⚠️ Cache Stale (Old): Last={last_dt.date()} Now={now_dt.date()} Delta={delta_days}d. Ricarico...")
                     use_cache_data = False


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
                        "z_sum": full_frozen_data.get("z_sum", [])[idx_start:],
                        "z_slope": full_frozen_data.get("z_slope", [])[idx_start:],
                        "raw_sum": full_frozen_data.get("raw_sum", [])[idx_start:],
                        "raw_slope": full_frozen_data.get("raw_slope", [])[idx_start:]
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
            
            # 2. Fourier Calculation
            fourier = FourierEngine(px, top_k=req.top_k)
            future_idx, future_vals = fourier.reconstruct_scenario(future_horizon=req.forecast_days)
            
            # 3. Calcola Minima Azione (STANDARD - slope goes to 0)
            # User requested to keep standard slope "as is" (0 at end)
            mechanics = ActionPath(px, alpha=req.alpha, beta=req.beta)
            
            # --- PRE-CALCOLO FROZEN HISTORY (Heavy Computation) ---
            print(f"🧊 Pre-calcolo Frozen History completa (può richiedere tempo)...")
            # Increase sampling step to avoid slowness due to repeated Fourier
            SAMPLE_EVERY = 2 
            MIN_POINTS = 100
            
            f_kin, f_pot, f_sum, f_slope, f_dates = [], [], [], [], []
            n_total = len(px)
            
            for t in range(MIN_POINTS, n_total, SAMPLE_EVERY):
                px_t = px.iloc[:t+1]
                try:
                    # A. Standard Frozen Metrics
                    mech_t = ActionPath(px_t, alpha=req.alpha, beta=req.beta)
                    
                    # 1. Kinetic Frozen (Shifted T-25)
                    lag_idx = -25
                    if len(mech_t.kin_density) >= 25:
                        val_kin = round(float(mech_t.kin_density.iloc[lag_idx]), 2)
                    else:
                        val_kin = 0.0
                    f_kin.append(val_kin)
                    
                    # 2. Potential Frozen (Current T)
                    val_pot = round(float(mech_t.pot_density.iloc[-1]), 2)
                    f_pot.append(val_pot)
                    
                    # 3. Frozen Sum (Current T)
                    curr_kin_raw = float(mech_t.kin_density.iloc[-1])
                    curr_pot_raw = float(mech_t.pot_density.iloc[-1])
                    val_sum = curr_kin_raw + curr_pot_raw
                    f_sum.append(val_sum)
                    
                    # B. [NEW] PREDICTIVE SLOPE (Ghost Future at time T)
                    # We must simulate what the slope WOULD be if we extended into the future known at time T
                    
                    # 1. Fourier on px_t
                    four_t = FourierEngine(px_t, top_k=req.top_k)
                    # We only need short horizon for ghost
                    _, fut_vals_t = four_t.reconstruct_scenario(future_horizon=14)
                    
                    # 2. Extend px_t
                    ghost_series_t = pd.Series(fut_vals_t, index=pd.date_range(px_t.index[-1], periods=15)[1:])
                    px_t_extended = pd.concat([px_t, ghost_series_t])
                    
                    # 3. ActionPath on Extended
                    mech_t_ext = ActionPath(px_t_extended, alpha=req.alpha, beta=req.beta)
                    
                    # 4. Capture Slope at time T (which is at index len(px_t)-1)
                    # The slope is now "unlocked" by the ghost future
                    val_slope = float(mech_t_ext.dX.iloc[len(px_t)-1])
                    f_slope.append(round(val_slope, 4))
                    
                    f_dates.append(px.index[t].strftime('%Y-%m-%d'))
                except Exception as e:
                    # print(f"Err frozen loop: {e}")
                    continue
            
            # [NEW] Normalize Frozen Slope (Rolling Z-Score)
            # Raw slope is hard to read. Z-Score makes it an oscillator.
            f_slope_series = pd.Series(f_slope)
            roll_fslope_mean = f_slope_series.rolling(window=252, min_periods=20).mean()
            roll_fslope_std = f_slope_series.rolling(window=252, min_periods=20).std()
            
            # Z-Score
            z_frozen_slope = ((f_slope_series - roll_fslope_mean) / (roll_fslope_std + 1e-6)).fillna(0).tolist()
            z_frozen_slope = [round(x, 2) for x in z_frozen_slope]

                
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
                "z_sum": z_frozen_sum,
                "z_slope": z_frozen_slope,
                "raw_sum": f_sum,
                "raw_slope": f_slope # [NEW] Save raw slope for strict re-simulation
            }
            
            # Salva tutto in cache
            TICKER_CACHE[req.ticker] = {
                "px": px,
                "frozen": full_frozen_data,
                "zigzag": zigzag_series,
                "volume": volume_series,
                "mkt_cap": mkt_cap
            }

        # --- SIMULATION TIME TRAVEL (True Point-in-Time Calculation) ---
        if req.end_date:
            end_ts = pd.Timestamp(req.end_date)
            # Slice Prices
            px = px[px.index <= end_ts]
            
            # Slice ZigZag (Series)
            if zigzag_series is not None:
                zigzag_series = zigzag_series[zigzag_series.index <= end_ts]
                
            # Slice Volume
            if volume_series is not None:
                volume_series = volume_series[volume_series.index <= end_ts]
            
            # Slice Frozen Data
            # To avoid look-ahead bias from the filter, we must:
            # 1. Slice the RAW SUM to the target date
            # 2. Re-apply Rolling Z-Score and Filter on the truncated series
            
            trunc_dates = []
            trunc_kin = []
            trunc_pot = []
            trunc_z_sum = []
            trunc_z_slope = []
            
            if full_frozen_data and "raw_sum" in full_frozen_data:
                full_dates = full_frozen_data["dates"]
                full_raw_sum = full_frozen_data["raw_sum"]
                # Fallback for old cache (though we should have invalidated)
                full_raw_slope = full_frozen_data.get("raw_slope", []) 
                
                # Find cut-off index
                from bisect import bisect_right
                # full_dates is sorted list of strings YYYY-MM-DD
                cut_idx = bisect_right(full_dates, req.end_date)
                
                if cut_idx > 0:
                    trunc_dates = full_frozen_data["dates"][:cut_idx]
                    trunc_kin = full_frozen_data["kin"][:cut_idx]
                    trunc_pot = full_frozen_data["pot"][:cut_idx]
                    
                    # --- Recalculate SUM Indicator ---
                    trunc_raw = full_raw_sum[:cut_idx]
                    s_trunc = pd.Series(trunc_raw)
                    roll_mean = s_trunc.rolling(window=252, min_periods=20).mean()
                    roll_std = s_trunc.rolling(window=252, min_periods=20).std()
                    z_trunc = ((s_trunc - roll_mean) / (roll_std + 1e-6)).fillna(0).tolist()
                    
                    # Filter (Butterworth)
                    try:
                        from scipy.signal import butter, filtfilt
                        b, a = butter(N=2, Wn=0.05, btype='low')
                        if len(z_trunc) > 15:
                            trunc_z_sum = filtfilt(b, a, z_trunc).tolist()
                        else:
                            trunc_z_sum = z_trunc
                    except:
                        trunc_z_sum = z_trunc
                    # Rounding
                    trunc_z_sum = [round(x, 2) for x in trunc_z_sum]
                    
                    # --- Recalculate SLOPE Indicator ---
                    if full_raw_slope:
                         trunc_raw_slope = full_raw_slope[:cut_idx]
                         s_slope = pd.Series(trunc_raw_slope)
                         roll_mean = s_slope.rolling(window=252, min_periods=20).mean()
                         roll_std = s_slope.rolling(window=252, min_periods=20).std()
                         trunc_z_slope_val = ((s_slope - roll_mean) / (roll_std + 1e-6)).fillna(0).tolist()
                         trunc_z_slope = [round(x, 2) for x in trunc_z_slope_val]
                    else:
                         # Fallback if raw slope missing 
                         if "z_slope" in full_frozen_data:
                             trunc_z_slope = full_frozen_data["z_slope"][:cut_idx]
                         else:
                             trunc_z_slope = []
                else:
                    # No data before date
                    pass
            else:
                # Fallback to old simple slicing if raw_sum missing (legacy cache)
                # But we should have invalidated cache earlier
                target_date_str = req.end_date
                for i, d in enumerate(full_frozen_data["dates"]):
                    if d <= target_date_str:
                        trunc_dates.append(d)
                        trunc_kin.append(full_frozen_data["kin"][i])
                        trunc_pot.append(full_frozen_data["pot"][i])
                        trunc_z_sum.append(full_frozen_data["z_sum"][i])
                        if "z_slope" in full_frozen_data and i < len(full_frozen_data["z_slope"]):
                            trunc_z_slope.append(full_frozen_data["z_slope"][i])
                    else:
                        break # Stop appena superiamo la data
            
            # Override response content
            full_frozen_data = {
                "dates": trunc_dates,
                "kin": trunc_kin,
                "pot": trunc_pot,
                "z_sum": trunc_z_sum,
                "z_slope": trunc_z_slope,
                "raw_sum": [],
                "raw_slope": []
            }
            
            frozen_dates = trunc_dates
            frozen_z_kin = trunc_kin
            frozen_z_pot = trunc_pot
            frozen_z_sum = trunc_z_sum
            # Slope is handled in frontend via full_frozen_data["z_slope"] since it's an overlay trace
            
            print(f"🕐 Simulating past: data truncated to {req.end_date}")
        else:
            # Dati completi
            frozen_dates = full_frozen_data["dates"]
            frozen_z_kin = full_frozen_data["kin"]
            frozen_z_pot = full_frozen_data["pot"]
            frozen_z_sum = full_frozen_data["z_sum"]
        
        # Prepare ZigZag List
        zigzag_line = zigzag_series.values.tolist() if zigzag_series is not None else []
        
        # --- LIVE CALCULATIONS (Run on potentially time-sliced data) ---
        # These MUST run AFTER time travel slicing and are needed for API response
        
        # Calcola Minima Azione (LIVE - on current px, possibly sliced)
        mechanics = ActionPath(px, alpha=req.alpha, beta=req.beta)
        
        # Fourier Calculation (LIVE)
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
        
        # --- STRATEGIA 4: MIN ACTION (TREND FOLLOWING) [NEW] ---
        # Usa la curva di minima azione (price_min_action / px_star) come trend follower.
        # TIMING: Triggered by Frozen Sum Z > -0.3 (Hybrid Mode)
        # DIRECTION: Price vs Curve
        
        backtest_result_ma = backtest_strategy(
            prices=price_real,
            z_kinetic=aligned_frozen_sum, # Trigger signal (same as SUM)
            z_slope=[],   # Ignorato
            dates=dates_historical,
            start_date=req.start_date,
            end_date=req.end_date,
            threshold=-0.3, # Trigger Threshold (same as SUM)
            trend_mode='PRICE_VS_CURVE',
            trend_curve=price_min_action 
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
            "frozen_min_action_strategy": backtest_result_ma,   # [NEW] Min Action Trend
            "forecast": {
                "dates": dates_future,
                "values": future_scenario
            },
            "fourier_components": fourier_comps,
            "frozen_data": {
                "dates": frozen_dates,
                "z_kinetic": frozen_z_kin,
                "z_potential": frozen_z_pot,
                "z_sum": frozen_z_sum,
                "z_slope": full_frozen_data.get("z_slope", [])  # [NEW] Predictive Slope
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
        
        # Get full cached data or fetch if missing/insufficient
        force_reload = False
        if req.ticker in TICKER_CACHE:
            cached_obj = TICKER_CACHE[req.ticker]
            if isinstance(cached_obj, dict):
                measure_px = cached_obj["px"]
            else:
                measure_px = cached_obj
            
            # Check sufficiency (need > 504 for loop to start + margin)
            if len(measure_px) < 550:
                print(f"⚠️ Dati in cache insufficienti per verifica ({len(measure_px)} pti). Ricarico...")
                force_reload = True
        
        if req.ticker not in TICKER_CACHE or force_reload:
            # Scarica almeno 5 anni per avere margine ampio
            start_date_long = (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d')
            md = MarketData(req.ticker, start_date=start_date_long)
            px = md.fetch()
            # Initialize cache with dictionary structure matching main logic
            TICKER_CACHE[req.ticker] = {"px": px}
        
        cached_obj = TICKER_CACHE[req.ticker]
        if isinstance(cached_obj, dict):
            full_px = cached_obj["px"].copy()
        else:
            # Fallback if somehow it's just the Series (legacy)
            full_px = cached_obj.copy()

        # [FIX] Load full_frozen_data for FROZEN/SUM strategies
        frozen_cache_key = f"{req.ticker}_frozen"
        full_frozen_data = TICKER_CACHE.get(frozen_cache_key) # Can be None if not analyzed yet
        full_frozen_dates = full_frozen_data["dates"] if full_frozen_data else []
        full_raw_sum = full_frozen_data["raw_sum"] if (full_frozen_data and "raw_sum" in full_frozen_data) else []
        
        # Determine date range
        all_dates = full_px.index.tolist()
        start_idx = 252 * 2  # Start after 2 years of data for Z-Score
        step_every = 1  # Check EVERY day for maximum precision
        
        # Track trades across time
        trade_history = {}  # entry_date -> {first_seen_data, changes: [], disappeared: False}
        corrupted_trades = []
        
        print(f"⏳ Inizio simulazione integrità ({len(all_dates) - start_idx} passi)...")
        
        for end_idx in range(start_idx, len(all_dates), step_every):
            end_date_obj = all_dates[end_idx]
            end_date_str = end_date_obj.strftime('%Y-%m-%d')
            
            # Simulate analysis at this point in time
            truncated_px = full_px.iloc[:end_idx+1]
            dates_historical = [d.strftime('%Y-%m-%d') for d in truncated_px.index]
            price_real = truncated_px.tolist()
            
            # Run backtest based on strategy
            if req.strategy == "LIVE":
                # Recalculate dynamic path (Live is always fresh)
                path = ActionPath(truncated_px, alpha=req.alpha, beta=req.beta)
                kinetic = path.kin_density
                
                # Calculate Z-scores
                z_kin_series = (kinetic - kinetic.rolling(252).mean()) / kinetic.rolling(252).std()
                z_signal = z_kin_series.tolist()
                threshold = 0.0
                use_z_roc = False
                
            elif req.strategy == "FROZEN":
                # [FIXED LOGIC] Use Frozen Point-in-Time Data
                # Retrieve from separate cache key loaded at start
                
                # Check if we have frozen data
                if full_frozen_data and "pot" in full_frozen_data:
                    # We have pre-calculated point-in-time data
                    
                    # Find subset of data available at time 'end_date_str'
                    # It includes all points with date <= end_date_str
                    
                    end_date_str = end_date_obj.strftime('%Y-%m-%d')

                    
                    # Find index in frozen list corresponding to end_date_str
                    # Optimized: Since we iterate step_every=1, we can track index. But binary search is safer.
                    # Dates are sorted strings YYYY-MM-DD
                    
                    # Find subset of raw_sum available at time 'end_date_str'
                    # It includes all points with date <= end_date_str
                    
                    # Optim: bisect_right for strings works
                    from bisect import bisect_right
                    cut_idx = bisect_right(full_frozen_dates, end_date_str)
                    
                    if cut_idx == 0:
                        # No frozen data available yet at this time
                        z_signal = []
                    else:
                        # [FIX] FROZEN strategy uses POTENTIAL (not Sum), and aligns BEFORE Z-Score
                        # This matches analyze_stock logic for the "Frozen" tab (Strategy 2)
                        trunc_pot_raw = full_frozen_data["pot"][:cut_idx]
                        trunc_dates = full_frozen_dates[:cut_idx]
                        
                        # ALIGNMENT First (Raw Pot to Truncated Prices)
                        # Create Series map: Date(str) -> Raw Value
                        pot_map = pd.Series(trunc_pot_raw, index=trunc_dates)
                        target_keys = [d.strftime('%Y-%m-%d') for d in truncated_px.index]
                        
                        # Reindex fills with 0 (assuming Pot=0 for missing data)
                        aligned_pot = pot_map.reindex(target_keys).fillna(0)
                        
                        # Apply Rolling Z-Score ON ALIGNED DATA (Matches analyze_stock)
                        roll_mean = aligned_pot.rolling(window=252, min_periods=20).mean()
                        roll_std = aligned_pot.rolling(window=252, min_periods=20).std()
                        # Use z_signal directly from potential z-score
                        z_signal = ((aligned_pot - roll_mean) / (roll_std + 1e-6)).fillna(0).tolist()

                else:
                    # Fallback if cache missing
                    z_signal = []
                
                threshold = 0.0
                use_z_roc = True
                
                
            else:  # SUM
                # SUM Strategy typically uses the same underlying Frozen Sum Z signal in the frontend
                # So we reuse the logic but with correct variables
                 
                if full_frozen_data and "raw_sum" in full_frozen_data:
                    full_raw_sum = full_frozen_data["raw_sum"]
                    # full_frozen_dates is already loaded at top scope (line 629)
                    
                    from bisect import bisect_right
                    cut_idx = bisect_right(full_frozen_dates, end_date_str)
                    
                    if cut_idx == 0:
                        z_signal = []
                    else:
                        trunc_raw_sum = full_raw_sum[:cut_idx]
                        trunc_dates = full_frozen_dates[:cut_idx]
                        s_sum = pd.Series(trunc_raw_sum)
                        roll_mean = s_sum.rolling(window=252, min_periods=20).mean()
                        roll_std = s_sum.rolling(window=252, min_periods=20).std()
                        z_frozen_raw = ((s_sum - roll_mean) / (roll_std + 1e-6)).fillna(0).tolist()
                        
                        try:
                            from scipy.signal import butter, filtfilt
                            # Match parameter from analyze_stock? Checking Wn. 
                            # If analyze uses 0.1, we should use 0.1. Typically I used 0.1 in previous steps.
                            # Let's standardize to 0.1 matching verify output findings if recent view_file confirmed. 
                            # However recent view_file showed 0.05 in verify but didn't show analyze definition.
                            # I will assume 0.05 as it was in verify, but to be safer I stick to what was there unless confirmed.
                            # BUT, wait, I saw analyze_stock line 498 threshold=-0.3.
                            # I'll stick to 0.05 to avoid changing signal logic blindly, but ensure robustness.
                            b, a = butter(N=2, Wn=0.05, btype='low') 
                            
                            if len(z_frozen_raw) > 15:
                                z_frozen_sum_filtered = filtfilt(b, a, z_frozen_raw).tolist()
                                z_signal_short = z_frozen_sum_filtered
                            else:
                                z_signal_short = z_frozen_raw
                        except:
                             z_signal_short = z_frozen_raw
                             
                        # [CRITICAL] ALIGNMENT & PADDING for SUM
                        # Align by Date Map first
                        z_series_map = pd.Series(z_signal_short, index=trunc_dates)
                        target_keys = [d.strftime('%Y-%m-%d') for d in truncated_px.index]
                        
                        # Reindex fills missing dates with 0 (or previous? No, signal is discrete)
                        z_signal = z_series_map.reindex(target_keys).fillna(0).tolist()
                        
                else:
                    z_signal = []

            threshold = -0.3
            use_z_roc = True
            
            # Common backtest call
            if not z_signal:
                 continue # Skip if no signal generated yet
            
            # Calculate slope consistently for all strategies
            # Z-ROC requires slope of the signal being traded
            z_signal_series = pd.Series(z_signal)
            z_slope_series = z_signal_series.diff(5) / 5
            z_slope_list = z_slope_series.fillna(0).tolist()

            backtest_result = backtest_strategy(
                prices=price_real,
                z_kinetic=z_signal,
                z_slope=z_slope_list,
                dates=dates_historical,
                threshold=threshold,
                use_z_roc=use_z_roc
            )
            
            skipped_trades_current = backtest_result.get('skipped_trades', []) 
            current_trades = backtest_result['trades']
            current_trade_dates = set()
            skipped_trade_dates = {t['date'] for t in skipped_trades_current} # Exact match
            skipped_trade_indices = {t['index'] for t in skipped_trades_current if 'index' in t} # Index match
            
            # Map date string to index for fuzzy matching
            date_to_idx = {d: i for i, d in enumerate(dates_historical)}

            # Compare with previously seen trades
            for trade in current_trades:
                entry_date = trade['entry_date']
                current_trade_dates.add(entry_date)
                
                if entry_date not in trade_history:
                    # First time seeing this trade - store it
                    trade_history[entry_date] = {
                        'first_seen': trade.copy(),
                        'first_seen_at': end_date_str,
                        'changes': [],
                        'disappeared': False
                    }
                else:
                    # Already seen - check for changes
                    record = trade_history[entry_date]
                    original = record['first_seen']
                    changes = []
                    
                    if original['direction'] != trade['direction']:
                        changes.append(f"Dir: {original['direction']}→{trade['direction']}")
                    
                    # Only flag exit_date change if original was not OPEN
                    # OPEN -> Date is normal closure. Date -> Date is retroactive change.
                    if original['exit_date'] != trade['exit_date'] and original['exit_date'] != 'OPEN':
                        changes.append(f"Exit: {original['exit_date']}→{trade['exit_date']}")
                    
                    if abs(original['entry_price'] - trade['entry_price']) > 0.01:
                        changes.append(f"Price: {original['entry_price']}→{trade['entry_price']}")

                    if changes:
                        # Append unique changes only
                        for c in changes:
                            if c not in record['changes']:
                                record['changes'].append(c)
            
            # CHECK FOR DISAPPEARED TRADES
            # Rules: Trade exists in history, is NOT in current_trades, and its entry_date is <= current sim date
            for hist_entry_date, record in trade_history.items():
                if hist_entry_date not in current_trade_dates:
                    # Trade is missing from current simulation
                    # Ensure we are simulating a time AFTER the trade should have started
                    if hist_entry_date <= end_date_str:
                         
                         # [NEW LOGIC] Check if it was skipped due to position already open
                         # If it matches exact or fuzzy, it means the SIGNAL IS VALID but blocked.
                         # In this case, we treat it as "Not Disappeared" (Hide it from error list).
                         is_blocked = False
                         
                         # 1. Exact Match
                         if hist_entry_date in skipped_trade_dates:
                             is_blocked = True
                         
                         # 2. Fuzzy Match
                         elif hist_entry_date in date_to_idx and skipped_trade_indices:
                             hist_idx = date_to_idx[hist_entry_date]
                             for offset in range(-3, 4):
                                 if (hist_idx + offset) in skipped_trade_indices:
                                     is_blocked = True
                                     break
                         
                         if is_blocked:
                             # It's a valid signal blocked by position. 
                             # User doesn't want to see "Ghosts". So we consider it NOT disappeared.
                             # If it was previously marked disappeared, clear it.
                             record['disappeared'] = False
                             if "❌ DISSOLTO" in record['changes']:
                                 record['changes'].remove("❌ DISSOLTO")
                             if "⚠️ BLOCCATO (Slittato)" in record['changes']:
                                 record['changes'].remove("⚠️ BLOCCATO (Slittato)")
                             if "⚠️ BLOCCATO (POS. APERTA)" in record['changes']:
                                 record['changes'].remove("⚠️ BLOCCATO (POS. APERTA)")
                         
                         else:
                             # It is NOT blocked, so the signal must be gone.
                             if not record['disappeared']:
                                 record['disappeared'] = True
                                 if "❌ DISSOLTO" not in record['changes']:
                                     record['changes'].append("❌ DISSOLTO")
                                     
                else:
                    # Trade is PRESENT in current simulation
                    # Check if it was previously marked as disappeared (Resurrection)
                    if record['disappeared']:
                        record['disappeared'] = False
                        
                        # Remove negative flags if it reappears
                        if "❌ DISSOLTO" in record['changes']:
                            record['changes'].remove("❌ DISSOLTO")
                        if "⚠️ BLOCCATO (POS. APERTA)" in record['changes']:
                            record['changes'].remove("⚠️ BLOCCATO (POS. APERTA)")
                        if "⚠️ BLOCCATO (Slittato)" in record['changes']:
                            record['changes'].remove("⚠️ BLOCCATO (Slittato)")
                            
                        # Mark as Unstable/Flickering instead
                        if "⚠️ INSTABILE" not in record['changes']:
                            record['changes'].append("⚠️ INSTABILE")

        # Collect corrupted trades
        for entry_date, data in trade_history.items():
            if data['changes']:
                corrupted_trades.append({
                    'entry_date': entry_date,
                    'original': data['first_seen'],
                    'first_seen_at': data['first_seen_at'],
                    'changes': list(set(data['changes']))
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


class DailyScanRequest(BaseModel):
    tickers: list[str] = []
    as_of_date: str | None = None  # Optional: simulate this date as "today"

@app.post("/scan-daily")
def scan_daily_signals(req: DailyScanRequest):
    """
    Scans a list of tickers for actionable signals (BUY/SELL) for the CURRENT day.
    Checks both FROZEN and SUM strategies.
    """
    try:
        import concurrent.futures
        
        tickers = req.tickers
        as_of_date = req.as_of_date  # Time travel date
        results = []
        
        # Helper function for checking signals
        def check_ticker_signal(ticker):
            """
            Call the /analyze endpoint internally to get backtest results,
            then extract the current signal state from the trades.
            This ensures 100% consistency with the main chart!
            """
            try:
                import requests
                
                # Call analyze endpoint internally
                analyze_req = {
                    "ticker": ticker,
                    "alpha": 200.0,
                    "beta": 1.0,
                    "start_date": "2023-01-20",
                    "end_date": as_of_date,  # Time travel
                    "use_cache": True
                }
                
                # Since we're in the same process, call the function directly
                # First, create an AnalysisRequest object
                req_obj = AnalysisRequest(**analyze_req)
                
                # Call the analyze function directly
                result = analyze_stock(req_obj)
                
                if "error" in result:
                    return None
                
                # Extract backtest data
                frozen_bt = result.get("frozen_strategy", {})
                sum_bt = result.get("frozen_sum_strategy", {})
                
                frozen_trades = frozen_bt.get("trades", [])
                sum_trades = sum_bt.get("trades", [])
                
                # Get last price date
                dates = result.get("dates", [])
                last_date = dates[-1] if dates else ""
                
                # Get Z-values from frozen series
                frozen_data = result.get("frozen_data", {})
                z_frozen_pot = frozen_data.get("pot", [])
                z_frozen_sum = frozen_data.get("z_sum", [])
                
                last_z_pot = z_frozen_pot[-1] if z_frozen_pot else 0
                last_z_sum = z_frozen_sum[-1] if z_frozen_sum else 0
                
                # Determine current state from trades
                def get_signal_state(trades):
                    """Determine BUY/SELL/HOLD/WAIT from backtest trades."""
                    if not trades:
                        return {"action": "WAIT", "trade": None}
                        
                    last_trade = trades[-1]
                    exit_dt = last_trade.get("exit_date")
                    
                    # 1. OPEN POSITION
                    if exit_dt is None or exit_dt == "OPEN" or last_trade.get("pnl_pct") is None:
                        entry_date = last_trade.get("entry_date", "")
                        if entry_date == last_date:
                            return {"action": "BUY", "trade": last_trade}
                        else:
                            return {"action": "HOLD", "trade": last_trade}
                    
                    # 2. CLOSED POSITION (Check if just closed)
                    if exit_dt == last_date:
                        return {"action": "SELL", "trade": last_trade}
                    
                    # 3. NO ACTIVE POSITION
                    return {"action": "WAIT", "trade": last_trade}
                
                frozen_res = get_signal_state(frozen_trades)
                sum_res = get_signal_state(sum_trades)
                
                # Get market cap
                market_cap = result.get("market_cap", 0)
                
                return {
                    "ticker": ticker,
                    "market_cap": market_cap,
                    "last_date": last_date,
                    "frozen": {
                        "strategy": "FROZEN", 
                        "action": frozen_res["action"], 
                        "value": round(last_z_pot, 2), 
                        "date": last_date,
                        "trade": frozen_res["trade"]
                    },
                    "sum": {
                        "strategy": "SUM", 
                        "action": sum_res["action"], 
                        "value": round(last_z_sum, 2), 
                        "date": last_date,
                        "trade": sum_res["trade"]
                    }
                }
                
            except Exception as e:
                print(f"Error scanning {ticker}: {e}")
                return None

        # PARALLEL EXECUTION
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_ticker_signal, t) for t in tickers]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res:
                    results.append(res)
        
        # Sort by Market Cap desc
        results.sort(key=lambda x: x['market_cap'], reverse=True)
        
        return results

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# --- PORTFOLIO API ---
PORTFOLIO_FILE = "portfolio.json"

class PortfolioManager:
    def __init__(self):
        self.use_firebase = False
        self.db = None
        self.local_file = PORTFOLIO_FILE
        
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
            import base64
            import json

            cred = None
            
            # 1. Check Env Var (for Railway/Cloud)
            env_key_b64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_BASE64")
            if env_key_b64:
                try:
                    # Decode Base64 -> JSON String -> Dict
                    decoded_json = base64.b64decode(env_key_b64).decode('utf-8')
                    cred_dict = json.loads(decoded_json)
                    cred = credentials.Certificate(cred_dict)
                    print("☁️ Configurazione Firebase caricata da ENV (Base64).")
                except Exception as e:
                    print(f"⚠️ Errore decodifica Base64 Firebase Key: {e}")

            # 2. Check Local File (for Local Dev)
            if not cred:
                key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serviceAccountKey.json")
                if os.path.exists(key_path):
                    cred = credentials.Certificate(key_path)
                    print("📂 Configurazione Firebase caricata da file locale.")

            # 3. Initialize App
            if cred:
                if not firebase_admin._apps:
                    firebase_admin.initialize_app(cred)
                self.db = firestore.client()
                self.use_firebase = True
                print("🔥 Firebase Portfolio Connesso! (Firestore)")
            else:
                 print("⚠️ Nessuna credenziale Firebase trovata (File o Env). Uso locale.")
                 self._ensure_local_file()
                 
        except Exception as e:
            print(f"⚠️ Errore inizializzazione Firebase generale: {e}")
            self._ensure_local_file()

    def _ensure_local_file(self):
        if not os.path.exists(self.local_file):
            with open(self.local_file, "w") as f:
                json.dump({"positions": []}, f)

    def load(self):
        if self.use_firebase:
            try:
                doc_ref = self.db.collection("portfolio").document("main")
                doc = doc_ref.get()
                if doc.exists:
                    data = doc.to_dict()
                    # Ensure positions exists
                    if "positions" not in data:
                        data["positions"] = []
                    return data
                else:
                    return {"positions": []}
            except Exception as e:
                print(f"⚠️ Errore lettura Firebase: {e}")
                return {"positions": []}
        else:
            with open(self.local_file, "r") as f:
                return json.load(f)

    def save(self, data):
        if self.use_firebase:
            try:
                doc_ref = self.db.collection("portfolio").document("main")
                doc_ref.set(data)
            except Exception as e:
                print(f"⚠️ Errore salvataggio Firebase: {e}")
                raise e
        else:
            with open(self.local_file, "w") as f:
                json.dump(data, f, indent=4)


    def get_price(self, ticker):
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
            return 0.0
        except:
            return 0.0




@app.post("/scan/email")
def trigger_email_scan(background_tasks: BackgroundTasks):
    """
    Triggers a full market scan of all tickers and sends results via email.
    Runs in background to avoid timeout.
    """
    from scanner import run_market_scan
    background_tasks.add_task(run_market_scan, send_email=True)
    return {"status": "started", "message": "📩 Scansione avviata! Riceverai l'email al termine (circa 5-10 min)."}

@app.post("/scan/test-email")
def test_email_config():
    """Quick test to verify email configuration works."""
    import os
    from notifications import NotificationManager
    
    sender = os.getenv("EMAIL_SENDER", "NOT SET")
    recipient = os.getenv("EMAIL_RECIPIENT", "NOT SET")
    password_set = "YES" if os.getenv("EMAIL_PASSWORD") else "NO"
    
    print(f"📧 Testing email config...")
    print(f"   Sender: {sender}")
    print(f"   Recipient: {recipient}")
    print(f"   Password set: {password_set}")
    
    notifier = NotificationManager()
    notifier.send_email(
        "🧪 Test Email - Financial Physics",
        "<h2>✅ Email funziona!</h2><p>Se ricevi questa email, la configurazione è corretta.</p>"
    )
    
    return {
        "sender": sender,
        "recipient": recipient,
        "password_set": password_set,
        "message": "Test email inviata! Controlla la console del server per errori."
    }

portfolio_mgr = PortfolioManager()

@app.get("/portfolio")
def get_portfolio():
    try:
        data = portfolio_mgr.load()
        positions = data.get("positions", [])
        
        updated_positions = []
        for p in positions:
            if p["status"] == "OPEN":
                curr = portfolio_mgr.get_price(p["ticker"])
                if curr > 0:
                    p["current_price"] = round(curr, 2)
                    entry = p["entry_price"]
                    direction = p.get("direction", "LONG")
                    
                    if direction == "LONG":
                        pnl = ((curr - entry) / entry) * 100
                    else:
                        pnl = ((entry - curr) / entry) * 100
                    p["pnl_pct"] = round(pnl, 2)
            updated_positions.append(p)
            
        return {"positions": updated_positions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class PortfolioTrade(BaseModel):
    ticker: str
    direction: str = "LONG"
    strategy: str = "Manual"
    notes: str = ""

@app.post("/portfolio/open")
def open_position(trade: PortfolioTrade):
    ticker = trade.ticker.upper()
    try:
        price = portfolio_mgr.get_price(ticker)
        if price == 0:
            raise HTTPException(status_code=400, detail="Prezzo non disponibile")
            
        data = portfolio_mgr.load()
        new_pos = {
            "id": str(uuid.uuid4()),
            "ticker": ticker,
            "direction": trade.direction,
            "strategy": trade.strategy,
            "notes": trade.notes,
            "entry_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "entry_price": round(price, 2),
            "status": "OPEN",
            "exit_date": None,
            "exit_price": None,
            "pnl_pct": 0.0,
            "current_price": round(price, 2)
        }
        data["positions"].append(new_pos)
        portfolio_mgr.save(data)
        return new_pos
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class PortfolioUpdate(BaseModel):
    strategy: str = None
    notes: str = None

@app.post("/portfolio/update/{pos_id}")
def update_position(pos_id: str, update: PortfolioUpdate):
    try:
        data = portfolio_mgr.load()
        positions = data.get("positions", [])
        found = False
        for p in positions:
            if p["id"] == pos_id:
                if update.strategy is not None:
                    p["strategy"] = update.strategy
                if update.notes is not None:
                    p["notes"] = update.notes
                found = True
                break
        
        if not found:
            raise HTTPException(status_code=404, detail="Posizione non trovata")
            
        portfolio_mgr.save(data)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/portfolio/close/{pos_id}")
def close_position(pos_id: str):
    try:
        data = portfolio_mgr.load()
        positions = data.get("positions", [])
        found = False
        for p in positions:
            if p["id"] == pos_id and p["status"] == "OPEN":
                price = portfolio_mgr.get_price(p["ticker"])
                if price == 0:
                     price = p.get("current_price", p["entry_price"])
                
                p["exit_price"] = round(price, 2)
                p["exit_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                p["status"] = "CLOSED"
                p["current_price"] = round(price, 2)
                
                entry = p["entry_price"]
                direction = p.get("direction", "LONG")
                if direction == "LONG":
                    pnl = ((price - entry) / entry) * 100
                else:
                    pnl = ((entry - price) / entry) * 100
                p["pnl_pct"] = round(pnl, 2)
                
                found = True
                break
        
        if not found:
            raise HTTPException(status_code=404, detail="Posizione non trovata")
            
        portfolio_mgr.save(data)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
