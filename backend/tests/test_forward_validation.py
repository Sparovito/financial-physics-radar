"""
Test per la VALIDAZIONE dal vivo del forward test (forward_test.py).

"I segnali sono positivi, o è solo il mercato che sale?" Il journal risponde
con due confronti costruiti nello stesso momento dei segnali:
  1. BENCHMARK: per ogni trade, il rendimento di SPY sulle stesse date
     (excess = trade - SPY).
  2. CONTROLLO STESSO GIORNO: per ogni segnale, un titolo estratto a caso lo
     stesso giorno, stessa regola (ingresso t+1, uscita a orizzonte). Misura
     quanto conta QUALE titolo (dal backtest: poco, +0.7 punti non significativi).
  3. BASE GIORNALIERA: a ogni scan, un titolo a caso in un giorno qualsiasi.
     Misura quanto conta QUANDO si compra. Se i segnali non battono la base,
     il "guadagno" è solo il mercato che sale.
Il verdetto COERENTE richiede anche che i segnali battano la base giornaliera.

Esecuzione: backend/venv/bin/python backend/tests/test_forward_validation.py
"""
import os
import sys

os.environ.setdefault("FPR_STORAGE", "local")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd


def _dates(n, start="2026-11-02"):
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, periods=n, freq="B")]


def _closed(group, ticker, entry_date, pnl, excess=None):
    prefix = {"control": "CTRL:", "baseline": "BASE:"}.get(group, "")
    return {"id": f"{prefix}{ticker}|{entry_date}", "group": group,
            "ticker": ticker, "strategy": "ARANCIONE", "direction": "LONG",
            "signal_date": entry_date, "status": "closed", "entry_date": entry_date,
            "entry_price": 100.0, "bars_held": 21, "exit_date": entry_date,
            "exit_price": 100.0 + pnl, "pnl_pct": pnl, "current_price": 100.0 + pnl,
            "current_pnl_pct": pnl, "horizon": 21, "cost_pct": 0.05,
            "bench_pnl_pct": (pnl - excess) if excess is not None else None, "excess_pct": excess}


def main():
    from forward_test import update_journal, journal_stats, journal_detail, PROTOCOL

    H = 3
    d = _dates(8)
    flat = [100.0] * 8
    series_full = {
        "TKR": (d, [100, 102, 104, 106, 108, 110, 112, 114]),
        "AAA": (d, flat), "BBB": (d, flat), "CCC": (d, flat), "DDD": (d, flat),
        # SPY sale dell'1% al giorno e NON ha la barra d[4] (festivo): va usata l'ultima data <= d[4]
        "SPY": ([x for i, x in enumerate(d) if i != 4],
                [100 * 1.01 ** i for i in range(8) if i != 4]),
    }
    universe = sorted(series_full)

    def upto(k):
        return {t: ([x for x in ds if x <= d[k]], [c for x, c in zip(ds, cs) if x <= d[k]])
                for t, (ds, cs) in series_full.items()}

    sig = [{"ticker": "TKR", "signal_date": d[0], "direction": "LONG", "strategy": "ARANCIONE", "price": 100}]
    params = {"strategy": "ARANCIONE", "entry_z": 2.0, "horizon": H}

    # --- 1. un segnale -> un controllo, stesso giorno, altro titolo ---
    j = {"created": d[0], "config": {}, "trades": []}
    update_journal(j, upto(0), sig, horizon=H, params=params, universe=universe, run_date=d[0])
    signals = [t for t in j["trades"] if t["group"] == "signal"]
    controls = [t for t in j["trades"] if t["group"] == "control"]
    assert len(signals) == 1 and len(controls) == 1, (len(signals), len(controls))
    c = controls[0]
    assert c["signal_date"] == d[0] and c["ticker"] != "TKR"
    assert c["id"].startswith("CTRL:")
    # ... e un titolo di BASE per lo scan di oggi (giorno qualsiasi)
    base = [t for t in j["trades"] if t["group"] == "baseline"]
    assert len(base) == 1 and base[0]["id"].startswith("BASE:"), base
    assert base[0]["ticker"] not in ("TKR", c["ticker"])

    # estrazione deterministica: stesso giorno, stesso universo -> stesso controllo
    j2 = {"created": d[0], "config": {}, "trades": []}
    update_journal(j2, upto(0), sig, horizon=H, params=params, universe=universe, run_date=d[0])
    assert [t["ticker"] for t in j2["trades"] if t["group"] == "control"] == [c["ticker"]]

    # rieseguire lo stesso giorno non aggiunge altri controlli
    update_journal(j, upto(0), sig, horizon=H, params=params, universe=universe, run_date=d[0])
    assert len([t for t in j["trades"] if t["group"] == "control"]) == 1
    assert len([t for t in j["trades"] if t["group"] == "baseline"]) == 1, "una sola base per giorno di scan"

    # --- 2. ciclo di vita + benchmark sulle stesse date ---
    update_journal(j, upto(1), [], horizon=H, params=params, universe=universe, run_date=d[1])
    s = [t for t in j["trades"] if t["group"] == "signal"][0]
    assert s["status"] == "open" and s["entry_date"] == d[1]
    update_journal(j, upto(4), [], horizon=H, params=params, universe=universe, run_date=d[4])
    s = [t for t in j["trades"] if t["group"] == "signal"][0]
    assert s["status"] == "closed" and s["exit_date"] == d[4], s
    # SPY: ingresso d[1] = 101.0; uscita d[4] manca -> ultima barra <= d[4] è d[3] = 100*1.01^3
    exp_bench = (100 * 1.01 ** 3 / (100 * 1.01) - 1) * 100
    assert abs(s["bench_pnl_pct"] - exp_bench) < 0.02, (s["bench_pnl_pct"], exp_bench)
    assert abs(s["excess_pct"] - (s["pnl_pct"] - s["bench_pnl_pct"])) < 0.02
    c = [t for t in j["trades"] if t["group"] == "control"][0]
    assert c["status"] == "closed", "il controllo segue la stessa regola"

    # --- 3. dettaglio per l'email: chiusi all'ultimo scan, in scadenza, aperti ---
    det = journal_detail(j)
    assert [t["ticker"] for t in det["closed_last_run"]] == ["TKR"], det["closed_last_run"]
    assert det["open"] == [] and det["due_soon"] == []
    j3 = {"created": d[0], "config": {}, "trades": []}
    update_journal(j3, upto(0), sig, horizon=H, params=params, universe=universe, run_date=d[0])
    update_journal(j3, upto(3), [], horizon=H, params=params, universe=universe, run_date=d[3])
    det3 = journal_detail(j3)
    assert [t["ticker"] for t in det3["open"]] == ["TKR"]
    assert [t["ticker"] for t in det3["due_soon"]] == ["TKR"], "mancano <=2 barre all'uscita"
    assert det3["open"][0]["bars_left"] == 1
    assert det3["open"][0]["expected_exit"] >= d[3]

    # --- 4. le statistiche principali contano solo i segnali ---
    st = journal_stats(j)
    assert st["closed"] == 1 and st["control_closed"] == 1
    assert st["avg_excess_pct"] is not None
    n_base = len([t for t in j["trades"] if t["group"] == "baseline"])
    assert n_base == 3, f"una base per ogni giorno di scan (3 scan): {n_base}"

    # --- 5. verdetto: media alta ma i segnali NON battono la base -> niente promozione ---
    weeks = [x.strftime("%Y-%m-%d") for x in pd.date_range("2026-11-02", periods=14, freq="W-MON")]
    sig_tr = [_closed("signal", f"S{i}", weeks[i % 12], 2.0 + (i % 7) * 0.1, excess=0.2) for i in range(30)]
    ctl = [_closed("control", f"C{i}", weeks[i % 12], 1.9 + (i % 5) * 0.1) for i in range(30)]
    base_high = [_closed("baseline", f"B{i}", weeks[i % 12], 2.4 + (i % 5) * 0.1) for i in range(30)]
    st = journal_stats({"created": "2026-11-02", "config": {}, "trades": sig_tr + ctl + base_high})
    assert st["avg_pnl_pct"] >= PROTOCOL["promote_avg_pct"]
    assert st["edge_vs_baseline"] is not None and st["edge_vs_baseline"] <= 0
    assert st["verdict"] == "ESTENDI", st["verdict"]
    assert "base" in st["verdict_reason"]
    # il controllo dello stesso giorno è informativo: calcolato ma non entra nel verdetto
    assert st["edge_vs_control"] is not None and st["timing_edge"] is not None

    # ... e con i segnali nettamente sopra la base -> COERENTE col backtest
    base_low = [_closed("baseline", f"B{i}", weeks[i % 12], 0.3 + (i % 5) * 0.1) for i in range(30)]
    st = journal_stats({"created": "2026-11-02", "config": {}, "trades": sig_tr + ctl + base_low})
    assert st["verdict"] == "COERENTE", st["verdict"]
    assert st["edge_vs_baseline"] > 1.0
    assert st["t_edge_baseline_clustered"] is not None and st["t_edge_baseline_clustered"] > 2

    # con poche basi chiuse il confronto non entra nel verdetto
    st = journal_stats({"created": "2026-11-02", "config": {}, "trades": sig_tr + base_high[:3]})
    assert st["verdict"] == "COERENTE"

    print("OK test_forward_validation — controllo e base deterministici, benchmark sulle stesse date, "
          "dettaglio email, verdetto condizionato alla base giornaliera")


if __name__ == "__main__":
    main()
