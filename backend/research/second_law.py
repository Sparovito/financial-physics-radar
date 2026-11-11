"""
IL SECONDO PRINCIPIO DELLA TERMODINAMICA APPLICATO AL MERCATO.

Enunciato di Kelvin: da un sistema in equilibrio a una sola temperatura non si
estrae lavoro; lo si estrae solo da uno squilibrio che si rilassa, e solo dalla
parte ORDINATA dell'energia. La parte disordinata è calore.

Traduzione. Ogni titolo ha uno scostamento x_i = (EMA20 − filtro) / (prezzo·σ),
in "sigma" (la molla del modello: negativo = prezzo sotto il percorso). Per
l'insieme dei titoli, ogni giorno:

    energia totale        E = media(x_i²)
    spostamento coerente  X = media(x_i)            (tutti dalla stessa parte)
    energia ordinata      W = X²                     capace di lavoro
    calore                Q = E − X² = varianza(x_i) disordine tra i titoli
    quota ordinata        m = X² / E                 (0 = solo calore, 1 = tutto ordinato)

Chi tiene un indice sente solo la parte ordinata: gli scostamenti dei singoli
titoli si compensano (è il motivo per cui scegliere i titoli non ha reso). Il
secondo principio dice allora due cose verificabili:
  1. il rendimento futuro dell'indice dipende da X (rilassamento verso
     l'equilibrio), non dal calore;
  2. una regola che compra l'indice quando X è molto negativo (sistema
     spostato tutto insieme sotto il percorso) estrae lavoro; quando X è nella
     norma non c'è niente da estrarre.

Verifica su una storia LUNGA: le soglie sono percentili causali (X confrontato
con i propri 5 anni precedenti), i periodi 2005-12 e 2013-20 non erano mai
stati guardati; il 2021-26 è quello delle analisi precedenti.

Regole (senza leva, liquidità a rendimento zero): esposizione di base all'indice,
che sale al 100% quando scatta il segnale e ci resta per 21 sedute dopo
l'ultimo giorno di segnale. Decisione alla chiusura t, esecuzione t+1.

    backend/venv/bin/python backend/research/second_law.py
    (FPR_LONG_PANEL=percorso.pkl con {"px": {ticker: Series di chiusure dal 2003}})
"""
import pickle

from common import os, np, pd, save_output, tstat
from faster_signal import kalman

ALPHA, HOLD = 200.0, 21
PERIODS = (("2005-12", "2005-01-01", "2012-12-31"), ("2013-20", "2013-01-01", "2020-12-31"), ("2021-26", "2021-01-01", "2099-01-01"))
INDEX = "SPY"


def load_long():
    cache = os.environ.get("FPR_LONG_PANEL")
    if cache and os.path.exists(cache):
        return pickle.load(open(cache, "rb"))["px"]
    import concurrent.futures
    import yfinance as yf
    from tickers_loader import load_tickers

    def one(t):
        try:
            s = yf.Ticker(t).history(start="2003-01-01")["Close"].dropna()
            s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
            return t, (s[~s.index.duplicated(keep="last")] if len(s) >= 400 else None)
        except Exception:
            return t, None
    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for t, s in ex.map(one, sorted(load_tickers())):
            if s is not None:
                out[t] = s
    return out


def per_ticker(px):
    px = px[px > 0]
    p = px.values.astype(float)
    if len(p) < 500:
        return None
    lr = np.zeros(len(p))
    lr[1:] = np.log(p[1:] / p[:-1])
    sig = pd.Series(lr).ewm(span=60, min_periods=20).std().values
    F = px.ewm(span=20, adjust=False).mean().values.astype(float)
    d = F - kalman(F, ALPHA)
    with np.errstate(divide="ignore", invalid="ignore"):
        x = np.clip(d / (p * sig), -15, 15)
    pot = pd.Series(0.5 * d ** 2)
    z = ((pot - pot.rolling(252, min_periods=40).mean()) / (pot.rolling(252, min_periods=40).std() + 1e-9)).fillna(0).values
    x[:260] = np.nan
    v2 = np.where(np.isfinite(x), ((z > 0) & (d < 0)).astype(float), np.nan)
    return pd.Series(x, index=px.index), pd.Series(v2, index=px.index)


def stats(r, w):
    """r: rendimenti semplici giornalieri dell'indice; w: esposizione applicata a quel giorno."""
    pr = w * r
    eq = np.cumprod(1 + pr)
    yrs = len(pr) / 252.0
    dd = float((1 - eq / np.maximum.accumulate(eq)).max())
    return {"cagr": float(eq[-1] ** (1 / yrs) - 1), "dd": dd,
            "sharpe": float(pr.mean() / (pr.std() + 1e-12) * np.sqrt(252)), "expo": float(w.mean())}


def main():
    prices = load_long()
    xs, v2s = {}, {}
    for tk, px in prices.items():
        try:
            r = per_ticker(px)
        except Exception:
            continue
        if r:
            xs[tk], v2s[tk] = r
    Xw = pd.DataFrame(xs)
    V2 = pd.DataFrame(v2s)
    n_valid = Xw.notna().sum(axis=1)
    days = n_valid.index[n_valid >= 150]
    Xw, V2 = Xw.loc[days], V2.loc[days]
    E = (Xw ** 2).mean(axis=1)
    X = Xw.mean(axis=1)
    Q = Xw.var(axis=1, ddof=0)
    m = (X ** 2) / E
    v2share = V2.mean(axis=1)
    pct = X.rolling(1260, min_periods=500).apply(lambda a: (a <= a[-1]).mean(), raw=True)

    spy = prices[INDEX].reindex(days).ffill()
    r = spy.pct_change().fillna(0).values
    f21 = np.log(spy.shift(-22) / spy.shift(-1)).values
    f1 = np.log(spy.shift(-2) / spy.shift(-1)).values
    idx = days
    print(f"titoli: {len(xs)} | giorni: {len(days)} dal {days[0].date()} al {days[-1].date()} | titoli per giorno: da {int(n_valid.loc[days].min())} a {int(n_valid.loc[days].max())}")
    print(f"energia totale media {E.mean():.2f} | ordinata {(X ** 2).mean():.2f} ({(X ** 2).mean() / E.mean():.0%}) | calore {Q.mean():.2f} ({Q.mean() / E.mean():.0%})")
    out = {"n_tickers": len(xs), "first_day": str(days[0].date()), "ordered_share": float((X ** 2).mean() / E.mean())}

    # --- 1. legge di rilassamento: il rendimento futuro dell'indice dipende da X? e dal calore? ---
    print("\n=== 1. Rilassamento: SPY nei 21 giorni dopo, per livello dello spostamento coerente X (percentile sui 5 anni prima) ===")
    buckets = (("X molto negativo (≤ 5%)", 0.0, 0.05), ("X negativo (5-20%)", 0.05, 0.20), ("X nella norma (20-80%)", 0.20, 0.80),
               ("X positivo (80-95%)", 0.80, 0.95), ("X molto positivo (> 95%)", 0.95, 1.01))
    out["relax"] = {}
    for nm, a, b in PERIODS:
        mper = (idx >= a) & (idx <= b) & np.isfinite(pct.values) & np.isfinite(f21)
        if mper.sum() < 200:
            continue
        line = f"{nm}: "
        rec = {}
        for lab, lo, hi in buckets:
            sel = mper & (pct.values > lo) & (pct.values <= hi) if lo > 0 else mper & (pct.values <= hi)
            rec[lab] = {"days": int(sel.sum()), "f21": float(np.nanmean(f21[sel])) if sel.sum() else float("nan"),
                        "f1": float(np.nanmean(f1[sel])) if sel.sum() else float("nan"),
                        "pos": float((f21[sel] > 0).mean()) if sel.sum() else float("nan")}
        out["relax"][nm] = rec
        print(f"{nm}  (un periodo qualsiasi: {np.expm1(np.nanmean(f21[mper])):+.2%} in 21 giorni, positivo {(f21[mper] > 0).mean():.0%})")
        for lab, _, _ in buckets:
            c = rec[lab]
            print(f"    {lab:28s} {c['days']:5d} giorni | 21 gg {np.expm1(c['f21']):+6.2%} (positivo {c['pos']:4.0%}) | giorno dopo {np.expm1(c['f1']):+.3%}")
    # pendenza su blocchi non sovrapposti di 21 giorni: X contro calore
    print("-- pendenza del rendimento a 21 giorni (blocchi non sovrapposti) su X e sul calore Q, entrambi standardizzati")
    out["slopes"] = {}
    for nm, a, b in PERIODS + (("tutto", "2005-01-01", "2099-01-01"),):
        mper = (idx >= a) & (idx <= b) & np.isfinite(f21) & np.isfinite(pct.values)
        ii = np.nonzero(mper)[0][::21]
        if len(ii) < 20:
            continue
        zx = (X.values[ii] - X.values[ii].mean()) / X.values[ii].std()
        zq = (Q.values[ii] - Q.values[ii].mean()) / Q.values[ii].std()
        A = np.column_stack([zx, zq, np.ones(len(ii))])
        coef, res_, _, _ = np.linalg.lstsq(A, f21[ii], rcond=None)
        resid = f21[ii] - A @ coef
        cov = np.linalg.inv(A.T @ A) * (resid @ resid) / (len(ii) - 3)
        tx, tq = coef[0] / np.sqrt(cov[0, 0]), coef[1] / np.sqrt(cov[1, 1])
        out["slopes"][nm] = {"x": float(coef[0]), "t_x": float(tx), "q": float(coef[1]), "t_q": float(tq), "blocks": int(len(ii))}
        print(f"    {nm:8s} ({len(ii)} blocchi): per ogni deviazione standard di X in meno {-coef[0]:+.2%} (t {-tx:+.1f}) | "
              f"per ogni deviazione standard di calore in più {coef[1]:+.2%} (t {tq:+.1f})")

    # --- 2. regole ---
    sig_x = (pct.values <= 0.05)
    sig_v2 = (v2share.values >= 0.30)
    sig_up = (pct.values >= 0.95)
    # il secondo principio vale per un sistema che non riceve più energia dall'esterno: il rilassamento
    # comincia quando lo spostamento coerente smette di crescere. Segnale "rientro iniziato": X è stato
    # nel 5% più basso nelle ultime 10 sedute E oggi è più alto di 5 sedute fa.
    touched = pd.Series(sig_x.astype(float)).rolling(10, min_periods=1).max().values > 0
    sig_relax = touched & (X.values > X.shift(5).values)

    def held(sigarr):
        return pd.Series(np.nan_to_num(sigarr.astype(float))).rolling(HOLD + 1, min_periods=1).max().values > 0

    def weights(base, sigarr, light=None):
        h = held(sigarr)
        w = np.where(h, 1.0, base)
        if light is not None:
            w = np.where(held(light) & ~h, base * 0.5, w)
        return np.r_[np.full(2, base), w[:-2]]             # decisione t → rendimento del giorno t+2

    rules = {
        "solo indice (100%)": lambda: np.ones(len(r)),
        "secondo principio: base 0% → 100% col segnale": lambda: weights(0.0, sig_x),
        "secondo principio: base 50% → 100%": lambda: weights(0.5, sig_x),
        "secondo principio: base 70% → 100%": lambda: weights(0.7, sig_x),
        "base 50% → 100%, e 25% quando X è molto positivo": lambda: weights(0.5, sig_x, light=sig_up),
        "rientro iniziato: base 0% → 100%": lambda: weights(0.0, sig_relax),
        "rientro iniziato: base 50% → 100%": lambda: weights(0.5, sig_relax),
        "rientro iniziato: base 70% → 100%": lambda: weights(0.7, sig_relax),
        "quota V2 ≥ 30%: base 50% → 100%": lambda: weights(0.5, sig_v2),
        "quota V2 ≥ 30%: base 0% → 100%": lambda: weights(0.0, sig_v2),
    }
    print("\n=== 2. Regole senza leva (rendimento annuo composto, ribasso massimo, Sharpe; liquidità a zero) ===")
    out["rules"] = {}
    for nm, a, b in PERIODS:
        mper = (idx >= a) & (idx <= b) & np.isfinite(pct.values)
        if mper.sum() < 200:
            continue
        print(f"{nm} ({mper.sum() / 252:.1f} anni)")
        out["rules"][nm] = {}
        for rn, fn in rules.items():
            w = fn()
            st = stats(r[mper], w[mper])
            fixed = stats(r[mper], np.full(mper.sum(), st["expo"]))
            out["rules"][nm][rn] = {**st, "fixed_cagr": fixed["cagr"], "fixed_dd": fixed["dd"]}
            print(f"    {rn:50s} {st['cagr']:+6.1%} l'anno | ribasso {st['dd']:4.0%} | Sharpe {st['sharpe']:4.2f} | esposizione media {st['expo']:4.0%} "
                  f"| stessa esposizione tenuta fissa: {fixed['cagr']:+5.1%}, ribasso {fixed['dd']:3.0%}")

    # --- 3. episodi del segnale del secondo principio ---
    print("\n=== 3. Episodi: X nel 5% più basso dei 5 anni precedenti (ingresso alla chiusura successiva) ===")
    on = np.nonzero(sig_x & np.isfinite(pct.values))[0]
    clusters = []
    for j in on:
        if clusters and j - clusters[-1][1] <= HOLD:
            clusters[-1][1] = j
        else:
            clusters.append([j, j])
    sp = spy.values
    eps = []
    for t, last in clusters:
        e = t + 1
        if e + 63 >= len(sp):
            continue
        eps.append({"date": str(idx[t].date()), "x": float(X.values[t]), "v2": float(v2share.values[t]), "m": float(m.values[t]),
                    "r21": float(sp[e + 21] / sp[e] - 1), "r63": float(sp[e + 63] / sp[e] - 1),
                    "worst": float(sp[e:e + 64].min() / sp[e] - 1), "days_on": int(last - t + 1)})
    out["episodes"] = eps
    print("inizio       X      quota V2  quota ordinata | SPY 21 gg   63 gg   punto più basso in 63 gg")
    for ep in eps:
        print(f"{ep['date']}  {ep['x']:+5.2f}   {ep['v2']:6.0%}   {ep['m']:10.0%}    | {ep['r21']:+7.1%} {ep['r63']:+7.1%} {ep['worst']:+10.1%}")
    for nm, a, b in PERIODS:
        c = [e for e in eps if a <= e["date"] <= b]
        if c:
            r21 = np.array([e["r21"] for e in c])
            r63 = np.array([e["r63"] for e in c])
            print(f"  {nm}: {len(c)} episodi | a 21 gg media {r21.mean():+.1%}, positivi {(r21 > 0).mean():.0%} | a 63 gg media {r63.mean():+.1%}, "
                  f"positivi {(r63 > 0).mean():.0%} | peggior punto {min(e['worst'] for e in c):+.1%}")
    print("\n=== 3b. Episodi con il segnale 'rientro iniziato' ===")
    on2 = np.nonzero(sig_relax & np.isfinite(pct.values))[0]
    cl2 = []
    for j in on2:
        if cl2 and j - cl2[-1][1] <= HOLD:
            cl2[-1][1] = j
        else:
            cl2.append([j, j])
    eps2 = []
    for t, last in cl2:
        e = t + 1
        if e + 63 >= len(sp):
            continue
        eps2.append({"date": str(idx[t].date()), "x": float(X.values[t]), "r21": float(sp[e + 21] / sp[e] - 1),
                     "r63": float(sp[e + 63] / sp[e] - 1), "worst": float(sp[e:e + 64].min() / sp[e] - 1)})
    out["episodes_relax"] = eps2
    print("inizio       X     | SPY 21 gg   63 gg   punto più basso in 63 gg")
    for ep in eps2:
        print(f"{ep['date']}  {ep['x']:+5.2f}  | {ep['r21']:+7.1%} {ep['r63']:+7.1%} {ep['worst']:+10.1%}")
    for nm, a, b in PERIODS + (("tutto", "2005-01-01", "2099-01-01"),):
        for lab, lst in (("primo tocco", eps), ("rientro iniziato", eps2)):
            c = [e for e in lst if a <= e["date"] <= b]
            if c:
                r21 = np.array([e["r21"] for e in c])
                r63 = np.array([e["r63"] for e in c])
                print(f"  {nm:8s} {lab:17s}: {len(c):2d} episodi | 21 gg media {r21.mean():+5.1%}, positivi {(r21 > 0).mean():4.0%} | 63 gg media {r63.mean():+5.1%}, "
                      f"positivi {(r63 > 0).mean():4.0%} | peggior punto {min(e['worst'] for e in c):+6.1%}")
    m63 = np.log(spy.shift(-64) / spy.shift(-1)).values
    ok = np.isfinite(m63) & np.isfinite(pct.values)
    print(f"  per confronto, un periodo qualsiasi di 63 sedute: {np.expm1(np.nanmean(m63[ok])):+.1%}, positivo {(m63[ok] > 0).mean():.0%}; "
          f"di 21 sedute: {np.expm1(np.nanmean(f21[ok])):+.1%}, positivo {(f21[ok] > 0).mean():.0%}")
    save_output("second_law.json", out)


if __name__ == "__main__":
    main()
