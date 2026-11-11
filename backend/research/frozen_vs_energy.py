"""
FROZEN contro ENERGY: l'arancione (potenziale Frozen, causale) è la versione in
tempo reale del blu (cinetica dell'Energy, calcolata con tutta la storia)?

Osservazione di partenza (dai grafici): le gobbe blu dell'Energy coincidono con
i movimenti grossi e l'arancione del Frozen "ha molto a che fare" col blu; i
due massimi sembrano coincidere.

Perché succede (matematica):
  blu       = ½·α·(velocità del percorso di minima azione)², percorso calcolato
              con passato E futuro → media a due lati degli incrementi di F
  arancione = ½·β·d², d = F − filtro. Vale d[t] = (1−K)·(d[t−1] + ΔF[t]):
              d è una media dei soli incrementi PASSATI di F (≈ 14 barre)
Sono la stessa grandezza (velocità al quadrato): l'arancione la misura con il
solo passato, quindi in ritardo. Il segno di d dà la direzione.

Misure:
  A. correlazione arancione(t) ↔ blu(t−k) per ogni ritardo k
  B. gobbe blu in salita (= operazioni long dell'oracolo): dopo quante barre si
     accende l'arancione, quanta parte del guadagno è già passata, dove cade il
     massimo dell'arancione
  C. cosa fa il prezzo DOPO, per fase dell'arancione (in carica / in scarica)
     e direzione (prezzo sopra / sotto il percorso)
  D. regole causali che ne derivano, col timing del portafoglio

Causale: decisione alla chiusura t, esecuzione t+1, primo rendimento t+2.

    backend/venv/bin/python backend/research/frozen_vs_energy.py
    (FPR_PANEL_CACHE=percorso.pkl per riusare prezzi già scaricati)
"""
from common import os, np, pd, save_output, tstat, OUTPUT_DIR
from logic import ActionPath
from kinetic_trend import load_panel, roll_z, week_ids

A0, A1, B0 = "2021-01-01", "2023-12-31", "2024-01-01"
ALPHA, BETA = 200.0, 1.0
LAGS = list(range(-5, 41))
DK = 3                                   # barre su cui si dice "in carica" / "in scarica"


def kalman(F):
    q, r = 1.0 / ALPHA, 1.0 / BETA
    x = np.empty(len(F))
    x[0], P = F[0], r
    for t in range(1, len(F)):
        Pp = P + q
        g = Pp / (Pp + r)
        x[t] = x[t - 1] + g * (F[t] - x[t - 1])
        P = (1 - g) * Pp
    return x


def runs(mask, min_len=1):
    out, n, t = [], len(mask), 0
    while t < n:
        if mask[t]:
            s = t
            while t < n and mask[t]:
                t += 1
            if t - s >= min_len:
                out.append((s, t - 1))
        else:
            t += 1
    return out


def lag_corr(a, b, k):
    """corr(a[t], b[t−k])"""
    if k > 0:
        x, y = a[k:], b[:-k]
    elif k < 0:
        x, y = a[:k], b[-k:]
    else:
        x, y = a, b
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 200:
        return np.nan
    return float(np.corrcoef(x[m], y[m])[0, 1])


def per_ticker(tk, px):
    p = px.values.astype(float)
    n, idx = len(p), px.index
    if n < 700:
        return None
    lr = np.zeros(n)
    lr[1:] = np.log(p[1:] / p[:-1])
    F = px.ewm(span=20, adjust=False).mean().values.astype(float)
    d = F - kalman(F)
    orange = 0.5 * BETA * d ** 2
    ap = ActionPath(px, alpha=ALPHA, beta=BETA)
    vs = ap.dX.values
    blue = 0.5 * ALPHA * vs ** 2
    z_or = np.array(roll_z(pd.Series(orange), minp=40).values, dtype=float)
    z_bl = np.array(roll_z(pd.Series(blue), minp=20).values, dtype=float)
    z_or[:260] = np.nan
    v0 = max(260, int(np.searchsorted(idx.values, np.datetime64(A0))))
    if n - v0 < 300:
        return None
    live = np.zeros(n, dtype=bool)
    live[v0:] = True
    res = {"ticker": tk}

    # --- A. correlazione ai vari ritardi ---
    o, b = np.where(live, orange, np.nan), np.where(live, blue, np.nan)
    ds, vv = np.where(live, d, np.nan), np.where(live, vs, np.nan)
    res["corr_energy"] = [lag_corr(np.sqrt(o), np.sqrt(b), k) for k in LAGS]
    res["corr_signed"] = [lag_corr(ds, vv, k) for k in LAGS]

    # --- B. gobbe blu in salita (operazioni long dell'oracolo) e risposta dell'arancione ---
    on = (z_or > 0) & (d > 0)
    hum = []
    for s, e in runs((z_bl > 0) & (vs > 0) & live, min_len=5):
        if e + 45 >= n:
            continue
        G = np.log(p[e] / p[s])
        if G <= 0.02:
            continue
        pb = s + int(np.argmax(blue[s:e + 1]))
        t_on = next((t for t in range(s, e + 41) if on[t]), None)
        po = s + int(np.argmax(orange[s:e + 41]))
        rec = {"len": e - s + 1, "gain": float(np.expm1(G)), "peak_lag": po - pb,
               "peak_pos": float((po - s) / max(e - s, 1)), "peak_after_end": bool(po > e),
               "gain_at_peak": float(np.log(p[min(po + 1, e)] / p[s]) / G),
               "already_on": bool(on[s]), "delay": None, "passed": None, "detected": False}
        if t_on is not None:
            rec["delay"] = t_on - s
            rec["detected"] = bool(t_on < e)
            rec["passed"] = float(np.log(p[min(t_on + 1, e)] / p[s]) / G) if t_on < e else 1.0
        hum.append(rec)
    res["humps"] = hum

    # episodi arancioni in salita: dove nascono rispetto alle gobbe blu, e quanto rendono
    up_blue = (z_bl > 0) & (vs > 0)
    dn_blue = (z_bl > 0) & (vs < 0)
    eps = []
    for s, e in runs(on & live, min_len=1):
        if e + 2 >= n:
            continue
        ret = p[min(e + 1, n - 1)] / p[s + 1] - 1 if e + 1 > s + 1 else 0.0
        where = "salita blu" if up_blue[s] else ("discesa blu" if dn_blue[s] else "nessuna gobba")
        eps.append({"date": str(idx[s].date()), "ret": float(ret), "bars": e - s + 1, "where": where})
    res["episodes"] = eps

    # --- C/D. celle e regole ---
    ris = orange > np.r_[np.full(DK, np.nan), orange[:-DK]]
    hi = z_or > 0
    cells = {
        "sopra, energia alta, in carica": hi & (d > 0) & ris,
        "sopra, energia alta, in scarica": hi & (d > 0) & ~ris,
        "sotto, energia alta, in carica": hi & (d < 0) & ris,
        "sotto, energia alta, in scarica": hi & (d < 0) & ~ris,
        "sopra, energia bassa": (z_or <= 0) & (d > 0),
        "sotto, energia bassa": (z_or <= 0) & (d < 0),
    }
    cross = np.zeros(n, dtype=bool)
    cross[1:] = on[1:] & ~on[:-1]
    acc = np.zeros(n, dtype=bool)                       # 10 barre dall'accensione
    for t in np.nonzero(cross)[0]:
        acc[t:t + 10] = True
    rules = {
        "segui l'arancione in salita (energia alta, sopra)": on,
        "solo finché è in carica (sopra)": on & ris,
        "le prime 10 barre dall'accensione (sopra)": acc,
        "V2: energia alta, sotto": hi & (d < 0),
        "V2 solo in carica": hi & (d < 0) & ris,
        "sopra il percorso (qualsiasi energia)": d > 0,
    }
    ret = np.full(n, np.nan)
    ret[:-2] = p[2:] / p[1:-1] - 1                     # rendimento da t+1 a t+2
    frame = pd.DataFrame({"ret": ret}, index=idx)
    for i, (nm, m) in enumerate(cells.items()):
        frame.loc[m, "cell"] = i
    frame = frame[live & np.isfinite(z_or)]
    frame["ticker"] = tk
    res["frame"] = frame.dropna(subset=["ret", "cell"])
    res["cell_names"] = list(cells.keys())

    wk = week_ids(idx)
    res["weekly"] = {}
    okz = live & np.isfinite(z_or)
    okz[:v0 + 2] = False
    for per, m in (("A", okz & (idx <= A1)), ("B", okz & (idx >= B0))):
        if m.sum() < 60:
            continue
        for nm, st in rules.items():
            pos = np.zeros(n)
            pos[2:] = st[:-2]
            f = pos[m].mean()
            res["weekly"][(nm, per)] = (pd.Series((pos[m] - f) * lr[m]).groupby(wk[m]).sum(), float(f))

    # --- E. dove sta il guadagno dell'oracolo: giorni in cui l'arancione ha il segno giusto / sbagliato ---
    r2 = np.full(n, np.nan)
    r2[:-2] = lr[2:]                                    # primo rendimento dopo l'esecuzione
    so, sc = np.sign(vs), np.sign(d)
    turn = np.zeros(n, dtype=bool)
    turn[1:] = so[1:] != so[:-1]
    since = np.zeros(n)
    c = 999
    for t in range(n):
        c = 0 if turn[t] else c + 1
        since[t] = c
    m = okz & np.isfinite(r2) & (so != 0) & (sc != 0)
    yrs = max(m.sum() / 252.0, 0.5)
    res["agree"] = {"days": int(m.sum()), "agree": int((so[m] == sc[m]).sum()), "years": float(yrs),
                    "A": float((so * r2)[m & (so == sc)].sum()), "D": float((so * r2)[m & (so != sc)].sum()),
                    "buckets": {}}
    for lab, lo, hi_ in (("0-5", 0, 5), ("5-10", 5, 10), ("10-20", 10, 20), ("20+", 20, 10 ** 9)):
        b = m & (since >= lo) & (since < hi_)
        res["agree"]["buckets"][lab] = (int(b.sum()), int((so[b] == sc[b]).sum()), float((so * r2)[b].sum()),
                                        float((sc * r2)[b].sum()))

    # --- F. accensione dell'arancione in salita: conta la pendenza? ---
    sl5 = z_or - np.r_[np.full(5, np.nan), z_or[:-5]]
    ign = []
    for s0, e0 in runs(on & live, min_len=1):
        if e0 + 2 >= n or s0 < v0 + 5:
            continue
        ign.append({"date": idx[s0], "slope": float(sl5[s0]), "ret": float(p[min(e0 + 1, n - 1)] / p[s0 + 1] - 1) if e0 > s0 else 0.0,
                    "bars": e0 - s0 + 1})
    res["ignitions"] = ign
    for sth in (0.5, 1.0):
        st = np.zeros(n, dtype=bool)
        inp = False
        for t in range(n):
            if not on[t]:
                inp = False
            elif not inp and sl5[t] > sth:
                inp = True
            st[t] = inp
        for per, mm in (("A", okz & (idx <= A1)), ("B", okz & (idx >= B0))):
            if mm.sum() < 60:
                continue
            pos = np.zeros(n)
            pos[2:] = st[:-2]
            f = pos[mm].mean()
            res["weekly"][(f"arancione in salita, entra solo con pendenza > {sth}", per)] = (
                pd.Series((pos[mm] - f) * lr[mm]).groupby(wk[mm]).sum(), float(f))

    res["curves"] = None
    if tk == "NVDA":
        res["curves"] = pd.DataFrame({"px": p, "blu": blue, "arancione": orange, "d": d, "v_oracolo": vs}, index=idx)
    return res


def main():
    prices = load_panel()
    results = []
    for tk, px in prices.items():
        try:
            r = per_ticker(tk, px)
        except Exception as e:
            print("errore", tk, e)
            continue
        if r:
            results.append(r)
    out = {"n_tickers": len(results)}
    print(f"titoli: {len(results)}")

    # --- A ---
    ce = np.nanmedian(np.array([r["corr_energy"] for r in results]), axis=0)
    cs = np.nanmedian(np.array([r["corr_signed"] for r in results]), axis=0)
    best_e = [LAGS[int(np.nanargmax(r["corr_energy"]))] for r in results]
    best_s = [LAGS[int(np.nanargmax(r["corr_signed"]))] for r in results]
    out["corr"] = {"lags": LAGS, "energy": [float(v) for v in ce], "signed": [float(v) for v in cs],
                   "best_lag_energy_median": float(np.median(best_e)), "best_lag_signed_median": float(np.median(best_s))}
    print("\n=== A. Arancione(t) contro blu(t−k): correlazione mediana tra i titoli ===")
    print("ritardo k (barre):   " + "  ".join(f"{k:>5d}" for k in (0, 3, 5, 8, 10, 12, 15, 20, 30)))
    print("energia (radice):    " + "  ".join(f"{ce[LAGS.index(k)]:5.2f}" for k in (0, 3, 5, 8, 10, 12, 15, 20, 30)))
    print("con il segno:        " + "  ".join(f"{cs[LAGS.index(k)]:5.2f}" for k in (0, 3, 5, 8, 10, 12, 15, 20, 30)))
    print(f"ritardo che dà la correlazione massima (mediana tra i titoli): energia {np.median(best_e):.0f} barre "
          f"(tra {np.percentile(best_e, 25):.0f} e {np.percentile(best_e, 75):.0f}), con segno {np.median(best_s):.0f} "
          f"(tra {np.percentile(best_s, 25):.0f} e {np.percentile(best_s, 75):.0f})")

    # --- B ---
    H = pd.DataFrame([h for r in results for h in r["humps"]])
    det = H[H["detected"]]
    out["humps"] = {
        "n": int(len(H)), "median_len": float(H["len"].median()), "mean_gain": float(H["gain"].mean()),
        "detected": float(H["detected"].mean()), "already_on": float(H["already_on"].mean()),
        "delay_median": float(det["delay"].median()), "passed_median": float(det["passed"].median()),
        "passed_mean_all": float(H["passed"].fillna(1.0).clip(0, 1).mean()),
        "peak_lag_median": float(H["peak_lag"].median()), "peak_after_end": float(H["peak_after_end"].mean()),
        "peak_pos_median": float(H["peak_pos"].median()), "gain_at_peak_median": float(H["gain_at_peak"].median()),
    }
    o = out["humps"]
    print(f"\n=== B. Gobbe blu in salita (operazioni long dell'oracolo): {o['n']} | durata mediana {o['median_len']:.0f} barre | "
          f"guadagno medio {o['mean_gain']:+.1%} ===")
    print(f"l'arancione (energia alta, prezzo sopra il percorso) si accende prima che la gobba finisca: {o['detected']:.0%} "
          f"(già acceso alla partenza: {o['already_on']:.0%})")
    print(f"  ritardo dell'accensione: mediana {o['delay_median']:.0f} barre | quota del guadagno già passata all'ingresso: "
          f"mediana {o['passed_median']:.0%}, media su tutte le gobbe {o['passed_mean_all']:.0%}")
    print(f"massimo dell'arancione rispetto al massimo del blu: {o['peak_lag_median']:+.0f} barre (mediana) | "
          f"cade dopo la fine della gobba blu nel {o['peak_after_end']:.0%} dei casi")
    print(f"  posizione del massimo arancione dentro la gobba (0 = inizio, 1 = fine): mediana {o['peak_pos_median']:.2f} | "
          f"guadagno dell'oracolo già fatto in quel momento: mediana {o['gain_at_peak_median']:.0%}")
    for lo, hi_ in ((5, 20), (20, 40), (40, 80), (80, 10 ** 6)):
        c = H[(H["len"] >= lo) & (H["len"] < hi_)]
        cd = c[c["detected"]]
        print(f"  gobbe di {lo}-{hi_ if hi_ < 10 ** 6 else '…'} barre: {len(c):5d} | guadagno medio {c['gain'].mean():+6.1%} | "
              f"accese in tempo {c['detected'].mean():4.0%} | ritardo {cd['delay'].median():3.0f} | "
              f"già passato {c['passed'].fillna(1.0).clip(0, 1).mean():4.0%} | massimo arancione dopo la fine {c['peak_after_end'].mean():4.0%}")

    E = pd.DataFrame([e for r in results for e in r["episodes"]])
    E = E[E["date"] >= A0]
    print(f"\nepisodi arancioni in salita (energia alta + prezzo sopra): {len(E)} | rendimento medio {E['ret'].mean():+.2%} | "
          f"vinti {(E['ret'] > 0).mean():.0%} | durata mediana {E['bars'].median():.0f} barre")
    out["episodes"] = {}
    for w, c in E.groupby("where"):
        out["episodes"][w] = {"share": float(len(c) / len(E)), "mean": float(c["ret"].mean()), "win": float((c["ret"] > 0).mean())}
        print(f"  nati dentro: {w:14s} {len(c) / len(E):5.0%} | rendimento medio {c['ret'].mean():+6.2%} | vinti {(c['ret'] > 0).mean():4.0%}")

    # --- C ---
    P = pd.concat([r["frame"] for r in results]).sort_index()
    names = results[0]["cell_names"]
    print("\n=== C. Cosa fa il prezzo dopo, per fase dell'arancione (rendimento in più rispetto alla media del titolo) ===")
    print(f"{'stato (prezzo rispetto al percorso, energia, fase)':46s} | {'2021-23: quota  al giorno  (t)':>30s} | {'2024-26: quota  al giorno  (t)':>30s}")
    out["cells"] = {}
    for i, nm in enumerate(names):
        line, rec = f"{nm:46s} |", {}
        for per, D in (("A", P[P.index <= A1]), ("B", P[P.index >= B0])):
            D = D.assign(ex=D["ret"] - D.groupby("ticker")["ret"].transform("mean"))
            c = D[D["cell"] == i]
            g = c["ex"].groupby(pd.Grouper(freq="W"))
            w = (g.sum() / g.count())[g.count() >= 30]
            rec[per] = {"share": float(len(c) / len(D)), "ex_bps": float(c["ex"].mean() * 1e4), "t": tstat(w.values)}
            line += f" {len(c) / len(D):12.0%} {c['ex'].mean() * 100:+9.3f}% ({tstat(w.values):+4.1f}) |"
        out["cells"][nm] = rec
        print(line)

    # --- D ---
    print("\n=== D. Regole causali: timing del portafoglio a pesi uguali (%/anno; t sulle settimane) ===")
    out["rules"] = {}
    rule_names = sorted({k[0] for r in results for k in r["weekly"]}, key=lambda s: s)
    for nm in rule_names:
        line, rec = f"{nm:52s} |", {}
        for per in ("A", "B"):
            fr = [r["weekly"][(nm, per)] for r in results if (nm, per) in r["weekly"]]
            w = pd.concat([f[0] for f in fr], axis=1).mean(axis=1)
            expo = float(np.mean([f[1] for f in fr]))
            rec[per] = {"per_year": float(w.mean() * 52 * 100), "t": tstat(w.values), "expo": expo}
            line += f" esposizione {expo:4.0%}  {w.mean() * 52 * 100:+6.1f} (t {tstat(w.values):+4.1f}) |"
        out["rules"][nm] = rec
        print(line)

    # --- E ---
    days = sum(r["agree"]["days"] for r in results)
    agree = sum(r["agree"]["agree"] for r in results)
    A_ = np.mean([r["agree"]["A"] / r["agree"]["years"] for r in results]) * 100
    D_ = np.mean([r["agree"]["D"] / r["agree"]["years"] for r in results]) * 100
    out["agree"] = {"share": agree / days, "A": float(A_), "D": float(D_), "buckets": {}}
    print("\n=== E. Dove sta il guadagno dell'oracolo (rendimento log medio per titolo, %/anno, sempre investito long/short) ===")
    print(f"giorni in cui il segno dell'arancione coincide con la direzione dell'oracolo: {agree / days:.0%}")
    print(f"  oracolo nei giorni in cui coincidono: {A_:+.1f} | oracolo nei giorni in cui NON coincidono: {D_:+.1f} | totale {A_ + D_:+.1f}")
    print(f"  seguire il segno dell'arancione = primo − secondo = {A_ - D_:+.1f}")
    print("  per distanza dall'ultima svolta dell'oracolo:")
    for lab in ("0-5", "5-10", "10-20", "20+"):
        b = [r["agree"]["buckets"][lab] for r in results]
        nd, na = sum(x[0] for x in b), sum(x[1] for x in b)
        yr = sum(r["agree"]["years"] for r in results)
        orc, cau = sum(x[2] for x in b) / yr * 100, sum(x[3] for x in b) / yr * 100
        out["agree"]["buckets"][lab] = {"share_days": nd / days, "agree": na / nd, "oracle": orc, "causal": cau}
        print(f"    {lab:>6s} barre dalla svolta: {nd / days:4.0%} dei giorni | segno giusto {na / nd:4.0%} | "
              f"oracolo {orc:+6.1f} %/anno | segno dell'arancione {cau:+6.1f} %/anno")

    # --- F ---
    I = pd.DataFrame([x for r in results for x in r["ignitions"]]).dropna(subset=["slope"])
    I["wk"] = week_ids(pd.DatetimeIndex(I["date"]))
    IA, IB = I[I["date"] <= A1], I[I["date"] >= B0]
    q1, q2 = IA["slope"].quantile([1 / 3, 2 / 3])
    out["ignition"] = {"q1": float(q1), "q2": float(q2)}
    print(f"\n=== F. Accensione dell'arancione in salita: conta la pendenza? (terzili 2021-23: {q1:+.2f}, {q2:+.2f} z in 5 barre) ===")
    for lab, sel in (("pendenza bassa", lambda d: d["slope"] <= q1), ("pendenza media", lambda d: (d["slope"] > q1) & (d["slope"] <= q2)),
                     ("pendenza alta", lambda d: d["slope"] > q2)):
        line = f"{lab:16s} |"
        for nm, d in (("A", IA), ("B", IB)):
            c = d[sel(d)]
            out["ignition"][f"{lab}_{nm}"] = {"n": int(len(c)), "mean": float(c["ret"].mean()), "win": float((c["ret"] > 0).mean()),
                                              "big": float((c["ret"] >= 0.15).mean())}
            line += (f" n {len(c):5d} media {c['ret'].mean() * 100:+5.2f}% vinte {(c['ret'] > 0).mean() * 100:3.0f}% "
                     f"≥+15% {(c['ret'] >= 0.15).mean() * 100:4.1f}% durata {c['bars'].median():3.0f} |")
        print(line)
    for nm, d in (("2021-23", IA), ("2024-26", IB)):
        diff = (d[d["slope"] > q2].groupby("wk")["ret"].mean() - d[d["slope"] <= q1].groupby("wk")["ret"].mean()).dropna()
        print(f"  alta − bassa, t settimanale {nm}: {tstat(diff.values):+.1f}")
    for nm in sorted({k[0] for r in results for k in r["weekly"] if "pendenza" in k[0]}):
        line = f"{nm:52s} |"
        for per in ("A", "B"):
            fr = [r["weekly"][(nm, per)] for r in results if (nm, per) in r["weekly"]]
            w = pd.concat([f[0] for f in fr], axis=1).mean(axis=1)
            line += f" esposizione {np.mean([f[1] for f in fr]):4.0%}  {w.mean() * 52 * 100:+6.1f} (t {tstat(w.values):+4.1f}) |"
        print(line)

    nv = next((r for r in results if r["ticker"] == "NVDA"), None)
    if nv is not None:
        c = nv["curves"]
        c = c[c.index >= "2023-11-01"]
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        c.to_csv(os.path.join(OUTPUT_DIR, "frozen_vs_energy_nvda.csv"))
    save_output("frozen_vs_energy.json", out)


if __name__ == "__main__":
    main()
