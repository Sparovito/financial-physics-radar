"""
Test per l'email giornaliera dell'ARANCIONE (stable_scanner.build_orange_email).

L'email deve rispondere a tre domande, in quest'ordine:
  1. cosa c'è da fare oggi (nuovi segnali, uscite);
  2. cosa c'è in portafoglio (posizioni del forward test);
  3. i segnali stanno funzionando? — confronto con titoli a caso lo stesso
     giorno e in un giorno qualsiasi, accanto ai valori attesi dal backtest.

Esecuzione: backend/venv/bin/python backend/tests/test_orange_email.py
"""
import os
import sys

os.environ.setdefault("FPR_STORAGE", "local")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _result(n_signals=2, with_forward=True):
    entries = [{"ticker": f"TK{i}", "price": 100.0 + i, "current_price": 100.0 + i, "slope": 2.5 + i,
                "depth_pct": 1.0 + 3 * i, "price_change_since": 0.0, "date": "2026-11-10",
                "direction": "LONG", "days_ago": 0, "kind": "PANIC", "pending_execution": True}
               for i in range(n_signals)]
    res = {
        "entries_today": entries, "entries_recent": [], "active": [], "errors": [{"ticker": "X"}],
        "params": {"alpha": 200, "mode": "LONG", "entry_threshold": 0, "exit_threshold": 0,
                   "strategy": "ARANCIONE", "entry_z": 2.0, "horizon": 21,
                   "n_tickers": 633, "n_downloaded": 630, "date": "2026-11-10"},
    }
    if with_forward:
        res["forward_test"] = {
            "created": "2026-11-10", "total": 9, "pending": 2, "open": 3, "closed": 4,
            "sum_pnl_pct": 9.2, "avg_pnl_pct": 2.3, "win_rate": 75.0, "open_avg_pnl_pct": 1.1,
            "n_clusters": 2, "t_naive": 1.9, "t_clustered": None,
            "avg_excess_pct": 0.8, "control_closed": 4, "control_avg_pnl_pct": 1.9,
            "baseline_closed": 6, "baseline_avg_pnl_pct": 0.7, "index_closed": 0, "index_avg_pnl_pct": None,
            "edge_vs_control": 0.4, "timing_edge": 1.2, "edge_vs_baseline": 1.6,
            "t_edge_baseline_clustered": None,
            "expected": {"signal": 3.4, "control": 2.7, "baseline": 1.2, "win_rate": 65, "source": "test"},
            "verdict": "IN_CORSO", "verdict_reason": "servono 30 trade chiusi in 12 settimane distinte (ora 4 in 2)",
            "protocol": {"min_closed": 30, "min_clusters": 12, "promote_avg_pct": 1.0, "stop_avg_pct": 0.0,
                         "extend_to": 60, "min_baseline_closed": 10, "breadth_pct_index": 2.0},
            "protocol_violations": 0, "frozen_params": {"strategy": "ARANCIONE", "entry_z": 2.0, "horizon": 21},
            "n_runs": 7, "last_run": "2026-11-10",
        }
        res["forward_detail"] = {
            "last_run": "2026-11-10",
            "pending": [],
            "open": [{"ticker": "OPN", "entry_date": "2026-10-20", "entry_price": 50.0, "current_price": 51.5,
                      "current_pnl_pct": 2.9, "bars_held": 15, "horizon": 21, "bars_left": 6,
                      "expected_exit": "2026-11-18"},
                     {"ticker": "DUE", "entry_date": "2026-10-12", "entry_price": 80.0, "current_price": 79.0,
                      "current_pnl_pct": -1.35, "bars_held": 20, "horizon": 21, "bars_left": 1,
                      "expected_exit": "2026-11-11"}],
            "due_soon": [{"ticker": "DUE", "entry_date": "2026-10-12", "entry_price": 80.0, "current_price": 79.0,
                          "current_pnl_pct": -1.35, "bars_held": 20, "horizon": 21, "bars_left": 1,
                          "expected_exit": "2026-11-11"}],
            "closed_last_run": [{"ticker": "CLS", "entry_date": "2026-10-09", "entry_price": 20.0,
                                 "exit_date": "2026-11-10", "exit_price": 21.0, "pnl_pct": 4.9,
                                 "excess_pct": 2.1}],
        }
    return res


def main():
    from stable_scanner import build_orange_email

    subject, body = build_orange_email(_result())
    assert "2026-11-10" in subject and "2 segnal" in subject, subject
    assert "IN CORSO" in subject.upper() or "in corso" in subject.lower(), subject

    # 1. cosa fare: segnali ordinati per distanza dal fondamentale (il più profondo prima)
    assert body.index("TK1") < body.index("TK0"), "segnali da ordinare per profondità"
    assert "prossima" in body.lower() and "21" in body
    # uscite: chiuso all'ultimo scan e in scadenza
    for needle in ("CLS", "+4.90%", "DUE", "2026-11-11"):
        assert needle in body, f"manca {needle}"
    # 2. posizioni aperte
    assert "OPN" in body and "15/21" in body
    # 3. confronto onesto con i tre gruppi e i valori attesi
    low = body.lower()
    for needle in ("stesso giorno", "giorno qualsiasi", "atteso"):
        assert needle in low, f"manca '{needle}' nel confronto"
    for value in ("+2.30%", "+1.90%", "+0.70%", "+3.4%", "+2.7%", "+1.2%"):
        assert value in body, f"manca il valore {value}"
    assert "4/30" in body and "2/12" in body, "avanzamento del protocollo"
    assert "anni" in low, "va detto che la conferma statistica richiede anni"
    # qualità dei dati
    assert "630/633" in body

    # giornata di panico: molti segnali -> avviso sul tetto e sull'ampiezza
    subject_p, body_p = build_orange_email(_result(n_signals=25))
    assert "25 segnal" in subject_p
    assert "tetto" in body_p.lower() and "%" in body_p

    # nessun segnale e nessuna uscita: lo dice chiaramente
    quiet = _result(n_signals=0)
    quiet["forward_detail"]["closed_last_run"] = []
    quiet["forward_detail"]["due_soon"] = []
    _, body_q = build_orange_email(quiet)
    assert "nessuna azione" in body_q.lower()

    # senza journal (forward test spento) l'email esce comunque
    _, body_n = build_orange_email(_result(with_forward=False))
    assert "TK0" in body_n and "forward test non attivo" in body_n.lower()

    print("OK test_orange_email — azioni, posizioni, confronto a tre gruppi, panico, giornata vuota")


if __name__ == "__main__":
    main()
