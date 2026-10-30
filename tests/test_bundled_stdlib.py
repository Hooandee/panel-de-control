import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Decky's frozen Python omits these on some releases (Steam Deck LCD, Decky 3.2.x): importing
# them keeps the whole backend from starting.
MISSING_ON_DECKY = ("http.server", "socketserver", "xmlrpc", "wsgiref")


def test_backend_avoids_modules_missing_from_deckys_python():
    offenders = []
    for path in [ROOT / "main.py", *sorted((ROOT / "py_modules").rglob("*.py"))]:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*(from|import)\s+(" + "|".join(re.escape(m) for m in MISSING_ON_DECKY) + r")\b", line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert offenders == []
