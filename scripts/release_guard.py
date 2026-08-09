#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys


_RELEASE_COMMIT = re.compile(
    r"^chore\(main\): release panel-de-control "
    r"(?P<version>\d+\.\d+\.\d+)(?: \(#\d+\))?$"
)
_RELEASE_HEADING = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)\]\(")
_RELEASE_FOOTER = (
    "This PR was generated with [Release Please]"
    "(https://github.com/googleapis/release-please). See "
    "[documentation](https://github.com/googleapis/release-please#release-please)."
)


def _release_version(value: str) -> str | None:
    first_line = value.splitlines()[0] if value else ""
    match = _RELEASE_COMMIT.fullmatch(first_line.strip())
    return match.group("version") if match else None


def validate_pr(title: str, body: str) -> str | None:
    version = _release_version(title)
    if version is None:
        return None

    lines = body.replace("\r\n", "\n").splitlines()
    delimiters = [index for index, line in enumerate(lines) if line == "---"]
    if len(delimiters) < 2:
        return (
            "Release Please no puede reconocer esta PR: conserva los dos "
            "delimitadores '---', el bloque de la versión y el footer generado."
        )

    content = lines[delimiters[0] + 1 : delimiters[-1]]
    first_content_line = next((line.strip() for line in content if line.strip()), "")
    heading = _RELEASE_HEADING.match(first_content_line)
    if heading is None or heading.group("version") != version:
        return (
            "Release Please no puede reconocer esta PR: la primera línea útil del "
            f"bloque generado debe contener la versión {version}."
        )

    footer = "\n".join(lines[delimiters[-1] + 1 :])
    if _RELEASE_FOOTER not in footer:
        return (
            "Release Please no puede reconocer esta PR: restaura el footer generado "
            "completo después del último delimitador."
        )
    return None


def validate_result(commit_message: str, release_created: str) -> str | None:
    version = _release_version(commit_message)
    if version is not None and release_created.lower() != "true":
        return (
            f"El commit de release {version} no creó el tag ni el artefacto. "
            "Release Please probablemente no pudo analizar el cuerpo de la PR."
        )
    return None


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "pr":
        error = validate_pr(
            os.environ.get("RELEASE_PR_TITLE", ""),
            os.environ.get("RELEASE_PR_BODY", ""),
        )
    elif mode == "result":
        error = validate_result(
            os.environ.get("RELEASE_COMMIT_MESSAGE", ""),
            os.environ.get("RELEASE_CREATED", ""),
        )
    else:
        print("usage: release_guard.py pr | result", file=sys.stderr)
        return 2

    if error:
        print(f"::error::{error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
