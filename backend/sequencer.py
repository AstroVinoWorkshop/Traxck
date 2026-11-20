"""Bounded, single-owner railway sequence runner. No commands on import."""
import copy
import json
import math
import threading
import time
import uuid
from .simulator import mapped_function

MAX_ACTIONS = 512
MAX_SECONDS = 600
DEFAULT_POINT_WAIT = 2.0  # settling interval after a move stops; not position feedback


def _number(value, low, high, name):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be a finite number in {low}–{high}')
    return float(value)


class Sequencer:
    def __init__(self, hardware, sim):
        self.hardware, self.sim = hardware, sim
        self.lock = threading.RLock()
        self.thread = None
        self.cancel = threading.Event()
        self.resume_event = threading.Event()
        self.resume_event.set()
        self.run = {'state': 'idle', 'run_id': None, 'step_index': None, 'error': None}
        with sim._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sequence_calibration (address INTEGER NOT NULL, direction INTEGER NOT NULL, speed INTEGER NOT NULL, mm_per_second REAL NOT NULL, PRIMARY KEY(address,direction,speed))')

    def calibrations(self):
        with self.sim._db() as db:
            rows = db.execute('SELECT address,direction,speed,mm_per_second FROM sequence_calibration ORDER BY address,direction,speed').fetchall()
        return [dict(address=a, direction=d, speed=s, mm_per_second=v) for a, d, s, v in rows]

    def calibrate(self, address, direction, speed, mm_per_second):
        self.sim._address(address)
        if type(address) is not int or type(direction) is not int or direction not in (-1, 1) or type(speed) is not int or not 1 <= speed <= 126:
            raise ValueError('Invalid locomotive, direction or speed')
        velocity = _number(mm_per_second, 0.001, 10000, 'mm_per_second')
        with self.sim._db() as db:
            db.execute('INSERT OR REPLACE INTO sequence_calibration VALUES (?,?,?,?)', (address, direction, speed, velocity))
        return dict(address=address, direction=direction, speed=speed, mm_per_second=velocity)

    def status(self):
        with self.lock:
            return copy.deepcopy(self.run)

    def _compile(self, steps):
        if not isinstance(steps, list) or len(steps) > 128:
            raise ValueError('Sequence requires at most 128 steps')
        result = []
        states = {}
        calibration = {(r['address'], r['direction'], r['speed']): r['mm_per_second'] for r in self.calibrations()}
        points = {p['id'] for p in self.sim._points()}

        def expand(items, depth=0):
            if depth > 4: raise ValueError('Loop nesting limit exceeded')
            for position, step in enumerate(items, start=1):
                if not isinstance(step, dict): raise ValueError('Invalid sequence step')
                typ = step.get('type', step.get('kind'))
                if typ == 'loop':
                    count = step.get('count')
                    body = step.get('steps')
                    if type(count) is not int or not 1 <= count <= 20 or not isinstance(body, list) or not body:
                        raise ValueError('Loop count must be 1–20 and steps nonempty')
                    for _ in range(count): expand(body, depth + 1)
                elif typ == 'state':
                    key, value = step.get('key'), step.get('value')
                    if not isinstance(key, str) or not 1 <= len(key) <= 40 or type(value) not in (str, bool, int) or isinstance(value, str) and len(value) > 80:
                        raise ValueError('Invalid state assignment')
                    states[key] = value
                    result.append({'type': 'state', 'key': key, 'value': value})
                elif typ == 'if_state':
                    key, value = step.get('key'), step.get('equals')
                    yes, no = step.get('then_steps'), step.get('else_steps', [])
                    if (not isinstance(key, str) or not 1 <= len(key) <= 40 or type(value) not in (str, bool, int) or
                        isinstance(value, str) and len(value) > 80 or not isinstance(yes, list) or not yes or
                        not isinstance(no, list) or len(yes) > 100 or len(no) > 100):
                        raise ValueError('Invalid state branch')
                    expand(yes if key in states and type(states[key]) is type(value) and states[key] == value else no, depth + 1)
                elif typ in ('wait', 'throttle'):
                    if typ == 'throttle':
                        address, speed, direction = step.get('address'), step.get('speed'), step.get('direction')
                        if type(address) is not int or type(speed) is not int or not 1 <= speed <= 126 or type(direction) is not int or direction not in (-1, 1):
                            raise ValueError('Invalid throttle step')
                        self.sim._address(address)
                        distance = step.get('distance_mm') if step.get('use_calibration') else None
                        if distance is not None:
                            velocity = calibration.get((address, direction, speed))
                            if velocity is None: raise ValueError('Calibration required for this locomotive/direction/speed')
                            seconds = _number(distance, 0.001, 100000, 'distance_mm') / velocity
                        else:
                            seconds = step.get('seconds')
                    else:
                        seconds = step.get('seconds')
                    seconds = _number(seconds, 0.01, 120, 'seconds')
                    action = {'type': typ, 'seconds': seconds}
                    if typ == 'throttle': action.update(address=address, speed=speed, direction=direction)
                    result.append(action)
                elif typ == 'point':
                    ident = step.get('id', step.get('point_id'))
                    if ident not in points or step.get('position') not in ('straight', 'diverging'):
                        raise ValueError('Invalid point step')
                    settle = _number(step.get('settle_seconds', DEFAULT_POINT_WAIT), 0, 120, 'settle_seconds')
                    result.append({'type': 'point', 'id': ident, 'position': step['position'], 'seconds': settle})
                elif typ == 'function':
                    roster = next((r for r in self.sim._roster() if r['id'] == step.get('roster_id')), None)
                    key, mode = step.get('key'), step.get('mode')
                    if not roster or type(roster.get('address')) is not int or mode not in ('on', 'off', 'hold'):
                        raise ValueError('Function requires a mapped train and on, off or hold mode')
                    loco = next((l for l in self.sim._locos() if l['address'] == roster['address']), None)
                    mapping = mapped_function(loco, key) if loco else None
                    if not mapping or (mapping['momentary'] and mode != 'hold'):
                        raise ValueError('Choose a mapped F0–F28; momentary functions require hold')
                    seconds = _number(step.get('seconds'), 0.01, 120, 'seconds') if mode == 'hold' else 0
                    result.append({'type': 'function', 'address': roster['address'], 'key': key, 'mode': mode, 'seconds': seconds})
                elif typ == 'move':
                    roster = next((r for r in self.sim._roster() if r['id'] == step.get('roster_id')), None)
                    if not roster or type(roster.get('address')) is not int: raise ValueError('Move requires mapped roster address')
                    converted = dict(step, type='throttle', address=roster['address'],
                                     direction=1 if step.get('direction') == 'forward' else -1)
                    if step.get('direction') not in ('forward', 'reverse'): raise ValueError('Invalid direction')
                    if step.get('distance_mm') is None: converted.pop('distance_mm', None)
                    expand([converted], depth)
                elif typ == 'note':
                    result.append({'type': 'note', 'label': step.get('label', '')})
                else:
                    raise ValueError(f'Unsupported sequence step type at position {position}: {typ!r}')
                if len(result) > MAX_ACTIONS: raise ValueError('Sequence exceeds action limit')
        expand(steps)
        if not result or sum(s.get('seconds', 0) for s in result) > MAX_SECONDS:
            raise ValueError('Sequence empty or exceeds 600 seconds')
        return result

    def start(self, steps):
        # Validate before claiming the controller. Never power the track automatically.
        actions = self._compile(steps)
        with self.hardware.lock, self.lock:
            if self.thread and self.thread.is_alive(): raise ValueError('Sequence already running')
            state = self.hardware.state()
            if not state['track_power'] or state['estop'] or (self.hardware.mode == 'HARDWARE' and not self.hardware.adapter):
                raise ValueError('Track power must be on and emergency stop clear')
            if any(v.get('speed', 0) for v in state['speeds'].values()):
                raise ValueError('Stop all locomotives before starting a sequence')
            self.cancel.clear()
            self.resume_event.set()
            self.run = {'state': 'running', 'run_id': str(uuid.uuid4()), 'step_index': 0, 'error': None, 'total_steps': len(actions)}
            self.hardware.sequence_owner = -1  # reserve before worker is scheduled
            self.thread = threading.Thread(target=self._execute, args=(actions,), daemon=True)
            try: self.thread.start()
            except Exception:
                self.hardware.sequence_owner = None
                self.run['state'] = 'error'
                raise
            return self.status()

    def pause(self):
        with self.lock:
            if self.run['state'] != 'running': raise ValueError('Sequence not running')
            self.run['state'] = 'pausing'
            self.resume_event.clear()
        return self.status()

    def resume(self):
        with self.lock:
            if self.run['state'] != 'paused': raise ValueError('Sequence not paused')
            self.run['state'] = 'running'
            self.resume_event.set()
        return self.status()

    def stop(self):
        with self.lock:
            if self.run['state'] not in ('running', 'pausing', 'paused', 'stopping'):
                return self.status()
            self.run['state'] = 'stopping'
            self.cancel.set()
            self.resume_event.set()
            thread = self.thread
        thread.join(timeout=5)
        if thread.is_alive():
            raise ConnectionError('Sequence stop not confirmed; use physical power cut-off')
        result = self.status()
        if result['state'] == 'error':
            raise ConnectionError(result['error'])
        return result

    def _execute(self, actions):
        active = None
        held = None
        enabled = set()
        error = None
        stopped = False
        with self.hardware.lock:
            self.hardware.sequence_owner = threading.get_ident()
        try:
            for index, step in enumerate(actions):
                if self.cancel.is_set(): stopped = True; break
                with self.lock: self.run['step_index'] = index
                typ = step['type']
                if typ == 'throttle':
                    active = (step['address'], step['direction'])
                    self.hardware.throttle(active[0], step['speed'], active[1])
                    self._wait(step['seconds'], active, step['speed'])
                    self.hardware.throttle(active[0], 0, active[1])
                    active = None
                elif typ == 'wait': self._wait(step['seconds'], None, 0)
                elif typ == 'point':
                    self._wait(step['seconds'], None, 0)
                    if not self.cancel.is_set(): self.hardware.point(step['id'], step['position'])
                elif typ == 'function':
                    pair = (step['address'], step['key'])
                    if step['mode'] == 'hold':
                        held = pair  # mark before sending: failed/ambiguous ON still gets OFF attempted
                        self.hardware.function(*pair, True)
                        self._wait(step['seconds'], None, 0)
                        self.hardware.function(*pair, False)
                        held = None
                    elif step['mode'] == 'on':
                        enabled.add(pair)
                        self.hardware.function(*pair, True)
                    else:
                        self.hardware.function(*pair, False)
                        enabled.discard(pair)
                elif typ == 'state':
                    with self.lock: self.run.setdefault('variables', {})[step['key']] = step['value']
            stopped = stopped or self.cancel.is_set()
        except Exception as exc:
            error = f'Sequence failed: {exc}; physical state may be unknown. Use physical power cut-off'
        finally:
            if active:
                try: self.hardware.throttle(active[0], 0, active[1])
                except Exception as exc:
                    error = f'Stop command failed: {exc}; physical state unknown. Use physical power cut-off'
            # Never leave sequence-owned functions energised after stop, error or completion.
            for address, key in ({held} if held else set()) | enabled:
                try: self.hardware.function(address, key, False)
                except Exception as exc:
                    error = f'Function release failed: {exc}; physical state unknown. Use physical power cut-off'
            with self.hardware.lock, self.lock:
                self.hardware.sequence_owner = None
                self.run['state'] = 'error' if error else 'stopped' if stopped else 'completed'
                self.run['error'] = error

    def _wait(self, seconds, active, speed):
        remaining = seconds
        while remaining > 0 and not self.cancel.is_set():
            with self.hardware.lock:
                if (self.hardware.mode == 'HARDWARE' and not self.hardware.adapter) or self.hardware.state()['estop'] or not self.hardware.state()['track_power']:
                    raise ConnectionError('Track power, link or emergency state changed')
            if not self.resume_event.is_set():
                if active: self.hardware.throttle(active[0], 0, active[1])
                with self.lock:
                    if self.run['state'] == 'pausing': self.run['state'] = 'paused'
                while not self.resume_event.wait(0.05):
                    if self.cancel.is_set(): return
                if self.cancel.is_set(): return
                if active: self.hardware.throttle(active[0], speed, active[1])
            start = time.monotonic()
            self.cancel.wait(min(0.05, remaining))
            remaining -= time.monotonic() - start
