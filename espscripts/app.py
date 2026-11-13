"""ESPScripts: local, revisioned ESPHome library. Never executes YAML."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import yaml
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

WEB = Path(__file__).resolve().parent / 'web'
app = Flask(__name__, static_folder=str(WEB), static_url_path='/static')
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
app.config['DB'] = os.environ.get('ESPSCRIPTS_DB', '/data/espscripts.sqlite3')


@contextmanager
def connect():
    path = Path(app.config['DB'])
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, version INTEGER NOT NULL, document TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS revisions (entry_id TEXT NOT NULL, version INTEGER NOT NULL, document TEXT NOT NULL, PRIMARY KEY(entry_id, version))')
    db.commit()
    try:
        with db:
            yield db
    finally:
        db.close()


class ESPHomeLoader(yaml.SafeLoader):
    pass


def tagged(loader, suffix, node):
    # Keep !secret, !lambda, !include etc. as data; never open files or run code.
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


ESPHomeLoader.add_multi_constructor('!', tagged)


def validate_document(data):
    if not isinstance(data, dict):
        raise ValueError('Opsætningen skal være et objekt.')
    result = {}
    for key in ('name', 'description', 'board', 'sensors', 'wiring', 'notes', 'yaml', 'tested_on', 'esphome_version', 'change_note'):
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > (500000 if key == 'yaml' else 20000):
            raise ValueError(f'Ugyldig værdi i {key}.')
        result[key] = value.strip() if key != 'yaml' else value
    if not result['name'] or not result['yaml'].strip():
        raise ValueError('Navn og YAML skal udfyldes.')
    result['kind'] = data.get('kind', 'block')
    result['status'] = data.get('status', 'untested')
    if result['kind'] not in ('block', 'complete') or result['status'] not in ('untested', 'tested', 'issues'):
        raise ValueError('Ugyldig type eller teststatus.')
    if result['status'] == 'tested' and not result['tested_on']:
        raise ValueError('Angiv hvad opsætningen er testet på, og gerne dato.')
    tags = data.get('tags', [])
    if not isinstance(tags, list) or len(tags) > 50 or any(not isinstance(t, str) or len(t) > 100 for t in tags):
        raise ValueError('Tags skal være en liste af korte tekster.')
    result['tags'] = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
    if result['yaml'].count('\n') > 10000:
        raise ValueError('YAML er for lang.')
    try:
        # Reject aliases to avoid recursive structures and alias expansion attacks.
        for token in yaml.scan(result['yaml']):
            if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)):
                raise ValueError('YAML-ankre og aliaser understøttes ikke i denne version.')
        parsed = yaml.load(result['yaml'], Loader=ESPHomeLoader)
        if not isinstance(parsed, dict):
            raise ValueError('YAML skal indeholde nøgler som sensor:, esphome: eller packages:.')
    except yaml.YAMLError as exc:
        mark = getattr(exc, 'problem_mark', None)
        location = f' ved linje {mark.line + 1}' if mark else ''
        raise ValueError('YAML-syntaksfejl' + location + '. Kontrollér indrykningen.') from None
    except RecursionError:
        raise ValueError('YAML har for mange indlejrede niveauer.') from None
    return result


@app.before_request
def protect():
    if os.environ.get('ESPSCRIPTS_LOCAL') != '1' and request.remote_addr != '172.30.32.2':
        return jsonify(error='Adgang kun gennem Home Assistant Ingress.'), 403
    if request.method in ('POST', 'PUT', 'DELETE') and request.headers.get('X-ESPScripts') != '1':
        return jsonify(error='Manglende forespørgselssikring.'), 403


@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'self'"
    return response


@app.errorhandler(ValueError)
def bad_input(exc):
    return jsonify(error=str(exc)), 400


@app.errorhandler(HTTPException)
def http_error(exc):
    return jsonify(error=exc.description), exc.code


@app.get('/')
def index():
    return send_from_directory(WEB, 'index.html')


@app.get('/api/entries')
def listing():
    with connect() as db:
        entries = [json.loads(row['document']) for row in db.execute('SELECT document FROM entries')]
    return jsonify(sorted(entries, key=lambda e: e['name'].casefold()))


def persist(db, data, entry_id=None, expected=None, historical=False):
    doc = validate_document(data)
    now = datetime.now(timezone.utc).isoformat()
    if entry_id:
        row = db.execute('SELECT * FROM entries WHERE id=?', (entry_id,)).fetchone()
        if not row:
            from werkzeug.exceptions import NotFound
            raise NotFound('Opsætningen findes ikke.')
        if expected != row['version']:
            from werkzeug.exceptions import Conflict
            raise Conflict('En anden har ændret opsætningen. Genindlæs før du gemmer.')
        old = json.loads(row['document'])
        version, created = row['version'] + 1, old['created_at']
    else:
        entry_id, version, created = str(uuid4()), 1, now
    if historical:
        for field in ('created_at', 'updated_at'):
            if not isinstance(data.get(field), str):
                raise ValueError('Backup mangler versionsdatoer.')
            try:
                datetime.fromisoformat(data[field])
            except ValueError:
                raise ValueError('Ugyldig versionsdato i backup.') from None
        created, now = data['created_at'], data['updated_at']
    doc.update(id=entry_id, version=version, created_at=created, updated_at=now)
    encoded = json.dumps(doc, ensure_ascii=False)
    db.execute('INSERT OR REPLACE INTO entries VALUES (?,?,?)', (entry_id, version, encoded))
    db.execute('INSERT INTO revisions VALUES (?,?,?)', (entry_id, version, encoded))
    return doc


@app.post('/api/entries')
def create():
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        doc = persist(db, request.get_json())
    return jsonify(doc), 201


@app.put('/api/entries/<entry_id>')
def update(entry_id):
    data = request.get_json()
    if not isinstance(data, dict):
        raise ValueError('Ugyldigt indhold.')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        doc = persist(db, data, entry_id, data.get('version'))
    return jsonify(doc)


@app.get('/api/entries/<entry_id>/history')
def history(entry_id):
    with connect() as db:
        rows = db.execute('SELECT document FROM revisions WHERE entry_id=? ORDER BY version DESC', (entry_id,)).fetchall()
    return jsonify([json.loads(row['document']) for row in rows])


@app.get('/api/backup')
def backup():
    with connect() as db:
        entries = [json.loads(r['document']) for r in db.execute('SELECT document FROM entries')]
        revisions = [json.loads(r['document']) for r in db.execute('SELECT document FROM revisions')]
    response = jsonify(format='espscripts', schema=1, entries=entries, revisions=revisions)
    response.headers['Content-Disposition'] = 'attachment; filename="espscripts-backup.json"'
    return response


@app.post('/api/import')
def import_backup():
    data = request.get_json()
    if not isinstance(data, dict) or data.get('format') != 'espscripts' or data.get('schema') != 1:
        raise ValueError('Filen er ikke en ESPScripts-backup.')
    entries, revisions = data.get('entries'), data.get('revisions')
    if not isinstance(entries, list) or not isinstance(revisions, list) or len(entries) > 1000 or len(revisions) > 20000:
        raise ValueError('Ugyldig eller for stor backup.')
    # Import as copies with fresh identities, preserving history; never overwrite.
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or entry['id'] in seen:
                raise ValueError('Backup indeholder ugyldige eller gentagne ID’er.')
            seen.add(entry['id'])
            past = [r for r in revisions if isinstance(r, dict) and r.get('id') == entry['id']]
            if not past or any(type(r.get('version')) is not int for r in past):
                raise ValueError('Ugyldig versionshistorik.')
            past.sort(key=lambda r: r['version'])
            if [r['version'] for r in past] != list(range(1, len(past) + 1)) or past[-1] != entry:
                raise ValueError('Versionshistorikken er ufuldstændig.')
            current = None
            for old in past:
                current = persist(db, old, current['id'] if current else None, current['version'] if current else None, historical=True)
    return jsonify(imported=len(entries)), 201


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8099)
