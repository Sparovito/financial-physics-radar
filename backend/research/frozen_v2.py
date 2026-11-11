"""
FROZEN V2 — scomposizione del segnale Frozen e ricerca di una direzione.

Domanda: il Frozen entra quando l'energia potenziale (z-score) è sopra la
media, ma l'energia è un QUADRATO: non ha segno. Si può dare al segnale una
direzione (long / short) che regga fuori campione?

Scomposizione: potenziale = ½β·d², con d = F − x_f (EMA20 meno il suo filtro
di Kalman causale). d HA un segno: >0 il prezzo recente sta sopra il percorso
filtrato (spinta in su), <0 sotto. Nel modello local-level la miglior stima
causale della pendenza dell'oracolo è proporzionale a d: il segno di d è
tutta l'informazione di direzione che il modello può dare in tempo reale.

Cosa misura lo script (tutto con decisione alla chiusura t, esecuzione alla
chiusura t+1, quindi primo rendimento incassato = quello del giorno t+2):
  1. quanto spesso il segno causale coincide con quello dell'oracolo, e con
     quanto ritardo;
  2. rendimento del giorno successivo per ZONA di energia × DIREZIONE,
     al netto della media del titolo (timing) e della media del giorno (mercato);
  3. regole long/short candidate: scelte sul primo periodo, giudicate sul secondo.
Significatività: medie giornaliere tra titoli → somme settimanali → t sulle
settimane (i titoli si muovono insieme: il t tra titoli sarebbe gonfiato).

    backend/venv/bin/python backend/research/frozen_v2.py
    (FPR_PANEL_CACHE=percorso.pkl per riusare prezzi già scaricati)
"""
import pickle

from common import os, np, pd, save_output, fetch_prices, tstat
from logic import ActionPath
from stable_strategy import POTENTIAL_ALPHA, POTENTIAL_BETA

FETCH_START = "2019-06-01"
A0, A1 = "2021-01-01", "2023-12-31"      # periodo di scelta
B0 = "2024-01-01"                         # periodo di verifica
COST = 0.05                               # % per lato
ZONES = [(-np.inf, 0.0, "z<0"), (0.0, 1.0, "0-1"), (1.0, 2.0, "1-2"), (2.0, np.inf, "z>2")]


def load_panel():
    cache = os.environ.get("FPR_PANEL_CACHE")
    if cache and os.path.exists(cache):
        return pickle.load(open(cache, "rb"))["px"]
    from tickers_loader import load_tickers
    return fetch_prices(sorted(load_tickers()), FETCH_START, min_len=400, workers=8)


def kalman_filter(y, alpha, beta):
    """Stessa ricorsione di logic.kalman_frozen_series (solo il filtro)."""
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
    F = px.ewm(span=20, adjust=False).mean()
    xf = kalman_filter(F.values.astype(float), POTENTIAL_ALPHA, POTENTIAL_BETA)
    d = F.values - xf
    d[:100] = np.nan
    pot = pd.Series(0.5 * POTENTIAL_BETA * d ** 2, index=px.index)
    z = (pot - pot.rolling(252, min_periods=40).mean()) / (pot.rolling(252, min_periods=40).std() + 1e-6)
    r = px.pct_change()
    oracle = ActionPath(px, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA).dX
    df = pd.DataFrame({
        "ticker": ticker,
        "d": d,
        "z": z.values,
        "o": np.sign(oracle.values),
        "ret": r.shift(-2).values,                       # primo giorno incassato dopo l'esecuzione a t+1
        "fwd5": (px.shift(-6) / px.shift(-1) - 1).values,
    }, index=px.index)
    df["sd"] = np.sign(df["d"])
    # ritardo rispetto all'oracolo: segno causale a t contro segno oracolo a t-k
    lag = {k: float((df["sd"] == df["o"].shift(k)).where(df["sd"].notna() & df["o"].shift(k).notna()).mean())
           for k in (0, 5, 10, 15, 20, 30)}
    return df.dropna(subset=["d", "z", "ret"]), lag


def weekly_cell(values):
    """values: Serie (indice = data) di rendimenti in eccesso delle osservazioni di una cella.
    Media per settimana = somma / numero di osservazioni della settimana (così un sabato
    con le sole crypto non pesa come un giorno con 600 titoli); t sulle medie settimanali."""
    g = values.groupby(pd.Grouper(freq="W"))
    w = (g.sum() / g.count())[g.count() >= 30]
    return float(values.mean() * 1e4), tstat(w.values), len(w)


def cell_table(df, label):
    print(f"\n--- {label}: rendimento del giorno dopo, per zona di energia × direzione ---")
    print(f"{'zona':5s} {'dir':4s} {'% oss':>6s} {'grezzo bps':>11s} {'- media titolo':>15s} {'t':>6s} {'- media giorno':>15s} {'t':>6s}")
    df = df.copy()
    df["ex_t"] = df["ret"] - df.groupby("ticker")["ret"].transform("mean")
    df["ex_m"] = df["ret"] - df.groupby(level=0)["ret"].transform("mean")
    out = {}
    for lo, hi, zn in ZONES:
        for s, sn in ((1, "su"), (-1, "giù")):
            c = df[(df["z"] > lo) & (df["z"] <= hi) & (df["sd"] == s)]
            if len(c) < 500:
                continue
            raw = c["ret"]
            bt, tt, _ = weekly_cell(c["ex_t"])
            bm, tm, _ = weekly_cell(c["ex_m"])
            out[f"{zn}|{sn}"] = {"share": len(c) / len(df), "raw_bps": float(raw.mean() * 1e4),
                                 "ex_ticker_bps": bt, "t_ticker": tt, "ex_market_bps": bm, "t_market": tm}
            print(f"{zn:5s} {sn:4s} {len(c) / len(df) * 100:5.1f}% {raw.mean() * 1e4:+11.1f} {bt:+15.1f} {tt:6.1f} {bm:+15.1f} {tm:6.1f}")
    return out


def rule_positions(df, name, cells=None):
    z, s = df["z"].values, df["sd"].values
    if name == "frozen (long se z>0)":
        return (z > 0).astype(float)
    if name == "sempre long":
        return np.ones(len(df))
    if name == "segno: long su / short giù":
        return s.astype(float)
    if name == "segno solo long":
        return (s > 0).astype(float)
    if name == "energia+segno: z>0 long su / short giù":
        return np.where(z > 0, s, 0.0)
    if name == "contrario: z>0 long giù / short su":
        return np.where(z > 0, -s, 0.0)
    if name == "estremi: z>2 long giù (arancione-stato)":
        return ((z > 2) & (s < 0)).astype(float)
    if name == "V2 long: z>0 e giù":
        return ((z > 0) & (s < 0)).astype(float)
    if name == "V2 long: z>1 e giù":
        return ((z > 1) & (s < 0)).astype(float)
    if name == "dai dati del 1° periodo":
        pos = np.zeros(len(df))
        for (lo, hi, zn) in ZONES:
            for sv, sn in ((1, "su"), (-1, "giù")):
                sign = cells.get(f"{zn}|{sn}", 0)
                if sign:
                    pos[(z > lo) & (z <= hi) & (s == sv)] = sign
        return pos
    raise ValueError(name)


def evaluate(df, pos, years):
    df = df.assign(pos=pos)
    g = df.groupby("ticker")
    mean_pos_long = g["pos"].transform(lambda p: (p > 0).mean())
    mean_pos_short = g["pos"].transform(lambda p: (p < 0).mean())
    pnl = df["pos"] * df["ret"]
    timing = pnl - (mean_pos_long - mean_pos_short) * df["ret"]
    turnover = g["pos"].apply(lambda p: p.diff().abs().sum()).mean() / years
    n_tickers = df["ticker"].nunique()
    # portafoglio a pesi uguali su TUTTI i titoli: chi quel giorno non scambia conta zero
    day = lambda v: v.groupby(level=0).sum() / n_tickers
    wk = lambda v: day(v).groupby(pd.Grouper(freq="W")).sum()
    w_pnl, w_tim = wk(pnl), wk(timing)
    long_leg = day(df["pos"].clip(lower=0) * df["ret"]).sum() / years * 100
    short_leg = day(df["pos"].clip(upper=0) * df["ret"]).sum() / years * 100
    return {
        "long_pct": float((df["pos"] > 0).mean() * 100), "short_pct": float((df["pos"] < 0).mean() * 100),
        "ret_y": float(day(pnl).sum() / years * 100), "long_y": float(long_leg), "short_y": float(short_leg),
        "cost_y": float(turnover * COST),
        "sharpe": float(w_pnl.mean() / w_pnl.std(ddof=1) * np.sqrt(52)) if w_pnl.std(ddof=1) > 0 else float("nan"),
        "timing_y": float(day(timing).sum() / years * 100), "t_timing": tstat(w_tim.values),
        "turnover_y": float(turnover),
    }


def main():
    prices = load_panel()
    frames, lags = [], []
    for t, px in prices.items():
        try:
            df, lag = features(t, px)
        except Exception:
            continue
        frames.append(df)
        lags.append(lag)
    panel = pd.concat(frames).sort_index()
    panel = panel[panel.index >= A0]
    last = panel.index.max().strftime("%Y-%m-%d")
    print(f"titoli {len(frames)} | osservazioni {len(panel):,} | {A0} → {last}")

    # ---------- 1. segno causale contro oracolo ----------
    print("\n--- 1. Quanto spesso il segno causale (d) coincide col segno della pendenza dell'oracolo ---")
    agree = {k: float(np.nanmean([l[k] for l in lags])) for k in lags[0]}
    for k, v in agree.items():
        print(f"  oracolo di {k:2d} barre prima: {v * 100:5.1f}%")
    print(f"  quota di giorni con d>0: {(panel['sd'] > 0).mean() * 100:.1f}% | con z>0: {(panel['z'] > 0).mean() * 100:.1f}%")

    A = panel[(panel.index <= A1)]
    B = panel[(panel.index >= B0)]
    yA = (pd.Timestamp(A1) - pd.Timestamp(A0)).days / 365.25
    yB = (panel.index.max() - pd.Timestamp(B0)).days / 365.25

    # ---------- 2. tabella zone × direzione ----------
    cellsA = cell_table(A, f"PRIMO PERIODO {A0} → {A1}")
    cellsB = cell_table(B, f"SECONDO PERIODO {B0} → {last}")

    # regola "dai dati": celle con |t| ≥ 2 sul PRIMO periodo (al netto della media del titolo)
    chosen = {k: (1 if v["t_ticker"] >= 2 else (-1 if v["t_ticker"] <= -2 else 0)) for k, v in cellsA.items()}
    print("\ncelle scelte sul 1° periodo (|t| ≥ 2):",
          {k: ("LONG" if v > 0 else "SHORT") for k, v in chosen.items() if v} or "nessuna")
    same = [k for k in cellsA if k in cellsB and np.sign(cellsA[k]["ex_ticker_bps"]) == np.sign(cellsB[k]["ex_ticker_bps"])]
    print(f"celle con lo stesso segno nei due periodi: {len(same)} su {len([k for k in cellsA if k in cellsB])}")

    # ---------- 3. regole candidate ----------
    rules = ["sempre long", "frozen (long se z>0)", "segno solo long", "segno: long su / short giù",
             "energia+segno: z>0 long su / short giù", "contrario: z>0 long giù / short su",
             "V2 long: z>0 e giù", "V2 long: z>1 e giù",
             "estremi: z>2 long giù (arancione-stato)", "dai dati del 1° periodo"]
    res = {}
    for label, df, years in (("PRIMO PERIODO", A, yA), ("SECONDO PERIODO (verifica)", B, yB)):
        print(f"\n--- 3. Regole — {label} — rendimenti %/anno del portafoglio a pesi uguali, senza costi ---")
        print(f"{'regola':42s} {'long':>5s} {'short':>6s} {'rend.':>7s} {'gamba L':>8s} {'gamba S':>8s} {'costi':>6s} {'Sharpe':>7s} {'timing':>7s} {'t':>6s}")
        for name in rules:
            e = evaluate(df, rule_positions(df, name, chosen), years)
            res.setdefault(name, {})[label] = e
            print(f"{name:42s} {e['long_pct']:4.0f}% {e['short_pct']:5.0f}% {e['ret_y']:+7.1f} {e['long_y']:+8.1f} {e['short_y']:+8.1f} "
                  f"{e['cost_y']:6.1f} {e['sharpe']:7.2f} {e['timing_y']:+7.1f} {e['t_timing']:6.1f}")

    # ---------- 4. per classe: la regola con segno regge fuori dalle azioni? ----------
    def klass(t):
        return "Crypto" if t.endswith("-USD") else "Valute" if t.endswith("=X") else "Materie prime" if t.endswith("=F") else "Azioni/ETF"
    print("\n--- 4. 'segno: long su / short giù' per classe, periodo intero: timing %/anno (t) ---")
    yAll = (panel.index.max() - pd.Timestamp(A0)).days / 365.25
    by_class = {}
    for k, sub in panel.groupby(panel["ticker"].map(klass)):
        e = evaluate(sub, rule_positions(sub, "segno: long su / short giù"), yAll)
        by_class[k] = e
        print(f"  {k:14s} titoli {sub['ticker'].nunique():4d} | rend. {e['ret_y']:+6.1f} | gamba short {e['short_y']:+6.1f} | timing {e['timing_y']:+6.1f} (t {e['t_timing']:.1f})")

    # ---------- 5. anno per anno: il Frozen di oggi contro la versione con direzione ----------
    print("\n--- 5. Anno per anno: timing %/anno (t settimanale) ---")
    yr_rules = ["frozen (long se z>0)", "V2 long: z>0 e giù", "V2 long: z>1 e giù",
                "estremi: z>2 long giù (arancione-stato)", "segno: long su / short giù"]
    print(f"{'anno':6s} {'sempre long':>12s} " + " ".join(f"{n[:26]:>28s}" for n in yr_rules))
    by_year = {}
    for y, sub in panel.groupby(panel.index.year):
        yrs = max((sub.index.max() - sub.index.min()).days / 365.25, 0.1)
        bh = evaluate(sub, rule_positions(sub, "sempre long"), yrs)["ret_y"]
        row = {}
        for n in yr_rules:
            e = evaluate(sub, rule_positions(sub, n), yrs)
            row[n] = (e["timing_y"], e["t_timing"], e["ret_y"])
        by_year[int(y)] = {"bh": bh, **{n: list(v) for n, v in row.items()}}
        print(f"{y:<6d} {bh:+12.1f} " + " ".join(f"{row[n][0]:+18.1f} (t {row[n][1]:+5.1f})" for n in yr_rules))

    save_output("frozen_v2.json", {"agree": agree, "cells_A": cellsA, "cells_B": cellsB, "chosen": chosen,
                                   "rules": res, "by_class": by_class, "by_year": by_year, "n_tickers": len(frames), "last": last})


if __name__ == "__main__":
    main()
