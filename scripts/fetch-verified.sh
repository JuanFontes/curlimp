#!/bin/sh
set -eu
url=${1:?Usage: fetch-verified.sh https-url sha256 destination}
checksum=${2:?Missing SHA-256}
destination=${3:?Missing destination}
case "$url" in https://*) ;; *) echo 'Only HTTPS source URLs are supported' >&2; exit 2 ;; esac
case "$checksum" in ''|*[!0-9a-f]*) echo 'Invalid SHA-256' >&2; exit 2 ;; esac
test "${#checksum}" -eq 64 || { echo 'Invalid SHA-256 length' >&2; exit 2; }

verify() {
  if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$1")
  else
    actual=$(shasum -a 256 "$1")
  fi
  actual=${actual%% *}
  if [ "$actual" != "$checksum" ]; then
    echo "SHA-256 mismatch: $1" >&2
    return 1
  fi
}

if [ -e "$destination" ]; then
  # Never silently replace a corrupt cached source with different bytes.
  verify "$destination"
  exit 0
fi
mkdir -p "$(dirname "$destination")"
temporary=$(mktemp "$destination.tmp.XXXXXX")
trap 'rm -f "$temporary"' EXIT HUP INT TERM
curl --fail --location --silent --show-error --retry 2 --connect-timeout 15 --max-time 180 \
  --proto '=https' --proto-redir '=https' --tlsv1.2 "$url" -o "$temporary"
verify "$temporary"
mv "$temporary" "$destination"
