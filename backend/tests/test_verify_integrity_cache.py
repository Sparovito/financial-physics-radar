"""
Test per il fix della chiave cache di /verify-integrity (main.py).

Bug: verify_trade_integrity leggeva TICKER_CACHE[f"{ticker}_frozen"], chiave
che nessuno scrive (analyze_stock salva in TICKER_CACHE[ticker]["frozen"]).
Risultato: per FROZEN/SUM z_signal era sempre vuoto -> il verificatore
rispondeva "0 trade corrotti" senza aver testato nulla (falso OK).

Il test costruisce una cache sintetica NEL FORMATO REALE di analyze_stock e
verifica che la simulazione processi davvero dei trade.

Esecuzione: backend/venv/bin/python backend/tests/test_verify_integrity_cache.py
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _build_synthetic_cache(n=800, seed=3):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0003, 0.011, n)
    px_vals = 90.0 * np.exp(np.cumsum(rets))
    idx = pd.date_range("2022-06-01", periods=n, freq="B")
    px = pd.Series(px_vals, index=idx, name="TESTSYN")

    # Serie frozen sintetica nel formato prodotto da analyze_stock:
    # una entry per ogni t da MIN_POINTS=100 in poi
    MIN_POINTS = 100
    t_range = range(MIN_POINTS, n)
    dates = [idx[t].strftime("%Y-%m-%d") for t in t_range]
    # raw_sum oscillante: lo z-score attraversera' la soglia -0.3 piu' volte
    base = np.linspace(0, 40 * np.pi, len(dates))
    raw_sum = (5 + 3 * np.sin(base) + rng.normal(0, 0.5, len(dates))).tolist()
    pot = (2 + 1.5 * np.sin(base + 0.7) + rng.normal(0, 0.3, len(dates))).tolist()
    kin = (1 + np.abs(rng.normal(0, 0.5, len(dates)))).tolist()

    return px, {
        "dates": dates,
        "kin": [round(v, 2) for v in kin],
        "pot": [round(v, 2) for v in pot],
        "z_sum": [0.0] * len(dates),  # non usato dalla verifica (ricalcola dai raw)
        "raw_sum": raw_sum,
    }


def main():
    import main as backend_main
    from main import verify_trade_integrity, VerifyIntegrityRequest

    px, frozen = _build_synthetic_cache()

    # Cache nel formato REALE scritto da analyze_stock
    backend_main.TICKER_CACHE["TESTSYN"] = {
        "px": px,
        "frozen": frozen,
    }

    # --- 1. SUM: la verifica deve processare trade reali, non tornare vuota ---
    req = VerifyIntegrityRequest(ticker="TESTSYN", strategy="SUM")
    res = asyncio.run(verify_trade_integrity(req))

    assert res["status"] == "ok", f"status inatteso: {res}"
    assert res["total_trades"] > 0, (
        "VERIFICA VACUA: 0 trade processati — la chiave cache dei dati frozen "
        "non viene trovata (bug f'{ticker}_frozen')"
    )

    # --- 2. FROZEN: idem ---
    req2 = VerifyIntegrityRequest(ticker="TESTSYN", strategy="FROZEN")
    res2 = asyncio.run(verify_trade_integrity(req2))
    assert res2["status"] == "ok", f"status inatteso: {res2}"
    assert res2["total_trades"] > 0, "VERIFICA VACUA anche per FROZEN"

    # --- 3. Senza dati frozen in cache: errore esplicito, NON falso ok ---
    backend_main.TICKER_CACHE["TESTSYN2"] = {"px": px}
    req3 = VerifyIntegrityRequest(ticker="TESTSYN2", strategy="SUM")
    res3 = asyncio.run(verify_trade_integrity(req3))
    assert res3["status"] == "error", (
        f"Senza dati frozen deve tornare un errore esplicito, non '{res3.get('status')}' "
        f"con {res3.get('total_trades', '?')} trade (falso OK vacuo)"
    )

    print(f"OK test_verify_integrity_cache — SUM: {res['total_trades']} trade, "
          f"{res['corrupted_count']} corrotti | FROZEN: {res2['total_trades']} trade | "
          f"no-frozen -> errore esplicito")


if __name__ == "__main__":
    main()
