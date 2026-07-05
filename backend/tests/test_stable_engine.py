"""
Test del motore STABLE unificato (backend/stable_strategy.py).

Unifica le 3 implementazioni divergenti (main.py Strategia 5, Lab JS,
stable_scanner.py) con semantica unica:
- segnale valutato sulla barra j, ESECUZIONE al close della barra j+execution_lag
- LONG:  entry slope > entry_th, exit slope < exit_th
- SHORT: entry slope < -entry_th, exit slope > -exit_th (soglie SPECULARI)
- BOTH:  due leg paralleli indipendenti
- costi per lato (cost_pct in %), win rate SOLO sui trade chiusi
- stats estese: max_drawdown, profit_factor, exposure_pct, sharpe, buy_hold_return
- signal_events: include segnali PENDENTI (senza barra di esecuzione disponibile)

Esecuzione: backend/venv/bin/python backend/tests/test_stable_engine.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np


def _dates(n, start="2024-01-01"):
    import pandas as pd
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, periods=n, freq="B")]


def test_t_plus_1_execution(backtest_stable):
    dates = _dates(10)
    prices = [100, 101, 102, 103, 104, 105, 106, 105, 104, 103]
    slopes = [-1, -1, 1, 1, 1, 1, -1, -1, -1, -1]

    res = backtest_stable(dates, prices, slopes, mode="LONG",
                          entry_th=0.0, exit_th=0.0, execution_lag=1, cost_pct=0.0)
    closed = [t for t in res["trades"] if t["exit_date"] != "OPEN"]
    assert len(closed) == 1, f"attesi 1 trade chiuso, trovati {len(closed)}"
    tr = closed[0]
    # Segnale alla barra 2 (slope 1>0) -> esecuzione al close della barra 3
    assert tr["entry_price"] == 103, f"entry t+1 attesa 103, trovata {tr['entry_price']}"
    assert tr["entry_date"] == dates[3]
    # Segnale exit alla barra 6 -> esecuzione barra 7
    assert tr["exit_price"] == 105, f"exit t+1 attesa 105, trovata {tr['exit_price']}"
    assert tr["exit_date"] == dates[7]
    exp_pnl = (105 / 103 - 1) * 100
    assert abs(tr["pnl_pct"] - round(exp_pnl, 2)) < 0.011

    # Controllo: con lag=0 entrerebbe alla barra del segnale (102)
    res0 = backtest_stable(dates, prices, slopes, mode="LONG",
                           entry_th=0.0, exit_th=0.0, execution_lag=0, cost_pct=0.0)
    assert res0["trades"][0]["entry_price"] == 102

    # Buy & hold e exposure
    bh = res["stats"]["buy_hold_return"]
    assert abs(bh - 3.0) < 0.011, f"buy&hold atteso 3%, trovato {bh}"
    expo = res["stats"]["exposure_pct"]
    assert 30 <= expo <= 50, f"exposure attesa ~40%, trovata {expo}"
    print(f"  OK t+1 execution (pnl {tr['pnl_pct']}%, B&H {bh}%, expo {expo}%)")


def test_costs(backtest_stable):
    dates = _dates(10)
    prices = [100, 101, 102, 103, 104, 105, 106, 105, 104, 103]
    slopes = [-1, -1, 1, 1, 1, 1, -1, -1, -1, -1]

    res_free = backtest_stable(dates, prices, slopes, mode="LONG", execution_lag=1)
    res_cost = backtest_stable(dates, prices, slopes, mode="LONG",
                               execution_lag=1, cost_pct=0.1)
    pnl_free = res_free["trades"][0]["pnl_pct"]
    pnl_cost = res_cost["trades"][0]["pnl_pct"]
    c = 0.001
    exp = ((105 * (1 - c) - 103 * (1 + c)) / (103 * (1 + c))) * 100
    assert pnl_cost < pnl_free, "i costi devono ridurre il pnl"
    assert abs(pnl_cost - round(exp, 2)) < 0.011, f"pnl con costi {pnl_cost} != atteso {exp:.4f}"
    print(f"  OK costi (senza: {pnl_free}%, con 0.1%/lato: {pnl_cost}%)")


def test_short_mirror(backtest_stable):
    dates = _dates(8)
    prices = [100, 99, 98, 97, 96, 97, 98, 99]
    slopes = [0, -0.5, -0.5, -0.1, 0, 0, 0, 0]

    res = backtest_stable(dates, prices, slopes, mode="SHORT",
                          entry_th=0.3, exit_th=0.2, execution_lag=1)
    closed = [t for t in res["trades"] if t["exit_date"] != "OPEN"]
    assert len(closed) == 1, f"atteso 1 trade SHORT, trovati {len(closed)}: {res['trades']}"
    tr = closed[0]
    assert tr["direction"] == "SHORT"
    # entry: slope[1]=-0.5 < -0.3 -> exec barra 2 (98)
    assert tr["entry_price"] == 98, f"entry short attesa 98, trovata {tr['entry_price']}"
    # exit: slope[3]=-0.1 > -0.2 -> exec barra 4 (96)
    assert tr["exit_price"] == 96
    exp = (98 - 96) / 98 * 100
    assert abs(tr["pnl_pct"] - round(exp, 2)) < 0.011
    print(f"  OK SHORT speculare (entry<-0.3, exit>-0.2, pnl {tr['pnl_pct']}%)")


def test_both_parallel(backtest_stable):
    dates = _dates(5)
    prices = [100, 101, 102, 103, 104]
    slopes = [0.0] * 5
    # entry_th=-0.5: LONG entra (0 > -0.5) e SHORT entra (0 < +0.5) in parallelo
    res = backtest_stable(dates, prices, slopes, mode="BOTH",
                          entry_th=-0.5, exit_th=-99, execution_lag=1)
    trades = res["trades"]
    assert len(trades) == 2, f"attesi 2 trade paralleli, trovati {len(trades)}"
    dirs = {t["direction"] for t in trades}
    assert dirs == {"LONG", "SHORT"}, f"direzioni: {dirs}"
    assert all(t["exit_date"] == "OPEN" for t in trades), "entrambi dovrebbero essere OPEN"
    print("  OK BOTH: LONG e SHORT aperti in parallelo")


def test_win_rate_closed_only(backtest_stable):
    dates = _dates(10)
    # 1 trade chiuso vincente (entry 101 -> exit 112) + 1 aperto in perdita
    # (entry 99, ultimo prezzo 90) -> win rate 100%
    prices = [100, 100, 101, 105, 110, 112, 100, 99, 95, 90]
    slopes = [-1, 1, 1, 1, -1, -1, 1, 1, 1, 1]
    res = backtest_stable(dates, prices, slopes, mode="LONG", execution_lag=1)
    closed = [t for t in res["trades"] if t["exit_date"] != "OPEN"]
    opened = [t for t in res["trades"] if t["exit_date"] == "OPEN"]
    assert len(closed) == 1 and len(opened) == 1, f"{res['trades']}"
    assert closed[0]["pnl_pct"] > 0
    assert opened[0]["pnl_pct"] < 0
    assert res["stats"]["win_rate"] == 100.0, (
        f"win rate deve escludere il trade OPEN: {res['stats']['win_rate']}"
    )
    assert res["stats"]["total_trades"] == 1
    print("  OK win rate solo sui chiusi (OPEN in perdita escluso)")


def test_no_lookahead_prefix(backtest_stable):
    rng = np.random.default_rng(9)
    n = 300
    prices = (100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, n)))).tolist()
    slopes = np.convolve(np.diff([100] + prices), np.ones(10) / 10, mode="same").tolist()
    dates = _dates(n)

    full = backtest_stable(dates, prices, slopes, mode="BOTH",
                           entry_th=0.05, exit_th=0.02, execution_lag=1, cost_pct=0.05)
    cut = 200
    part = backtest_stable(dates[:cut], prices[:cut], slopes[:cut], mode="BOTH",
                           entry_th=0.05, exit_th=0.02, execution_lag=1, cost_pct=0.05)

    # Equity: il prefisso non deve cambiare
    max_err = max(abs(a - b) for a, b in zip(part["equity_curve"], full["equity_curve"][:cut]))
    assert max_err < 1e-9, f"NON CAUSALE: equity prefix cambia (max {max_err})"

    # Trade chiusi entro il cut: identici
    f_closed = [t for t in full["trades"] if t["exit_date"] != "OPEN" and t["exit_date"] < dates[cut]]
    p_closed = [t for t in part["trades"] if t["exit_date"] != "OPEN"]
    assert f_closed == p_closed, "i trade chiusi nel prefisso differiscono"
    print(f"  OK no-lookahead ({len(p_closed)} trade nel prefisso identici)")


def test_pending_signal_events(backtest_stable):
    dates = _dates(6)
    prices = [100, 100, 100, 100, 100, 100]
    slopes = [-1, -1, -1, -1, -1, 1]  # segnale LONG sull'ULTIMA barra
    res = backtest_stable(dates, prices, slopes, mode="LONG", execution_lag=1)
    assert res["trades"] == [], "nessun trade deve essere aperto (esecuzione domani)"
    pend = [e for e in res["signal_events"] if e["type"] == "ENTRY" and e["exec_date"] is None]
    assert len(pend) == 1, f"atteso 1 segnale pendente: {res['signal_events']}"
    assert pend[0]["signal_date"] == dates[5]
    assert pend[0]["direction"] == "LONG"
    print("  OK segnale ENTRY pendente sull'ultima barra (exec_date=None)")


def test_date_filter(backtest_stable):
    dates = _dates(10)
    prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    slopes = [1] * 10
    res = backtest_stable(dates, prices, slopes, mode="LONG", execution_lag=1,
                          start_date=dates[4], end_date=dates[8])
    # Prima dello start: equity 0, nessun trade
    assert all(v == 0 for v in res["equity_curve"][:4])
    tr = res["trades"][0]
    assert tr["entry_date"] >= dates[4], f"entry {tr['entry_date']} prima dello start"
    # B&H calcolato solo nel range
    exp_bh = (prices[8] / prices[4] - 1) * 100
    assert abs(res["stats"]["buy_hold_return"] - round(exp_bh, 2)) < 0.011
    print("  OK filtro date (equity 0 fuori range, B&H nel range)")


def main():
    from stable_strategy import backtest_stable  # RED: modulo non esiste ancora

    test_t_plus_1_execution(backtest_stable)
    test_costs(backtest_stable)
    test_short_mirror(backtest_stable)
    test_both_parallel(backtest_stable)
    test_win_rate_closed_only(backtest_stable)
    test_no_lookahead_prefix(backtest_stable)
    test_pending_signal_events(backtest_stable)
    test_date_filter(backtest_stable)
    print("OK test_stable_engine — 8/8 scenari")


if __name__ == "__main__":
    main()
