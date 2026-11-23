#!/bin/bash
# WIT Destek rapor sayfasi kurulumu (RustDesk sunucusunda, root olarak).
# Konsoldan:  wget -q raw.githubusercontent.com/witdestekwit-lab/wit-destek/master/wit/report-install.sh
#             sudo bash report-install.sh
set -e
BASE="https://raw.githubusercontent.com/witdestekwit-lab/wit-destek/master/wit"
mkdir -p /opt/wit-report /var/lib/wit-report

curl -fsSL "$BASE/report.py" -o /opt/wit-report/report.py
chmod 755 /opt/wit-report/report.py

cat > /etc/systemd/system/wit-report.service <<'EOF'
[Unit]
Description=WIT Destek rapor sayfasini uret
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/wit-report/report.py
EOF

cat > /etc/systemd/system/wit-report.timer <<'EOF'
[Unit]
Description=WIT Destek raporu 15 dakikada bir

[Timer]
OnBootSec=1min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/wit-report-web.service <<'EOF'
[Unit]
Description=WIT Destek rapor web sayfasi (8080)
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 -m http.server 8080 --directory /var/lib/wit-report
DynamicUser=yes
ReadOnlyPaths=/var/lib/wit-report
NoNewPrivileges=yes
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 8080 sadece ofis aglari ve VPN'den
for net in 192.168.2.0/24 10.10.58.0/24 10.250.250.0/24; do
  ufw allow from "$net" to any port 8080 proto tcp comment 'WIT rapor' >/dev/null
done

systemctl daemon-reload
/usr/bin/python3 /opt/wit-report/report.py || true
systemctl enable --now wit-report.timer wit-report-web.service
sleep 1
systemctl --no-pager --lines=0 status wit-report-web.service | head -3
ls -la /var/lib/wit-report/
echo
echo "RAPOR KURULDU: http://$(hostname -I | awk '{print $1}'):8080"
