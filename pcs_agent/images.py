"""Bounded local AUTOMATIC1111 API adapter. Never installs or launches services."""
import base64
import json
from pathlib import Path
import urllib.request
import urllib.error
import uuid
from urllib.parse import urlsplit


def local_url(value):
    if not isinstance(value, str):
        raise ValueError('Image server address must be text.')
    u = urlsplit(value)
    if (u.scheme != 'http' or u.hostname not in {'127.0.0.1', '::1'} or u.username
            or u.password or u.query or u.fragment or u.path not in {'', '/'}):
        raise ValueError('Image server must use a literal loopback HTTP address, without credentials or a path.')
    _ = u.port
    return value.rstrip('/')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Image service redirects are not allowed.')


def request(config, path, payload=None):
    url = local_url(config.get('image_url', 'http://127.0.0.1:7860')) + path
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data, {'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=min(config['model_timeout'], config['task_timeout'])) as response:
            raw = response.read(12_000_001)
        if len(raw) > 12_000_000:
            raise ValueError('Image response exceeds 12 MB.')
        return json.loads(raw)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError('Local image API unavailable or timed out. Start AUTOMATIC1111 with --api and a loaded model. No retry was sent; generation may still be running. Detail: ' + str(exc)) from exc


def image_task(command, config, emit, metrics):
    if config.get('_member_mode'):
        raise PermissionError('Local image generation is administrator-only.')
    metrics['route'] = 'local image API'
    status = command.strip().casefold() == '/image-status'
    prompt = command.strip()[len('/image'):].strip()
    if not status and not prompt:
        raise ValueError('Use /image followed by a description.')
    emit({'kind': 'log', 'stage': True, 'text': 'Checking local image API.' if status else 'Requesting one local image. Cancelling Strident may not stop the external generator.'})
    metrics['tool_calls'] += 1
    if status:
        data = request(config, '/sdapi/v1/sd-models')
        if not isinstance(data, list):
            raise ValueError('Unexpected image API model-list response.')
        titles = [str(m.get('title', '')) for m in data if isinstance(m, dict)]
        reply = 'Image API reachable. Available models: ' + (', '.join(titles) or 'none') + '. Image generation has not been tested.'
        result = {'ok': bool(titles), 'summary': reply}
    else:
        root = Path(config['workspace']).resolve()
        folder = root / 'Generated'
        if folder.is_symlink() or folder.is_junction() or (folder.exists() and not folder.is_dir()):
            raise ValueError('Generated must be a real workspace directory.')
        folder.mkdir(parents=True, exist_ok=True)
        data = request(config, '/sdapi/v1/txt2img', {'prompt': prompt, 'steps': 20, 'width': 512,
                       'height': 512, 'batch_size': 1, 'n_iter': 1, 'send_images': True, 'save_images': False})
        images = data.get('images') if isinstance(data, dict) else None
        if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], str):
            raise ValueError('Image API must return exactly one base64 image.')
        encoded = images[0]
        if encoded.startswith('data:image/png;base64,'):
            encoded = encoded.split(',', 1)[1]
        raw = base64.b64decode(encoded, validate=True)
        if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw) > 8_000_000:
            raise ValueError('Expected a PNG image no larger than 8 MB; no file saved.')
        if folder.is_symlink() or folder.is_junction() or folder.resolve().parent != root:
            raise ValueError('Generated directory changed during the request.')
        path = folder / ('image-' + uuid.uuid4().hex + '.png')
        with path.open('xb') as stream:
            stream.write(raw)
        reply = 'Image saved locally: ' + str(path)
        result = {'ok': True, 'summary': reply, 'path': str(path), 'bytes': len(raw)}
    emit({'kind': 'tool', 'name': 'local_image', 'result': result})
    return {'status': 'complete' if result['ok'] else 'needs_attention', 'summary': reply,
            'reply': reply, 'evidence': [{'tool': 'local_image', **result}]}
