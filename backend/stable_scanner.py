"""
STABLE Strategy Scanner with Daily Email Alerts

Uses the SAME download system as main.py (MarketData + PRICE_CACHE + TICKER_CACHE)
to avoid separate Yahoo requests that get rate-limited.

Two email sections:
  1) ENTRY OGGI — trigger scattato oggi
  2) ENTRY RECENTI (< 5gg) — trigger negli ultimi 5 giorni, con "X giorni fa"
"""
import os
import json
import datetime
import concurrent.futures
import threading
import pandas as pd
import numpy as np

from notifications import NotificationManager

# --- CONFIG FILE ---
STABLE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "stable_alert_config.json")

DEFAULT_CONFIG = {
    "enabled": True,
    # 22:30 Europe/Rome = dopo la chiusura USA (22:00): la candela daily di
    # Yahoo è completa. Girare a mercati aperti produce segnali su barre
    # parziali che possono sparire il giorno dopo (repainting).
    "trigger_hour": 22,
    "trigger_minute": 30,
    "mode": "LONG",
    "entry_threshold": 0.0,
    "exit_threshold": 0.0,
    "alpha": 200,
    "start_date": "2023-01-01",
    "tickers": [],
    "preset": "all",
    "recipient": "",
    # Se True (default), scarta l'ultima barra quando è quella di OGGI e
    # sono prima delle 22:05 Rome: segnali solo su barre COMPLETE.
    "skip_partial_today": True,
    # Strategia dei segnali: STABLE (trend) | ARANCIONE (scarico del
    # potenziale: onset z_pot>entry_z con prezzo<F, hold `horizon` barre)
    # | COMBO (trend OR arancione).
    "strategy": "STABLE",
    "entry_z": 2.0,
    "horizon": 21,
    # Forward test: registra i segnali reali nel journal persistente
    # (paper trading a quota fissa, esecuzione t+1).
    "forward_test": True,
}

CONFIG_NAME = "stable_alert_config"


def load_config():
    """Config dallo storage persistente (Firestore; il file nel repo è il
    seed iniziale e il fallback). Su Railway il disco si azzera a ogni
    deploy: senza storage remoto le modifiche fatte dalla UI andavano perse."""
    try:
        from storage import get_storage
        cfg = get_storage().load(CONFIG_NAME, default=None)
        if cfg:
            return {**DEFAULT_CONFIG, **cfg}
    except Exception as e:
        print(f"⚠️ Errore caricamento config STABLE: {e}")
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    try:
        from storage import get_storage
        ok = get_storage().save(CONFIG_NAME, cfg)
        print(f"✅ Config STABLE salvata ({get_storage().status()['backend']})")
        return bool(ok)
    except Exception as e:
        print(f"❌ Errore salvataggio config STABLE: {e}")
        return False


def strategy_params(cfg):
    """Parametri che DEFINISCONO il segnale: sono quelli che il forward test
    congela. L'alpha entra solo dove governa davvero il segnale (leg trend)."""
    from stable_strategy import POTENTIAL_ALPHA, POTENTIAL_BETA
    strategy = cfg.get("strategy", "STABLE")
    p = {"strategy": strategy}
    if strategy in ("ARANCIONE", "COMBO"):
        p.update({"entry_z": float(cfg.get("entry_z", 2.0)),
                  "horizon": int(cfg.get("horizon", 21)),
                  "potential_alpha": POTENTIAL_ALPHA,
                  "potential_beta": POTENTIAL_BETA})
    if strategy in ("STABLE", "COMBO"):
        p.update({"alpha": float(cfg.get("alpha", 200)),
                  "entry_threshold": float(cfg.get("entry_threshold", 0.0)),
                  "exit_threshold": float(cfg.get("exit_threshold", 0.0))})
    if strategy == "STABLE":
        p["mode"] = cfg.get("mode", "LONG")
    return p


# ============================================================
#  DOWNLOAD: reuse main.py system (MarketData + caches)
# ============================================================

def download_all_prices(tickers, start_date, max_workers=8):
    """
    Download prices using the SAME system as the rest of the app:
    PRICE_CACHE → TICKER_CACHE → MarketData (yfinance single ticker).

    This is the system that already works for analysis.
    """
    from main import PRICE_CACHE, TICKER_CACHE, _price_cache_lock
    from logic import MarketData

    all_prices = {}
    failed = []
    cache_key_prefix = start_date or "6m"
    _lock = threading.Lock()

    # Separate cached vs to-download
    to_download = []
    for t in tickers:
        key = f"{t}|{cache_key_prefix}"
        if key in PRICE_CACHE:
            all_prices[t] = PRICE_CACHE[key].copy()
        elif t in TICKER_CACHE:
            px = TICKER_CACHE[t]["px"].copy()
            if start_date:
                start_ts = pd.Timestamp(start_date)
                if px.index.tz is not None and start_ts.tz is None:
                    start_ts = start_ts.tz_localize(px.index.tz)
                px = px[px.index >= start_ts]
            with _price_cache_lock:
                PRICE_CACHE[key] = px.copy()
            all_prices[t] = px
        else:
            to_download.append(t)

    print(f"   💾 {len(all_prices)} dalla cache, 🌐 {len(to_download)} da scaricare")

    if not to_download:
        return all_prices, failed

    def fetch_one(ticker):
        key = f"{ticker}|{cache_key_prefix}"
        try:
            md = MarketData(ticker, start_date=start_date)
            px = md.fetch()
            if px is not None and len(px) >= 30:
                with _price_cache_lock:
                    PRICE_CACHE[key] = px.copy()
                with _lock:
                    all_prices[ticker] = px
            else:
                with _lock:
                    failed.append(ticker)
        except Exception as e:
            with _lock:
                failed.append(ticker)

    n_workers = min(max_workers, len(to_download))
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(fetch_one, t): t for t in to_download}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            done += 1
            if done % 50 == 0:
                print(f"      Download: {done}/{len(to_download)}...")
            try:
                future.result()
            except Exception:
                pass

    print(f"   📦 Download completato: {len(all_prices)} OK, {len(failed)} falliti")
    return all_prices, failed


# ============================================================
#  SIGNAL COMPUTATION (motore unificato stable_strategy)
# ============================================================

def drop_partial_last_bar(px, today=None, now=None, ticker=None, utc_today=None):
    """
    Scarta l'ultima barra daily se è la barra di OGGI e siamo prima delle
    22:05 Europe/Rome (chiusura USA = 22:00): in quel caso la candela Yahoo
    è INCOMPLETA e un segnale calcolato su di essa può sparire entro la
    chiusura (repainting). I segnali devono usare solo barre complete.

    Crypto (ticker che finisce in -USD): la barra giornaliera chiude a
    mezzanotte UTC, quindi quella del giorno UTC in corso è incompleta a
    qualunque ora — anche alle 22:30 di Roma.
    """
    if px is None or len(px) == 0:
        return px
    if today is None:
        today = datetime.date.today()
    if now is None:
        try:
            import pytz
            now = datetime.datetime.now(pytz.timezone("Europe/Rome")).replace(tzinfo=None)
        except Exception:
            now = datetime.datetime.now()

    last = px.index[-1]
    last_date = last.date() if hasattr(last, "date") else last

    if ticker and ticker.upper().endswith("-USD"):
        if utc_today is None:
            utc_today = datetime.datetime.utcnow().date()
        return px.iloc[:-1] if last_date >= utc_today else px

    cutoff = now.replace(hour=22, minute=5, second=0, microsecond=0)
    if last_date == today and now < cutoff:
        return px.iloc[:-1]
    return px


def analyze_ticker_signals(ticker, px, today, alpha=200, mode="LONG",
                           entry_threshold=0.0, exit_threshold=0.0, recent_days=5,
                           strategy="STABLE", entry_z=2.0, horizon=21):
    """
    Segnali per un ticker, derivati dal MOTORE UNIFICATO — stessa semantica
    del Lab (level-based, SHORT speculare, esecuzione t+1).

    strategy: "STABLE" (trend) | "ARANCIONE" (scarico del potenziale)
              | "COMBO" (trend OR arancione)

    Returns: {"entries": [...], "active": [...]}
      entries: segnali ENTRY degli ultimi `recent_days` giorni di calendario
               (days_ago=0 = oggi; pending_execution=True se l'esecuzione
               reale avverrà alla prossima barra). Per ARANCIONE/COMBO il
               campo "kind" distingue PANIC (onset del potenziale) da TREND,
               e "slope" contiene lo z del potenziale per i segnali PANIC.
      active:  posizioni aperte; per la parte arancione include "days_left"
               (barre rimanenti dell'holding, salvo estensioni).
    """
    from stable_strategy import (backtest_stable, backtest_potential_discharge,
                                 backtest_combo, potential_discharge_onsets)
    from logic import kalman_frozen_series

    min_len = 10 if strategy == "STABLE" else 160  # kalman(100) + rolling z(40) + margine
    if len(px) < min_len:
        return {"entries": [], "active": []}

    ema_span = max(5, int(alpha / 10))
    F_alpha = px.ewm(span=ema_span, adjust=False).mean()
    dF_alpha = F_alpha.diff().fillna(0)
    stable_slope = dF_alpha.ewm(span=14, adjust=False).mean()

    dates = [d.strftime("%Y-%m-%d") for d in px.index]
    prices = [float(v) for v in px.values]
    slopes = [float(v) for v in stable_slope.values]

    onset_idx, z_pot = [], []
    if strategy in ("ARANCIONE", "COMBO"):
        # Il potenziale usa SEMPRE i parametri validati, non l'alpha del trend
        from stable_strategy import POTENTIAL_ALPHA, POTENTIAL_BETA
        fr = kalman_frozen_series(px, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA,
                                  min_points=100, kin_lag=25)
        pot = ([float("nan")] * 100 + list(fr["pot_last"]))[:len(prices)]
        F20 = px.ewm(span=20, adjust=False).mean().values.tolist()
        onset_idx, z_pot = potential_discharge_onsets(prices, pot, F20, entry_z=entry_z)
        if strategy == "ARANCIONE":
            res = backtest_potential_discharge(dates, prices, pot, F20,
                                               entry_z=entry_z, horizon=horizon,
                                               execution_lag=1, cost_pct=0.0)
        else:
            res = backtest_combo(dates, prices, slopes, pot, F20,
                                 entry_th=entry_threshold, exit_th=exit_threshold,
                                 entry_z=entry_z, horizon=horizon,
                                 execution_lag=1, cost_pct=0.0)
    else:
        res = backtest_stable(dates, prices, slopes, mode=mode,
                              entry_th=entry_threshold, exit_th=exit_threshold,
                              execution_lag=1, cost_pct=0.0)

    current_price = prices[-1]
    current_slope = slopes[-1]
    onset_set = set(onset_idx)
    last_idx = len(prices) - 1
    last_onset = onset_idx[-1] if onset_idx else None
    # barre rimanenti dell'holding arancione (se la finestra è attiva)
    days_left = None
    if last_onset is not None and last_idx - last_onset < horizon:
        days_left = int(horizon - (last_idx - last_onset))

    entries = []
    for ev in res["signal_events"]:
        if ev["type"] != "ENTRY":
            continue
        sig_date = datetime.date.fromisoformat(ev["signal_date"])
        days_ago = (today - sig_date).days
        if days_ago < 0 or days_ago > recent_days:
            continue
        sig_price = float(ev["price_at_signal"]) if ev["price_at_signal"] else 0.0
        sig_i = ev["signal_index"]
        is_panic = (strategy == "ARANCIONE") or (sig_i in onset_set) or (
            # per la combo l'onset può precedere di poco la transizione di posizione
            strategy == "COMBO" and any(o <= sig_i and sig_i - o < horizon for o in onset_idx)
            and (sig_i >= len(slopes) or slopes[sig_i] <= entry_threshold)
        )
        signal_val = (z_pot[sig_i] if (is_panic and sig_i < len(z_pot))
                      else float(ev["slope_at_signal"]))
        # distanza del prezzo sotto il fondamentale EMA20, in %: nel backtest
        # è il criterio (debole ma migliore dello z) per ordinare i segnali
        ema20 = float(px.ewm(span=20, adjust=False).mean().iloc[sig_i]) if sig_i < len(px) else 0.0
        depth_pct = ((ema20 - sig_price) / ema20 * 100) if ema20 > 0 else 0.0
        entries.append({
            "depth_pct": round(depth_pct, 2),
            "ticker": ticker,
            "price": sig_price,
            "current_price": current_price,
            "slope": float(signal_val),
            "price_change_since": ((current_price - sig_price) / sig_price * 100) if sig_price > 0 else 0,
            "date": ev["signal_date"],
            "direction": ev["direction"],
            "days_ago": days_ago,
            "kind": ("PANIC" if is_panic and strategy != "STABLE" else "TREND"),
            # True = segnale sull'ultima barra: l'ingresso reale è alla
            # PROSSIMA barra disponibile (esecuzione t+1)
            "pending_execution": ev["exec_date"] is None,
        })

    active = []
    for tr in res["trades"]:
        if tr["exit_date"] != "OPEN":
            continue
        active.append({
            "ticker": ticker,
            "direction": tr["direction"],
            "entry_date": tr["entry_date"],
            "entry_price": tr["entry_price"],
            "current_price": current_price,
            "pnl_pct": tr["pnl_pct"],
            "slope": current_slope,
            "days_left": days_left if strategy != "STABLE" else None,
        })

    return {"entries": entries, "active": active}


def compute_stable_signals(tickers, alpha=200, start_date=None, mode="LONG",
                            entry_threshold=0.0, exit_threshold=0.0, max_workers=8,
                            skip_partial_today=True,
                            strategy="STABLE", entry_z=2.0, horizon=21,
                            price_sink=None, as_of_date=None):
    """
    Compute signals for all tickers (strategia configurabile).

    start_date: auto — 6 mesi per STABLE; 24 mesi per ARANCIONE/COMBO
        (servono ~100 barre di warmup Kalman + finestra dello z-score 252).
    skip_partial_today: scarta la barra di oggi se i mercati possono essere
        ancora aperti (vedi drop_partial_last_bar).
    price_sink: dict opzionale — viene riempito con {ticker: (dates, closes)}
        delle barre COMPLETE usate per i segnali (serve al forward test).
    as_of_date: "YYYY-MM-DD" — calcola i segnali come se oggi fosse quel
        giorno, usando solo le barre fino a quella data (viaggio nel tempo).
    """
    real_today = datetime.date.today()
    today = datetime.date.fromisoformat(as_of_date) if as_of_date else real_today
    today_str = today.strftime("%Y-%m-%d")

    if not start_date:
        lookback_days = 180 if strategy == "STABLE" else 730
        # per date passate recenti si riusa lo stesso scarico dello scan di
        # oggi (stessa chiave di cache): cambiare giorno non riscarica tutto
        anchor = real_today if (real_today - today).days <= 180 else today
        start_date = (anchor - datetime.timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    entries_today = []
    entries_recent = []
    active_positions = []
    errors_list = []

    # --- PHASE 1: Download (reuses main.py system) ---
    print(f"🔬 STABLE Scanner: {len(tickers)} tickers (α={alpha}, mode={mode}, "
          f"entry>{entry_threshold}, exit<{exit_threshold}, from={start_date})")

    all_prices, failed = download_all_prices(tickers, start_date, max_workers=max_workers)
    errors_list = [{"ticker": t, "error": "Download fallito"} for t in failed]

    # --- PHASE 2: Compute signals (CPU-only, motore unificato) ---
    print(f"   🧮 Calcolo segnali per {len(all_prices)} tickers (motore unificato)...")

    _lock = threading.Lock()

    def analyze_ticker(ticker, px):
        try:
            if as_of_date:
                px = px[px.index <= pd.Timestamp(as_of_date)]
            elif skip_partial_today:
                px = drop_partial_last_bar(px, today=today, ticker=ticker)
            res = analyze_ticker_signals(
                ticker, px, today, alpha=alpha, mode=mode,
                entry_threshold=entry_threshold, exit_threshold=exit_threshold,
                strategy=strategy, entry_z=entry_z, horizon=horizon,
            )
            with _lock:
                for e in res["entries"]:
                    if e["days_ago"] == 0:
                        entries_today.append(e)
                    else:
                        entries_recent.append(e)
                active_positions.extend(res["active"])
                if price_sink is not None:
                    price_sink[ticker] = (
                        [d.strftime("%Y-%m-%d") for d in px.index],
                        [float(v) for v in px.values],
                    )
        except Exception as e:
            with _lock:
                errors_list.append({"ticker": ticker, "error": str(e)})

    # Skip if nothing downloaded
    if not all_prices:
        print(f"   ⚠️ Nessun ticker scaricato.")
        return {
            "entries_today": [], "entries_recent": [], "active": [],
            "errors": errors_list,
            "params": {
                "alpha": alpha, "mode": mode,
                "entry_threshold": entry_threshold, "exit_threshold": exit_threshold,
                "n_tickers": len(tickers), "n_downloaded": 0, "date": today_str,
            }
        }

    n_workers = min(max_workers, len(all_prices), 12)
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(analyze_ticker, t, px): t for t, px in all_prices.items()}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            done += 1
            if done % 100 == 0:
                print(f"      Calcolo: {done}/{len(all_prices)}...")
            try:
                future.result()
            except Exception as e:
                t = futures[future]
                errors_list.append({"ticker": t, "error": str(e)})

    entries_recent.sort(key=lambda x: x["days_ago"])

    print(f"✅ STABLE Scanner: {len(entries_today)} ENTRY OGGI, "
          f"{len(entries_recent)} RECENTI, {len(active_positions)} attivi, "
          f"{len(errors_list)} errori")

    return {
        "entries_today": entries_today,
        "entries_recent": entries_recent,
        "active": active_positions,
        "errors": errors_list,
        "params": {
            "alpha": alpha, "mode": mode,
            "entry_threshold": entry_threshold, "exit_threshold": exit_threshold,
            "strategy": strategy, "entry_z": entry_z, "horizon": horizon,
            "n_tickers": len(tickers), "n_downloaded": len(all_prices), "date": today_str,
        }
    }


def orange_daily_scan(tickers, as_of_date=None, entry_z=None, horizon=None, max_workers=8):
    """
    SCANSIONE GIORNALIERA sull'arancione (dashboard, POST /scan-daily-orange).

    Sola lettura: non scrive il journal e non manda email. Ritorna
      signals_new    segnali sull'ultima seduta chiusa di ciascun titolo:
                     da eseguire alla prossima chiusura; ordinati per
                     distanza del prezzo sotto il fondamentale
      signals_recent segnali dei 5 giorni precedenti
      active         posizioni che la regola terrebbe oggi
      breadth_pct    % dei titoli scansionati con un segnale nuovo: dal
                     backtest il vantaggio sta soprattutto nel GIORNO
      forward        stato del forward test (solo in modalità "oggi")
    """
    from forward_test import EXPECTED, _expected_exit, load_journal, journal_stats

    cfg = load_config()
    entry_z = float(entry_z if entry_z is not None else cfg.get("entry_z", 2.0))
    horizon = int(horizon if horizon is not None else cfg.get("horizon", 21))

    res = compute_stable_signals(
        tickers=list(tickers), strategy="ARANCIONE", entry_z=entry_z, horizon=horizon,
        skip_partial_today=True, max_workers=max_workers, as_of_date=as_of_date,
    )

    def row(e):
        return {
            "ticker": e["ticker"], "signal_date": e["date"], "price": round(e["price"], 4),
            "depth_pct": e.get("depth_pct", 0.0), "z": round(e.get("slope", 0.0), 2),
            "days_ago": e["days_ago"], "current_price": round(e.get("current_price", 0.0), 4),
            "change_since_pct": round(e.get("price_change_since", 0.0), 2),
            "exit_estimate": _expected_exit(e["date"], horizon + 1),
        }

    every = res["entries_today"] + res["entries_recent"]
    new = sorted((row(e) for e in every if e.get("pending_execution")),
                 key=lambda r: r["depth_pct"], reverse=True)
    recent = sorted((row(e) for e in every if not e.get("pending_execution")),
                    key=lambda r: r["days_ago"])
    n_scanned = res["params"].get("n_downloaded", 0)

    forward = None
    if not as_of_date:
        try:
            forward = journal_stats(load_journal())
        except Exception as e:
            print(f"⚠️ Stato forward test non leggibile: {e}")

    return {
        "date": res["params"]["date"],
        "as_of": as_of_date,
        "entry_z": entry_z, "horizon": horizon,
        "n_requested": len(tickers), "n_scanned": n_scanned,
        "failed": [e["ticker"] for e in res["errors"] if e.get("ticker")],
        "breadth_pct": round(len(new) / n_scanned * 100, 2) if n_scanned else 0.0,
        "signals_new": new,
        "signals_recent": recent,
        "active": sorted(res["active"], key=lambda p: p.get("days_left") or 0),
        "expected": dict(EXPECTED),
        "forward": forward,
    }


# ============================================================
#  EMAIL BUILDER
# ============================================================

def build_stable_email(scan_result):
    params = scan_result["params"]
    entries_today = scan_result["entries_today"]
    entries_recent = scan_result["entries_recent"]
    active = scan_result["active"]
    errors = scan_result["errors"]
    today_str = params["date"]

    n_today = len(entries_today)
    n_recent = len(entries_recent)
    n_active = len(active)

    strategy = params.get("strategy", "STABLE")
    strat_label = {"STABLE": "🟣 STABLE", "ARANCIONE": "🟠 ARANCIONE",
                   "COMBO": "⚡ COMBO"}.get(strategy, strategy)
    subject = f"{strat_label.split()[0]} {strategy}: {n_today} ENTRY oggi, {n_recent} recenti ({today_str})"

    style = """
    <style>
        body { font-family: 'Helvetica Neue', Helvetica, sans-serif; background: #f0f2f5; padding: 20px; }
        .container { background: #fff; padding: 24px; border-radius: 12px; max-width: 900px; margin: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }
        h2 { border-bottom: 3px solid #aa44ff; padding-bottom: 12px; color: #1a1d29; font-size: 22px; }
        h3 { margin-top: 28px; margin-bottom: 12px; font-size: 15px; text-transform: uppercase; letter-spacing: 1.5px; }
        .params { background: #f8f8ff; border: 1px solid #e0e0e8; border-radius: 8px; padding: 14px; margin-bottom: 20px; font-size: 13px; color: #555; }
        .params b { color: #aa44ff; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 12px; }
        th { background: #1a1d29; color: #fff; padding: 10px 12px; text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
        td { padding: 10px 12px; border-bottom: 1px solid #eee; }
        tr:last-child td { border-bottom: none; }
        .bg-green { background-color: #e8f5e9; }
        .bg-yellow { background-color: #fffde7; }
        .bg-purple { background-color: #f3e5f5; }
        .text-green { color: #2e7d32; font-weight: bold; }
        .text-red { color: #c62828; font-weight: bold; }
        .text-purple { color: #7b1fa2; font-weight: bold; }
        .badge-long { background: #2e7d32; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
        .badge-short { background: #c62828; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
        .badge-days { background: #f57c00; color: #fff; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
        .stat-box { display: inline-block; background: #f0f2f5; border-radius: 8px; padding: 10px 16px; margin: 4px; text-align: center; }
        .stat-box .num { font-size: 24px; font-weight: bold; color: #aa44ff; }
        .stat-box .lbl { font-size: 11px; color: #888; text-transform: uppercase; }
    </style>
    """

    body = f"<html><head>{style}</head><body><div class='container'>"
    body += f"<h2>🔬 STABLE Strategy Alert — {today_str}</h2>"

    # Params
    body += "<div class='params'>"
    body += f"<b>Strategia:</b> {strat_label} &nbsp;|&nbsp; "
    body += f"<b>Alpha:</b> {params['alpha']} &nbsp;|&nbsp; "
    if strategy in ("ARANCIONE", "COMBO"):
        body += f"<b>Entry Z pot ></b> {params.get('entry_z', 2.0)} &nbsp;|&nbsp; "
        body += f"<b>Hold:</b> {params.get('horizon', 21)} barre &nbsp;|&nbsp; "
    if strategy in ("STABLE", "COMBO"):
        body += f"<b>Mode:</b> {params['mode']} &nbsp;|&nbsp; "
        body += f"<b>Entry ></b> {params['entry_threshold']} &nbsp;|&nbsp; "
        body += f"<b>Exit <</b> {params['exit_threshold']} &nbsp;|&nbsp; "
    body += f"<b>Tickers:</b> {params['n_downloaded']}/{params['n_tickers']}"
    body += "<br><span style='font-size:11px; color:#999;'>Segnali calcolati su barre COMPLETE "
    body += "(semantica identica al backtest del Lab, esecuzione t+1: il segnale di oggi "
    body += "si esegue realisticamente alla prossima apertura).</span>"
    body += "</div>"

    # Stats
    body += "<div style='margin-bottom: 20px;'>"
    body += f"<div class='stat-box'><div class='num' style='color:#2e7d32;'>{n_today}</div><div class='lbl'>Entry Oggi</div></div>"
    body += f"<div class='stat-box'><div class='num' style='color:#f57c00;'>{n_recent}</div><div class='lbl'>Recenti (&lt;5gg)</div></div>"
    body += f"<div class='stat-box'><div class='num'>{n_active}</div><div class='lbl'>Posiz. Attive</div></div>"
    body += "</div>"

    # SEZIONE 1: ENTRY OGGI
    if entries_today:
        entries_today.sort(key=lambda x: abs(x.get("slope", 0)), reverse=True)
        body += "<h3 style='color:#2e7d32;'>🟢 SEGNALI DI INGRESSO — OGGI</h3>"
        body += "<p style='font-size:12px; color:#666; margin-top:-8px;'>Il trigger è scattato nella giornata odierna</p>"
        body += "<table><thead><tr><th>Ticker</th><th>Direzione</th><th>Prezzo Entry</th><th>Segnale</th></tr></thead><tbody>"
        for e in entries_today:
            dir_badge = "badge-long" if e.get("direction") == "LONG" else "badge-short"
            kind = e.get("kind", "TREND")
            kind_badge = " <span style='background:#f57c00;color:#fff;padding:2px 6px;border-radius:4px;font-size:10px;'>🟠 PANICO</span>" if kind == "PANIC" else ""
            body += f"<tr class='bg-green'><td><b>{e['ticker']}</b>{kind_badge}</td>"
            body += f"<td><span class='{dir_badge}'>{e.get('direction', 'LONG')}</span></td>"
            body += f"<td>${e['price']:.2f}</td>"
            body += f"<td class='text-purple'>{e['slope']:.4f}</td></tr>"
        body += "</tbody></table>"
        body += "<p style='font-size:11px; color:#999;'>Esecuzione t+1: ingresso reale alla prossima apertura/chiusura disponibile.</p>"
    else:
        body += "<h3 style='color:#2e7d32;'>🟢 SEGNALI DI INGRESSO — OGGI</h3>"
        body += "<p style='font-size:13px; color:#999; padding:10px;'>Nessun nuovo segnale di ingresso oggi.</p>"

    # SEZIONE 2: ENTRY RECENTI (< 5gg)
    if entries_recent:
        entries_recent.sort(key=lambda x: x["days_ago"])
        body += "<h3 style='color:#f57c00;'>🟡 INGRESSI RECENTI — ULTIMI 5 GIORNI</h3>"
        body += "<p style='font-size:12px; color:#666; margin-top:-8px;'>Trigger scattato nei giorni scorsi</p>"
        body += "<table><thead><tr><th>Ticker</th><th>Dir</th><th>Prezzo Entry</th><th>Prezzo Attuale</th><th>Var %</th><th>Quando</th></tr></thead><tbody>"
        for e in entries_recent:
            dir_badge = "badge-long" if e.get("direction") == "LONG" else "badge-short"
            var_pct = e.get("price_change_since", 0)
            var_cls = "text-green" if var_pct >= 0 else "text-red"
            days = e["days_ago"]
            days_label = "IERI" if days == 1 else f"{days}gg fa"
            body += f"<tr class='bg-yellow'><td><b>{e['ticker']}</b></td>"
            body += f"<td><span class='{dir_badge}'>{e.get('direction', 'LONG')}</span></td>"
            body += f"<td>${e['price']:.2f}</td>"
            body += f"<td>${e.get('current_price', 0):.2f}</td>"
            body += f"<td class='{var_cls}'>{var_pct:+.2f}%</td>"
            body += f"<td><span class='badge-days'>{days_label}</span> <small>({e['date']})</small></td></tr>"
        body += "</tbody></table>"

    # SEZIONE 3: POSIZIONI ATTIVE
    if active:
        active.sort(key=lambda x: x.get("pnl_pct", 0), reverse=True)
        avg_pnl = sum(p["pnl_pct"] for p in active) / len(active)
        avg_cls = "text-green" if avg_pnl >= 0 else "text-red"
        body += "<h3 style='color:#7b1fa2;'>🟣 POSIZIONI ATTIVE</h3>"
        body += f"<p><b>Media PnL:</b> <span class='{avg_cls}'>{avg_pnl:.2f}%</span> su {n_active} posizioni</p>"
        body += "<table><thead><tr><th>Ticker</th><th>Dir</th><th>Ingresso</th><th>Prezzo Att.</th><th>P/L %</th></tr></thead><tbody>"
        for p in active:
            dir_badge = "badge-long" if p.get("direction") == "LONG" else "badge-short"
            pnl_cls = "text-green" if p["pnl_pct"] >= 0 else "text-red"
            days_left = p.get("days_left")
            left_label = f" <small style='color:#f57c00;'>(~{days_left} barre)</small>" if days_left else ""
            body += f"<tr class='bg-purple'><td><b>{p['ticker']}</b></td>"
            body += f"<td><span class='{dir_badge}'>{p.get('direction', 'LONG')}</span></td>"
            body += f"<td>{p['entry_date']} @ ${p['entry_price']:.2f}{left_label}</td>"
            body += f"<td>${p['current_price']:.2f}</td>"
            body += f"<td class='{pnl_cls}'>{p['pnl_pct']:.2f}%</td></tr>"
        body += "</tbody></table>"

    if not entries_today and not entries_recent and not active:
        body += f"<p style='font-size: 16px; color: #888; text-align: center; padding: 30px;'>Nessun segnale {strategy} rilevato.</p>"

    # SEZIONE 4: FORWARD TEST (track record paper trading a quota fissa)
    ft = scan_result.get("forward_test")
    if ft:
        body += "<h3 style='color:#00838f;'>🧪 FORWARD TEST — dal " + str(ft.get("created", "?")) + "</h3>"
        body += "<p style='font-size:12px; color:#666; margin-top:-8px;'>Paper trading dei segnali reali: quota fissa per trade, esecuzione t+1, uscita a orizzonte. Nessun dato retroattivo.</p>"
        sum_cls = "text-green" if ft.get("sum_pnl_pct", 0) >= 0 else "text-red"
        body += "<div style='margin-bottom: 16px;'>"
        body += f"<div class='stat-box'><div class='num'>{ft.get('closed', 0)}</div><div class='lbl'>Chiusi</div></div>"
        body += f"<div class='stat-box'><div class='num'>{ft.get('open', 0)}</div><div class='lbl'>Aperti</div></div>"
        body += f"<div class='stat-box'><div class='num'>{ft.get('pending', 0)}</div><div class='lbl'>In ingresso</div></div>"
        body += f"<div class='stat-box'><div class='num {sum_cls}' style='color:{'#2e7d32' if ft.get('sum_pnl_pct',0)>=0 else '#c62828'};'>{ft.get('sum_pnl_pct', 0):+.1f}%</div><div class='lbl'>Somma P&L</div></div>"
        body += f"<div class='stat-box'><div class='num'>{ft.get('avg_pnl_pct', 0):+.2f}%</div><div class='lbl'>Media/Trade</div></div>"
        body += f"<div class='stat-box'><div class='num'>{ft.get('win_rate', 0):.0f}%</div><div class='lbl'>Win Rate</div></div>"
        body += "</div>"
        proto = ft.get("protocol", {})
        verdict_txt = {
            "IN_CORSO": "In corso — non ancora giudicabile",
            "PROMUOVI": "PROMUOVI — criterio di promozione raggiunto",
            "STOP": "STOP — media per trade non positiva",
            "ESTENDI": "ESTENDI — risultato intermedio, si prosegue",
            "NON_CONFERMATO": "NON CONFERMATO — edge non raggiunto",
        }.get(ft.get("verdict"), ft.get("verdict", ""))
        body += "<p style='font-size:12px; color:#555;'>"
        body += f"<b>Protocollo:</b> {verdict_txt}. "
        body += f"Chiusi {ft.get('closed', 0)}/{proto.get('min_closed', 30)}, "
        body += f"settimane distinte {ft.get('n_clusters', 0)}/{proto.get('min_clusters', 3)}; "
        body += f"soglia promozione media ≥ {proto.get('promote_avg_pct', 1.0):+.1f}%/trade."
        if ft.get("protocol_violations"):
            body += f" <span style='color:#c62828;'>⚠️ {ft['protocol_violations']} cambio/i di parametri a journal avviato.</span>"
        body += "</p>"

    n_err = len(errors)
    if n_err > 0:
        body += f"<p style='font-size: 11px; color: #bbb; margin-top: 20px;'>⚠️ {n_err} ticker non scaricati</p>"

    body += "<p style='font-size: 12px; color: #888; margin-top: 30px; border-top: 1px solid #eee; padding-top: 12px;'>"
    body += "Generato da <b>STABLE Strategy Lab</b> — Financial Physics AI</p>"
    body += "</div></body></html>"

    return subject, body


# ============================================================
#  EMAIL ARANCIONE — azioni del giorno + validazione del forward test
# ============================================================

MAX_POSITIONS = 10   # tetto di posizioni simultanee del protocollo di sizing

VERDICT_LABEL = {
    "IN_CORSO": ("In corso", "#555"),
    "COERENTE": ("Coerente col backtest", "#2e7d32"),
    "STOP": ("Stop", "#c62828"),
    "ESTENDI": ("Da estendere", "#f57c00"),
    "NON_CONFERMATO": ("Non confermato", "#c62828"),
}


def _pct(v, digits=2):
    return "—" if v is None else f"{v:+.{digits}f}%"


def build_orange_email(scan_result):
    """Email giornaliera della strategia ARANCIONE.

    Ordine: (1) cosa fare oggi, (2) posizioni del forward test, (3) i segnali
    stanno funzionando? — confronto con titoli a caso lo stesso giorno e in
    un giorno qualsiasi, accanto ai valori attesi dal backtest."""
    p = scan_result["params"]
    day = p["date"]
    horizon = p.get("horizon", 21)
    signals = sorted(scan_result.get("entries_today", []),
                     key=lambda e: e.get("depth_pct", 0), reverse=True)
    recent = scan_result.get("entries_recent", [])
    ft = scan_result.get("forward_test")
    det = scan_result.get("forward_detail") or {"open": [], "due_soon": [], "closed_last_run": [], "pending": []}
    closed_now, due_soon, open_pos = det["closed_last_run"], det["due_soon"], det["open"]

    n_sig = len(signals)
    n_exit = len(closed_now) + len(due_soon)
    n_scanned = max(1, p.get("n_downloaded", 0))
    breadth = n_sig / n_scanned * 100
    v_label, v_color = VERDICT_LABEL.get(ft["verdict"], (ft["verdict"], "#555")) if ft else ("forward test non attivo", "#555")

    subject = (f"🟠 {day} · {n_sig} segnal{'e' if n_sig == 1 else 'i'} · {n_exit} uscit{'a' if n_exit == 1 else 'e'}"
               + (f" · forward {ft['closed']} chiusi ({v_label.lower()})" if ft else ""))

    css = """
    <style>
      body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background:#f0f2f5; padding:16px; color:#1a1d29; }
      .wrap { background:#fff; max-width:860px; margin:auto; padding:22px; border-radius:10px; }
      h2 { font-size:20px; margin:0 0 4px; }
      h3 { font-size:14px; text-transform:uppercase; letter-spacing:1px; margin:26px 0 8px; }
      .sub { color:#666; font-size:13px; margin:0 0 14px; }
      table { width:100%; border-collapse:collapse; font-size:13px; margin:6px 0 10px; }
      th { background:#1a1d29; color:#fff; text-align:left; padding:8px 10px; font-size:11px; text-transform:uppercase; }
      td { padding:8px 10px; border-bottom:1px solid #eee; }
      .num { text-align:right; font-variant-numeric: tabular-nums; }
      .pos { color:#2e7d32; font-weight:bold; } .neg { color:#c62828; font-weight:bold; }
      .note { font-size:12px; color:#666; margin:4px 0 10px; line-height:1.5; }
      .box { border:1px solid #e0e0e8; border-radius:8px; padding:12px 14px; margin:10px 0; background:#fafafe; }
      .warn { border-color:#f57c00; background:#fff8ee; }
    </style>"""

    def cls(v):
        return "pos" if (v or 0) >= 0 else "neg"

    b = f"<html><head><meta charset='utf-8'>{css}</head><body><div class='wrap'>"
    b += f"<h2>🟠 Arancione — {day}</h2>"
    b += (f"<p class='sub'>{n_sig} nuovi segnali · {len(closed_now)} uscite eseguite · "
          f"{len(due_soon)} in scadenza · {len(open_pos)} posizioni aperte</p>")

    # ---------- 1. COSA FARE OGGI ----------
    b += "<h3 style='color:#e65100;'>1 · Cosa fare oggi</h3>"
    if not signals and not closed_now and not due_soon:
        b += "<div class='box'>Nessuna azione oggi: nessun nuovo segnale e nessuna uscita in scadenza.</div>"

    if signals:
        b += (f"<p class='note'><b>Nuovi segnali ({n_sig}).</b> Ingresso alla prossima chiusura disponibile, "
              f"uscita dopo {horizon} barre. Ordinati per distanza del prezzo sotto il fondamentale: nel backtest "
              f"la metà più distante ha reso +4.8% contro +2.1% dell'altra.</p>")
        b += ("<table><tr><th>Ticker</th><th class='num'>Prezzo al segnale</th><th class='num'>Sotto il fondamentale</th>"
              "<th class='num'>z potenziale</th><th>Uscita indicativa</th></tr>")
        from forward_test import _expected_exit
        for i, e in enumerate(signals):
            # ingresso domani (1 barra) + horizon barre
            exit_est = _expected_exit(e["date"], horizon + 1)
            beyond = " style='color:#999;'" if i >= MAX_POSITIONS else ""
            b += (f"<tr{beyond}><td><b>{e['ticker']}</b></td><td class='num'>{e['price']:.2f}</td>"
                  f"<td class='num'>{e.get('depth_pct', 0):.1f}%</td><td class='num'>{e.get('slope', 0):.1f}</td>"
                  f"<td>~{exit_est}</td></tr>")
        b += "</table>"
        free = max(0, MAX_POSITIONS - len(open_pos))
        if n_sig > free:
            b += (f"<div class='box warn'><b>Più segnali che posti.</b> Con un tetto di {MAX_POSITIONS} posizioni "
                  f"e {len(open_pos)} già aperte restano {free} posti: valgono le prime righe della tabella.</div>")
        if breadth >= 2.0:
            b += (f"<div class='box warn'><b>Giornata di panico diffuso:</b> ha dato segnale il {breadth:.1f}% "
                  f"dei titoli scansionati. Nel backtest, dopo giornate così, anche l'indice (SPY) ha reso in media "
                  f"+3.9% in 21 barre contro +1.1% di un giorno qualsiasi (26 casi): il vantaggio sta soprattutto "
                  f"nel giorno, meno nel singolo titolo.</div>")

    if closed_now:
        b += "<p class='note'><b>Uscite eseguite all'ultimo scan.</b></p>"
        b += ("<table><tr><th>Ticker</th><th>Ingresso</th><th>Uscita</th><th class='num'>P/L</th>"
              "<th class='num'>contro SPY</th></tr>")
        for t in closed_now:
            b += (f"<tr><td><b>{t['ticker']}</b></td><td>{t['entry_date']} @ {t['entry_price']:.2f}</td>"
                  f"<td>{t['exit_date']} @ {t['exit_price']:.2f}</td>"
                  f"<td class='num {cls(t['pnl_pct'])}'>{_pct(t['pnl_pct'])}</td>"
                  f"<td class='num'>{_pct(t.get('excess_pct'))}</td></tr>")
        b += "</table>"

    if due_soon:
        b += "<p class='note'><b>In scadenza</b> (uscita alla chiusura indicata).</p>"
        b += "<table><tr><th>Ticker</th><th class='num'>Barre rimaste</th><th>Uscita indicativa</th><th class='num'>P/L attuale</th></tr>"
        for t in due_soon:
            b += (f"<tr><td><b>{t['ticker']}</b></td><td class='num'>{t['bars_left']}</td><td>{t['expected_exit']}</td>"
                  f"<td class='num {cls(t['current_pnl_pct'])}'>{_pct(t['current_pnl_pct'])}</td></tr>")
        b += "</table>"

    if recent:
        names = ", ".join(f"{e['ticker']} ({e['days_ago']}g fa)" for e in sorted(recent, key=lambda e: e["days_ago"])[:15])
        b += f"<p class='note'>Segnali dei giorni scorsi già registrati: {names}.</p>"

    # ---------- 2. POSIZIONI ----------
    b += "<h3 style='color:#6a1b9a;'>2 · Posizioni aperte del forward test</h3>"
    if open_pos:
        b += ("<table><tr><th>Ticker</th><th>Ingresso</th><th class='num'>Prezzo attuale</th><th class='num'>P/L</th>"
              "<th class='num'>Barre</th><th>Uscita indicativa</th></tr>")
        for t in open_pos:
            b += (f"<tr><td><b>{t['ticker']}</b></td><td>{t['entry_date']} @ {t['entry_price']:.2f}</td>"
                  f"<td class='num'>{t['current_price']:.2f}</td>"
                  f"<td class='num {cls(t['current_pnl_pct'])}'>{_pct(t['current_pnl_pct'])}</td>"
                  f"<td class='num'>{t['bars_held']}/{t['horizon']}</td><td>{t['expected_exit']}</td></tr>")
        b += "</table>"
        if len(open_pos) > MAX_POSITIONS:
            b += (f"<p class='note'>Il forward test registra <b>tutti</b> i segnali a quota fissa, per misurarli senza "
                  f"scelte: non applica il tetto di {MAX_POSITIONS} posizioni che useresti con capitale vero.</p>")
    else:
        b += "<p class='note'>Nessuna posizione aperta.</p>"

    # ---------- 3. STA FUNZIONANDO? ----------
    b += "<h3 style='color:#00695c;'>3 · I segnali stanno funzionando?</h3>"
    if not ft:
        b += "<p class='note'>Forward test non attivo: nessun confronto disponibile.</p>"
    else:
        ex = ft.get("expected", {})
        proto = ft.get("protocol", {})
        b += ("<p class='note'>In un mercato che sale quasi ogni acquisto guadagna: il P/L da solo non dice nulla. "
              "Per questo, insieme a ogni segnale, il sistema registra con la stessa regola un titolo a caso lo "
              "stesso giorno e un titolo a caso in un giorno qualsiasi. Conta la differenza tra le righe.</p>")
        b += ("<table><tr><th>Cosa è stato comprato</th><th class='num'>Trade chiusi</th>"
              "<th class='num'>Media per trade</th><th class='num'>Atteso dal backtest</th></tr>")
        rows = [
            ("Titoli del segnale", ft["closed"], ft["avg_pnl_pct"] if ft["closed"] else None, ex.get("signal")),
            ("Titolo a caso, stesso giorno", ft["control_closed"], ft["control_avg_pnl_pct"], ex.get("control")),
            ("Titolo a caso, giorno qualsiasi", ft["baseline_closed"], ft["baseline_avg_pnl_pct"], ex.get("baseline")),
        ]
        if ft.get("index_closed"):
            rows.append(("Indice SPY nei giorni di panico", ft["index_closed"], ft["index_avg_pnl_pct"], None))
        for name, n, avg, exp in rows:
            exp_txt = f"{exp:+.1f}%" if exp is not None else "—"
            b += (f"<tr><td>{name}</td><td class='num'>{n}</td>"
                  f"<td class='num {cls(avg) if avg is not None else ''}'>{_pct(avg)}</td>"
                  f"<td class='num'>{exp_txt}</td></tr>")
        b += "</table>"
        b += ("<p class='note'>"
              f"<b>Segnali − giorno qualsiasi:</b> {_pct(ft.get('edge_vs_baseline'))} (atteso +2.2). "
              f"<b>Di cui dal giorno scelto:</b> {_pct(ft.get('timing_edge'))} (atteso +1.5); "
              f"<b>dal titolo scelto:</b> {_pct(ft.get('edge_vs_control'))} (atteso +0.7). "
              f"Win rate {ft['win_rate']:.0f}% (atteso {ex.get('win_rate', 65)}%). "
              f"Contro SPY sulle stesse date: {_pct(ft.get('avg_excess_pct'))}.</p>")
        b += (f"<div class='box'><b style='color:{v_color};'>Semaforo: {v_label}</b> — {ft.get('verdict_reason', '')}.<br>"
              f"Avanzamento: {ft['closed']}/{proto.get('min_closed', 30)} trade chiusi, "
              f"{ft['n_clusters']}/{proto.get('min_clusters', 12)} settimane distinte. "
              "Il semaforo dice solo se i risultati sono coerenti col backtest: ogni settimana con segnali vale "
              "come una sola osservazione, e per una conferma statistica del vantaggio servirebbero anni.")
        if ft.get("protocol_violations"):
            b += (f"<br><span class='neg'>Attenzione: {ft['protocol_violations']} cambio/i di parametri a journal "
                  "avviato, il campione non è più omogeneo.</span>")
        b += "</div>"

    # ---------- piede ----------
    failed = len(scan_result.get("errors", []))
    b += ("<p class='note' style='margin-top:22px; border-top:1px solid #eee; padding-top:10px;'>"
          f"Titoli scansionati: {p.get('n_downloaded', 0)}/{p.get('n_tickers', 0)}"
          + (f" ({failed} non scaricati)" if failed else "")
          + f". Segnale: z del potenziale &gt; {p.get('entry_z', 2.0)} con prezzo sotto il fondamentale; "
          f"uscita dopo {horizon} barre. Calcolato solo su barre giornaliere complete. "
          "Paper trading: nessun ordine viene eseguito.</p>")
    b += "</div></body></html>"
    return subject, b


# ============================================================
#  MAIN ENTRY POINT
# ============================================================

def run_stable_scan(send_email=True):
    print("=" * 60)
    print("🔬 STABLE Strategy Scanner — Avvio scansione...")
    print("=" * 60)

    cfg = load_config()

    if not cfg.get("enabled", True):
        print("⚠️ STABLE alerts disabilitati.")
        return {"status": "disabled"}

    tickers = cfg.get("tickers", [])
    if not tickers:
        try:
            from tickers_loader import load_tickers
            tickers_map = load_tickers()
            tickers = list(tickers_map.keys())
            print(f"📋 Caricati {len(tickers)} tickers da tickers.js")
        except Exception as e:
            print(f"❌ Errore caricamento tickers: {e}")
            return {"status": "error", "message": str(e)}

    if not tickers:
        print("⚠️ Nessun ticker configurato.")
        return {"status": "no_tickers"}

    strategy = cfg.get("strategy", "STABLE")
    horizon = int(cfg.get("horizon", 21))
    price_sink = {} if cfg.get("forward_test", True) else None

    # il benchmark serve al forward test (confronto sulle stesse date)
    if price_sink is not None and strategy == "ARANCIONE":
        from forward_test import BENCHMARK
        if BENCHMARK not in tickers:
            tickers = list(tickers) + [BENCHMARK]

    result = compute_stable_signals(
        tickers=tickers,
        alpha=cfg.get("alpha", 200),
        start_date=None,  # auto: 6 mesi (STABLE) / 24 mesi (ARANCIONE/COMBO)
        mode=cfg.get("mode", "LONG"),
        entry_threshold=cfg.get("entry_threshold", 0.0),
        exit_threshold=cfg.get("exit_threshold", 0.0),
        max_workers=8,
        skip_partial_today=cfg.get("skip_partial_today", True),
        strategy=strategy,
        entry_z=cfg.get("entry_z", 2.0),
        horizon=horizon,
        price_sink=price_sink,
    )

    # --- FORWARD TEST: registra i segnali reali nel journal persistente ---
    # Il journal chiude a orizzonte fisso: è la regola dell'ARANCIONE. Per
    # STABLE/COMBO l'uscita dipende dallo slope, quindi un track record a
    # orizzonte fisso sarebbe fuorviante: non viene registrato.
    if price_sink is not None and strategy != "ARANCIONE":
        print(f"🧪 Forward test non registrato: supportato solo per ARANCIONE (strategia attuale {strategy})")
    elif price_sink is not None:
        try:
            from forward_test import (load_journal, save_journal,
                                      update_journal, journal_stats, journal_detail)
            journal = load_journal()
            # oggi + recenti (<5gg): se uno scan salta un giorno il segnale
            # non va perso. L'ingresso resta la prima barra dopo il segnale,
            # quindi registrarlo in ritardo non cambia il prezzo di carico.
            candidates = result["entries_today"] + result["entries_recent"]
            if not journal.get("runs"):
                # journal appena nato: si parte da zero, senza nulla di
                # retroattivo. Entrano solo i segnali dell'ultima seduta
                # chiusa (ancora da eseguire), non quelli dei giorni prima.
                candidates = [e for e in candidates if e.get("pending_execution")]
            new_signals = [{
                "ticker": e["ticker"], "signal_date": e["date"],
                "direction": e.get("direction", "LONG"),
                "strategy": strategy, "price": e.get("price"),
            } for e in candidates]
            update_journal(journal, price_sink, new_signals, horizon=horizon,
                           params=strategy_params(cfg),
                           universe=list(price_sink.keys()))
            save_journal(journal)
            result["forward_test"] = journal_stats(journal)
            result["forward_detail"] = journal_detail(journal)
            ft = result["forward_test"]
            print(f"🧪 Forward test: {ft['closed']} chiusi, media {ft['avg_pnl_pct']}%, "
                  f"semaforo {ft['verdict']} ({ft['verdict_reason']})")
        except Exception as e:
            print(f"⚠️ Forward test update fallito: {e}")

    if send_email:
        builder = build_orange_email if strategy == "ARANCIONE" else build_stable_email
        subject, body = builder(result)
        notifier = NotificationManager()
        recipient = cfg.get("recipient", "")
        if recipient:
            notifier.recipient = recipient
        notifier.send_email(subject, body)

    return {
        "status": "ok",
        "entries_today": len(result["entries_today"]),
        "entries_recent": len(result["entries_recent"]),
        "active": len(result["active"]),
        "errors": len(result["errors"]),
        "result": result,
    }


if __name__ == "__main__":
    run_stable_scan(send_email=True)
