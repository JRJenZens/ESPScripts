import io
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch
from email.message import Message

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'espscripts'))
import link_import
import test_app as base
module = base.module


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.catalog = module.BUILTIN_CATALOG

    def test_product_heading_not_sidebar_determines_chip(self):
        html = '<title>Getting started</title><nav>ESP32S3 ESP32C5</nav><main><article><h1>Getting Started with Seeed Studio XIAO ESP32C3</h1><p>An ESP32-C3 development board with UART.</p></article></main>'
        result = link_import.draft_from_html('https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/', html, self.catalog)
        self.assertEqual(result['draft']['hardware_type'], 'esp32')
        self.assertEqual(result['draft']['category'], 'ESP32-C3')
        self.assertEqual(result['draft']['esphome']['board'], 'seeed_xiao_esp32c3')
        self.assertIsNotNone(result['existing'])

    def test_expansion_board_does_not_inherit_host_chip(self):
        html = '<nav>XIAO ESP32C3</nav><main><h1>24GHz mmWave for XIAO</h1><p>A presence sensor expansion board for XIAO. Interface: UART.</p></main>'
        result = link_import.draft_from_html('https://wiki.seeedstudio.com/mmwave_for_xiao/', html, self.catalog)['draft']
        self.assertEqual(result['kind'], 'boards')
        self.assertEqual(result['hardware_type'], 'expansion')
        self.assertEqual(result['esphome'], {})
        self.assertEqual(result['detail'], '')
        self.assertEqual(result['category'], 'UART')

    def test_sensor_unknown_and_no_script_execution(self):
        html = '<script>throw new Error("executed")</script><h1>Special Temperature Sensor</h1><main>Uses I2C.</main>'
        sensor = link_import.draft_from_html('https://example.com/sensor', html, self.catalog)['draft']
        self.assertEqual(sensor['kind'], 'sensors')
        self.assertEqual(sensor['category'], 'I2C')
        self.assertEqual(sensor['detail'], '')
        unknown = link_import.draft_from_html('https://example.com/', '<meta property="og:title" content="My Custom Gadget">', self.catalog)['draft']
        self.assertEqual(unknown['hardware_type'], 'other')
        with self.assertRaises(ValueError):
            link_import.draft_from_html('https://example.com/', '<html></html>', self.catalog)


class NetworkTests(unittest.TestCase):
    def test_invalid_urls_never_reach_network(self):
        for value in (None, '', 'http://example.com/', 'file:///etc/passwd', 'https://user:pw@example.com/', 'https://example.com:8123/', 'https://example.com/\r\nHost:x', 'https://example.com\\@localhost'):
            with self.subTest(value=value), patch.object(socket, 'getaddrinfo') as dns:
                with self.assertRaises(ValueError):
                    link_import.public_target(value)
                dns.assert_not_called()

    def test_local_and_mixed_dns_are_blocked(self):
        for addresses in (['127.0.0.1'], ['192.168.1.2'], ['172.30.32.2'], ['169.254.169.254'], ['::1'], ['::ffff:127.0.0.1'], ['93.184.215.14', '10.0.0.2']):
            with self.subTest(addresses=addresses), patch.object(socket, 'getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in addresses]):
                with self.assertRaises(ValueError):
                    link_import.public_target('https://example.com/')

    def test_redirect_to_private_is_not_followed(self):
        class Response:
            status = 302
            def getheader(self, name):
                return 'https://127.0.0.1/private'
        class Connection:
            def __init__(self, *args, **kwargs): pass
            def request(self, *args, **kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass
        def target(url):
            if '127.0.0.1' in url:
                raise ValueError('private')
            from urllib.parse import urlsplit
            return urlsplit(url), 'example.com', ['93.184.215.14']
        with patch.object(link_import, 'public_target', side_effect=target), patch.object(link_import, 'PinnedHTTPS', Connection):
            with self.assertRaisesRegex(ValueError, 'private'):
                link_import.fetch_page('https://example.com/')

    def test_connection_uses_validated_ip_and_original_tls_hostname(self):
        with patch.object(link_import.ssl, 'create_default_context') as context, patch.object(socket, 'create_connection') as create:
            connection = link_import.PinnedHTTPS('example.com', '93.184.215.14', 5)
            connection.connect()
            create.assert_called_once_with(('93.184.215.14', 443), 5)
            context.return_value.wrap_socket.assert_called_once_with(create.return_value, server_hostname='example.com')

    def test_response_size_and_content_type_limits(self):
        class Connection:
            def __init__(self, *args, **kwargs): pass
            def request(self, *args, **kwargs): pass
            def getresponse(self): return response
            def close(self): pass
        class Response(io.BytesIO):
            status = 200
            def getheader(self, name, default=None): return default
        from urllib.parse import urlsplit
        for content_type, payload in [('text/html', b'x' * (link_import.MAX_BYTES + 1)), ('application/pdf', b'%PDF-1.0')]:
            response = Response(payload)
            response.headers = Message()
            response.headers['Content-Type'] = content_type
            with patch.object(link_import, 'public_target', return_value=(urlsplit('https://example.com'), 'example.com', ['93.184.215.14'])), patch.object(link_import, 'PinnedHTTPS', Connection):
                with self.assertRaises(ValueError):
                    link_import.fetch_page('https://example.com')


class LinkAPITests(unittest.TestCase):
    setUp = base.LibraryTests.setUp
    tearDown = base.LibraryTests.tearDown
    req = base.LibraryTests.req

    def test_preview_requires_save_and_metadata_survives_backup(self):
        url = 'https://example.com/c3'
        html = '<main><h1>My ESP32-C3 board</h1></main>'
        with patch.object(module, 'fetch_page', return_value=(url, html)):
            response = self.req('catalog/preview-link', 'POST', {'url': url})
        self.assertEqual(response.status_code, 200)
        draft = response.get_json()['draft']
        self.assertFalse(any(x['custom'] for x in self.req('catalog').get_json()['boards']))
        added = self.req('catalog', 'POST', draft)
        self.assertEqual(added.status_code, 201)
        self.assertEqual(added.get_json()['hardware_type'], 'esp32')
        self.assertEqual(self.req('backup').get_json()['catalog'][0]['docs_url'], url)
        self.assertEqual(self.req('catalog', 'POST', dict(draft, name='Bad', esphome={'script': 'anything'})).status_code, 400)
        with patch.object(module, 'fetch_page', side_effect=ValueError('Kunne ikke hente siden.')):
            self.assertEqual(self.req('catalog/preview-link', 'POST', {'url': url}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
