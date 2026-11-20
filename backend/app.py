"""Simulation-first railway API with explicit opt-in DCC-EX TCP control."""
import os
import ipaddress
import secrets
import io
import uuid
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .simulator import Simulator
from .hardware import HardwareController
from .sequencer import Sequencer
from .railway_plug import router as railway_plug_router
from . import railway_plug

ROOT = Path(__file__).resolve().parents[1]
PHOTO_DIR = ROOT / 'data' / 'roster-photos'
MAX_IMAGE_BYTES = 8 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 24_000_000
sim = Simulator(Path(os.environ.get('WORKSHOP_DB', ROOT / 'data' / 'workshop.db')))
hardware = HardwareController(sim)
sequencer = Sequencer(hardware, sim)

def sync_railway_mains():
    plug = railway_plug.status()
    if plug['available']:
        if not plug['on']:
            # The independent mains monitor may change power mid-sequence.
            # Cancellation must precede teardown, but teardown must proceed on stop failure.
            try: sequencer.stop()
            except (ConnectionError, RuntimeError): pass
        hardware.reconcile_mains(plug['on'])

@asynccontextmanager
async def lifespan(app):
    async def monitor():
        while True:
            try:
                await asyncio.to_thread(sync_railway_mains)
            except Exception:
                # An unavailable HA status must not be interpreted as mains off.
                pass
            await asyncio.sleep(5)
    task = asyncio.create_task(monitor())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

app = FastAPI(title='Traxck Railway Control', version='0.2.0', lifespan=lifespan,
              description='Verified railway mains prepares the DCC-EX link; track power remains explicit.')
app.include_router(railway_plug_router)

class Power(BaseModel): on: bool
class Throttle(BaseModel): address: int; speed: int = Field(ge=0, le=126); direction: int
class Function(BaseModel): address: int; key: int; on: bool
class Point(BaseModel): position: str
class PointEdit(BaseModel):
    label: str; device: str = ''; output: int | None = None; address: int | None = None
class SequenceEdit(BaseModel):
    name: str
    steps: list[dict]
class CalibrationEdit(BaseModel):
    address: int; direction: int; speed: int; mm_per_second: float
class Loco(BaseModel):
    name: str; address: int; decoder: str = ''; functions: list[dict] = Field(default_factory=list)
    class_name: str = ''; running_number: str = ''; sound_profile: str = ''; photo: str = ''; notes: str = ''
class RosterEdit(BaseModel):
    name: str; address: int | None = None; decoder: str = ''; functions: list[dict] = Field(default_factory=list)
    class_name: str = ''; running_number: str = ''; sound_profile: str = ''; notes: str = ''
class Layout(BaseModel): name: str; segments: list[dict]; pieces: list[dict] = Field(default_factory=list); buildings: list[dict] = Field(default_factory=list); diagramVersion: int | None = None; canvas: dict | None = None; perimeter: list[dict] | None = None
class ConnectionConfig(BaseModel): host: str; port: int
class Mode(BaseModel): mode: str
class DiagnosticCommand(BaseModel): command: str = Field(max_length=16)
class NativeCommand(BaseModel):
    command: str = Field(max_length=64)
    confirmed: bool = Field(strict=True)
    wiring_confirmed: bool = Field(default=False, strict=True)
    programming_track_isolated: bool = Field(default=False, strict=True)
class CVValue(BaseModel): value: int = Field(strict=True, ge=0, le=255)
class CVRead(BaseModel): programming_track_confirmed: bool = Field(strict=True)
class CVWrite(CVValue, CVRead): pass

def require_operator(request: Request):
    # Legacy token-free local-network mode: never expose through a public proxy.
    subnet = os.environ.get('WORKSHOP_LAN_SUBNET', '')
    tailscale_host = os.environ.get('WORKSHOP_TAILSCALE_IP', '')
    tailscale_dns = os.environ.get('WORKSHOP_TAILSCALE_HOSTNAME', '').rstrip('.').lower()
    if subnet:
        try:
            peer = ipaddress.ip_address(request.client.host)
            network = ipaddress.ip_network(subnet, strict=False)
            tail_host = ipaddress.ip_address(tailscale_host) if tailscale_host else None
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(403, 'Invalid local network')
        tailnet = ipaddress.ip_network('100.64.0.0/10')
        if peer not in network and not peer.is_loopback and not (tail_host and peer in tailnet):
            raise HTTPException(403, 'Home LAN or Tailscale only')
        hostname = request.url.hostname
        if not hostname:
            raise HTTPException(403, 'Invalid local network')
        try:
            allowed_host = ipaddress.ip_address(hostname)
        except ValueError:
            if not (tail_host and tailscale_dns and hostname.lower().rstrip('.') == tailscale_dns and peer in tailnet):
                raise HTTPException(403, 'Use the local or Tailscale address')
        else:
            if allowed_host not in network and not allowed_host.is_loopback and allowed_host != tail_host:
                raise HTTPException(403, 'Use the local or Tailscale address')
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Same-origin app required')
        if request.headers.get('sec-fetch-site', 'same-origin') not in ('same-origin', 'none'):
            raise HTTPException(403, 'Same-origin app required')
        return
    token = os.environ.get('WORKSHOP_OPERATOR_TOKEN', '')
    if not token: raise HTTPException(503, 'Hardware API disabled: set WORKSHOP_OPERATOR_TOKEN in service environment')
    supplied = request.headers.get('X-Operator-Token', '')
    if not secrets.compare_digest(supplied, token): raise HTTPException(401, 'Operator token required')

def require_inventory(request: Request):
    # Editing inventory is peer-address based. Proxies can invalidate this boundary;
    # bind to loopback only and do not expose the API through a public proxy.
    try: address = ipaddress.ip_address(request.client.host)
    except (ValueError, AttributeError): raise HTTPException(403, 'Inventory edits require a local or Tailscale connection')
    tailnet = (ipaddress.ip_network('100.64.0.0/10'), ipaddress.ip_network('fd7a:115c:a1e0::/48'))
    if not address.is_loopback and not any(address in network for network in tailnet):
        raise HTTPException(403, 'Inventory edits require a local or Tailscale connection')
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Inventory edits require the same-origin app')

def command(request: Request, fn, *args):
    # Keep the authorization decision and routing atomic with mode/connect changes.
    with hardware.lock:
        if hardware.adapter is not None or os.environ.get('WORKSHOP_LAN_SUBNET'): require_operator(request)
        return apply(fn, *args)

def apply(fn, *args):
    try: return fn(*args)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    except ConnectionError as exc: raise HTTPException(503, str(exc)) from exc

@app.get('/api/hardware')
def hardware_status(request: Request):
    require_operator(request)
    return hardware.state()
@app.put('/api/hardware/config')
def configure(payload: ConnectionConfig, request: Request):
    require_operator(request)
    return apply(hardware.configure, payload.model_dump())
@app.post('/api/hardware/connect')
def connect(request: Request):
    require_operator(request)
    return apply(hardware.connect)
@app.post('/api/hardware/disconnect')
def disconnect(request: Request):
    require_operator(request)
    stop_failure = None
    try: apply(sequencer.stop)
    except HTTPException as exc: stop_failure = exc
    # Still try to cut track power after a failed locomotive stop.
    disconnect_failure = None
    try: result = apply(hardware.disconnect, bool(stop_failure))
    except HTTPException as exc: disconnect_failure = exc
    if stop_failure:
        detail = str(stop_failure.detail)
        if disconnect_failure: detail += '; ' + str(disconnect_failure.detail)
        raise HTTPException(503, detail + '; physical state unknown. Use physical power cut-off.')
    if disconnect_failure: raise disconnect_failure
    return result
@app.post('/api/hardware/mode')
def mode(payload: Mode, request: Request):
    require_operator(request)
    apply(sequencer.stop)
    return apply(hardware.set_mode, payload.mode)

@app.post('/api/hardware/diagnostic')
def diagnostic(payload: DiagnosticCommand, request: Request):
    require_operator(request)
    return apply(hardware.diagnostic, payload.command)

@app.post('/api/hardware/command')
def native_command(payload: NativeCommand, request: Request):
    require_operator(request)
    with hardware.lock: hardware._guard_sequence()
    if payload.command in ('<1>', '<1 MAIN>', '<1 PROG>', '<1 JOIN>'):
        plug = railway_plug.status()
        if not plug['available'] or not plug['on']:
            raise HTTPException(400, 'Railway mains must be confirmed on before track power')
    return apply(hardware.native_command, payload.command, payload.confirmed,
                 payload.wiring_confirmed, payload.programming_track_isolated)

@app.get('/api/state')
def state(): return hardware.state()
@app.post('/api/power')
def power(payload: Power, request: Request):
    if not payload.on:
        if hardware.adapter is not None or os.environ.get('WORKSHOP_LAN_SUBNET'): require_operator(request)
        stop_failure = None
        try: apply(sequencer.stop)
        except HTTPException as exc: stop_failure = exc
        # Power OFF must still be attempted if a locomotive's zero-speed command failed.
        power_failure = None
        try: result = command(request, hardware.power, False)
        except HTTPException as exc: power_failure = exc
        if power_failure and stop_failure:
            raise HTTPException(503, 'Stop and power-off failed; physical state unknown. Use physical power cut-off. '
                                + str(stop_failure.detail) + '; ' + str(power_failure.detail))
        if power_failure: raise power_failure
        if stop_failure: raise stop_failure
        return result
    if payload.on and hardware.config:
        require_operator(request)
        plug = railway_plug.status()
        if not plug['available'] or not plug['on']:
            raise HTTPException(400, 'Railway mains must be confirmed on before track power')
        with hardware.lock:
            hardware.reconcile_mains(True)
            if not hardware.adapter or hardware.mode != 'HARDWARE':
                raise HTTPException(503, hardware.error or 'Command station not ready; retry after it boots')
    return command(request, hardware.power, payload.on)
@app.post('/api/throttle')
def throttle(payload: Throttle, request: Request):
    return command(request, hardware.throttle, payload.address, payload.speed, payload.direction)
@app.post('/api/functions')
def function(payload: Function, request: Request):
    return command(request, hardware.function, payload.address, payload.key, payload.on)
@app.post('/api/points/{ident}')
def point(ident: str, payload: Point, request: Request):
    return command(request, hardware.point, ident, payload.position)
@app.put('/api/point-inventory/{ident}')
def save_point(ident: str, payload: PointEdit, request: Request):
    require_inventory(request)
    with hardware.lock:
        apply(hardware._guard_sequence)
        return apply(sim.save_point, ident, payload.label, payload.device, payload.output, payload.address)
@app.delete('/api/point-inventory/{ident}')
def delete_point(ident: str, request: Request):
    require_inventory(request)
    with hardware.lock:
        apply(hardware._guard_sequence)
        return apply(sim.delete_point, ident)
@app.get('/api/sequences')
def list_sequences(): return sim.sequences()
@app.put('/api/sequences/{ident}')
def save_sequence(ident: str, payload: SequenceEdit, request: Request):
    require_inventory(request)
    return apply(sim.save_sequence, ident, payload.model_dump())
@app.delete('/api/sequences/{ident}')
def delete_sequence(ident: str, request: Request):
    require_inventory(request)
    return apply(sim.delete_sequence, ident)
@app.get('/api/sequences/{ident}/preview')
def preview_sequence(ident: str): return apply(sim.preview_sequence, ident)
@app.get('/api/sequences/{ident}/execution-preview')
def execution_preview(ident: str, request: Request):
    require_operator(request)
    sequence = next((item for item in sim.sequences() if item['id'] == ident), None)
    if sequence is None: raise HTTPException(404, 'Unknown sequence')
    actions = apply(sequencer._compile, sequence['steps'])
    elapsed, timeline = 0, []
    for step in actions:
        duration = step.get('seconds', 0)
        timeline.append({**step, 'start_seconds': elapsed, 'end_seconds': elapsed + duration})
        elapsed += duration
    return {'id': ident, 'steps': timeline, 'duration_seconds': elapsed,
            'warning': 'Estimated open-loop motion only; no sensor feedback or physical position verification. No commands sent.'}
@app.get('/api/sequencer/status')
def sequence_status(request: Request):
    require_operator(request)
    return sequencer.status()
@app.get('/api/sequencer/calibrations')
def sequence_calibrations(request: Request):
    require_operator(request)
    return sequencer.calibrations()
@app.put('/api/sequencer/calibrations')
def sequence_calibrate(payload: CalibrationEdit, request: Request):
    require_operator(request)
    return apply(sequencer.calibrate, payload.address, payload.direction, payload.speed, payload.mm_per_second)
@app.post('/api/sequences/{ident}/run')
def sequence_run(ident: str, request: Request):
    require_operator(request)
    sequence = next((item for item in sim.sequences() if item['id'] == ident), None)
    if sequence is None: raise HTTPException(404, 'Unknown sequence')
    return apply(sequencer.start, sequence['steps'])
@app.post('/api/sequencer/pause')
def sequence_pause(request: Request):
    require_operator(request)
    return apply(sequencer.pause)
@app.post('/api/sequencer/resume')
def sequence_resume(request: Request):
    require_operator(request)
    return apply(sequencer.resume)
@app.post('/api/sequencer/stop')
def sequence_stop(request: Request):
    require_operator(request)
    return apply(sequencer.stop)
@app.post('/api/emergency-stop')
def emergency_stop(request: Request):
    if hardware.adapter is not None or os.environ.get('WORKSHOP_LAN_SUBNET'): require_operator(request)
    sequencer.cancel.set()
    sequencer.resume_event.set()
    emergency_failure = None
    try: result = command(request, hardware.emergency_stop)
    except HTTPException as exc: emergency_failure = exc
    stop_failure = None
    try: apply(sequencer.stop)
    except HTTPException as exc: stop_failure = exc
    if emergency_failure or stop_failure:
        raise HTTPException(503, 'Emergency stop could not be confirmed; use physical power cut-off. '
                            + '; '.join(str(exc.detail) for exc in (emergency_failure, stop_failure) if exc))
    return result
@app.post('/api/emergency-reset')
def emergency_reset(request: Request):
    return command(request, hardware.reset_emergency)
def remove_old_photo(url):
    if url and url.startswith('/user-photos/'):
        filename = url.removeprefix('/user-photos/')
        try: uuid.UUID(filename.removesuffix('.jpg'))
        except ValueError: return
        (PHOTO_DIR / filename).unlink(missing_ok=True)

@app.get('/user-photos/{filename}')
def user_photo(filename: str):
    try:
        if not filename.endswith('.jpg'): raise ValueError()
        uuid.UUID(filename[:-4])
    except ValueError: raise HTTPException(404, 'Image not found')
    path = PHOTO_DIR / filename
    if not path.is_file(): raise HTTPException(404, 'Image not found')
    return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=86400'})

@app.put('/api/roster/{name}/photo')
async def upload_roster_photo(name: str, request: Request):
    require_inventory(request)
    if name not in {item['id'] for item in sim.snapshot()['roster']}:
        raise HTTPException(404, 'Unknown roster entry')
    if request.headers.get('content-type', '').split(';')[0] not in {'image/jpeg', 'image/png', 'image/webp'}:
        raise HTTPException(415, 'Use JPEG, PNG or WebP')
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_IMAGE_BYTES: raise HTTPException(413, 'Image exceeds 8 MB')
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 24_000_000:
                raise ValueError('Unsupported or oversized image')
            image.load()
            image = ImageOps.exif_transpose(image)
            image.thumbnail((1600, 1200))
            clean = image.convert('RGB')
            output = io.BytesIO()
            clean.save(output, format='JPEG', quality=85)
    except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, 'Invalid image') from exc
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid.uuid4()}.jpg'
    destination = PHOTO_DIR / filename
    destination.write_bytes(output.getvalue())
    try: old = sim.set_roster_photo(name, '/user-photos/' + filename)
    except ValueError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(404, str(exc)) from exc
    remove_old_photo(old)
    return hardware.state()

@app.delete('/api/roster/{name}/photo')
def restore_roster_photo(name: str, request: Request):
    require_inventory(request)
    try: old = sim.set_roster_photo(name, None)
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc
    remove_old_photo(old)
    return hardware.state()

@app.get('/api/roster/{ident}/cvs')
def roster_cvs(ident: str):
    return {'id': ident, 'stored_values': apply(sim.get_cv_values, ident)}

@app.put('/api/roster/{ident}/cvs/{cv}')
def set_roster_cv(ident: str, cv: int, payload: CVValue, request: Request):
    require_inventory(request)
    return {'id': ident, 'stored_values': apply(sim.set_cv_value, ident, cv, payload.value)}

@app.delete('/api/roster/{ident}/cvs/{cv}')
def delete_roster_cv(ident: str, cv: int, request: Request):
    require_inventory(request)
    return {'id': ident, 'stored_values': apply(sim.delete_cv_value, ident, cv)}

@app.post('/api/roster/{ident}/cvs/{cv}/read')
def read_roster_cv(ident: str, cv: int, payload: CVRead, request: Request):
    require_operator(request)
    return apply(hardware.program_cv, ident, cv, None, payload.programming_track_confirmed)

@app.post('/api/roster/{ident}/cvs/{cv}/write')
def write_roster_cv(ident: str, cv: int, payload: CVWrite, request: Request):
    require_operator(request)
    return apply(hardware.program_cv, ident, cv, payload.value, payload.programming_track_confirmed)

@app.post('/api/roster')
def create_roster(payload: RosterEdit, request: Request):
    require_inventory(request)
    with hardware.lock:
        apply(hardware._guard_sequence)
        apply(sim.create_roster, payload.model_dump())
        return hardware.state()

@app.put('/api/roster/{ident}')
def edit_roster(ident: str, payload: RosterEdit, request: Request):
    require_inventory(request)
    with hardware.lock:
        apply(hardware._guard_sequence)
        current = next((item for item in sim.snapshot()['roster'] if item['id'] == ident), None)
        if current is None: raise HTTPException(404, 'Unknown roster entry')
        mapping_changed = current['functions'] != payload.functions
        if mapping_changed and hardware.mode == 'HARDWARE' and hardware.power_on:
            raise HTTPException(400, 'Switch physical track power off before editing function mapping')
        if mapping_changed and hardware.speeds.get(str(current['address']), {}).get('speed', 0):
            raise HTTPException(400, 'Stop the moving locomotive before editing function mapping')
        if current['address'] != payload.address:
            if hardware.mode == 'HARDWARE' and hardware.power_on:
                raise HTTPException(400, 'Switch physical track power off before changing DCC addresses')
            if hardware.speeds.get(str(current['address']),{}).get('speed',0):
                raise HTTPException(400, 'Stop the moving locomotive before changing its DCC address')
        apply(sim.update_roster, ident, payload.model_dump())
        if current['address'] != payload.address:
            hardware.speeds.pop(str(current['address']),None)
        if mapping_changed or current['address'] != payload.address:
            hardware.functions.pop(str(current['address']),None)
        return hardware.state()

@app.post('/api/locomotives')
def add_locomotive(payload: Loco, request: Request):
    require_inventory(request)
    with hardware.lock:
        apply(hardware._guard_sequence)
        apply(sim.add_locomotive, payload.model_dump())
    return hardware.state()
@app.put('/api/layout')
def save_layout(payload: Layout, request: Request):
    require_inventory(request)
    apply(sim.save_layout, payload.model_dump(exclude_none=True))
    return hardware.state()

DIST = ROOT / 'frontend' / 'dist'
if DIST.exists():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')

    @app.get('/{path:path}')
    def spa(path: str): return FileResponse(DIST / 'index.html')
