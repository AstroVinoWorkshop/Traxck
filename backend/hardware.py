"""Opt-in DCC-EX native TCP control. No transport opens during construction."""
import json
import re
import socket
import threading
import time

HOST = re.compile(r'^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$')
# Fixed, parameter-free queries from the DCC-EX native command reference.
# Never let a caller supply arbitrary native frames through this endpoint.
DIAGNOSTIC_COMMANDS = frozenset(('<s>', '<c>', '<#>', '<J I>', '<J G>',
                                 '<=>', '<J R>', '<J T>', '<J O>', '<Q>',
                                 '<S>', '<T>', '<I>', '<JC>', '<J A>'))


class DCCEXAdapter:
    """DCC-EX native framed commands over a configured TCP socket."""
    def __init__(self, connection):
        self.connection = connection
        self.connection.settimeout(2)
        self.buffer = b''

    def send(self, command):
        self.connection.sendall((command + '\n').encode('ascii'))

    def diagnostic(self, command):
        """Issue an allow-listed read-only query, returning bounded raw station output."""
        if command not in DIAGNOSTIC_COMMANDS:
            raise ValueError('Only supported read-only station queries are available')
        if self.buffer.strip():
            raise ConnectionError('Pending station data; reconnect before querying')
        self.send(command)
        data = b''
        deadline = time.monotonic() + 2
        try:
            while time.monotonic() < deadline:
                self.connection.settimeout(min(0.2 if data else 1.5, max(0.001, deadline - time.monotonic())))
                try: chunk = self.connection.recv(4096)
                except socket.timeout:
                    if data: break
                    continue
                if not chunk: raise ConnectionError('Command station closed connection')
                data += chunk
                if len(data) > 8192: raise ConnectionError('Oversized station output')
        finally:
            self.connection.settimeout(2)
        if not data: raise TimeoutError('No response from command station')
        return data.decode('ascii', errors='replace').strip()

    def confirm_power(self, on, track=None):
        """Wait for a matching power broadcast; other frames are not acknowledgements."""
        expected = b'p1' if on else b'p0'
        while True:
            start = self.buffer.find(b'<')
            end = self.buffer.find(b'>', start + 1) if start >= 0 else -1
            if end >= 0:
                frame = self.buffer[start + 1:end].strip()
                self.buffer = self.buffer[end + 1:]
                match = expected + (b' ' + track.encode('ascii') if track else b'')
                if frame == match:
                    return '<' + frame.decode('ascii') + '>'
                continue
            if len(self.buffer) > 8192:
                raise ConnectionError('Oversized command station response')
            chunk = self.connection.recv(4096)
            if not chunk:
                raise ConnectionError('Command station closed connection')
            self.buffer += chunk

    def cv_command(self, cv, value=None):
        """One service-track operation; reject unsolicited, ambiguous or stale frames."""
        if self.buffer.strip(): raise ConnectionError('Pending station data before CV operation')
        self.buffer = b''
        command = f'<R {cv}>' if value is None else f'<W {cv} {value}>'
        self.send(command)
        expected = b'v' if value is None else b'r'
        deadline = time.monotonic() + 2
        data = b''
        while b'>' not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError('CV response timeout')
            self.connection.settimeout(remaining)
            chunk = self.connection.recv(4096)
            if not chunk: raise ConnectionError('Station closed CV connection')
            data += chunk
            if len(data) > 128: raise ConnectionError('Oversized CV response')
        if not re.fullmatch(rb'\s*<' + expected + rb' ' + str(cv).encode('ascii') + rb' (0|[1-9][0-9]{0,2})>\s*', data):
            raise ConnectionError('Unexpected CV response')
        result = int(data.strip().split(b' ')[-1][:-1])
        if result > 255 or (value is not None and result != value):
            raise ConnectionError('CV response value mismatch')
        self.last_cv_response = data.decode('ascii').strip()
        return result

    def close(self): self.connection.close()


class HardwareController:
    """Routes commands only after explicit connect, mode selection and power-on."""
    def __init__(self, sim, socket_factory=socket.create_connection):
        self.sim = sim
        self.socket_factory = socket_factory
        self.lock = threading.RLock()
        self.sequence_owner = None
        self.adapter = None
        self.mode = 'SIMULATION'
        self.power_on = False
        self.main_power_off_verified = False
        self.estop = False
        self.speeds = {}
        self.functions = {}
        self.error = None
        self.mains_fault = False
        self.manual_simulation = False
        with sim._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS hardware_config (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            db.execute("CREATE TABLE IF NOT EXISTS hardware_mode (id INTEGER PRIMARY KEY CHECK(id=1), mode TEXT NOT NULL CHECK(mode IN ('SIMULATION','HARDWARE')))")
            row = db.execute('SELECT data FROM hardware_config WHERE id=1').fetchone()
            saved_mode = db.execute('SELECT mode FROM hardware_mode WHERE id=1').fetchone()
        self.config = json.loads(row[0]) if row else None
        self.mode = saved_mode[0] if saved_mode else 'SIMULATION'

    def state(self):
        with self.lock:
            state = self.sim.snapshot()
            state.update(mode=self.mode, hardware_connected=self.adapter is not None,
                         connection=self.config, hardware_error=self.error,
                         physical_power_verified=False,
                         main_power_off_verified=self.main_power_off_verified if self.adapter is not None else False)
            if self.mode == 'HARDWARE':
                state.update(track_power=self.power_on, estop=self.estop,
                             speeds=self.speeds, functions=self.functions)
            return state

    def configure(self, config):
        with self.lock:
            self._guard_sequence()
            if self.adapter: raise ValueError('Disconnect before changing connection settings')
            host, port = config.get('host'), config.get('port')
            if not isinstance(host, str) or not HOST.fullmatch(host) or '..' in host or not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
                raise ValueError('Host must be a DNS name or IP address and port must be 1–65535')
            clean = {'host':host, 'port':port}
            with self.sim._db() as db:
                db.execute('INSERT OR REPLACE INTO hardware_config VALUES (1,?)',(json.dumps(clean),))
            self.config = clean
            self.error = None
            return self.state()

    def connect(self):
        with self.lock:
            self._guard_sequence()
            if not self.config: raise ValueError('Configure host and port first')
            if self.adapter: raise ValueError('Already connected')
            try:
                self.adapter = DCCEXAdapter(self.socket_factory((self.config['host'],self.config['port']), 2))
            except (OSError, TimeoutError) as exc:
                self.error = f'Connection failed: {exc}'
                raise ConnectionError(self.error) from exc
            self.error = None
            self.power_on = False
            self.main_power_off_verified = False
            self.estop = False
            self.speeds = {}
            self.functions = {}
            return self.state()

    def reconcile_mains(self, on):
        """Prepare a verified powered station; never issue rail-power commands."""
        with self.lock:
            if not on:
                if self.adapter:
                    self.disconnect(force=True)
                self.mains_fault = False
                self.manual_simulation = False
                return self.state()
            if not self.config or self.mains_fault or self.manual_simulation:
                return self.state()
            if not self.adapter:
                try:
                    self.connect()
                except ConnectionError:
                    return self.state()  # Station may still be booting.
            if self.mode != 'HARDWARE':
                self.set_mode('HARDWARE')
            return self.state()

    def disconnect(self, force=False):
        with self.lock:
            if not force: self._guard_sequence()
            power_failure = None
            if self.adapter:
                if self.power_on:
                    try: self.adapter.send('<0>')
                    except (OSError, ConnectionError, TimeoutError) as exc:
                        power_failure = exc
                    self.error = 'Track power state unknown after disconnect; verify at station or use physical power cut-off'
                try: self.adapter.close()
                except OSError as exc: power_failure = power_failure or exc
            self.adapter = None
            self.power_on = False
            self.main_power_off_verified = False
            self.speeds = {}
            self.functions = {}
            if power_failure:
                self.error = f'Disconnect power-off failed; physical state unknown. Use physical power cut-off: {power_failure}'
                raise ConnectionError(self.error) from power_failure
            return self.state()

    def set_mode(self, mode):
        with self.lock:
            self._guard_sequence()
            if mode not in ('SIMULATION','HARDWARE'): raise ValueError('Invalid mode')
            if mode == 'HARDWARE' and not self.adapter: raise ValueError('Connect explicitly before hardware mode')
            if mode == 'SIMULATION' and self.power_on: raise ValueError('Turn track power off before simulation mode')
            with self.sim._db() as db:
                db.execute('INSERT OR REPLACE INTO hardware_mode (id, mode) VALUES (1, ?)', (mode,))
            self.mode = mode
            self.manual_simulation = mode == 'SIMULATION'
            return self.state()

    def _guard_sequence(self):
        if self.sequence_owner is not None and self.sequence_owner != threading.get_ident():
            raise ValueError('Sequence running; stop it before manual control')

    def _send(self, command):
        try: self.adapter.send(command)
        except (OSError, ConnectionError, TimeoutError) as exc:
            original_error = f'Transport failed; physical state unknown. Use physical power cut-off: {exc}'
            self.error = original_error
            self.mains_fault = True
            try: self.disconnect()
            except ConnectionError: pass  # Preserve the original transport failure.
            self.error = original_error
            raise ConnectionError(self.error) from exc

    def diagnostic(self, command):
        with self.lock:
            if command not in DIAGNOSTIC_COMMANDS:
                raise ValueError('Only supported read-only station queries are available')
            if self.mode != 'HARDWARE' or not self.adapter:
                raise ValueError('Connected HARDWARE mode required')
            try:
                return {'command': command, 'output': self.adapter.diagnostic(command)}
            except (OSError, TimeoutError, ConnectionError) as exc:
                self.error = f'Diagnostic transport failed: {exc}'
                self.disconnect()
                raise ConnectionError(self.error) from exc

    def native_command(self, command, confirmed=False, wiring_confirmed=False,
                       programming_track_isolated=False):
        """Validated subset of native frames, with explicit sent/acknowledged status."""
        with self.lock:
            self._guard_sequence()
            if type(command) is not str or len(command) > 64 or not re.fullmatch(r'<[ -~]+>', command) or command.count('<') != 1 or command.count('>') != 1:
                raise ValueError('Invalid native command frame')
            if type(confirmed) is not bool or not confirmed:
                raise ValueError('Explicit operator confirmation required')
            if self.mode != 'HARDWARE' or not self.adapter:
                raise ValueError('Connected HARDWARE mode required')
            if command in DIAGNOSTIC_COMMANDS:
                result = self.diagnostic(command)
                return dict(command=command, output=result['output'], acknowledged=False,
                            sent=True, status='response_received')
            if command in ('<0>', '<1>', '<1 JOIN>', '<0 MAIN>', '<1 MAIN>', '<0 PROG>', '<1 PROG>'):
                on = command.startswith('<1')
                join = command == '<1 JOIN>'
                track = command[3:-1] if command in ('<0 MAIN>', '<1 MAIN>', '<0 PROG>', '<1 PROG>') else ('JOIN' if join else None)
                if join and (type(wiring_confirmed) is not bool or not wiring_confirmed):
                    raise ValueError('JOIN requires explicit wiring phase acknowledgement')
                if on and (self.estop or self.mains_fault):
                    raise ValueError('Emergency stop or mains fault prevents power on')
                try:
                    self._send(command)
                    response = self.adapter.confirm_power(on, track)
                except (OSError, TimeoutError, ConnectionError) as exc:
                    self._native_failure('Power response unverified', exc)
                # A track-specific response cannot establish the other track's state.
                if track is None:
                    self.power_on = on
                    self.main_power_off_verified = not on
                elif on:
                    self.power_on = True
                    if track in ('MAIN', 'JOIN'): self.main_power_off_verified = False
                elif track == 'MAIN':
                    self.main_power_off_verified = True
                if not on and track != 'PROG':
                    for speed in self.speeds.values(): speed['speed'] = 0
                return dict(command=command, output=response, acknowledged=True,
                            sent=True, status='confirmed')
            match = re.fullmatch(r'<([RW]) ([0-9]{1,4})(?: ([0-9]{1,3}))?>', command)
            if match:
                op, cv_text, value_text = match.groups()
                cv = int(cv_text)
                value = int(value_text) if value_text is not None else None
                if not 1 <= cv <= 1024 or (op == 'R' and value is not None) or (op == 'W' and (value is None or value > 255)):
                    raise ValueError('Invalid service-track CV command')
                if type(programming_track_isolated) is not bool or not programming_track_isolated:
                    raise ValueError('Isolated programming track acknowledgement required')
                if (self.power_on or not self.main_power_off_verified or self.estop or
                    self.sim.track_power or self.sim.estop or
                    any(s.get('speed', 0) for s in self.speeds.values()) or
                    any(s.get('speed', 0) for s in self.sim.speeds.values())):
                    raise ValueError('Verified main power off and stopped trains required')
                try:
                    result = self.adapter.cv_command(cv, value)
                except (OSError, TimeoutError, ConnectionError) as exc:
                    self._native_failure('CV response unverified', exc)
                response = self.adapter.last_cv_response
                return dict(command=command, output=response, acknowledged=True,
                            sent=True, status='confirmed', value=result)
            match = re.fullmatch(r'<t ([0-9]{1,5}) ([0-9]{1,3}) ([01])>', command)
            if match:
                address, speed, direction = map(int, match.groups())
                if speed > 126: raise ValueError('Speed must be 0–126')
                self.throttle(address, speed, 1 if direction else -1)
                return dict(command=command, output=None, acknowledged=False,
                            sent=True, status='sent_unconfirmed')
            match = re.fullmatch(r'<F ([0-9]{1,5}) ([0-9]{1,2}) ([01])>', command)
            if match:
                address, key, on = map(int, match.groups())
                self.function(address, key, bool(on))
                return dict(command=command, output=None, acknowledged=False,
                            sent=True, status='sent_unconfirmed')
            raise ValueError('Unsupported or unsafe native command')

    def _native_failure(self, context, exc):
        self.error = f'{context}; physical state unknown. Use physical power cut-off: {exc}'
        self.mains_fault = True
        self.disconnect()
        raise ConnectionError(self.error) from exc

    def program_cv(self, ident, cv, value=None, programming_track_confirmed=False):
        """Service-track programming is never addressed; operator must isolate decoder."""
        raise ValueError('CV discovery/programming disabled until actual programming track is validated')
        with self.lock:
            if type(cv) is not int or not 1 <= cv <= 1024 or (value is not None and (type(value) is not int or not 0 <= value <= 255)):
                raise ValueError('Invalid CV number or value')
            if self.mode != 'HARDWARE' or not self.adapter:
                raise ValueError('Connected HARDWARE mode required')
            if self.power_on or not self.main_power_off_verified or self.estop or self.sim.track_power or self.sim.estop or any(s.get('speed', 0) != 0 for s in self.speeds.values()) or any(s.get('speed', 0) != 0 for s in self.sim.speeds.values()):
                raise ValueError('Main power off, stopped trains and clear emergency stop required')
            loco = next((l for l in self.sim._locos() if l.get('roster_id') == ident or (not l.get('roster_id') and l['name'] == ident)), None)
            if not loco or not loco.get('address') or not loco.get('decoder') or not programming_track_confirmed:
                raise ValueError('Verified roster mapping and isolated programming track confirmation required')
            try:
                result = self.adapter.cv_command(cv, value)
            except (OSError, TimeoutError, ConnectionError) as exc:
                self.error = 'CV programming response unverified; physical state unknown. Use physical power cut-off'
                self.disconnect()
                raise ConnectionError(self.error) from exc
            return {'id': ident, 'cv': cv, 'value': result, 'source': 'read_back' if value is None else 'write_ack'}

    def power(self, on):
        with self.lock:
            self._guard_sequence()
            if self.mode == 'SIMULATION': return self.sim.power(on)
            if not self.adapter: raise ValueError('Connect to command station before changing track power')
            if on and self.estop: raise ValueError('Reset emergency stop before power on')
            try:
                self._send('<1>' if on else '<0>')
                self.adapter.confirm_power(on)
            except (OSError, TimeoutError, ConnectionError) as exc:
                if self.adapter:
                    try: self.adapter.send('<0>')
                    except OSError: pass
                self.error = 'Power confirmation failed; physical state unknown. Use physical power cut-off'
                self.mains_fault = True
                self.disconnect()
                raise ConnectionError(self.error) from exc
            self.power_on = bool(on)
            self.main_power_off_verified = not on
            if not on:
                for speed in self.speeds.values(): speed['speed'] = 0
            return self.state()

    def throttle(self, address, speed, direction):
        with self.lock:
            self._guard_sequence()
            if self.mode == 'SIMULATION': return self.sim.throttle(address,speed,direction)
            self.sim._address(address)
            if not self.power_on or self.estop: raise ValueError('Track power off or emergency stop engaged')
            if type(speed) is not int or not 0 <= speed <= 126 or type(direction) is not int or direction not in (-1,1):
                raise ValueError('Invalid speed or direction')
            self._send(f'<t {address} {speed} {1 if direction == 1 else 0}>')
            self.speeds[str(address)] = {'speed':speed,'direction':direction}
            return self.state()

    def function(self, address, key, on):
        with self.lock:
            self._guard_sequence()
            if self.mode == 'SIMULATION': return self.sim.function(address,key,on)
            loco = next((l for l in self.sim._locos() if l['address'] == address),None)
            from .simulator import mapped_function
            if not loco or not mapped_function(loco, key):
                raise ValueError('Function not mapped for locomotive')
            if not self.power_on or self.estop: raise ValueError('Track power off or emergency stop engaged')
            if type(on) is not bool: raise ValueError('Invalid function state')
            self._send(f'<F {address} {key} {int(on)}>')
            self.functions.setdefault(str(address),{})[str(key)] = on
            return self.state()

    def point(self, ident, position):
        with self.lock:
            self._guard_sequence()
            if self.mode == 'SIMULATION': return self.sim.point(ident, position)
            if position not in ('straight', 'diverging'): raise ValueError('Invalid point position')
            point = next((p for p in self.sim._points() if p['id'] == ident), None)
            if point is None: raise ValueError('Unknown point')
            address = point.get('address')
            if type(address) is not int or not 1 <= address <= 2044:
                raise ValueError('Configure a valid DCC accessory address first')
            if not self.adapter: raise ValueError('Command station not connected')
            if not self.power_on or self.estop: raise ValueError('Track power off or emergency stop engaged')
            self._send(f'<a {address} {int(position == "diverging")}>')
            return self.sim.record_hardware_point(ident, position)

    def emergency_stop(self):
        with self.lock:
            if self.mode == 'SIMULATION':
                state = self.sim.emergency_stop()
                if self.adapter:
                    self.estop = True
                    self.power_on = False
                    self._send('<!>')
                    self._send('<0>')
                return state
            self.estop = True
            self.power_on = False
            for speed in self.speeds.values(): speed['speed'] = 0
            if not self.adapter:
                raise ConnectionError('Command station disconnected; use physical power cut-off')
            try:
                self._send('<!>')
                self._send('<0>')
            except ConnectionError:
                raise
            return self.state()

    def reset_emergency(self):
        with self.lock:
            self._guard_sequence()
            if self.mode == 'SIMULATION': return self.sim.reset_emergency()
            self.estop = False
            self.power_on = False
            return self.state()
