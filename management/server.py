"""Local application catalog. Run with: python management/server.py"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from shared.common import VERSIONS

REGISTRY = ROOT / 'apps.json'
SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
APP_ID = re.compile(r'^A\d{3,}$')


def read_registry(path=REGISTRY):
    with path.open(encoding='utf-8') as file:
        data = json.load(file)
    if not isinstance(data, dict) or not isinstance(data.get('apps'), list) or not isinstance(data.get('next_id'), int):
        raise ValueError('Invalid application registry')
    return data


def write_registry(data, path=REGISTRY):
    # Atomic replacement preserves the previous catalog if writing fails.
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as file:
            name = file.name
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write('\n')
        os.replace(name, path)
    finally:
        if name and os.path.exists(name): os.unlink(name)


def validate_app(data, apps, current_id=None):
    if not isinstance(data, dict): raise ValueError('Invalid data')
    name, slug, description, status = (data.get(k, '') for k in ('name', 'slug', 'description', 'status'))
    if not all(isinstance(v, str) for v in (name, slug, description, status)):
        raise ValueError('Fields must be text')
    name, slug, description = name.strip(), slug.strip(), description.strip()
    if not name or len(name) > 120: raise ValueError('Name must contain 1–120 characters')
    if not SLUG.fullmatch(slug) or len(slug) > 80: raise ValueError('Slug must use lowercase letters, numbers, and hyphens')
    if len(description) > 500: raise ValueError('Description must be 500 characters or fewer')
    if status not in ('active', 'planned', 'archived'): raise ValueError('Invalid status')
    if any(a['slug'] == slug and a['id'] != current_id for a in apps): raise ValueError('Slug is already in use')
    return {'slug': slug, 'name': name, 'description': description, 'status': status}


def create_app(data, path=REGISTRY):
    registry = read_registry(path)
    values = validate_app(data, registry['apps'])
    # IDs are never reused, including archived applications.
    used = {a['id'] for a in registry['apps']}
    number = max(1, registry['next_id'])
    while f'A{number:03d}' in used: number += 1
    app = {'id': f'A{number:03d}', **values}
    registry['next_id'] = number + 1
    registry['apps'].append(app)
    write_registry(registry, path)
    return app


def update_app(app_id, data, path=REGISTRY):
    registry = read_registry(path)
    app = next((a for a in registry['apps'] if a['id'] == app_id), None)
    if app is None: raise KeyError(app_id)
    # A slug is a package/update identity and must not silently change.
    if data.get('slug') != app['slug']: raise ValueError('Slug cannot be changed after creation')
    app.update(validate_app(data, registry['apps'], app_id))
    write_registry(registry, path)
    return app


class Handler(BaseHTTPRequestHandler):
    def allowed_host(self):
        return self.headers.get('Host', '').lower() in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def respond(self, code, body, content_type='application/json; charset=utf-8'):
        if not isinstance(body, bytes): body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code); self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body))); self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if not self.allowed_host(): return self.respond(403, {'error':'Invalid host'})
        route = urlsplit(self.path).path
        if route == '/api/apps':
            try:
                data = read_registry()
                return self.respond(200, {'apps': [{**a, 'version': VERSIONS.get(a['slug'])} for a in data['apps']], 'next_id': data['next_id']})
            except (OSError, ValueError) as exc: return self.respond(500, {'error':str(exc)})
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if route not in files: return self.respond(404, {'error':'Not found'})
        name, content_type = files[route]
        self.respond(200, (ROOT / name).read_bytes(), content_type)

    def do_POST(self): self.change('create')
    def do_PUT(self): self.change('update')

    def change(self, action):
        if not self.allowed_host(): return self.respond(403, {'error':'Invalid host'})
        origin = self.headers.get('Origin', '')
        if origin != f'http://{self.headers.get("Host", "")}': return self.respond(403, {'error':'Invalid origin'})
        if self.headers.get_content_type() != 'application/json': return self.respond(415, {'error':'JSON required'})
        route = urlsplit(self.path).path
        match = re.fullmatch(r'/api/apps/(A\d{3,})', route)
        if (action == 'create' and route != '/api/apps') or (action == 'update' and not match):
            return self.respond(404, {'error':'Not found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > 8192: raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(size))
            result = create_app(data) if action == 'create' else update_app(match.group(1), data)
            self.respond(201 if action == 'create' else 200, result)
        except (ValueError, UnicodeError) as exc: self.respond(400, {'error':str(exc)})
        except KeyError: self.respond(404, {'error':'Application not found'})
        except OSError: self.respond(500, {'error':'Unable to save the registry'})


def main():
    parser = argparse.ArgumentParser(description='Run the local FishFish application catalog')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = HTTPServer(('127.0.0.1', args.port), Handler)
    print(f'FishFish catalog: http://127.0.0.1:{server.server_port}/', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__': main()
