"""
Test per la strategia "SCARICO DEL POTENZIALE" (la linea arancione).

Regola (validata dall'event study 2026-07-05: dopo z_pot>2 con prezzo sotto
il fondamentale, ritorno medio a 10gg ~4x la baseline):
  - onset: z-score rolling del potenziale causale attraversa entry_z dal basso
           E prezzo < F (dislocazione al ribasso / panico)
  - posizione LONG per `horizon` barre (estesa se arriva un nuovo onset)
  - esecuzione t+1 e costi via motore unificato (backtest_stable)

Esecuzione: backend/venv/bin/python backend/tests/test_potential_discharge.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _dates(n, start="2023-01-02"):
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, periods=n, freq="B")]


def _base_scenario(n=400, spike_at=(300,), rising=False):
    """pot_raw COSTANTE con spike deterministici (niente rumore: gli onset
    devono avvenire solo dove li mettiamo); prezzi in discesa (prezzo<F)
    o in salita (prezzo>F)."""
    pot = np.ones(n)
    for s in spike_at:
        pot[s:s + 3] = 6.0  # spike netto -> z ben sopra 2
    if rising:
        prices = list(100 * (1.004 ** np.arange(n)))
    else:
        prices = list(100 * (0.998 ** np.arange(n)))  # discesa: prezzo < EMA20
    F = pd.Series(prices).ewm(span=20, adjust=False).mean().tolist()
    return _dates(n), prices, pot.tolist(), F


def test_entry_t1_and_horizon(backtest_potential_discharge):
    HOR = 21
    dates, prices, pot, F = _base_scenario(spike_at=(300,))
    res = backtest_potential_discharge(dates, prices, pot, F,
                                       entry_z=2.0, horizon=HOR,
                                       execution_lag=1, cost_pct=0.0)
    closed = [t for t in res["trades"] if t["exit_date"] != "OPEN"]
    assert len(closed) == 1, f"atteso 1 trade: {res['trades']}"
    tr = closed[0]
    assert tr["direction"] == "LONG"
    # onset alla barra 300 -> ingresso eseguito alla barra 301
    assert tr["entry_date"] == dates[301], f"entry {tr['entry_date']} != {dates[301]}"
    # exit: pos torna 0 alla barra 300+HOR -> esecuzione 300+HOR+1
    assert tr["exit_date"] == dates[300 + HOR + 1], (
        f"exit {tr['exit_date']} != {dates[300 + HOR + 1]}"
    )
    assert res["n_onsets"] == 1
    print(f"  OK entry t+1 ({tr['entry_date']}) e holding {HOR} barre ({tr['exit_date']})")


def test_no_entry_when_price_above_F(backtest_potential_discharge):
    dates, prices, pot, F = _base_scenario(spike_at=(300,), rising=True)
    res = backtest_potential_discharge(dates, prices, pot, F,
                                       entry_z=2.0, horizon=21)
    assert res["trades"] == [], f"spike col prezzo SOPRA F non deve entrare: {res['trades']}"
    assert res["n_onsets"] == 0
    print("  OK nessun ingresso su spike rialzista (prezzo > F)")


def test_extension_on_respike(backtest_potential_discharge):
    HOR = 21
    dates, prices, pot, F = _base_scenario(n=420, spike_at=(300, 310))
    res = backtest_potential_discharge(dates, prices, pot, F,
                                       entry_z=2.0, horizon=HOR)
    closed = [t for t in res["trades"] if t["exit_date"] != "OPEN"]
    assert len(closed) == 1, f"i due spike devono fondersi in un solo trade: {res['trades']}"
    tr = closed[0]
    # holding esteso: exit ~ 310 + HOR + 1
    assert tr["exit_date"] == dates[310 + HOR + 1], (
        f"exit {tr['exit_date']} != {dates[310 + HOR + 1]} (estensione mancata)"
    )
    assert res["n_onsets"] == 2
    print("  OK estensione su secondo spike (un solo trade, holding prolungato)")


def test_prefix_causality(backtest_potential_discharge):
    rng = np.random.default_rng(9)
    n = 500
    prices = (100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))).tolist()
    pot = (1 + np.abs(rng.normal(0, 1.2, n)) ** 2).tolist()
    F = pd.Series(prices).ewm(span=20, adjust=False).mean().tolist()
    dates = _dates(n)

    full = backtest_potential_discharge(dates, prices, pot, F, entry_z=2.0, horizon=21)
    cut = 350
    part = backtest_potential_discharge(dates[:cut], prices[:cut], pot[:cut], F[:cut],
                                        entry_z=2.0, horizon=21)
    err = max(abs(a - b) for a, b in zip(part["equity_curve"], full["equity_curve"][:cut]))
    assert err < 1e-9, f"NON CAUSALE: equity prefix cambia (max err {err})"
    print("  OK causalità (prefisso equity identico)")


def main():
    from stable_strategy import backtest_potential_discharge  # RED: non esiste

    test_entry_t1_and_horizon(backtest_potential_discharge)
    test_no_entry_when_price_above_F(backtest_potential_discharge)
    test_extension_on_respike(backtest_potential_discharge)
    test_prefix_causality(backtest_potential_discharge)
    print("OK test_potential_discharge — 4/4")


if __name__ == "__main__":
    main()
