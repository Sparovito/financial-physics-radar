"""
Test per l'autenticazione degli endpoint che modificano dati (main.py).

Problema: chiunque conoscesse l'URL pubblico poteva azzerare il journal,
far partire le email o modificare il portfolio.

Regola: se la variabile d'ambiente API_KEY è impostata, gli endpoint
mutanti richiedono l'header X-API-Key. Se non è impostata il server resta
aperto (sviluppo locale) e lo segnala su /auth/status.

Esecuzione: backend/venv/bin/python backend/tests/test_auth.py
"""
import os
import sys

os.environ["FPR_STORAGE"] = "local"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PROTECTED = [
    ("POST", "/scan/email"),
    ("POST", "/scan/test-email"),
    ("POST", "/stable-alert/config"),
    ("POST", "/stable-alert/trigger"),
    ("POST", "/stable-alert/test"),
    ("POST", "/stable-alert/trigger-with-result"),
    ("POST", "/forward-test/reset"),
    ("POST", "/portfolio/open"),
    ("POST", "/portfolio/update/{pos_id}"),
    ("POST", "/portfolio/close/{pos_id}"),
]
OPEN = [("GET", "/health"), ("POST", "/analyze"), ("GET", "/forward-test/status"),
        ("GET", "/auth/status")]


def main():
    from fastapi import HTTPException
    import main as backend_main
    from main import require_api_key, app

    # --- 1. senza API_KEY configurata: aperto ---
    os.environ.pop("API_KEY", None)
    assert require_api_key(None) is None
    assert require_api_key("qualsiasi") is None

    # --- 2. con API_KEY: header mancante o errato -> 401 ---
    os.environ["API_KEY"] = "chiave-di-test"
    for bad in (None, "", "sbagliata"):
        try:
            require_api_key(bad)
            raise AssertionError(f"chiave {bad!r} accettata")
        except HTTPException as e:
            assert e.status_code == 401
    assert require_api_key("chiave-di-test") is None
    os.environ.pop("API_KEY", None)

    # --- 3. ogni endpoint mutante dichiara la dipendenza ---
    def has_guard(method, path):
        for r in app.routes:
            if getattr(r, "path", None) == path and method in getattr(r, "methods", set()):
                return any(d.call is require_api_key for d in r.dependant.dependencies)
        raise AssertionError(f"route non trovata: {method} {path}")

    for method, path in PROTECTED:
        assert has_guard(method, path), f"{method} {path} NON protetto"
    for method, path in OPEN:
        assert not has_guard(method, path), f"{method} {path} non dovrebbe richiedere la chiave"

    # --- 4. /auth/status riflette la configurazione ---
    assert backend_main.auth_status()["auth_required"] is False
    os.environ["API_KEY"] = "x"
    assert backend_main.auth_status()["auth_required"] is True
    os.environ.pop("API_KEY", None)

    # --- 5. l'email originale Frozen/SUM delle 16:30 non è più schedulata ---
    assert backend_main.scheduler.get_job("daily_scan") is None, \
        "il job delle 16:30 deve restare spento salvo LEGACY_FROZEN_SUM_EMAIL=1"
    assert has_guard("POST", "/scan/email"), "l'invio manuale resta, protetto"
    assert not has_guard("POST", "/scan-daily-orange"), "la scansione giornaliera è di sola lettura"

    print(f"OK test_auth — {len(PROTECTED)} endpoint protetti, {len(OPEN)} aperti, 401 su chiave errata, "
          f"email 16:30 spenta")


if __name__ == "__main__":
    main()
