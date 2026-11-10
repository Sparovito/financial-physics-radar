"""
Esegue l'intera suite (Python + node). Usato dalla CI e in locale:

    backend/venv/bin/python backend/tests/run_all.py

FPR_STORAGE=local: i test non devono mai toccare il Firestore vero.
Esce con codice 1 al primo insieme di fallimenti.
"""
import os
import sys
import glob
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
env = dict(os.environ, FPR_STORAGE="local")
env.pop("API_KEY", None)

failed = []
py_tests = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
node_tests = sorted(glob.glob(os.path.join(HERE, "test_*.cjs")))
node = shutil.which("node")

for path in py_tests:
    name = os.path.basename(path)
    if name == "test_js_py_parity.py" and not node:
        print(f"SKIP  {name} (node non disponibile)")
        continue
    proc = subprocess.run([sys.executable, path], capture_output=True, text=True, env=env)
    last = (proc.stdout.strip().splitlines() or [""])[-1]
    if proc.returncode == 0 and last.startswith("OK"):
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")
        failed.append(name)

for path in node_tests:
    name = os.path.basename(path)
    if not node:
        print(f"SKIP  {name} (node non disponibile)")
        continue
    proc = subprocess.run([node, path], capture_output=True, text=True, env=env)
    if proc.returncode == 0:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")
        failed.append(name)

total = len(py_tests) + len(node_tests)
print(f"\n{total - len(failed)}/{total} passati")
sys.exit(1 if failed else 0)
