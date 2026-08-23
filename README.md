# HiveDash

Ein selbst gebautes, minimalistisches Homepage/Homarr-artiges Dashboard, das sich
**automatisch** um Dienste erweitert:

- **Nginx Proxy Manager**: alle konfigurierten Proxy-Hosts werden per API abgefragt
  und als klickbare Kacheln (mit Domain, online/offline-Status) angezeigt.
- **Proxmox VE**: alle VMs und LXC-Container werden per API abgefragt (Name, Status,
  CPU/RAM). Wo möglich wird ein Proxmox-Gast automatisch einem NPM-Proxy-Host
  zugeordnet (per IP-Abgleich) und als eine gemeinsame Kachel mit Live-Stats
  dargestellt. Alles, was sich nicht eindeutig zuordnen lässt, wird trotzdem
  angezeigt (als reiner Link bzw. als reine Infrastruktur-Kachel) - nichts wird
  stillschweigend unterschlagen.

Kein manuelles YAML pro Dienst nötig: Ein neuer Proxy-Host in NPM oder eine neue
VM/LXC in Proxmox taucht nach dem nächsten Poll-Intervall automatisch auf.

Mehrbenutzerfähig: jeder Login sieht standardmäßig dasselbe (automatisch gepflegte)
Standard-Dashboard, ein Admin kann aber zusätzliche Dashboards anlegen und darauf
Sichtbarkeit/Reihenfolge/Anzeigename einzelner Dienste pro Dashboard anpassen - und
einzelnen Nutzern eines davon zuweisen.

Jeder Dienst bekommt außerdem automatisch ein Logo zugeordnet, sobald eines mit
passendem Stichwort in der Logo-Bibliothek hinterlegt ist (`/admin/logos`) - entweder
selbst hochgeladen oder gezielt aus dem offenen Icon-Katalog
[dashboard-icons](https://github.com/homarr-labs/dashboard-icons) importiert. Eine
manuelle Korrektur pro Dienst ist im Dashboard-Editor jederzeit möglich.

## Funktionsweise

Ein FastAPI-Backend pollt beide APIs unabhängig voneinander im Hintergrund - NPM alle
`NPM_POLL_INTERVAL_SECONDS` (Default: 60s, ändert sich selten), Proxmox alle
`PROXMOX_POLL_INTERVAL_SECONDS` (Default: 5s, für zeitnahe CPU/RAM-Werte) - und schreibt
das Ergebnis in eine SQLite-Datenbank (statt nur in den Prozessspeicher) - ein Neustart
des Containers verliert also keine Daten, und ein kurzzeitiger NPM/Proxmox-Ausfall lässt
die zuletzt bekannten Dienste weiter sichtbar (nur die Fehlermeldung ändert sich). Das
Frontend ist eine Angular-SPA (gestylt mit [Tabler](https://github.com/tabler/tabler)):
sobald ein Poll durchgelaufen ist, schiebt das Backend die aktualisierten Daten per
WebSocket (`/api/ws/dashboard`) direkt an alle offenen Dashboards - kein Warten auf den
nächsten Reload. Ein regelmäßiger HTTP-Fallback-Check bleibt bestehen, falls die
WebSocket-Verbindung (z. B. durch einen Proxy ohne Upgrade-Unterstützung) nicht zustande
kommt. Login/Session/Admin-Verwaltung laufen über dieselbe FastAPI-API.

### Login

- **Lokal**: E-Mail/Passwort, von einem Admin angelegt (siehe `POST /api/admin/users`
  bzw. die Admin-Oberfläche unter `/admin/users`). Es gibt bewusst keine
  Selbstregistrierung.
- **OIDC/SSO** (optional): gegen einen beliebigen OIDC-Provider (z. B. eine eigene
  Authentik-Instanz) - siehe `OIDC_*`/`PUBLIC_BASE_URL` in `.env.example`. Der erste
  Login überhaupt (egal ob lokal oder per OIDC) wird automatisch Admin, damit es nie
  zu einem "keiner kann sich mehr einloggen"-Zustand kommen kann.

### Zuordnungslogik (NPM ↔ Proxmox)

Der `forward_host` eines NPM-Proxy-Hosts wird mit den bekannten IP-Adressen aller
laufenden Proxmox-Gäste verglichen:

- **QEMU-VMs**: IP kommt vom `qemu-guest-agent` - der muss in der VM installiert
  und aktiv sein, sonst bleibt die IP unbekannt und es gibt keine Zuordnung
  (der Dienst wird trotzdem ganz normal als Link angezeigt).
- **LXC-Container**: IP kommt vom Proxmox-Interfaces-Endpunkt, funktioniert ohne
  Zusatz-Software.
- Zeigt `forward_host` direkt auf eine IP, die zu einem Docker-Container *innerhalb*
  einer VM/eines LXC gehört (typisches Setup), matcht das trotzdem auf den
  VM/LXC-Host, da dessen IP identisch mit der des Docker-Host-Netzwerks ist -
  bei `network_mode: host` oder Makvlan-Setups funktioniert das gut, bei
  Docker-Bridge-Networking mit eigener Container-IP nicht (dann bleibt der
  Dienst unzugeordnet, aber sichtbar).

## Setup

### 1. Zugangsdaten anlegen (mit minimalen Rechten)

**Nginx Proxy Manager**: Users -> Add User, eigener Nutzer nur für dieses
Dashboard. Unter "Permissions" beim neuen User "Proxy Hosts" (und die anderen
Bereiche, die du nicht brauchst) auf **View Only** statt Manage stellen - dann
kann der Dashboard-Nutzer nichts an eurer Konfiguration ändern, nur lesen.

**Proxmox VE**: Datacenter -> Permissions -> API Tokens -> Add.
- User z. B. `root@pam` (oder besser: einen eigenen, unprivilegierten User anlegen)
- Token-ID z. B. `dashboard`
- "Privilege Separation" **aktiviert** lassen
- danach unter Datacenter -> Permissions -> Add -> API Token Permission:
  Path `/`, Token `user@realm!dashboard`, Role `PVEAuditor` (rein lesend) hinzufügen

Damit hat das Dashboard nur Lesezugriff auf Proxmox.

### 2. Konfigurieren

```bash
cp .env.example .env
# .env mit deinen echten Werten befüllen
```

Zusätzlich zu NPM/Proxmox unbedingt ausfüllen:
- `COOKIE_SECRET`: zufälliger String, z. B.
  `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
- `BOOTSTRAP_ADMIN_EMAIL`/`BOOTSTRAP_ADMIN_PASSWORD`: legt beim allerersten Start
  (wenn noch kein Nutzer existiert) diesen Admin-Account an. Weitere Nutzer danach
  über die Admin-Oberfläche (`/admin/users`) anlegen.
- `PUBLIC_BASE_URL`: die von außen erreichbare URL des Dashboards (auch ohne OIDC
  sinnvoll zu setzen). Nur nötig für OIDC: `OIDC_ISSUER`/`OIDC_CLIENT_ID`/
  `OIDC_CLIENT_SECRET` - sonst alle drei leer lassen, dann bleibt SSO deaktiviert.

### 3. Starten

```bash
docker compose up -d --build
```

Dashboard ist danach unter `http://<server>:8080` erreichbar.

### 4. Testen

```bash
curl http://localhost:8080/api/health
curl http://localhost:8080/api/dashboard | jq .
```

Bei Problemen: `docker compose logs -f` - NPM- und Proxmox-Fehler landen dort
verständlich (z. B. 401 bei falschem Passwort/Token) und werden zusätzlich unten
auf der Dashboard-Seite selbst als Fehlertext eingeblendet, statt die Seite leer
zu lassen.

## Grenzen / bewusste Vereinfachungen

- Der Katalog-Import unter `/admin/logos` braucht Internetzugriff *nur in dem Moment*,
  in dem ein Admin aktiv sucht/importiert - Polling und laufender Betrieb sind davon
  komplett unabhängig und funktionieren auch offline.
- Es werden nur NPM **Proxy Hosts** ausgelesen, keine Redirection Hosts oder
  Streams - lässt sich in `app/clients/npm.py` ergänzen, falls gewünscht.
- Die NPM-Poll-Frequenz ist bewusst niedrig (60s) gehalten, um NPM nicht unnötig zu
  belasten; Proxmox pollt standardmäßig alle 5s für zeitnahe CPU/RAM-Werte. Beides über
  `NPM_POLL_INTERVAL_SECONDS`/`PROXMOX_POLL_INTERVAL_SECONDS` anpassbar.
- Kein Self-Service-Passwort-Reset (kein SMTP im Projekt) - ein Admin muss ein neues
  Passwort über `/admin/users` setzen.
- Nur ein OIDC-Provider gleichzeitig konfigurierbar (Schema erlaubt mehrere, es fehlt
  nur die Konfigurationsoberfläche dafür).
