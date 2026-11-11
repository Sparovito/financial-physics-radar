"""
INTERCETTARE LA PARTENZA CON LA FISICA.

Con i soli prezzi di chiusura la partenza vera e quella falsa nel giorno 0 sono
uguali (oracle_events.py). Qui si aggiunge informazione nuova, ciascuna con il
suo analogo fisico, e si chiede: questa grandezza, misurata nel giorno stesso,
distingue le partenze che proseguono?

  massa               volume del giorno rispetto alla sua mediana a 60 barre
  impulso             massa × velocità: variazione ≥ 2σ con volume ≥ 2× (un "colpo")
  temperatura         escursione massimo-minimo media a 20 barre (agitazione)
  buca di potenziale  il prezzo esce dal massimo delle 40 barre precedenti;
                      "a freddo" se la temperatura era bassa (compressione)
  ordine              efficienza del moto = |spostamento netto| / cammino
                      percorso in 10 barre: da casuale (≈0) a diretto (≈1)
  scale               la direzione veloce gira su mentre quelle lente salgono
                      (interferenza costruttiva) o scendono (distruttiva)
  campo esterno       quota di titoli con direzione in su: balzo di 20 punti in
                      10 barre (il mercato spinge nello stesso verso)
  rallentamento       autocorrelazione dei rendimenti a 60 barre alta (i sistemi
  critico             vicini a una transizione "ricordano" di più)

Rivelatori dichiarati prima di guardare i risultati; per ognuno, nei due
periodi 2021-23 e 2024-26:
  - quante volte scatta;
  - quante volte è vicino (±5 barre) a un ingresso long dell'oracolo;
  - rendimento dei 10 e 20 giorni dopo (ingresso alla chiusura successiva)
    rispetto alla media degli ALTRI titoli negli stessi giorni, con t sulle
    settimane.

    backend/venv/bin/python backend/research/physics_start.py
    (FPR_OHLCV_CACHE=percorso.pkl con {"ohlcv": {ticker: DataFrame O/H/L/C/V}})
"""
import pickle

from common import os, np, pd, save_output, tstat
from logic import ActionPath
from faster_signal import kalman
from nowcast import nowcast_velocity
from oracle_events import zroll, episodes

A0, A1, B0 = "2021-01-01", "2023-12-31", "2024-01-01"
ALPHA = 200.0


def load_ohlcv():
    cache = os.environ.get("FPR_OHLCV_CACHE")
    if cache and os.path.exists(cache):
        return pickle.load(open(cache, "rb"))["ohlcv"]
    import concurrent.futures
    import yfinance as yf
    from tickers_loader import load_tickers

    def one(t):
        try:
            df = yf.Ticker(t).history(start="2019-06-01")[["Open", "High", "Low", "Close", "Volume"]]
            df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
            return t, (df if len(df) >= 400 else None)
        except Exception:
            return t, None
    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for t, df in ex.map(one, sorted(load_tickers())):
            if df is not None:
                out[t] = df
    return out


def shift(a, k):
    return np.r_[np.full(k, np.nan), a[:-k]]


def build(tk, df):
    df = df[(df["Close"] > 0)].copy()
    df = df[~df.index.duplicated(keep="last")]
    p = df["Close"].values.astype(float)
    n, idx = len(p), df.index
    if n < 700:
        return None
    lr = np.zeros(n)
    lr[1:] = np.log(p[1:] / p[:-1])
    sig = pd.Series(lr).ewm(span=60, min_periods=20).std().shift(1).values
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = lr / sig
        V = df["Volume"].values.astype(float)
        vmed = pd.Series(V).rolling(60, min_periods=30).median().shift(1).values
        volrel = np.where(vmed > 0, V / vmed, np.nan)
        hi_, lo_ = np.maximum(df["High"].values.astype(float), p), np.minimum(df["Low"].values.astype(float), p)
        hl = np.log(hi_ / np.where(lo_ > 0, lo_, p))
        temp = pd.Series(hl).ewm(span=20, min_periods=10).mean()
        comp = (temp / temp.rolling(252, min_periods=120).median()).shift(1).values
        prevmax = pd.Series(p).rolling(40, min_periods=40).max().shift(1).values
        brk = p > prevmax
        recent = pd.Series(brk.astype(float)).rolling(10, min_periods=1).max().shift(1).fillna(0).values > 0
        net = p - shift(p, 10)
        path = pd.Series(np.abs(np.r_[0.0, np.diff(p)])).rolling(10).sum().values
        er = np.abs(net) / path
        er_before = pd.Series(er).rolling(6).min().shift(5).values
    F = pd.Series(p).ewm(span=20, adjust=False).mean().values
    xf = kalman(F, ALPHA)
    vn, _ = nowcast_velocity(p, F, xf)
    vn = np.nan_to_num(vn)
    d0 = (vn > 0) & (np.r_[0.0, vn[:-1]] <= 0)
    F100 = pd.Series(p).ewm(span=100, adjust=False).mean().values
    slow_up = F100 > shift(F100, 5)
    sma200 = pd.Series(p).rolling(200).mean().values
    ar1 = pd.Series(lr).rolling(60).corr(pd.Series(lr).shift(1)).values
    vol3 = pd.Series(volrel).rolling(3, min_periods=1).max().values

    v0 = max(260, int(np.searchsorted(idx.values, np.datetime64(A0))))
    hi = n - 25
    if hi - v0 < 300:
        return None
    mech = ActionPath(pd.Series(p, index=idx), alpha=ALPHA, beta=1.0)
    ent = [s for s, e, lg in episodes(zroll(mech.kin_density.values), zroll(mech.dX.values), v0, n - 40) if lg]
    near = np.zeros(n, dtype=bool)
    for s in ent:
        near[max(s - 5, 0):s + 6] = True
    f10, f20 = np.full(n, np.nan), np.full(n, np.nan)
    f10[:-11] = np.log(p[11:] / p[1:-10])
    f20[:-21] = np.log(p[21:] / p[1:-20])
    valid = np.zeros(n, dtype=bool)
    valid[v0:hi] = True
    return {"tk": tk, "idx": idx, "valid": valid, "near": near, "f10": f10, "f20": f20, "up": vn > 0,
            "rs": rs, "volrel": volrel, "comp": comp, "brk": brk & ~recent, "er": er, "er_before": er_before, "net": net,
            "d0": d0, "slow_up": slow_up, "above200": p > sma200, "ar1": ar1, "vol3": vol3,
            "has_vol": bool(np.nanmedian(V[v0:]) > 0)}


def detectors(b, thrust):
    rs, vr, d0 = b["rs"], b["volrel"], b["d0"]
    with np.errstate(invalid="ignore"):
        return {
            "direzione gira su (riferimento)": d0,
            "impulso: +2σ con massa (volume ≥ 2×)": (rs >= 2) & (vr >= 2),
            "velocità senza massa: +2σ, volume < 1×": (rs >= 2) & (vr < 1),
            "massa senza velocità: volume ≥ 2×, prezzo fermo": (vr >= 2) & (np.abs(rs) < 0.5),
            "impulso contrario: −2σ con massa": (rs <= -2) & (vr >= 2),
            "fuga dalla buca a freddo (dopo compressione)": b["brk"] & (b["comp"] < 0.75),
            "fuga dalla buca a caldo": b["brk"] & (b["comp"] > 1.25),
            "da casuale a diretto (efficienza 0.25 → 0.6)": (b["er"] >= 0.6) & (b["net"] > 0) & (b["er_before"] <= 0.25),
            "gira su con le scale lente a favore": d0 & b["slow_up"] & b["above200"],
            "gira su contro le scale lente": d0 & ~b["slow_up"] & ~b["above200"],
            "gira su con il campo del mercato (+20 punti)": d0 & (thrust >= 0.20),
            "gira su col mercato fermo o contrario": d0 & (thrust <= 0.0),
            "gira su con rallentamento critico (AR1 ≥ 0.15)": d0 & (b["ar1"] >= 0.15),
            "gira su con massa (volume ≥ 2× in 3 barre)": d0 & (b["vol3"] >= 2),
        }


def main():
    data = load_ohlcv()
    built = []
    for tk, df in data.items():
        try:
            b = build(tk, df)
        except Exception as e:
            print("errore", tk, e)
            continue
        if b:
            built.append(b)
    print(f"titoli: {len(built)} | con volumi: {sum(b['has_vol'] for b in built)}")

    def wide(key):
        return pd.concat([pd.Series(b[key], index=b["idx"], name=b["tk"]) for b in built], axis=1)
    cnt = wide("valid").sum(axis=1)
    days = cnt.index[cnt >= 300]
    breadth = wide("up").astype(float).where(wide("valid").fillna(False).astype(bool)).mean(axis=1).reindex(days)
    thrust = (breadth - breadth.shift(10))
    m10 = wide("f10").where(wide("valid").fillna(False).astype(bool)).mean(axis=1)
    m20 = wide("f20").where(wide("valid").fillna(False).astype(bool)).mean(axis=1)

    rows = []
    base = {"A": [0, 0], "B": [0, 0]}
    for b in built:
        idx = b["idx"]
        th = thrust.reindex(idx).ffill().values
        det = detectors(b, th)
        a10, a20 = b["f10"] - m10.reindex(idx).values, b["f20"] - m20.reindex(idx).values
        per = np.where(idx <= A1, "A", np.where(idx >= B0, "B", ""))
        for k in ("A", "B"):
            m = b["valid"] & (per == k)
            base[k][0] += int(b["near"][m].sum())
            base[k][1] += int(m.sum())
        for name, mask in det.items():
            if "massa" in name or "volume" in name:
                if not b["has_vol"]:
                    continue
            sel = np.nonzero(np.nan_to_num(mask.astype(float)).astype(bool) & b["valid"] & np.isfinite(a10) & np.isfinite(a20))[0]
            for t in sel:
                rows.append((name, idx[t], per[t], a10[t], a20[t], bool(b["near"][t])))
    E = pd.DataFrame(rows, columns=["det", "date", "per", "x10", "x20", "near"])
    E = E[E["per"] != ""]
    out = {"n_tickers": len(built), "base_near": {k: v[0] / v[1] for k, v in base.items()}, "detectors": {}}
    print(f"giorni vicini (±5 barre) a un ingresso long dell'oracolo, in un giorno qualsiasi: "
          f"{out['base_near']['A']:.1%} (2021-23), {out['base_near']['B']:.1%} (2024-26)")
    print(f"\n{'rivelatore':50s} | {'2021-23: casi  vicino  10 gg (t)        20 gg (t)':>52s} | {'2024-26: casi  vicino  10 gg (t)        20 gg (t)':>52s}")
    for name in dict.fromkeys(E["det"]):
        line, rec = f"{name:50s} |", {}
        for k in ("A", "B"):
            c = E[(E["det"] == name) & (E["per"] == k)]
            if len(c) < 30:
                line += f" {len(c):13d}  {'pochi casi':>36s} |"
                continue
            g = c.groupby(pd.Grouper(key="date", freq="W"))
            t10, t20 = tstat(g["x10"].mean().dropna().values), tstat(g["x20"].mean().dropna().values)
            rec[k] = {"n": int(len(c)), "near": float(c["near"].mean()), "x10": float(c["x10"].mean()), "t10": t10,
                      "x20": float(c["x20"].mean()), "t20": t20}
            line += (f" {len(c):13d} {c['near'].mean():6.0%}  {np.expm1(c['x10'].mean()):+6.2%} ({t10:+4.1f})  "
                     f"{np.expm1(c['x20'].mean()):+6.2%} ({t20:+4.1f}) |")
        out["detectors"][name] = rec
        print(line)
    # --- la partenza COLLETTIVA: l'ordine compare in tutto il sistema insieme ---
    # parametro d'ordine = quota di titoli con direzione in su; "transizione" = balzo in 10 barre
    spy = next((b for b in built if b["tk"] == "SPY"), None)
    if spy is not None:
        s10 = pd.Series(spy["f10"], index=spy["idx"]).reindex(days)
        s20 = pd.Series(spy["f20"], index=spy["idx"]).reindex(days)
        lo10 = breadth.rolling(10).min().shift(1)
        conds = {
            "balzo ≥ +20 punti in 10 barre": thrust >= 0.20,
            "balzo ≥ +30 punti in 10 barre": thrust >= 0.30,
            "da meno del 35% a più del 60% in 10 barre": (breadth >= 0.60) & (lo10 <= 0.35),
            "crollo ≤ −30 punti in 10 barre": thrust <= -0.30,
        }
        print("\n=== La partenza collettiva: quota di titoli con direzione in su (parametro d'ordine) → SPY dopo ===")
        print(f"quota media {breadth.mean():.0%} | SPY in un periodo qualsiasi: 10 gg {np.expm1(s10.mean()):+.2%}, 20 gg {np.expm1(s20.mean()):+.2%}")
        out["collective"] = {}
        for name, c in conds.items():
            c = c.reindex(days).fillna(False)
            line, rec = f"{name:44s} |", {}
            for k, m in (("2021-23", (days >= A0) & (days <= A1)), ("2024-26", days >= B0)):
                sel = c.values & m & np.isfinite(s20.values)
                d_sel = days[sel]
                if len(d_sel) < 5:
                    line += f" {k}: {len(d_sel):3d} giorni (pochi) |"
                    continue
                ep = int((np.diff(d_sel.values).astype("timedelta64[D]").astype(int) > 14).sum() + 1)
                base10, base20 = s10[m].mean(), s20[m].mean()
                starts = [d_sel[0]] + [d_sel[i] for i in range(1, len(d_sel)) if (d_sel[i] - d_sel[i - 1]).days > 14]
                e20 = np.array([s20[d] for d in starts])
                rec[k] = {"days": int(len(d_sel)), "episodes": ep, "x10": float(s10[sel].mean() - base10),
                          "x20": float(s20[sel].mean() - base20), "episodes_pos20": float((e20 > 0).mean()),
                          "episode_mean20": float(e20.mean())}
                line += (f" {k}: {len(d_sel):3d} giorni, {ep:2d} episodi | SPY 10 gg {np.expm1(s10[sel].mean()):+5.2%}, 20 gg {np.expm1(s20[sel].mean()):+5.2%} "
                         f"(normale {np.expm1(base20):+.2%}) | episodi positivi a 20 gg {(e20 > 0).mean():4.0%} |")
            out["collective"][name] = rec
            print(line)
    save_output("physics_start.json", out)


if __name__ == "__main__":
    main()
