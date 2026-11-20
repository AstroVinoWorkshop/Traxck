"""Isolated, fail-safe railway simulator. No physical device commands are emitted."""
import json
import math
import sqlite3
import threading
from pathlib import Path

# Inventory is separate from addressable simulator locomotives. Never invent DCC IDs.
ROSTER = [
    {'name':'Steam locomotive A','class_name':'','running_number':''},
    {'name':'Steam locomotive B','class_name':'','running_number':''},
    {'name':'Steam locomotive C','class_name':'','running_number':''},
    {'name':'Steam locomotive D','class_name':'','running_number':''},
    {'name':'Steam locomotive E','class_name':'','running_number':''},
    {'name':'Diesel locomotive A','class_name':'','running_number':''},
    {'name':'Shunter A','class_name':'','running_number':''},
    {'name':'Shunter B','class_name':'','running_number':''},
]
POINTS = [{'id':f'P{i}','label':f'Point {i} · location to confirm','device':'','output':None,'address':None,'commanded':'straight','hardware_commanded':None,'verified':None} for i in range(1, 9)]
FUNCTION_ICON_IDS = frozenset('function power play stop check whistle horn bell speaker mute volume-up volume-down announcement radio music brake compressor engine diesel steam headlight rear-light cab-light interior-light marker-light flashing-light beacon dim-light shunting coupler doors fan smoke steam-release pantograph wipers gear train clock warning spark'.split())

def validated_functions(functions):
    """Only explicitly sourced, operator-entered F0–F28 assignments can drive a decoder."""
    if (not isinstance(functions, list) or len(functions) > 29 or
        any(not isinstance(f, dict) or type(f.get('key')) is not int or not 0 <= f['key'] <= 28 or
            not isinstance(f.get('label'), str) or not f['label'].strip() or len(f['label']) > 80 or
            type(f.get('momentary')) is not bool or
            not isinstance(f.get('source'), str) or not f['source'].strip() or len(f['source']) > 200 or
            f.get('confidence') not in ('manual', 'verified') or
            ('icon' in f and (not isinstance(f['icon'], str) or f['icon'] not in FUNCTION_ICON_IDS)) for f in functions) or
        len({f['key'] for f in functions if isinstance(f, dict) and type(f.get('key')) is int}) != len(functions)):
        raise ValueError('Invalid function mapping: F0–F28 need a source and manual/verified confidence')
    return [{**{k: f[k] for k in ('key', 'label', 'momentary', 'source', 'confidence')},
             **({'icon': f['icon']} if 'icon' in f else {})} for f in functions]

def mapped_function(loco, key):
    return next((f for f in loco.get('functions', []) if type(key) is int and 0 <= key <= 28 and
                 f.get('key') == key and f.get('source') and f.get('confidence') in ('manual', 'verified') and
                 type(f.get('momentary')) is bool), None)

class Simulator:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS locos (address INTEGER PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS roster (name TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS points (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS layout (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sequences (id TEXT PRIMARY KEY, data TEXT NOT NULL)')

            for item in ROSTER:
                db.execute('INSERT OR IGNORE INTO roster VALUES (?,?)', (item['name'],json.dumps(item)))
            # Retire only the three exact illustrative demo rows, not user-added entries.
            for address, name in ((3,'Class 08 Shunter'),(4,'Class 66 Freight'),(5,'Express Passenger')):
                row = db.execute('SELECT data FROM locos WHERE address=?',(address,)).fetchone()
                if row:
                    old = json.loads(row[0])
                    if old.get('name') == name and ('illustrative' in old.get('decoder','') or old.get('notes','').startswith('Demo')):
                        db.execute('DELETE FROM locos WHERE address=?',(address,))
            db.execute('CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY)')
            if not db.execute('SELECT 1 FROM migrations WHERE name=?', ('eight_accessory_points',)).fetchone():
                # Add missing slots once, retaining existing names, addresses and extra points.
                # A point deliberately deleted later must not reappear on every restart.
                db.executemany('INSERT OR IGNORE INTO points VALUES (?,?)', [(p['id'],json.dumps(p)) for p in POINTS])
                db.execute('INSERT INTO migrations VALUES (?)', ('eight_accessory_points',))
        self.track_power = False
        self.estop = False
        self.speeds = {str(l['address']): {'speed':0,'direction':1} for l in self._locos()}
        self.functions = {}
        self.events = []
        self._log('Simulator ready; track power off')

    def _db(self): return sqlite3.connect(self.path)
    def _log(self, message):
        from datetime import datetime, timezone
        self.events.insert(0, {'time':datetime.now(timezone.utc).isoformat(timespec='seconds'),'message':message})
        self.events = self.events[:40]
    def _locos(self):
        with self._db() as db: return [json.loads(r[0]) for r in db.execute('SELECT data FROM locos ORDER BY address')]
    def _points(self):
        with self._db() as db: return [{**{'address':None,'hardware_commanded':None},**json.loads(r[0])} for r in db.execute('SELECT data FROM points ORDER BY id')]
    def _roster(self):
        with self._db() as db:
            items = {name:json.loads(data) for name,data in db.execute('SELECT name,data FROM roster')}
        locos = self._locos()
        return [{**items[key], 'id': key, 'address': next((l['address'] for l in locos if l.get('roster_id') == key or (not l.get('roster_id') and l['name'] == items[key]['name'])), None),
                 'decoder': next((l['decoder'] for l in locos if l.get('roster_id') == key or (not l.get('roster_id') and l['name'] == items[key]['name'])), items[key].get('decoder','')),
                 'functions': next((l['functions'] for l in locos if l.get('roster_id') == key or (not l.get('roster_id') and l['name'] == items[key]['name'])), []),
                 'profile_source': next((l.get('profile_source','') for l in locos if l.get('roster_id') == key), ''),
                 'cv_values': items[key].get('cv_values', {})}
                for key in [item['name'] for item in ROSTER] if key in items] + [
                {**item, 'id': key, 'address': next((l['address'] for l in locos if l.get('roster_id') == key), None),
                 'decoder': next((l['decoder'] for l in locos if l.get('roster_id') == key), item.get('decoder','')),
                 'functions': next((l['functions'] for l in locos if l.get('roster_id') == key), []),
                 'profile_source': next((l.get('profile_source','') for l in locos if l.get('roster_id') == key), ''),
                 'cv_values': item.get('cv_values', {})}
                for key,item in items.items() if key not in {seed['name'] for seed in ROSTER}]
    def get_cv_values(self, ident):
        with self.lock, self._db() as db:
            row = db.execute('SELECT data FROM roster WHERE name=?', (ident,)).fetchone()
            if row is None: raise ValueError('Unknown roster entry')
            return json.loads(row[0]).get('cv_values', {})

    def set_cv_value(self, ident, cv, value):
        if type(cv) is not int or not 1 <= cv <= 1024 or type(value) is not int or not 0 <= value <= 255:
            raise ValueError('Invalid CV number or value')
        with self.lock, self._db() as db:
            row = db.execute('SELECT data FROM roster WHERE name=?', (ident,)).fetchone()
            if row is None: raise ValueError('Unknown roster entry')
            item = json.loads(row[0]); item.setdefault('cv_values', {})[str(cv)] = value
            db.execute('UPDATE roster SET data=? WHERE name=?', (json.dumps(item), ident))
            return item['cv_values']

    def delete_cv_value(self, ident, cv):
        if type(cv) is not int or not 1 <= cv <= 1024: raise ValueError('Invalid CV number')
        with self.lock, self._db() as db:
            row = db.execute('SELECT data FROM roster WHERE name=?', (ident,)).fetchone()
            if row is None: raise ValueError('Unknown roster entry')
            item = json.loads(row[0]); item.setdefault('cv_values', {}).pop(str(cv), None)
            db.execute('UPDATE roster SET data=? WHERE name=?', (json.dumps(item), ident))
            return item['cv_values']

    def set_roster_photo(self, name, photo):
        """Store only a server-generated photo URL; keep the roster address-free."""
        with self.lock:
            with self._db() as db:
                row = db.execute('SELECT data FROM roster WHERE name=?', (name,)).fetchone()
                if not row:
                    raise ValueError('Unknown roster entry')
                item = json.loads(row[0]); old = item.get('photo')
                if photo is None: item.pop('photo', None)
                else: item['photo'] = photo
                db.execute('UPDATE roster SET data=? WHERE name=?', (json.dumps(item), name))
            return old

    def update_roster(self, ident, data):
        """Edit inventory and its optional verified DCC mapping as one transaction."""
        with self.lock:
            with self._db() as db:
                row = db.execute('SELECT data FROM roster WHERE name=?', (ident,)).fetchone()
                if not row: raise ValueError('Unknown roster entry')
                item = json.loads(row[0]); old_name = item['name']
                name = data.get('name', old_name)
                if not isinstance(name, str) or not name.strip() or len(name) > 120: raise ValueError('Invalid train name')
                name = name.strip()
                if any(json.loads(r[0]).get('name') == name for r in db.execute('SELECT data FROM roster WHERE name!=?', (ident,))):
                    raise ValueError('Train name already exists')
                address = data.get('address')
                if address is not None and (type(address) is not int or not 1 <= address <= 10239): raise ValueError('Invalid DCC address')
                decoder = data.get('decoder', item.get('decoder',''))
                functions = validated_functions(data.get('functions', []))
                if not isinstance(decoder,str) or len(decoder)>120: raise ValueError('Invalid decoder')

                locos = [(addr,json.loads(raw)) for addr,raw in db.execute('SELECT address,data FROM locos')]
                linked = [(addr,l) for addr,l in locos if l.get('roster_id') == ident or (not l.get('roster_id') and l['name'] == old_name)]
                if len(linked)>1: raise ValueError('Multiple DCC addresses linked to this train')
                old_address = linked[0][0] if linked else None
                if linked and (self.track_power or self.speeds.get(str(old_address), {}).get('speed', 0)) and (functions != linked[0][1].get('functions', []) or address != old_address):
                    raise ValueError('Stop and switch power off before editing function mapping or DCC address')
                if address != old_address and old_address is not None and self.speeds.get(str(old_address),{}).get('speed',0):
                    raise ValueError('Stop the moving locomotive before changing its DCC address')
                if address is not None and any(addr==address and addr!=old_address for addr,_ in locos): raise ValueError('DCC address already exists')
                for key in ('class_name','running_number','sound_profile','notes'):
                    value = data.get(key, item.get(key,''))
                    if not isinstance(value,str) or len(value)>2000: raise ValueError('Invalid '+key)
                    item[key] = value
                item['name'] = name
                item['decoder'] = decoder.strip()
                db.execute('UPDATE roster SET data=? WHERE name=?', (json.dumps(item),ident))
                if old_address is not None:
                    db.execute('DELETE FROM locos WHERE address=?',(old_address,))
                if address is not None:
                    loco = {**(linked[0][1] if linked else {}), **{k:item.get(k,'') for k in ('name','class_name','running_number','sound_profile','notes')}, 'address':address,'decoder':decoder.strip(),'functions':functions,'profile_source':'operator entry','roster_id':ident}
                    db.execute('INSERT INTO locos VALUES (?,?)',(address,json.dumps(loco)))
            if old_address != address:
                if old_address is not None:
                    self.speeds.pop(str(old_address),None)
                    self.functions.pop(str(old_address),None)
                if address is not None: self.speeds[str(address)] = {'speed':0,'direction':1}
            if old_address is not None: self.functions.pop(str(old_address), None)
            self._log(f'Roster entry {ident} updated')
            return self.snapshot()

    def create_roster(self, data):
        """Create an inventory entry, optionally mapping an operator-entered address."""
        name = data.get('name', '')
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise ValueError('Invalid train name')
        ident = name.strip()
        with self.lock:
            with self._db() as db:
                if db.execute('SELECT 1 FROM roster WHERE name=?', (ident,)).fetchone():
                    raise ValueError('Train name already exists')
                db.execute('INSERT INTO roster VALUES (?,?)', (ident, json.dumps({'name': ident})))
            try:
                return self.update_roster(ident, data)
            except Exception:
                with self._db() as db:
                    db.execute('DELETE FROM roster WHERE name=?', (ident,))
                raise

    def snapshot(self):
        with self.lock:
            return {'mode':'SIMULATION','hardware_connected':False,'track_power':self.track_power,'estop':self.estop,'locomotives':self._locos(),'roster':self._roster(),'points':self._points(),'sequences':self.sequences(),'speeds':self.speeds,'functions':self.functions,'events':self.events,'layout':self.layout()}
    def _address(self, address):
        if not any(l['address']==address for l in self._locos()): raise ValueError('Unknown locomotive address')
    def power(self, on):
        with self.lock:
            if on and self.estop: raise ValueError('Reset emergency stop before power on')
            self.track_power = bool(on)
            if not on:
                for item in self.speeds.values(): item['speed'] = 0
            self._log('Simulated track power ' + ('ON' if on else 'OFF'))
            return self.snapshot()
    def throttle(self, address, speed, direction):
        with self.lock:
            self._address(address)
            if not self.track_power or self.estop: raise ValueError('Track power off or emergency stop engaged')
            if not isinstance(speed,int) or isinstance(speed,bool) or speed<0 or speed>126 or direction not in (-1,1): raise ValueError('Invalid speed or direction')
            self.speeds[str(address)] = {'speed':speed,'direction':direction}
            self._log(f'Simulated locomotive {address}: speed {speed}, direction {direction}')
            return self.snapshot()
    def emergency_stop(self):
        with self.lock:
            self.estop = True
            self.track_power = False
            for item in self.speeds.values(): item['speed'] = 0
            self._log('EMERGENCY STOP: simulation power off; all speeds zero')
            return self.snapshot()
    def reset_emergency(self):
        with self.lock:
            self.estop = False
            self.track_power = False
            self._log('Emergency latch reset; power remains off')
            return self.snapshot()
    def point(self, ident, position):
        with self.lock:
            if position not in ('straight','diverging'): raise ValueError('Invalid point position')
            with self._db() as db:
                row = db.execute('SELECT data FROM points WHERE id=?',(ident,)).fetchone()
                if not row: raise ValueError('Unknown point')
                item = json.loads(row[0]); item['commanded']=position; item['verified']=None
                db.execute('UPDATE points SET data=? WHERE id=?',(json.dumps(item),ident))
            self._log(f'Simulated {ident} command: {position}; physical position unverified')
            return self.snapshot()
    def save_point(self, ident, label, device, output, address=None):
        if not isinstance(ident,str) or not ident.startswith('P') or not ident[1:].isdigit() or not 1 <= int(ident[1:]) <= 99 or ident != f'P{int(ident[1:])}': raise ValueError('Invalid point ID')
        if not isinstance(label,str) or not label.strip() or len(label) > 80 or not isinstance(device,str) or len(device) > 80 or (output is not None and (type(output) is not int or not 1 <= output <= 99)): raise ValueError('Invalid point details')
        if address is not None and (type(address) is not int or not 1 <= address <= 2044): raise ValueError('Invalid DCC accessory address (1–2044)')
        with self.lock, self._db() as db:
            if address is not None and any(p['id'] != ident and p.get('address') == address for p in self._points()):
                raise ValueError('DCC accessory address already assigned')
            row = db.execute('SELECT data FROM points WHERE id=?',(ident,)).fetchone()
            item = json.loads(row[0]) if row else {'id':ident,'commanded':'straight','verified':None}
            if item.get('address') != address: item['hardware_commanded'] = None
            item.update(label=label.strip(),device=device.strip(),output=output,address=address)
            db.execute('INSERT OR REPLACE INTO points VALUES (?,?)',(ident,json.dumps(item)))
        self._log(f'Point {ident} inventory saved; no hardware command sent')
        return self.snapshot()
    def record_hardware_point(self, ident, position):
        with self.lock, self._db() as db:
            row = db.execute('SELECT data FROM points WHERE id=?',(ident,)).fetchone()
            if not row: raise ValueError('Unknown point')
            item = json.loads(row[0]); item.update(commanded=position, hardware_commanded=position, verified=None)
            db.execute('UPDATE points SET data=? WHERE id=?',(json.dumps(item), ident))
        self._log(f'DCC accessory command sent for {ident}: {position}; physical position unverified')
        return self.snapshot()
    def delete_point(self, ident):
        with self.lock, self._db() as db:
            if not db.execute('DELETE FROM points WHERE id=?',(ident,)).rowcount: raise ValueError('Unknown point')
        self._log(f'Point {ident} removed from inventory; no hardware command sent')
        return self.snapshot()
    def function(self, address, key, on):
        with self.lock:
            loco = next((l for l in self._locos() if l['address']==address),None)
            if not loco or not mapped_function(loco, key): raise ValueError('Function not mapped for locomotive')
            if not self.track_power or self.estop: raise ValueError('Track power off or emergency stop engaged')
            self.functions.setdefault(str(address),{})[str(key)] = bool(on)
            self._log(f'Simulated F{key} for {address}: {"ON" if on else "OFF"}')
            return self.snapshot()
    def add_locomotive(self, data):
        with self.lock:
            try:
                address = data['address']; name = data['name']; decoder = data.get('decoder', ''); functions = data['functions']
                if not isinstance(address,int) or isinstance(address,bool) or not 1<=address<=10239 or not isinstance(name,str) or not name.strip() or not isinstance(decoder,str) or len(decoder)>120 or not isinstance(functions,list): raise ValueError()
                if any(not isinstance(f.get('key'),int) or not 0<=f['key']<=68 or not f.get('label') for f in functions): raise ValueError()
            except (KeyError,TypeError,AttributeError): raise ValueError('Invalid locomotive data')
            except ValueError: raise ValueError('Invalid locomotive data')
            item = {'name':name.strip(),'address':address,'decoder':decoder.strip(),'functions':functions,'class_name':data.get('class_name',''),'running_number':data.get('running_number',''),'sound_profile':data.get('sound_profile',''),'photo':data.get('photo',''),'notes':data.get('notes','')}
            try:
                with self._db() as db: db.execute('INSERT INTO locos VALUES (?,?)',(address,json.dumps(item)))
            except sqlite3.IntegrityError: raise ValueError('DCC address already exists')
            self._log(f'Locomotive {name} added to simulation registry')
            return self.snapshot()
    def layout(self):
        with self._db() as db: row = db.execute('SELECT data FROM layout WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {'name':'Workshop shelf layout','segments':[]}
    def sequences(self):
        with self.lock, self._db() as db:
            return [dict(json.loads(row[0]), id=row[1]) for row in db.execute('SELECT data,id FROM sequences ORDER BY id')]
    def save_sequence(self, ident, data):
        if not isinstance(ident, str) or not 1 <= len(ident) <= 64 or not all(c.isalnum() or c in '-_' for c in ident) or not ident.isascii():
            raise ValueError('Invalid sequence ID')
        if not isinstance(data, dict) or not isinstance(data.get('name'), str) or not 1 <= len(data['name'].strip()) <= 120:
            raise ValueError('Enter a sequence name')
        steps = data.get('steps')
        if not isinstance(steps, list) or len(steps) > 100:
            raise ValueError('A sequence needs a list of up to 100 steps')
        with self.lock:
            point_ids = {p['id'] for p in self._points()}
            roster_ids = {r['id'] for r in self._roster()}
            clean = []
            for step in steps:
                if not isinstance(step, dict) or step.get('kind') not in ('note', 'wait', 'point', 'move', 'loop', 'state', 'if_state', 'function'):
                    raise ValueError('Unknown sequence step')
                kind = step['kind']
                if kind == 'loop':
                    count, body = step.get('count'), step.get('steps')
                    if type(count) is not int or not 1 <= count <= 20 or not isinstance(body, list) or not body or len(body) > 100 or len(json.dumps(step)) > 20000:
                        raise ValueError('Invalid bounded loop')
                    clean.append({'kind': 'loop', 'count': count, 'steps': body})
                elif kind == 'state':
                    key, value = step.get('key'), step.get('value')
                    if not isinstance(key, str) or not 1 <= len(key) <= 40 or type(value) not in (str, bool, int) or isinstance(value, str) and len(value) > 80:
                        raise ValueError('Invalid state')
                    clean.append({'kind': 'state', 'key': key, 'value': value})
                elif kind == 'if_state':
                    key, value = step.get('key'), step.get('equals')
                    yes, no = step.get('then_steps'), step.get('else_steps', [])
                    if (not isinstance(key, str) or not 1 <= len(key) <= 40 or type(value) not in (str, bool, int) or
                        isinstance(value, str) and len(value) > 80 or not isinstance(yes, list) or not yes or
                        not isinstance(no, list) or len(yes) > 100 or len(no) > 100 or len(json.dumps(step)) > 20000):
                        raise ValueError('Invalid state branch')
                    clean.append({'kind': kind, 'key': key, 'equals': value, 'then_steps': yes, 'else_steps': no})
                elif kind == 'note':
                    label = step.get('label')
                    if not isinstance(label, str) or not 1 <= len(label.strip()) <= 200: raise ValueError('Enter a note')
                    clean.append({'kind': kind, 'label': label.strip()})
                elif kind == 'wait':
                    seconds = step.get('seconds')
                    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 3600: raise ValueError('Wait must be 1–3600 seconds')
                    clean.append({'kind': kind, 'seconds': seconds})
                elif kind == 'point':
                    if step.get('point_id') not in point_ids or step.get('position') not in ('straight', 'diverging'): raise ValueError('Choose a known point and position')
                    seconds = step.get('settle_seconds', 2)
                    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= 120: raise ValueError('Point settling wait must be 0–120 seconds')
                    clean.append({'kind': kind, 'point_id': step['point_id'], 'position': step['position'], 'settle_seconds': seconds})
                elif kind == 'function':
                    roster = next((r for r in self._roster() if r['id'] == step.get('roster_id')), None)
                    loco = next((l for l in self._locos() if roster and l['address'] == roster.get('address')), None)
                    mapping = mapped_function(loco, step.get('key')) if loco else None
                    mode = step.get('mode')
                    if not mapping or mode not in ('on', 'off', 'hold') or mapping['momentary'] and mode != 'hold':
                        raise ValueError('Choose a sourced mapped F0–F28 function; momentary requires hold')
                    seconds = step.get('seconds', 1)
                    if mode == 'hold' and (type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 120):
                        raise ValueError('Function hold must be 0.01–120 seconds')
                    clean.append({'kind': kind, 'roster_id': roster['id'], 'key': mapping['key'], 'mode': mode, 'seconds': seconds if mode == 'hold' else 0})
                else:
                    seconds, speed, distance = step.get('seconds'), step.get('speed'), step.get('distance_mm')
                    if (step.get('roster_id') not in roster_ids or step.get('direction') not in ('forward', 'reverse') or
                        type(speed) is not int or not 1 <= speed <= 126 or type(seconds) not in (int, float) or
                        not math.isfinite(seconds) or not 0 < seconds <= 3600 or
                        (distance is not None and (type(distance) not in (int, float) or not math.isfinite(distance) or not 0 < distance <= 100000))):
                        raise ValueError('Choose a train, direction, speed (1–126) and duration (1–3600 s)')
                    if type(step.get('use_calibration', False)) is not bool or step.get('use_calibration') and distance is None:
                        raise ValueError('Calibrated move requires distance_mm')
                    move = {'kind': kind, 'roster_id': step['roster_id'], 'direction': step['direction'], 'speed': speed, 'seconds': seconds, 'distance_mm': distance}
                    if step.get('use_calibration'): move['use_calibration'] = True
                    clean.append(move)
            result = {'id': ident, 'name': data['name'].strip(), 'steps': clean}
            with self._db() as db:
                db.execute('INSERT OR REPLACE INTO sequences VALUES (?,?)', (ident, json.dumps(result)))
            return result
    def delete_sequence(self, ident):
        with self.lock, self._db() as db:
            if not db.execute('DELETE FROM sequences WHERE id=?', (ident,)).rowcount: raise ValueError('Unknown sequence')
        return {'deleted': ident}
    def preview_sequence(self, ident):
        with self.lock, self._db() as db:
            row = db.execute('SELECT data FROM sequences WHERE id=?', (ident,)).fetchone()
            if not row: raise ValueError('Unknown sequence')
            data = json.loads(row[0])
            elapsed, timeline = 0, []
            for step in data['steps']:
                duration = step.get('settle_seconds', 2) if step['kind'] == 'point' else step.get('seconds', 0)
                timeline.append({**step, 'start_seconds': elapsed, 'end_seconds': elapsed + duration,
                                 'estimated_distance_mm': step.get('distance_mm') if step['kind'] == 'move' else None})
                elapsed += duration
            return {'id': ident, 'name': data['name'], 'duration_seconds': elapsed, 'steps': timeline,
                    'warning': 'Planning preview only. Distance is operator-entered, not measured. No commands are sent.'}
    def save_layout(self, data):
        if not isinstance(data,dict) or not isinstance(data.get('name'),str) or not data['name'].strip() or len(data['name'])>120 or not isinstance(data.get('segments'),list) or len(json.dumps(data))>100000: raise ValueError('Invalid layout')
        if data.get('diagramVersion') not in (None, 2): raise ValueError('Invalid diagram version')
        canvas = data.get('canvas', {'width': 900, 'height': 500})
        if not isinstance(canvas, dict) or any(type(canvas.get(key)) is not int or not low <= canvas[key] <= high for key, low, high in [('width', 900, 2400), ('height', 500, 1400)]):
            raise ValueError('Invalid canvas size')
        perimeter = data.get('perimeter')
        if perimeter is not None:
            if not isinstance(perimeter, list) or not 3 <= len(perimeter) <= 24:
                raise ValueError('Invalid perimeter')
            for vertex in perimeter:
                if not isinstance(vertex, dict) or any(type(vertex.get(key)) not in (int, float) or not math.isfinite(vertex[key]) or not 0 <= vertex[key] <= canvas[axis] for key, axis in [('x', 'width'), ('y', 'height')]):
                    raise ValueError('Invalid perimeter vertex')
        kinds = {'observed-main','observed-inner','observed-station','observed-siding','straight','short-straight','curve','wide-curve','left-point','right-point','curved-left-point','curved-right-point','y-point','three-way-point','diamond','single-slip','double-slip','buffer-stop','uncoupler','point-motor','pillar','peco-flex','roco-35900','tunnel-portal','bridge','level-crossing','elevated-line','shelf-outline','platform-pair','plan-label'}
        pieces = data.get('pieces', [])
        if not isinstance(pieces,list) or len(pieces)>400: raise ValueError('Invalid layout pieces')
        ids = set()
        for p in pieces:
            if not isinstance(p,dict) or not isinstance(p.get('id'),str) or not 1<=len(p['id'])<=80 or p['id'] in ids or p.get('kind') not in kinds: raise ValueError('Invalid layout piece')
            ids.add(p['id'])
            if any(type(p.get(key)) not in (int,float) or not math.isfinite(p[key]) or not low<=p[key]<=high for key,low,high in [('x',0,900),('y',0,500),('rotation',-360,360),('length',20,360),('curve',-200,200)]): raise ValueError('Invalid layout geometry')
            if p.get('kind') == 'plan-label' and (not isinstance(p.get('text'),str) or not 1<=len(p['text'].strip())<=100 or any(c in p['text'] for c in '<>')): raise ValueError('Invalid plan label')
        buildings = data.get('buildings', [])
        if not isinstance(buildings,list) or len(buildings)>100: raise ValueError('Invalid layout buildings')
        for b in buildings:
            if not isinstance(b,dict) or not isinstance(b.get('id'),str) or not 1<=len(b['id'])<=80 or b['id'] in ids: raise ValueError('Invalid building ID')
            ids.add(b['id'])
            if not isinstance(b.get('name'),str) or not 1<=len(b['name'].strip())<=80 or any(c in b['name'] for c in '<>'): raise ValueError('Invalid building name')
            if any(type(b.get(key)) not in (int,float) or not math.isfinite(b[key]) or not low<=b[key]<=high for key,low,high in [('x',0,900),('y',0,500),('width',20,360),('height',20,360),('rotation',-360,360)]): raise ValueError('Invalid building geometry')
        with self.lock:
            with self._db() as db: db.execute('INSERT OR REPLACE INTO layout VALUES (1,?)',(json.dumps(data),))
            self._log('Layout saved')
            return self.snapshot()
