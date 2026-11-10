"""
Test per strategy_scan.py — il calcolo dietro lo Scanner Strategie (Massivo).

Prima lo scanner chiamava /analyze per ogni titolo (analisi completa con
Fourier e dati orari) e mostrava solo ROI e win rate, senza confronto col
compra-e-tieni. Ora un calcolo dedicato restituisce, per titolo:
  - buy & hold nel periodo;
  - per ogni strategia (oracolo LIVE, FROZEN, SUM, STABLE, ARANCIONE, COMBO):
    ROI, win rate, trade, esposizione, alpha = ROI − esposizione × B&H;
  - i trade (per il simulatore).
Le strategie causali non devono dipendere dai dati successivi alla data di fine.

Esecuzione: backend/venv/bin/python backend/tests/test_strategy_scan.py
"""
import os
import sys

os.environ.setdefault("FPR_STORAGE", "local")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

STRATEGIES = ["live", "frozen", "sum", "stable", "orange", "combo"]
CAUSAL = ["frozen", "sum", "stable", "orange", "combo"]


def _px(n=900, seed=5):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.014, n)
    rets[600:604] = -0.05
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.Series(100 * np.exp(np.cumsum(rets)), index=idx)


def main():
    from strategy_scan import scan_one, fetch_prices_cached

    px = _px()
    start = px.index[400].strftime("%Y-%m-%d")
    end = px.index[800].strftime("%Y-%m-%d")

    r = scan_one(px, start_date=start, end_date=end)

    # --- 1. struttura e buy & hold ---
    assert set(r["strategies"]) == set(STRATEGIES), r["strategies"].keys()
    exp_bh = (px.iloc[800] / px.iloc[400] - 1) * 100
    assert abs(r["bh"] - exp_bh) < 0.02, (r["bh"], exp_bh)
    assert r["trend"] in ("up", "down", "stable")
    for name in STRATEGIES:
        s = r["strategies"][name]
        for key in ("roi", "win_rate", "trades", "expo", "alpha"):
            assert key in s and s[key] is not None, f"{name}.{key} mancante"
        assert 0 <= s["expo"] <= 100, f"{name} esposizione {s['expo']}"
        assert abs(s["alpha"] - (s["roi"] - s["expo"] / 100 * r["bh"])) < 0.05
        for t in r["trades"][name]:
            assert t["entry_date"] >= start, f"{name}: trade prima dell'inizio periodo"
            assert t["exit_date"] == "OPEN" or t["exit_date"] <= end, f"{name}: trade oltre la fine"

    # --- 2. le strategie causali non vedono il futuro ---
    r_trunc = scan_one(px.iloc[:801], start_date=start, end_date=None)
    for name in CAUSAL:
        a, b = r["strategies"][name], r_trunc["strategies"][name]
        assert abs(a["roi"] - b["roi"]) < 1e-6 and a["trades"] == b["trades"], \
            f"{name} dipende dai dati dopo la data di fine ({a['roi']} vs {b['roi']})"

    # --- 3. l'arancione usa i parametri validati, indipendenti da alpha ---
    r350 = scan_one(px, start_date=start, end_date=end, alpha=350)
    assert r350["strategies"]["orange"] == r["strategies"]["orange"]

    # --- 4. storia troppo corta: errore esplicito, non numeri inventati ---
    try:
        scan_one(px.iloc[:120], start_date=px.index[50].strftime("%Y-%m-%d"))
        raise AssertionError("storia corta accettata")
    except ValueError as e:
        assert "storia" in str(e).lower()

    # --- 5. cache prezzi: uno scarico per titolo al giorno, falliti segnalati ---
    calls = []

    def fake_fetch(t, s):
        calls.append(t)
        if t == "BAD":
            raise ValueError("no data")
        return px

    got, failed = fetch_prices_cached(["AAA", "BBB", "BAD"], "2021-01-01", fake_fetch, day="2026-11-11")
    assert set(got) == {"AAA", "BBB"} and "BAD" in failed
    fetch_prices_cached(["AAA", "CCC"], "2021-01-01", fake_fetch, day="2026-11-11")
    assert calls.count("AAA") == 1, "AAA non va riscaricato nello stesso giorno"
    fetch_prices_cached(["AAA"], "2021-01-01", fake_fetch, day="2026-11-12")
    assert calls.count("AAA") == 2, "il giorno dopo la cache va rinnovata"

    o = r["strategies"]
    print("OK test_strategy_scan — B&H %.1f%% | " % r["bh"]
          + " | ".join(f"{n} {o[n]['roi']:+.1f}%" for n in STRATEGIES)
          + " | causali senza futuro, cache giornaliera")


if __name__ == "__main__":
    main()
