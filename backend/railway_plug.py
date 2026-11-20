"""Home Assistant-backed upstream railway plug; never conflated with track power."""
import json
import os
import re
import tempfile
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix='/api/railway-plug', tags=['railway-plug'])

def _config_path():
    return Path(os.environ.get('RAILWAY_PLUG_CONFIG_FILE', str(Path(__file__).resolve().parents[1] / 'data' / 'railway-plug.json')))

def _saved():
    path = _config_path()
    if not path.exists():
        return {}
    try:
        with path.open(encoding='utf-8') as source:
            return json.load(source)
    except (OSError, ValueError) as exc:
        raise RuntimeError('Railway plug configuration is unreadable') from exc


def _settings():
    saved = _saved()
    url = os.environ.get('RAILWAY_HA_URL', '').rstrip('/')
    token_file = os.environ.get('RAILWAY_HA_TOKEN_FILE')
    token = os.environ.get('RAILWAY_HA_TOKEN', '').strip()
    if token_file:
        try:
            token = open(token_file, encoding='utf-8').read().strip()
        except OSError as exc:
            raise RuntimeError('Railway plug credential file is unavailable') from exc
    entity = os.environ.get('RAILWAY_PLUG_ENTITY_ID', '').strip()
    url = saved.get('url', url)
    token = saved.get('token', token)
    entity = saved.get('entity_id', entity)
    if entity and not entity.startswith(('switch.', 'light.')):
        raise RuntimeError('Railway plug entity must be a switch or light')
    return url, token, entity


class PlugConfig(BaseModel):
    url: str = Field(min_length=1, max_length=256)
    entity_id: str = Field(min_length=1, max_length=128)
    token: str = Field(default='', max_length=4096)

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment or any(c.isspace() for c in value):
            raise ValueError('Use a Home Assistant http(s) base URL without credentials or path')
        return value.rstrip('/')

    @field_validator('entity_id')
    @classmethod
    def valid_entity(cls, value):
        if not re.fullmatch(r'(switch|light)\.[a-z0-9_]+', value):
            raise ValueError('Select a switch or light entity ID')
        return value


def _protect_setup(request):
    from .app import require_inventory
    require_inventory(request)
    if request.headers.get('sec-fetch-site', 'same-origin') not in ('same-origin', 'none'):
        raise HTTPException(403, 'Same-origin setup required')
    if request.headers.get('origin') and request.headers['origin'].rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Same-origin setup required')


def _public_config():
    url, token, entity = _settings()
    return {'url': url, 'entity_id': entity, 'credential_configured': bool(token)}


@router.get('/config')
def read_config(request: Request):
    _protect_setup(request)
    return _public_config()


@router.put('/config')
def save_config(config: PlugConfig, request: Request):
    _protect_setup(request)
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'JSON setup required')
    old_token = _settings()[1]
    token = config.token.strip() or old_token
    if not token:
        raise HTTPException(422, 'Enter a Home Assistant long-lived access token')
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.railway-plug-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump({'url': config.url, 'entity_id': config.entity_id, 'token': token}, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return _public_config()


def _ha(method, path, token, url, data=None):
    request = urllib.request.Request(
        url + '/api/' + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError('Home Assistant is unavailable or rejected the railway plug request') from exc


def _resolve(url, token, entity):
    if entity:
        result = _ha('GET', 'states/' + urllib.parse.quote(entity, safe=''), token, url)
    else:
        matches = [s for s in _ha('GET', 'states', token, url)
                   if s.get('entity_id', '').startswith(('switch.', 'light.'))
                   and s.get('attributes', {}).get('friendly_name', '').casefold() == 'model railway']
        if len(matches) != 1:
            raise RuntimeError('Expected one Model Railway switch/light in Home Assistant; configure RAILWAY_PLUG_ENTITY_ID')
        result = matches[0]
    if result.get('entity_id', '').split('.')[0] not in ('switch', 'light'):
        raise RuntimeError('Railway plug is not a switch/light')
    return result


def status():
    url, token, entity = _settings()
    if not token:
        return {'configured': False, 'available': False, 'on': None, 'entity_id': None,
                'message': 'Home Assistant credential not configured'}
    try:
        result = _resolve(url, token, entity)
        state = result.get('state')
        return {'configured': True, 'available': state in ('on', 'off'),
                'on': state == 'on' if state in ('on', 'off') else None,
                'entity_id': result['entity_id'], 'message': None if state in ('on', 'off') else 'Plug state unavailable'}
    except RuntimeError as exc:
        return {'configured': True, 'available': False, 'on': None, 'entity_id': entity or None, 'message': str(exc)}


class PlugCommand(BaseModel):
    on: bool = Field(strict=True)
    confirmed: bool = Field(strict=True)


@router.get('')
def read_plug():
    return status()


@router.post('')
def set_plug(command: PlugCommand, request: Request):
    # This app has no browser token flow: mains control is restricted to direct
    # loopback/Tailscale clients, never a public proxy or arbitrary LAN peer.
    from .app import require_inventory
    require_inventory(request)
    if request.headers.get('sec-fetch-site', 'same-origin') not in ('same-origin', 'none'):
        raise HTTPException(403, 'Same-origin plug control required')
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'JSON plug command required')
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Cross-origin plug control refused')
    if not command.confirmed:
        raise HTTPException(400, 'Confirm that switching the upstream railway supply is safe')
    url, token, entity = _settings()
    if not token:
        raise HTTPException(503, 'Railway plug credential not configured')
    try:
        current = _resolve(url, token, entity)
        domain, object_id = current['entity_id'].split('.', 1)
        if current.get('state') not in ('on', 'off'):
            raise RuntimeError('Plug state unavailable; refusing blind control')
        if (current['state'] == 'on') != command.on:
            _ha('POST', 'services/' + domain + '/' + ('turn_on' if command.on else 'turn_off'), token, url,
                {'entity_id': current['entity_id']})
        after = _resolve(url, token, current['entity_id'])
        if after.get('state') != ('on' if command.on else 'off'):
            raise RuntimeError('Plug command sent but resulting state is not verified')
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {'configured': True, 'available': True, 'on': command.on, 'entity_id': after['entity_id'], 'message': None}
