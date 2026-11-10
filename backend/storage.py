"""
Persistenza dello stato operativo (journal del forward test, config email).

Su Railway il disco del container si azzera a ogni deploy/riavvio: un file
JSON locale non è persistenza. Lo stato va su Firestore (collezione
`app_state`, come già fa il portfolio) e il file locale resta come mirror
e come fallback quando Firestore non è raggiungibile o non è configurato.

Regole:
- load(): Firestore se ha il documento; altrimenti file locale (seed);
  altrimenti il default. load() non scrive mai.
- save(): scrive su Firestore E sul file locale (mirror, best effort).
- FPR_STORAGE=local forza il solo backend locale (test, CI).
"""
import os
import json
import gzip
import base64
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COLLECTION = "app_state"
# Sotto questa soglia il documento resta leggibile dalla console Firebase;
# sopra viene compresso (limite Firestore: 1 MB per documento).
MAX_PLAIN_BYTES = 400_000
READ_TIMEOUT_S = 10


def encode_payload(data):
    raw = json.dumps(data, separators=(",", ":"))
    stamp = datetime.datetime.utcnow().isoformat() + "Z"
    if len(raw.encode("utf-8")) <= MAX_PLAIN_BYTES:
        return {"json": raw, "updated": stamp}
    packed = gzip.compress(raw.encode("utf-8"))
    return {"gz": base64.b64encode(packed).decode("ascii"), "updated": stamp}


def decode_payload(doc):
    if not doc:
        return None
    if "json" in doc:
        return json.loads(doc["json"])
    if "gz" in doc:
        return json.loads(gzip.decompress(base64.b64decode(doc["gz"])).decode("utf-8"))
    return None


class LocalBackend:
    def __init__(self, base_dir=BASE_DIR):
        self.base_dir = base_dir

    def _path(self, name):
        return os.path.join(self.base_dir, f"{name}.json")

    def get(self, name):
        p = self._path(name)
        if not os.path.exists(p):
            return None
        with open(p, "r") as f:
            return json.load(f)

    def set(self, name, data):
        with open(self._path(name), "w") as f:
            json.dump(data, f, indent=1)


class FirestoreBackend:
    def __init__(self, db, collection=COLLECTION):
        self.db = db
        self.collection = collection

    def get(self, name):
        snap = self.db.collection(self.collection).document(name).get(timeout=READ_TIMEOUT_S)
        if not snap.exists:
            return None
        return decode_payload(snap.to_dict())

    def set(self, name, data):
        self.db.collection(self.collection).document(name).set(encode_payload(data))


class Storage:
    def __init__(self, remote=None, local=None):
        self.remote = remote
        self.local = local or LocalBackend()

    def load(self, name, default=None):
        if self.remote is not None:
            try:
                data = self.remote.get(name)
                if data is not None:
                    return data
            except Exception as e:
                print(f"⚠️ Storage remoto non leggibile per '{name}' ({e}): uso il file locale")
        try:
            data = self.local.get(name)
            if data is not None:
                return data
        except Exception as e:
            print(f"⚠️ File locale '{name}' illeggibile ({e})")
        return default

    def save(self, name, data):
        ok_remote = None
        if self.remote is not None:
            try:
                self.remote.set(name, data)
                ok_remote = True
            except Exception as e:
                ok_remote = False
                print(f"⚠️ Salvataggio remoto di '{name}' fallito ({e}): resta solo il file locale")
        try:
            self.local.set(name, data)
        except Exception as e:
            print(f"⚠️ Mirror locale di '{name}' non scritto ({e})")
            if not ok_remote:
                raise
        return ok_remote is not False

    def status(self):
        return {"remote": self.remote is not None,
                "backend": "firestore" if self.remote is not None else "file locale"}


def _firestore_client():
    """Stesse credenziali del portfolio: env FIREBASE_SERVICE_ACCOUNT_BASE64
    (Railway) oppure serviceAccountKey.json (sviluppo locale)."""
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = None
        env_key = os.getenv("FIREBASE_SERVICE_ACCOUNT_BASE64")
        if env_key:
            cred = credentials.Certificate(json.loads(base64.b64decode(env_key).decode("utf-8")))
        else:
            key_path = os.path.join(BASE_DIR, "serviceAccountKey.json")
            if os.path.exists(key_path):
                cred = credentials.Certificate(key_path)
        if cred is None:
            return None
        firebase_admin.initialize_app(cred)
    return firestore.client()


_storage = None


def get_storage():
    global _storage
    if _storage is not None:
        return _storage
    remote = None
    if os.getenv("FPR_STORAGE", "").lower() != "local":
        try:
            db = _firestore_client()
            if db is not None:
                remote = FirestoreBackend(db)
        except Exception as e:
            print(f"⚠️ Firestore non disponibile per lo storage ({e}): uso i file locali")
    _storage = Storage(remote=remote)
    print(f"💾 Storage stato operativo: {_storage.status()['backend']}")
    return _storage
