import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('espscripts', Path(__file__).resolve().parents[1] / 'espscripts/app.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        module.app.config.update(TESTING=True, DB=str(Path(self.tmp.name) / 'library.sqlite3'))
        self.client = module.app.test_client()
        self.headers = {'X-ESPScripts': '1'}
        self.env = {'REMOTE_ADDR': '172.30.32.2'}
        self.doc = dict(name='C5 temperatur', board='ESP32-C5', sensors='BME280', kind='block', status='untested', yaml='sensor:\n  - platform: bme280_i2c\n    address: 0x76\nwifi:\n  ssid: !secret wifi_ssid\n', tags=['I2C'])

    def tearDown(self):
        self.tmp.cleanup()

    def req(self, path, method='GET', data=None):
        return self.client.open('/api/' + path, method=method, json=data, headers=self.headers, environ_overrides=self.env)

    def test_revision_restore_and_concurrent_edits(self):
        original = self.req('entries', 'POST', self.doc).get_json()
        change = dict(original, yaml='sensor:\n  - platform: bh1750\n', status='tested', tested_on='ESP32-C5, 2026-11-13')
        changed = self.req('entries/' + original['id'], 'PUT', change)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.req('entries/' + original['id'], 'PUT', change).status_code, 409)
        restored = self.req('entries/' + original['id'], 'PUT', dict(original, version=2, change_note='Gendannet version 1')).get_json()
        self.assertEqual(restored['version'], 3)
        history = self.req('entries/' + original['id'] + '/history').get_json()
        self.assertEqual([d['version'] for d in history], [3, 2, 1])
        self.assertEqual(history[-1]['yaml'], self.doc['yaml'])
        self.assertEqual(self.req('entries').get_json()[0]['yaml'], self.doc['yaml'])

    def test_backup_roundtrip_and_atomic_failure(self):
        original = self.req('entries', 'POST', self.doc).get_json()
        self.req('entries/' + original['id'], 'PUT', dict(original, notes='Revideret'))
        backup = self.req('backup').get_json()
        self.assertEqual(self.req('import', 'POST', backup).status_code, 201)
        items = self.req('entries').get_json()
        self.assertEqual(len(items), 2)
        self.assertEqual(len({item['id'] for item in items}), 2)
        for item in items:
            self.assertEqual(item['updated_at'], backup['entries'][0]['updated_at'])
            self.assertEqual(len(self.req('entries/' + item['id'] + '/history').get_json()), 2)
        broken = dict(backup, entries=backup['entries'] + [dict(backup['entries'][0], id='broken')])
        self.assertEqual(self.req('import', 'POST', broken).status_code, 400)
        self.assertEqual(len(self.req('entries').get_json()), 2)

    def test_bad_yaml_and_test_status(self):
        for invalid in ('sensor: [', '- just-a-list', 'a: &a [*a]', '!!python/object/apply:os.system [touch /tmp/should-not-exist]'):
            response = self.req('entries', 'POST', dict(self.doc, yaml=invalid))
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.req('entries', 'POST', dict(self.doc, status='tested')).status_code, 400)
        self.assertEqual(self.req('entries', 'POST', dict(self.doc, yaml='esphome:\n  on_boot: !lambda |-\n    return;\n')).status_code, 201)

    def test_ingress_and_mutation_protection(self):
        self.assertEqual(self.client.get('/api/entries').status_code, 403)
        self.assertEqual(self.client.post('/api/entries', json=self.doc, environ_overrides=self.env).status_code, 403)
        for path in ('/', '/static/app.js'):
            with self.client.get(path, environ_overrides=self.env) as response:
                self.assertEqual(response.status_code, 200)
        self.assertEqual(self.req('entries/' + 'missing', 'PUT', dict(self.doc, version=1)).status_code, 404)

    def test_exact_yaml_and_restart(self):
        text = '# Kommentar\nsensor:\n  - platform: bh1750\n    name: "Lys"\n'
        self.req('entries', 'POST', dict(self.doc, yaml=text))
        module.app.test_client()  # New client reads durable SQLite, not in-memory data.
        self.assertEqual(self.req('entries').get_json()[0]['yaml'], text)


if __name__ == '__main__':
    unittest.main()
