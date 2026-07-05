"""
FORWARD TEST — paper trading "da oggi in poi".

A ogni scan giornaliero i segnali REALI vengono registrati in un journal
persistente; gli ingressi si riempiono alla prima barra successiva al
segnale (esecuzione t+1, come nei backtest), le uscite scattano dopo
`horizon` barre, il P&L usa la stessa formula con costi del motore
unificato. Il track record è a QUOTA FISSA (ogni trade pesa 1): le
statistiche restano confrontabili trade per trade, senza path-dependence —
la scelta giusta per la fase di misura (il compounding si valuta dopo,
quando il track record è validato).

Il journal è ricostruibile e onesto: nessun valore viene mai riscritto
retroattivamente; pending -> open -> closed è a senso unico.
"""
import os
import json
import datetime

from stable_strategy import _pnl_frac

JOURNAL_PATH = os.path.join(os.path.dirname(__file__), "forward_test_journal.json")


def load_journal(path=None):
    p = path or JOURNAL_PATH
    if os.path.exists(p):
        try:
            with open(p, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Journal illeggibile ({e}): ne creo uno nuovo")
    return {
        "created": datetime.date.today().strftime("%Y-%m-%d"),
        "config": {},
        "trades": [],
    }


def save_journal(journal, path=None):
    p = path or JOURNAL_PATH
    with open(p, "w") as f:
        json.dump(journal, f, indent=1)


def _trade_id(ticker, signal_date):
    return f"{ticker}|{signal_date}"


def update_journal(journal, price_series, new_signals, horizon,
                   cost_pct=0.05, today=None):
    """
    price_series: {ticker: (dates: list[str], closes: list[float])} —
                  solo barre COMPLETE (lo scanner scarta già la parziale).
    new_signals:  [{ticker, signal_date, direction, strategy, ...}] —
                  i segnali ENTRY del giorno (da compute_stable_signals).
    horizon:      barre di holding (dalla barra di ingresso).
    """
    existing = {t["id"] for t in journal["trades"]}
    c = float(cost_pct)

    # 1. nuovi segnali -> pending (mai duplicati)
    for sig in new_signals:
        tid = _trade_id(sig["ticker"], sig["signal_date"])
        if tid in existing:
            continue
        journal["trades"].append({
            "id": tid,
            "ticker": sig["ticker"],
            "strategy": sig.get("strategy", ""),
            "direction": sig.get("direction", "LONG"),
            "signal_date": sig["signal_date"],
            "signal_price": sig.get("price"),
            "status": "pending",
            "entry_date": None, "entry_price": None,
            "bars_held": 0,
            "exit_date": None, "exit_price": None,
            "pnl_pct": None,
            "current_price": None, "current_pnl_pct": None,
            "horizon": int(horizon),
            "cost_pct": c,
            "recorded_at": (today or datetime.date.today().strftime("%Y-%m-%d")),
        })
        existing.add(tid)

    # 2. avanzamento pending/open con i prezzi disponibili
    for tr in journal["trades"]:
        if tr["status"] == "closed":
            continue
        series = price_series.get(tr["ticker"])
        if not series:
            continue
        dates, closes = series
        hor = int(tr.get("horizon", horizon))
        tc = float(tr.get("cost_pct", c))

        if tr["status"] == "pending":
            # entry = prima barra COMPLETA successiva alla data del segnale
            entry_idx = next((i for i, d in enumerate(dates) if d > tr["signal_date"]), None)
            if entry_idx is None:
                continue
            tr["status"] = "open"
            tr["entry_date"] = dates[entry_idx]
            tr["entry_price"] = float(closes[entry_idx])

        if tr["status"] == "open":
            try:
                entry_idx = dates.index(tr["entry_date"])
            except ValueError:
                continue  # storia non copre l'entry (finestra diversa): riprova domani
            last_idx = len(dates) - 1
            exit_idx = entry_idx + hor
            if last_idx >= exit_idx:
                tr["status"] = "closed"
                tr["exit_date"] = dates[exit_idx]
                tr["exit_price"] = float(closes[exit_idx])
                tr["pnl_pct"] = round(_pnl_frac(tr["direction"], tr["entry_price"],
                                                tr["exit_price"], tc / 100.0) * 100, 2)
                tr["bars_held"] = hor
                tr["current_price"] = tr["exit_price"]
                tr["current_pnl_pct"] = tr["pnl_pct"]
            else:
                tr["bars_held"] = last_idx - entry_idx
                tr["current_price"] = float(closes[last_idx])
                tr["current_pnl_pct"] = round(_pnl_frac(tr["direction"], tr["entry_price"],
                                                        tr["current_price"], tc / 100.0) * 100, 2)
    return journal


def journal_stats(journal):
    trades = journal.get("trades", [])
    closed = [t for t in trades if t["status"] == "closed"]
    open_t = [t for t in trades if t["status"] == "open"]
    pending = [t for t in trades if t["status"] == "pending"]
    pnls = [t["pnl_pct"] for t in closed if t["pnl_pct"] is not None]
    wins = sum(1 for p in pnls if p > 0)
    open_pnls = [t["current_pnl_pct"] for t in open_t if t["current_pnl_pct"] is not None]
    return {
        "created": journal.get("created"),
        "total": len(trades),
        "pending": len(pending),
        "open": len(open_t),
        "closed": len(closed),
        "sum_pnl_pct": round(sum(pnls), 2) if pnls else 0.0,
        "avg_pnl_pct": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        "win_rate": round(wins / len(pnls) * 100, 1) if pnls else 0.0,
        "open_avg_pnl_pct": round(sum(open_pnls) / len(open_pnls), 2) if open_pnls else 0.0,
    }
