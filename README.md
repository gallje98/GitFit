# GitFit

Kleine Flask-Webapp zur Registrierung, Anmeldung und Verwaltung von Trainingsbuchungen.

## Starten

```bash
pip install -r requirements.txt
python app.py
```

Benötigt eine MySQL-Datenbank. Die Zugangsdaten und Schlüssel werden über eine `.env`-Datei gesetzt (`DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_NAME`, `SECRET_KEY`, `JWT_SECRET_KEY`). Die Tabellen stehen in `schema.sql`.
