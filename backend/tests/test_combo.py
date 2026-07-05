"""
Test per la strategia COMBO: trend STABLE (core) + Scarico del Potenziale
(satellite). Posizione = OR dei due segnali, eseguita dal motore unificato.

Evidenza OOS 2026-07-05: Sharpe 0.33 -> 0.44 vs trend da solo, drawdown
invariato, robusto su tutta la griglia dei parametri del satellite.

Esecuzione: backend/venv/bin/python backend/tests/test_combo.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _dates(n, start="2023-01-02"):
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, periods=n, freq="B")]


def _falling_prices(n):
    prices = list(100 * (0.998 ** np.arange(n)))
    F = pd.Series(prices).ewm(span=20, adjust=False).mean().tolist()
    return prices, F


def test_union_discharge_only(backtest_combo):
    """Trend sempre fuori (slope<0): la combo deve coincidere col satellite."""
    n = 400
    dates = _dates(n)
    prices, F = _falling_prices(n)
    slopes = [-1.0] * n
    pot = np.ones(n); pot[300:303] = 6.0

    res = backtest_combo(dates, prices, slopes, pot.tolist(), F,
                         entry_th=0.0, exit_th=0.0, entry_z=2.0, horizon=21,
                         execution_lag=1, cost_pct=0.0)
    closed = [t for t in res["trades"] if t["exit_date"] != "OPEN"]
    assert len(closed) == 1, f"atteso 1 trade dal satellite: {res['trades']}"
    assert closed[0]["entry_date"] == dates[301]
    assert closed[0]["exit_date"] == dates[300 + 21 + 1]
    assert res["n_onsets"] == 1
    print("  OK trend fuori -> combo = solo satellite (entry t+1, holding 21)")


def test_trend_hysteresis(backtest_combo):
    """Leg trend con isteresi: tra exit_th e entry_th la posizione resta."""
    n = 60
    dates = _dates(n)
    prices = [100.0] * n
    F = [100.0] * n
    pot = [1.0] * n  # satellite mai attivo
    slopes = [0.0] * n
    # sale sopra entry(0.1) alla barra 10, scende a 0.05 (zona isteresi) alle
    # barre 20-29, sotto exit(0.0) alla barra 40
    for i in range(10, 20): slopes[i] = 0.2
    for i in range(20, 30): slopes[i] = 0.05
    for i in range(30, 40): slopes[i] = 0.2
    for i in range(40, n): slopes[i] = -0.1

    res = backtest_combo(dates, prices, slopes, pot, F,
                         entry_th=0.1, exit_th=0.0, entry_z=2.0, horizon=21)
    closed = [t for t in res["trades"] if t["exit_date"] != "OPEN"]
    assert len(closed) == 1, f"l'isteresi deve tenere UN solo trade: {res['trades']}"
    tr = closed[0]
    assert tr["entry_date"] == dates[11], f"entry {tr['entry_date']} != {dates[11]}"
    assert tr["exit_date"] == dates[41], f"exit {tr['exit_date']} != {dates[41]}"
    print("  OK isteresi trend (0.05 tra exit 0 ed entry 0.1 non chiude)")


def test_union_merges_legs(backtest_combo):
    """Trend attivo 100-340, satellite 330-350: UN solo trade continuo."""
    n = 420
    dates = _dates(n)
    prices, F = _falling_prices(n)
    slopes = [-1.0] * n
    for i in range(100, 341):
        slopes[i] = 1.0
    pot = np.ones(n); pot[330:333] = 6.0

    res = backtest_combo(dates, prices, slopes, pot.tolist(), F,
                         entry_th=0.0, exit_th=0.0, entry_z=2.0, horizon=21)
    closed = [t for t in res["trades"] if t["exit_date"] != "OPEN"]
    assert len(closed) == 1, f"i due leg devono fondersi in un trade: {res['trades']}"
    tr = closed[0]
    assert tr["entry_date"] == dates[101]
    # pos: trend fino a 340, satellite fino a 330+21-1=350 -> ultimo pos=1 a 350,
    # decisione barra 351 (pos=0) -> exit eseguito barra 352
    assert tr["exit_date"] == dates[352], f"exit {tr['exit_date']} != {dates[352]}"
    print("  OK fusione dei leg (trade unico esteso dal satellite)")


def test_prefix_causality(backtest_combo):
    rng = np.random.default_rng(4)
    n = 500
    prices = (100 * np.exp(np.cumsum(rng.normal(0, 0.014, n)))).tolist()
    F = pd.Series(prices).ewm(span=20, adjust=False).mean().tolist()
    slopes = pd.Series(prices).diff().ewm(span=10, adjust=False).mean().fillna(0).tolist()
    pot = (1 + np.abs(rng.normal(0, 1.1, n)) ** 2).tolist()
    dates = _dates(n)

    full = backtest_combo(dates, prices, slopes, pot, F,
                          entry_th=0.0, exit_th=0.0, entry_z=2.0, horizon=21,
                          cost_pct=0.05)
    cut = 360
    part = backtest_combo(dates[:cut], prices[:cut], slopes[:cut], pot[:cut], F[:cut],
                          entry_th=0.0, exit_th=0.0, entry_z=2.0, horizon=21,
                          cost_pct=0.05)
    err = max(abs(a - b) for a, b in zip(part["equity_curve"], full["equity_curve"][:cut]))
    assert err < 1e-9, f"NON CAUSALE (max err {err})"
    print("  OK causalità (prefisso equity identico)")


def main():
    from stable_strategy import backtest_combo  # RED: non esiste ancora

    test_union_discharge_only(backtest_combo)
    test_trend_hysteresis(backtest_combo)
    test_union_merges_legs(backtest_combo)
    test_prefix_causality(backtest_combo)
    print("OK test_combo — 4/4")


if __name__ == "__main__":
    main()
