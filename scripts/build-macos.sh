#!/bin/sh
# Build the native Apple Silicon engine and Rust CLI from verified inputs.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(dirname -- "$script_dir")
. "$repo/engine.lock"
workspace=${1:?Usage: build-macos.sh absolute-workspace [jobs] [--engine-only]}
jobs=${2:-4}
mode=${3:-full}
case "$mode" in full|--engine-only) ;; *) echo 'Unknown build mode' >&2; exit 2 ;; esac
[ "$(uname -s)/$(uname -m)" = Darwin/arm64 ] || { echo 'Native macOS arm64 is required' >&2; exit 2; }
case "$workspace" in /*) ;; *) echo 'Workspace must be absolute' >&2; exit 2 ;; esac
case "$workspace" in *,*) echo 'Build workspace cannot contain a comma' >&2; exit 2 ;; esac
case "$jobs" in ''|*[!0-9]*|0) echo 'jobs must be a positive integer' >&2; exit 2 ;; esac
for tool in cmake ninja clang cargo rustc go perl patch make; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Required build tool not found: $tool" >&2; exit 2; }
done
prefix="$workspace/native"
build="$workspace/build"
upstream="$workspace/upstream"
[ ! -e "$prefix" ] || { echo 'Use a fresh native installation prefix' >&2; exit 2; }
export MACOSX_DEPLOYMENT_TARGET=${MACOSX_DEPLOYMENT_TARGET:-13.0}
sh "$script_dir/prepare-engine.sh" "$repo/vendor/engine" "$upstream" "$ENGINE_VENDOR_SHA256"
cmake -S "$upstream" -B "$build" \
  "-DCMAKE_INSTALL_PREFIX=$prefix" "-DCMAKE_OSX_DEPLOYMENT_TARGET=$MACOSX_DEPLOYMENT_TARGET" \
  -DUSE_LIBIDN2=OFF "-DCURL_IMPERSONATE_VERSION=$ENGINE_VERSION" \
  -DCURL_CA_BUNDLE=/etc/ssl/cert.pem -DCURL_CA_PATH=none "-DSUBJOBS=$jobs"
cmake --build "$build" --parallel 1
make -C "$upstream" checkbuild BUILD_DIR="$build"
cmake --install "$build" --strip
cmake -P "$build/CollectLicenses.cmake"
cp "$build"/licenses/LICENSE* "$prefix/"
cp "$upstream/ORIGIN.md" "$prefix/engine-origin.md"
cp "$upstream/SHA256SUMS" "$prefix/engine-inputs.sha256"
cat > "$prefix/engine-build.txt" <<EOF
build_kind=source
engine_version=$ENGINE_VERSION
engine_revision=$ENGINE_REVISION
engine_source=vendored
engine_vendor_sha256=$ENGINE_VENDOR_SHA256
platform=macos
architecture=arm64
macos_deployment_target=$MACOSX_DEPLOYMENT_TARGET
idn_backend=AppleIDN
EOF
(
  cd "$upstream"
  sed -n '/^set(.*_VERSION /p; /^set(.*_COMMIT /p; /^set(.*_URL_HASH /p' CMakeLists.txt
  shasum -a 256 patches/*.patch
) >> "$prefix/engine-build.txt"
test -f "$prefix/include/curl/curl.h"
test -f "$prefix/lib/libcurl-impersonate.dylib"
[ "$mode" != --engine-only ] || exit 0
cd "$repo"
CURL_IMPERSONATE_DIR="$prefix" CARGO_TARGET_DIR="$workspace/target" cargo build --release --locked
printf 'rustc_version=%s\n' "$(rustc --version)" >> "$prefix/engine-build.txt"
printf 'Native CLI: %s/target/release/curlimp\n' "$workspace"
