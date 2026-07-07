#!/usr/bin/env bash
# Build a fully static, dependency-free ryzenadj for x86_64 Linux and drop it at
# <outdir>/ryzenadj (default: bin/ryzenadj) next to its LGPL license text.
#
# RyzenAdj links libpci through pkg-config, so we build a static libpci with every
# optional feature off (no zlib/hwdb/kmod/dns/shared) and point pkg-config at it.
# The result links -static and needs no host libraries, so it runs on SteamOS and
# Bazzite alike.
#
# Runnable off-CI: expects cmake, pkg-config, make, a C compiler, curl and tar on PATH.
set -euo pipefail

RYZENADJ_TAG="${RYZENADJ_TAG:-v0.19.0}"
PCIUTILS_TAG="${PCIUTILS_TAG:-v3.13.0}"
outdir="${1:-bin}"

for tool in cmake pkg-config make cc curl tar; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing required tool: $tool" >&2; exit 1; }
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
prefix="$work/pci"

pci_opts=(ZLIB=no HWDB=no LIBKMOD=no DNS=no SHARED=no)

# Static libpci. PREFIX is baked into libpci.pc when the .pc is generated (at build
# time), so it MUST match on both the build and install invocations. Passing it only
# to install-lib leaves the already-generated .pc pointing at /usr/local, which breaks
# both the compile (-I) and the static link (-L) against our staging copy.
curl -fsSL "https://github.com/pciutils/pciutils/archive/refs/tags/${PCIUTILS_TAG}.tar.gz" | tar xz -C "$work"
pci="$work/pciutils-${PCIUTILS_TAG#v}"
make -C "$pci" -j"$(nproc)" PREFIX="$prefix" "${pci_opts[@]}" lib/libpci.a
make -C "$pci" PREFIX="$prefix" "${pci_opts[@]}" install-lib

# pkg-config (and CMake's pkg_check_modules) read PKG_CONFIG_PATH from the environment.
export PKG_CONFIG_PATH="$prefix/lib/pkgconfig"
pkg-config --exists libpci || { echo "libpci.pc not found under $PKG_CONFIG_PATH" >&2; exit 1; }
pkgflags="$(pkg-config --static --cflags --libs libpci)"
echo "resolved libpci flags: $pkgflags"
# Guard against the stale-prefix failure above: the resolved paths must live inside the
# staging prefix, never /usr/local (which would silently fail to link against our libpci.a).
case "$pkgflags" in
  *"$prefix"*) : ;;
  *) echo "libpci.pc does not point at the staging prefix ($prefix)" >&2; exit 1 ;;
esac

# Build the CLI. PREFER_STATIC_LINKING adds -static and selects the static libpci target;
# BUILD_SHARED_LIBS=OFF keeps libryzenadj static too so nothing wants a libpci.so.
curl -fsSL "https://github.com/FlyGoat/RyzenAdj/archive/refs/tags/${RYZENADJ_TAG}.tar.gz" | tar xz -C "$work"
ryz="$work/RyzenAdj-${RYZENADJ_TAG#v}"
cmake -S "$ryz" -B "$ryz/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DPREFER_STATIC_LINKING=ON \
  -DBUILD_SHARED_LIBS=OFF
cmake --build "$ryz/build" -j"$(nproc)"

mkdir -p "$outdir"
cp "$ryz/build/ryzenadj" "$outdir/ryzenadj"
chmod +x "$outdir/ryzenadj"

# LGPL-3.0 requires the license text to ship with the binary.
for lic in LICENSE LICENSE.txt COPYING COPYING.LESSER; do
  if [ -f "$ryz/$lic" ]; then cp "$ryz/$lic" "$outdir/ryzenadj-LICENSE.txt"; break; fi
done
test -f "$outdir/ryzenadj-LICENSE.txt"

echo "built $outdir/ryzenadj ($RYZENADJ_TAG) with static libpci ($PCIUTILS_TAG)"
