"""Local browser QA only: npm run build; python test/serve-fixtures.py.

Open http://127.0.0.1:5175/mmwave-component/?scenario=mixed
Scenarios: mixed, alpha, corrupt, error, empty. No flashable binaries are served.
"""
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DIST = Path(__file__).resolve().parents[1] / 'dist'
PREFIX = '/mmwave-component/'


def manifest(version):
    return json.dumps({'name': 'QA ONLY - DO NOT FLASH', 'version': version,
                      'builds': [{'chipFamily': 'ESP32-C3', 'parts': [{'path': 'NOT-A-FIRMWARE.bin', 'offset': 0}]}]}).encode()


def release(channel, suffix):
    version = f'v0.0.0-{channel}.{suffix}'
    binary = 'v0.0.0-alpha.1' if channel == 'beta' else version
    return {'id': version, 'version': version, 'binaryVersion': binary, 'channel': channel,
            'sourceCommit': 'a' * 40, 'publishedAt': f'2026-10-{suffix + 10:02d}T00:00:00Z',
            'firmware': [{'radarId': 'r60abd1', 'chipFamily': 'ESP32-C3', 'boardIds': ['esp32-c3-supermini'],
                          'manifest': f'firmware/{version}/r60abd1-ESP32-C3/manifest.json',
                          'manifestSha256': sha256(manifest(binary)).hexdigest()}]}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def reply(self, content, mime='application/json', status=200):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(urlparse(self.headers.get('Referer', '')).query)
        scenario = query.get('scenario', ['mixed'])[0]
        if parsed.path == PREFIX + 'releases.json':
            if scenario == 'error':
                return self.reply(b'{}', status=503)
            versions = [] if scenario == 'empty' else [release('alpha', 2)]
            if scenario != 'alpha' and versions:
                versions.append(release('beta', 1))
            if scenario == 'corrupt':
                for version in versions: version['firmware'][0]['manifestSha256'] = '0' * 64
            return self.reply(json.dumps({'schemaVersion': 1, 'releases': versions}).encode())
        if parsed.path.startswith(PREFIX + 'firmware/'):
            if parsed.path.endswith('/manifest.json'):
                version = parsed.path.split('/')[3]
                return self.reply(manifest('v0.0.0-alpha.1' if '-beta.' in version else version))
            return self.reply(b'QA ONLY: firmware binaries are deliberately unavailable.', status=404)
        if parsed.path == PREFIX:
            html = (DIST / 'index.html').read_text(encoding='utf-8')
            html = html.replace('<body>', '<body><div style="background:#fef08a;color:#422006;padding:8px;text-align:center">QA FIXTURE · No real firmware · Do not connect hardware</div>')
            return self.reply(html.encode(), 'text/html; charset=utf-8')
        if not parsed.path.startswith(PREFIX):
            return self.reply(b'Use /mmwave-component/?scenario=mixed', status=404)
        self.path = '/' + parsed.path.removeprefix(PREFIX)
        return super().do_GET()


if __name__ == '__main__':
    if not (DIST / 'index.html').exists():
        raise SystemExit('Run npm run build first')
    print('QA only: http://127.0.0.1:5175/mmwave-component/?scenario=mixed', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 5175), Handler).serve_forever()
