"""
Test per compute_stable_kinetic_z (logic.py).

Contesto: in main.py il blocco "Stable Kinetic Z" referenziava una variabile
`dF` inesistente -> NameError silenziato dal try/except -> pannello S.KinZ
sempre vuoto. Il fix estrae il calcolo in una funzione pura e testabile.

Esecuzione: backend/venv/bin/python backend/tests/test_stable_kinetic_z.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd


def _synthetic_px(n=700, seed=7):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.012, n)
    px = 100.0 * np.exp(np.cumsum(rets))
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.Series(px, index=idx, name="TEST")


def _reference_impl(px, alpha, threshold=0.5):
    """Reimplementazione indipendente della formula documentata:
    dF = derivata della curva fondamentale F_alpha (EMA span=alpha/10),
    EMA(20) su dF, kin = 0.5*alpha*dF_smooth^2, z rolling 252 (min 20),
    regime a isteresi +-threshold."""
    ema_span = max(5, int(alpha / 10))
    F_alpha = px.ewm(span=ema_span, adjust=False).mean()
    dF = F_alpha.diff().fillna(0)
    dF_clean = dF.fillna(0).replace([np.inf, -np.inf], 0)
    dF_smooth20 = dF_clean.ewm(span=20, adjust=False).mean()
    raw = 0.5 * alpha * dF_smooth20 ** 2
    mean = raw.rolling(window=252, min_periods=20).mean()
    std = raw.rolling(window=252, min_periods=20).std()
    z = ((raw - mean) / (std + 1e-6)).fillna(0)
    z_vals = z.values
    regime = np.zeros(len(z_vals))
    current = 0.0
    for i in range(len(z_vals)):
        if z_vals[i] > threshold:
            current = 1.0
        elif z_vals[i] < -threshold:
            current = -1.0
        regime[i] = current
    return z_vals.tolist(), regime.tolist()


def main():
    from logic import compute_stable_kinetic_z  # RED: non esiste ancora

    px = _synthetic_px()
    alpha = 200.0

    z_line, regime = compute_stable_kinetic_z(px, alpha)

    # 1. Lunghezze coerenti con la serie prezzi
    assert len(z_line) == len(px), f"len z {len(z_line)} != len px {len(px)}"
    assert len(regime) == len(px), f"len regime {len(regime)} != len px {len(px)}"

    # 2. Nessun NaN/Inf (deve essere JSON-serializzabile)
    assert all(np.isfinite(v) for v in z_line), "z contiene NaN/Inf"
    assert set(regime) <= {-1.0, 0.0, 1.0}, f"regime con valori inattesi: {set(regime)}"

    # 3. Corrispondenza con la formula documentata
    z_ref, regime_ref = _reference_impl(px, alpha)
    max_err = max(abs(a - b) for a, b in zip(z_line, z_ref))
    assert max_err < 1e-9, f"z diverge dalla formula documentata (max err {max_err})"
    assert regime == regime_ref, "regime diverge dalla reference"

    # 4. CAUSALITA': il prefisso non cambia troncando la serie
    cut = 500
    z_cut, regime_cut = compute_stable_kinetic_z(px.iloc[:cut], alpha)
    max_prefix_err = max(abs(a - b) for a, b in zip(z_cut, z_line[:cut]))
    assert max_prefix_err < 1e-12, (
        f"NON CAUSALE: il passato cambia aggiungendo dati (max err {max_prefix_err})"
    )
    assert regime_cut == regime[:cut], "regime non causale"

    # 5. Il regime deve avere almeno uno switch su dati realistici
    n_switch = int(np.sum(np.abs(np.diff(regime)) > 0))
    assert n_switch >= 1, "regime piatto: hysteresis sospetta"

    print(f"OK test_stable_kinetic_z — {len(px)} punti, {n_switch} switch regime, "
          f"max_err formula {max_err:.2e}")


if __name__ == "__main__":
    main()
