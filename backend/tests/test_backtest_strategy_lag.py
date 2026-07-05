"""
Test esecuzione t+1 per il backtest_strategy legacy (LIVE/FROZEN/SUM/MA).

Problema: il segnale è calcolato sul close della barra i e l'ingresso
avveniva allo STESSO close — nella realtà si esegue al più la barra dopo.
Fix: parametro execution_lag (default 1). execution_lag=0 riproduce il
vecchio comportamento same-bar.

Esecuzione: backend/venv/bin/python backend/tests/test_backtest_strategy_lag.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd


def _dates(n, start="2024-01-01"):
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, periods=n, freq="B")]


def main():
    from logic import backtest_strategy

    dates = _dates(10)
    prices = [100, 101, 102, 103, 104, 105, 106, 105, 104, 103]
    #        segnale ON alla barra 2 (z>0), OFF alla barra 6
    z_kin = [-1, -1, 1, 1, 1, 1, -1, -1, -1, -1]
    z_slope = [1] * 10  # direzione LONG

    # --- default: esecuzione t+1 ---
    res = backtest_strategy(prices=prices, z_kinetic=z_kin, z_slope=z_slope,
                            dates=dates)
    closed = [t for t in res["trades"] if t["exit_date"] != "OPEN"]
    assert len(closed) == 1, f"atteso 1 trade: {res['trades']}"
    tr = closed[0]
    assert tr["entry_price"] == 103, (
        f"entry t+1 attesa 103 (segnale barra 2, exec barra 3), trovata {tr['entry_price']}"
    )
    assert tr["entry_date"] == dates[3]
    assert tr["exit_price"] == 105, f"exit t+1 attesa 105, trovata {tr['exit_price']}"
    assert tr["exit_date"] == dates[7]

    # --- legacy: execution_lag=0 riproduce il same-bar ---
    res0 = backtest_strategy(prices=prices, z_kinetic=z_kin, z_slope=z_slope,
                             dates=dates, execution_lag=0)
    tr0 = [t for t in res0["trades"] if t["exit_date"] != "OPEN"][0]
    assert tr0["entry_price"] == 102, f"legacy same-bar attesa 102, trovata {tr0['entry_price']}"
    assert tr0["exit_price"] == 106

    # --- curve mode (MA strategy): direzione decisa sulla barra del segnale ---
    curve = [101.5] * 10  # prezzo sopra la curva dalla barra 2 in poi
    res_c = backtest_strategy(prices=prices, z_kinetic=z_kin, z_slope=[],
                              dates=dates, trend_mode='PRICE_VS_CURVE',
                              trend_curve=curve)
    tr_c = res_c["trades"][0]
    assert tr_c["direction"] == "LONG"
    assert tr_c["entry_price"] == 103, f"curve mode entry t+1 attesa 103: {tr_c}"

    print("OK test_backtest_strategy_lag — t+1 default, lag=0 legacy, curve mode coerente")


if __name__ == "__main__":
    main()
