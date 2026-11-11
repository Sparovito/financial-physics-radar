"""
Calcolo dello SCANNER STRATEGIE (Massivo).

Per ogni titolo: buy & hold del periodo e, per ogni strategia, ROI, win rate,
numero di trade, esposizione, e due confronti col "stare investiti per la
stessa frazione di tempo in momenti qualsiasi":

  alpha  = ROI − esposizione × B&H. È la colonna storica: confronta un
           rendimento composto con una quota LINEARE del compra-e-tieni, quindi
           su titoli saliti molto penalizza anche chi sceglie i tempi a caso.
  timing = eccesso calcolato sui rendimenti logaritmici giornalieri (vedi
           timing_excess): vale zero in media per tempi scelti a caso,
           qualunque sia la salita del titolo. È la misura da guardare.

`weekly` (somma settimanale dell'eccesso, per strategia) serve a calcolare la
significatività sul portafoglio di tutti i titoli: i titoli si muovono
insieme, quindi il t va fatto sulle settimane, non sui titoli.

Stesse formule di /analyze (LIVE, FROZEN, SUM, STABLE) più ARANCIONE, COMBO e
FROZEN V2 (potenziale sopra la media + prezzo sotto il percorso filtrato),
ma senza Fourier, ZigZag orario e serie per i grafici: allo scanner non servono.
Senza costi di transazione, come le strategie della dashboard.

Nota di lettura: è una descrizione del passato. Il rendimento passato di una
strategia su un titolo non prevede quello futuro (research/scanner_persistence.py).
"""
import datetime
import threading
import concurrent.futures

import math

import numpy as np
import pandas as pd

from logic import (ActionPath, backtest_strategy, kalman_frozen_series, causal_lowpass)
from stable_strategy import (backtest_stable, backtest_potential_discharge, backtest_combo,
                             backtest_frozen_v2, backtest_frozen_v2_rise, frozen_v2_states,
                             signed_energy, backtest_direction, ORANGE_LAG_BARS,
                             POTENTIAL_ALPHA, POTENTIAL_BETA)

WARMUP_DAYS = 560          # giorni di calendario scaricati prima dell'inizio periodo
MIN_BARS = 160
ZWIN = 252


def _zroll(values, min_periods=20):
    s = pd.Series(values, dtype=float)
    return ((s - s.rolling(ZWIN, min_periods=min_periods).mean())
            / (s.rolling(ZWIN, min_periods=min_periods).std() + 1e-6)).fillna(0)


def _exposure(trades, dates, lo, hi):
    """% di barre del periodo [lo, hi] con una posizione aperta."""
    idx = {d: i for i, d in enumerate(dates)}
    covered = set()
    for t in trades:
        a = idx.get(t["entry_date"])
        b = hi if t["exit_date"] == "OPEN" else idx.get(t["exit_date"])
        if a is None or b is None:
            continue
        covered.update(range(max(a, lo), min(b, hi) + 1))
    n = hi - lo + 1
    return round(len(covered) / n * 100, 1) if n > 0 else 0.0


def position_series(trades, dates, lo, hi):
    """Posizione tenuta in ogni barra (+1 long, −1 short, 0 fuori).
    Un trade eseguito alla chiusura della barra a incassa i rendimenti dalla
    barra a+1 fino a quella di uscita compresa."""
    idx = {d: i for i, d in enumerate(dates)}
    pos = np.zeros(len(dates))
    for t in trades:
        a = idx.get(t["entry_date"])
        b = hi if t["exit_date"] == "OPEN" else idx.get(t["exit_date"])
        if a is None or b is None:
            continue
        pos[a + 1:min(b, hi) + 1] = -1.0 if t.get("direction") == "SHORT" else 1.0
    return pos


def _week_start(date_str):
    d = datetime.date.fromisoformat(date_str)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def timing_excess(prices, pos, dates, lo, hi):
    """
    Quanto ha reso la strategia in più rispetto a tenere le STESSE quote di
    tempo long e short in momenti qualsiasi del periodo [lo, hi].

    Per ogni barra, in rendimenti logaritmici:
        eccesso = rendimento della strategia
                  − f_long · log(1+r) − f_short · log(1−r)
    con f_long, f_short = frazioni di barre long e short. La somma è il log
    del rapporto tra il capitale della strategia e quello atteso con tempi a
    caso: zero in media se i tempi non contengono informazione.

    Returns: (timing in %, {lunedì della settimana: somma dell'eccesso})
    """
    p = np.asarray(prices, dtype=float)
    r = p[lo + 1:hi + 1] / p[lo:hi] - 1.0
    q = np.asarray(pos, dtype=float)[lo + 1:hi + 1]
    if len(r) == 0:
        return 0.0, {}
    lg_long = np.log1p(np.clip(r, -0.999, None))
    lg_short = np.log1p(np.clip(-r, -0.999, None))
    f_long, f_short = float((q > 0).mean()), float((q < 0).mean())
    strat = np.where(q > 0, lg_long, np.where(q < 0, lg_short, 0.0))
    x = strat - f_long * lg_long - f_short * lg_short
    weekly = {}
    for d, v in zip(dates[lo + 1:hi + 1], x):
        k = _week_start(d)
        weekly[k] = weekly.get(k, 0.0) + float(v)
    return float(math.expm1(x.sum()) * 100), weekly


def aggregate_weekly(results):
    """Toglie `weekly` dai risultati per titolo e ritorna, per strategia,
    {settimana: [somma dell'eccesso tra i titoli, numero di titoli]}.
    Il client somma i batch e divide: è il rendimento in eccesso settimanale
    del portafoglio a pesi uguali, su cui si calcola un t onesto."""
    agg = {}
    for r in results.values():
        for name, weeks in (r.pop("weekly", None) or {}).items():
            a = agg.setdefault(name, {})
            for k, v in weeks.items():
                cell = a.setdefault(k, [0.0, 0])
                cell[0] += v
                cell[1] += 1
    return {name: {k: [round(v[0], 6), v[1]] for k, v in weeks.items()} for name, weeks in agg.items()}


def _slim(trades):
    return [{"entry_date": t["entry_date"], "exit_date": t["exit_date"],
             "direction": t.get("direction", "LONG"),
             "entry_price": t.get("entry_price"), "exit_price": t.get("exit_price"),
             "pnl_pct": t.get("pnl_pct")} for t in trades]


def scan_one(px, start_date, end_date=None, alpha=200.0, beta=1.0, entry_z=2.0, horizon=21):
    """px: serie di chiusure CON la storia di warmup prima di start_date."""
    if end_date:
        px = px[px.index <= pd.Timestamp(end_date)]
    if len(px) < MIN_BARS:
        raise ValueError(f"storia insufficiente ({len(px)} barre, ne servono {MIN_BARS})")

    dates = px.index.strftime("%Y-%m-%d").tolist()
    prices = [float(v) for v in px.values]
    lo = next((i for i, d in enumerate(dates) if d >= start_date), None)
    hi = len(dates) - 1
    if lo is None or hi - lo < 20:
        raise ValueError("storia insufficiente nel periodo richiesto")

    bh = (prices[hi] / prices[lo] - 1) * 100
    trend = "up" if bh > 15 else ("down" if bh < -15 else "stable")
    kw = {"start_date": start_date, "end_date": end_date}
    out, trades_out, weekly_out = {}, {}, {}

    def put(name, res, expo=None):
        st = res["stats"]
        trades = res["trades"]
        closed = [t for t in trades if t["exit_date"] != "OPEN"]
        wins = sum(1 for t in closed if (t.get("pnl_pct") or 0) > 0)
        e = expo if expo is not None else _exposure(trades, dates, lo, hi)
        roi = float(st["total_return"])
        out[name] = {
            "roi": round(roi, 2),
            "win_rate": round(wins / len(closed) * 100, 1) if closed else 0.0,   # solo trade chiusi
            "trades": len(closed),
            "expo": e,
            "alpha": round(roi - e / 100 * bh, 2),
        }
        timing, weekly = timing_excess(prices, position_series(trades, dates, lo, hi), dates, lo, hi)
        out[name]["timing"] = round(timing, 2)
        weekly_out[name] = weekly
        trades_out[name] = _slim(trades)

    # --- LIVE: smoother bidirezionale = ORACOLO (conosce il futuro del periodo) ---
    mech = ActionPath(px, alpha=alpha, beta=beta)
    z_kin = _zroll(mech.kin_density.values).tolist()
    z_slope = _zroll(mech.dX.values).tolist()
    put("live", backtest_strategy(prices=prices, z_kinetic=z_kin, z_slope=z_slope, dates=dates, **kw))

    # --- FROZEN / SUM: serie point-in-time (Kalman), come /analyze ---
    fr = kalman_frozen_series(px, alpha=alpha, beta=beta, min_points=100, kin_lag=25)
    pad = len(prices) - len(fr["pot_last"])
    z_pot = _zroll([0] * pad + [round(v, 2) for v in fr["pot_last"]]).tolist()
    put("frozen", backtest_strategy(prices=prices, z_kinetic=z_pot, z_slope=z_slope, dates=dates,
                                    use_z_roc=True, **kw))
    z_sum_raw = _zroll([k + p for k, p in zip(fr["kin_last"], fr["pot_last"])]).tolist()
    z_sum = [-999] * pad + [round(x, 2) for x in causal_lowpass(z_sum_raw)]
    put("sum", backtest_strategy(prices=prices, z_kinetic=z_sum, z_slope=z_slope, dates=dates,
                                 threshold=-0.3, use_z_roc=True, **kw))

    # --- STABLE: slope causale, motore unificato (LONG, soglie 0/0, t+1) ---
    span = max(5, int(alpha / 10))
    slope = px.ewm(span=span, adjust=False).mean().diff().fillna(0).ewm(span=14, adjust=False).mean().values.tolist()
    res = backtest_stable(dates, prices, slope, mode="LONG", execution_lag=1, cost_pct=0.0, **kw)
    put("stable", res, expo=res["stats"]["exposure_pct"])

    # --- ARANCIONE / COMBO: potenziale con i parametri validati ---
    if alpha == POTENTIAL_ALPHA and beta == POTENTIAL_BETA:
        fo = fr
    else:
        fo = kalman_frozen_series(px, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA, min_points=100, kin_lag=25)
    pot = ([float("nan")] * 100 + list(fo["pot_last"]))[:len(prices)]
    F20 = px.ewm(span=20, adjust=False).mean().values.tolist()
    res = backtest_potential_discharge(dates, prices, pot, F20, entry_z=entry_z, horizon=horizon,
                                       execution_lag=1, cost_pct=0.0, **kw)
    put("orange", res, expo=res["stats"]["exposure_pct"])
    res = backtest_combo(dates, prices, slope, pot, F20, entry_z=entry_z, horizon=horizon,
                         execution_lag=1, cost_pct=0.0, **kw)
    put("combo", res, expo=res["stats"]["exposure_pct"])

    # --- FROZEN V2: potenziale sopra la media E prezzo recente sotto il percorso filtrato ---
    xf = ([float("nan")] * 100 + list(fo["ma_price"]))[:len(prices)]
    disp = [f - x for f, x in zip(F20, xf)]
    res = backtest_frozen_v2(dates, prices, pot, disp, execution_lag=1, cost_pct=0.0, **kw)
    put("frozen2", res, expo=res["stats"]["exposure_pct"])

    # --- V2 RISALITA: entra con la V2, tiene la risalita, esce al massimo dell'arancione ---
    res = backtest_frozen_v2_rise(dates, prices, pot, disp, execution_lag=1, cost_pct=0.0, **kw)
    put("frozen2r", res, expo=res["stats"]["exposure_pct"])

    return {
        "bh": round(bh, 2), "trend": trend, "n_bars": hi - lo + 1,
        "first_date": dates[lo], "last_date": dates[hi], "last_price": round(prices[hi], 4),
        "strategies": out, "trades": trades_out, "weekly": weekly_out,
    }


def v2_inputs(px, frozen=None):
    """Le due serie causali su cui lavorano Frozen V2, V2 Risalita e gli stati
    dell'arancione, coi parametri validati del potenziale (non quelli scelti
    a schermo): potenziale ½β·d² e scostamento d = EMA20 − filtro di Kalman.
    Allineate ai prezzi; le prime 100 barre sono NaN (riscaldamento del filtro)."""
    fo = frozen if frozen is not None else kalman_frozen_series(
        px, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA, min_points=100, kin_lag=25)
    n = len(px)
    pot = ([float("nan")] * 100 + list(fo["pot_last"]))[:n]
    F20 = px.ewm(span=20, adjust=False).mean().values.tolist()
    xf = ([float("nan")] * 100 + list(fo["ma_price"]))[:n]
    disp = [f - x for f, x in zip(F20, xf)]
    return pot, disp


def orange_scale(alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA):
    """Fattore che porta l'arancione (½β·d²) nella scala del blu (½α·v²).
    Su un movimento a ritmo costante v il filtro resta indietro di
    d = v·(1−K)/K (K = guadagno di Kalman a regime), quindi
    blu / arancione = α·K² / (β·(1−K)²)  ≈ 1.07 per α=200, β=1."""
    q, r = 1.0 / alpha, 1.0 / beta
    p_pred = (q + math.sqrt(q * q + 4 * q * r)) / 2
    k = p_pred / (p_pred + r)
    return alpha * k * k / (beta * (1 - k) ** 2)


NOWCAST_HORIZON = 60     # barre di F prevista: oltre, il peso sul punto di oggi è trascurabile


def _steady_gain(alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA):
    """Guadagno di Kalman a regime del modello a livello locale."""
    q, r = 1.0 / alpha, 1.0 / beta
    p_pred = (q + math.sqrt(q * q + 4 * q * r)) / 2
    return p_pred / (p_pred + r)


def oracle_nowcast(px, frozen=None, horizon=NOWCAST_HORIZON, span=20):
    """
    STIMA DI OGGI della velocità dell'oracolo (nowcast), una per barra.

    Il blu è la velocità del percorso di minima azione calcolato su passato e
    futuro di F = EMA20. Il futuro di F non è tutto ignoto: una media insegue
    il prezzo, quindi (se le variazioni future del prezzo sono imprevedibili)

        F attesa tra k barre = prezzo_oggi − (1−a)^k · (prezzo_oggi − F_oggi)

    Si prolunga F con questa previsione per `horizon` barre, si prosegue il
    filtro di Kalman sulla serie prolungata e si torna indietro (ricorsione
    RTS) fino a ieri: la differenza tra oggi e ieri è la velocità stimata.

    Causale: usa solo dati fino alla barra stessa, non viene ridisegnata e
    non è spostata nel tempo. È il massimo ottenibile: nello stesso giorno
    somiglia al blu 0.87 (l'arancione 0.82) e nessuna combinazione lineare di
    21 grandezze passate fa meglio (research/nowcast.py). Riconosce una svolta
    in 5 barre invece di 10, ma cambia segno 15 volte l'anno invece di 6.7.

    Returns: list[float] in unità di prezzo per barra; NaN nel riscaldamento.
    """
    fo = frozen if frozen is not None else kalman_frozen_series(
        px, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA, min_points=100, kin_lag=25)
    n = len(px)
    p = px.values.astype(float)
    F = px.ewm(span=span, adjust=False).mean().values.astype(float)
    xf = np.array(([float("nan")] * 100 + list(fo["ma_price"]))[:n], dtype=float)
    a = 2.0 / (span + 1)
    K = _steady_gain()
    C = 1.0 - K
    gap = p - F
    X = np.empty((horizon + 1, n))
    X[0] = xf
    x = xf.copy()
    for k in range(1, horizon + 1):
        x = x + K * ((p - (1 - a) ** k * gap) - x)
        X[k] = x
    sm = X[horizon]
    for k in range(horizon - 1, -1, -1):
        sm = X[k] + C * (sm - X[k])
    prev = np.r_[float("nan"), xf[:-1]] if n else xf
    return (sm - (prev + C * (sm - prev))).tolist()


_NOWCAST_SCALE = {}


def nowcast_scale():
    """Su un movimento a ritmo costante la stima di oggi vede circa il 71% della
    velocità vera (la previsione assume che il prezzo si fermi): questo fattore
    porta la sua energia nella scala del blu."""
    if "v" not in _NOWCAST_SCALE:
        ramp = pd.Series([100 + 0.5 * i for i in range(500)],
                         index=pd.date_range("2020-01-01", periods=500, freq="B"))
        ratio = oracle_nowcast(ramp)[400] / 0.5
        _NOWCAST_SCALE["v"] = 1.0 / (ratio * ratio)
    return _NOWCAST_SCALE["v"]


def v2_chart_block(px, start_date=None, end_date=None):
    """Quello che serve al grafico di /analyze:
    - state: lo stato dell'arancione per barra (0-4, vedi frozen_v2_states);
    - v2, rise: i backtest di Frozen V2 e V2 Risalita sulle date del grafico;
    - dir: il backtest della regola Direzione (dentro finché la stima di oggi
      del blu è sopra lo zero), in tempo reale;
    - direction: le energie CON IL SEGNO (sopra lo zero = salita, sotto =
      discesa) nella scala del blu, per il pannello "Direzione":
        oracle   cinetica del percorso di minima azione × segno della sua
                 velocità: è l'ORACOLO, usa il futuro e viene ridisegnato
        nowcast  la stima di oggi del blu (oracle_nowcast): causale, non
                 spostata nel tempo, non ridisegnata
        orange   il potenziale causale × segno dello scostamento (la vecchia
                 curva: ripete il blu con `lag` = 9 barre di ritardo)
        velocity le stesse tre curve senza il quadrato (velocità del percorso,
                 unità di prezzo per barra): è la scala disegnata dal pannello
    Tutto tranne `oracle` è causale: troncando la storia il passato non
    cambia. Parametri del potenziale sempre quelli validati (α=200, β=1)."""
    dates = px.index.strftime("%Y-%m-%d").tolist()
    prices = [float(v) for v in px.values]
    fo = kalman_frozen_series(px, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA, min_points=100, kin_lag=25)
    pot, disp = v2_inputs(px, frozen=fo)
    kw = dict(execution_lag=1, cost_pct=0.0, start_date=start_date, end_date=end_date)
    scale = orange_scale()
    mech = ActionPath(px, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA)
    oracle = [float(f"{v:.6g}") for v in (np.sign(mech.dX.values) * mech.kin_density.values)]
    v_now = oracle_nowcast(px, frozen=fo)
    now_scale = nowcast_scale()
    nowcast = [None if v != v else float(f"{(1.0 if v > 0 else -1.0 if v < 0 else 0.0) * 0.5 * POTENTIAL_ALPHA * v * v * now_scale:.6g}")
               for v in v_now]
    # le stesse tre curve in scala di velocità (unità di prezzo per barra), senza il quadrato:
    # su un movimento a ritmo costante valgono tutte quanto la velocità vera
    k_gain = _steady_gain()
    v_ratio, d_ratio = math.sqrt(now_scale), k_gain / (1.0 - k_gain)
    velocity = {
        "oracle": [float(f"{v:.6g}") for v in mech.dX.values],
        "nowcast": [None if v != v else float(f"{v * v_ratio:.6g}") for v in v_now],
        "orange": [None if (d is None or d != d) else float(f"{d * d_ratio:.6g}") for d in disp],
    }
    return {
        "state": frozen_v2_states(pot, disp),
        "v2": backtest_frozen_v2(dates, prices, pot, disp, **kw),
        "rise": backtest_frozen_v2_rise(dates, prices, pot, disp, **kw),
        "dir": backtest_direction(dates, prices, v_now, **kw),
        "direction": {
            "oracle": oracle,
            "nowcast": nowcast,
            "orange": signed_energy(pot, disp, scale=scale),
            "lag": ORANGE_LAG_BARS,
            "scale": round(scale, 4),
            "nowcast_scale": round(now_scale, 4),
            "velocity": velocity,
        },
    }


# ---------- prezzi: cache limitata a un giorno ----------
_cache = {"key": None, "data": {}}
_cache_lock = threading.Lock()


def fetch_prices_cached(tickers, start, fetch_fn, day=None, max_workers=8):
    """Scarica (una volta al giorno per titolo e data di inizio) le serie.
    La cache viene buttata quando cambia il giorno o l'inizio: su un server
    sempre acceso non restano prezzi vecchi e la memoria non cresce."""
    day = day or datetime.date.today().strftime("%Y-%m-%d")
    key = (day, start)
    with _cache_lock:
        if _cache["key"] != key:
            _cache["key"], _cache["data"] = key, {}
        data = _cache["data"]
        missing = [t for t in tickers if t not in data]

    failed = {}

    def one(t):
        try:
            return t, fetch_fn(t, start), None
        except Exception as e:
            return t, None, str(e)

    if missing:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(missing)))) as ex:
            for t, px, err in ex.map(one, missing):
                if px is not None and len(px) > 0:
                    with _cache_lock:
                        data[t] = px
                else:
                    failed[t] = err or "nessun dato"
    return {t: data[t] for t in tickers if t in data}, failed
