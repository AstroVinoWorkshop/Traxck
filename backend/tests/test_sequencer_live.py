"""Simulation-only safety checks. No hardware connection or real station commands."""
import time
import json
import importlib
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from backend.simulator import Simulator
from backend.hardware import HardwareController
from backend.sequencer import Sequencer


def setup(tmp_path):
    sim = Simulator(tmp_path / 'rail.db')
    controller = HardwareController(sim, socket_factory=lambda *args: pytest.fail('hardware connection attempted'))
    runner = Sequencer(controller, sim)
    with sim._db() as db:
        db.execute('INSERT INTO locos VALUES (?,?)', (3, json.dumps({'name': 'Test locomotive', 'address': 3, 'functions': []})))
    sim.power(True)
    address = 3
    return sim, controller, runner, address


def until(runner, state, timeout=2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if runner.status()['state'] == state: return
        time.sleep(.01)
    assert runner.status()['state'] == state, runner.status()


def mapped_setup(tmp_path):
    sim, hw, runner, address = setup(tmp_path)
    roster = sim._roster()[0]
    mapping = [{'key': 1, 'label': 'Horn', 'momentary': True, 'source': 'Manual p2', 'confidence': 'manual'},
               {'key': 2, 'label': 'Light', 'momentary': False, 'source': 'Manual p3', 'confidence': 'verified'}]
    with sim._db() as db:
        db.execute('UPDATE locos SET data=? WHERE address=?',
                   (json.dumps({'name': roster['name'], 'address': address, 'decoder': roster['decoder'], 'functions': mapping}), address))
    return sim, hw, runner, address, roster['id']


def test_point_wait_precedes_command_and_cancel_skips_point(tmp_path, monkeypatch):
    sim, hw, runner, address = setup(tmp_path)
    calls = []
    original_throttle = hw.throttle
    monkeypatch.setattr(hw, 'throttle', lambda *args: (calls.append(('throttle', args[1])), original_throttle(*args)))
    monkeypatch.setattr(hw, 'point', lambda *args: calls.append(('point', args)))
    point = sim._points()[0]['id']
    actions = runner._compile([{'type': 'throttle', 'address': address, 'speed': 5, 'direction': 1, 'seconds': .01},
                               {'type': 'point', 'id': point, 'position': 'straight'}])
    assert actions[-1]['seconds'] == 2
    runner.start([{'type': 'point', 'id': point, 'position': 'straight', 'settle_seconds': .2}])
    runner.stop()
    assert not calls
    runner.start([{'type': 'throttle', 'address': address, 'speed': 5, 'direction': 1, 'seconds': .01},
                  {'type': 'point', 'id': point, 'position': 'straight', 'settle_seconds': .02}])
    until(runner, 'completed')
    assert calls.index(('throttle', 0)) < next(i for i, item in enumerate(calls) if item[0] == 'point')


def test_function_hold_off_on_and_cleanup(tmp_path, monkeypatch):
    sim, hw, runner, address, ident = mapped_setup(tmp_path)
    calls = []
    original = hw.function
    monkeypatch.setattr(hw, 'function', lambda *args: (calls.append(args), original(*args)))
    hold = {'kind': 'function', 'roster_id': ident, 'key': 1, 'mode': 'hold', 'seconds': .03}
    sim.save_sequence('fn-test', {'name': 'Functions', 'steps': [hold]})
    assert sim.preview_sequence('fn-test')['duration_seconds'] == .03
    runner.start([hold]); until(runner, 'completed')
    assert calls == [(address, 1, True), (address, 1, False)]
    calls.clear()
    runner.start([{'kind': 'function', 'roster_id': ident, 'key': 2, 'mode': 'on'},
                  {'kind': 'wait', 'seconds': .3}])
    while (address, 2, True) not in calls: time.sleep(.005)
    runner.stop()
    assert (address, 2, False) in calls
    with pytest.raises(ValueError, match='mapped'):
        runner._compile([{'kind': 'function', 'roster_id': ident, 'key': 28, 'mode': 'on'}])
    with pytest.raises(ValueError, match='momentary'):
        runner._compile([{'kind': 'function', 'roster_id': ident, 'key': 1, 'mode': 'on'}])


def test_function_explicit_off_and_error_release(tmp_path, monkeypatch):
    sim, hw, runner, address, ident = mapped_setup(tmp_path)
    calls = []
    original = hw.function
    monkeypatch.setattr(hw, 'function', lambda *args: (calls.append(args), original(*args)))
    runner.start([{'kind': 'function', 'roster_id': ident, 'key': 2, 'mode': 'on'},
                  {'kind': 'function', 'roster_id': ident, 'key': 2, 'mode': 'off'}])
    until(runner, 'completed')
    assert calls == [(address, 2, True), (address, 2, False)]
    calls.clear()
    monkeypatch.setattr(hw, 'point', lambda *args: (_ for _ in ()).throw(ConnectionError('injected point failure')))
    runner.start([{'kind': 'function', 'roster_id': ident, 'key': 2, 'mode': 'on'},
                  {'kind': 'point', 'id': sim._points()[0]['id'], 'position': 'straight', 'settle_seconds': 0}])
    until(runner, 'error')
    assert calls == [(address, 2, True), (address, 2, False)]
    assert 'point failure' in runner.status()['error']


def test_run_pause_resume_stop_blocks_manual(tmp_path):
    sim, hw, runner, address = setup(tmp_path)
    runner.start([{'type': 'throttle', 'address': address, 'speed': 35, 'direction': 1, 'seconds': 2}])
    until(runner, 'running')
    with pytest.raises(ValueError, match='Sequence running'):
        hw.throttle(address, 20, 1)
    runner.pause()
    until(runner, 'paused')
    assert sim.speeds[str(address)]['speed'] == 0
    runner.resume()
    assert runner.stop()['state'] == 'stopped'
    assert sim.speeds[str(address)]['speed'] == 0
    hw.throttle(address, 0, 1)


def test_bounded_loop_and_calibration(tmp_path):
    sim, hw, runner, address = setup(tmp_path)
    runner.calibrate(address, 1, 20, 100)
    actions = runner._compile([{'type': 'loop', 'count': 2, 'steps': [
        {'type': 'throttle', 'address': address, 'direction': 1, 'speed': 20,
         'distance_mm': 2, 'use_calibration': True}]}])
    assert len(actions) == 2
    assert actions[0]['seconds'] == pytest.approx(.02)
    runner.start([{'type': 'loop', 'count': 2, 'steps': [
        {'type': 'throttle', 'address': address, 'direction': 1, 'speed': 20,
         'distance_mm': 2, 'use_calibration': True}]}])
    until(runner, 'completed')
    assert sim.speeds[str(address)]['speed'] == 0
    with pytest.raises(ValueError):
        runner._compile([{'type': 'loop', 'count': 21, 'steps': [{'type': 'wait', 'seconds': 1}]}])
    with pytest.raises(ValueError):
        runner._compile([{'type': 'wait', 'seconds': float('nan')}])
    with pytest.raises(ValueError):
        runner._compile([{'type': 'loop', 'count': 20, 'steps': [{'type': 'wait', 'seconds': 120}]}])


def test_state_branches_are_deterministic_and_bounded(tmp_path):
    sim, hw, runner, address = setup(tmp_path)
    steps = [{'type': 'state', 'key': 'phase', 'value': 'departure'},
             {'type': 'if_state', 'key': 'phase', 'equals': 'departure',
              'then_steps': [{'type': 'wait', 'seconds': .02}],
              'else_steps': [{'type': 'wait', 'seconds': 9}]}]
    assert runner._compile(steps)[-1]['seconds'] == .02
    sim.save_sequence('branch', {'name': 'Branch', 'steps': [{**s, 'kind': s['type']} for s in steps]})
    with pytest.raises(ValueError, match='exceeds 600 seconds'):
        runner._compile([{'type': 'loop', 'count': 20, 'steps': [
            {'type': 'if_state', 'key': 'phase', 'equals': 'departure',
             'then_steps': [{'type': 'wait', 'seconds': 1}],
             'else_steps': [{'type': 'wait', 'seconds': 40}]}]}])


def test_emergency_and_failed_stop_are_not_reported_safe(tmp_path, monkeypatch):
    sim, hw, runner, address = setup(tmp_path)
    runner.start([{'type': 'throttle', 'address': address, 'speed': 30, 'direction': 1, 'seconds': 2}])
    until(runner, 'running')
    hw.emergency_stop()
    until(runner, 'error')
    assert 'physical power cut-off' in runner.status()['error']
    assert sim.speeds.get(str(address), {'speed': 0})['speed'] == 0

    sim.reset_emergency()
    sim.power(True)
    original = hw.throttle
    def fail_zero(addr, speed, direction):
        if speed == 0: raise ConnectionError('mock write failure')
        return original(addr, speed, direction)
    monkeypatch.setattr(hw, 'throttle', fail_zero)
    runner.start([{'type': 'throttle', 'address': address, 'speed': 30, 'direction': 1, 'seconds': 2}])
    deadline = time.monotonic() + 2
    while sim.speeds.get(str(address), {}).get('speed') != 30 and time.monotonic() < deadline:
        time.sleep(.01)
    assert sim.speeds[str(address)]['speed'] == 30
    with pytest.raises(ConnectionError, match='physical power cut-off'):
        runner.stop()
    assert runner.status()['state'] == 'error'


def test_mock_adapter_rejects_manual_commands_during_run(tmp_path):
    sim, hw, runner, address = setup(tmp_path)
    class FakeAdapter:
        def __init__(self): self.sent = []
        def send(self, frame): self.sent.append(frame)
        def close(self): pass
    adapter = FakeAdapter()
    hw.adapter, hw.mode, hw.power_on = adapter, 'HARDWARE', True
    runner.start([{'type': 'throttle', 'address': address, 'speed': 30, 'direction': 1, 'seconds': 2}])
    until(runner, 'running')
    with pytest.raises(ValueError, match='Sequence running'): hw.throttle(address, 10, 1)
    with pytest.raises(ValueError, match='Sequence running'): hw.point('missing', 'straight')
    # Wait for the fake adapter's throttle dispatch; 'running' is set first.
    end = time.monotonic() + 2
    while '<t 3 30 1>' not in adapter.sent and time.monotonic() < end:
        time.sleep(.01)
    assert '<t 3 30 1>' in adapter.sent
    assert runner.stop()['state'] == 'stopped'
    assert '<t 3 0 1>' in adapter.sent


def test_power_off_still_attempted_after_stop_failure(tmp_path, monkeypatch):
    sim, hw, runner, address = setup(tmp_path)
    class FakeAdapter:
        def __init__(self): self.sent = []
        def send(self, frame):
            self.sent.append(frame)
            if frame == '<t 3 0 1>': raise OSError('mock zero-speed failure')
        def confirm_power(self, on): return '<p0>'
        def close(self): pass
    adapter = FakeAdapter()
    hw.adapter, hw.mode, hw.power_on = adapter, 'HARDWARE', True
    api = importlib.import_module('backend.app')
    monkeypatch.setattr(api, 'hardware', hw)
    monkeypatch.setattr(api, 'sequencer', runner)
    monkeypatch.setenv('WORKSHOP_OPERATOR_TOKEN', 'test-only-token')
    monkeypatch.delenv('WORKSHOP_LAN_SUBNET', raising=False)
    request = Request({'type': 'http', 'scheme': 'http', 'server': ('testserver', 80),
                       'client': ('127.0.0.1', 1111), 'path': '/api/power',
                       'headers': [(b'x-operator-token', b'test-only-token')]})
    runner.start([{'type': 'throttle', 'address': address, 'speed': 30, 'direction': 1, 'seconds': 2}])
    deadline = time.monotonic() + 2
    while '<t 3 30 1>' not in adapter.sent and time.monotonic() < deadline: time.sleep(.01)
    assert '<t 3 30 1>' in adapter.sent
    with pytest.raises(HTTPException, match='physical power cut-off'):
        api.power(api.Power(on=False), request)
    assert '<0>' in adapter.sent
    assert runner.status()['state'] == 'error'


@pytest.mark.parametrize('route', ['disconnect', 'mode', 'emergency'])
def test_control_transitions_cancel_runner(tmp_path, monkeypatch, route):
    sim, hw, runner, address = setup(tmp_path)
    api = importlib.import_module('backend.app')
    monkeypatch.setattr(api, 'hardware', hw)
    monkeypatch.setattr(api, 'sequencer', runner)
    monkeypatch.setenv('WORKSHOP_OPERATOR_TOKEN', 'test-only-token')
    monkeypatch.delenv('WORKSHOP_LAN_SUBNET', raising=False)
    request = Request({'type': 'http', 'scheme': 'http', 'server': ('testserver', 80),
                       'client': ('127.0.0.1', 1111), 'path': '/api/hardware/' + route,
                       'headers': [(b'x-operator-token', b'test-only-token')]})
    runner.start([{'type': 'throttle', 'address': address, 'speed': 30, 'direction': 1, 'seconds': 2}])
    until(runner, 'running')
    if route == 'disconnect': api.disconnect(request)
    elif route == 'mode': api.mode(api.Mode(mode='SIMULATION'), request)
    else: api.emergency_stop(request)
    assert runner.status()['state'] == 'stopped'
    assert sim.speeds.get(str(address), {'speed': 0})['speed'] == 0


def test_disconnect_reports_track_power_failure_with_fake_adapter(tmp_path):
    sim, hw, runner, address = setup(tmp_path)
    class FakeAdapter:
        def send(self, frame): raise OSError('mock power-off failure')
        def close(self): pass
    hw.adapter, hw.mode, hw.power_on = FakeAdapter(), 'HARDWARE', True
    with pytest.raises(ConnectionError, match='physical power cut-off'):
        hw.disconnect()
    assert hw.adapter is None
    assert 'physical power cut-off' in hw.error
