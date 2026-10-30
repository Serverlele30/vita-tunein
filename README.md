# PS-Vita-TuneIn – Wiederbelebung der offiziellen App

Offizielle TuneIn-Radio-App für die PS Vita (**PCSB00407**, WayForward 2013, unverändert aus PKGj).
Läuft wieder: Startseite, Kategorien, Login, Favoriten, Wiedergabe.

## Aufbau
- **Domain:** `tin.serverlele.de` (RSA-Zertifikat `tin-rsa`, nginx-Block `server/nginx/vita-tunein.conf`)
- **Adapter:** `server/adapter.py` auf `127.0.0.1:8445`, Dienst `vita-tunein.service`
- **Vita:** `ux0:app/TLSF00001/redirects.txt` (tls_fixer):
opml.radiotime.com tin.serverlele.de home.wayforward.com tin.serverlele.de
- **HTTP-Hosts** (`opml.radiotime.com`, `feed.tunein.com`, `feed.radiotime.com`) laufen derzeit noch über
  DNS-Umleitung (`diag/dnsmasq-vita-tunein.conf`); Ziel: taiHEN-Plugin, das die Hosts im Speicher patcht.

## Gefundene Ursachen
1. **Endlos-Laden beim Start:** TuneIn/Cloudflare antwortet mit `Transfer-Encoding: chunked`; der
   HTTP-Client der App kann das nicht → `OPML: Retry`. Adapter liefert mit `Content-Length`.
2. **Login stürzt ab:** `Account.ashx` läuft per HTTPS → tls_fixer-Umleitung auf `tin.serverlele.de`.
3. **Wiedergabe lädt endlos:** `Tune.ashx` liefert HTTPS-URLs mit 302-Weiterleitung. Adapter schreibt
   sie auf `http://tin.serverlele.de/stream?u=<base64>` um (MP3 zuerst) und reicht den Stream mit
   ICY-Kopfzeilen durch.
4. **songlookup-Spam:** Vita schickt Umlaute roh in der URL; fehlender `title` in der Antwort führt zu
   Endlos-Wiederholung. Adapter kodiert den Pfad neu, füllt `title` auf und cacht 10 min.
5. `home.wayforward.com/esportadb/mysql_to_csv.php` (Debug-Upload des Entwicklers) wird mit leerem 200 beantwortet.

## App-Interna
- Oberfläche: Scaleform-SWF `flash/TuneInVita.swf`; Netzwerk + OPML-Parser nativ im eboot.
- Partner-ID der App: `764nxqij`. Endpunkte: `Config.ashx`, `Browse.ashx?c=feed[&id=…&ItemCount=…]`,
  `Tune.ashx`, `Search.ashx`, `Preset.ashx`, `Describe.ashx`, `songlookup.ashx`, `Account.ashx` (HTTPS).

## Betrieb
- Logs: `journalctl -u vita-tunein -f`, `docker exec npm-npm-1 tail -f /data/logs/vita-tunein_access.log`
- Zertifikate: `/etc/cron.d/vita-certs` (ttv/ytv/tin, täglich 04:17, Log `/var/log/vita-certs.log`)
- Repo aktualisieren: `./sync-from-vps.sh && git add -A && git commit -m "…" && git push`
