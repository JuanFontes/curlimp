#!/bin/sh
# Build the vendored, verified superbuild and collect its native output.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$script_dir/../engine.lock"
workspace=${1:?Usage: build-engine.sh absolute-workspace absolute-prefix [jobs]}
prefix=${2:?Missing installation prefix}
jobs=${3:-4}
case "$workspace:$prefix" in /*:/*) ;; *) echo 'Build paths must be absolute' >&2; exit 2 ;; esac
case "$jobs" in ''|*[!0-9]*|0) echo 'jobs must be a positive integer' >&2; exit 2 ;; esac
if [ -e "$prefix" ]; then
  echo 'Use a fresh installation prefix for the native build' >&2
  exit 2
fi
upstream="$workspace/upstream"
build="$workspace/build"
idn_archive="$build/deps/downloads/libidn2-$LIBIDN2_VERSION.tar.gz"
sh "$script_dir/prepare-engine.sh" "$script_dir/../vendor/curl-impersonate" "$upstream" "$ENGINE_VENDOR_SHA256"
# Prepopulate the exact archive consumed by the upstream IDN helper. Both
# mirrors must match the same fixed digest; a failed verification stops build.
if ! sh "$script_dir/fetch-verified.sh" "$LIBIDN2_SOURCE_URL" "$LIBIDN2_SOURCE_SHA256" "$idn_archive"; then
  sh "$script_dir/fetch-verified.sh" "$LIBIDN2_SOURCE_MIRROR" "$LIBIDN2_SOURCE_SHA256" "$idn_archive"
fi
cd "$upstream"
make prepare-libidn2 BUILD_DIR="$build" JOBS="$jobs" LIBIDN2_VERSION="$LIBIDN2_VERSION"
# Run one dependency build at a time; each may use jobs workers. This avoids
# multiplying the outer and inner parallelism and exhausting small builders.
configure_args="-DCMAKE_INSTALL_PREFIX=$prefix -DSUBJOBS=$jobs -DCURL_IMPERSONATE_VERSION=$ENGINE_VERSION -DCURL_CA_PATH=/etc/ssl/certs -DCURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt"
make build BUILD_DIR="$build" JOBS=1 CMAKE_CONFIGURE_ARGS="$configure_args"
make checkbuild BUILD_DIR="$build"
make install-strip BUILD_DIR="$build" JOBS=1 CMAKE_CONFIGURE_ARGS="$configure_args"
cmake -P "$build/CollectLicenses.cmake"
cp "$build"/licenses/LICENSE* "$prefix/"
cp ORIGIN.md "$prefix/engine-origin.md"
cp SHA256SUMS "$prefix/engine-inputs.sha256"
cat > "$prefix/engine-build.txt" <<EOF
build_kind=source
engine_version=$ENGINE_VERSION
engine_revision=$ENGINE_REVISION
engine_source=vendored
engine_vendor_sha256=$ENGINE_VENDOR_SHA256
libidn2_version=$LIBIDN2_VERSION
libidn2_source_sha256=$LIBIDN2_SOURCE_SHA256
architecture=$(uname -m)
EOF
# Keep the exact dependency versions/hashes and applied patch digests available
# alongside the artifact, without relying on future state of an upstream tag.
sed -n '/^set(.*_VERSION /p; /^set(.*_COMMIT /p; /^set(.*_URL_HASH /p' CMakeLists.txt >> "$prefix/engine-build.txt"
sha256sum patches/*.patch >> "$prefix/engine-build.txt"
test -f "$prefix/include/curl/curl.h"
test -f "$prefix/lib/libcurl-impersonate.so"
echo "Source engine built and checked: $ENGINE_REVISION"
