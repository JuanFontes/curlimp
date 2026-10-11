#!/bin/sh
# Keep this launcher with its runtime directory; symlinks to it are supported.
set -eu
fail() { printf 'curlimp: %s\n' "$1" >&2; exit 2; }
[ "$(uname -s)" = Linux ] || fail 'This package requires Linux.'
case "$(uname -m)" in
  @MACHINE@) ;;
  *) fail 'This package requires @ARCH@; download the matching architecture.' ;;
esac
launcher=$(readlink -f -- "$0") || fail 'Cannot resolve the launcher path.'
bundle=$(dirname -- "$launcher")
case "$bundle" in *:*|*';'*) fail 'The package path cannot contain a colon or semicolon.' ;; esac
runtime=$bundle/runtime
# Respect explicit trust settings; CLI --cacert still takes precedence.
if [ -z "${CURL_CA_BUNDLE:-}${SSL_CERT_FILE:-}" ]; then
  CURL_CA_BUNDLE=$runtime/etc/ssl/certs/ca-certificates.crt
  export CURL_CA_BUNDLE
fi
exec "$runtime/@LOADER@" \
  --library-path "$runtime/opt/native/lib:$runtime/@LIBDIR@" \
  "$runtime/usr/local/bin/curlimp" "$@"
