import json
from concurrent.futures import ThreadPoolExecutor

from settings_store import SettingsStore


def test_concurrent_saves_share_one_atomic_writer(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    payloads = [{"writer": writer, "sequence": sequence} for writer in range(4) for sequence in range(50)]

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(store.save, payload) for payload in payloads]
        for future in futures:
            future.result()

    assert json.loads(path.read_text()) in payloads
    assert not (tmp_path / "settings.json.tmp").exists()
