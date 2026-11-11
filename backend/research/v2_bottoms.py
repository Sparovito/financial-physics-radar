"""
V2 E I MINIMI: sul lato basso l'arancione riesce ad avvicinarsi all'oracolo?

Da frozen_vs_energy.py: l'arancione è la cinetica dell'oracolo in ritardo di 9
barre; in alto arriva tardi, in basso lo stato "prezzo sotto il percorso +
energia alta" (V2) è l'unico con un vantaggio. Qui si misura:

  1. dove cade la V2 rispetto al minimo dell'oracolo (la svolta in salita del
     percorso di minima azione): quante barre prima/dopo si accende, quanto si
     perde prima del minimo, quanta parte della risalita si incassa;
  2. regole che partono dalla V2 e provano a tenere la risalita:
       V2            dentro finché energia alta e prezzo sotto il percorso
       V2 in carica  solo finché l'energia aumenta
       V2 lunga      entra con la V2, resta finché il prezzo non torna sotto il
                     percorso DOPO esserci salito sopra (esce a fine trend)
       V2 al picco   come la lunga, ma esce anche quando, sopra il percorso,
                     l'energia è alta e comincia a scendere (massimo arancione)
     con accanto "sopra il percorso" (trend puro) come riferimento.

Decisione alla chiusura t, esecuzione t+1, primo rendimento t+2.

    backend/venv/bin/python backend/research/v2_bottoms.py
    (FPR_PANEL_CACHE=percorso.pkl per riusare prezzi già scaricati)
"""
from common import np, pd, save_output, tstat
from logic import ActionPath
from kinetic_trend import load_panel, roll_z, week_ids
from frozen_vs_energy import kalman, runs

A0, A1, B0 = "2021-01-01", "2023-12-31", "2024-01-01"
ALPHA, BETA = 200.0, 1.0
DK = 3


def hold_rule(v2, d, z, ris, peak_exit=False, stop_bars=None):
    """Entra con la V2 e tiene la risalita: resta finché il prezzo, DOPO essere salito sopra il
    percorso, non torna sotto. Finché è sotto il percorso resta dentro (anche a V2 spenta:
    l'energia scende proprio mentre il prezzo si riavvicina al percorso).
    peak_exit: esce anche quando, sopra il percorso, l'energia è alta e comincia a scendere.
    stop_bars: esce se dopo tante barre dall'ultima V2 il prezzo non è mai salito sopra."""
    n = len(v2)
    st = np.zeros(n, dtype=bool)
    inp, above, wait = False, False, 0
    for t in range(n):
        if d[t] != d[t] or z[t] != z[t]:
            inp = False
            continue
        if not inp:
            if v2[t]:
                inp, above, wait = True, False, 0
        else:
            if d[t] > 0:
                above = True
            wait = 0 if (v2[t] or above) else wait + 1
            out = above and d[t] < 0
            if peak_exit and above and d[t] > 0 and z[t] > 0 and not ris[t]:
                out = True
            if stop_bars and wait >= stop_bars:
                out = True
            if out:
                inp = False
        st[t] = inp
    return st


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
    z = np.array(roll_z(pd.Series(orange), minp=40).values, dtype=float)
    z[:260] = np.nan
    ris = orange > np.r_[np.full(DK, np.nan), orange[:-DK]]
    vs = ActionPath(px, alpha=ALPHA, beta=BETA).dX.values
    v0 = max(260, int(np.searchsorted(idx.values, np.datetime64(A0))))
    if n - v0 < 300:
        return None
    v2 = (z > 0) & (d < 0)

    rules = {
        "V2": v2,
        "V2 in carica": v2 & ris,
        "V2 lunga (esce a fine trend)": hold_rule(v2, d, z, ris),
        "V2 lunga, fuori dopo 40 barre senza risalita": hold_rule(v2, d, z, ris, stop_bars=40),
        "V2 al picco (esce al massimo arancione)": hold_rule(v2, d, z, ris, peak_exit=True),
        "sopra il percorso (trend puro)": d > 0,
    }

    live = np.zeros(n, dtype=bool)
    live[v0 + 2:] = True
    live &= np.isfinite(np.r_[np.full(2, np.nan), z[:-2]])
    wk = week_ids(idx)
    res = {"ticker": tk, "weekly": {}, "rules": {}, "bottoms": []}
    up = vs > 0
    yrs = max(live.sum() / 252.0, 0.5)

    pos_of = {}
    for nm, st in rules.items():
        pos = np.zeros(n)
        pos[2:] = st[:-2]
        pos_of[nm] = pos
        earn = pos * lr
        r = {"expo": float(pos[live].mean()), "roi": float(np.expm1(earn[live].sum())),
             "bh": float(np.expm1(lr[live].sum())),
             "in_down": float(earn[live & ~up].sum() / yrs), "in_up": float(earn[live & up].sum() / yrs)}
        trades = []
        for s, e in runs(st & np.r_[np.zeros(v0, dtype=bool), np.ones(n - v0, dtype=bool)], 1):
            a, b = min(s + 1, n - 1), min(e + 2, n - 1)
            if b > a:
                trades.append((str(idx[a].date()), float(p[b] / p[a] - 1), int(b - a)))
        r["trades"] = trades
        res["rules"][nm] = r
        for per, m in (("A", live & (idx <= A1)), ("B", live & (idx >= B0))):
            if m.sum() < 60:
                continue
            f = pos[m].mean()
            res["weekly"][(nm, per)] = (pd.Series((pos[m] - f) * lr[m]).groupby(wk[m]).sum(), float(f))

    # --- i minimi dell'oracolo: svolta in salita del percorso ---
    turns_up = [t for t in range(max(v0, 1), n) if up[t] and not up[t - 1]]
    turns_dn = [t for t in range(max(v0, 1), n) if not up[t] and up[t - 1]]
    for t0 in turns_up:
        t1 = next((t for t in turns_dn if t > t0), None)
        tp = next((t for t in reversed(turns_dn) if t < t0), None)
        if t1 is None or tp is None or t1 + 3 >= n:
            continue
        b0 = t0 - 1                                       # barra del minimo del percorso
        G = np.log(p[t1 - 1] / p[b0])
        fall = np.log(p[b0] / p[tp - 1])
        if G < 0.03:
            continue
        win = v2[max(tp, b0 - 30):b0 + 11]
        first = next((t for t in range(max(tp, b0 - 60), b0 + 11) if v2[t]), None)
        rec = {"rise": float(G), "fall": float(fall), "len": int(t1 - t0), "v2_near": bool(win.any()),
               "lead": None if first is None else int(first - b0)}
        for nm, pos in pos_of.items():
            rec[f"cap|{nm}"] = float((pos * lr)[b0 + 1:t1].sum() / G)
            rec[f"pre|{nm}"] = float((pos * lr)[tp:b0 + 1].sum())
        res["bottoms"].append(rec)
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
    names = list(results[0]["rules"].keys())
    out = {"n_tickers": len(results), "rules": {}}
    print(f"titoli: {len(results)}")

    Bm = pd.DataFrame([b for r in results for b in r["bottoms"]])
    near = Bm[Bm["v2_near"]]
    out["bottoms"] = {"n": int(len(Bm)), "v2_near": float(Bm["v2_near"].mean()),
                      "rise_mean_with": float(np.expm1(near["rise"]).mean()),
                      "rise_mean_without": float(np.expm1(Bm[~Bm["v2_near"]]["rise"]).mean()),
                      "fall_mean_with": float(np.expm1(near["fall"]).mean()),
                      "fall_mean_without": float(np.expm1(Bm[~Bm["v2_near"]]["fall"]).mean()),
                      "lead_median": float(near["lead"].median()), "lead_q25": float(near["lead"].quantile(.25)),
                      "lead_q75": float(near["lead"].quantile(.75))}
    o = out["bottoms"]
    print(f"\n=== 1. Minimi dell'oracolo seguiti da una risalita di almeno +3%: {o['n']} ===")
    print(f"con la V2 accesa vicino al minimo (da 30 barre prima a 10 dopo): {o['v2_near']:.0%}")
    print(f"  con V2: discesa precedente {o['fall_mean_with']:+.1%}, risalita successiva {o['rise_mean_with']:+.1%} | "
          f"senza V2: discesa {o['fall_mean_without']:+.1%}, risalita {o['rise_mean_without']:+.1%}")
    print(f"  prima accensione della V2 rispetto al minimo: mediana {o['lead_median']:+.0f} barre "
          f"(metà dei casi tra {o['lead_q25']:+.0f} e {o['lead_q75']:+.0f})")
    print(f"\n{'regola':46s} | {'perso prima del minimo':>22s} | {'quota di risalita incassata (media / mediana)':>46s}")
    for nm in names:
        pre, cap = near[f"pre|{nm}"], near[f"cap|{nm}"]
        capw = (near[f"cap|{nm}"] * near["rise"]).sum() / near["rise"].sum()
        out["rules"][nm] = {"pre_mean": float(np.expm1(pre.mean())), "cap_mean": float(cap.mean()),
                            "cap_median": float(cap.median()), "cap_weighted": float(capw)}
        print(f"{nm:46s} | {np.expm1(pre.mean()):+21.1%} | media {cap.mean():5.0%}  mediana {cap.median():5.0%}  pesata {capw:5.0%}")

    print("\n=== 2. Dove nasce il rendimento (log %/anno per titolo): mentre l'oracolo scende / mentre sale ===")
    print(f"{'regola':46s} {'espos.':>6s} {'oracolo giù':>12s} {'oracolo su':>11s} {'totale':>8s} | {'operaz.':>7s} {'vinte':>6s} {'media':>7s} {'giorni':>6s} | {'ROI med.':>8s}")
    for nm in names:
        dn = np.mean([r["rules"][nm]["in_down"] for r in results]) * 100
        upv = np.mean([r["rules"][nm]["in_up"] for r in results]) * 100
        expo = np.mean([r["rules"][nm]["expo"] for r in results])
        tr = [t for r in results for t in r["rules"][nm]["trades"]]
        g = np.array([t[1] for t in tr])
        dd = np.array([t[2] for t in tr])
        roi = np.median([r["rules"][nm]["roi"] for r in results])
        out["rules"][nm].update({"expo": float(expo), "in_down": float(dn), "in_up": float(upv), "trades": len(tr),
                                 "win": float((g > 0).mean()), "mean_trade": float(g.mean()),
                                 "median_days": float(np.median(dd)), "roi_median": float(roi)})
        print(f"{nm:46s} {expo:5.0%} {dn:+12.1f} {upv:+11.1f} {dn + upv:+8.1f} | {len(tr):7d} {(g > 0).mean():5.0%} "
              f"{g.mean():+6.1%} {np.median(dd):6.0f} | {roi:+7.0%}")
    bh = np.median([r["rules"][names[0]]["bh"] for r in results])
    print(f"compra e tieni, mediana per titolo: {bh:+.0%}")

    print("\n=== 3. Timing del portafoglio a pesi uguali (%/anno; t sulle settimane) ===")
    for nm in names:
        line = f"{nm:46s} |"
        for per in ("A", "B"):
            fr = [r["weekly"][(nm, per)] for r in results if (nm, per) in r["weekly"]]
            w = pd.concat([f[0] for f in fr], axis=1).mean(axis=1)
            half = len(w) // 2
            out["rules"][nm][per] = {"per_year": float(w.mean() * 52 * 100), "t": tstat(w.values),
                                     "expo": float(np.mean([f[1] for f in fr]))}
            line += (f" espos. {np.mean([f[1] for f in fr]):4.0%}  {w.mean() * 52 * 100:+6.1f} (t {tstat(w.values):+4.1f}; "
                     f"metà {tstat(w.values[:half]):+.1f}/{tstat(w.values[half:]):+.1f}) |")
        print(line)
    save_output("v2_bottoms.json", out)


if __name__ == "__main__":
    main()
