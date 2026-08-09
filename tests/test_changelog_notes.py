import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "changelog_notes.py"


def _run(tmp_path: Path, mode: str, changelog: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), mode],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def test_check_accepts_separate_spanish_english_and_italian_blocks(tmp_path):
    changelog = """# Changelog

## [0.37.0](https://example.test/0.37.0)

### Español

* Abre el panel desde el QAM.
* Reinicia Decky para aplicar el cambio.

### English

* Open the panel from the QAM.
* Restart Decky to apply the change.

### Italiano

* Apri il pannello dal QAM.
* Riavvia Decky per applicare la modifica.

## [0.36.0](https://example.test/0.36.0)
"""

    result = _run(tmp_path, "--check", changelog)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "trilingual" in result.stdout


def test_release_body_groups_and_strips_all_three_language_labels(tmp_path):
    changelog = """# Changelog

## [0.37.0](https://example.test/0.37.0)

### Español

* Abre el panel desde el QAM. ([#415](https://example.test/415))

### English

* Open the panel from the QAM. ([#415](https://example.test/415))

### Italiano

* Apri il pannello dal QAM. ([#415](https://example.test/415))

## [0.36.0](https://example.test/0.36.0)
"""

    result = _run(tmp_path, "--release-body", changelog)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == """### Novedades

- Abre el panel desde el QAM.

### What's new

- Open the panel from the QAM.

### Novità

- Apri il pannello dal QAM.
"""


def test_check_rejects_partial_italian_translation(tmp_path):
    changelog = """# Changelog

## [0.37.0](https://example.test/0.37.0)

### Español

* Primera entrada.
* Segunda entrada.

### English

* First entry.
* Second entry.

### Italiano

* Prima voce.
"""

    result = _run(tmp_path, "--check", changelog)

    assert result.returncode == 1
    assert "Italian (**IT:**)" in result.stdout


def test_check_keeps_release_please_english_bullets_compatible(tmp_path):
    changelog = """# Changelog

## [0.37.0](https://example.test/0.37.0)

* Open the panel from the QAM.
* **ES:** Abre el panel desde el QAM.
"""

    result = _run(tmp_path, "--check", changelog)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "bilingual" in result.stdout


def test_check_keeps_explicit_language_labels_compatible(tmp_path):
    changelog = """# Changelog

## [0.37.0](https://example.test/0.37.0)

* **ES:** Abre el panel desde el QAM.
* **EN:** Open the panel from the QAM.
* **IT:** Apri il pannello dal QAM.
"""

    result = _run(tmp_path, "--check", changelog)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "trilingual" in result.stdout


def test_check_rejects_unknown_language_labels(tmp_path):
    changelog = """# Changelog

## [0.37.0](https://example.test/0.37.0)

* **ES:** Abre el panel desde el QAM.
* **EN:** Open the panel from the QAM.
* **FR:** Ouvrez le panneau depuis le QAM.
"""

    result = _run(tmp_path, "--check", changelog)

    assert result.returncode == 1
    assert "unsupported language label: FR" in result.stdout
