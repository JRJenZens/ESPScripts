"""Fetch public product pages as inert metadata; no scripts, includes or firmware."""
import http.client
import ipaddress
import re
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

MAX_BYTES = 1500000


def public_target(url):
    if not isinstance(url, str) or len(url) > 2000 or re.search(r'[\s\\\x00-\x1f\x7f]', url):
        raise ValueError('Indsæt et gyldigt HTTPS-link til produktsiden.')
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme != 'https' or not host or parts.username or parts.password or parts.port not in (None, 443):
            raise ValueError()
        host = host.encode('idna').decode('ascii')
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(row[4][0] for row in addresses))
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError()
    except (OSError, UnicodeError, ValueError):
        raise ValueError('Brug et offentligt HTTPS-link uden loginoplysninger. Lokale adresser understøttes ikke.') from None
    return parts, host, ips


class PinnedHTTPS(http.client.HTTPSConnection):
    """Keep DNS validation and the actual TLS connection on the same address."""
    def __init__(self, host, address, timeout):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def fetch_page(url):
    deadline = time.monotonic() + 20
    for _ in range(4):
        parts, host, addresses = public_target(url)
        connection = PinnedHTTPS(host, addresses[0], timeout=5)
        try:
            path = quote(urlunsplit(('', '', parts.path or '/', parts.query, '')), safe="/%?=&:@!$'()*+;,-._~")
            connection.request('GET', path, headers={'User-Agent': 'ESPScripts/0.3 (+https://github.com/JRJenZens/ESPScripts)', 'Accept': 'text/html', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('Siden viderestiller uden et gyldigt link.')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError('Produktsiden kunne ikke hentes (HTTP %s). Tilføj modellen manuelt, eller prøv et andet dokumentationslink.' % response.status)
            if response.getheader('Content-Encoding', 'identity').lower() not in ('identity', ''):
                raise ValueError('Siden sender et format, som ikke understøttes. Prøv et andet dokumentationslink.')
            if response.headers.get_content_type() not in ('text/html', 'application/xhtml+xml'):
                raise ValueError('Linket skal åbne en HTML-produktside, ikke en fil eller PDF.')
            chunks, size = [], 0
            while True:
                if time.monotonic() > deadline:
                    raise ValueError('Produktsiden svarede for langsomt. Prøv igen eller tilføj modellen manuelt.')
                chunk = response.read(min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError('Produktsiden er for stor. Prøv et mere direkte dokumentationslink.')
            charset = response.headers.get_content_charset() or 'utf-8'
            try:
                html = b''.join(chunks).decode(charset, errors='replace')
            except LookupError:
                html = b''.join(chunks).decode('utf-8', errors='replace')
            return urlunsplit(('https', parts.netloc, parts.path or '/', parts.query, '')), html
        except (OSError, http.client.HTTPException):
            raise ValueError('Linket kunne ikke hentes. Kontrollér adressen, eller opret modellen manuelt.') from None
        finally:
            connection.close()
    raise ValueError('Produktsiden viderestiller for mange gange.')


class ProductPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.h1, self.main = [], [], []
        self.meta = {}
        self.stack = []
        self.h1_done = False
        self.h1_depth = None
        self.main_size = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            key = (attrs.get('property') or attrs.get('name') or '').lower()
            self.meta.setdefault(key, attrs.get('content', ''))
        if tag in ('meta', 'link', 'img', 'input', 'br', 'hr', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track', 'col'):
            return
        if len(self.stack) >= 200:
            raise ValueError('HTML har for mange indlejrede niveauer.')
        self.stack.append(tag)
        if tag == 'h1' and not self.h1_done:
            self.h1_depth = len(self.stack)

    def handle_endtag(self, tag):
        if tag == 'h1' and self.h1_depth is not None:
            self.h1_done = True
            self.h1_depth = None
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack) - 1 - self.stack[::-1].index(tag)]

    def handle_data(self, text):
        if any(t in self.stack for t in ('script', 'style', 'nav', 'aside', 'footer', 'header', 'noscript')):
            return
        if 'title' in self.stack:
            self.title.append(text)
        if self.h1_depth is not None:
            self.h1.append(text)
        if ('article' in self.stack or 'main' in self.stack) and self.main_size < 30000:
            self.main.append(text[:30000 - self.main_size])
            self.main_size += len(self.main[-1])


def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def draft_from_html(url, html, catalog):
    page = ProductPage()
    try:
        page.feed(html)
    except (ValueError, RecursionError):
        raise ValueError('Siden kunne ikke læses. Tilføj modellen manuelt.') from None
    title = clean(' '.join(page.h1) or page.meta.get('og:title') or ' '.join(page.title))
    title = re.split(r'\s+[|]\s+', title)[0]
    title = re.sub(r'^(getting started (?:with\s+)?|introduction to\s+)', '', title, flags=re.I)
    title = clean(title.replace(',', ' · '))[:200]
    if not title or title.lower() in ('just a moment...', 'access denied', 'page not found', '403 forbidden', '404 not found'):
        raise ValueError('Der blev ikke fundet en produkttitel. Siden kan kræve JavaScript eller blokere import. Opret modellen manuelt.')
    intro = clean(' '.join(page.main))[:4000]
    description = clean(page.meta.get('description') or page.meta.get('og:description') or '')[:400]
    heading = title.lower()
    context = (title + ' ' + description + ' ' + intro[:1500]).lower()
    chip_match = re.search(r'\besp32[ -]?(c61|c[2356]|s[23]|h2|p4)\b', heading)
    variant = 'esp32' + chip_match.group(1) if chip_match else ('esp32' if re.search(r'\besp32\b', heading) else '')
    expansion = bool(re.search(r'expansion board|extension board|shield', heading + ' ' + description + ' ' + intro[:800]))
    sensor = bool(re.search(r'sensor|mmwave|radar|temperature|humidity|accelerometer', heading))
    hardware_type = 'expansion' if expansion else ('sensor' if sensor else ('esp32' if variant else 'other'))
    kind = 'sensors' if hardware_type == 'sensor' else 'boards'
    buses = [label for pattern, label in ((r'\bi[²2]c\b', 'I2C'), (r'\buart\b|serial port', 'UART'), (r'\bspi\b', 'SPI'), (r'one.wire', 'ONE_WIRE')) if re.search(pattern, context)]
    category = variant.upper().replace('ESP32', 'ESP32-').rstrip('-') if hardware_type == 'esp32' else (' / '.join(buses) if buses else ('Udvidelsesboard' if expansion else 'Ukendt'))
    detail, esphome = '', {}
    existing = None
    for item_kind in ('boards', 'sensors'):
        for item in catalog[item_kind]:
            same_url = item.get('docs_url', '').rstrip('/').lower() == url.rstrip('/').lower()
            compact = lambda value: re.sub(r'[^a-z0-9]', '', value.lower()).replace('seeedstudio', 'seeed')
            same_name = compact(item['name']) == compact(title)
            if same_url or same_name:
                existing = dict(id=item['id'], kind=item_kind, name=item['name'])
                # Use board IDs only from a known catalog match; do not guess from a product title.
                detail = item.get('detail', '')
                esphome = item.get('esphome', {}) if hardware_type == 'esp32' else {}
                break
        if existing:
            break
    draft = dict(name=title, kind=kind, hardware_type=hardware_type, category=category, detail=detail, docs_url=url, description=description, esphome=esphome)
    return dict(draft=draft, existing=existing, notice='Forslag ud fra sidens titel og tekst. Kontrollér type og oplysninger før du gemmer. ESPHome-kompatibilitet og fysisk test er ikke bekræftet.')
