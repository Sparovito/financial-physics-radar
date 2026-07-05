"""
Test per il FORWARD TEST journal (forward_test.py) — il paper trading
"da oggi in poi" richiesto dall'utente: ogni scan giornaliero registra i
segnali reali, riempie gli ingressi alla barra successiva (esecuzione t+1),
chiude a orizzonte e accumula il track record a QUOTA FISSA.

Esecuzione: backend/venv/bin/python backend/tests/test_forward_journal.py
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _series(vals, start="2026-07-01"):
    dates = [d.strftime("%Y-%m-%d") for d in pd.date_range(start, periods=len(vals), freq="B")]
    return dates, [float(v) for v in vals]


def main():
    from forward_test import (load_journal, save_journal, update_journal,
                              journal_stats)  # RED: modulo non esiste

    HORIZON = 3
    COST = 0.05

    # --- giorno 0: segnale su TKR, prezzi disponibili fino a d0 ---
    dates, closes = _series([100, 102, 104, 106, 108, 110])
    d = dates  # alias
    journal = {"trades": [], "created": d[0], "config": {"horizon": HORIZON}}

    prices_d0 = {"TKR": (d[:1], closes[:1])}
    signals_d0 = [{"ticker": "TKR", "signal_date": d[0], "direction": "LONG",
                   "strategy": "ARANCIONE"}]
    update_journal(journal, prices_d0, signals_d0, horizon=HORIZON, cost_pct=COST)
    assert len(journal["trades"]) == 1
    tr = journal["trades"][0]
    assert tr["status"] == "pending", f"atteso pending: {tr}"

    # --- duplicato: lo stesso segnale non crea un secondo trade ---
    update_journal(journal, prices_d0, signals_d0, horizon=HORIZON, cost_pct=COST)
    assert len(journal["trades"]) == 1, "segnale duplicato non deve raddoppiare"

    # --- giorno 1: barra successiva disponibile -> fill entry t+1 ---
    prices_d1 = {"TKR": (d[:2], closes[:2])}
    update_journal(journal, prices_d1, [], horizon=HORIZON, cost_pct=COST)
    tr = journal["trades"][0]
    assert tr["status"] == "open", f"atteso open: {tr}"
    assert tr["entry_date"] == d[1] and tr["entry_price"] == 102.0

    # --- giorni successivi: mark-to-market ---
    prices_d3 = {"TKR": (d[:4], closes[:4])}
    update_journal(journal, prices_d3, [], horizon=HORIZON, cost_pct=COST)
    tr = journal["trades"][0]
    assert tr["status"] == "open"
    assert tr["bars_held"] == 2
    assert abs(tr["current_pnl_pct"] - ((106 * (1 - COST/100) - 102 * (1 + COST/100)) / (102 * (1 + COST/100)) * 100)) < 0.02

    # --- dopo horizon barre: chiusura alla barra entry_idx + horizon ---
    prices_d5 = {"TKR": (d, closes)}
    update_journal(journal, prices_d5, [], horizon=HORIZON, cost_pct=COST)
    tr = journal["trades"][0]
    assert tr["status"] == "closed", f"atteso closed: {tr}"
    assert tr["exit_date"] == d[1 + HORIZON] and tr["exit_price"] == closes[1 + HORIZON]
    exp_pnl = (closes[4] * (1 - COST/100) - 102 * (1 + COST/100)) / (102 * (1 + COST/100)) * 100
    assert abs(tr["pnl_pct"] - exp_pnl) < 0.02, f"pnl {tr['pnl_pct']} != {exp_pnl:.3f}"

    # --- stats a quota fissa ---
    stats = journal_stats(journal)
    assert stats["closed"] == 1 and stats["open"] == 0 and stats["pending"] == 0
    assert abs(stats["sum_pnl_pct"] - tr["pnl_pct"]) < 0.02
    assert stats["win_rate"] == 100.0

    # --- persistenza su file ---
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        save_journal(journal, path)
        j2 = load_journal(path)
        assert j2["trades"][0]["pnl_pct"] == tr["pnl_pct"]
    finally:
        os.unlink(path)

    print("OK test_forward_journal — pending->open(t+1)->closed(horizon), "
          f"pnl {tr['pnl_pct']:+.2f}%, no duplicati, persistenza")


if __name__ == "__main__":
    main()
