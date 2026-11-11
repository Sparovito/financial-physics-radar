"""
Test della misura di TIMING dello Scanner Massivo e della strategia Frozen V2.

Perché esiste: la colonna "alpha" storica (ROI − esposizione × B&H) confronta
un rendimento composto con una frazione lineare del compra-e-tieni. Su un
titolo salito molto dà alpha negativo anche a una strategia che entra ed esce
A CASO. La misura di timing lavora sui rendimenti logaritmici giornalieri:

    eccesso(giorno) = rendimento della strategia
                      − quota di tempo long  × rendimento del titolo
                      − quota di tempo short × rendimento dello short

La somma vale zero in media per qualsiasi strategia che scelga i tempi a caso,
qualunque sia la salita del titolo.

Frozen V2: il Frozen entra quando l'energia potenziale è sopra la media, ma
l'energia è un quadrato e non ha direzione. V2 aggiunge il segno dello
scostamento d = EMA20 − filtro: long solo se l'energia è sopra la media E d<0.

Esecuzione: backend/venv/bin/python backend/tests/test_scan_timing.py
"""
import os
import sys
import math

os.environ.setdefault("FPR_STORAGE", "local")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _dates(n):
    return pd.date_range("2022-01-03", periods=n, freq="B").strftime("%Y-%m-%d").tolist()


def _px(n=900, seed=5):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.014, n)
    rets[600:604] = -0.05
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.Series(100 * np.exp(np.cumsum(rets)), index=idx)


def main():
    from strategy_scan import (scan_one, position_series, timing_excess, aggregate_weekly)
    from stable_strategy import frozen_v2_positions, backtest_frozen_v2

    # --- 1. titolo che sale a ritmo costante (+100% circa): qualsiasi scelta dei tempi vale zero ---
    n = 500
    dates = _dates(n)
    prices = [100 * 1.0014 ** i for i in range(n)]
    lo, hi = 0, n - 1
    trades = [{"entry_date": dates[50], "exit_date": dates[200], "direction": "LONG"},
              {"entry_date": dates[320], "exit_date": dates[410], "direction": "LONG"}]
    pos = position_series(trades, dates, lo, hi)
    assert pos[50] == 0 and pos[51] == 1 and pos[200] == 1 and pos[201] == 0, "esposto dal giorno dopo l'ingresso a quello di uscita"
    timing, weekly = timing_excess(prices, pos, dates, lo, hi)
    assert abs(timing) < 1e-6, f"su una salita costante il timing deve essere 0, è {timing}"
    # ...mentre l'alpha lineare storico penalizza la stessa strategia
    roi = (prices[200] / prices[50]) * (prices[410] / prices[320]) - 1
    bh = prices[hi] / prices[lo] - 1
    expo = float((pos != 0).mean())
    assert (roi - expo * bh) * 100 < -5, "atteso: l'alpha lineare è negativo senza che ci sia un errore di timing"

    # --- 2. le somme settimanali ricostruiscono il totale; le chiavi sono lunedì ---
    tot = sum(weekly.values())
    assert abs(math.expm1(tot) * 100 - timing) < 1e-9
    for k in weekly:
        assert pd.Timestamp(k).weekday() == 0, f"chiave settimana non lunedì: {k}"

    # --- 3. tempi giusti → positivo, tempi sbagliati → negativo, simmetrici in log ---
    alt = [100.0]
    for i in range(1, n):
        alt.append(alt[-1] * (1.01 if i % 2 == 1 else 0.99))
    good = np.array([1.0 if i % 2 == 1 else 0.0 for i in range(n)])
    bad = 1.0 - good
    good[0] = bad[0] = 0.0
    t_good, _ = timing_excess(alt, good, dates, 0, n - 1)
    t_bad, _ = timing_excess(alt, bad, dates, 0, n - 1)
    assert t_good > 50 and t_bad < -30, (t_good, t_bad)

    # --- 4. short: su una discesa costante, anche lo short a caso vale zero; lo short giusto è positivo ---
    down = [100 * 0.999 ** i for i in range(n)]
    sh = position_series([{"entry_date": dates[100], "exit_date": dates[300], "direction": "SHORT"}], dates, 0, n - 1)
    assert sh[101] == -1 and sh[300] == -1 and sh[301] == 0
    t_sh, _ = timing_excess(down, sh, dates, 0, n - 1)
    assert abs(t_sh) < 1e-6, t_sh
    short_good = -bad                       # short nei giorni di ribasso della serie alternata
    t_sg, _ = timing_excess(alt, short_good, dates, 0, n - 1)
    assert t_sg > 50, t_sg

    # --- 5. scan_one: 'timing' per ogni strategia, coerente col ROI composto; settimane restituite ---
    px = _px()
    start = px.index[400].strftime("%Y-%m-%d")
    end = px.index[800].strftime("%Y-%m-%d")
    r = scan_one(px, start_date=start, end_date=end)
    assert "frozen2" in r["strategies"], "manca la strategia Frozen V2"
    for name, st in r["strategies"].items():
        assert "timing" in st and math.isfinite(st["timing"]), f"{name}: timing mancante"
        assert name in r["weekly"], f"{name}: settimane mancanti"
        tot = sum(r["weekly"][name].values())
        assert abs(math.expm1(tot) * 100 - st["timing"]) < 0.02, name
    # per le strategie solo long senza costi il rendimento log delle posizioni è log(1+ROI)
    d_all = px[px.index <= pd.Timestamp(end)]
    dts = d_all.index.strftime("%Y-%m-%d").tolist()
    prs = [float(v) for v in d_all.values]
    lo = next(i for i, d in enumerate(dts) if d >= start)
    hi = len(dts) - 1
    for name in ("stable", "orange", "combo", "frozen2"):
        ps = position_series(r["trades"][name], dts, lo, hi)
        logret = sum(math.log(prs[i] / prs[i - 1]) for i in range(lo + 1, hi + 1) if ps[i] > 0)
        assert abs(math.expm1(logret) * 100 - r["strategies"][name]["roi"]) < 0.05, \
            f"{name}: posizioni ricostruite ≠ ROI ({math.expm1(logret) * 100:.2f} vs {r['strategies'][name]['roi']})"

    # --- 6. aggregato per settimana tra più titoli: somma e numero di titoli, 'weekly' tolto dalla risposta ---
    r2 = scan_one(_px(seed=9), start_date=start, end_date=end)
    wk_a = dict(r["weekly"]["stable"])
    wk_b = dict(r2["weekly"]["stable"])
    results = {"AAA": r, "BBB": r2}
    agg = aggregate_weekly(results)
    assert "weekly" not in results["AAA"] and "weekly" not in results["BBB"]
    k = sorted(wk_a)[3]
    assert abs(agg["stable"][k][0] - (wk_a[k] + wk_b[k])) < 1e-6 and agg["stable"][k][1] == 2

    # --- 7. Frozen V2: posizione solo con energia sopra la media E scostamento negativo ---
    m = 400
    pot = [1.0 + 0.01 * (i % 7) for i in range(m)]
    disp = [0.5] * m
    for i in range(300, 330):                # energia alta, prezzo SOTTO il percorso
        pot[i], disp[i] = 9.0, -3.0
    for i in range(350, 380):                # energia alta, prezzo SOPRA il percorso
        pot[i], disp[i] = 9.0, +3.0
    p2 = frozen_v2_positions(pot, disp)
    assert sum(p2[300:330]) >= 25, "energia alta + sotto il percorso → long"
    assert sum(p2[350:380]) == 0, "energia alta + sopra il percorso → fuori"
    assert sum(p2[:300]) == 0, "energia nella media → fuori"
    assert frozen_v2_positions([float("nan")] * 50, [float("nan")] * 50) == [0] * 50

    # causale: troncare i dati non cambia le posizioni passate
    assert frozen_v2_positions(pot[:340], disp[:340]) == p2[:340]

    # esecuzione t+1 col motore unificato
    dts2 = _dates(m)
    prs2 = [100 + 0.1 * i for i in range(m)]
    res = backtest_frozen_v2(dts2, prs2, pot, disp)
    first = res["trades"][0]
    sig = next(i for i, v in enumerate(p2) if v == 1)
    assert first["entry_date"] == dts2[sig + 1], "ingresso alla chiusura successiva al segnale"

    # --- 8. Frozen V2 nello scanner non vede il futuro ---
    r_trunc = scan_one(px.iloc[:801], start_date=start, end_date=None)
    a, b = r["strategies"]["frozen2"], r_trunc["strategies"]["frozen2"]
    assert abs(a["roi"] - b["roi"]) < 1e-6 and a["trades"] == b["trades"] and abs(a["timing"] - b["timing"]) < 1e-6

    print("OK test_scan_timing — salita costante: timing %.6f (alpha lineare %.1f) | tempi giusti %+.0f%%, sbagliati %+.0f%% | Frozen V2 causale"
          % (timing, (roi - expo * bh) * 100, t_good, t_bad))


if __name__ == "__main__":
    main()
