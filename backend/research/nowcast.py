"""
SOVRAPPORRE SENZA RITARDO: la miglior stima "di oggi" del blu.

Il blu (cinetica dell'oracolo) è la velocità del percorso di minima azione
calcolato su passato E futuro della curva F = EMA20 del prezzo. Il futuro di F
però non è tutto ignoto: una media a 20 barre insegue il prezzo, quindi nei
prossimi giorni F andrà verso il prezzo di OGGI qualunque cosa succeda:

    F attesa tra k barre = prezzo_oggi − (1−a)^k · (prezzo_oggi − F_oggi),  a = 2/21

(è la previsione esatta se le variazioni future del prezzo sono imprevedibili).
STIMA DI OGGI (nowcast): si prolunga F con questa previsione per H barre, si
ricalcola il percorso di minima azione sulla serie prolungata e si legge la
sua velocità nel punto di oggi. È causale: usa solo dati fino a oggi, non
viene mai ridisegnata e NON è spostata nel tempo.

Confronto con l'arancione attuale e con i segnali veloci di faster_signal.py:
  somiglianza col blu nello stesso giorno (correlazione, con il segno),
  ritardo alle svolte, cambi di segno l'anno, risultato in tempo reale.

    backend/venv/bin/python backend/research/nowcast.py
    (FPR_PANEL_CACHE=percorso.pkl per riusare prezzi già scaricati)
"""
import math

from common import np, pd, save_output, tstat
from logic import ActionPath, kalman_llt_velocity
from kinetic_trend import load_panel, week_ids
from faster_signal import kalman

A0, A1, B0 = "2021-01-01", "2023-12-31", "2024-01-01"
ALPHA, BETA, SPAN, H = 200.0, 1.0, 20, 60


def steady_gain(alpha=ALPHA, beta=BETA):
    q, r = 1.0 / alpha, 1.0 / beta
    p_pred = (q + math.sqrt(q * q + 4 * q * r)) / 2
    return p_pred / (p_pred + r)


def nowcast_velocity(p, F, xf, horizon=H, span=SPAN):
    """Velocità del percorso di minima azione nel punto di oggi, stimata con i soli dati
    fino a oggi: filtro in avanti sulla F prevista per `horizon` barre, poi ricorsione
    all'indietro fino a ieri. Vettoriale sui giorni. Ritorna (velocità, percorso stimato)."""
    a = 2.0 / (span + 1)
    K = steady_gain()
    C = 1.0 - K
    gap = p - F
    X = np.empty((horizon + 1, len(p)))
    X[0] = xf
    x = xf.copy()
    for k in range(1, horizon + 1):
        Fk = p - (1 - a) ** k * gap
        x = x + K * (Fk - x)
        X[k] = x
    s = X[horizon]
    for k in range(horizon - 1, -1, -1):
        s = X[k] + C * (s - X[k])
    prev = np.r_[np.nan, xf[:-1]]
    s_prev = prev + C * (s - prev)
    return s - s_prev, s


def ramp_ratio():
    """Su una salita a ritmo costante: velocità stimata / velocità vera (per mettere in scala)."""
    n = 800
    p = 100 + 0.5 * np.arange(n)
    F = pd.Series(p).ewm(span=SPAN, adjust=False).mean().values
    v, _ = nowcast_velocity(p, F, kalman(F, ALPHA))
    return float(v[600] / 0.5)


def per_ticker(tk, px):
    p = px.values.astype(float)
    n, idx = len(p), px.index
    if n < 700:
        return None
    lr = np.zeros(n)
    lr[1:] = np.log(p[1:] / p[:-1])
    Fs = px.ewm(span=SPAN, adjust=False).mean()
    F = Fs.values.astype(float)
    xf = kalman(F, ALPHA)
    d = F - xf
    vs = ActionPath(px, alpha=ALPHA, beta=BETA).dX.values
    up = vs > 0
    vn, _ = nowcast_velocity(p, F, xf)
    dF = Fs.diff().fillna(0)
    sigs = {
        "arancione attuale (ritardo 9)": d,
        "STIMA DI OGGI del blu (nowcast)": vn,
        "pendenza EMA20 lisciata 5": dF.ewm(span=5, adjust=False).mean().values,
        "velocità 2 stati λ=1e-3": np.asarray(kalman_llt_velocity(np.log(px), 1e-3)["velocity"]),
        "prezzo − EMA20": p - F,
    }
    v0 = max(260, int(np.searchsorted(idx.values, np.datetime64(A0))))
    if n - v0 < 300:
        return None
    live = np.zeros(n, dtype=bool)
    live[v0 + 2:] = True
    yrs = live.sum() / 252.0
    wk = week_ids(idx)
    turns = [t for t in range(v0, n) if up[t] != up[t - 1]]
    out = {"sig": {}, "weekly": {}, "bh": float(np.expm1(lr[live].sum()))}
    for name, sig in sigs.items():
        sig = np.nan_to_num(np.asarray(sig, dtype=float))
        sg = np.sign(sig)
        st = sg > 0
        cors = []
        for k in range(0, 16):
            x, y = (sig[v0 + k:], vs[v0:n - k]) if k else (sig[v0:], vs[v0:])
            cors.append(float(np.corrcoef(x, y)[0, 1]))
        en_s, en_o = np.sign(sig[v0:]) * sig[v0:] ** 2, np.sign(vs[v0:]) * vs[v0:] ** 2
        delays = []
        for a_, t0 in enumerate(turns[:-1]):
            t1, s = turns[a_ + 1], (1.0 if up[t0] else -1.0)
            f = next((t for t in range(t0 - 1, t1) if sg[t] == s), None)
            if f is not None:
                delays.append(f - (t0 - 1))
        pos = np.zeros(n)
        pos[2:] = st[:-2]
        ch = np.diff(st[v0:].astype(int))
        tr = []
        for e in np.nonzero(ch == 1)[0] + v0 + 1:
            x_ = next((j for j in range(e, n) if not st[j]), n - 1)
            a2, b2 = min(e + 1, n - 1), min(x_ + 1, n - 1)
            if b2 > a2:
                tr.append(p[b2] / p[a2] - 1)
        out["sig"][name] = {"cors": cors, "corr_energy0": float(np.corrcoef(en_s, en_o)[0, 1]),
                            "agree": float((sg[live] == np.where(up[live], 1.0, -1.0)).mean()), "delays": delays,
                            "flips": float((sg[v0 + 1:] != sg[v0:-1]).sum() / yrs),
                            "roi": float(np.expm1((pos * lr)[live].sum())), "expo": float(pos[live].mean()), "trades": tr}
        for per, m in (("A", live & (idx <= A1)), ("B", live & (idx >= B0))):
            if m.sum() < 60:
                continue
            f = pos[m].mean()
            out["weekly"][(name, per)] = pd.Series((pos[m] - f) * lr[m]).groupby(wk[m]).sum()
    return out


def main():
    rho = ramp_ratio()
    print(f"salita a ritmo costante: la stima di oggi vede il {rho:.0%} della velocità vera "
          f"(fattore di scala dell'energia {1 / rho ** 2:.2f})")
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
    out = {"n_tickers": len(results), "ramp_ratio": rho, "signals": {}}
    print(f"titoli: {len(results)} | compra e tieni mediano {np.median([r['bh'] for r in results]):+.0%}")
    print(f"\n{'curva':34s} | {'somiglianza col blu: stesso giorno':>34s} {'massima (a barre)':>18s} {'energia col segno':>18s} {'verso giusto':>12s} | "
          f"{'ritardo':>7s} {'cambi/anno':>10s} | {'ROI med.':>8s} {'vinte':>6s} | {'timing 2021-23':>15s} | {'timing 2024-26':>15s}")
    for nm in names:
        C = np.median(np.array([r["sig"][nm]["cors"] for r in results]), axis=0)
        k_best = int(np.argmax(C))
        d = np.array([x for r in results for x in r["sig"][nm]["delays"]])
        tr = np.array([x for r in results for x in r["sig"][nm]["trades"]])
        rec = {"corr0": float(C[0]), "corr_best": float(C[k_best]), "lag_best": k_best,
               "corr_energy0": float(np.median([r["sig"][nm]["corr_energy0"] for r in results])),
               "agree": float(np.mean([r["sig"][nm]["agree"] for r in results])),
               "delay_median": float(np.median(d)), "delay_q25": float(np.percentile(d, 25)), "delay_q75": float(np.percentile(d, 75)),
               "flips": float(np.mean([r["sig"][nm]["flips"] for r in results])),
               "roi_median": float(np.median([r["sig"][nm]["roi"] for r in results])), "win": float((tr > 0).mean())}
        line = (f"{nm:34s} | {C[0]:34.2f} {C[k_best]:11.2f} ({k_best:2d}) {rec['corr_energy0']:18.2f} {rec['agree']:12.0%} | "
                f"{rec['delay_median']:7.0f} {rec['flips']:10.1f} | {rec['roi_median']:+8.0%} {rec['win']:6.0%} |")
        for per in ("A", "B"):
            w = pd.concat([r["weekly"][(nm, per)] for r in results if (nm, per) in r["weekly"]], axis=1).mean(axis=1)
            rec[per] = {"per_year": float(w.mean() * 52 * 100), "t": tstat(w.values)}
            line += f" {w.mean() * 52 * 100:+6.1f} (t {tstat(w.values):+4.1f}) |"
        out["signals"][nm] = rec
        print(line)
    save_output("nowcast.json", out)


if __name__ == "__main__":
    main()
