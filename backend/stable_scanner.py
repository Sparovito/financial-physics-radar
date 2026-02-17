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
    "trigger_hour": 18,
    "trigger_minute": 0,
    "mode": "LONG",
    "entry_threshold": 0.0,
    "exit_threshold": 0.0,
    "alpha": 200,
    "start_date": "2023-01-01",
    "tickers": [],
    "preset": "all",
    "recipient": "",
}

def load_config():
    if os.path.exists(STABLE_CONFIG_PATH):
        try:
            with open(STABLE_CONFIG_PATH, "r") as f:
                cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg}
        except Exception as e:
            print(f"⚠️ Errore caricamento config STABLE: {e}")
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(STABLE_CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
        print(f"✅ Config STABLE salvata: {STABLE_CONFIG_PATH}")
        return True
    except Exception as e:
        print(f"❌ Errore salvataggio config STABLE: {e}")
        return False


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
#  SIGNAL COMPUTATION
# ============================================================

def compute_stable_signals(tickers, alpha=200, start_date=None, mode="LONG",
                            entry_threshold=0.0, exit_threshold=0.0, max_workers=8):
    """
    Compute STABLE strategy signals for all tickers.

    start_date: auto-calculated to 6 months ago (enough for EMA convergence).
    """
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")

    if not start_date:
        start_date = (today - datetime.timedelta(days=180)).strftime("%Y-%m-%d")

    entries_today = []
    entries_recent = []
    active_positions = []
    errors_list = []

    # --- PHASE 1: Download (reuses main.py system) ---
    print(f"🔬 STABLE Scanner: {len(tickers)} tickers (α={alpha}, mode={mode}, "
          f"entry>{entry_threshold}, exit<{exit_threshold}, from={start_date})")

    all_prices, failed = download_all_prices(tickers, start_date, max_workers=max_workers)
    errors_list = [{"ticker": t, "error": "Download fallito"} for t in failed]

    # --- PHASE 2: Compute signals (CPU-only) ---
    print(f"   🧮 Calcolo segnali per {len(all_prices)} tickers...")

    _lock = threading.Lock()

    def analyze_ticker(ticker, px):
        try:
            ema_span = max(5, int(alpha / 10))
            F_alpha = px.ewm(span=ema_span, adjust=False).mean()
            dF_alpha = F_alpha.diff().fillna(0)
            stable_slope = dF_alpha.ewm(span=14, adjust=False).mean()

            slopes = stable_slope.values
            prices_arr = px.values
            dates_arr = px.index
            n = len(slopes)

            if n < 10:
                return

            current_price = float(prices_arr[-1])
            current_slope = float(slopes[-1])

            # Full backtest to determine trade state + entry signal dates
            in_trade = False
            trade_entry_date = None
            trade_entry_price = None
            trade_direction = None
            entry_signals = []

            for i in range(1, n):
                s = float(slopes[i])
                s_prev = float(slopes[i-1])

                if mode in ("LONG", "BOTH"):
                    if not in_trade and s > entry_threshold and s_prev <= entry_threshold:
                        in_trade = True
                        trade_entry_date = dates_arr[i]
                        trade_entry_price = float(prices_arr[i])
                        trade_direction = "LONG"
                        entry_signals.append((i, "LONG"))
                    elif in_trade and trade_direction == "LONG" and s < exit_threshold and s_prev >= exit_threshold:
                        in_trade = False

                if mode in ("SHORT", "BOTH"):
                    if not in_trade and s < -entry_threshold and s_prev >= -entry_threshold:
                        in_trade = True
                        trade_entry_date = dates_arr[i]
                        trade_entry_price = float(prices_arr[i])
                        trade_direction = "SHORT"
                        entry_signals.append((i, "SHORT"))
                    elif in_trade and trade_direction == "SHORT" and s > -exit_threshold and s_prev <= -exit_threshold:
                        in_trade = False

            # Check recent entry signals (last 5 calendar days)
            for (idx, direction) in entry_signals:
                signal_date = dates_arr[idx]
                signal_date_py = signal_date.date() if hasattr(signal_date, 'date') else signal_date
                days_ago = (today - signal_date_py).days

                if days_ago < 0 or days_ago > 5:
                    continue

                signal_price = float(prices_arr[idx])
                signal_slope = float(slopes[idx])
                price_change_pct = ((current_price - signal_price) / signal_price) * 100 if signal_price > 0 else 0

                info = {
                    "ticker": ticker,
                    "price": signal_price,
                    "current_price": current_price,
                    "slope": signal_slope,
                    "price_change_since": price_change_pct,
                    "date": signal_date_py.strftime("%Y-%m-%d"),
                    "direction": direction,
                    "days_ago": days_ago,
                }

                with _lock:
                    if days_ago == 0:
                        entries_today.append(info)
                    else:
                        entries_recent.append(info)

            # Track active positions
            if in_trade and trade_entry_date is not None:
                pnl = 0.0
                if trade_entry_price and trade_entry_price > 0:
                    if trade_direction == "LONG":
                        pnl = ((current_price - trade_entry_price) / trade_entry_price) * 100
                    else:
                        pnl = ((trade_entry_price - current_price) / trade_entry_price) * 100

                entry_date_str = trade_entry_date.strftime("%Y-%m-%d") if hasattr(trade_entry_date, 'strftime') else str(trade_entry_date)

                with _lock:
                    active_positions.append({
                        "ticker": ticker,
                        "direction": trade_direction,
                        "entry_date": entry_date_str,
                        "entry_price": trade_entry_price or 0,
                        "current_price": current_price,
                        "pnl_pct": pnl,
                        "slope": current_slope,
                    })

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
            "n_tickers": len(tickers), "n_downloaded": len(all_prices), "date": today_str,
        }
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

    subject = f"🔬 STABLE: {n_today} ENTRY oggi, {n_recent} recenti ({today_str})"

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
    body += f"<b>Alpha:</b> {params['alpha']} &nbsp;|&nbsp; "
    body += f"<b>Mode:</b> {params['mode']} &nbsp;|&nbsp; "
    body += f"<b>Entry ></b> {params['entry_threshold']} &nbsp;|&nbsp; "
    body += f"<b>Exit <</b> {params['exit_threshold']} &nbsp;|&nbsp; "
    body += f"<b>Tickers:</b> {params['n_downloaded']}/{params['n_tickers']}"
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
        body += "<table><thead><tr><th>Ticker</th><th>Direzione</th><th>Prezzo Entry</th><th>Slope</th></tr></thead><tbody>"
        for e in entries_today:
            dir_badge = "badge-long" if e.get("direction") == "LONG" else "badge-short"
            body += f"<tr class='bg-green'><td><b>{e['ticker']}</b></td>"
            body += f"<td><span class='{dir_badge}'>{e.get('direction', 'LONG')}</span></td>"
            body += f"<td>${e['price']:.2f}</td>"
            body += f"<td class='text-purple'>{e['slope']:.4f}</td></tr>"
        body += "</tbody></table>"
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
            body += f"<tr class='bg-purple'><td><b>{p['ticker']}</b></td>"
            body += f"<td><span class='{dir_badge}'>{p.get('direction', 'LONG')}</span></td>"
            body += f"<td>{p['entry_date']} @ ${p['entry_price']:.2f}</td>"
            body += f"<td>${p['current_price']:.2f}</td>"
            body += f"<td class='{pnl_cls}'>{p['pnl_pct']:.2f}%</td></tr>"
        body += "</tbody></table>"

    if not entries_today and not entries_recent and not active:
        body += "<p style='font-size: 16px; color: #888; text-align: center; padding: 30px;'>Nessun segnale STABLE rilevato.</p>"

    n_err = len(errors)
    if n_err > 0:
        body += f"<p style='font-size: 11px; color: #bbb; margin-top: 20px;'>⚠️ {n_err} ticker non scaricati</p>"

    body += "<p style='font-size: 12px; color: #888; margin-top: 30px; border-top: 1px solid #eee; padding-top: 12px;'>"
    body += "Generato da <b>STABLE Strategy Lab</b> — Financial Physics AI</p>"
    body += "</div></body></html>"

    return subject, body


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

    result = compute_stable_signals(
        tickers=tickers,
        alpha=cfg.get("alpha", 200),
        start_date=None,  # auto: 6 mesi fa
        mode=cfg.get("mode", "LONG"),
        entry_threshold=cfg.get("entry_threshold", 0.0),
        exit_threshold=cfg.get("exit_threshold", 0.0),
        max_workers=8
    )

    if send_email:
        subject, body = build_stable_email(result)
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
