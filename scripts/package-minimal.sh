#!/bin/sh
# Assemble a small glibc runtime from the already working Debian runtime.
set -eu
root=${1:?Usage: package-minimal.sh absolute-output-directory}
case "$root" in /*) ;; *) echo 'Output directory must be absolute' >&2; exit 2 ;; esac
[ ! -e "$root" ] || { echo 'Use a fresh output directory' >&2; exit 2; }
mkdir -p "$root/usr/local/bin" "$root/usr/share" "$root/opt" "$root/etc" "$root/tmp" "$root/work"
chmod 1777 "$root/tmp"
cp -a /usr/local/bin/curlimp "$root/usr/local/bin/"
mkdir -p "$root/usr/local/share/zsh/site-functions"
cp /usr/local/share/zsh/site-functions/_curlimp "$root/usr/local/share/zsh/site-functions/"
cp -a /opt/native "$root/opt/"
cp /runtime-refresh.txt "$root/opt/native/runtime-refresh.txt"
# Resolve only our own executable. ldd includes transitive shared libraries
# and the architecture-specific ELF loader; missing libraries fail packaging.
ldd /usr/local/bin/curlimp > "$root/opt/native/runtime-libraries.txt"
if grep -q 'not found' "$root/opt/native/runtime-libraries.txt"; then
  echo 'Unresolved runtime library' >&2
  exit 1
fi
awk '$2 == "=>" && $3 ~ /^\// {print $3} $1 ~ /^\// {print $1}' "$root/opt/native/runtime-libraries.txt" |
while read -r library; do
  case "$library" in /opt/native/*) continue ;; esac
  mkdir -p "$root$(dirname -- "$library")"
  cp -L "$library" "$root$library"
done
# Keep the CA bundle and hashed certificate directory, including link targets.
cp -a /etc/ssl "$root/etc/"
cp -a /usr/share/ca-certificates "$root/usr/share/"
cp -a /etc/nsswitch.conf "$root/etc/"
# Preserve licenses for the application, engine, libc, GCC runtime, and CAs.
cp -a /usr/share/licenses "$root/usr/share/"
cp -a /usr/share/common-licenses "$root/usr/share/"
for package in libc6 libgcc-s1 libstdc++6 gcc-12-base ca-certificates; do
  mkdir -p "$root/usr/share/doc/$package"
  cp -L "/usr/share/doc/$package/copyright" "$root/usr/share/doc/$package/"
done
dpkg-query -W -f='${binary:Package} ${Version}\n' libc6 libgcc-s1 libstdc++6 gcc-12-base ca-certificates > "$root/opt/native/runtime-packages.txt"
# Verify the actual assembled filesystem, with no fallback to host libraries.
chroot "$root" /usr/local/bin/curlimp --version
chroot "$root" /usr/local/bin/curlimp --list-profiles > /dev/null
