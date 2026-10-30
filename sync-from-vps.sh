#!/bin/sh
# Holt die Live-Dateien vom VPS ins Repo und bricht bei Secrets ab.
set -e
cd "$(dirname "$0")"
mkdir -p server/systemd server/nginx server/cron diag
cp /opt/vita-tunein/adapter.py                        server/adapter.py
cp /etc/systemd/system/vita-tunein.service            server/systemd/
cp /root/npm/data/nginx/custom/vita-tunein.conf       server/nginx/
cp /etc/cron.d/vita-certs                             server/cron/
[ -f /etc/dnsmasq.d/vita-tunein.conf ] && cp /etc/dnsmasq.d/vita-tunein.conf diag/dnsmasq-vita-tunein.conf || true
if grep -rInE 'BEGIN [A-Z ]*PRIVATE KEY|password=[A-Za-z0-9!$%._-]{3,}|api[_-]?key *=' server diag; then
  echo "ABBRUCH: moegliche Secrets gefunden" >&2; exit 1
fi
echo "Sync ok"
