import json
import pathlib

import tdp_route_snapshot

_PINNED = pathlib.Path(__file__).parent / "fixtures" / "tdp_route_digests.json"


def test_route_selection_and_writes_match_the_pinned_record():
    pinned = json.loads(_PINNED.read_text())
    current = tdp_route_snapshot.build_digests()

    changed = sorted(name for name in pinned.keys() & current.keys() if pinned[name] != current[name])
    assert (changed, sorted(pinned.keys() - current.keys()), sorted(current.keys() - pinned.keys())) == (
        [], [], []
    ), (
        "TDP route behaviour changed; inspect with "
        "`python tests/tdp_route_snapshot.py out.json --full` on both trees"
    )
