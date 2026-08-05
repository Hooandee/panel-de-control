#!/usr/bin/env python3
import sys
from pathlib import Path


def main():
    if len(sys.argv) not in {2, 3}:
        raise SystemExit("usage: inputplumber-manifest.py <root> [all|version]")
    root = Path(sys.argv[1]).resolve()
    selector = sys.argv[2] if len(sys.argv) == 3 else "all"
    sys.path.insert(0, str(root / "py_modules"))
    from controllers.inputplumber_compat import load_builds

    builds = load_builds(str(root))
    selected = [
        build for build in builds
        if selector == "all" or build.version == selector
    ]
    if not selected:
        raise SystemExit(f"unsupported InputPlumber version: {selector}")
    for build in selected:
        print("\t".join((
            build.version,
            build.upstream_commit,
            build.patch,
            build.artifact,
            build.artifact_sha256,
            build.provenance,
        )))


if __name__ == "__main__":
    main()
