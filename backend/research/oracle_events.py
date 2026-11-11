"""
GLI INGRESSI E LE USCITE DELL'ORACOLO VISTI CON I DATI DEL GIORNO 0.

Sul grafico le linee verdi e rosse della strategia LIVE sono gli ingressi e le
uscite dell'oracolo (z della cinetica del percorso di minima azione sopra zero,
verso dato dalla pendenza). Domanda: nel giorno in cui l'oracolo entra o esce,
i dati causali (Frozen: arancione, stato, stima di oggi) hanno una forma
riconoscibile? E al contrario: quando quella forma compare, quante volte c'è
davvero un ingresso dell'oracolo?

  1. profilo: media delle grandezze causali nei giorni attorno all'evento
  2. impronta del giorno 0: quanto ogni condizione è più frequente del normale
  3. al contrario: la stessa regola dell'oracolo applicata alla stima di oggi
     ("LIVE in tempo reale") — quanti ingressi dell'oracolo prende, quanti dei
     suoi segnali sono veri, con che ritardo
  4. un modello lineare su tutte le grandezze (stimato sul 2021-23, giudicato
     sul 2024-26): riesce a riconoscere il giorno dell'ingresso?
  5. cosa rende comprare sugli ingressi riconosciuti

Tutte le grandezze causali sono calcolate con i soli dati fino a quel giorno.

    backend/venv/bin/python backend/research/oracle_events.py
    (FPR_PANEL_CACHE=percorso.pkl per riusare prezzi già scaricati)
"""
from common import np, pd, save_output, tstat
from logic import ActionPath
from kinetic_trend import load_panel, week_ids
from faster_signal import kalman
from nowcast import nowcast_velocity

A0, A1, B0 = "2021-01-01", "2023-12-31", "2024-01-01"
ALPHA, BETA, ZWIN = 200.0, 1.0, 252
REL = (-15, -10, -5, -2, 0, 2, 5, 10)
TAIL = 40                                  # ultime barre escluse: lì l'oracolo non è ancora definitivo


def zroll(x, minp=20):
    s = pd.Series(x, dtype=float)
    return ((s - s.rolling(ZWIN, min_periods=minp).mean()) / (s.rolling(ZWIN, min_periods=minp).std() + 1e-6)).fillna(0).values


def episodes(z_kin, z_slope, lo, hi):
    """Regola LIVE: dentro quando z della cinetica > 0; verso LONG se z della pendenza > 0 all'ingresso.
    Ritorna [(barra del segnale, barra del segnale di uscita, long?)]."""
    out, t = [], max(lo, 1)
    while t < hi:
        if z_kin[t] > 0 and z_kin[t - 1] <= 0:
            s = t
            while t < hi and z_kin[t] > 0:
                t += 1
            out.append((s, t, bool(z_slope[s] > 0)))
        else:
            t += 1
    return out


def per_ticker(tk, px):
    p = px.values.astype(float)
    n, idx = len(p), px.index
    if n < 700 or (p <= 0).any():
        return None
    lr = np.zeros(n)
    lr[1:] = np.log(p[1:] / p[:-1])
    sig = pd.Series(lr).ewm(span=60, min_periods=20).std().values
    Fs = px.ewm(span=20, adjust=False).mean()
    F = Fs.values.astype(float)
    xf = kalman(F, ALPHA)
    d = F - xf
    pot = 0.5 * BETA * d ** 2
    ps = pd.Series(pot)
    z_or = ((ps - ps.rolling(ZWIN, min_periods=40).mean()) / (ps.rolling(ZWIN, min_periods=40).std() + 1e-9)).fillna(0).values
    rising = pot > np.r_[np.full(3, np.nan), pot[:-3]]
    state = np.where(z_or <= 0, 0, np.where(d < 0, np.where(rising, 1, 2), np.where(rising, 3, 4)))
    vn, _ = nowcast_velocity(p, F, xf)
    vn = np.nan_to_num(vn)
    mech = ActionPath(px, alpha=ALPHA, beta=BETA)
    zk_or, zs_or = zroll(mech.kin_density.values), zroll(mech.dX.values)
    zk_now, zs_now = zroll(0.5 * ALPHA * vn ** 2), zroll(vn)

    v0 = max(260, int(np.searchsorted(idx.values, np.datetime64(A0))))
    hi = n - TAIL
    if hi - v0 < 300:
        return None
    unit = p * sig
    with np.errstate(divide="ignore", invalid="ignore"):
        f = {
            "scostamento (σ)": d / unit,
            "scostamento, variazione 3 barre": (d - np.r_[np.full(3, np.nan), d[:-3]]) / unit,
            "z energia arancione": z_or,
            "stima di oggi (σ/barra)": vn / unit,
            "stima di oggi, variazione 3 barre": (vn - np.r_[np.full(3, np.nan), vn[:-3]]) / unit,
            "prezzo − media 20 (σ)": (p - F) / unit,
            "z cinetica stima di oggi": zk_now,
            "z pendenza stima di oggi": zs_now,
            "rendimento 5 barre (σ)": (np.log(p) - np.r_[np.full(5, np.nan), np.log(p[:-5])]) / (sig * np.sqrt(5)),
            "rendimento 20 barre (σ)": (np.log(p) - np.r_[np.full(20, np.nan), np.log(p[:-20])]) / (sig * np.sqrt(20)),
        }
    X = np.column_stack(list(f.values()) + [(state == k).astype(float) for k in (1, 2, 3, 4)])
    X = np.nan_to_num(X, posinf=0.0, neginf=0.0)

    ep_or = episodes(zk_or, zs_or, v0, hi)
    ep_now = episodes(zk_now, zs_now, v0, hi)
    wk = week_ids(idx)
    live = np.zeros(n, dtype=bool)
    live[v0 + 2:hi] = True
    res = {"ticker": tk, "events": {}, "base": {}, "weekly": {}, "rules": {}}

    conds = {
        "arancione col prezzo sopra il percorso": d > 0,
        "energia arancione sopra la media": z_or > 0,
        "stato V2 (sotto + energia alta)": (state == 1) | (state == 2),
        "sopra il percorso + energia alta": (state == 3) | (state == 4),
        "V2 in una delle 20 barre prima": pd.Series(((state == 1) | (state == 2)).astype(float)).rolling(20, min_periods=1).max().values > 0,
        "stima di oggi positiva": vn > 0,
        "stima di oggi in aumento (3 barre)": vn > np.r_[np.full(3, np.nan), vn[:-3]],
        "z cinetica della stima di oggi > 0": zk_now > 0,
        "prezzo sopra la media a 20": p > F,
    }
    res["base"] = {k: float(v[live].mean()) for k, v in conds.items()}

    def collect(name, days):
        days = [t for t in days if v0 + 20 <= t < hi - 12]
        prof = {k: np.array([[v[t + r] for r in REL] for t in days]) if days else np.zeros((0, len(REL)))
                for k, v in (("d>0", d > 0), ("z_or>0", z_or > 0), ("v2", (state == 1) | (state == 2)), ("vn>0", vn > 0),
                             ("zk_now>0", zk_now > 0), ("dn", f["scostamento (σ)"]), ("vnn", f["stima di oggi (σ/barra)"]))}
        mv = np.array([[np.log(p[t] / p[t - 10]), np.log(p[t + 10] / p[t])] for t in days]) if days else np.zeros((0, 2))
        res["events"][name] = {"n": len(days), "prof": prof, "move": mv,
                               "cond": {k: (float(v[days].mean()) if days else np.nan) for k, v in conds.items()}}

    collect("ingresso LONG dell'oracolo", [s + 1 for s, e, lg in ep_or if lg])
    collect("uscita LONG dell'oracolo", [e + 1 for s, e, lg in ep_or if lg])
    collect("ingresso SHORT dell'oracolo", [s + 1 for s, e, lg in ep_or if not lg])

    # --- confronto ingressi: LIVE in tempo reale (stima di oggi) contro oracolo ---
    o_in = np.array([s for s, e, lg in ep_or if lg])
    c_in = np.array([s for s, e, lg in ep_now if lg])
    match = {"oracle": len(o_in), "causal": len(c_in), "lags": [], "hit_causal": 0}
    for s in o_in:
        if len(c_in):
            j = c_in[np.argmin(np.abs(c_in - s))]
            if -5 <= j - s <= 15:
                match["lags"].append(int(j - s))
    for s in c_in:
        if len(o_in) and np.min(np.abs(o_in - s)[(s - o_in >= -5) & (s - o_in <= 15)], initial=99) < 99:
            match["hit_causal"] += 1
    res["match"] = match

    # --- il picco dell'arancione sopra il percorso (▼ sul grafico) contro le uscite long dell'oracolo ---
    peaks, side, marked = [], 0, False
    for t in range(v0, hi):
        cur = 1 if state[t] in (3, 4) else (-1 if state[t] in (1, 2) else 0)
        if cur != side:
            side, marked = cur, False
        if not marked and state[t] == 4:
            peaks.append(t)
            marked = True
    peaks = np.array(peaks)
    o_out = np.array([e for s, e, lg in ep_or if lg and e < hi])
    pk = {"peaks": len(peaks), "exits": len(o_out), "lags": [], "peak_hit": 0, "fwd": []}
    for e in o_out:
        if len(peaks):
            j = peaks[np.argmin(np.abs(peaks - e))]
            if abs(j - e) <= 10:
                pk["lags"].append(int(j - e))
    mean10 = np.nanmean(np.log(p[v0 + 12:hi] / p[v0 + 2:hi - 10])) if hi - v0 > 30 else 0.0
    for t in peaks:
        if len(o_out) and np.min(np.abs(o_out - t)) <= 10:
            pk["peak_hit"] += 1
        if t + 12 < n:
            pk["fwd"].append((idx[t], float(np.log(p[t + 12] / p[t + 2]) - mean10)))
    res["peak"] = pk

    # --- posizioni e rendimenti: gambe long ---
    def long_state(eps):
        st = np.zeros(n, dtype=bool)
        for s, e, lg in eps:
            if lg:
                st[s:e] = True
        return st
    for name, st in (("oracolo (long)", long_state(ep_or)), ("LIVE in tempo reale (long)", long_state(ep_now)),
                     ("V2 (energia alta, sotto il percorso)", (state == 1) | (state == 2))):
        pos = np.zeros(n)
        pos[2:] = st[:-2]
        tr = [p[min(e + 1, n - 1)] / p[min(s + 1, n - 1)] - 1 for s, e, lg in (ep_or if "oracolo" in name else ep_now) if lg] \
            if "V2" not in name else []
        res["rules"][name] = {"roi": float(np.expm1((pos * lr)[live].sum())), "expo": float(pos[live].mean()), "trades": tr}
        for per, m in (("A", live & (idx <= A1)), ("B", live & (idx >= B0))):
            if m.sum() < 60:
                continue
            fr = pos[m].mean()
            res["weekly"][(name, per)] = pd.Series((pos[m] - fr) * lr[m]).groupby(wk[m]).sum()
    res["bh"] = float(np.expm1(lr[live].sum()))

    # --- dati per il modello: bersaglio = ingresso LONG dell'oracolo entro ±2 barre ---
    y = np.zeros(n)
    for s in o_in:
        y[max(s - 1, 0):s + 4] = 1.0                     # linea sul grafico = s+1; finestra s-1..s+3
    fwd = np.full(n, np.nan)
    fwd[:-12] = np.log(p[12:] / p[2:-10])                # da t+2 a t+12
    a = live & (idx <= A1)
    b = live & (idx >= B0)
    res["XA"], res["yA"] = X[a], y[a]
    res["XB"], res["yB"], res["fB"], res["dB"] = X[b], y[b], fwd[b] - np.nanmean(fwd[b]), idx[b]
    res["feat_names"] = list(f.keys()) + ["stato 1", "stato 2", "stato 3", "stato 4"]

    if tk == "AAPL":
        rows = []
        for s, e, lg in ep_or:
            if str(idx[s].date()) < "2023-11-01":
                continue
            t = s + 1
            near = c_in[(c_in - s >= -5) & (c_in - s <= 15)] if lg and len(c_in) else []
            rows.append((str(idx[t].date()), "LONG" if lg else "SHORT", str(idx[min(e + 1, n - 1)].date()),
                         float(p[min(e + 1, n - 1)] / p[t] - 1) * (1 if lg else -1), int(state[t]), float(z_or[t]),
                         float(f["stima di oggi (σ/barra)"][t]), bool(conds["V2 in una delle 20 barre prima"][t]),
                         (int(near[0] - s) if len(near) else None)))
        res["aapl"] = rows
    return res


def auc(score, y):
    order = np.argsort(score)
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


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

    # --- 1. profili ---
    for ev in ("ingresso LONG dell'oracolo", "uscita LONG dell'oracolo"):
        n_ev = sum(r["events"][ev]["n"] for r in results)
        P = {k: np.vstack([r["events"][ev]["prof"][k] for r in results if r["events"][ev]["n"]]) for k in results[0]["events"][ev]["prof"]}
        mv = np.vstack([r["events"][ev]["move"] for r in results if r["events"][ev]["n"]])
        print(f"\n=== 1. {ev.upper()}: {n_ev} eventi | prezzo nei 10 giorni prima {np.expm1(mv[:, 0].mean()):+.1%}, "
              f"nei 10 dopo {np.expm1(mv[:, 1].mean()):+.1%} ===")
        print(f"{'giorni dall evento':40s} " + " ".join(f"{r:>6d}" for r in REL))
        rows = (("prezzo sopra il percorso (arancione > 0)", "d>0", True), ("energia arancione sopra la media", "z_or>0", True),
                ("stato V2 (sotto + energia alta)", "v2", True), ("stima di oggi positiva", "vn>0", True),
                ("z cinetica della stima di oggi > 0", "zk_now>0", True),
                ("scostamento medio (σ)", "dn", False), ("stima di oggi media (σ/barra)", "vnn", False))
        out[ev] = {"n": n_ev}
        for lab, k, pct in rows:
            m = np.nanmean(P[k].astype(float), axis=0)
            out[ev][lab] = [float(v) for v in m]
            print(f"{lab:40s} " + " ".join((f"{v:6.0%}" if pct else f"{v:+6.2f}") for v in m))

    # --- 2. impronta del giorno 0 ---
    print("\n=== 2. Impronta del giorno 0: quanto spesso vale ogni condizione (tra parentesi: in un giorno qualsiasi) ===")
    base = {k: np.mean([r["base"][k] for r in results]) for k in results[0]["base"]}
    evs = ("ingresso LONG dell'oracolo", "uscita LONG dell'oracolo", "ingresso SHORT dell'oracolo")
    print(f"{'condizione':40s} {'qualsiasi':>10s} " + " ".join(f"{e.replace(' dell’oracolo', '')[:22]:>24s}" for e in evs))
    out["fingerprint"] = {}
    for k in base:
        vals = []
        for e in evs:
            w = np.array([r["events"][e]["n"] for r in results], dtype=float)
            c = np.array([r["events"][e]["cond"][k] if r["events"][e]["n"] else 0.0 for r in results])
            vals.append(float((w * c).sum() / w.sum()))
        out["fingerprint"][k] = {"base": float(base[k]), **dict(zip(evs, vals))}
        print(f"{k:40s} {base[k]:10.0%} " + " ".join(f"{v:16.0%} (×{v / base[k]:3.1f})" for v in vals))

    # --- 3. LIVE in tempo reale contro oracolo ---
    n_o = sum(r["match"]["oracle"] for r in results)
    n_c = sum(r["match"]["causal"] for r in results)
    lags = np.array([x for r in results for x in r["match"]["lags"]])
    hit = sum(r["match"]["hit_causal"] for r in results)
    out["match"] = {"oracle_entries": n_o, "causal_entries": n_c, "recall": len(lags) / n_o, "precision": hit / n_c,
                    "lag_median": float(np.median(lags)), "lag_q25": float(np.percentile(lags, 25)), "lag_q75": float(np.percentile(lags, 75))}
    print(f"\n=== 3. La regola dell'oracolo applicata alla stima di oggi (\"LIVE in tempo reale\") ===")
    print(f"ingressi long dell'oracolo: {n_o} | ingressi long in tempo reale: {n_c}")
    print(f"ingressi dell'oracolo con un ingresso in tempo reale vicino (da 5 barre prima a 15 dopo): {len(lags) / n_o:.0%} "
          f"| ritardo mediano {np.median(lags):+.0f} barre (metà dei casi tra {np.percentile(lags, 25):+.0f} e {np.percentile(lags, 75):+.0f})")
    print(f"ingressi in tempo reale che corrispondono a un ingresso dell'oracolo: {hit / n_c:.0%}  → falsi: {1 - hit / n_c:.0%}")

    # --- 3b. picco dell'arancione (▼) contro uscite long dell'oracolo ---
    n_pk = sum(r["peak"]["peaks"] for r in results)
    n_ex = sum(r["peak"]["exits"] for r in results)
    lg = np.array([x for r in results for x in r["peak"]["lags"]])
    hitp = sum(r["peak"]["peak_hit"] for r in results)
    F10 = pd.DataFrame([x for r in results for x in r["peak"]["fwd"]], columns=["date", "v"])
    out["peak"] = {"peaks": n_pk, "exits": n_ex, "recall": len(lg) / n_ex, "precision": hitp / n_pk,
                   "lag_median": float(np.median(lg)), "lag_q25": float(np.percentile(lg, 25)), "lag_q75": float(np.percentile(lg, 75))}
    print(f"\n=== 3b. Il picco dell'arancione sopra il percorso (▼) e le uscite long dell'oracolo ===")
    print(f"uscite long dell'oracolo: {n_ex} | picchi ▼: {n_pk}")
    print(f"uscite dell'oracolo con un ▼ entro 10 barre: {len(lg) / n_ex:.0%} | il ▼ arriva {np.median(lg):+.0f} barre rispetto all'uscita "
          f"(metà dei casi tra {np.percentile(lg, 25):+.0f} e {np.percentile(lg, 75):+.0f})")
    print(f"▼ che corrispondono a un'uscita dell'oracolo (entro 10 barre): {hitp / n_pk:.0%}")
    for nm, d in (("2021-23", F10[F10["date"] <= A1]), ("2024-26", F10[F10["date"] >= B0])):
        wkm = d.groupby(pd.Grouper(key="date", freq="W"))["v"].mean().dropna()
        out["peak"][nm] = {"fwd10": float(d["v"].mean()), "t": tstat(wkm.values)}
        print(f"  dopo un ▼, nei 10 giorni successivi il titolo fa {np.expm1(d['v'].mean()):+.2%} rispetto alla sua media ({nm}; t settimanale {tstat(wkm.values):+.1f}; {len(d)} casi)")

    # --- 4. modello lineare ---
    XA = np.vstack([r["XA"] for r in results])
    yA = np.concatenate([r["yA"] for r in results])
    XB = np.vstack([r["XB"] for r in results])
    yB = np.concatenate([r["yB"] for r in results])
    fB = np.concatenate([r["fB"] for r in results])
    mu, sd = XA.mean(axis=0), XA.std(axis=0) + 1e-9
    XA, XB = np.clip((XA - mu) / sd, -6, 6), np.clip((XB - mu) / sd, -6, 6)
    XA1, XB1 = np.column_stack([XA, np.ones(len(XA))]), np.column_stack([XB, np.ones(len(XB))])
    w = np.linalg.solve(XA1.T @ XA1 + 10.0 * np.eye(XA1.shape[1]), XA1.T @ yA)
    sB = XB1 @ w
    names = results[0]["feat_names"]
    out["model"] = {"auc": auc(sB, yB), "base": float(yB.mean()), "weights": dict(zip(names, [float(v) for v in w[:-1]]))}
    print(f"\n=== 4. Modello lineare (stimato 2021-23, giudicato 2024-26): oggi siamo vicini (±2 barre) a un ingresso long dell'oracolo? ===")
    print(f"giorni vicini a un ingresso, in un giorno qualsiasi: {yB.mean():.1%} | capacità di ordinare i giorni (AUC, 0.5 = a caso, 1 = perfetto): {out['model']['auc']:.2f}")
    for q in (0.01, 0.05, 0.10):
        thr = np.quantile(sB, 1 - q)
        sel = sB >= thr
        ok = np.isfinite(fB)
        out["model"][f"top{int(q * 100)}"] = {"precision": float(yB[sel].mean()), "fwd10": float(np.nanmean(fB[sel & ok]))}
        print(f"  {q:4.0%} dei giorni col punteggio più alto: vicini a un ingresso vero {yB[sel].mean():.0%} "
              f"(×{yB[sel].mean() / yB.mean():.1f}) | rendimento dei 10 giorni dopo rispetto alla media {np.expm1(np.nanmean(fB[sel & ok])):+.2%}")
    top = np.argsort(-np.abs(w[:-1]))[:6]
    print("  grandezze che pesano di più: " + "; ".join(f"{names[i]} ({w[i]:+.3f})" for i in top))

    # --- 5. risultato ---
    print("\n=== 5. Comprare sugli ingressi e vendere sulle uscite (gamba long, senza costi) ===")
    out["rules"] = {}
    for nm in results[0]["rules"]:
        roi = np.median([r["rules"][nm]["roi"] for r in results])
        expo = np.mean([r["rules"][nm]["expo"] for r in results])
        tr = np.array([x for r in results for x in r["rules"][nm]["trades"]])
        line = f"{nm:38s} ROI mediano {roi:+6.0%} | esposizione {expo:4.0%} |"
        rec = {"roi_median": float(roi), "expo": float(expo)}
        if len(tr):
            rec.update({"win": float((tr > 0).mean()), "mean_trade": float(tr.mean()), "trades": int(len(tr))})
            line += f" operazioni {len(tr)} vinte {(tr > 0).mean():4.0%} media {tr.mean():+5.1%} |"
        for per in ("A", "B"):
            wkl = pd.concat([r["weekly"][(nm, per)] for r in results if (nm, per) in r["weekly"]], axis=1).mean(axis=1)
            rec[per] = {"per_year": float(wkl.mean() * 52 * 100), "t": tstat(wkl.values)}
            line += f" timing {wkl.mean() * 52 * 100:+6.1f} (t {tstat(wkl.values):+4.1f}) |"
        out["rules"][nm] = rec
        print(line)
    print(f"compra e tieni mediano: {np.median([r['bh'] for r in results]):+.0%}")

    ap = next((r for r in results if r["ticker"] == "AAPL"), None)
    if ap is not None and "aapl" in ap:
        print("\n=== AAPL: gli ingressi dell'oracolo dal 11/2023 e i dati del giorno 0 ===")
        print("ingresso    verso  uscita      risultato | stato  z arancione  stima di oggi  V2 nelle 20 barre prima | ingresso in tempo reale")
        for d0, vs_, d1, g, st, z, vn, v2b, lag in ap["aapl"]:
            print(f"{d0}  {vs_:5s}  {d1}  {g:+8.1%} | {st:5d}  {z:+11.2f}  {vn:+13.2f}  {'sì' if v2b else 'no':>22s} | "
                  f"{('dopo ' + str(lag) + ' barre') if lag is not None and lag >= 0 else (str(-lag) + ' barre prima' if lag is not None else 'nessuno')}")
        out["aapl"] = ap["aapl"]
    save_output("oracle_events.json", out)


if __name__ == "__main__":
    main()
