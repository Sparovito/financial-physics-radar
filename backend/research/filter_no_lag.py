"""
UN FILTRO SENZA RITARDO SUL FREEZE?

Il freeze (stima di oggi della velocità dell'oracolo) vede la direzione giusta,
ma con la regola dell'oracolo (dentro quando la cinetica z > 0) spezza una
salita in tante operazioni: a ogni pausa la cinetica torna sotto zero.

Un filtro lineare che liscia usando solo il passato introduce sempre ritardo
(più attenua il rumore, più ritarda: è la relazione guadagno-fase di Bode).
Senza ritardo restano due famiglie:
  - filtri A SOGLIA (isteresi): non lisciano il segnale, cambiano solo quando
    si decide. Entra sopra una soglia, esce sotto un'altra più bassa; oppure
    esce solo quando gira la DIREZIONE; oppure tiene un minimo di barre.
  - filtri che ANTICIPANO la tendenza (zero-lag EMA di Ehlers, media di Hull):
    tolgono il ritardo aggiungendo una estrapolazione, che amplifica il rumore.
In più un filtro mediano corto (toglie i picchi isolati, 2 barre di ritardo).

Per ogni variante, sui 611 titoli (gamba long, senza costi):
  ingressi rispetto all'oracolo, quanti sono veri, ritardo, operazioni per ogni
  operazione dell'oracolo, durata, ROI mediano, timing nei due periodi.

    backend/venv/bin/python backend/research/filter_no_lag.py
    (FPR_PANEL_CACHE=percorso.pkl per riusare prezzi già scaricati)
"""
from common import np, pd, save_output, tstat
from logic import ActionPath
from kinetic_trend import load_panel, week_ids
from faster_signal import kalman
from nowcast import nowcast_velocity
from oracle_events import zroll, episodes

A0, A1, B0 = "2021-01-01", "2023-12-31", "2024-01-01"
ALPHA, TAIL = 200.0, 40


def ema(x, span):
    return pd.Series(x).ewm(span=span, adjust=False).mean().values


def zlema(x, span):
    lag = (span - 1) // 2
    s = pd.Series(x)
    return (s + (s - s.shift(lag)).fillna(0)).ewm(span=span, adjust=False).mean().values


def wma(x, n):
    w = np.arange(1, n + 1, dtype=float)
    return pd.Series(x).rolling(n).apply(lambda a: (a * w).sum() / w.sum(), raw=True).values


def hull(x, n):
    return np.nan_to_num(wma(2 * np.nan_to_num(wma(x, n // 2)) - np.nan_to_num(wma(x, n)), int(np.sqrt(n))))


def machine(zk, long_ok, lo, hi, enter=0.0, leave=0.0, exit_dir=None, dwell=0):
    """Gamba long. Entra quando zk supera `enter` con verso long; esce quando zk scende sotto
    `leave` (o, se exit_dir è dato, quando exit_dir diventa falso), non prima di `dwell` barre."""
    out, t = [], max(lo, 1)
    while t < hi:
        if zk[t] > enter and zk[t - 1] <= enter and long_ok[t]:
            s = t
            t += 1
            while t < hi:
                gone = (not exit_dir[t]) if exit_dir is not None else (zk[t] < leave)
                if gone and (t - s) >= dwell:
                    break
                t += 1
            out.append((s, t))
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
    F = px.ewm(span=20, adjust=False).mean().values.astype(float)
    xf = kalman(F, ALPHA)
    vn = np.nan_to_num(nowcast_velocity(p, F, xf)[0])
    mech = ActionPath(px, alpha=ALPHA, beta=1.0)
    zk_or, zs_or = zroll(mech.kin_density.values), zroll(mech.dX.values)
    v0 = max(260, int(np.searchsorted(idx.values, np.datetime64(A0))))
    hi = n - TAIL
    if hi - v0 < 300:
        return None
    o_eps = [(s, e) for s, e, lg in episodes(zk_or, zs_or, v0, hi) if lg]
    o_in = np.array([s for s, e in o_eps])

    def zpair(v):
        return zroll(0.5 * ALPHA * v ** 2), zroll(v)

    zk, zs = zpair(vn)
    zk_zl, zs_zl = zpair(zlema(vn, 9))
    zk_hu, zs_hu = zpair(hull(vn, 9))
    zk_em, zs_em = zpair(ema(vn, 9))
    zk_med = pd.Series(zk).rolling(5, min_periods=1).median().values
    up = vn > 0
    variants = {
        "freeze com'è (esce sotto 0)": machine(zk, zs > 0, v0, hi),
        "isteresi: esce sotto −0,5": machine(zk, zs > 0, v0, hi, leave=-0.5),
        "isteresi: esce sotto −1": machine(zk, zs > 0, v0, hi, leave=-1.0),
        "banda: entra sopra +0,5, esce sotto −0,5": machine(zk, zs > 0, v0, hi, enter=0.5, leave=-0.5),
        "esce solo quando gira la direzione": machine(zk, zs > 0, v0, hi, exit_dir=up),
        "tenuta minima 10 barre": machine(zk, zs > 0, v0, hi, dwell=10),
        "tenuta minima 20 barre": machine(zk, zs > 0, v0, hi, dwell=20),
        "zero-lag EMA (Ehlers, 9)": machine(zk_zl, zs_zl > 0, v0, hi),
        "media di Hull (9)": machine(zk_hu, zs_hu > 0, v0, hi),
        "mediana a 5 barre sulla cinetica": machine(zk_med, zs > 0, v0, hi),
        "EMA normale a 9 (con ritardo, riferimento)": machine(zk_em, zs_em > 0, v0, hi),
        "ORACOLO": o_eps,
    }
    wk = week_ids(idx)
    live = np.zeros(n, dtype=bool)
    live[v0 + 2:hi] = True
    res = {"n_oracle": len(o_eps), "v": {}, "weekly": {}, "bh": float(np.expm1(lr[live].sum()))}
    for name, eps in variants.items():
        st = np.zeros(n, dtype=bool)
        for s, e in eps:
            st[s:e] = True
        pos = np.zeros(n)
        pos[2:] = st[:-2]
        c_in = np.array([s for s, e in eps])
        lags, hit = [], 0
        for s in o_in:
            if len(c_in):
                j = c_in[np.argmin(np.abs(c_in - s))]
                if -5 <= j - s <= 15:
                    lags.append(int(j - s))
        for s in c_in:
            if len(o_in) and ((s - o_in >= -5) & (s - o_in <= 15)).any():
                hit += 1
        # quante operazioni cadono dentro ogni operazione dell'oracolo
        inside = [int(((c_in >= s - 5) & (c_in < e)).sum()) for s, e in o_eps] if len(c_in) else [0] * len(o_eps)
        tr = [p[min(e + 1, n - 1)] / p[min(s + 1, n - 1)] - 1 for s, e in eps]
        true_flag = [bool(len(o_in) and ((s - o_in >= -5) & (s - o_in <= 15)).any()) for s, e in eps]
        res["v"][name] = {"n": len(eps), "lags": lags, "hit": hit, "inside": inside, "trades": tr, "true_flag": true_flag,
                          "bars": [e - s for s, e in eps], "roi": float(np.expm1((pos * lr)[live].sum())),
                          "expo": float(pos[live].mean())}
        for per, m in (("A", live & (idx <= A1)), ("B", live & (idx >= B0))):
            if m.sum() < 60:
                continue
            f = pos[m].mean()
            res["weekly"][(name, per)] = pd.Series((pos[m] - f) * lr[m]).groupby(wk[m]).sum()
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
    n_or = sum(r["n_oracle"] for r in results)
    print(f"titoli: {len(results)} | operazioni long dell'oracolo: {n_or} | compra e tieni mediano {np.median([r['bh'] for r in results]):+.0%}")
    print(f"\n{'variante':44s} {'ingressi':>8s} {'veri':>5s} {'trovati':>8s} {'ritardo':>7s} {'per op.':>7s} {'durata':>6s} {'vinte':>6s} {'media':>7s} | "
          f"{'ROI med.':>8s} {'espos.':>6s} | {'timing 2021-23':>15s} | {'timing 2024-26':>15s}")
    out = {"n_tickers": len(results), "oracle_trades": n_or, "variants": {}}
    for name in results[0]["v"]:
        n_ = sum(r["v"][name]["n"] for r in results)
        hit = sum(r["v"][name]["hit"] for r in results)
        lags = np.array([x for r in results for x in r["v"][name]["lags"]])
        inside = np.array([x for r in results for x in r["v"][name]["inside"]])
        tr = np.array([x for r in results for x in r["v"][name]["trades"]])
        bars = np.array([x for r in results for x in r["v"][name]["bars"]])
        roi = np.median([r["v"][name]["roi"] for r in results])
        expo = np.mean([r["v"][name]["expo"] for r in results])
        rec = {"entries": int(n_), "true": hit / n_, "found": len(lags) / n_or, "lag": float(np.median(lags)),
               "per_oracle_trade": float(inside.mean()), "bars": float(np.median(bars)), "win": float((tr > 0).mean()),
               "mean_trade": float(tr.mean()), "roi_median": float(roi), "expo": float(expo)}
        line = (f"{name:44s} {n_:8d} {hit / n_:5.0%} {len(lags) / n_or:8.0%} {np.median(lags):+7.0f} {inside.mean():7.1f} {np.median(bars):6.0f} "
                f"{(tr > 0).mean():6.0%} {tr.mean():+7.1%} | {roi:+8.0%} {expo:6.0%} |")
        for per in ("A", "B"):
            w = pd.concat([r["weekly"][(name, per)] for r in results if (name, per) in r["weekly"]], axis=1).mean(axis=1)
            rec[per] = {"per_year": float(w.mean() * 52 * 100), "t": tstat(w.values)}
            line += f" {w.mean() * 52 * 100:+6.1f} (t {tstat(w.values):+4.1f}) |"
        out["variants"][name] = rec
        print(line)
    print("\n=== Dove si perde: operazioni vicine a un ingresso vero dell'oracolo contro le altre ===")
    for name in results[0]["v"]:
        if name == "ORACOLO":
            continue
        tr = np.array([x for r in results for x in r["v"][name]["trades"]])
        fl = np.array([x for r in results for x in r["v"][name]["true_flag"]])
        out["variants"][name].update({"mean_true": float(tr[fl].mean()), "win_true": float((tr[fl] > 0).mean()),
                                      "mean_false": float(tr[~fl].mean()), "win_false": float((tr[~fl] > 0).mean())})
        print(f"{name:44s} vere {fl.mean():4.0%}: media {tr[fl].mean():+5.1%}, vinte {(tr[fl] > 0).mean():4.0%} | "
              f"false {1 - fl.mean():4.0%}: media {tr[~fl].mean():+5.1%}, vinte {(tr[~fl] > 0).mean():4.0%}")
    save_output("filter_no_lag.json", out)


if __name__ == "__main__":
    main()
