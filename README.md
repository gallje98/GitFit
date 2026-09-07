# GitFit

Flask-Webapp zur Registrierung, Anmeldung und Verwaltung von Events.

## Funktionen

- Registrierung und Login für Benutzer
- Anzeige zukünftiger Events mit freien Plätzen
- Ein Event pro Benutzer nur einmal buchen
- Eigene Event-Anmeldungen wieder löschen
- Verwaltung von Benutzern, Abos, Zahlungen und Events im Adminbereich
- Geschützte Admin-API für offene Zahlungen und Eventdaten

## Projektstruktur

```text
app.py          Flask-Anwendung und Routen
schema.sql      Datenbankschema für MariaDB
templates/      HTML-Seiten der Webanwendung
static/         CSS-Dateien und Bilder
```

## Starten

```bash
pip install -r requirements.txt
python app.py
```

### Umgebungsvariablen

Die Anwendung benötigt eine MariaDB. Die Zugangsdaten und Schlüssel werden über eine `.env`-Datei gesetzt:

```env
SECRET_KEY=ein-langer-geheimer-wert
ADMIN_API_KEY=ein-geheimer-api-schluessel
DB_USER=benutzer
DB_PASSWORD=passwort
DB_HOST=localhost
DB_NAME=gitfit
```

### Datenbank einrichten

Nach dem Erstellen der Datenbank wird das aktuelle Schema einmalig ausgeführt:

```bash
mariadb -u root -p gitfit < schema.sql
```

Das Datenmodell verwendet die Tabellen `users`, `events` und `event_bookings`.

## Benutzerablauf

Ein Benutzer registriert sich, meldet sich an und sieht im Dashboard die zukünftigen Events. Bei einer Buchung wird geprüft, ob das Event noch freie Plätze hat und ob der Benutzer bereits angemeldet ist. Eigene Event-Anmeldungen können anschliessend wieder gelöscht werden.


### Admin-Zugriff

Administratoren können im Browser unter `/admin` Benutzer, Events und ausstehende Zahlungen verwalten. Für externe Clients stehen die geschützten Endpunkte `GET /api/admin/users/pending-payments` und `GET /api/admin/events` zur Verfügung.

Die Berechtigung wird ausschliesslich über das Feld `is_admin` in der Datenbank vergeben. Es gibt keine Weboberfläche zum Erstellen oder Ändern von Admin-Benutzern. Für neue Installationen kann ein Benutzer nach der Registrierung direkt in MariaDB zum Admin gemacht werden:

```sql
UPDATE users
SET is_admin = TRUE
WHERE email = 'admin@beispiel.ch';
```

Bei einer bestehenden Datenbank muss die neue Spalte einmalig ergänzt werden:

```sql
ALTER TABLE users
ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE;
```

Für `/admin` ist eine normale Browser-Anmeldung erforderlich. Für die API-Endpunkte muss der statische API-Key als `X-API-Key`-Header übergeben werden.

## API-Schnittstelle

Die API stellt zwei geschützte Admin-Abfragen bereit. Der statische API-Key wird nur auf dem Server in der `.env`-Datei gespeichert und muss im Header übergeben werden:

### `GET /api/admin/users/pending-payments`

Ruft alle Benutzer ab, deren Zahlungsstatus noch ausstehend ist. Die Antwort enthält unter anderem Benutzername, E-Mail-Adresse, Abotyp sowie Beginn und Ende des Abonnements.

```bash
curl https://lab11.ifalabs.org/api/admin/users/pending-payments -H "X-API-Key: <ADMIN_API_KEY>"
```

### `GET /api/admin/events`

Ruft alle Events mit Datum, maximaler Teilnehmerzahl und aktueller Belegung ab. Zusätzlich werden die zugehörigen Buchungen inklusive Benutzername, E-Mail-Adresse und Buchungszeitpunkt ausgegeben.

```bash
curl https://lab11.ifalabs.org/api/admin/events -H "X-API-Key: <ADMIN_API_KEY>"
```

<<<<<<< HEAD
Nur Anfragen mit dem korrekten API-Key können diese Endpunkte verwenden. Der Key läuft nicht automatisch ab und kann durch Änderung der `.env`-Variable ersetzt werden. 
=======
Nur Anfragen mit dem korrekten API-Key können diese Endpunkte verwenden. Der Key läuft nicht automatisch ab und kann durch Änderung der `.env`-Variable ersetzt werden. 
>>>>>>> 047241a (Veraltete Bookings entfernen und Dokumentation erweitert)
