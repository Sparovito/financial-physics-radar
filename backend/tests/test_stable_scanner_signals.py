"""
Test per stable_scanner.py rifatto sul motore unificato.

Problemi risolti:
1. Il vecchio scanner usava una semantica DIVERSA da Lab/backend
   (crossing-based invece di level-based, soglie SHORT negate a mano,
   BOTH con stato condiviso). Ora deriva tutto da stable_strategy.backtest_stable.
2. Barra parziale: girando alle 10:05 Rome (mercato USA aperto) l'ultima
   candela daily Yahoo è incompleta -> i segnali "ENTRY OGGI" potevano
   sparire il giorno dopo. Ora drop_partial_last_bar scarta la barra di oggi
   se calcolata prima delle 22:05 Europe/Rome.

Esecuzione: backend/venv/bin/python backend/tests/test_stable_scanner_signals.py
"""
import sys
import os
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _px_decline_then_rally(n_down=100, n_up=50, start="2025-01-02"):
    vals = [100.0]
    for _ in range(n_down - 1):
        vals.append(vals[-1] * 0.997)
    for _ in range(n_up):
        vals.append(vals[-1] * 1.005)
    idx = pd.date_range(start, periods=len(vals), freq="B")
    return pd.Series(vals, index=idx, name="TEST")


def _stable_slope(px, alpha=200):
    ema_span = max(5, int(alpha / 10))
    F = px.ewm(span=ema_span, adjust=False).mean()
    dF = F.diff().fillna(0)
    return dF.ewm(span=14, adjust=False).mean()


def test_active_position_and_entry_window():
    from stable_scanner import analyze_ticker_signals

    px = _px_decline_then_rally()
    slope = _stable_slope(px)
    # prima barra in cui lo slope diventa positivo = data del segnale ENTRY
    cross_idx = next(i for i in range(1, len(slope)) if slope.iloc[i] > 0)
    signal_date = px.index[cross_idx].date()

    # --- oggi = ultimo giorno: il segnale è vecchio -> nessuna entry <5gg,
    #     ma la posizione LONG è ATTIVA e in profitto ---
    today = px.index[-1].date()
    res = analyze_ticker_signals("TEST", px, today, alpha=200, mode="LONG",
                                 entry_threshold=0.0, exit_threshold=0.0)
    assert res["entries"] == [], f"entry inattese: {res['entries']}"
    assert len(res["active"]) == 1, f"attesa 1 posizione attiva: {res['active']}"
    act = res["active"][0]
    assert act["direction"] == "LONG"
    assert act["pnl_pct"] > 0, "il rally dovrebbe dare pnl positivo"
    # esecuzione t+1: entry il giorno DOPO il segnale
    assert act["entry_date"] == px.index[cross_idx + 1].strftime("%Y-%m-%d"), (
        f"entry {act['entry_date']} != exec t+1 {px.index[cross_idx + 1].date()}"
    )

    # --- oggi = 2 giorni (calendario) dopo il segnale -> entry recente ---
    today2 = signal_date + datetime.timedelta(days=2)
    res2 = analyze_ticker_signals("TEST", px, today2, alpha=200, mode="LONG",
                                  entry_threshold=0.0, exit_threshold=0.0)
    matching = [e for e in res2["entries"] if e["date"] == signal_date.strftime("%Y-%m-%d")]
    assert len(matching) == 1, f"attesa 1 entry recente: {res2['entries']}"
    assert matching[0]["days_ago"] == 2
    assert matching[0]["direction"] == "LONG"
    print(f"  OK entry/active (segnale {signal_date}, exec t+1, pnl {act['pnl_pct']:.1f}%)")


def test_short_mirror_thresholds():
    from stable_scanner import analyze_ticker_signals

    # discesa ripida -> slope fortemente negativo
    vals = [100.0]
    for _ in range(120):
        vals.append(vals[-1] * 0.99)
    px = pd.Series(vals, index=pd.date_range("2025-01-02", periods=len(vals), freq="B"))

    today = px.index[-1].date()
    res = analyze_ticker_signals("TEST", px, today, alpha=200, mode="SHORT",
                                 entry_threshold=0.3, exit_threshold=0.2)
    # soglie SPECULARI: lo short entra quando slope < -0.3
    slope = _stable_slope(px)
    assert slope.min() < -0.3, "lo scenario deve superare la soglia"
    assert len(res["active"]) == 1, f"atteso SHORT attivo: {res['active']}"
    assert res["active"][0]["direction"] == "SHORT"
    assert res["active"][0]["pnl_pct"] > 0, "short in discesa deve guadagnare"
    print("  OK SHORT speculare nello scanner (entry slope < -0.3)")


def test_drop_partial_last_bar():
    from stable_scanner import drop_partial_last_bar

    today = datetime.date(2026, 7, 3)
    idx = pd.date_range("2026-06-01", "2026-07-03", freq="B")
    px = pd.Series(np.linspace(100, 110, len(idx)), index=idx)
    assert px.index[-1].date() == today

    # Alle 15:00 Rome i mercati USA sono aperti -> barra di oggi SCARTATA
    now_open = datetime.datetime(2026, 7, 3, 15, 0)
    out = drop_partial_last_bar(px, today=today, now=now_open)
    assert len(out) == len(px) - 1, "barra parziale non scartata"
    assert out.index[-1].date() < today

    # Alle 22:30 Rome la candela USA è chiusa -> barra di oggi TENUTA
    now_closed = datetime.datetime(2026, 7, 3, 22, 30)
    out2 = drop_partial_last_bar(px, today=today, now=now_closed)
    assert len(out2) == len(px), "barra completa scartata per errore"

    # Ultima barra di ieri (es. weekend): mai scartata
    px_yesterday = px.iloc[:-1]
    out3 = drop_partial_last_bar(px_yesterday, today=today, now=now_open)
    assert len(out3) == len(px_yesterday)
    print("  OK drop_partial_last_bar (15:00 scarta, 22:30 tiene, ieri intatta)")


def test_default_config():
    from stable_scanner import DEFAULT_CONFIG
    assert DEFAULT_CONFIG["trigger_hour"] == 22, "trigger default deve essere dopo la chiusura USA"
    assert DEFAULT_CONFIG["trigger_minute"] == 30
    assert DEFAULT_CONFIG.get("skip_partial_today") is True
    print("  OK default config (22:30 Rome, skip_partial_today)")


def main():
    test_active_position_and_entry_window()
    test_short_mirror_thresholds()
    test_drop_partial_last_bar()
    test_default_config()
    print("OK test_stable_scanner_signals — 4/4")


if __name__ == "__main__":
    main()
