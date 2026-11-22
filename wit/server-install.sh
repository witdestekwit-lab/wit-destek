#!/bin/bash
# WIT Destek - RustDesk sunucusu (hbbs + hbbr) kurulumu
# Ubuntu 22.04 / 24.04 (amd64) icin. Kullanim:
#   wget -q raw.githubusercontent.com/witdestekwit-lab/wit-destek/master/wit/server-install.sh
#   sudo bash server-install.sh
set -euo pipefail

VERSION="1.1.16"
BASE="https://github.com/rustdesk/rustdesk-server/releases/download/${VERSION}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Bu script root olarak calismali: sudo bash server-install.sh"
  exit 1
fi

echo "== Paketler indiriliyor (RustDesk Server ${VERSION}) =="
TMP=$(mktemp -d)
cd "$TMP"
for p in hbbs hbbr utils; do
  wget -q "${BASE}/rustdesk-server-${p}_${VERSION}_amd64.deb"
done

echo "== Kuruluyor =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ./rustdesk-server-hbbs_${VERSION}_amd64.deb \
                      ./rustdesk-server-hbbr_${VERSION}_amd64.deb \
                      ./rustdesk-server-utils_${VERSION}_amd64.deb

echo "== Guvenlik duvari =="
apt-get install -y -qq ufw
ufw allow 22/tcp comment 'SSH (sadece ofis ici, modemde acmayin)' >/dev/null
ufw allow 21115:21117/tcp comment 'RustDesk' >/dev/null
ufw allow 21116/udp comment 'RustDesk' >/dev/null
ufw --force enable >/dev/null

echo "== Servisler =="
systemctl enable --now rustdesk-hbbs rustdesk-hbbr
sleep 3
systemctl --no-pager --lines=0 status rustdesk-hbbs rustdesk-hbbr | grep -E "rustdesk-|Active:"

KEY_FILE=/var/lib/rustdesk-server/id_ed25519.pub
for i in $(seq 1 10); do [ -s "$KEY_FILE" ] && break; sleep 1; done

echo
echo "=============================================="
echo " WIT Destek sunucusu hazir"
echo " Yerel IP : $(hostname -I | awk '{print $1}')"
echo " KEY      : $(cat "$KEY_FILE")"
echo "=============================================="
echo "Modemde su portlari bu IP'ye yonlendirin:"
echo "  TCP 21115, 21116, 21117  ve  UDP 21116"
rm -rf "$TMP"
