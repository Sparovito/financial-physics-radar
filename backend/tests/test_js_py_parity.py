"""
Test di parità tra il motore Python (backend/stable_strategy.py) e la sua
replica JavaScript (frontend/stable_engine.js) usata dallo STABLE Lab.

Le tre implementazioni storiche della strategia (backend, Lab JS, scanner)
divergevano in semantica: questo test blocca ogni nuova divergenza.

Esecuzione: backend/venv/bin/python backend/tests/test_js_py_parity.py
(richiede node nel PATH)
"""
import sys
import os
import json
import subprocess
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

TOL = 0.011  # entrambi i motori arrotondano a 2 decimali


def _make_series(seed, n=350):
    rng = np.random.default_rng(seed)
    prices = (100 * np.exp(np.cumsum(rng.normal(0.0004, 0.014, n)))).round(4).tolist()
    slopes = np.convolve(np.diff([prices[0]] + prices),
                         np.ones(8) / 8, mode="same").round(6).tolist()
    dates = [d.strftime("%Y-%m-%d") for d in pd.date_range("2023-01-02", periods=n, freq="B")]
    return {"dates": dates, "prices": prices, "slopes": slopes}


def _compare_run(idx, py, js):
    # equity e trade_pnl
    assert len(py["equity_curve"]) == len(js["equity_curve"]), f"run {idx}: len equity"
    for k, (a, b) in enumerate(zip(py["equity_curve"], js["equity_curve"])):
        assert abs(a - b) <= TOL, f"run {idx}: equity[{k}] {a} vs {b}"
    for k, (a, b) in enumerate(zip(py["trade_pnl_curve"], js["trade_pnl_curve"])):
        assert abs(a - b) <= TOL, f"run {idx}: trade_pnl[{k}] {a} vs {b}"

    # trades
    assert len(py["trades"]) == len(js["trades"]), (
        f"run {idx}: n trades {len(py['trades'])} vs {len(js['trades'])}"
    )
    for k, (tp, tj) in enumerate(zip(py["trades"], js["trades"])):
        for field in ("entry_date", "exit_date", "direction"):
            assert tp[field] == tj[field], f"run {idx} trade {k}: {field} {tp[field]} vs {tj[field]}"
        for field in ("entry_price", "exit_price", "pnl_pct", "capital_after"):
            assert abs(tp[field] - tj[field]) <= TOL, (
                f"run {idx} trade {k}: {field} {tp[field]} vs {tj[field]}"
            )

    # signal events (tipo/direzione/date devono coincidere)
    ev_py = [(e["type"], e["direction"], e["signal_date"], e["exec_date"]) for e in py["signal_events"]]
    ev_js = [(e["type"], e["direction"], e["signal_date"], e["exec_date"]) for e in js["signal_events"]]
    assert ev_py == ev_js, f"run {idx}: signal_events divergono\nPY {ev_py}\nJS {ev_js}"

    # stats
    for field in ("final_capital", "total_return", "win_rate", "total_trades",
                  "avg_trade_pct", "max_drawdown", "profit_factor", "wins",
                  "losses", "exposure_pct", "sharpe", "buy_hold_return"):
        a, b = py["stats"][field], js["stats"][field]
        assert abs(a - b) <= TOL, f"run {idx}: stats.{field} {a} vs {b}"


def main():
    from stable_strategy import backtest_stable

    series = {"a": _make_series(1), "b": _make_series(2), "c": _make_series(3)}
    runs = [
        {"series": "a", "mode": "LONG", "entry_th": 0.0, "exit_th": 0.0,
         "execution_lag": 1, "cost_pct": 0.0, "initial_capital": 1000.0},
        {"series": "a", "mode": "LONG", "entry_th": 0.1, "exit_th": -0.1,
         "execution_lag": 1, "cost_pct": 0.05, "initial_capital": 1000.0},
        {"series": "b", "mode": "SHORT", "entry_th": 0.3, "exit_th": 0.2,
         "execution_lag": 1, "cost_pct": 0.05, "initial_capital": 1000.0},
        {"series": "b", "mode": "BOTH", "entry_th": 0.05, "exit_th": 0.02,
         "execution_lag": 1, "cost_pct": 0.1, "initial_capital": 1000.0},
        {"series": "c", "mode": "LONG", "entry_th": 0.0, "exit_th": 0.0,
         "execution_lag": 0, "cost_pct": 0.0, "initial_capital": 1000.0},
        {"series": "c", "mode": "BOTH", "entry_th": -0.7, "exit_th": -1.2,
         "execution_lag": 1, "cost_pct": 0.0, "initial_capital": 1000.0,
         "start_date": "2023-06-01", "end_date": "2024-03-01"},
    ]

    # Python
    py_results = []
    for r in runs:
        s = series[r["series"]]
        py_results.append(backtest_stable(
            s["dates"], s["prices"], s["slopes"], mode=r["mode"],
            entry_th=r["entry_th"], exit_th=r["exit_th"],
            execution_lag=r["execution_lag"], cost_pct=r["cost_pct"],
            initial_capital=r["initial_capital"],
            start_date=r.get("start_date"), end_date=r.get("end_date"),
        ))

    # JavaScript
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"series": series, "runs": runs}, f)
        fixture_path = f.name
    try:
        runner = os.path.join(os.path.dirname(__file__), "parity_runner.cjs")
        proc = subprocess.run(["node", runner, fixture_path],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, f"runner JS fallito:\n{proc.stderr}"
        js_results = json.loads(proc.stdout)
    finally:
        os.unlink(fixture_path)

    assert len(js_results) == len(py_results)
    for idx, (py, js) in enumerate(zip(py_results, js_results)):
        _compare_run(idx, py, js)
        n_tr = len(py["trades"])
        print(f"  OK run {idx} ({runs[idx]['mode']}, lag={runs[idx]['execution_lag']}, "
              f"cost={runs[idx]['cost_pct']}): {n_tr} trades identici")

    print("OK test_js_py_parity — motore JS speculare al Python su 6 configurazioni")


if __name__ == "__main__":
    main()
