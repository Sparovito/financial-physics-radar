"""
STATO DEL SISTEMA — il secondo principio della termodinamica applicato al mercato.

Da un sistema in equilibrio non si estrae lavoro; lo si estrae da uno
squilibrio che si rilassa, e solo dalla parte ORDINATA dell'energia.

Ogni titolo ha uno scostamento dal proprio percorso, in sigma:

    x_i = (EMA20 − filtro di Kalman di EMA20) / (prezzo · volatilità giornaliera)

L'energia totale dell'insieme, media(x_i²), si divide in
    parte ordinata   X² , con X = media(x_i): tutti spostati dalla stessa parte
    calore           varianza(x_i): ognuno per conto suo
Chi tiene un indice sente solo X; il calore si compensa (≈ 73% dell'energia).

Segnale "rientro iniziato" (research/second_law.py, storia 2004→2026):
    X è stato nel 5% più basso dei 5 anni precedenti nelle ultime 10 sedute
    E oggi è più alto di 5 sedute fa
cioè lo squilibrio collettivo c'è stato e ha smesso di crescere. La posizione
resta aperta fino a 21 sedute dopo l'ultimo giorno di segnale.

Misura su SPY (base 50% → 100%, senza leva) rispetto alla stessa esposizione
tenuta fissa: +0.7 / +1.5 / +2.5 %/anno nel 2005-12 / 2013-20 / 2021-26; 20
episodi, +3.3% a 21 sedute con l'80% positivi (un periodo qualsiasi +0.9%,
68%); caso peggiore −25.7% dopo l'ingresso (luglio 2008). La condizione "ha
smesso di crescere" è stata aggiunta dopo aver visto fallire il "primo
tocco" nel 2008: CANDIDATA, non validata fuori campione.

Tutto causale: i valori passati non cambiano quando arrivano dati nuovi.

La storia di X sta in due posti: un seme nel repository
(backend/data/system_history.csv, costruito da research/build_system_history.py)
e una coda giornaliera nello storage (documento "system_history").
"""
import os

import numpy as np
import pandas as pd

from stable_strategy import POTENTIAL_ALPHA, POTENTIAL_BETA, backtest_stable

WARMUP = 260            # barre di riscaldamento per titolo
MIN_TICKERS = 150       # giorni con meno titoli non contano (fine settimana delle crypto, festività)
PCT_WINDOW = 1260       # 5 anni di sedute
PCT_MIN = 500
TOUCH = 0.05            # "estremo": X nel 5% più basso della finestra
MEMORY = 10             # ...in una delle ultime 10 sedute
TURN = 5                # ...e oggi più alto di 5 sedute fa
HOLD = 21               # sedute di tenuta dopo l'ultimo giorno di segnale
CLIP = 15.0

SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "system_history.csv")
STORE_NAME = "system_history"


def _kalman(F, alpha=POTENTIAL_ALPHA, beta=POTENTIAL_BETA):
    q, r = 1.0 / alpha, 1.0 / beta
    x = np.empty(len(F))
    x[0], P = F[0], r
    for t in range(1, len(F)):
        Pp = P + q
        g = Pp / (Pp + r)
        x[t] = x[t - 1] + g * (F[t] - x[t - 1])
        P = (1 - g) * Pp
    return x


def ticker_displacement(px):
    """Scostamento del titolo dal suo percorso, in sigma giornaliere (negativo = prezzo
    recente sotto il percorso). NaN nelle prime WARMUP barre. Causale."""
    px = px[px > 0]
    p = px.values.astype(float)
    n = len(p)
    out = np.full(n, np.nan)
    if n > WARMUP:
        lr = np.zeros(n)
        lr[1:] = np.log(p[1:] / p[:-1])
        sig = pd.Series(lr).ewm(span=60, min_periods=20).std().values
        F = px.ewm(span=20, adjust=False).mean().values.astype(float)
        d = F - _kalman(F)
        with np.errstate(divide="ignore", invalid="ignore"):
            x = np.clip(d / (p * sig), -CLIP, CLIP)
        out[WARMUP:] = x[WARMUP:]
    return pd.Series(out, index=px.index)


def coherent_series(prices, min_tickers=MIN_TICKERS):
    """Spostamento coerente X = media degli scostamenti tra i titoli, per giorno.
    prices: {ticker: Series di chiusure}. Ritorna DataFrame [X, n] con i soli
    giorni in cui almeno `min_tickers` titoli hanno un valore."""
    cols = {}
    for tk, px in prices.items():
        try:
            s = ticker_displacement(px)
        except Exception:
            continue
        s = s[~s.index.duplicated(keep="last")].dropna()
        if len(s):
            cols[tk] = s
    if not cols:
        return pd.DataFrame({"X": [], "n": []})
    wide = pd.DataFrame(cols)
    n = wide.notna().sum(axis=1)
    out = pd.DataFrame({"X": wide.mean(axis=1), "n": n})
    return out[out["n"] >= min_tickers]


def causal_percentile(values, window=PCT_WINDOW, min_periods=PCT_MIN):
    """Quota di valori della finestra (che termina oggi) minori o uguali a quello di oggi."""
    s = pd.Series(np.asarray(values, dtype=float))
    return s.rolling(window, min_periods=min_periods).apply(lambda a: (a <= a[-1]).mean(), raw=True).values


def relaxation_signal(X, pct, touch=TOUCH, memory=MEMORY, turn=TURN):
    """Rientro iniziato: estremo nelle ultime `memory` sedute E X più alto di `turn` sedute fa."""
    X = np.asarray(X, dtype=float)
    pct = np.asarray(pct, dtype=float)
    low = np.nan_to_num((pct <= touch).astype(float))
    touched = pd.Series(low).rolling(memory, min_periods=1).max().values > 0
    prev = np.r_[np.full(turn, np.nan), X[:-turn]] if len(X) > turn else np.full(len(X), np.nan)
    with np.errstate(invalid="ignore"):
        return touched & (X > prev)


def hold_flags(signal, hold=HOLD):
    """Vero nel giorno del segnale e nelle `hold` sedute successive all'ultimo segnale."""
    s = pd.Series(np.asarray(signal, dtype=float))
    return s.rolling(hold + 1, min_periods=1).max().values > 0


def analyse(history, window=PCT_WINDOW, min_periods=PCT_MIN):
    """history: DataFrame [X, n] per giorno. Aggiunge pct, signal, hold, touched."""
    an = history[["X", "n"]].copy()
    an["pct"] = causal_percentile(an["X"].values, window, min_periods)
    an["signal"] = relaxation_signal(an["X"].values, an["pct"].values)
    an["hold"] = hold_flags(an["signal"].values)
    low = np.nan_to_num((an["pct"].values <= TOUCH).astype(float))
    an["touched"] = pd.Series(low, index=an.index).rolling(MEMORY, min_periods=1).max().values > 0
    return an


def current_state(an):
    """Stato del sistema nell'ultimo giorno dell'analisi:
    equilibrio | squilibrio in aumento | rientro iniziato | in tenuta."""
    if an is None or len(an) == 0:
        return {"state": "non disponibile"}
    last = an.iloc[-1]
    sig_days = np.nonzero(an["signal"].values)[0]
    since = (len(an) - 1 - int(sig_days[-1])) if len(sig_days) else None
    if bool(last["signal"]):
        state = "rientro iniziato"
    elif bool(last["hold"]):
        state = "in tenuta"
    elif bool(last["touched"]):
        state = "squilibrio in aumento"
    else:
        state = "equilibrio"
    pct = None if last["pct"] != last["pct"] else round(float(last["pct"]) * 100, 1)
    return {
        "state": state,
        "date": str(an.index[-1].date()),
        "X": round(float(last["X"]), 3),
        "percentile": pct,
        "tickers": int(last["n"]),
        "last_signal": str(an.index[int(sig_days[-1])].date()) if len(sig_days) else None,
        "sessions_left": (HOLD - since) if (since is not None and bool(last["hold"])) else 0,
    }


def hold_positions(dates, an):
    """Posizione desiderata (0/1) per ogni data di un titolo: 1 se quel giorno il sistema è in
    tenuta. Per le date che la storia del sistema non ha vale l'ultimo stato noto."""
    if an is None or len(an) == 0:
        return [0] * len(dates)
    h = an["hold"].astype(float)
    want = pd.to_datetime(pd.Index(dates))
    full = h.reindex(h.index.union(want)).ffill().fillna(0.0)
    return [int(v) for v in full.reindex(want).values]


def backtest_system(dates, prices, an, execution_lag=1, cost_pct=0.0, initial_capital=1000.0,
                    start_date=None, end_date=None):
    """Sul titolo dato: dentro solo nei periodi di tenuta del sistema (esecuzione t+1)."""
    pseudo = [p - 0.5 for p in hold_positions(dates, an)]
    return backtest_stable(dates, prices, pseudo, mode="LONG", entry_th=0.4, exit_th=0.0,
                           execution_lag=execution_lag, cost_pct=cost_pct, initial_capital=initial_capital,
                           start_date=start_date, end_date=end_date)


# ---------- storia: seme nel repository + coda nello storage ----------

def write_history_csv(history, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = history[["X", "n"]].copy()
    out.index = [d.strftime("%Y-%m-%d") for d in out.index]
    out["X"] = out["X"].round(5)
    out["n"] = out["n"].astype(int)
    out.to_csv(path, index_label="date")


def read_history_csv(path):
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    return df[["X", "n"]].sort_index()


def rows_after(computed, last_date):
    """Righe calcolate con data successiva a `last_date`."""
    return computed[computed.index > pd.Timestamp(last_date)][["X", "n"]]


def merge_history(base, tail):
    """Unisce seme e coda; a parità di data vince la coda."""
    if tail is None or len(tail) == 0:
        return base
    out = pd.concat([base[["X", "n"]], tail[["X", "n"]]])
    return out[~out.index.duplicated(keep="last")].sort_index()


def _tail_from_store(storage):
    data = storage.load(STORE_NAME, default=None) if storage is not None else None
    rows = (data or {}).get("rows") or []
    if not rows:
        return None
    return pd.DataFrame({"X": [float(r[1]) for r in rows], "n": [int(r[2]) for r in rows]},
                        index=pd.to_datetime([r[0] for r in rows]))


def load_history(storage=None):
    seed = read_history_csv(SEED_PATH)
    return merge_history(seed, _tail_from_store(storage))


_ANALYSIS_CACHE = {"key": None, "an": None}


def cached_analysis(storage=None):
    """Analisi della storia corrente (seme + coda), ricalcolata solo quando la storia cambia."""
    hist = load_history(storage)
    key = (len(hist), str(hist.index[-1]), round(float(hist["X"].iloc[-1]), 5))
    if _ANALYSIS_CACHE["key"] != key:
        _ANALYSIS_CACHE["key"], _ANALYSIS_CACHE["an"] = key, analyse(hist)
    return _ANALYSIS_CACHE["an"]


def refresh(fetch_prices, tickers, storage, today=None, complete_only=True):
    """Aggiorna la coda con i giorni mancanti. fetch_prices(tickers, start) → {ticker: Series}.
    Ricalcola anche gli ultimi 10 giorni già presenti (se una barra era stata salvata quando
    non era ancora definitiva viene corretta). Con complete_only la barra di `today` non
    viene salvata: di giorno potrebbe essere parziale."""
    hist = load_history(storage)
    last = hist.index[-1]
    today = pd.Timestamp(today or pd.Timestamp.now().normalize())
    start = (last - pd.Timedelta(days=700)).strftime("%Y-%m-%d")
    prices = fetch_prices(tickers, start)
    computed = coherent_series(prices)
    new = computed[computed.index > last - pd.Timedelta(days=10)][["X", "n"]]
    if complete_only:
        new = new[new.index < today]
    added = int((new.index > last).sum())
    if len(new):
        old_tail = _tail_from_store(storage)
        tail = merge_history(old_tail if old_tail is not None else new.iloc[:0], new)
        rows = [[d.strftime("%Y-%m-%d"), round(float(r["X"]), 5), int(r["n"])] for d, r in tail.iterrows()]
        storage.save(STORE_NAME, {"rows": rows})
    return {"added": added, "last_date": str((new.index[-1] if len(new) else last).date()),
            "tickers_downloaded": len(prices)}
