#!/usr/bin/env bash
# Build a fully static dropbearmulti (dropbear + dropbearkey) for Linux and drop it at
# <outdir>/dropbear-<arch> next to its MIT license text. Cross-compiles with `zig cc`
# against musl so one host can produce every architecture.
#
# Usage: build-dropbear.sh <x86_64|aarch64> [outdir]
set -euo pipefail
trap 'echo "build-dropbear: failed at line $LINENO: $BASH_COMMAND" >&2' ERR

DROPBEAR_VERSION="${DROPBEAR_VERSION:-2026.94}"
DROPBEAR_SHA256="${DROPBEAR_SHA256:-e098034a843699200c8c977a991fff73159735bf795d5f72ef672c41a6b1ae81}"
arch="${1:?usage: build-dropbear.sh <x86_64|aarch64> [outdir]}"
outdir="${2:-bin}"

case "$arch" in
  x86_64|aarch64) ;;
  *) echo "unsupported arch: $arch" >&2; exit 1 ;;
esac
for tool in zig make curl tar shasum; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing required tool: $tool" >&2; exit 1; }
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
tarball="$work/dropbear.tar.bz2"
curl -fsSL "https://matt.ucc.asn.au/dropbear/releases/dropbear-${DROPBEAR_VERSION}.tar.bz2" -o "$tarball"
echo "${DROPBEAR_SHA256}  $tarball" | shasum -a 256 -c -
tar xjf "$tarball" -C "$work"
src="$work/dropbear-${DROPBEAR_VERSION}"

# Key-only server. Re-exec stays off because it relies on fexecve, which proot cannot emulate;
# multi-user stays on because the non-multiuser build refuses to run on a normal kernel.
cat > "$src/localoptions.h" <<'OPTS'
#define DROPBEAR_REEXEC 0
#define DROPBEAR_SVR_PASSWORD_AUTH 0
#define DROPBEAR_SVR_PAM_AUTH 0
#define DROPBEAR_SVR_AGENTFWD 0
#define DROPBEAR_CLI_AGENTFWD 0
#define DROPBEAR_X11FWD 0
#define DROPBEAR_SFTPSERVER 0
#define DROPBEAR_RSA 0
#define DEFAULT_PATH "/usr/local/bin:/usr/bin:/bin"
#define DEFAULT_ROOT_PATH "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
OPTS

cd "$src"
CC="zig cc -target ${arch}-linux-musl" CFLAGS="-Os" LDFLAGS="-s" AR="zig ar" RANLIB="zig ranlib" \
  ./configure --host="${arch}-linux-musl" --enable-static --disable-zlib \
  --disable-lastlog --disable-utmp --disable-utmpx --disable-wtmp --disable-wtmpx \
  --disable-pututline --disable-pututxline >/dev/null
make -j"$(getconf _NPROCESSORS_ONLN)" PROGRAMS="dropbear dropbearkey" MULTI=1 STATIC=1 >/dev/null

mkdir -p "$outdir"
cp dropbearmulti "$outdir/dropbear-${arch}"
chmod +x "$outdir/dropbear-${arch}"
cp LICENSE "$outdir/dropbear-LICENSE"
