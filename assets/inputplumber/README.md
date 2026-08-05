# InputPlumber Xbox HD haptics extension

`compatibility.json` lists the InputPlumber versions maintained for the
experimental ROG Xbox Ally X RC73XA in-game trigger bridge. Each bundled
executable is the declared upstream commit with its adjacent patch applied.
Panel de Control selects one only when the active controller manager, device,
stock version and stock checksum all match the manifest.

InputPlumber is Copyright its contributors and licensed under
GPL-3.0-or-later. The corresponding source for each executable is its pinned
upstream commit plus the patch shipped in this directory.
`scripts/build-inputplumber-xbox-hd.sh` reconstructs every declared variant
from <https://github.com/ShadowBlip/InputPlumber>.

Run `bash scripts/build-inputplumber-xbox-hd.sh bin all` to rebuild the complete
manifest and `bash scripts/verify-inputplumber-xbox-hd.sh . all` to verify it.
