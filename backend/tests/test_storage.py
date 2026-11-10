"""
Test per storage.py — persistenza di journal e config.

Problema: journal del forward test e config email erano file JSON sul disco
del backend; su Railway il disco si azzera a ogni deploy. Ora lo stato va su
Firestore (come il portfolio) con il file locale come mirror/fallback.

Qui non si tocca il Firestore vero: si testano la codifica dei documenti e
la logica primario/fallback con un remoto finto in memoria.

Esecuzione: backend/venv/bin/python backend/tests/test_storage.py
"""
import os
import sys
import json
import tempfile

os.environ["FPR_STORAGE"] = "local"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeRemote:
    """Remoto in memoria con la stessa interfaccia dei backend (get/set)."""
    def __init__(self, fail=False):
        self.docs = {}
        self.fail = fail

    def get(self, name):
        if self.fail:
            raise RuntimeError("rete assente")
        return self.docs.get(name)

    def set(self, name, data):
        if self.fail:
            raise RuntimeError("rete assente")
        self.docs[name] = json.loads(json.dumps(data))


def main():
    from storage import (LocalBackend, Storage, encode_payload, decode_payload,
                         MAX_PLAIN_BYTES)

    with tempfile.TemporaryDirectory() as tmp:
        local = LocalBackend(tmp)

        # --- 1. backend locale: roundtrip e documento mancante ---
        assert local.get("non_esiste") is None
        local.set("cfg", {"a": 1, "lista": [1, 2, 3]})
        assert local.get("cfg") == {"a": 1, "lista": [1, 2, 3]}
        assert os.path.exists(os.path.join(tmp, "cfg.json"))

        # --- 2. codifica: documento piccolo in chiaro, grande compresso ---
        small = {"trades": [{"id": "A|2026-01-01", "pnl": 1.5}]}
        enc = encode_payload(small)
        assert "json" in enc and "gz" not in enc, "piccolo deve restare leggibile"
        assert decode_payload(enc) == small

        big = {"trades": [{"id": f"T{i}|2026-01-01", "note": "x" * 300} for i in range(4000)]}
        assert len(json.dumps(big)) > MAX_PLAIN_BYTES
        enc_big = encode_payload(big)
        assert "gz" in enc_big, "grande deve essere compresso"
        assert len(enc_big["gz"]) < 900_000, "deve stare nel limite di 1MB di Firestore"
        assert decode_payload(enc_big) == big

        # --- 3. remoto primario + mirror locale ---
        remote = FakeRemote()
        st = Storage(remote=remote, local=local)
        st.save("journal", {"trades": [1, 2]})
        assert remote.docs["journal"] == {"trades": [1, 2]}
        assert local.get("journal") == {"trades": [1, 2]}, "il mirror locale va scritto"
        assert st.load("journal") == {"trades": [1, 2]}

        # il remoto vince sul file locale
        local.set("journal", {"trades": ["vecchio"]})
        assert st.load("journal") == {"trades": [1, 2]}

        # --- 4. remoto senza documento -> seed dal file locale (senza scrivere) ---
        local.set("seed_cfg", {"strategy": "ARANCIONE"})
        assert st.load("seed_cfg") == {"strategy": "ARANCIONE"}
        assert "seed_cfg" not in remote.docs, "load non deve scrivere sul remoto"

        # --- 5. niente da nessuna parte -> default ---
        assert st.load("mai_visto", default={"x": 0}) == {"x": 0}

        # --- 6. remoto in errore: si degrada sul locale, senza eccezioni ---
        broken = Storage(remote=FakeRemote(fail=True), local=local)
        assert broken.load("journal") == {"trades": ["vecchio"]}
        broken.save("journal", {"trades": ["nuovo"]})     # non deve sollevare
        assert local.get("journal") == {"trades": ["nuovo"]}

        # --- 7. solo locale ---
        only_local = Storage(remote=None, local=local)
        only_local.save("solo", {"k": "v"})
        assert only_local.load("solo") == {"k": "v"}
        assert only_local.status()["remote"] is False

    print("OK test_storage — locale, codifica chiaro/gz, primario+mirror, seed, fallback su errore")


if __name__ == "__main__":
    main()
