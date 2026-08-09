import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_guard.py"
GENERATED_FOOTER = (
    "This PR was generated with [Release Please]"
    "(https://github.com/googleapis/release-please). See "
    "[documentation](https://github.com/googleapis/release-please#release-please)."
)


def _run(mode: str, **values: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **values}
    return subprocess.run(
        [sys.executable, str(SCRIPT), mode],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_pr_rejects_release_body_that_release_please_cannot_parse():
    result = _run(
        "pr",
        RELEASE_PR_TITLE="chore(main): release panel-de-control 0.36.0",
        RELEASE_PR_BODY="## Español\n\nNotas humanas sin el bloque generado.",
    )

    assert result.returncode == 1
    assert "Release Please no puede reconocer" in result.stdout


def test_pr_accepts_human_header_around_parseable_release_body():
    body = f"""Resumen humano en español.
---

## [0.37.0](https://example.test/compare) (2026-08-09)

* Cambio visible

---
{GENERATED_FOOTER}
"""
    result = _run(
        "pr",
        RELEASE_PR_TITLE="chore(main): release panel-de-control 0.37.0",
        RELEASE_PR_BODY=body,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_pr_rejects_human_text_inside_generated_release_section():
    body = f"""Resumen humano fuera del bloque.
---

Esta línea impide que el parser encuentre la versión.
## [0.37.0](https://example.test/compare) (2026-08-09)

---
{GENERATED_FOOTER}
"""
    result = _run(
        "pr",
        RELEASE_PR_TITLE="chore(main): release panel-de-control 0.37.0",
        RELEASE_PR_BODY=body,
    )

    assert result.returncode == 1
    assert "primera línea útil" in result.stdout


def test_pr_rejects_truncated_release_please_footer():
    body = """Resumen humano.
---

## [0.37.0](https://example.test/compare) (2026-08-09)

---
This PR was generated with [Release Please](https://example.test/wrong).
"""
    result = _run(
        "pr",
        RELEASE_PR_TITLE="chore(main): release panel-de-control 0.37.0",
        RELEASE_PR_BODY=body,
    )

    assert result.returncode == 1
    assert "footer generado completo" in result.stdout


def test_pr_ignores_non_release_pull_requests():
    result = _run(
        "pr",
        RELEASE_PR_TITLE="docs: improve installation guide",
        RELEASE_PR_BODY="Any body is valid here.",
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_result_rejects_release_commit_without_created_release():
    result = _run(
        "result",
        RELEASE_COMMIT_MESSAGE=(
            "chore(main): release panel-de-control 0.36.0 (#415)\n\nRelease notes"
        ),
        RELEASE_CREATED="false",
    )

    assert result.returncode == 1
    assert "no creó el tag ni el artefacto" in result.stdout


def test_result_accepts_created_release_and_regular_commit():
    released = _run(
        "result",
        RELEASE_COMMIT_MESSAGE="chore(main): release panel-de-control 0.37.0 (#416)",
        RELEASE_CREATED="true",
    )
    regular = _run(
        "result",
        RELEASE_COMMIT_MESSAGE="fix: keep plugin bundle loadable",
        RELEASE_CREATED="false",
    )

    assert released.returncode == 0, released.stdout + released.stderr
    assert regular.returncode == 0, regular.stdout + regular.stderr
