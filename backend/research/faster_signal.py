"""
SI PUÒ VELOCIZZARE IL SEGNALE DI DIREZIONE?

Il segno dell'arancione (scostamento d = EMA20 − filtro, α=200) cambia circa 10
barre dopo la svolta dell'oracolo. Qui si provano segnali più veloci e si misura
il prezzo della velocità: ogni segnale è una media degli incrementi passati del
prezzo; meno barre media, prima gira, ma più spesso gira a vuoto.

Per ogni segnale (tutti causali):
  ritardo    barre tra la svolta dell'oracolo (α=200) e il primo giorno in cui
             il segnale ha il nuovo segno
  cambi/anno quante volte cambia segno in un anno (l'oracolo: circa 3,5)
  giusto     quota di giorni con lo stesso verso dell'oracolo
  risultato  comprando quando è positivo e vendendo quando è negativo, in tempo
             reale (decisione t, esecuzione t+1): ROI mediano, operazioni vinte,
             timing del portafoglio nei due periodi

    backend/venv/bin/python backend/research/faster_signal.py
    (FPR_PANEL_CACHE=percorso.pkl per riusare prezzi già scaricati)
"""
from common import np, pd, save_output, tstat
from logic import ActionPath, kalman_llt_velocity
from kinetic_trend import load_panel, week_ids

A0, A1, B0 = "2021-01-01", "2023-12-31", "2024-01-01"


def kalman(F, alpha, beta=1.0):
    q, r = 1.0 / alpha, 1.0 / beta
    x = np.empty(len(F))
    x[0], P = F[0], r
    for t in range(1, len(F)):
        Pp = P + q
        g = Pp / (Pp + r)
        x[t] = x[t - 1] + g * (F[t] - x[t - 1])
        P = (1 - g) * Pp
    return x


def signals(px):
    F20 = px.ewm(span=20, adjust=False).mean()
    F10 = px.ewm(span=10, adjust=False).mean()
    f20 = F20.values.astype(float)
    d200 = f20 - kalman(f20, 200.0)
    dF = F20.diff().fillna(0)
    lp = np.log(px)
    lead = d200 + 9.0 * (d200 - np.r_[np.full(3, np.nan), d200[:-3]]) / 3.0
    # varianti miste: lento = arancione attuale, veloce = pendenza di EMA20 lisciata 5
    fast = dF.ewm(span=5, adjust=False).mean().values
    pot = pd.Series(0.5 * d200 ** 2)
    z = ((pot - pot.rolling(252, min_periods=40).mean()) / (pot.rolling(252, min_periods=40).std() + 1e-9)).fillna(0).values
    both = np.where((d200 > 0) & (fast > 0), 1.0, -1.0)
    either = np.where((d200 > 0) | (fast > 0), 1.0, -1.0)
    adaptive = np.where(z > 0, np.sign(fast), np.sign(d200))
    mixed = {
        "misto: entra lento, esce veloce": both,
        "misto: entra veloce, esce lento": either,
        "misto: veloce solo con energia alta": adaptive,
    }
    base = {
        "arancione attuale (α=200)": d200,
        "arancione α=100": f20 - kalman(f20, 100.0),
        "arancione α=50": f20 - kalman(f20, 50.0),
        "arancione α=25": f20 - kalman(f20, 25.0),
        "arancione anticipato (proiettato 9 barre)": lead,
        "pendenza EMA20 lisciata 14 (Stable)": dF.ewm(span=14, adjust=False).mean().values,
        "pendenza EMA20 lisciata 5": dF.ewm(span=5, adjust=False).mean().values,
        "pendenza EMA20": dF.values,
        "EMA10 − filtro α=50": F10.values - kalman(F10.values.astype(float), 50.0),
        "prezzo − EMA20": (px - F20).values,
        "velocità 2 stati λ=1e-4": np.asarray(kalman_llt_velocity(lp, 1e-4)["velocity"]),
        "velocità 2 stati λ=1e-3": np.asarray(kalman_llt_velocity(lp, 1e-3)["velocity"]),
    }
    base.update(mixed)
    return base


def per_ticker(tk, px):
    p = px.values.astype(float)
    n, idx = len(p), px.index
    if n < 700:
        return None
    lr = np.zeros(n)
    lr[1:] = np.log(p[1:] / p[:-1])
    vs = ActionPath(px, alpha=200.0, beta=1.0).dX.values
    up = vs > 0
    v0 = max(260, int(np.searchsorted(idx.values, np.datetime64(A0))))
    if n - v0 < 300:
        return None
    live = np.zeros(n, dtype=bool)
    live[v0 + 2:] = True
    yrs = live.sum() / 252.0
    wk = week_ids(idx)
    turns = [t for t in range(v0, n) if up[t] != up[t - 1]]
    out = {"oracle_turns_per_year": len(turns) / yrs, "bh": float(np.expm1(lr[live].sum())), "sig": {}, "weekly": {}}
    for name, sig in signals(px).items():
        sig = np.asarray(sig, dtype=float)
        sg = np.sign(np.nan_to_num(sig))
        st = sg > 0
        delays, never = [], 0
        for a, t0 in enumerate(turns[:-1]):
            t1, s = turns[a + 1], (1.0 if up[t0] else -1.0)
            f = next((t for t in range(t0 - 1, t1) if sg[t] == s), None)
            if f is None:
                never += 1
            else:
                delays.append(f - (t0 - 1))
        flips = int((sg[v0 + 1:] != sg[v0:-1]).sum())
        pos = np.zeros(n)
        pos[2:] = st[:-2]
        ch = np.diff(st[v0:].astype(int))
        ent = np.nonzero(ch == 1)[0] + v0 + 1
        tr = []
        for e in ent:
            x = next((j for j in range(e, n) if not st[j]), n - 1)
            a, b = min(e + 1, n - 1), min(x + 1, n - 1)
            if b > a:
                tr.append(p[b] / p[a] - 1)
        out["sig"][name] = {"delays": delays, "never": never, "turns": len(turns) - 1, "flips_per_year": flips / yrs,
                            "agree": float((sg[live] == np.where(up[live], 1.0, -1.0)).mean()),
                            "roi": float(np.expm1((pos * lr)[live].sum())), "expo": float(pos[live].mean()), "trades": tr}
        for per, m in (("A", live & (idx <= A1)), ("B", live & (idx >= B0))):
            if m.sum() < 60:
                continue
            f = pos[m].mean()
            out["weekly"][(name, per)] = pd.Series((pos[m] - f) * lr[m]).groupby(wk[m]).sum()
    return out


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
    names = list(results[0]["sig"].keys())
    out = {"n_tickers": len(results), "oracle_turns_per_year": float(np.mean([r["oracle_turns_per_year"] for r in results])),
           "bh_median": float(np.median([r["bh"] for r in results])), "signals": {}}
    print(f"titoli: {len(results)} | svolte dell'oracolo: {out['oracle_turns_per_year']:.1f} l'anno per titolo | "
          f"compra e tieni mediano {out['bh_median']:+.0%}")
    print(f"\n{'segnale':42s} {'ritardo':>8s} {'(25-75%)':>9s} {'mai':>5s} {'cambi/anno':>10s} {'giusto':>7s} | "
          f"{'ROI med.':>8s} {'espos.':>6s} {'vinte':>6s} {'media':>7s} | {'timing 2021-23':>15s} | {'timing 2024-26':>15s}")
    for nm in names:
        d = np.array([x for r in results for x in r["sig"][nm]["delays"]])
        never = sum(r["sig"][nm]["never"] for r in results) / sum(r["sig"][nm]["turns"] for r in results)
        flips = np.mean([r["sig"][nm]["flips_per_year"] for r in results])
        agree = np.mean([r["sig"][nm]["agree"] for r in results])
        roi = np.median([r["sig"][nm]["roi"] for r in results])
        expo = np.mean([r["sig"][nm]["expo"] for r in results])
        tr = np.array([x for r in results for x in r["sig"][nm]["trades"]])
        rec = {"delay_median": float(np.median(d)), "delay_q25": float(np.percentile(d, 25)), "delay_q75": float(np.percentile(d, 75)),
               "never": float(never), "flips_per_year": float(flips), "agree": float(agree), "roi_median": float(roi),
               "expo": float(expo), "win": float((tr > 0).mean()), "mean_trade": float(tr.mean())}
        line = (f"{nm:42s} {np.median(d):8.0f} {np.percentile(d, 25):4.0f}-{np.percentile(d, 75):<4.0f} {never:5.0%} {flips:10.1f} {agree:7.0%} | "
                f"{roi:+8.0%} {expo:6.0%} {(tr > 0).mean():6.0%} {tr.mean():+7.1%} |")
        for per in ("A", "B"):
            w = pd.concat([r["weekly"][(nm, per)] for r in results if (nm, per) in r["weekly"]], axis=1).mean(axis=1)
            rec[per] = {"per_year": float(w.mean() * 52 * 100), "t": tstat(w.values)}
            line += f" {w.mean() * 52 * 100:+6.1f} (t {tstat(w.values):+4.1f}) |"
        out["signals"][nm] = rec
        print(line)
    save_output("faster_signal.json", out)


if __name__ == "__main__":
    main()
