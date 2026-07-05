"""
Test per il filtro passa-basso CAUSALE che sostituisce filtfilt nel segnale SUM.

Problema: filtfilt (Butterworth zero-phase) è bidirezionale — il valore
filtrato al giorno t dipende dai giorni SUCCESSIVI. Il backtest SUM operava
quindi su un segnale che conosce il futuro.

Fix: causal_lowpass (stesso Butterworth, versione lfilter causale con
inizializzazione lfilter_zi sul primo campione).

Proprietà verificate:
1. Causalità stretta: il prefisso non cambia troncando la serie.
2. Il risultato è DIVERSO da filtfilt (sanity: la semantica è cambiata).
3. End-to-end: /verify-integrity sulla strategia SUM sintetica riporta
   0 trade corrotti (con filtfilt ne trovava >0).

Esecuzione: backend/venv/bin/python backend/tests/test_causal_sum.py
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np


def main():
    from logic import causal_lowpass  # RED: non esiste ancora
    from scipy.signal import butter, filtfilt

    rng = np.random.default_rng(42)
    x = np.cumsum(rng.normal(0, 1, 600)) + 3 * np.sin(np.linspace(0, 20 * np.pi, 600))

    # --- 1. Causalità: prefix stability ---
    full = causal_lowpass(x.tolist())
    for cut in (150, 300, 550):
        trunc = causal_lowpass(x[:cut].tolist())
        max_err = max(abs(a - b) for a, b in zip(trunc, full[:cut]))
        assert max_err < 1e-10, (
            f"NON CAUSALE: troncando a {cut} il prefisso cambia (max err {max_err:.2e})"
        )

    # --- 2. Deve differire da filtfilt (zero-phase) ---
    b, a = butter(N=2, Wn=0.05, btype='low')
    zero_phase = filtfilt(b, a, x)
    diff = max(abs(p - q) for p, q in zip(full, zero_phase))
    assert diff > 0.1, "sospetto: output identico a filtfilt (ancora non-causale?)"

    # --- 3. Lunghezza e serie vuota ---
    assert len(full) == len(x)
    assert causal_lowpass([]) == []

    print(f"OK causal_lowpass — prefisso stabile, diverge da filtfilt (max diff {diff:.2f})")

    # --- 4. END-TO-END: verify-integrity SUM deve dare 0 corrotti ---
    from test_verify_integrity_cache import _build_synthetic_cache
    import main as backend_main
    from main import verify_trade_integrity, VerifyIntegrityRequest

    px, frozen = _build_synthetic_cache()
    backend_main.TICKER_CACHE["TESTCAUSAL"] = {"px": px, "frozen": frozen}

    res = asyncio.run(verify_trade_integrity(
        VerifyIntegrityRequest(ticker="TESTCAUSAL", strategy="SUM")))
    assert res["status"] == "ok", f"status inatteso: {res}"
    assert res["total_trades"] > 0, "verifica vacua"
    assert res["corrupted_count"] == 0, (
        f"LOOKAHEAD RESIDUO: {res['corrupted_count']} trade corrotti nella SUM "
        f"({[c['changes'] for c in res['corrupted_trades']]})"
    )

    print(f"OK verify-integrity SUM — {res['total_trades']} trade, 0 corrotti (era >0 con filtfilt)")


if __name__ == "__main__":
    main()
