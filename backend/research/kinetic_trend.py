"""
CINETICA → SALITE GROSSE: la regola "entra quando Kinetic Z > 0 e sale con una
bella pendenza, esci quando torna a 0" prende davvero le salite grosse?

La curva viola del pannello "Kinetic Z" è lo z-score (252 barre) dell'energia
cinetica del percorso di minima azione calcolato su TUTTA la storia caricata:
il valore di un giorno passato dipende anche dai prezzi venuti dopo. Sul
grafico di oggi è la cinetica dell'ORACOLO. Quello che si vedeva quel giorno
era solo il bordo destro della curva di allora.

Lo script prova la stessa regola su tre versioni della curva:
  ORACOLO  la curva come è disegnata oggi (non eseguibile: usa il futuro)
  BORDO    la curva come era disegnata QUEL giorno (ricalcolata ogni giorno
           con i soli dati disponibili: identica a /analyze con end_date = t)
  RITARDO  il punto di L barre fa della curva di quel giorno (più stabile,
           ma in ritardo di L barre)
e su una cinetica causale vera (filtro a 2 stati, velocità del trend in sigma),
con accanto due inseguitori di trend di riferimento (STABLE e media a 200).

Regola (uguale per tutte):
  ingresso  z > 0  E  z − z di 5 barre prima > pendenza  E  percorso in salita
  uscita    z ≤ 0  (variante "+dir": anche se il percorso gira in discesa)
Decisione alla chiusura t, esecuzione alla chiusura t+1, primo rendimento t+2.

Misure:
  - timing del portafoglio a pesi uguali (%/anno, t sulle settimane), periodi
    2021-23 e 2024-26;
  - cattura delle salite grosse: salita ≥ +40% senza mai un ritracciamento del
    15% (definita a posteriori sul prezzo). Per ogni salita: quota del guadagno
    incassata, quanta parte era già passata all'ingresso;
  - rendimento dentro e fuori dalle salite grosse.

    backend/venv/bin/python backend/research/kinetic_trend.py
    (FPR_PANEL_CACHE=percorso.pkl per riusare prezzi già scaricati)
"""
import pickle

from common import os, np, pd, save_output, fetch_prices, tstat
from logic import ActionPath, kalman_llt_velocity

FETCH_START = "2019-06-01"
A0, A1, B0 = "2021-01-01", "2023-12-31", "2024-01-01"
ALPHA, BETA = 200.0, 1.0
ZWIN = 252
K = 5                       # barre su cui si misura la pendenza della curva
LAGS = (5, 10, 20)          # ritardi provati
JMAX = max(LAGS) + K
L = JMAX + ZWIN + 1         # profondità della "curva vista quel giorno"
REV, BIG = 0.15, 0.40       # ritracciamento che chiude una salita; salita grossa
SLOPES = (0.0, 0.25, 0.5)


def load_panel():
    cache = os.environ.get("FPR_PANEL_CACHE")
    if cache and os.path.exists(cache):
        return pickle.load(open(cache, "rb"))["px"]
    from tickers_loader import load_tickers
    return fetch_prices(sorted(load_tickers()), FETCH_START, min_len=400, workers=8)


def edge_view(F):
    """S[j, t] = percorso di minima azione nel punto t−j, calcolato coi dati fino a t.
    Filtro di Kalman in avanti + ricorsione RTS all'indietro, vettoriale in t
    (stessa matematica di logic.kalman_frozen_series)."""
    n = len(F)
    q, r = 1.0 / ALPHA, 1.0 / BETA
    xf, Pf = np.empty(n), np.empty(n)
    xf[0], Pf[0] = F[0], r
    for t in range(1, n):
        Pp = Pf[t - 1] + q
        g = Pp / (Pp + r)
        xf[t] = xf[t - 1] + g * (F[t] - xf[t - 1])
        Pf[t] = (1 - g) * Pp
    C = Pf / (Pf + q)
    S = np.full((L + 1, n), np.nan)
    S[0] = xf
    for j in range(1, min(L, n - 1) + 1):
        S[j, j:] = xf[:n - j] + C[:n - j] * (S[j - 1, j:] - xf[:n - j])
    return S


def z_rows(kin, jmax):
    """z-score a 252 barre della cinetica 'vista quel giorno', per i punti t−0..t−jmax."""
    zero = np.zeros((1, kin.shape[1]))
    c1 = np.vstack([zero, np.cumsum(kin, axis=0)])
    c2 = np.vstack([zero, np.cumsum(kin ** 2, axis=0)])
    out = np.empty((jmax + 1, kin.shape[1]))
    for j in range(jmax + 1):
        m = (c1[j + ZWIN] - c1[j]) / ZWIN
        v = (c2[j + ZWIN] - c2[j] - ZWIN * m ** 2) / (ZWIN - 1)
        out[j] = (kin[j] - m) / (np.sqrt(np.clip(v, 0, None)) + 1e-6)
    return out


def roll_z(s, minp=20):
    return ((s - s.rolling(ZWIN, min_periods=minp).mean()) / (s.rolling(ZWIN, min_periods=minp).std() + 1e-6))


def run_rule(z, slope, rising, s, exit_dir=False):
    n = len(z)
    state = np.zeros(n)
    inp = False
    for t in range(n):
        zt = z[t]
        if zt != zt or slope[t] != slope[t]:
            inp = False
            continue
        if not inp:
            if zt > 0 and slope[t] > s and rising[t]:
                inp = True
        elif zt <= 0 or (exit_dir and not rising[t]):
            inp = False
        state[t] = inp
    return state


def up_legs(p, lo, rev=REV):
    """Salite (minimo → massimo) separate da ritracciamenti di almeno `rev`. Definite a posteriori."""
    legs, mode = [], None
    hi_i = lo_i = start = lo
    for i in range(lo + 1, len(p)):
        if mode is None:
            hi_i = i if p[i] > p[hi_i] else hi_i
            lo_i = i if p[i] < p[lo_i] else lo_i
            if p[i] >= p[lo_i] / (1 - rev):
                mode, start, hi_i = "up", lo_i, i
            elif p[i] <= p[hi_i] * (1 - rev):
                mode, lo_i = "down", i
        elif mode == "up":
            if p[i] > p[hi_i]:
                hi_i = i
            elif p[i] <= p[hi_i] * (1 - rev):
                legs.append((start, hi_i))
                mode, lo_i = "down", i
        else:
            if p[i] < p[lo_i]:
                lo_i = i
            elif p[i] >= p[lo_i] / (1 - rev):
                mode, start, hi_i = "up", lo_i, i
    if mode == "up":
        legs.append((start, hi_i))
    return legs


def week_ids(idx):
    return (idx.values.astype("datetime64[D]").astype(np.int64) + 3) // 7


def trades_of(state, p, v0):
    out, n, t = [], len(p), max(v0, 1)
    while t < n:
        if state[t] and not state[t - 1]:
            e = t
            while t < n and state[t]:
                t += 1
            a, b = min(e + 1, n - 1), min(t + 1, n - 1)   # esecuzioni a t+1
            if b > a:
                out.append((a, b, p[b] / p[a] - 1))
        else:
            t += 1
    return out


def per_ticker(tk, px):
    p = px.values.astype(float)
    n, idx = len(p), px.index
    lr = np.zeros(n)
    lr[1:] = np.log(p[1:] / p[:-1])

    # --- la curva "vista quel giorno" ---
    F = px.ewm(span=20, adjust=False).mean().values.astype(float)
    S = edge_view(F)
    dS = S[:-1] - S[1:]
    Z = z_rows(0.5 * ALPHA * dS ** 2, JMAX)

    # --- la curva di oggi (oracolo) ---
    ap = ActionPath(px, alpha=ALPHA, beta=BETA)
    z_or = roll_z(ap.kin_density).fillna(0).values
    up_or = (ap.dX > 0).values
    sl_or = np.r_[np.full(K, np.nan), z_or[K:] - z_or[:-K]]

    # --- cinetica causale vera: velocità del trend (2 stati), in sigma ---
    lp = np.log(px)
    sig = lp.diff().ewm(span=60, min_periods=20).std()
    kk = pd.Series(kalman_llt_velocity(lp, 1e-5)["velocity"], index=idx) / sig
    zT = roll_z(0.5 * kk ** 2, minp=40)
    sl_T = (zT - zT.shift(K)).values
    up_T = (kk > 0).values

    valid = np.isfinite(Z[JMAX]) & np.isfinite(Z[JMAX - K]) & np.isfinite(zT.values) & np.isfinite(sl_T)
    if not valid.any():
        return None
    v0 = max(int(np.argmax(valid)), int(np.searchsorted(idx.values, np.datetime64(A0))))
    if n - v0 < 300:
        return None

    states = {}
    for s in SLOPES:
        states[f"ORACOLO p{s}"] = run_rule(z_or, sl_or, up_or, s)
        states[f"BORDO p{s}"] = run_rule(Z[0], Z[0] - Z[K], dS[0] > 0, s)
    states["BORDO p0.25 +dir"] = run_rule(Z[0], Z[0] - Z[K], dS[0] > 0, 0.25, exit_dir=True)
    for lag in LAGS:
        states[f"RITARDO {lag} p0.25"] = run_rule(Z[lag], Z[lag] - Z[lag + K], dS[lag] > 0, 0.25)
    states["RITARDO 10 p0.25 +dir"] = run_rule(Z[10], Z[10] - Z[10 + K], dS[0] > 0, 0.25, exit_dir=True)
    states["2 STATI p0.25"] = run_rule(zT.values, sl_T, up_T, 0.25)
    states["2 STATI p0.25 +dir"] = run_rule(zT.values, sl_T, up_T, 0.25, exit_dir=True)
    slope = px.ewm(span=20, adjust=False).mean().diff().fillna(0).ewm(span=14, adjust=False).mean().values
    states["STABLE (trend)"] = (slope > 0).astype(float)
    states["MEDIA 200"] = (px > px.rolling(200).mean()).values.astype(float)
    states["SEMPRE DENTRO"] = np.ones(n)

    wk = week_ids(idx)
    live = np.zeros(n, dtype=bool)
    live[v0 + 2:] = True
    masks = {"A": live & (idx <= A1), "B": live & (idx >= B0), "ALL": live}

    legs = [(a, b) for a, b in up_legs(p, v0 + 1) if np.log(p[b] / p[a]) >= np.log(1 + BIG)]
    in_leg = np.zeros(n, dtype=bool)
    for a, b in legs:
        in_leg[a + 1:b + 1] = True
    years = max((idx[-1] - idx[v0]).days / 365.25, 0.5)

    res = {"ticker": tk, "rules": {}, "weekly": {}, "legs": {}, "n_legs": len(legs)}
    for name, st in states.items():
        pos = np.zeros(n)
        pos[2:] = st[:-2]
        earn = pos * lr
        r = {}
        for per, m in masks.items():
            if m.sum() < 60:
                continue
            f = pos[m].mean()
            x = earn[m] - f * lr[m]
            r[per] = {"expo": float(f), "roi": float(np.expm1(earn[m].sum())), "bh": float(np.expm1(lr[m].sum()))}
            res["weekly"][(name, per)] = pd.Series(x).groupby(wk[m]).sum()
        tr = trades_of(st, p, v0)
        r["trades"] = [(str(idx[a].date()), str(idx[b].date()), float(g), int(b - a)) for a, b, g in tr]
        m = masks["ALL"]
        r["inside"] = float(earn[m & in_leg].sum() / years)
        r["outside"] = float(earn[m & ~in_leg].sum() / years)
        res["rules"][name] = r

        rows = []
        for a, b in legs:
            G = np.log(p[b] / p[a])
            cap = earn[a + 1:b + 1].sum() / G
            inpos = np.nonzero(pos[a + 1:b + 1] > 0)[0]
            missed = 1.0 if len(inpos) == 0 else float(np.log(p[a + inpos[0]] / p[a]) / G)
            late = None if len(inpos) == 0 else int(inpos[0])
            rows.append((float(np.expm1(G)), float(cap), missed, late, str(idx[a].date()), str(idx[b].date())))
        res["legs"][name] = rows

    # --- quanto la curva di oggi è diversa da quella vista quel giorno ---
    so = states["ORACOLO p0.25"]
    m = live & (so > 0)
    res["repaint"] = {
        "days_oracle_in": int(m.sum()),
        "edge_z_pos": int((Z[0][m] > 0).sum()),
        "edge_rule_in": int((states["BORDO p0.25"][m] > 0).sum()),
        "corr": float(np.corrcoef(z_or[live], Z[0][live])[0, 1]) if live.sum() > 50 else float("nan"),
        "days": int(live.sum()), "edge_pos_days": int((Z[0][live] > 0).sum()),
        "edge_max": float(np.nanmax(Z[0][live])), "edge_median": float(np.nanmedian(Z[0][live])),
        "today_pos_days": int((z_or[live] > 0).sum()),
    }
    # dopo quante barre la gobba viola compare sopra il giorno di partenza dell'oracolo
    emerg = []
    for t0 in np.nonzero((so[1:] > 0) & (so[:-1] == 0))[0] + 1:
        if t0 < v0 or t0 + JMAX >= n:
            continue
        # primo giorno T in cui la curva disegnata a T mostra un punto sopra zero dopo t0
        T = next((T for T in range(t0, min(t0 + 120, n))
                  if (Z[:min(T - t0, JMAX) + 1, T] > 0).any()), None)
        t1 = next((u for u in range(t0, n) if so[u] == 0), n - 1)      # fine dell'operazione dell'oracolo
        tot = float(np.log(p[min(t1 + 1, n - 1)] / p[min(t0 + 1, n - 1)]))
        emerg.append((None if T is None else T - t0,
                      None if T is None else float(np.log(p[T] / p[t0])), tot, t1 - t0))
    res["emerg"] = emerg

    # partenze del trend (STABLE gira in salita) con l'energia misurata quel giorno
    kf = pd.Series(kalman_llt_velocity(lp, 1e-3)["velocity"], index=idx) / sig
    dpot = pd.Series(0.5 * BETA * (F - S[0]) ** 2, index=idx)
    feats = pd.DataFrame({
        "cinetica veloce": kf, "cinetica lenta": kk, "accelerazione": kk - kk.shift(K),
        "z potenziale": roll_z(dpot, minp=40), "scostamento": pd.Series(F - S[0], index=idx),
        "distanza dai massimi": px / px.rolling(252).max() - 1,
        "spinta a 20 barre": (lp - lp.shift(20)) / (sig * np.sqrt(20)),
        "volatilita relativa": sig / lp.diff().ewm(span=252, min_periods=120).std(),
    }, index=idx)
    stb = states["STABLE (trend)"]
    rows = []
    for a, b, g in trades_of(stb, p, v0):
        t = a - 1                                  # giorno della decisione
        rows.append({"ticker": tk, "date": idx[t], **feats.iloc[t].to_dict(), "ret": float(g), "bars": int(b - a),
                     "in_leg": bool(in_leg[min(a + 1, n - 1)])})
    res["starts"] = rows
    res["stable_state"] = pd.Series(stb, index=idx).iloc[v0:]

    res["curves"] = None
    if tk == "NVDA":
        res["curves"] = pd.DataFrame({"px": p, "z_oggi": z_or, "z_quel_giorno": Z[0], "z_10_barre_fa": Z[10],
                                      "oracolo": so, "bordo": states["BORDO p0.25"],
                                      "ritardo10": states["RITARDO 10 p0.25"]}, index=idx)
    return res


def portfolio_timing(results, name, per):
    frames = [r["weekly"][(name, per)] for r in results if (name, per) in r["weekly"]]
    w = pd.concat(frames, axis=1).mean(axis=1)
    half = len(w) // 2
    return {"per_year": float(w.mean() * 52 * 100), "t": tstat(w.values),
            "t1": tstat(w.values[:half]), "t2": tstat(w.values[half:]), "weeks": int(len(w))}


def starts(results, out):
    """All'ingresso del trend l'energia distingue le salite vere dalle false partenze?
    Terzili fissati sul 2021-23 e riusati tali e quali sul 2024-26."""
    E = pd.DataFrame([row for r in results for row in r["starts"]])
    br = pd.concat([r["stable_state"] for r in results], axis=1)
    breadth = br.mean(axis=1)[br.count(axis=1) >= 300]
    E["quota titoli in trend"] = breadth.reindex(E["date"]).values
    E["wk"] = week_ids(pd.DatetimeIndex(E["date"]))
    feats = ["cinetica veloce", "cinetica lenta", "accelerazione", "z potenziale", "distanza dai massimi",
             "spinta a 20 barre", "volatilita relativa", "quota titoli in trend"]
    A, B = E[E["date"] <= A1], E[E["date"] >= B0]
    print(f"\n=== ALLA PARTENZA DEL TREND: l'energia distingue le salite vere dalle false partenze? ===")
    for nm, d in (("2021-23", A), ("2024-26", B)):
        print(f"partenze {nm}: {len(d)} | rendimento medio {d['ret'].mean():+.2%} | vinte {(d['ret'] > 0).mean():.0%} | "
              f"≥ +15%: {(d['ret'] >= 0.15).mean():.1%} | dentro una salita grossa: {d['in_leg'].mean():.0%}")
    out["starts"] = {}
    print(f"{'grandezza (terzile)':32s} | {'2021-23: media  vinte  ≥+15%  in salita':>40s} | {'2024-26: media  vinte  ≥+15%  in salita':>40s}")
    for f in feats:
        q1, q2 = A[f].quantile([1 / 3, 2 / 3])
        rec = {}
        for lab, sel in (("basso", lambda d: d[f] <= q1), ("medio", lambda d: (d[f] > q1) & (d[f] <= q2)),
                         ("alto", lambda d: d[f] > q2)):
            line = f"{f + ' ' + lab:32s} |"
            for nm, d in (("A", A), ("B", B)):
                c = d[sel(d)]
                rec[f"{lab}_{nm}"] = {"n": int(len(c)), "mean": float(c["ret"].mean()), "win": float((c["ret"] > 0).mean()),
                                      "big": float((c["ret"] >= 0.15).mean()), "in_leg": float(c["in_leg"].mean())}
                line += f" {c['ret'].mean() * 100:+13.2f}% {(c['ret'] > 0).mean() * 100:5.0f}% {(c['ret'] >= 0.15).mean() * 100:5.1f}% {c['in_leg'].mean() * 100:8.0f}% |"
            print(line)
        ts = []
        for nm, d in (("A", A), ("B", B)):
            hi = d[d[f] > q2].groupby("wk")["ret"].mean()
            lo = d[d[f] <= q1].groupby("wk")["ret"].mean()
            diff = (hi - lo).dropna()
            ts.append(tstat(diff.values))
            rec[f"t_{nm}"] = ts[-1]
        print(f"{'   alto − basso, t settimanale':32s} | {ts[0]:+.1f} (2021-23) | {ts[1]:+.1f} (2024-26)")
        out["starts"][f] = rec

    # il potenziale alto alla partenza: prezzo sotto o sopra il percorso?
    q2 = A["z potenziale"].quantile(2 / 3)
    print(f"-- z potenziale alla partenza: sopra zero nel {(E['z potenziale'] > 0).mean():.1%} dei casi; "
          f"terzile alto = sopra {q2:+.2f}. Diviso per posizione del prezzo rispetto al percorso:")
    for lab, sel in (("terzile alto, prezzo SOTTO il percorso", lambda d: (d["z potenziale"] > q2) & (d["scostamento"] < 0)),
                     ("terzile alto, prezzo SOPRA il percorso", lambda d: (d["z potenziale"] > q2) & (d["scostamento"] > 0)),
                     ("resto", lambda d: d["z potenziale"] <= q2)):
        line = f"{lab:38s} |"
        rec = {}
        for nm, d in (("A", A), ("B", B)):
            c = d[sel(d)]
            w = (c.groupby("wk")["ret"].mean() - d.groupby("wk")["ret"].mean()).dropna()
            rec[nm] = {"n": int(len(c)), "mean": float(c["ret"].mean()), "win": float((c["ret"] > 0).mean()),
                       "big": float((c["ret"] >= 0.15).mean()), "t_vs_all": tstat(w.values)}
            line += (f" n {len(c):5d} media {c['ret'].mean() * 100:+5.2f}% vinte {(c['ret'] > 0).mean() * 100:3.0f}% "
                     f"≥+15% {(c['ret'] >= 0.15).mean() * 100:4.1f}% (t {tstat(w.values):+.1f}) |")
        print(line)
        out["starts"][lab] = rec


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
    print(f"titoli: {len(results)} | salite grosse (≥ +{BIG:.0%} senza ritracciare del {REV:.0%}): "
          f"{sum(r['n_legs'] for r in results)}")

    out = {"n_tickers": len(results), "rules": {}}
    print("\n=== TIMING del portafoglio a pesi uguali (%/anno; t sulle settimane) ===")
    print(f"{'regola':24s} {'espos.':>6s} | {'2021-23':>16s} | {'2024-26':>16s} | {'tutto':>22s}")
    for nm in names:
        row = {}
        for per in ("A", "B", "ALL"):
            row[per] = portfolio_timing(results, nm, per)
        expo = np.mean([r["rules"][nm]["ALL"]["expo"] for r in results if "ALL" in r["rules"][nm]])
        row["expo"] = float(expo)
        out["rules"][nm] = row
        print(f"{nm:24s} {expo * 100:5.0f}% | {row['A']['per_year']:+7.1f} (t {row['A']['t']:+4.1f}) | "
              f"{row['B']['per_year']:+7.1f} (t {row['B']['t']:+4.1f}) | "
              f"{row['ALL']['per_year']:+7.1f} (t {row['ALL']['t']:+4.1f}; {row['ALL']['t1']:+.1f}/{row['ALL']['t2']:+.1f})")

    print("\n=== OPERAZIONI e risultato per titolo (2021 → oggi, senza costi) ===")
    print(f"{'regola':24s} {'operaz.':>8s} {'vinte':>6s} {'media':>7s} {'mediana':>8s} {'giorni':>6s} | "
          f"{'ROI med.':>8s} {'B&H med.':>8s} {'batte B&H':>9s}")
    for nm in names:
        tr = [t for r in results for t in r["rules"][nm]["trades"]]
        g = np.array([t[2] for t in tr]) if tr else np.array([0.0])
        d = np.array([t[3] for t in tr]) if tr else np.array([0])
        roi = np.array([r["rules"][nm]["ALL"]["roi"] for r in results if "ALL" in r["rules"][nm]])
        bh = np.array([r["rules"][nm]["ALL"]["bh"] for r in results if "ALL" in r["rules"][nm]])
        out["rules"][nm].update({"trades": len(tr), "win": float((g > 0).mean()), "mean_trade": float(g.mean()),
                                 "median_trade": float(np.median(g)), "median_days": float(np.median(d)),
                                 "roi_median": float(np.median(roi)), "bh_median": float(np.median(bh)),
                                 "beats_bh": float((roi > bh).mean())})
        print(f"{nm:24s} {len(tr):8d} {(g > 0).mean() * 100:5.0f}% {g.mean() * 100:+6.1f}% {np.median(g) * 100:+7.1f}% "
              f"{np.median(d):6.0f} | {np.median(roi) * 100:+7.0f}% {np.median(bh) * 100:+7.0f}% {(roi > bh).mean() * 100:8.0f}%")

    print("\n=== CATTURA delle salite grosse ===")
    print(f"{'regola':24s} {'cattura med.':>12s} {'media':>6s} {'≥ metà':>7s} {'zero':>6s} {'già passato':>11s} {'ritardo gg':>10s}"
          f" | per ampiezza: 40-80% / 80-150% / >150%")
    for nm in names:
        rows = [x for r in results for x in r["legs"][nm]]
        cap = np.array([x[1] for x in rows])
        mis = np.array([x[2] for x in rows])
        late = np.array([x[3] for x in rows if x[3] is not None])
        size = np.array([x[0] for x in rows])
        by = [np.median(cap[(size >= lo) & (size < hi)]) for lo, hi in ((0.4, 0.8), (0.8, 1.5), (1.5, 1e9))]
        out["rules"][nm].update({"capture_median": float(np.median(cap)), "capture_mean": float(cap.mean()),
                                 "capture_half": float((cap >= 0.5).mean()), "capture_zero": float((cap <= 0.02).mean()),
                                 "missed_median": float(np.median(mis)), "late_median": float(np.median(late)),
                                 "capture_by_size": [float(v) for v in by], "legs": len(rows)})
        print(f"{nm:24s} {np.median(cap) * 100:11.0f}% {cap.mean() * 100:5.0f}% {(cap >= 0.5).mean() * 100:6.0f}% "
              f"{(cap <= 0.02).mean() * 100:5.0f}% {np.median(mis) * 100:10.0f}% {np.median(late):10.0f}"
              f" | {by[0] * 100:.0f}% / {by[1] * 100:.0f}% / {by[2] * 100:.0f}%")

    print("\n=== DENTRO e FUORI dalle salite grosse (rendimento log medio per titolo, %/anno) ===")
    print(f"{'regola':24s} {'dentro':>8s} {'fuori':>8s} {'totale':>8s}")
    for nm in names:
        ins = np.mean([r["rules"][nm]["inside"] for r in results]) * 100
        outs = np.mean([r["rules"][nm]["outside"] for r in results]) * 100
        out["rules"][nm].update({"inside": float(ins), "outside": float(outs)})
        print(f"{nm:24s} {ins:+8.1f} {outs:+8.1f} {ins + outs:+8.1f}")

    rp = {k: sum(r["repaint"][k] for r in results) for k in ("days_oracle_in", "edge_z_pos", "edge_rule_in")}
    corr = np.nanmedian([r["repaint"]["corr"] for r in results])
    days = sum(r["repaint"]["days"] for r in results)
    edge_pos = sum(r["repaint"]["edge_pos_days"] for r in results)
    today_pos = sum(r["repaint"]["today_pos_days"] for r in results)
    edge_max = max(r["repaint"]["edge_max"] for r in results)
    edge_med = float(np.median([r["repaint"]["edge_median"] for r in results]))
    out["repaint"] = {**rp, "corr_median": float(corr), "days": days, "edge_pos_days": edge_pos,
                      "today_pos_days": today_pos, "edge_max": edge_max, "edge_median": edge_med}
    print(f"\ngiorni-titolo esaminati: {days} | curva di oggi sopra zero: {today_pos} ({today_pos / days:.0%}) | "
          f"bordo di quel giorno sopra zero: {edge_pos} | valore tipico del bordo {edge_med:+.2f}, massimo {edge_max:+.2f}")
    print("\n=== La curva di oggi contro quella vista quel giorno ===")
    print(f"giorni in cui la regola sulla curva di OGGI è dentro: {rp['days_oracle_in']}")
    print(f"  di questi, quel giorno il bordo della curva era sopra zero: {rp['edge_z_pos'] / rp['days_oracle_in']:.1%}")
    print(f"  di questi, quel giorno la stessa regola sul bordo era dentro: {rp['edge_rule_in'] / rp['days_oracle_in']:.1%}")
    print(f"correlazione mediana tra curva di oggi e bordo di quel giorno: {corr:.2f}")

    em = [e for r in results for e in r["emerg"]]
    js = np.array([e[0] if e[0] is not None else 999 for e in em])
    seen = np.array([e[0] is not None for e in em])
    mv = np.array([e[1] for e in em if e[0] is not None])
    tot = np.array([e[2] for e in em if e[0] is not None])
    dur = np.array([e[3] for e in em])
    after_end = np.array([e[0] is None or e[0] >= e[3] for e in em])
    out["emergence"] = {"n": len(em), "within_10": float((js <= 10).mean()), "within_20": float((js <= 20).mean()),
                        "within_30": float((js <= 30).mean()), "median_bars": float(np.median(js[seen])),
                        "median_oracle_duration": float(np.median(dur)), "after_oracle_exit": float(after_end.mean()),
                        "move_before_visible": float(np.expm1(np.median(mv))),
                        "share_of_gain_gone": float(mv.sum() / tot.sum())}
    print(f"partenze dell'oracolo: {len(em)} (durata mediana dell'operazione {np.median(dur):.0f} barre)")
    print(f"  la gobba viola diventa visibile entro 10 barre: {(js <= 10).mean():.1%} | entro 20: {(js <= 20).mean():.1%} | "
          f"entro 30: {(js <= 30).mean():.1%} | mediana {np.median(js[seen]):.0f} barre")
    print(f"  visibile solo dopo che l'oracolo è già uscito (o mai): {after_end.mean():.0%}")
    print(f"  prezzo dal giorno di partenza a quando la gobba si vede: mediana {np.expm1(np.median(mv)):+.1%}; "
          f"quota del guadagno dell'oracolo già passata: {mv.sum() / tot.sum():.0%}")

    starts(results, out)

    nv = next((r for r in results if r["ticker"] == "NVDA"), None)
    if nv is not None:
        c = nv["curves"]
        print("\n=== NVDA: le operazioni della regola (pendenza 0.25) ===")
        for nm in ("ORACOLO p0.25", "BORDO p0.25", "RITARDO 10 p0.25", "2 STATI p0.25 +dir", "STABLE (trend)"):
            tr = [t for t in nv["rules"][nm]["trades"] if t[0] >= "2023-11-01"]
            tot = np.prod([1 + t[2] for t in tr]) - 1 if tr else 0.0
            print(f"-- {nm}: {len(tr)} operazioni dal 11/2023, composto {tot * 100:+.0f}%")
            for a, b, g, d in tr:
                print(f"     {a} → {b}  {g * 100:+6.1f}%  ({d} barre)")
        c0 = c[c.index >= "2023-11-01"]["px"]
        print(f"-- NVDA compra e tieni dal {c0.index[0].date()}: {c0.iloc[-1] / c0.iloc[0] - 1:+.0%}")
        print("-- le salite grosse di NVDA e quanto ne prende ogni regola")
        for i, leg in enumerate(nv["legs"]["ORACOLO p0.25"]):
            line = f"     {leg[4]} → {leg[5]}  salita {leg[0] * 100:+.0f}% |"
            for nm in ("ORACOLO p0.25", "BORDO p0.25", "RITARDO 10 p0.25", "2 STATI p0.25 +dir", "STABLE (trend)"):
                line += f" {nm.split(' p')[0]} {nv['legs'][nm][i][1] * 100:.0f}%"
            print(line)
        print("-- la curva nei giorni di partenza dell'oracolo (z di oggi / z visto quel giorno)")
        st = c["oracolo"].values
        for t in range(1, len(c)):
            if st[t] and not st[t - 1] and str(c.index[t].date()) >= "2023-11-01":
                first = next((u for u in range(t, len(c)) if c["z_quel_giorno"].values[u] > 0), None)
                wait = "mai" if first is None else f"{first - t} barre dopo, prezzo {c['px'].values[first] / c['px'].values[t] - 1:+.0%}"
                print(f"     {c.index[t].date()}  z oggi {c['z_oggi'].values[t]:+.2f} | z quel giorno "
                      f"{c['z_quel_giorno'].values[t]:+.2f} | bordo sopra zero: {wait}")
        out["nvda"] = {nm: [t for t in nv["rules"][nm]["trades"] if t[0] >= "2023-11-01"]
                       for nm in ("ORACOLO p0.25", "BORDO p0.25", "RITARDO 10 p0.25", "2 STATI p0.25 +dir", "STABLE (trend)")}

    save_output("kinetic_trend.json", out)


if __name__ == "__main__":
    main()
