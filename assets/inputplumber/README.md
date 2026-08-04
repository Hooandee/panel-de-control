# InputPlumber Xbox HD haptics extension

The bundled `inputplumber-xbox-hd-v0.77.4` executable is InputPlumber 0.77.4
(commit `bb7424fd6fc097d123850950aaf1e6988f2093f3`) with the adjacent
`v0.77.4-xbox-hd.patch` applied. It is used only on the ROG Xbox Ally X RC73XA
with the exact supported stock InputPlumber build.

InputPlumber is Copyright its contributors and licensed under GPL-3.0. Its
corresponding source is the pinned upstream commit plus the patch shipped in
this directory. `scripts/build-inputplumber-xbox-hd.sh` reconstructs and builds
that exact source:
https://github.com/ShadowBlip/InputPlumber/tree/bb7424fd6fc097d123850950aaf1e6988f2093f3

Build the corresponding source by checking out the commit above, applying the
patch and running `cargo build --release --bin inputplumber`.
