"""
ENERGIA → ORACOLO: cosa dicono potenziale e cinetica PRIMA che il prezzo si muova?

Punto di partenza: Frozen V2 (potenziale sopra la media + prezzo sotto il
percorso) ha un timing di circa +2%/anno; l'oracolo +37%/anno. Questo script
cerca, in modo dichiarato in anticipo, schemi di energia che riducano la
distanza. Tutto causale: decisione alla chiusura t, esecuzione a t+1, primo
rendimento incassato quello del giorno t+2.

Due "macchine" di energia:
  A. quella del progetto (livello locale su EMA20, α=200): scostamento d,
     potenziale ½d², z-score a 252 barre. Qui cinetica ≡ potenziale.
  B. filtro a trend locale (2 stati: livello + velocità) sul log-prezzo, a tre
     scale. Qui le due energie sono DISTINTE:
        potenziale V = ½·u²   con u = (prezzo − livello)/σ   (molla tirata)
        cinetica   T = ½·k²   con k = velocità/σ             (moto del trend)
     σ = volatilità giornaliera (EWMA 60): tutto è in "sigma", confrontabile
     tra titoli.

Ipotesi scritte PRIMA di guardare i dati (verifica su 2024-26 fatta una volta):
  H1 scarica: dentro lo stato V2, i giorni in cui il potenziale sta già
     scendendo (lo scostamento rientra) rendono più di quelli in cui sale.
  H2 cinetica di lungo periodo: dentro V2, trend lento in salita > in discesa.
  H3 energia del SISTEMA: V2 rende di più quando tanti titoli sono in V2 insieme.
  H4 profondità: più lo scostamento è profondo (in sigma), più rende.
  H5 compressione: energia totale bassa per giorni → poi movimento ampio,
     nella direzione del trend lento.
  H6 l'energia anticipa l'oracolo: dopo uno stato V2 la pendenza dell'oracolo
     5-20 barre DOPO è positiva più spesso della norma.
  H7 fase potenziale/cinetica (scala veloce): il quadrante (u, k) prevede il
     rendimento; "sotto e in risalita" (u<0, k>0) è il migliore.
Poi: un modello lineare su tutte le grandezze, stimato su 2021-23 e giudicato
su 2024-26, e le regole candidate confrontate con V2.

Significatività: medie settimanali della cella → t sulle settimane.

    backend/venv/bin/python backend/research/energy_patterns.py
    (FPR_PANEL_CACHE=percorso.pkl per riusare prezzi già scaricati)
"""
import pickle

from common import os, np, pd, save_output, fetch_prices, tstat
from logic import ActionPath, kalman_llt_velocity
from stable_strategy import POTENTIAL_ALPHA, POTENTIAL_BETA

FETCH_START = "2019-06-01"
A0, A1, B0 = "2021-01-01", "2023-12-31", "2024-01-01"
LAM_FAST, LAM_SLOW, LAM_VSLOW = 1e-3, 1e-5, 1e-7     # ≈ 8, 25, 80 barre di memoria


def load_panel():
    cache = os.environ.get("FPR_PANEL_CACHE")
    if cache and os.path.exists(cache):
        return pickle.load(open(cache, "rb"))["px"]
    from tickers_loader import load_tickers
    return fetch_prices(sorted(load_tickers()), FETCH_START, min_len=400, workers=8)


def kalman_filter(y, alpha, beta):
    q, r = 1.0 / alpha, 1.0 / beta
    x = np.empty(len(y))
    x[0], P = y[0], r
    for t in range(1, len(y)):
        Pp = P + q
        K = Pp / (Pp + r)
        x[t] = x[t - 1] + K * (y[t] - x[t - 1])
        P = (1 - K) * Pp
    return x


def features(ticker, px):
    lp = np.log(px)
    r = lp.diff()
    sig = r.ewm(span=60, min_periods=20).std()

    # --- macchina A (quella del progetto) ---
    F = px.ewm(span=20, adjust=False).mean()
    xf = kalman_filter(F.values.astype(float), POTENTIAL_ALPHA, POTENTIAL_BETA)
    d = pd.Series(F.values - xf, index=px.index)
    d.iloc[:100] = np.nan
    pot = 0.5 * POTENTIAL_BETA * d ** 2
    z = (pot - pot.rolling(252, min_periods=40).mean()) / (pot.rolling(252, min_periods=40).std() + 1e-9)
    dn = d / (px * sig)                                  # scostamento in sigma giornaliere

    # --- macchina B: livello + velocità a tre scale ---
    out = {}
    for name, lam in (("f", LAM_FAST), ("s", LAM_SLOW), ("v", LAM_VSLOW)):
        k = kalman_llt_velocity(lp, lam)
        lev = pd.Series(k["level"], index=px.index)
        vel = pd.Series(k["velocity"], index=px.index)
        out["u" + name] = (lp - lev) / sig               # molla: prezzo − livello
        out["k" + name] = vel / sig                      # moto: velocità del trend
    E = 0.5 * out["uf"] ** 2 + 0.5 * out["kf"] ** 2      # energia totale, scala veloce
    comp = E.rolling(10).mean() / E.rolling(252, min_periods=120).mean()

    oracle = np.sign(ActionPath(px, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA).dX)
    df = pd.DataFrame({
        "ticker": ticker, "d": d, "z": z, "dn": dn, "dd3": dn - dn.shift(3),
        "uf": out["uf"], "kf": out["kf"], "us": out["us"], "ks": out["ks"], "kv": out["kv"],
        "E": E, "comp": comp, "vr": sig / r.ewm(span=252, min_periods=120).std(),
        "o": oracle, "o5": oracle.shift(-5), "o10": oracle.shift(-10), "o20": oracle.shift(-20),
        "om10": oracle.shift(10),
        "ret": px.pct_change().shift(-2),
        "fwd10": px.shift(-11) / px.shift(-1) - 1,
    }, index=px.index)
    df.iloc[:260] = np.nan                               # riscaldamento dei filtri
    df["ticker"] = ticker
    return df


def build(prices):
    frames = []
    for t, px in prices.items():
        try:
            frames.append(features(t, px))
        except Exception:
            continue
    panel = pd.concat(frames).sort_index()
    panel = panel[panel.index >= A0].dropna(subset=["d", "z", "ret", "uf", "kv"])
    panel["v2"] = (panel["z"] > 0) & (panel["d"] < 0)
    # energia del sistema: quota di titoli nello stato V2 quel giorno (solo giorni con mercato pieno)
    g = panel.groupby(level=0)["v2"]
    breadth = (g.mean()[g.count() >= 300]).reindex(sorted(set(panel.index))).ffill()
    panel["sys"] = breadth.reindex(panel.index).values
    return panel.dropna(subset=["sys"])


def cell(df, mask):
    """quota di osservazioni, rendimento grezzo e in eccesso sulla media del titolo (bps/giorno), t settimanale."""
    c = df[mask]
    if len(c) < 300:
        return None
    g = c["ex"].groupby(pd.Grouper(freq="W"))
    w = (g.sum() / g.count())[g.count() >= 30]
    return {"share": len(c) / len(df), "raw": float(c["ret"].mean() * 1e4),
            "ex": float(c["ex"].mean() * 1e4), "t": tstat(w.values), "weeks": int(len(w))}


def show(title, rows, A, B, store):
    print(f"\n--- {title} ---")
    print(f"{'cella':46s} | {'2021-23: quota':>14s} {'ecc. bps':>9s} {'t':>5s} | {'2024-26: quota':>14s} {'ecc. bps':>9s} {'t':>5s}")
    for label, fn in rows:
        a, b = cell(A, fn(A)), cell(B, fn(B))
        store[f"{title} | {label}"] = {"A": a, "B": b}
        fa = f"{a['share'] * 100:13.1f}% {a['ex']:+9.1f} {a['t']:5.1f}" if a else f"{'—':>30s}"
        fb = f"{b['share'] * 100:13.1f}% {b['ex']:+9.1f} {b['t']:5.1f}" if b else f"{'—':>30s}"
        print(f"{label:46s} | {fa} | {fb}")


def get_panel():
    cache = os.environ.get("FPR_FEATURE_CACHE")
    if cache and os.path.exists(cache):
        return pd.read_pickle(cache)
    panel = build(load_panel())
    if cache:
        panel.to_pickle(cache)
    return panel


def decay(panel, mask, horizon=12):
    """Rendimento in eccesso (bps) nel giorno j dopo l'esecuzione, per le osservazioni in `mask`."""
    g = panel.groupby("ticker")["exall"]
    out = []
    for j in range(horizon):
        out.append(float(g.shift(-j)[mask].mean() * 1e4))
    return out


def ridge_fit(X, y, lam=10.0):
    XtX = X.T @ X + lam * np.eye(X.shape[1])
    return np.linalg.solve(XtX, X.T @ y)


def design(df, mu=None, sd=None):
    c = lambda v, lo, hi: np.clip(v, lo, hi)
    v2 = df["v2"].astype(float)
    cols = {
        "dn": c(df["dn"], -8, 8), "z": c(df["z"], -3, 6), "uf": c(df["uf"], -6, 6), "kf": c(df["kf"], -3, 3),
        "us": c(df["us"], -8, 8), "ks": c(df["ks"], -2, 2), "kv": c(df["kv"], -1, 1), "sys": df["sys"],
        "vr": c(df["vr"], 0.3, 3), "dd3": c(df["dd3"], -4, 4),
        "uf_neg": c(df["uf"], -6, 0), "dn_neg": c(df["dn"], -8, 0),
        "falling": ((df["uf"] < 0) & (df["kf"] < 0)).astype(float),
        "v2": v2, "v2_sys": v2 * df["sys"], "v2_uf_neg": v2 * c(df["uf"], -6, 0),
        "v2_falling": v2 * ((df["uf"] < 0) & (df["kf"] < 0)).astype(float),
        "ufneg_sys": c(df["uf"], -6, 0) * df["sys"],
    }
    X = pd.DataFrame(cols, index=df.index).fillna(0.0)
    if mu is None:
        mu, sd = X.mean(), X.std() + 1e-9
    Xs = ((X - mu) / sd)
    Xs["const"] = 1.0
    return Xs, mu, sd


def simulate_account(R, sig, score, spy, hold=10, slots=10, core="SPY", cost=0.05):
    """
    Conto a `slots` posti uguali, giorno per giorno (valori a mercato).
    Segnale alla chiusura i → acquisto alla chiusura i+1 → tenuto `hold` giorni
    (un nuovo segnale sullo stesso titolo allunga la tenuta). Quando i segnali
    sono più dei posti liberi entrano quelli col punteggio più alto.
    I posti senza segnale stanno nell'indice (core="SPY") o in cassa (core=None).
    cost: % per lato, applicato a ogni compravendita (anche dell'indice).
    R, sig, score: matrici giorni × titoli (numpy); spy: rendimenti dell'indice.
    """
    n, m = R.shape
    held = {}                                    # titolo → giorni residui
    eq, curve, in_names, rotations = 1.0, [], 0, 0
    for i in range(1, n):
        # rendimento del giorno i con le posizioni decise alla chiusura i-1
        day = 0.0
        for j in held:
            rj = R[i, j]
            day += (rj if rj == rj else 0.0)
        idle = slots - len(held)
        if core == "SPY":
            day += idle * spy[i]
        eq *= 1.0 + day / slots
        in_names += len(held)
        # alla chiusura i: escono le posizioni scadute, entrano i segnali della chiusura i-1
        trades = 0
        for j in list(held):
            held[j] -= 1
        cand = np.flatnonzero(sig[i - 1])
        for j in cand:
            if j in held:
                held[j] = hold
        for j in [j for j, left in held.items() if left <= 0]:
            del held[j]
            trades += 1
        free = slots - len(held)
        if free > 0 and len(cand):
            new = [j for j in cand if j not in held and R[i, j] == R[i, j]]
            new.sort(key=lambda j: -score[i - 1, j])
            for j in new[:free]:
                held[j] = hold
                trades += 1
        if trades:
            eq *= 1.0 - trades * (cost / 100.0) * (2 if core == "SPY" else 1) / slots
            rotations += trades
        curve.append(eq)
    c = np.array(curve)
    d = np.diff(np.log(c))
    years = n / 252.0
    return {"ann": float((c[-1] ** (1 / years) - 1) * 100), "vol": float(d.std() * np.sqrt(252) * 100),
            "sharpe": float(d.mean() / d.std() * np.sqrt(252)) if d.std() > 0 else float("nan"),
            "maxdd": float((1 - c / np.maximum.accumulate(c)).max() * 100),
            "busy": float(in_names / (slots * (n - 1)) * 100), "rot_y": float(rotations / years)}


def main():
    panel = get_panel()
    A = panel[panel.index <= A1].copy()
    B = panel[panel.index >= B0].copy()
    for df in (A, B):
        df["ex"] = df["ret"] - df.groupby("ticker")["ret"].transform("mean")
        df["exm"] = df["ret"] - df.groupby(level=0)["ret"].transform("mean")     # contro la media dei titoli quel giorno
    print(f"titoli {panel['ticker'].nunique()} | osservazioni {len(panel):,} | {A0} → {panel.index.max():%Y-%m-%d}")
    print(f"stato V2: {A['v2'].mean() * 100:.1f}% dei giorni (2021-23), {B['v2'].mean() * 100:.1f}% (2024-26)")
    S = {}

    # soglie definite SOLO sul primo periodo
    sys_q = A["sys"].quantile([1 / 3, 2 / 3]).values
    dn_q = A.loc[A["v2"], "dn"].quantile([1 / 3, 2 / 3]).values
    print(f"terzili energia del sistema (quota titoli in V2): {sys_q[0] * 100:.1f}% / {sys_q[1] * 100:.1f}% | "
          f"terzili profondità in V2: {dn_q[0]:.2f} / {dn_q[1]:.2f} sigma")

    show("Base", [("stato V2 (tutti i giorni)", lambda d: d["v2"]),
                  ("fuori da V2", lambda d: ~d["v2"])], A, B, S)
    show("H1 scarica del potenziale (dentro V2)", [
        ("potenziale in discesa (scostamento rientra)", lambda d: d["v2"] & (d["dd3"] > 0)),
        ("potenziale ancora in salita", lambda d: d["v2"] & (d["dd3"] <= 0))], A, B, S)
    show("H2 trend lento (dentro V2)", [
        ("trend lento in salita", lambda d: d["v2"] & (d["kv"] > 0)),
        ("trend lento in discesa", lambda d: d["v2"] & (d["kv"] <= 0))], A, B, S)
    show("H3 energia del sistema (dentro V2)", [
        ("pochi titoli in V2 (sistema calmo)", lambda d: d["v2"] & (d["sys"] <= sys_q[0])),
        ("medio", lambda d: d["v2"] & (d["sys"] > sys_q[0]) & (d["sys"] <= sys_q[1])),
        ("molti titoli in V2 (sistema carico)", lambda d: d["v2"] & (d["sys"] > sys_q[1]))], A, B, S)
    show("H3b energia del sistema (TUTTI i titoli, anche fuori da V2)", [
        ("sistema calmo", lambda d: d["sys"] <= sys_q[0]),
        ("medio", lambda d: (d["sys"] > sys_q[0]) & (d["sys"] <= sys_q[1])),
        ("sistema carico", lambda d: d["sys"] > sys_q[1]),
        ("sistema carico, titolo NON in V2", lambda d: (d["sys"] > sys_q[1]) & ~d["v2"])], A, B, S)
    show("H4 profondità dello scostamento (dentro V2)", [
        ("più profondo (terzile)", lambda d: d["v2"] & (d["dn"] <= dn_q[0])),
        ("medio", lambda d: d["v2"] & (d["dn"] > dn_q[0]) & (d["dn"] <= dn_q[1])),
        ("meno profondo", lambda d: d["v2"] & (d["dn"] > dn_q[1]))], A, B, S)
    show("H5 compressione dell'energia (energia 10gg < metà della media annua)", [
        ("compressa + trend lento su", lambda d: (d["comp"] < 0.5) & (d["kv"] > 0)),
        ("compressa + trend lento giù", lambda d: (d["comp"] < 0.5) & (d["kv"] <= 0)),
        ("non compressa", lambda d: d["comp"] >= 0.5)], A, B, S)
    show("H7 fase potenziale/cinetica, scala veloce (tutti i giorni)", [
        ("sotto il livello, velocità su  (u<0,k>0)", lambda d: (d["uf"] < 0) & (d["kf"] > 0)),
        ("sotto il livello, velocità giù (u<0,k<0)", lambda d: (d["uf"] < 0) & (d["kf"] <= 0)),
        ("sopra il livello, velocità su  (u>0,k>0)", lambda d: (d["uf"] >= 0) & (d["kf"] > 0)),
        ("sopra il livello, velocità giù (u>0,k<0)", lambda d: (d["uf"] >= 0) & (d["kf"] <= 0))], A, B, S)
    show("H7b la stessa fase, dentro V2", [
        ("V2 + sotto, velocità su", lambda d: d["v2"] & (d["uf"] < 0) & (d["kf"] > 0)),
        ("V2 + sotto, velocità giù", lambda d: d["v2"] & (d["uf"] < 0) & (d["kf"] <= 0)),
        ("V2 + sopra il livello veloce", lambda d: d["v2"] & (d["uf"] >= 0))], A, B, S)

    # ---------- H5: la compressione prevede l'AMPIEZZA? ----------
    print("\n--- H5b ampiezza del movimento nei 10 giorni dopo (|rendimento| / sigma attesa) ---")
    for label, df in (("2021-23", A), ("2024-26", B)):
        amp = (df["fwd10"].abs())
        c, n = amp[df["comp"] < 0.5].mean(), amp[df["comp"] >= 0.5].mean()
        print(f"  {label}: dopo compressione {c * 100:.2f}% | altrimenti {n * 100:.2f}%")

    # ---------- H6: l'energia anticipa l'oracolo? ----------
    print("\n--- H6 pendenza dell'oracolo: quanto spesso è POSITIVA ---")
    print(f"{'condizione oggi':44s} {'10 prima':>9s} {'oggi':>7s} {'+5':>7s} {'+10':>7s} {'+20':>7s}")
    H6 = {}
    conds = [("tutti i giorni", lambda d: d["z"] > -99),
             ("segno causale su (d>0)", lambda d: d["d"] > 0),
             ("segno causale giù (d<0), energia bassa", lambda d: (d["d"] < 0) & (d["z"] <= 0)),
             ("stato V2 (d<0, energia sopra media)", lambda d: d["v2"]),
             ("V2 con energia z>2", lambda d: d["v2"] & (d["z"] > 2)),
             ("V2 + sistema carico", lambda d: d["v2"] & (d["sys"] > sys_q[1])),
             ("segno su (d>0) + energia sopra media", lambda d: (d["d"] > 0) & (d["z"] > 0)),
             ("segno su (d>0) + energia sotto media", lambda d: (d["d"] > 0) & (d["z"] <= 0))]
    for label, fn in conds:
        c = panel[fn(panel)]
        row = {k: float((c[k] > 0).mean() * 100) for k in ("om10", "o", "o5", "o10", "o20")}
        H6[label] = row
        print(f"{label:44s} {row['om10']:8.1f}% {row['o']:6.1f}% {row['o5']:6.1f}% {row['o10']:6.1f}% {row['o20']:6.1f}%")

    # =====================================================================
    # SECONDO GIRO — dopo aver visto il primo: il vantaggio sta nei giorni in
    # cui il titolo sta ANCORA scendendo (potenziale in carica) e quando la
    # discesa è di tutto il sistema. Qui si misura quanto, per quanto tempo,
    # e cosa aggiunge un modello su tutte le grandezze insieme.
    # =====================================================================
    fall = lambda d: (d["uf"] < 0) & (d["kf"] < 0)             # sotto il livello veloce e velocità in giù
    loaded = lambda d: d["sys"] > sys_q[0]                      # sistema non calmo (soglia dal 1° periodo)

    show("G1 tre condizioni insieme (V2 × in caduta × sistema)", [
        ("V2 + in caduta + sistema non calmo", lambda d: d["v2"] & fall(d) & loaded(d)),
        ("V2 + in caduta + sistema calmo", lambda d: d["v2"] & fall(d) & ~loaded(d)),
        ("V2 + NON in caduta + sistema non calmo", lambda d: d["v2"] & ~fall(d) & loaded(d)),
        ("V2 + NON in caduta + sistema calmo", lambda d: d["v2"] & ~fall(d) & ~loaded(d))], A, B, S)
    show("G2 prima del segnale: energia veloce, titolo NON ancora in V2", [
        ("non V2, in caduta oltre 2 sigma", lambda d: ~d["v2"] & fall(d) & (d["uf"] < -2)),
        ("non V2, in caduta tra 1 e 2 sigma", lambda d: ~d["v2"] & fall(d) & (d["uf"] >= -2) & (d["uf"] < -1)),
        ("non V2, in caduta meno di 1 sigma", lambda d: ~d["v2"] & fall(d) & (d["uf"] >= -1)),
        ("non V2, in caduta oltre 1 sigma + sistema non calmo", lambda d: ~d["v2"] & fall(d) & (d["uf"] < -1) & loaded(d))], A, B, S)
    show("G3 in caduta, per profondità veloce (tutti i giorni)", [
        ("in caduta oltre 2 sigma", lambda d: fall(d) & (d["uf"] < -2)),
        ("in caduta tra 1 e 2 sigma", lambda d: fall(d) & (d["uf"] >= -2) & (d["uf"] < -1)),
        ("in caduta meno di 1 sigma", lambda d: fall(d) & (d["uf"] >= -1)),
        ("in salita oltre 2 sigma (u>2, k>0)", lambda d: (d["uf"] > 2) & (d["kf"] > 0))], A, B, S)
    show("G4 regime di volatilità (dentro V2 + in caduta)", [
        ("volatilità recente sopra la sua media", lambda d: d["v2"] & fall(d) & (d["vr"] > 1)),
        ("volatilità recente sotto la sua media", lambda d: d["v2"] & fall(d) & (d["vr"] <= 1))], A, B, S)
    klass = lambda d: d["ticker"].str.endswith("-USD")
    show("G5 per classe (V2 + in caduta)", [
        ("azioni, ETF, materie prime, valute", lambda d: d["v2"] & fall(d) & ~klass(d)),
        ("crypto", lambda d: d["v2"] & fall(d) & klass(d))], A, B, S)

    # ---------- profilo nel tempo: per quanti giorni dura il vantaggio ----------
    panel["exall"] = panel["ret"] - panel.groupby("ticker")["ret"].transform("mean")
    print("\n--- Profilo: rendimento in eccesso (bps) nei giorni successivi all'esecuzione ---")
    print(f"{'stato alla decisione':42s} " + " ".join(f"g{j + 1:>4d}" for j in range(12)) + "   somma 1-5  somma 6-12")
    prof = {}
    for label, per, m in (
        ("V2 + in caduta (2021-23)", "A", panel["v2"] & fall(panel) & (panel.index <= A1)),
        ("V2 + in caduta (2024-26)", "B", panel["v2"] & fall(panel) & (panel.index >= B0)),
        ("V2 NON in caduta (2021-23)", "A", panel["v2"] & ~fall(panel) & (panel.index <= A1)),
        ("V2 NON in caduta (2024-26)", "B", panel["v2"] & ~fall(panel) & (panel.index >= B0)),
        ("in caduta >1σ, non V2 (2021-23)", "A", ~panel["v2"] & fall(panel) & (panel["uf"] < -1) & (panel.index <= A1)),
        ("in caduta >1σ, non V2 (2024-26)", "B", ~panel["v2"] & fall(panel) & (panel["uf"] < -1) & (panel.index >= B0)),
    ):
        dc = decay(panel, m)
        prof[label] = dc
        print(f"{label:42s} " + " ".join(f"{v:+5.0f}" for v in dc) + f"   {sum(dc[:5]):+8.0f}  {sum(dc[5:]):+9.0f}")

    # ---------- modello lineare su tutte le grandezze: stimato su 2021-23, giudicato su 2024-26 ----------
    XA, mu, sd = design(A)
    XB, _, _ = design(B, mu, sd)
    yA = np.clip(A["ex"].values * 1e4, -1500, 1500)
    w = ridge_fit(XA.values, yA, lam=50.0)
    A["score"], B["score"] = XA.values @ w, XB.values @ w
    print("\n--- Modello lineare (ridge): pesi sulle grandezze standardizzate (bps per 1 deviazione standard) ---")
    order = np.argsort(-np.abs(w[:-1]))
    print("  " + " | ".join(f"{XA.columns[i]} {w[i]:+.1f}" for i in order[:10]))
    cuts = np.quantile(A["score"], [0.5, 0.8, 0.9, 0.95, 0.99])
    print(f"{'fascia di punteggio (soglie dal 2021-23)':42s} | {'2021-23: quota':>14s} {'ecc. bps':>9s} {'t':>5s} | {'2024-26: quota':>14s} {'ecc. bps':>9s} {'t':>5s}")
    bands = [("sotto la mediana", -np.inf, cuts[0]), ("50-80%", cuts[0], cuts[1]), ("80-90%", cuts[1], cuts[2]),
             ("90-95%", cuts[2], cuts[3]), ("95-99%", cuts[3], cuts[4]), ("top 1%", cuts[4], np.inf)]
    model = {}
    for label, lo, hi in bands:
        a = cell(A, (A["score"] > lo) & (A["score"] <= hi))
        b = cell(B, (B["score"] > lo) & (B["score"] <= hi))
        model[label] = {"A": a, "B": b}
        print(f"{label:42s} | {a['share'] * 100:13.1f}% {a['ex']:+9.1f} {a['t']:5.1f} | {b['share'] * 100:13.1f}% {b['ex']:+9.1f} {b['t']:5.1f}")

    # ---------- confronto delle regole come STATO (timing %/anno = quota × eccesso × 252) ----------
    print("\n--- Regole a confronto: timing %/anno del portafoglio a pesi uguali (quota giorni × eccesso), senza costi ---")
    print(f"{'regola (long quando la condizione è vera)':52s} | {'2021-23: tempo':>14s} {'timing':>7s} {'per posto':>10s} | {'2024-26: tempo':>14s} {'timing':>7s} {'per posto':>10s}")
    rules = [
        ("V2 (riferimento)", lambda d: d["v2"]),
        ("V2 + in caduta", lambda d: d["v2"] & fall(d)),
        ("V2 + in caduta + sistema non calmo", lambda d: d["v2"] & fall(d) & loaded(d)),
        ("V2 + sistema non calmo", lambda d: d["v2"] & loaded(d)),
        ("in caduta oltre 1 sigma (anche fuori V2)", lambda d: fall(d) & (d["uf"] < -1)),
        ("in caduta oltre 1 sigma + sistema non calmo", lambda d: fall(d) & (d["uf"] < -1) & loaded(d)),
        ("V2 oppure in caduta oltre 2 sigma", lambda d: d["v2"] | (fall(d) & (d["uf"] < -2))),
        ("modello: punteggio nel top 10% del 2021-23", lambda d: d["score"] > cuts[2]),
        ("modello: punteggio nel top 5% del 2021-23", lambda d: d["score"] > cuts[3]),
    ]
    rr = {}
    for label, fn in rules:
        a, b = cell(A, fn(A)), cell(B, fn(B))
        rr[label] = {"A": a, "B": b}
        ta, tb = a["share"] * a["ex"] * 252 / 100, b["share"] * b["ex"] * 252 / 100
        # "per posto": eccesso annuo per unità di capitale effettivamente investito
        print(f"{label:52s} | {a['share'] * 100:13.1f}% {ta:+7.1f} {a['ex'] * 252 / 100:+9.0f}% | {b['share'] * 100:13.1f}% {tb:+7.1f} {b['ex'] * 252 / 100:+9.0f}%")

    # ---------- quando o quale? lo stesso eccesso misurato contro il mercato dello stesso giorno ----------
    print("\n--- Quando o quale titolo? Eccesso (bps/giorno) sulla media del titolo e sulla media del mercato quel giorno ---")
    print(f"{'stato':44s} | {'2021-23: sul titolo':>19s} {'sul mercato':>12s} {'t':>5s} | {'2024-26: sul titolo':>19s} {'sul mercato':>12s} {'t':>5s}")
    wq = {}
    def tm(df, mask):
        c = df[mask]
        g = c["exm"].groupby(pd.Grouper(freq="W"))
        wk = (g.sum() / g.count())[g.count() >= 30]
        return float(c["ex"].mean() * 1e4), float(c["exm"].mean() * 1e4), tstat(wk.values)
    for label, fn in (("V2", lambda d: d["v2"]),
                      ("V2 + in caduta + sistema non calmo", lambda d: d["v2"] & fall(d) & loaded(d)),
                      ("modello top 5%", lambda d: d["score"] > cuts[3]),
                      ("modello top 1%", lambda d: d["score"] > cuts[4])):
        a, b = tm(A, fn(A)), tm(B, fn(B))
        wq[label] = {"A": a, "B": b}
        print(f"{label:44s} | {a[0]:+19.1f} {a[1]:+12.1f} {a[2]:5.1f} | {b[0]:+19.1f} {b[1]:+12.1f} {b[2]:5.1f}")

    # ---------- nei 10 giorni dopo: quanto e quanto spesso ----------
    print("\n--- Nei 10 giorni dopo l'ingresso: rendimento medio e quota di casi positivi ---")
    f10 = {}
    for label, fn in (("un giorno qualsiasi", lambda d: d["z"] > -99), ("V2", lambda d: d["v2"]),
                      ("V2 + in caduta + sistema non calmo", lambda d: d["v2"] & fall(d) & loaded(d)),
                      ("modello top 5%", lambda d: d["score"] > cuts[3]), ("modello top 1%", lambda d: d["score"] > cuts[4])):
        row = []
        for df in (A, B):
            c = df.loc[fn(df), "fwd10"].dropna()
            row += [float(c.mean() * 100), float((c > 0).mean() * 100), float(c.quantile(0.05) * 100)]
        f10[label] = row
        print(f"  {label:38s} 2021-23: {row[0]:+5.2f}%  positivi {row[1]:4.1f}%  5% peggiore {row[2]:+6.1f}%   |   2024-26: {row[3]:+5.2f}%  positivi {row[4]:4.1f}%  5% peggiore {row[5]:+6.1f}%")

    # ---------- conto reale a 10 posti, valori a mercato, costi 0.05% per lato ----------
    prices = load_panel()
    spy_px = prices["SPY"]
    cal = spy_px.index[spy_px.index >= A0]
    tick = sorted(panel["ticker"].unique())
    P = pd.DataFrame({t: prices[t].reindex(cal, method="ffill") for t in tick})
    Rw = P.pct_change()
    first = {t: prices[t].index.min() for t in tick}
    for t in tick:                                         # nessun rendimento prima che il titolo esista
        Rw.loc[Rw.index < first[t], t] = np.nan
    full = pd.concat([A, B])
    wide = lambda col: full.pivot(columns="ticker", values=col).reindex(index=cal, columns=tick)
    SC = wide("score").fillna(-1e9).values
    full["v3"] = full["v2"] & fall(full) & loaded(full)
    rng = np.random.default_rng(42)
    RND = rng.random(SC.shape)
    V2w = wide("v2").fillna(False).values.astype(bool)
    rules_acc = [
        ("controllo: segnali a caso (stessa frequenza di V2)", RND < V2w.mean(), None),
        ("V2 (precedenza a caso)", V2w, None),
        ("V2 (precedenza al punteggio)", V2w, SC),
        ("V2 + in caduta + sistema non calmo", wide("v3").fillna(False).values.astype(bool), SC),
        ("modello top 10%", SC > cuts[2], SC),
        ("modello top 5%", SC > cuts[3], SC),
        ("modello top 1%", SC > cuts[4], SC),
    ]
    RND2 = np.random.default_rng(7).random(SC.shape)
    acc = {}
    spy_r = Rw["SPY"].fillna(0).values
    ew_r = Rw.mean(axis=1).fillna(0).values
    for label, lo_d, hi_d in (("2021-23", A0, A1), ("2024-26 (verifica)", B0, "2100-01-01")):
        m = (cal >= lo_d) & (cal <= hi_d)
        Rm, spym = Rw.values[m], spy_r[m]
        yrs = m.sum() / 252
        bh = lambda r: {"ann": float((np.prod(1 + r) ** (1 / yrs) - 1) * 100), "vol": float(np.std(np.log1p(r)) * np.sqrt(252) * 100),
                        "maxdd": float((1 - np.cumprod(1 + r) / np.maximum.accumulate(np.cumprod(1 + r))).max() * 100)}
        b_spy, b_ew = bh(spym), bh(ew_r[m])
        print(f"\n--- Conto a 10 posti, tenuta 10 giorni, costi 0.05% per lato — {label} ---")
        print(f"  solo indice SPY: {b_spy['ann']:+.1f}%/anno, ribasso massimo {b_spy['maxdd']:.0f}% | tutti i titoli a pesi uguali: {b_ew['ann']:+.1f}%/anno, ribasso massimo {b_ew['maxdd']:.0f}%")
        print(f"  {'regola':50s} | {'posti liberi in CASSA:':>22s} {'%/anno':>7s} {'ribasso':>8s} {'Sharpe':>7s} | {'posti liberi nell INDICE:':>25s} {'%/anno':>7s} {'vs SPY':>7s} {'ribasso':>8s} {'Sharpe':>7s} | {'posti occupati':>14s}")
        for name, sg, sc in rules_acc:
            scm = (RND2 if sc is None else sc)[m]
            cash = simulate_account(Rm, sg[m], scm, spym, core=None)
            idx = simulate_account(Rm, sg[m], scm, spym, core="SPY")
            acc[f"{label} | {name}"] = {"cash": cash, "index": idx, "spy": b_spy}
            print(f"  {name:50s} | {'':22s} {cash['ann']:+7.1f} {cash['maxdd']:7.0f}% {cash['sharpe']:7.2f} | {'':25s} {idx['ann']:+7.1f} {idx['ann'] - b_spy['ann']:+7.1f} {idx['maxdd']:7.0f}% {idx['sharpe']:7.2f} | {idx['busy']:13.0f}%")

    # =====================================================================
    # ENERGIA DEL SISTEMA → MERCATO. Dai giri precedenti: mediato per giorno,
    # il titolo in V2 non batte il mercato; conta QUANDO. Qui la domanda è
    # posta direttamente all'indice: quota di titoli in V2 (potenziale carico
    # verso il basso) alla chiusura t → rendimento di SPY dal giorno t+2.
    # =====================================================================
    gb = panel.groupby(level=0)
    okd = gb["v2"].count() >= 300
    bq = gb["v2"].mean()[okd].reindex(cal).ffill()
    upq = gb.apply(lambda d: ((d["z"] > 0) & (d["d"] > 0)).mean())[okd].reindex(cal).ffill()
    spy_full = prices["SPY"]
    s1 = spy_full.pct_change().shift(-2).reindex(cal)
    s21 = (spy_full.shift(-22) / spy_full.shift(-1) - 1).reindex(cal)
    print(f"\n--- ENERGIA DEL SISTEMA: quota di titoli in V2 → SPY (media di tutti i giorni {s1.mean() * 1e4:+.1f} bps, a 21 giorni {s21.mean() * 100:+.2f}%) ---")
    print(f"{'quota titoli in V2':20s} {'giorni':>7s} {'SPY giorno dopo':>16s} {'2021-23':>9s} {'2024-26':>9s} {'SPY a 21 gg':>12s} {'positivi':>9s}")
    sysm = {}
    isA, isB = cal <= A1, cal >= B0
    for lo, hi in ((0, .05), (.05, .125), (.125, .20), (.20, .30), (.30, .45), (.45, 1.01)):
        m = ((bq >= lo) & (bq < hi)).values
        if m.sum() < 5:
            continue
        sysm[f"{lo}-{hi}"] = {"days": int(m.sum()), "next_bps": float(s1[m].mean() * 1e4), "A": float(s1[m & isA].mean() * 1e4),
                              "B": float(s1[m & isB].mean() * 1e4), "fwd21": float(s21[m].mean() * 100)}
        print(f"{lo * 100:4.0f}% – {min(hi, 1) * 100:3.0f}%          {int(m.sum()):7d} {s1[m].mean() * 1e4:+12.1f} bps {s1[m & isA].mean() * 1e4:+9.1f} {s1[m & isB].mean() * 1e4:+9.1f} "
              f"{s21[m].mean() * 100:+11.2f}% {(s21[m] > 0).mean() * 100:8.0f}%")

    # episodi: i giorni sopra soglia non sono prove indipendenti, gli episodi sì
    TH = 0.30
    posi = {d: i for i, d in enumerate(spy_full.index)}
    hot = [d for d in cal if bq[d] >= TH]
    eps, cur = [], [hot[0]]
    for d in hot[1:]:
        if posi[d] - posi[cur[-1]] > 10:
            eps.append(cur)
            cur = [d]
        else:
            cur.append(d)
    eps.append(cur)
    print(f"\n--- Episodi con quota ≥ {TH * 100:.0f}% (separati da più di 10 sedute): ingresso alla chiusura successiva al primo giorno ---")
    print(f"{'inizio':12s} {'giorni':>6s} {'picco':>6s} {'SPY +10':>8s} {'SPY +21':>8s} {'SPY +63':>8s} {'punto più basso entro 21 gg':>28s}")
    ep_rows = []
    for e in eps:
        i = posi[e[0]] + 1
        f = lambda h: float((spy_full.iloc[i + h] / spy_full.iloc[i] - 1) * 100) if i + h < len(spy_full) else float("nan")
        worst = float((spy_full.iloc[i:i + 22].min() / spy_full.iloc[i] - 1) * 100)
        ep_rows.append({"start": f"{e[0]:%Y-%m-%d}", "days": len(e), "peak": float(max(bq[d] for d in e)), "f10": f(10), "f21": f(21), "f63": f(63), "worst": worst})
        print(f"{e[0]:%Y-%m-%d}   {len(e):6d} {max(bq[d] for d in e) * 100:5.0f}% {f(10):+7.1f}% {f(21):+7.1f}% {f(63):+7.1f}% {worst:+27.1f}%")
    f21 = np.array([r["f21"] for r in ep_rows])
    f21 = f21[~np.isnan(f21)]
    base21 = float(s21.mean() * 100)
    t_ep = float((f21.mean() - base21) / (f21.std(ddof=1) / np.sqrt(len(f21))))
    print(f"episodi {len(ep_rows)} | a 21 giorni: media {f21.mean():+.1f}% contro {base21:+.2f}% di un giorno qualsiasi, positivi {int((f21 > 0).sum())} su {len(f21)}, t sugli episodi {t_ep:.1f}")

    print("\n--- Robustezza: SPY del giorno dopo (bps) nei giorni sopra soglia — 2021-23 / 2024-26 — e altri indici ---")
    others = {k: prices[k].pct_change().shift(-2).reindex(cal) for k in ("SPY", "QQQ", "IWM") if k in prices}
    for th in (0.20, 0.25, 0.30, 0.35, 0.40):
        m = (bq >= th).values
        print(f"  quota ≥ {th * 100:.0f}%: giorni {int((m & isA).sum())}/{int((m & isB).sum())} | " +
              " | ".join(f"{k} {v[m & isA].mean() * 1e4:+.0f} / {v[m & isB].mean() * 1e4:+.0f}" for k, v in others.items()))
    print("  per anno (giorni sopra 30% → SPY dopo | resto dell'anno): " + " · ".join(
        f"{y}: {int(((bq >= TH).values & (cal.year == y)).sum())}gg {s1[(bq >= TH).values & (cal.year == y)].mean() * 1e4:+.0f} | {s1[~(bq >= TH).values & (cal.year == y)].mean() * 1e4:+.0f}"
        for y in range(2021, 2027) if ((bq >= TH).values & (cal.year == y)).sum() > 0))

    print("\n--- Misura dell'effetto come regola di esposizione su SPY (senza costi; il costo della leva non è contato) ---")
    def expo(w, label):
        out, rec = [], {}
        for per, pm in (("2021-23", isA), ("2024-26", isB), ("tutto", cal >= A0)):
            x = (w * s1)[pm].dropna()
            c = np.cumprod(1 + x.values)
            yrs = len(x) / 252
            rec[per] = {"ann": float((c[-1] ** (1 / yrs) - 1) * 100), "sharpe": float(x.mean() / x.std() * np.sqrt(252)),
                        "maxdd": float((1 - c / np.maximum.accumulate(c)).max() * 100), "expo": float(w[pm].mean())}
            out.append(f"{per}: {rec[per]['ann']:+5.1f}%/anno, Sharpe {rec[per]['sharpe']:.2f}, ribasso {rec[per]['maxdd']:.0f}%, esposizione {rec[per]['expo']:.2f}")
        print(f"  {label:48s} " + " | ".join(out))
        return rec
    one = pd.Series(1.0, index=cal)
    exr = {
        "solo SPY": expo(one, "solo SPY"),
        "doppio sopra 30%": expo(one + 1.0 * (bq >= TH), "esposizione doppia quando quota ≥ 30%"),
        "metà/pieno": expo(0.5 * one + 0.5 * (bq >= TH), "metà normalmente, piena quando quota ≥ 30%"),
        "fuori 12-30, doppio sopra": expo(one - 1.0 * ((bq >= .125) & (bq < TH)) + 1.0 * (bq >= TH), "fuori tra 12% e 30% (carica), doppia sopra 30%"),
        "metà se energia su ≥30%": expo(one - 0.5 * (upq >= .30), "metà quando l'energia verso l'ALTO è ≥ 30%"),
    }

    save_output("energy_patterns.json", {"cells": S, "H6": H6, "sys_q": list(map(float, sys_q)), "dn_q": list(map(float, dn_q)),
                                         "profile": prof, "model_bands": model, "rules": rr, "when_or_which": wq,
                                         "system_buckets": sysm, "system_episodes": ep_rows, "system_t_episodes": t_ep,
                                         "system_exposure": exr,
                                         "fwd10": f10, "account": acc,
                                         "weights": {XA.columns[i]: float(w[i]) for i in range(len(w))}})
    return panel, A, B, S


if __name__ == "__main__":
    main()
