import importlib.util
import os
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'espscripts'))
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

    def test_standardprint_template_and_reuse(self):
        template = (module.WEB / 'standardprint.yaml').read_text()
        standard = self.req('entries', 'POST', dict(self.doc, name='Mit standardprint', kind='standard', yaml=template))
        self.assertEqual(standard.status_code, 201)
        values = dict(device_name='esp32-019', friendly_name='ESP32-019', secret_prefix='esp32_019', variant='esp32c3', flash_size='4MB')
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace('{{' + key + '}}', value)
        parsed = module.yaml.load(rendered, Loader=module.ESPHomeLoader)
        self.assertEqual(parsed['substitutions']['device_name'], 'esp32-019')
        self.assertEqual(parsed['substitutions']['wg_private_key'], 'esp32_019_wg_secret')
        self.assertEqual(parsed['packages']['base'], 'common/base.yaml')
        self.assertEqual(parsed['esp32']['variant'], 'esp32c3')
        self.assertEqual(self.req('entries', 'POST', dict(self.doc, kind='complete', yaml=rendered)).status_code, 201)

    def test_exact_yaml_and_restart(self):
        text = '# Kommentar\nsensor:\n  - platform: bh1750\n    name: "Lys"\n'
        self.req('entries', 'POST', dict(self.doc, yaml=text))
        module.app.test_client()  # New client reads durable SQLite, not in-memory data.
        self.assertEqual(self.req('entries').get_json()[0]['yaml'], text)


class CatalogTests(unittest.TestCase):
    setUp = LibraryTests.setUp
    tearDown = LibraryTests.tearDown
    req = LibraryTests.req

    def test_catalog_and_custom_models(self):
        initial = self.req('catalog').get_json()
        self.assertGreater(len(initial['boards']), 200)
        self.assertGreaterEqual(len(initial['sensors']), 200)
        self.assertTrue(any('c5' in b['id'] for b in initial['boards']))
        item = dict(kind='boards', name='Mit C5-board', category='ESP32-C5', detail='esp32-c5-devkitc-1', docs_url='https://esphome.io/components/esp32/')
        added = self.req('catalog', 'POST', item)
        self.assertEqual(added.status_code, 201)
        doc = added.get_json()
        self.assertTrue(doc['custom'])
        self.assertEqual(self.req('catalog', 'POST', item).status_code, 409)
        self.assertEqual(self.req('catalog/' + doc['id'], 'PUT', dict(doc, detail='Opdateret')).status_code, 200)
        self.assertEqual(self.req('catalog/' + doc['id'], 'PUT', doc).status_code, 409)
        self.assertEqual(self.req('catalog/' + initial['boards'][0]['id'], 'PUT', item).status_code, 404)
        self.assertEqual(len(self.req('catalog').get_json()['boards']), len(initial['boards']) + 1)

    def test_custom_backup_and_legacy_import(self):
        self.req('entries', 'POST', self.doc)
        item = dict(kind='sensors', name='Min temperatursensor', category='I2C', detail='sensor.custom', docs_url='')
        self.req('catalog', 'POST', item)
        backup = self.req('backup').get_json()
        self.assertEqual(backup['schema'], 2)
        self.assertEqual(len(backup['catalog']), 1)
        other_db = str(Path(self.tmp.name) / 'restored.sqlite3')
        module.app.config['DB'] = other_db
        self.assertEqual(self.req('import', 'POST', backup).status_code, 201)
        custom = [x for x in self.req('catalog').get_json()['sensors'] if x['custom']]
        self.assertEqual(custom[0]['name'], item['name'])
        self.assertEqual(self.req('import', 'POST', backup).status_code, 201)
        self.assertEqual(len([x for x in self.req('catalog').get_json()['sensors'] if x['custom']]), 1)
        self.assertEqual(self.req('import', 'POST', dict(backup, schema=1)).status_code, 201)

    def test_catalog_input_is_data(self):
        for url in ('javascript:alert(1)', 'http://example.com', 'https://user:password@example.com'):
            self.assertEqual(self.req('catalog', 'POST', dict(kind='sensors', name='Test', docs_url=url)).status_code, 400)
        self.assertEqual(self.req('catalog', 'POST', dict(kind='unknown', name='Test')).status_code, 400)
        self.assertEqual(self.req('catalog', 'POST', dict(kind='sensors', name='A, B')).status_code, 400)
        item = dict(kind='sensors', name='<script>test</script>', category='', detail='', docs_url='')
        self.assertEqual(self.req('catalog', 'POST', item).status_code, 201)
        self.assertEqual([s for s in self.req('catalog').get_json()['sensors'] if s['custom']][0]['name'], item['name'])

if __name__ == '__main__':
    unittest.main()
