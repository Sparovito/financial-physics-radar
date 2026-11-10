"""
Utilità condivise dagli script di ricerca (riproducibili: seme fisso).

Gli script in questa cartella NON fanno parte del runtime: rieseguono le
analisi su cui poggiano le scelte del progetto, così i numeri citati nella
documentazione si possono sempre ricalcolare.

    backend/venv/bin/python backend/research/orange_verification.py
    backend/venv/bin/python backend/research/oos_comparison.py
"""
import os
import sys
import json
import random
import datetime
import concurrent.futures

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.environ.setdefault("FPR_STORAGE", "local")

import numpy as np
import pandas as pd

from logic import MarketData, kalman_frozen_series
from stable_strategy import POTENTIAL_ALPHA, POTENTIAL_BETA

SEED = 42
COST = 0.05          # % per lato
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def sample_universe(target=120, seed=SEED):
    """Campione stratificato per categoria della lista ticker corrente.
    NOTA survivorship: la lista è quella di OGGI (i delistati mancano)."""
    from tickers_loader import load_tickers
    universe = load_tickers()
    by_cat = {}
    for sym, cat in universe.items():
        by_cat.setdefault(cat, []).append(sym)
    rnd = random.Random(seed)
    sample = set()
    for cat in sorted(by_cat):
        syms = sorted(by_cat[cat])
        k = max(1, round(target * len(syms) / len(universe)))
        sample.update(rnd.sample(syms, min(k, len(syms))))
    return sorted(sample), len(universe)


def fetch_prices(tickers, start, min_len=400, workers=6):
    def one(t):
        try:
            px = MarketData(t, start_date=start).fetch()
            return t, (px if len(px) >= min_len else None)
        except Exception:
            return t, None
    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for t, px in ex.map(one, tickers):
            if px is not None:
                out[t] = px
    return out


def orange_inputs(px):
    """Serie causali per la strategia arancione (parametri validati)."""
    dates = px.index.strftime("%Y-%m-%d").tolist()
    prices = [float(v) for v in px.values]
    fr = kalman_frozen_series(px, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA,
                              min_points=100, kin_lag=25)
    pot = ([float("nan")] * 100 + list(fr["pot_last"]))[:len(prices)]
    F = px.ewm(span=20, adjust=False).mean().values.tolist()
    return dates, prices, pot, F


def week_key(date_str):
    y, w, _ = datetime.date.fromisoformat(date_str).isocalendar()
    return f"{y}-W{w:02d}"


def tstat(values):
    v = np.asarray(values, dtype=float)
    if len(v) < 2 or v.std(ddof=1) == 0:
        return float("nan")
    return float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v))))


def cluster_stats(trades, n_boot=5000, seed=SEED):
    """trades: [(entry_date, pnl_pct)].
    I trade dello stesso panico non sono indipendenti: la significatività
    onesta si calcola a livello di cluster (settimana di ingresso).
    Ritorna t ingenuo, t sulle medie settimanali e l'intervallo bootstrap
    a blocchi (ricampionando le settimane) della media per trade."""
    pnls = np.array([p for _, p in trades], dtype=float)
    clusters = {}
    for d, p in trades:
        clusters.setdefault(week_key(d), []).append(p)
    keys = sorted(clusters)
    sums = np.array([sum(clusters[k]) for k in keys])
    counts = np.array([len(clusters[k]) for k in keys])
    means = sums / counts

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    boot = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {
        "n_trades": int(len(pnls)),
        "n_clusters": int(len(keys)),
        "mean_per_trade": round(float(pnls.mean()), 3),
        "t_naive": round(tstat(pnls), 2),
        "t_clustered": round(tstat(means), 2),
        "boot_ci95_mean_per_trade": [round(float(lo), 3), round(float(hi), 3)],
        "boot_p_mean_le_0": round(float((boot <= 0).mean()), 4),
        "largest_cluster_share": round(float(counts.max() / counts.sum()), 3),
    }


def simulate_sizing(trades, scheme="fixed", capital=100.0, stake_pct=10.0, cap=10):
    """Stessa logica (base realizzata) di frontend/stable_engine.js::simulateSizing.
    trades: [(entry_date, exit_date, pnl_pct)]."""
    events = []
    for i, (en, ex, pnl) in enumerate(trades):
        events.append((en, 1, i))
        events.append((ex, 0, i))
    events.sort()
    fixed = capital * stake_pct / 100
    cash, open_pos = capital, {}
    skipped, max_conc, peak, maxdd = 0, 0, capital, 0.0
    for date, kind, i in events:
        if kind == 0:
            if i not in open_pos:
                continue
            cash += open_pos.pop(i) * (1 + trades[i][2] / 100)
        else:
            invested = sum(open_pos.values())
            stake = (cash + invested) * stake_pct / 100 if scheme == "compound" else fixed
            if scheme != "fixed_unlimited" and (len(open_pos) >= cap or stake > cash + 1e-9):
                skipped += 1
                continue
            cash -= stake
            open_pos[i] = stake
            max_conc = max(max_conc, len(open_pos))
        equity = cash + sum(open_pos.values())
        peak = max(peak, equity)
        maxdd = max(maxdd, (peak - equity) / peak * 100)
    return {"return_pct": round((cash / capital - 1) * 100, 1), "max_dd": round(maxdd, 1),
            "skipped": skipped, "max_concurrent": max_conc}


def save_output(name, data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name)
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
    return path
