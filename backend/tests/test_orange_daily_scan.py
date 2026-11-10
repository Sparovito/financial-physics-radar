"""
Test per la SCANSIONE GIORNALIERA rifatta sull'arancione
(stable_scanner.orange_daily_scan, usata da POST /scan-daily-orange).

La vecchia scansione dava "STRONG BUY / BUY" in base a Frozen e SUM, le
strategie che nei test non hanno mostrato vantaggio. La nuova mostra:
- i segnali arancioni dell'ultima seduta chiusa (da eseguire alla prossima
  chiusura), ordinati per distanza del prezzo dal fondamentale;
- i segnali dei giorni precedenti e le posizioni che la regola terrebbe;
- l'ampiezza (quanti titoli hanno dato segnale): il vantaggio sta nel giorno;
- lo stato del forward test (sola lettura: la scansione manuale non scrive
  nel journal e non manda email).
Supporta il "viaggio nel tempo" (as_of_date) senza guardare il futuro.

Esecuzione: backend/venv/bin/python backend/tests/test_orange_daily_scan.py
"""
import os
import sys
import datetime

os.environ.setdefault("FPR_STORAGE", "local")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _universe():
    idx = pd.date_range(end="2026-11-06", periods=503, freq="B")
    rng = np.random.default_rng(3)
    out = {}
    crash = [100.0] * 500 + [97.0, 94.09, 91.27]          # crollo nelle ultime 3 barre
    out["CRASH"] = pd.Series(crash, index=idx)
    for k in range(5):
        out[f"FLAT{k}"] = pd.Series(100 + np.cumsum(rng.normal(0, 0.05, 503)), index=idx)
    return out, idx


def main():
    import stable_scanner
    from stable_scanner import orange_daily_scan, drop_partial_last_bar

    prices, idx = _universe()
    calls = {"n": 0}

    def fake_download(tickers, start_date, max_workers=8):
        calls["n"] += 1
        return {t: prices[t].copy() for t in tickers if t in prices}, [t for t in tickers if t not in prices]

    stable_scanner.download_all_prices = fake_download
    tickers = sorted(prices) + ["MANCANTE"]
    first_crash = idx[500].strftime("%Y-%m-%d")
    last = idx[-1].strftime("%Y-%m-%d")

    # --- 1. alla data del primo crollo: segnale NUOVO, da eseguire alla prossima chiusura ---
    r = orange_daily_scan(tickers, as_of_date=first_crash)
    assert r["as_of"] == first_crash and r["n_scanned"] == 6 and r["n_requested"] == 7
    assert [s["ticker"] for s in r["signals_new"]] == ["CRASH"], r["signals_new"]
    s = r["signals_new"][0]
    assert s["signal_date"] == first_crash
    assert s["depth_pct"] > 0 and s["z"] > 2
    assert s["exit_estimate"] > first_crash
    assert abs(r["breadth_pct"] - 100 / 6) < 0.1
    assert r["forward"] is None, "nel viaggio nel tempo lo stato del forward test non c'entra"

    # --- 2. tre sedute dopo: il segnale è 'dei giorni scorsi' e la regola tiene la posizione ---
    r2 = orange_daily_scan(tickers, as_of_date=last)
    assert r2["signals_new"] == []
    assert [s["ticker"] for s in r2["signals_recent"]] == ["CRASH"]
    assert r2["signals_recent"][0]["days_ago"] >= 1
    assert [p["ticker"] for p in r2["active"]] == ["CRASH"]

    # --- 3. prima del crollo: nessun segnale (niente futuro) ---
    before = idx[498].strftime("%Y-%m-%d")
    r3 = orange_daily_scan(tickers, as_of_date=before)
    assert r3["signals_new"] == [] and r3["signals_recent"] == [] and r3["active"] == []

    # --- 4. i valori attesi dal backtest viaggiano con la risposta ---
    assert r["expected"]["signal"] == 3.4 and r["expected"]["baseline"] == 1.2

    # --- 5. la scansione manuale non scrive il journal ---
    journal_file = os.path.join(os.path.dirname(__file__), "..", "forward_test_journal.json")
    existed = os.path.exists(journal_file)
    orange_daily_scan(tickers)                       # modalità "oggi"
    assert os.path.exists(journal_file) == existed, "la scansione manuale non deve creare il journal"

    # --- 6. crypto: la candela del giorno UTC in corso è sempre incompleta ---
    today = datetime.date(2026, 11, 10)
    cidx = pd.date_range(end="2026-11-10", periods=30, freq="D")
    px = pd.Series(np.linspace(1, 2, 30), index=cidx)
    late = datetime.datetime(2026, 11, 10, 22, 30)   # dopo la chiusura USA
    assert len(drop_partial_last_bar(px, today=today, now=late, ticker="AAPL", utc_today=today)) == 30
    assert len(drop_partial_last_bar(px, today=today, now=late, ticker="BTC-USD", utc_today=today)) == 29, \
        "per le crypto la barra del giorno UTC corrente va scartata anche la sera"
    # dopo mezzanotte UTC la barra di ieri è completa
    assert len(drop_partial_last_bar(px, today=today + datetime.timedelta(days=1),
                                     now=late + datetime.timedelta(hours=3), ticker="BTC-USD",
                                     utc_today=today + datetime.timedelta(days=1))) == 30

    print("OK test_orange_daily_scan — segnale nuovo/recente/assente per data, ampiezza, "
          "nessuna scrittura del journal, candela crypto incompleta")


if __name__ == "__main__":
    main()
