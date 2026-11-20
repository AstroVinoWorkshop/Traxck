import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from backend.simulator import Simulator
from backend.hardware import HardwareController
from backend.tests.test_hardware import FakeSocket


@pytest.fixture
def rig():
    with tempfile.TemporaryDirectory() as root:
        sim = Simulator(Path(root) / 'test.db')
        sock = FakeSocket()
        hw = HardwareController(sim, socket_factory=lambda *args: sock)
        from backend import app as module
        old = module.sim, module.hardware, module.require_inventory
        module.sim, module.hardware, module.require_inventory = sim, hw, lambda request: None
        with patch.dict('os.environ', {'WORKSHOP_OPERATOR_TOKEN': 'test-secret'}):
            yield sim, hw, sock, TestClient(module.app)
        hw.disconnect()
        module.sim, module.hardware, module.require_inventory = old


def prepare(sim, hw):
    sim.update_roster('Steam locomotive E', {'address': 77, 'decoder': 'operator-verified', 'functions': []})
    hw.configure({'host': 'dcc-ex.local', 'port': 2560})
    hw.connect()
    hw.set_mode('HARDWARE')
    hw.adapter.connection.replies = [b'<p0>']
    hw.power(False)  # fake station acknowledgement; never a physical station
    hw.adapter.connection.sent.clear()


def test_cv_profile_persists_without_changing_readback_or_other_roster(rig):
    sim, hw, sock, client = rig
    url = '/api/roster/Steam locomotive E/cvs/29'
    assert client.put(url, json={'value': 34}).status_code == 200
    assert sock.sent == []
    assert client.get('/api/roster/Steam locomotive E/cvs').json()['stored_values'] == {'29': 34}
    assert next(r for r in client.get('/api/state').json()['roster'] if r['id'] == 'Steam locomotive E')['cv_values'] == {'29': 34}
    assert Simulator(sim.path).get_cv_values('Steam locomotive E') == {'29': 34}
    assert sim.get_cv_values('Steam locomotive A') == {}
    assert client.delete(url).status_code == 200
    assert sim.get_cv_values('Steam locomotive E') == {}


@pytest.mark.parametrize('cv,value', [(0,1),(1025,1),(1,-1),(1,256),(1,True),(1,'3')])
def test_invalid_cv_or_value_does_not_mutate(rig, cv, value):
    sim, hw, sock, client = rig
    assert client.put(f'/api/roster/Steam locomotive E/cvs/{cv}', json={'value': value}).status_code in (400,422)
    assert sim.get_cv_values('Steam locomotive E') == {}
    assert sock.sent == []


def test_connected_unverified_main_power_cannot_program(rig):
    sim, hw, sock, client = rig
    sim.update_roster('Steam locomotive E', {'address': 77, 'decoder': 'operator-verified', 'functions': []})
    hw.configure({'host': 'dcc-ex.local', 'port': 2560})
    hw.connect(); hw.set_mode('HARDWARE')
    client.headers['X-Operator-Token'] = 'test-secret'
    response = client.post('/api/roster/Steam locomotive E/cvs/3/read', json={'programming_track_confirmed': True})
    assert response.status_code == 400
    assert sock.sent == []


def test_unvalidated_programming_track_blocks_both_operations_without_commands(rig):
    sim, hw, sock, client = rig
    prepare(sim, hw)
    client.headers['X-Operator-Token'] = 'test-secret'
    for operation, body in [('read', {'programming_track_confirmed': True}),
                            ('write', {'programming_track_confirmed': True, 'value': 42})]:
        response = client.post(f'/api/roster/Steam locomotive E/cvs/3/{operation}', json=body)
        assert response.status_code == 400
        assert 'disabled' in response.json()['detail']
        assert sock.sent == []


@pytest.mark.skip(reason='Programming-track hardware not validated; retain for future re-enablement')
def test_live_programming_requires_all_gates_and_never_auto_powers(rig):
    sim, hw, sock, client = rig
    url = '/api/roster/Steam locomotive E/cvs/3/read'
    body = {'programming_track_confirmed': True}
    assert client.post(url, json=body).status_code == 401
    client.headers['X-Operator-Token'] = 'test-secret'
    assert client.post(url, json=body).status_code == 400
    prepare(sim, hw)
    assert client.post(url, json={'programming_track_confirmed': False}).status_code == 400
    hw.power_on = True
    assert client.post(url, json=body).status_code == 400
    hw.power_on = False
    hw.speeds['77'] = {'speed': 2, 'direction': 1}
    assert client.post(url, json=body).status_code == 400
    hw.speeds['77']['speed'] = 0
    sock.replies = [b'<v 3 42>']
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    assert response.json()['source'] == 'read_back'
    assert response.json()['value'] == 42
    assert sock.sent == [b'<R 3>\n']
    assert sim.get_cv_values('Steam locomotive E') == {}


@pytest.mark.skip(reason='Programming-track hardware not validated; retain for future re-enablement')
def test_write_ack_is_not_a_stored_value(rig):
    sim, hw, sock, client = rig
    prepare(sim, hw)
    client.headers['X-Operator-Token'] = 'test-secret'
    sim.set_cv_value('Steam locomotive E', 4, 11)
    sock.replies = [b'<r 4 13>']
    response = client.post('/api/roster/Steam locomotive E/cvs/4/write', json={'value': 13, 'programming_track_confirmed': True})
    assert response.status_code == 200, response.text
    assert response.json()['source'] == 'write_ack'
    assert sock.sent == [b'<W 4 13>\n']
    assert sim.get_cv_values('Steam locomotive E') == {'4': 11}


@pytest.mark.parametrize('reply', [b'<v 4 3>', b'<v 3 -1>', b'<v 3 256>', b'<r 3 2>', b'<v 3 02>', b'<v 3 2x>', b'<v 3 2', b'', b'<v 3 2>\n<v 3 9>'])
@pytest.mark.skip(reason='Programming-track hardware not validated; retain for future re-enablement')
def test_bad_or_missing_read_reply_fails_closed(rig, reply):
    sim, hw, sock, client = rig
    prepare(sim, hw)
    client.headers['X-Operator-Token'] = 'test-secret'
    sock.replies = [reply] if reply else []
    response = client.post('/api/roster/Steam locomotive E/cvs/3/read', json={'programming_track_confirmed': True})
    assert response.status_code == 503, response.text
    assert not hw.state()['hardware_connected']
    assert sim.get_cv_values('Steam locomotive E') == {}


@pytest.mark.skip(reason='Programming-track hardware not validated; retain for future re-enablement')
def test_mismatched_write_ack_fails_closed(rig):
    sim, hw, sock, client = rig
    prepare(sim, hw)
    client.headers['X-Operator-Token'] = 'test-secret'
    sock.replies = [b'<r 3 42>']
    response = client.post('/api/roster/Steam locomotive E/cvs/3/write', json={'value': 43, 'programming_track_confirmed': True})
    assert response.status_code == 503
    assert not hw.state()['hardware_connected']
