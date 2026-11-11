"""
Test dello STATO DEL SISTEMA (secondo principio applicato al mercato).

Idea (research/second_law.py): lo scostamento di ogni titolo dal suo percorso,
in sigma, ha una parte comune a tutti i titoli (ordinata) e una parte propria
di ciascuno (calore). Solo la parte comune X = media degli scostamenti muove
un indice. Segnale "rientro iniziato": X è stato nel 5% più basso dei 5 anni
precedenti nelle ultime 10 sedute E oggi è più alto di 5 sedute fa; la
posizione resta aperta fino a 21 sedute dopo l'ultimo giorno di segnale.

Tutto deve essere causale: il passato non cambia quando arrivano dati nuovi.

Esecuzione: backend/venv/bin/python backend/tests/test_system_state.py
"""
import os
import sys
import math
import tempfile

os.environ.setdefault("FPR_STORAGE", "local")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _universe(n_tickers=40, n=900, seed=7):
    """Titoli con una componente comune (il "mercato") più rumore proprio; crollo comune a metà."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=n, freq="B")
    common = rng.normal(0.0003, 0.008, n)
    common[600:612] = -0.03                      # panico: tutti giù insieme per 12 sedute
    common[612:640] = 0.008                      # rientro
    out = {}
    for k in range(n_tickers):
        own = rng.normal(0, 0.012, n)
        out[f"T{k:02d}"] = pd.Series(100 * np.exp(np.cumsum(common + own)), index=idx)
    return out, idx


def main():
    import system_state as ss

    prices, idx = _universe()

    # --- 1. scostamento del singolo titolo: sigma, riscaldamento, causalità ---
    px = prices["T00"]
    x = ss.ticker_displacement(px)
    assert len(x) == len(px) and x.index.equals(px.index)
    assert x.iloc[:ss.WARMUP].isna().all() and np.isfinite(x.iloc[ss.WARMUP:]).all()
    assert x.iloc[605:615].mean() < -1.0, "dopo il crollo comune il prezzo è sotto il percorso"
    cut = ss.ticker_displacement(px.iloc[:700])
    assert np.allclose(cut.values[ss.WARMUP:], x.values[ss.WARMUP:700]), "lo scostamento passato non cambia"

    # --- 2. spostamento coerente: media tra i titoli, solo giorni con abbastanza titoli ---
    co = ss.coherent_series(prices, min_tickers=20)
    assert list(co.columns) == ["X", "n"] and co["n"].min() >= 20
    d = idx[620]
    manual = np.mean([ss.ticker_displacement(p)[d] for p in prices.values()])
    assert abs(co.loc[d, "X"] - manual) < 1e-9
    assert co["X"].idxmin() >= idx[600] and co["X"].idxmin() <= idx[625], "il minimo di X cade nel panico comune"
    few = ss.coherent_series({k: prices[k] for k in list(prices)[:5]}, min_tickers=20)
    assert len(few) == 0, "con pochi titoli nessun giorno è valido"

    # --- 3. percentile causale ---
    v = np.array([5.0, 4.0, 3.0, 2.0, 1.0, 6.0])
    p = ss.causal_percentile(v, window=5, min_periods=3)
    assert math.isnan(p[0]) and math.isnan(p[1])
    assert abs(p[2] - 1 / 3) < 1e-9 and abs(p[4] - 1 / 5) < 1e-9 and abs(p[5] - 1.0) < 1e-9
    assert np.allclose(ss.causal_percentile(v[:5], 5, 3)[2:], p[2:5]), "il percentile passato non cambia"

    # --- 4. segnale "rientro iniziato": niente finché X scende, sì quando risale dopo un estremo ---
    X = np.r_[np.zeros(30), np.linspace(0, -3, 16), np.linspace(-2.8, -1.0, 10), np.zeros(30)]
    pct = np.r_[np.full(30, 0.5), np.linspace(0.5, 0.0, 16), np.full(10, 0.02), np.full(30, 0.5)]
    sig = ss.relaxation_signal(X, pct, touch=0.05, memory=10, turn=5)
    assert not sig[:46].any(), "mentre lo squilibrio cresce non c'è segnale"
    first = int(np.argmax(sig))
    assert 46 <= first <= 51 and X[first] > X[first - 5], f"primo segnale quando X risale (indice {first})"
    assert not sig[70:].any(), "lontano dall'estremo niente segnale"

    # --- 5. tenuta: 21 sedute dopo l'ultimo giorno di segnale ---
    s = np.zeros(60, dtype=bool)
    s[10] = True
    h = ss.hold_flags(s, hold=21)
    assert h[10] and h[31] and not h[32] and not h[9]

    # --- 6. analisi completa su una storia sintetica + stato di oggi ---
    hist = co.copy()
    an = ss.analyse(hist, window=300, min_periods=150)
    assert set(["X", "n", "pct", "signal", "hold"]) <= set(an.columns) and len(an) == len(hist)
    assert an["signal"].loc[idx[612]:idx[640]].any(), "dopo il panico comune deve scattare il rientro"
    assert not an["signal"].loc[idx[600]:idx[608]].any(), "non durante la caduta"
    an_cut = ss.analyse(hist.iloc[:500], window=300, min_periods=150)
    assert an_cut["signal"].tolist() == an["signal"].iloc[:500].tolist(), "i segnali passati non cambiano"
    st = ss.current_state(an.loc[:idx[606]])
    assert st["state"] == "squilibrio in aumento", st
    day_sig = an.index[an["signal"]][0]
    assert ss.current_state(an.loc[:day_sig])["state"] == "rientro iniziato"
    later = an.index[an.index.get_loc(an.index[an["signal"]][-1]) + 5]
    st2 = ss.current_state(an.loc[:later])
    assert st2["state"] == "in tenuta" and 0 < st2["sessions_left"] <= 21
    assert ss.current_state(an.loc[:idx[400]])["state"] == "equilibrio"

    # --- 7. posizioni e backtest su un titolo: dentro solo nei periodi di tenuta, esecuzione t+1 ---
    dates = [d.strftime("%Y-%m-%d") for d in idx]
    pos = ss.hold_positions(dates, an)
    assert len(pos) == len(dates) and set(pos) <= {0, 1}
    assert pos[an.index.get_loc(day_sig) + (len(dates) - len(an))] == 1 if len(an) == len(dates) else True
    spy = [float(v) for v in prices["T01"].values]
    res = ss.backtest_system(dates, spy, an)
    first_in = next(i for i, v in enumerate(pos) if v == 1)
    assert res["trades"][0]["entry_date"] == dates[first_in + 1], "ingresso alla chiusura successiva al segnale"
    assert len(res["trade_pnl_curve"]) == len(dates)
    # date del titolo che il sistema non conosce (es. fine settimana delle crypto): vale l'ultimo stato noto
    assert ss.hold_positions(["1999-01-01"], an) == [0]

    # scanner: la colonna "system" c'è solo se si passa l'analisi del sistema, e ha il timing
    from strategy_scan import scan_one
    start, end = idx[400].strftime("%Y-%m-%d"), idx[850].strftime("%Y-%m-%d")
    r_no = scan_one(prices["T01"], start_date=start, end_date=end)
    r_si = scan_one(prices["T01"], start_date=start, end_date=end, system=an)
    assert "system" not in r_no["strategies"] and "system" in r_si["strategies"]
    assert math.isfinite(r_si["strategies"]["system"]["timing"]) and "system" in r_si["weekly"]
    assert 0 < r_si["strategies"]["system"]["expo"] < 40, "dentro solo nei periodi di tenuta"

    # --- 8. storia: seme + coda, aggiornamento con prezzi nuovi ---
    with tempfile.TemporaryDirectory() as tmp:
        seed = os.path.join(tmp, "seed.csv")
        ss.write_history_csv(co.iloc[:500], seed)
        loaded = ss.read_history_csv(seed)
        assert len(loaded) == 500 and abs(loaded["X"].iloc[-1] - co["X"].iloc[499]) < 1e-5
        new_rows = ss.rows_after(co, loaded.index[-1])
        assert len(new_rows) == len(co) - 500 and new_rows.index[0] > loaded.index[-1]
        merged = ss.merge_history(loaded, new_rows)
        assert len(merged) == len(co) and merged.index.is_monotonic_increasing
        # la coda corregge anche l'ultimo giorno del seme, se ripetuto
        fix = co.iloc[499:501].copy()
        fix.iloc[0, 0] = 9.99
        assert ss.merge_history(loaded, fix)["X"].iloc[499] == 9.99

        # aggiornamento: scarica, calcola i giorni mancanti, salva la coda, non salva la barra di oggi
        from storage import Storage, LocalBackend
        store = Storage(remote=None, local=LocalBackend(base_dir=tmp))
        old_seed = ss.SEED_PATH
        ss.SEED_PATH = seed
        try:
            calls = []

            def fetch(tickers, start):
                calls.append((len(tickers), start))
                return prices
            orig_min = ss.MIN_TICKERS
            ss.MIN_TICKERS = 20
            co_default = ss.coherent_series(prices, min_tickers=20)
            real_coherent = ss.coherent_series
            ss.coherent_series = lambda pr, min_tickers=20: real_coherent(pr, min_tickers=20)
            info = ss.refresh(fetch, list(prices), store, today=co_default.index[-1])
            assert info["added"] == len(co) - 500 - 1, f"l'ultima barra (oggi) non va salvata: {info}"
            assert calls and calls[0][0] == len(prices)
            hist = ss.load_history(store)
            assert len(hist) == len(co) - 1 and hist.index[-1] == co.index[-2]
            again = ss.refresh(fetch, list(prices), store, today=co_default.index[-1])
            assert again["added"] == 0, "un secondo aggiornamento non aggiunge nulla"
            ss.coherent_series = real_coherent
            ss.MIN_TICKERS = orig_min
        finally:
            ss.SEED_PATH = old_seed

    # --- 9. il seme vero esiste, è lungo e produce episodi plausibili ---
    real = ss.read_history_csv(ss.SEED_PATH)
    assert len(real) > 5000 and str(real.index[0].date()) < "2005-01-01", "serve la storia lunga"
    an_real = ss.analyse(real)
    n_sig = int(an_real["signal"].sum())
    assert 100 < n_sig < 1500, f"giorni di segnale fuori scala: {n_sig}"
    assert an_real["signal"].loc["2009-03-10":"2009-03-31"].any(), "marzo 2009: rientro dopo il minimo"
    assert an_real["signal"].loc["2020-03-23":"2020-04-10"].any(), "fine marzo 2020: rientro dopo il crollo"
    assert not an_real["signal"].loc["2017-01-01":"2017-12-31"].any(), "2017: anno senza squilibri"

    print(f"OK test_system_state — scostamento coerente, percentile e segnale causali; seme: {len(real)} giorni dal {real.index[0].date()}, "
          f"{n_sig} giorni di segnale")


if __name__ == "__main__":
    main()
