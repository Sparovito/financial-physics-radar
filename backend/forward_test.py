"""
FORWARD TEST — paper trading "da oggi in poi".

A ogni scan giornaliero i segnali REALI vengono registrati in un journal
persistente; gli ingressi si riempiono alla prima barra successiva al
segnale (esecuzione t+1), le uscite scattano dopo `horizon` barre, il P&L
usa la stessa formula con costi del motore unificato. Quota fissa: ogni
trade pesa 1. Il journal è a senso unico (pending -> open -> closed).

"I segnali valgono qualcosa, o è solo il mercato che sale?"
In un mercato rialzista quasi ogni acquisto guadagna: il confronto con lo
zero non dice nulla. Per questo, insieme a ogni segnale, il journal
registra con la STESSA regola tre gruppi di confronto:

  control   un titolo a caso lo STESSO giorno del segnale
            -> misura quanto conta QUALE titolo
  baseline  un titolo a caso a ogni scan (giorno qualsiasi)
            -> misura quanto conta QUANDO si compra
  index     il benchmark (SPY) nei giorni in cui i segnali sono tanti
            -> "e se nei giorni di panico comprassi solo l'indice?"

Riferimento dal backtest 2021 → 11/2026 (research/scanner_persistence.py),
rendimento a 21 barre, costi inclusi:
  titolo qualsiasi, giorno qualsiasi   +1.2%
  titolo qualsiasi, giorni di segnale  +2.7%   (QUANDO: +1.5, t a cluster 1.6)
  titolo del segnale                   +3.4%   (QUALE:  +0.7, t a cluster 0.9)
  totale contro la base                +2.2    (t a cluster 1.7)

PROTOCOLLO (memory/FORWARD_TEST_PROTOCOL.md): regole fissate prima di avere
dati. Il verdetto è un SEMAFORO di coerenza col backtest, non una prova
statistica: per confermare un vantaggio di +2 punti servirebbero anni.
"""
import os
import json
import random
import hashlib
import datetime

from stable_strategy import _pnl_frac

JOURNAL_NAME = "forward_test_journal"
JOURNAL_PATH = os.path.join(os.path.dirname(__file__), f"{JOURNAL_NAME}.json")

PROTOCOL = {
    "min_closed": 30,
    "min_clusters": 12,           # settimane distinte con trade chiusi
    "promote_avg_pct": 1.0,
    "stop_avg_pct": 0.0,
    "extend_to": 60,
    "min_baseline_closed": 10,    # sotto questa soglia la base non entra nel verdetto
    "breadth_pct_index": 2.0,     # % dell'universo con segnale -> trade di confronto sull'indice
}

EXPECTED = {
    "signal": 3.4, "control": 2.7, "baseline": 1.2, "win_rate": 65,
    "source": "research/scanner_persistence.py, 2021 → 11/2026, 121 ticker",
}

BENCHMARK = "SPY"
GROUP_PREFIX = {"signal": "", "control": "CTRL:", "baseline": "BASE:", "index": "IDX:"}


def _new_journal():
    return {
        "created": datetime.date.today().strftime("%Y-%m-%d"),
        "config": {},
        "trades": [],
        "runs": [],
        "universe_snapshots": [],
        "protocol_violations": [],
    }


def load_journal(path=None):
    """Senza path usa lo storage persistente (Firestore + mirror locale)."""
    if path:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Journal illeggibile ({e}): ne creo uno nuovo")
        return _new_journal()
    from storage import get_storage
    return get_storage().load(JOURNAL_NAME, default=None) or _new_journal()


def save_journal(journal, path=None):
    if path:
        with open(path, "w") as f:
            json.dump(journal, f, indent=1)
        return
    from storage import get_storage
    get_storage().save(JOURNAL_NAME, journal)


def _group(tr):
    return tr.get("group", "signal")


def _trade_id(ticker, signal_date, group="signal"):
    return f"{GROUP_PREFIX[group]}{ticker}|{signal_date}"


def _universe_hash(tickers):
    return hashlib.sha1(",".join(sorted(tickers)).encode("utf-8")).hexdigest()[:12]


def _seeded(*parts):
    seed = int(hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12], 16)
    return random.Random(seed)


def _price_on_or_before(series, date):
    """Close dell'ultima barra con data <= date (festivi/calendari diversi)."""
    if not series:
        return None
    dates, closes = series
    last = None
    for d, c in zip(dates, closes):
        if d > date:
            break
        last = c
    return float(last) if last is not None else None


def _new_trade(group, ticker, signal_date, horizon, cost, stamp,
               strategy="", direction="LONG", price=None):
    return {
        "id": _trade_id(ticker, signal_date, group),
        "group": group,
        "ticker": ticker,
        "strategy": strategy,
        "direction": direction,
        "signal_date": signal_date,
        "signal_price": price,
        "status": "pending",
        "entry_date": None, "entry_price": None,
        "bars_held": 0,
        "exit_date": None, "exit_price": None,
        "pnl_pct": None,
        "current_price": None, "current_pnl_pct": None,
        "bench_entry": None, "bench_pnl_pct": None, "excess_pct": None,
        "horizon": int(horizon),
        "cost_pct": float(cost),
        "recorded_at": stamp,
        "closed_at_run": None,
    }


def update_journal(journal, price_series, new_signals, horizon,
                   cost_pct=0.05, today=None,
                   params=None, universe=None, run_date=None,
                   benchmark=BENCHMARK, max_controls_per_day=20):
    """
    price_series: {ticker: (dates: list[str], closes: list[float])} —
                  solo barre COMPLETE (lo scanner scarta già la parziale).
    new_signals:  [{ticker, signal_date, direction, strategy, ...}]
    params:       parametri della strategia, congelati al primo update.
    universe:     ticker scansionati oggi. Serve al registro dell'universo
                  e all'estrazione dei gruppi di confronto (senza universo
                  vengono registrati solo i segnali).
    """
    journal.setdefault("config", {})
    journal.setdefault("runs", [])
    journal.setdefault("universe_snapshots", [])
    journal.setdefault("protocol_violations", [])
    stamp = run_date or today or datetime.date.today().strftime("%Y-%m-%d")
    c = float(cost_pct)

    # 0. parametri congelati
    if params is not None:
        frozen = journal["config"].get("params")
        if frozen is None:
            journal["config"]["params"] = dict(params)
        elif frozen != params and journal["trades"]:
            if not any(v.get("to") == params for v in journal["protocol_violations"]):
                journal["protocol_violations"].append(
                    {"date": stamp, "from": dict(frozen), "to": dict(params)})
        elif frozen != params:
            journal["config"]["params"] = dict(params)

    existing = {t["id"] for t in journal["trades"]}

    def add(group, ticker, signal_date, **kw):
        tid = _trade_id(ticker, signal_date, group)
        if tid in existing:
            return False
        journal["trades"].append(_new_trade(group, ticker, signal_date, horizon, c, stamp, **kw))
        existing.add(tid)
        return True

    # 1. nuovi segnali -> pending (mai duplicati)
    new_by_date = {}
    for sig in new_signals:
        if add("signal", sig["ticker"], sig["signal_date"],
               strategy=sig.get("strategy", ""), direction=sig.get("direction", "LONG"),
               price=sig.get("price")):
            new_by_date.setdefault(sig["signal_date"], []).append(sig["ticker"])
    n_new = sum(len(v) for v in new_by_date.values())

    # 2. gruppi di confronto (estrazione deterministica: seme = data)
    if universe is not None:
        tickers = sorted(universe)
        busy = {t["ticker"] for t in journal["trades"] if t["status"] != "closed"}

        # 2a. control: per ogni segnale, un titolo a caso lo stesso giorno
        for d in sorted(new_by_date):
            k = min(len(new_by_date[d]), max_controls_per_day)
            eligible = [t for t in tickers
                        if t not in busy and t != benchmark
                        and price_series.get(t) and d in price_series[t][0]]
            for t in _seeded("control", d).sample(eligible, min(k, len(eligible))):
                if add("control", t, d, strategy="CONTROLLO"):
                    busy.add(t)

        # 2b. baseline: un titolo a caso per ogni giorno di scan
        if not any(_group(t) == "baseline" and t["recorded_at"] == stamp for t in journal["trades"]):
            eligible = [t for t in tickers
                        if t not in busy and t != benchmark and price_series.get(t)
                        and price_series[t][0]]
            if eligible:
                t = _seeded("baseline", stamp).choice(eligible)
                if add("baseline", t, price_series[t][0][-1], strategy="BASE"):
                    busy.add(t)

        # 2c. index: giorni con molti segnali -> stesso trade sul benchmark
        index_open = any(_group(t) == "index" and t["status"] != "closed" for t in journal["trades"])
        for d in sorted(new_by_date):
            breadth = len(new_by_date[d]) / max(1, len(tickers)) * 100
            if (breadth >= PROTOCOL["breadth_pct_index"] and not index_open
                    and price_series.get(benchmark)):
                if add("index", benchmark, d, strategy="INDICE"):
                    index_open = True

    # 3. avanzamento pending/open con i prezzi disponibili
    bench_series = price_series.get(benchmark)
    for tr in journal["trades"]:
        if tr["status"] == "closed":
            continue
        series = price_series.get(tr["ticker"])
        if not series:
            continue
        dates, closes = series
        hor = int(tr.get("horizon", horizon))
        tc = float(tr.get("cost_pct", c))

        if tr["status"] == "pending":
            entry_idx = next((i for i, d in enumerate(dates) if d > tr["signal_date"]), None)
            if entry_idx is None:
                continue
            tr["status"] = "open"
            tr["entry_date"] = dates[entry_idx]
            tr["entry_price"] = float(closes[entry_idx])
            tr["bench_entry"] = _price_on_or_before(bench_series, tr["entry_date"])

        if tr["status"] == "open":
            try:
                entry_idx = dates.index(tr["entry_date"])
            except ValueError:
                continue  # la storia scaricata non copre l'entry: riprova domani
            last_idx = len(dates) - 1
            exit_idx = entry_idx + hor
            if last_idx >= exit_idx:
                tr["status"] = "closed"
                tr["exit_date"] = dates[exit_idx]
                tr["exit_price"] = float(closes[exit_idx])
                tr["pnl_pct"] = round(_pnl_frac(tr["direction"], tr["entry_price"],
                                                tr["exit_price"], tc / 100.0) * 100, 2)
                tr["bars_held"] = hor
                tr["current_price"] = tr["exit_price"]
                tr["current_pnl_pct"] = tr["pnl_pct"]
                tr["closed_at_run"] = stamp
                bench_exit = _price_on_or_before(bench_series, tr["exit_date"])
                if tr.get("bench_entry") and bench_exit:
                    tr["bench_pnl_pct"] = round((bench_exit / tr["bench_entry"] - 1) * 100, 2)
                    tr["excess_pct"] = round(tr["pnl_pct"] - tr["bench_pnl_pct"], 2)
            else:
                tr["bars_held"] = last_idx - entry_idx
                tr["current_price"] = float(closes[last_idx])
                tr["current_pnl_pct"] = round(_pnl_frac(tr["direction"], tr["entry_price"],
                                                        tr["current_price"], tc / 100.0) * 100, 2)

    # 4. registro dello scan e dell'universo
    if universe is not None:
        tickers = sorted(universe)
        h = _universe_hash(tickers)
        snaps = journal["universe_snapshots"]
        if not snaps or snaps[-1]["hash"] != h:
            snaps.append({"date": stamp, "hash": h, "n": len(tickers), "tickers": tickers})
        run = {"date": stamp, "n_scanned": len(tickers), "universe_hash": h, "n_new_signals": n_new}
        runs = journal["runs"]
        if runs and runs[-1]["date"] == stamp:
            run["n_new_signals"] += runs[-1].get("n_new_signals", 0)
            runs[-1] = run
        else:
            runs.append(run)
    return journal


def _week_key(date_str):
    y, w, _ = datetime.date.fromisoformat(date_str).isocalendar()
    return f"{y}-W{w:02d}"


def _tstat(values):
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    if var <= 0:
        return None
    return round(mean / ((var / n) ** 0.5), 2)


def _avg(values):
    return round(sum(values) / len(values), 2) if values else None


def _verdict(n_closed, n_clusters, avg, edge_base, n_base):
    p = PROTOCOL
    if n_closed < p["min_closed"] or n_clusters < p["min_clusters"]:
        return "IN_CORSO", (f"servono {p['min_closed']} trade chiusi in {p['min_clusters']} settimane distinte "
                            f"(ora {n_closed} in {n_clusters})")
    if avg <= p["stop_avg_pct"]:
        return "STOP", "media per trade non positiva"
    ok_avg = avg >= p["promote_avg_pct"]
    base_counts = n_base >= p["min_baseline_closed"] and edge_base is not None
    ok_edge = (not base_counts) or edge_base > 0
    if ok_avg and ok_edge:
        return "COERENTE", "risultati in linea col backtest, nessun segnale d'allarme"
    reason = ("i segnali non battono la base giornaliera: il guadagno è il mercato che sale"
              if ok_avg else f"media sotto la soglia di +{p['promote_avg_pct']}%")
    return ("ESTENDI" if n_closed < p["extend_to"] else "NON_CONFERMATO"), reason


def journal_stats(journal):
    trades = journal.get("trades", [])

    def closed_pnls(group):
        return [t["pnl_pct"] for t in trades
                if _group(t) == group and t["status"] == "closed" and t.get("pnl_pct") is not None]

    sig = [t for t in trades if _group(t) == "signal"]
    closed = [t for t in sig if t["status"] == "closed" and t.get("pnl_pct") is not None]
    open_t = [t for t in sig if t["status"] == "open"]
    pending = [t for t in sig if t["status"] == "pending"]
    pnls = [t["pnl_pct"] for t in closed]
    wins = sum(1 for p in pnls if p > 0)
    open_pnls = [t["current_pnl_pct"] for t in open_t if t["current_pnl_pct"] is not None]
    avg = round(sum(pnls) / len(pnls), 2) if pnls else 0.0

    # cluster = settimana di ingresso: i trade dello stesso panico non sono
    # osservazioni indipendenti
    clusters = {}
    for t in closed:
        clusters.setdefault(_week_key(t["entry_date"]), []).append(t["pnl_pct"])
    cluster_means = [sum(v) / len(v) for v in clusters.values()]

    ctl, base, idx = closed_pnls("control"), closed_pnls("baseline"), closed_pnls("index")
    avg_ctl, avg_base = _avg(ctl), _avg(base)
    edge_ctl = round(avg - avg_ctl, 2) if (pnls and ctl) else None
    edge_base = round(avg - avg_base, 2) if (pnls and base) else None
    timing = round(avg_ctl - avg_base, 2) if (ctl and base) else None
    t_edge_base = _tstat([m - avg_base for m in cluster_means]) if base else None
    excess = [t["excess_pct"] for t in closed if t.get("excess_pct") is not None]

    verdict, reason = _verdict(len(closed), len(clusters), avg, edge_base, len(base))

    return {
        "created": journal.get("created"),
        "total": len(sig),
        "pending": len(pending),
        "open": len(open_t),
        "closed": len(closed),
        "sum_pnl_pct": round(sum(pnls), 2) if pnls else 0.0,
        "avg_pnl_pct": avg,
        "win_rate": round(wins / len(pnls) * 100, 1) if pnls else 0.0,
        "open_avg_pnl_pct": round(sum(open_pnls) / len(open_pnls), 2) if open_pnls else 0.0,
        "n_clusters": len(clusters),
        "t_naive": _tstat(pnls),
        "t_clustered": _tstat(cluster_means),
        # confronti
        "avg_excess_pct": _avg(excess),
        "control_closed": len(ctl), "control_avg_pnl_pct": avg_ctl,
        "baseline_closed": len(base), "baseline_avg_pnl_pct": avg_base,
        "index_closed": len(idx), "index_avg_pnl_pct": _avg(idx),
        "edge_vs_control": edge_ctl,          # quanto conta QUALE titolo
        "timing_edge": timing,                # quanto conta QUANDO
        "edge_vs_baseline": edge_base,        # totale
        "t_edge_baseline_clustered": t_edge_base,
        "expected": dict(EXPECTED),
        # protocollo
        "verdict": verdict,
        "verdict_reason": reason,
        "protocol": dict(PROTOCOL),
        "protocol_violations": len(journal.get("protocol_violations", [])),
        "frozen_params": journal.get("config", {}).get("params"),
        "n_runs": len(journal.get("runs", [])),
        "last_run": (journal.get("runs") or [{}])[-1].get("date"),
    }


def _expected_exit(entry_date, horizon):
    """Data indicativa di uscita: `horizon` giorni lavorativi dopo l'ingresso."""
    d = datetime.date.fromisoformat(entry_date)
    left = int(horizon)
    while left > 0:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d.strftime("%Y-%m-%d")


def journal_detail(journal, due_within=2):
    """Liste operative per l'email (solo i SEGNALI, non i gruppi di confronto):
    posizioni aperte, in scadenza entro `due_within` barre, chiuse all'ultimo scan."""
    sig = [t for t in journal.get("trades", []) if _group(t) == "signal"]
    runs = journal.get("runs") or []
    last_run = runs[-1]["date"] if runs else max(
        (t["closed_at_run"] for t in sig if t.get("closed_at_run")), default=None)

    open_list = []
    for t in sig:
        if t["status"] != "open":
            continue
        row = dict(t)
        row["bars_left"] = int(t["horizon"]) - int(t.get("bars_held", 0))
        # stima dalla data dell'ultimo scan + barre rimaste: contare dall'ingresso
        # sfasa la data ogni volta che in mezzo c'è un festivo
        base = last_run or t["entry_date"]
        row["expected_exit"] = _expected_exit(base, row["bars_left"]) if last_run else _expected_exit(t["entry_date"], t["horizon"])
        open_list.append(row)
    open_list.sort(key=lambda r: r["bars_left"])

    return {
        "last_run": last_run,
        "pending": [dict(t) for t in sig if t["status"] == "pending"],
        "open": open_list,
        "due_soon": [r for r in open_list if r["bars_left"] <= due_within],
        "closed_last_run": [dict(t) for t in sig
                            if t["status"] == "closed" and last_run and t.get("closed_at_run") == last_run],
    }
