#!/bin/sh
# Verify and stage the engine build inputs stored in this repository.
set -eu
source_dir=${1:?Usage: prepare-engine.sh source-directory destination manifest-sha256}
destination=${2:?Missing destination}
expected=${3:?Missing manifest SHA-256}
case "$expected" in ''|*[!0-9a-f]*) echo 'Invalid manifest SHA-256' >&2; exit 2 ;; esac
[ "${#expected}" -eq 64 ] || { echo 'Invalid manifest SHA-256 length' >&2; exit 2; }
source_dir=$(CDPATH= cd -- "$source_dir" && pwd)
sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi
}
verify() (
  cd "$1"
  actual=$(sha256 SHA256SUMS)
  [ "${actual%% *}" = "$expected" ] || { echo 'Engine manifest checksum mismatch' >&2; exit 1; }
  sha256 -c SHA256SUMS
  if [ "${2:-}" = strict ]; then
    expected_files=$({ printf './SHA256SUMS\n'; awk '{print "./" $2}' SHA256SUMS; } | LC_ALL=C sort)
    actual_files=$(find . \( -type f -o -type l \) -print | LC_ALL=C sort)
    [ "$actual_files" = "$expected_files" ] || { echo 'Unlisted engine build input' >&2; exit 1; }
  fi
)
verify "$source_dir"
if [ -e "$destination" ]; then
  verify "$destination" strict
  exit 0
fi
mkdir -p "$(dirname -- "$destination")"
staging=$(mktemp -d "$destination.tmp.XXXXXX")
trap 'rm -rf "$staging"' EXIT HUP INT TERM
# Copy only pinned inputs, preserving the executable mode of build helpers.
while read -r digest name; do
  mkdir -p "$staging/$(dirname -- "$name")"
  cp -p "$source_dir/$name" "$staging/$name"
done < "$source_dir/SHA256SUMS"
cp -p "$source_dir/SHA256SUMS" "$staging/SHA256SUMS"
verify "$staging" strict
mv "$staging" "$destination"
trap - EXIT HUP INT TERM
