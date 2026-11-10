"""
Test per il PROTOCOLLO del forward test (forward_test.py).

I criteri di promozione sono fissati PRIMA di vedere i risultati
(memory/FORWARD_TEST_PROTOCOL.md):
  - si giudica solo con almeno 30 trade chiusi in almeno 12 settimane distinte
    (i panici arrivano a grappolo: 30 trade nello stesso giorno sono 1 evento)
  - media/trade >= +1.0%  -> COERENTE col backtest (semaforo, non prova)
  - media/trade <= 0%     -> STOP
  - in mezzo              -> ESTENDI fino a 60, poi NON_CONFERMATO
  - parametri congelati: se cambiano a journal avviato, viene registrata
    una violazione del protocollo
Inoltre: significatività robusta ai cluster (t sulle medie settimanali) e
registro dell'universo scansionato (contro il survivorship in avanti).

Esecuzione: backend/venv/bin/python backend/tests/test_forward_protocol.py
"""
import os
import sys

os.environ["FPR_STORAGE"] = "local"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd


def _closed(ticker, entry_date, pnl):
    return {"id": f"{ticker}|{entry_date}", "ticker": ticker, "strategy": "ARANCIONE",
            "direction": "LONG", "signal_date": entry_date, "status": "closed",
            "entry_date": entry_date, "entry_price": 100.0, "bars_held": 21,
            "exit_date": entry_date, "exit_price": 100.0 + pnl, "pnl_pct": pnl,
            "current_price": 100.0 + pnl, "current_pnl_pct": pnl, "horizon": 21,
            "cost_pct": 0.05}


def _journal(trades):
    return {"created": "2026-07-06", "config": {}, "trades": trades}


def main():
    from forward_test import journal_stats, update_journal, PROTOCOL

    assert PROTOCOL["min_closed"] == 30 and PROTOCOL["min_clusters"] == 12
    assert PROTOCOL["promote_avg_pct"] == 1.0 and PROTOCOL["stop_avg_pct"] == 0.0

    weeks = [d.strftime("%Y-%m-%d") for d in pd.date_range("2026-07-06", periods=14, freq="W-MON")]

    # --- 1. pochi trade: ancora in corso ---
    st = journal_stats(_journal([_closed(f"T{i}", weeks[i % 4], 2.0) for i in range(10)]))
    assert st["verdict"] == "IN_CORSO", st["verdict"]
    assert st["closed"] == 10 and st["n_clusters"] == 4

    # --- 2. 30 trade ma tutti nella stessa settimana: NON giudicabile ---
    st = journal_stats(_journal([_closed(f"T{i}", weeks[0], 3.0) for i in range(30)]))
    assert st["n_clusters"] == 1
    assert st["verdict"] == "IN_CORSO", "un solo grappolo non basta per giudicare"

    # --- 2b. 30 trade ma in sole 5 settimane: ancora troppo pochi eventi indipendenti ---
    st = journal_stats(_journal([_closed(f"T{i}", weeks[i % 5], 2.0) for i in range(30)]))
    assert st["verdict"] == "IN_CORSO" and st["n_clusters"] == 5

    # --- 3. 30 trade su 12 settimane, media +2% -> COERENTE ---
    st = journal_stats(_journal([_closed(f"T{i}", weeks[i % 12], 2.0 + (i % 7) * 0.1) for i in range(30)]))
    assert st["verdict"] == "COERENTE", st
    assert st["n_clusters"] == 12
    assert st["t_clustered"] is not None and st["t_clustered"] > 2

    # --- 4. media negativa -> STOP ---
    st = journal_stats(_journal([_closed(f"T{i}", weeks[i % 12], -0.5) for i in range(30)]))
    assert st["verdict"] == "STOP", st["verdict"]

    # --- 5. media tra 0 e 1: ESTENDI sotto 60, NON_CONFERMATO da 60 in su ---
    st = journal_stats(_journal([_closed(f"T{i}", weeks[i % 12], 0.5) for i in range(40)]))
    assert st["verdict"] == "ESTENDI", st["verdict"]
    st = journal_stats(_journal([_closed(f"T{i}", weeks[i % 13], 0.5) for i in range(60)]))
    assert st["verdict"] == "NON_CONFERMATO", st["verdict"]

    # --- 6. t cluster-robusto < t ingenuo quando i trade sono a grappolo ---
    clustered = []
    for w, level in zip(weeks[:4], [6.0, -3.0, 5.0, -2.0]):
        clustered += [_closed(f"T{w}{i}", w, level) for i in range(10)]
    st = journal_stats(_journal(clustered))
    assert st["t_naive"] > st["t_clustered"], (
        f"il t ingenuo ({st['t_naive']}) deve sovrastimare quello a cluster ({st['t_clustered']})")

    # --- 7. parametri congelati: cambio a journal avviato = violazione ---
    j = _journal([])
    p0 = {"strategy": "ARANCIONE", "entry_z": 2.0, "horizon": 21}
    update_journal(j, {}, [], horizon=21, params=p0, universe=["A", "B"], run_date="2026-07-06")
    assert j["config"]["params"] == p0
    assert journal_stats(j)["protocol_violations"] == 0

    j["trades"].append(_closed("A", "2026-07-06", 1.0))
    update_journal(j, {}, [], horizon=21, params=dict(p0, entry_z=1.5),
                   universe=["A", "B"], run_date="2026-07-07")
    assert journal_stats(j)["protocol_violations"] == 1
    assert j["config"]["params"] == p0, "i parametri originali restano il riferimento"
    # la stessa modifica ripetuta non conta due volte
    update_journal(j, {}, [], horizon=21, params=dict(p0, entry_z=1.5),
                   universe=["A", "B"], run_date="2026-07-08")
    assert journal_stats(j)["protocol_violations"] == 1

    # --- 8. registro universo: snapshot solo quando cambia, un run per data ---
    assert len(j["universe_snapshots"]) == 1
    assert j["universe_snapshots"][0]["tickers"] == ["A", "B"]
    update_journal(j, {}, [], horizon=21, params=p0, universe=["A", "B", "C"], run_date="2026-07-09")
    assert len(j["universe_snapshots"]) == 2
    assert [r["date"] for r in j["runs"]] == ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09"]
    update_journal(j, {}, [], horizon=21, params=p0, universe=["A", "B", "C"], run_date="2026-07-09")
    assert len(j["runs"]) == 4, "due scan nello stesso giorno = un solo run"

    print("OK test_forward_protocol — verdetti, cluster, t robusto, parametri congelati, registro universo")


if __name__ == "__main__":
    main()
