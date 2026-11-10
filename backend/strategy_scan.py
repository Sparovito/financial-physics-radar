"""
Calcolo dello SCANNER STRATEGIE (Massivo).

Per ogni titolo: buy & hold del periodo e, per ogni strategia, ROI, win rate,
numero di trade, esposizione e alpha (ROI − esposizione × B&H): il confronto
che dice se il timing ha aggiunto qualcosa rispetto a stare semplicemente
investiti per la stessa frazione di tempo.

Stesse formule di /analyze (LIVE, FROZEN, SUM, STABLE) più ARANCIONE e COMBO,
ma senza Fourier, ZigZag orario e serie per i grafici: allo scanner non servono.
Senza costi di transazione, come le strategie della dashboard.

Nota di lettura: è una descrizione del passato. Il rendimento passato di una
strategia su un titolo non prevede quello futuro (research/scanner_persistence.py).
"""
import datetime
import threading
import concurrent.futures

import pandas as pd

from logic import (ActionPath, backtest_strategy, kalman_frozen_series, causal_lowpass)
from stable_strategy import (backtest_stable, backtest_potential_discharge, backtest_combo,
                             POTENTIAL_ALPHA, POTENTIAL_BETA)

WARMUP_DAYS = 560          # giorni di calendario scaricati prima dell'inizio periodo
MIN_BARS = 160
ZWIN = 252


def _zroll(values, min_periods=20):
    s = pd.Series(values, dtype=float)
    return ((s - s.rolling(ZWIN, min_periods=min_periods).mean())
            / (s.rolling(ZWIN, min_periods=min_periods).std() + 1e-6)).fillna(0)


def _exposure(trades, dates, lo, hi):
    """% di barre del periodo [lo, hi] con una posizione aperta."""
    idx = {d: i for i, d in enumerate(dates)}
    covered = set()
    for t in trades:
        a = idx.get(t["entry_date"])
        b = hi if t["exit_date"] == "OPEN" else idx.get(t["exit_date"])
        if a is None or b is None:
            continue
        covered.update(range(max(a, lo), min(b, hi) + 1))
    n = hi - lo + 1
    return round(len(covered) / n * 100, 1) if n > 0 else 0.0


def _slim(trades):
    return [{"entry_date": t["entry_date"], "exit_date": t["exit_date"],
             "direction": t.get("direction", "LONG"),
             "entry_price": t.get("entry_price"), "exit_price": t.get("exit_price"),
             "pnl_pct": t.get("pnl_pct")} for t in trades]


def scan_one(px, start_date, end_date=None, alpha=200.0, beta=1.0, entry_z=2.0, horizon=21):
    """px: serie di chiusure CON la storia di warmup prima di start_date."""
    if end_date:
        px = px[px.index <= pd.Timestamp(end_date)]
    if len(px) < MIN_BARS:
        raise ValueError(f"storia insufficiente ({len(px)} barre, ne servono {MIN_BARS})")

    dates = px.index.strftime("%Y-%m-%d").tolist()
    prices = [float(v) for v in px.values]
    lo = next((i for i, d in enumerate(dates) if d >= start_date), None)
    hi = len(dates) - 1
    if lo is None or hi - lo < 20:
        raise ValueError("storia insufficiente nel periodo richiesto")

    bh = (prices[hi] / prices[lo] - 1) * 100
    trend = "up" if bh > 15 else ("down" if bh < -15 else "stable")
    kw = {"start_date": start_date, "end_date": end_date}
    out, trades_out = {}, {}

    def put(name, res, expo=None):
        st = res["stats"]
        trades = res["trades"]
        closed = [t for t in trades if t["exit_date"] != "OPEN"]
        wins = sum(1 for t in closed if (t.get("pnl_pct") or 0) > 0)
        e = expo if expo is not None else _exposure(trades, dates, lo, hi)
        roi = float(st["total_return"])
        out[name] = {
            "roi": round(roi, 2),
            "win_rate": round(wins / len(closed) * 100, 1) if closed else 0.0,   # solo trade chiusi
            "trades": len(closed),
            "expo": e,
            "alpha": round(roi - e / 100 * bh, 2),
        }
        trades_out[name] = _slim(trades)

    # --- LIVE: smoother bidirezionale = ORACOLO (conosce il futuro del periodo) ---
    mech = ActionPath(px, alpha=alpha, beta=beta)
    z_kin = _zroll(mech.kin_density.values).tolist()
    z_slope = _zroll(mech.dX.values).tolist()
    put("live", backtest_strategy(prices=prices, z_kinetic=z_kin, z_slope=z_slope, dates=dates, **kw))

    # --- FROZEN / SUM: serie point-in-time (Kalman), come /analyze ---
    fr = kalman_frozen_series(px, alpha=alpha, beta=beta, min_points=100, kin_lag=25)
    pad = len(prices) - len(fr["pot_last"])
    z_pot = _zroll([0] * pad + [round(v, 2) for v in fr["pot_last"]]).tolist()
    put("frozen", backtest_strategy(prices=prices, z_kinetic=z_pot, z_slope=z_slope, dates=dates,
                                    use_z_roc=True, **kw))
    z_sum_raw = _zroll([k + p for k, p in zip(fr["kin_last"], fr["pot_last"])]).tolist()
    z_sum = [-999] * pad + [round(x, 2) for x in causal_lowpass(z_sum_raw)]
    put("sum", backtest_strategy(prices=prices, z_kinetic=z_sum, z_slope=z_slope, dates=dates,
                                 threshold=-0.3, use_z_roc=True, **kw))

    # --- STABLE: slope causale, motore unificato (LONG, soglie 0/0, t+1) ---
    span = max(5, int(alpha / 10))
    slope = px.ewm(span=span, adjust=False).mean().diff().fillna(0).ewm(span=14, adjust=False).mean().values.tolist()
    res = backtest_stable(dates, prices, slope, mode="LONG", execution_lag=1, cost_pct=0.0, **kw)
    put("stable", res, expo=res["stats"]["exposure_pct"])

    # --- ARANCIONE / COMBO: potenziale con i parametri validati ---
    if alpha == POTENTIAL_ALPHA and beta == POTENTIAL_BETA:
        fo = fr
    else:
        fo = kalman_frozen_series(px, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA, min_points=100, kin_lag=25)
    pot = ([float("nan")] * 100 + list(fo["pot_last"]))[:len(prices)]
    F20 = px.ewm(span=20, adjust=False).mean().values.tolist()
    res = backtest_potential_discharge(dates, prices, pot, F20, entry_z=entry_z, horizon=horizon,
                                       execution_lag=1, cost_pct=0.0, **kw)
    put("orange", res, expo=res["stats"]["exposure_pct"])
    res = backtest_combo(dates, prices, slope, pot, F20, entry_z=entry_z, horizon=horizon,
                         execution_lag=1, cost_pct=0.0, **kw)
    put("combo", res, expo=res["stats"]["exposure_pct"])

    return {
        "bh": round(bh, 2), "trend": trend, "n_bars": hi - lo + 1,
        "first_date": dates[lo], "last_date": dates[hi], "last_price": round(prices[hi], 4),
        "strategies": out, "trades": trades_out,
    }


# ---------- prezzi: cache limitata a un giorno ----------
_cache = {"key": None, "data": {}}
_cache_lock = threading.Lock()


def fetch_prices_cached(tickers, start, fetch_fn, day=None, max_workers=8):
    """Scarica (una volta al giorno per titolo e data di inizio) le serie.
    La cache viene buttata quando cambia il giorno o l'inizio: su un server
    sempre acceso non restano prezzi vecchi e la memoria non cresce."""
    day = day or datetime.date.today().strftime("%Y-%m-%d")
    key = (day, start)
    with _cache_lock:
        if _cache["key"] != key:
            _cache["key"], _cache["data"] = key, {}
        data = _cache["data"]
        missing = [t for t in tickers if t not in data]

    failed = {}

    def one(t):
        try:
            return t, fetch_fn(t, start), None
        except Exception as e:
            return t, None, str(e)

    if missing:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(missing)))) as ex:
            for t, px, err in ex.map(one, missing):
                if px is not None and len(px) > 0:
                    with _cache_lock:
                        data[t] = px
                else:
                    failed[t] = err or "nessun dato"
    return {t: data[t] for t in tickers if t in data}, failed
