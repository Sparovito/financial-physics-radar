import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt
import os
import sys
import json
from datetime import datetime
from logic import MarketData, ActionPath, FourierEngine, backtest_strategy
from shared_state import TICKER_CACHE

def run_analysis(ticker, alpha=200.0, beta=1.0, top_k=5, forecast_days=60, start_date="2023-01-01", end_date=None, use_cache=False):
    print(f"Ricevuta richiesta analisi: {ticker}")
    
    # 1. Scarica Dati & Gestione Cache Avanzata
    px = None
    full_frozen_data = None
    
    # Check Cache
    use_cache_data = False
    if use_cache and ticker in TICKER_CACHE:
        cached_obj = TICKER_CACHE[ticker]
        cached_px = cached_obj["px"]
        
        # Verify Date Coverage
        if start_date:
            req_start_ts = pd.Timestamp(start_date)
            if cached_px.index[0] > req_start_ts + pd.Timedelta(days=10):
                print(f"⚠️ Cache miss (Storia insufficiente): Cached({cached_px.index[0].date()}) > Req({start_date})")
                use_cache_data = False
            else:
                use_cache_data = True
        else:
            use_cache_data = True
        
        if use_cache_data and cached_obj.get("frozen") is None:
            print(f"⚠️ Cache partial miss (Dati Frozen mancanti). Ricalcolo...")
            use_cache_data = False

    if use_cache_data:
        print(f"⚡ CACHE HIT: Uso dati in memoria per {ticker}")
        cached_obj = TICKER_CACHE[ticker]
        px = cached_obj["px"]
        full_frozen_data = cached_obj.get("frozen", None)
        zigzag_series = cached_obj.get("zigzag", None)
        volume_series = cached_obj.get("volume", None)
        if volume_series is None:
            volume_series = pd.Series([0]*len(px), index=px.index)
        mkt_cap = cached_obj.get("mkt_cap", 0)

        # Slice by Requested Start Date
        if start_date:
            start_ts = pd.Timestamp(start_date)
            if px.index.tz is not None and start_ts.tz is None:
                start_ts = start_ts.tz_localize(px.index.tz)
            
            px = px[px.index >= start_ts]
            if volume_series is not None:
                volume_series = volume_series[volume_series.index >= start_ts]
            if zigzag_series is not None:
                zigzag_series = zigzag_series[zigzag_series.index >= start_ts]
            
            # Slice Frozen Data Lists
            if full_frozen_data:
                start_date_str = start_date
                idx_start = 0
                for i, d in enumerate(full_frozen_data["dates"]):
                    if d >= start_date_str:
                        idx_start = i
                        break
                
                full_frozen_data = {
                    "dates": full_frozen_data["dates"][idx_start:],
                    "kin": full_frozen_data["kin"][idx_start:],
                    "pot": full_frozen_data["pot"][idx_start:],
                    "z_sum": full_frozen_data.get("z_sum", [])[idx_start:] 
                }
    else:
        # Scarica storia COMPLETA
        print(f"🌐 API FETCH: Scarico dati freschi per {ticker}...")
        md = MarketData(ticker, start_date=start_date, end_date=None)
        px = md.fetch()
        
        # Extract Volume
        if hasattr(md, 'df_full') and 'Volume' in md.df_full.columns:
            volume_series = md.df_full['Volume']
        else:
            volume_series = pd.Series([0]*len(px), index=px.index)

        # Market Cap
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
            mkt_cap = 0
        
        print(f"📊 {ticker} Market Cap = {mkt_cap}")

        # Calculate ZigZag (Hourly if possible)
        try:
            print(f"📊 Fetching hourly data for ZigZag...")
            hourly_data = md.ticker_obj.history(period="2y", interval="1h")
            if not hourly_data.empty and 'Open' in hourly_data.columns and 'Close' in hourly_data.columns:
                hourly_diff = hourly_data['Close'] - hourly_data['Open']
                hourly_signs = hourly_diff.apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
                hourly_signs.index = pd.to_datetime(hourly_signs.index).date
                daily_net = hourly_signs.groupby(hourly_signs.index).sum()
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
                print("⚠️ Hourly data not available, using daily fallback")
                d_open = md.df_full['Open']
                d_close = md.df_full['Close']
                diff = d_close - d_open
                signs = diff.apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
                zigzag_series = signs.cumsum()
        except Exception as e:
            print(f"⚠️ Errore calcolo ZigZag: {e}")
            zigzag_series = pd.Series([0]*len(px), index=px.index)
        
        # Pre-calcolo Frozen
        print(f"🧊 Pre-calcolo Frozen History completa (può richiedere tempo)...")
        SAMPLE_EVERY = 1
        MIN_POINTS = 100
        f_kin, f_pot, f_sum, f_dates = [], [], [], []
        n_total = len(px)
        
        for t in range(MIN_POINTS, n_total, SAMPLE_EVERY):
            px_t = px.iloc[:t+1]
            try:
                mech_t = ActionPath(px_t, alpha=alpha, beta=beta)
                if len(mech_t.kin_density) >= 25:
                    val_kin = round(float(mech_t.kin_density.iloc[-25]), 2)
                else:
                    val_kin = 0.0
                f_kin.append(val_kin)
                val_pot = round(float(mech_t.pot_density.iloc[-1]), 2)
                f_pot.append(val_pot)
                curr_kin_raw = float(mech_t.kin_density.iloc[-1])
                curr_pot_raw = float(mech_t.pot_density.iloc[-1])
                val_sum = curr_kin_raw + curr_pot_raw
                f_sum.append(val_sum)
                f_dates.append(px.index[t].strftime('%Y-%m-%d'))
            except:
                continue
        
        # Normalize Frozen Sum
        f_sum_series = pd.Series(f_sum)
        roll_fsum_mean = f_sum_series.rolling(window=252, min_periods=20).mean()
        roll_fsum_std = f_sum_series.rolling(window=252, min_periods=20).std()
        z_frozen_sum = ((f_sum_series - roll_fsum_mean) / (roll_fsum_std + 1e-6)).fillna(0).tolist()
        
        try:
            b, a = butter(N=2, Wn=0.05, btype='low')
            z_frozen_sum_filtered = filtfilt(b, a, z_frozen_sum).tolist()
            z_frozen_sum = z_frozen_sum_filtered
        except Exception as e:
            print(f"⚠️ Filter failed: {e}")
        
        z_frozen_sum = [round(x, 2) for x in z_frozen_sum]
        
        full_frozen_data = {
            "dates": f_dates,
            "kin": f_kin,
            "pot": f_pot,
            "z_sum": z_frozen_sum,
            "raw_sum": f_sum
        }
        
        TICKER_CACHE[ticker] = {
            "px": px,
            "frozen": full_frozen_data,
            "zigzag": zigzag_series,
            "volume": volume_series,
            "mkt_cap": mkt_cap
        }

    # Simulation Time Travel
    if end_date:
        end_ts = pd.Timestamp(end_date)
        px = px[px.index <= end_ts]
        
        if zigzag_series is not None:
            zigzag_series = zigzag_series[zigzag_series.index <= end_ts]
        if volume_series is not None:
            volume_series = volume_series[volume_series.index <= end_ts]
        
        # Slice Frozen
        trunc_dates = []
        trunc_kin = []
        trunc_pot = []
        trunc_z_sum = []
        
        if full_frozen_data and "raw_sum" in full_frozen_data:
            full_dates = full_frozen_data["dates"]
            full_raw_sum = full_frozen_data["raw_sum"]
            from bisect import bisect_right
            cut_idx = bisect_right(full_dates, end_date)
            if cut_idx > 0:
                trunc_dates = full_frozen_data["dates"][:cut_idx]
                trunc_kin = full_frozen_data["kin"][:cut_idx]
                trunc_pot = full_frozen_data["pot"][:cut_idx]
                trunc_raw = full_raw_sum[:cut_idx]
                
                s_trunc = pd.Series(trunc_raw)
                roll_mean = s_trunc.rolling(window=252, min_periods=20).mean()
                roll_std = s_trunc.rolling(window=252, min_periods=20).std()
                z_trunc = ((s_trunc - roll_mean) / (roll_std + 1e-6)).fillna(0).tolist()
                
                try:
                    b, a = butter(N=2, Wn=0.05, btype='low')
                    if len(z_trunc) > 15:
                        trunc_z_sum = filtfilt(b, a, z_trunc).tolist()
                    else:
                        trunc_z_sum = z_trunc
                except:
                    trunc_z_sum = z_trunc
                trunc_z_sum = [round(x, 2) for x in trunc_z_sum]
            else:
                pass
        else:
            # Fallback
            target_date_str = end_date
            for i, d in enumerate(full_frozen_data["dates"]):
                if d <= target_date_str:
                    trunc_dates.append(d)
                    trunc_kin.append(full_frozen_data["kin"][i])
                    trunc_pot.append(full_frozen_data["pot"][i])
                    trunc_z_sum.append(full_frozen_data["z_sum"][i])
                else:
                    break
        
        full_frozen_data = {
            "dates": trunc_dates,
            "kin": trunc_kin,
            "pot": trunc_pot,
            "z_sum": trunc_z_sum,
            "raw_sum": []
        }
        frozen_dates = trunc_dates
        frozen_z_kin = trunc_kin
        frozen_z_pot = trunc_pot
        frozen_z_sum = trunc_z_sum
        print(f"🕐 Simulating past: data truncated to {end_date}")
    else:
        frozen_dates = full_frozen_data["dates"]
        frozen_z_kin = full_frozen_data["kin"]
        frozen_z_pot = full_frozen_data["pot"]
        frozen_z_sum = full_frozen_data["z_sum"]

    zigzag_line = zigzag_series.values.tolist() if zigzag_series is not None else []
    
    # Live Minima Azione
    mechanics = ActionPath(px, alpha=alpha, beta=beta)
    fourier = FourierEngine(px, top_k=top_k)
    future_idx, future_vals = fourier.reconstruct_scenario(future_horizon=forecast_days)
    
    dates_historical = px.index.strftime('%Y-%m-%d').tolist()
    price_real = px.values.tolist()
    price_min_action = mechanics.px_star.values.tolist()
    fundamentals = mechanics.F.values.tolist()
    kin_density = mechanics.kin_density.values.tolist()
    pot_density = mechanics.pot_density.values.tolist()
    cum_action = mechanics.cumulative_action.values.tolist()
    slope_line = mechanics.dX.values.tolist()
    z_residuo_line = mechanics.z_residuo.values.tolist()
    
    ROC_PERIOD = 20
    roc = ((px - px.shift(ROC_PERIOD)) / px.shift(ROC_PERIOD) * 100).fillna(0)
    roc_line = roc.values.tolist()
    roll_roc_mean = roc.rolling(window=252, min_periods=20).mean()
    roll_roc_std = roc.rolling(window=252, min_periods=20).std()
    z_roc = ((roc - roll_roc_mean) / (roll_roc_std + 1e-6)).fillna(0)
    z_roc_line = z_roc.values.tolist()
    
    ZSCORE_WINDOW = 252
    kin = mechanics.kin_density
    roll_kin_mean = kin.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
    roll_kin_std = kin.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
    z_kin_series = ((kin - roll_kin_mean) / (roll_kin_std + 1e-6)).fillna(0).values.tolist()
    
    slope = mechanics.dX
    roll_slope_mean = slope.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
    roll_slope_std = slope.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
    z_slope_series = ((slope - roll_slope_mean) / (roll_slope_std + 1e-6)).fillna(0).values.tolist()
    
    # Backtest LIVE
    backtest_result = backtest_strategy(
        prices=price_real,
        z_kinetic=z_kin_series,
        z_slope=z_slope_series,
        dates=dates_historical,
        start_date=start_date,
        end_date=end_date
    )
    
    # Backtest FROZEN (POTENTIAL)
    padding_size = len(price_real) - len(frozen_z_pot)
    aligned_frozen_pot = [0] * padding_size + frozen_z_pot
    frozen_pot_series = pd.Series(aligned_frozen_pot).fillna(0)
    roll_fpot_mean = frozen_pot_series.rolling(window=ZSCORE_WINDOW, min_periods=20).mean()
    roll_fpot_std = frozen_pot_series.rolling(window=ZSCORE_WINDOW, min_periods=20).std()
    z_frozen_pot_score = ((frozen_pot_series - roll_fpot_mean) / (roll_fpot_std + 1e-6)).fillna(0).values.tolist()
    
    backtest_result_frozen = backtest_strategy(
        prices=price_real,
        z_kinetic=z_frozen_pot_score,
        z_slope=z_slope_series,
        dates=dates_historical,
        start_date=start_date,
        end_date=end_date,
        use_z_roc=True
    )
    
    # Backtest FROZEN SUM
    padding_sum = len(price_real) - len(frozen_z_sum)
    aligned_frozen_sum = [-999] * padding_sum + frozen_z_sum
    
    backtest_result_frozen_sum = backtest_strategy(
        prices=price_real,
        z_kinetic=aligned_frozen_sum,
        z_slope=z_slope_series,
        dates=dates_historical,
        start_date=start_date,
        end_date=end_date,
        threshold=-0.3, # Entry at -0.3
        use_z_roc=True
    )
    
    try:
        dates_future = [d.strftime('%Y-%m-%d') for d in future_idx]
    except:
        dates_future = [str(d) for d in future_idx]
        
    avg_abs_kin = ((kin - roll_kin_mean) / (roll_kin_std + 1e-6)).fillna(0).abs().mean()
    
    return {
        "status": "ok",
        "ticker": ticker,
        "avg_abs_kin": round(float(avg_abs_kin), 2),
        "market_cap": mkt_cap,
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
            "zigzag": zigzag_line
        },
        "backtest": backtest_result,
        "frozen_strategy": backtest_result_frozen,
        "frozen_sum_strategy": backtest_result_frozen_sum,
        "forecast": {
            "dates": dates_future,
            "values": future_scenario
        },
        "fourier_components": fourier.get_components(),
        "frozen": {
            "dates": frozen_dates,
            "z_kinetic": frozen_z_kin,
            "z_potential": frozen_z_pot,
            "z_sum": frozen_z_sum
        }
    }
