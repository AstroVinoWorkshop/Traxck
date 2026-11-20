import pytest
from fastapi.testclient import TestClient
from backend import app as module
from backend.simulator import Simulator
from backend.hardware import HardwareController


def test_roster_edit_persists_and_does_not_reseed(tmp_path):
    path = tmp_path / 'workshop.db'
    sim = Simulator(path)
    sim.update_roster('Steam locomotive E', {'name':'My Steam locomotive E','class_name':'A4','running_number':'4468','decoder':'Unknown','notes':'Test','address':None,'functions':[]})
    item = next(i for i in Simulator(path).snapshot()['roster'] if i['id'] == 'Steam locomotive E')
    assert item['name'] == 'My Steam locomotive E'
    assert item['running_number'] == '4468'
    assert len(Simulator(path).snapshot()['roster']) == 8
    assert Simulator(path).snapshot()['locomotives'] == []


def test_verified_address_and_functions_edit_and_reject_duplicate(tmp_path):
    sim = Simulator(tmp_path / 'workshop.db')
    sim.update_roster('Steam locomotive E', {'name':'Steam locomotive E','address':21,'decoder':'ESU','functions':[{'key':0,'label':'Light','momentary':False,'source':'Test fixture','confidence':'verified'}]})
    assert sim.snapshot()['locomotives'][0]['roster_id'] == 'Steam locomotive E'
    sim.update_roster('Steam locomotive E', {'name':'Steam locomotive E','address':22,'decoder':'ESU','functions':[{'key':0,'label':'Light','momentary':False,'source':'Test fixture','confidence':'verified'}]})
    assert [l['address'] for l in sim.snapshot()['locomotives']] == [22]
    assert '21' not in sim.snapshot()['speeds']
    sim.update_roster('Steam locomotive A', {'name':'Steam locomotive A','address':23,'decoder':'ESU','functions':[]})
    with pytest.raises(ValueError, match='already exists'):
        sim.update_roster('Steam locomotive A', {'name':'Steam locomotive A','address':22,'decoder':'ESU','functions':[]})
    assert len(sim.snapshot()['locomotives']) == 2


def test_address_change_rejects_moving_but_metadata_allowed(tmp_path):
    sim = Simulator(tmp_path / 'workshop.db')
    data = {'name':'Steam locomotive E','address':21,'decoder':'ESU','functions':[]}
    sim.update_roster('Steam locomotive E', data)
    sim.power(True)
    sim.throttle(21, 8, 1)
    with pytest.raises(ValueError, match='Stop and switch power off'):
        sim.update_roster('Steam locomotive E', {**data,'address':22})
    sim.update_roster('Steam locomotive E', {**data,'notes':'Running'})
    assert sim.snapshot()['speeds']['21']['speed'] == 8


def test_local_roster_edit_needs_no_number_or_token_but_remote_write_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'sim', Simulator(tmp_path / 'workshop.db'))
    monkeypatch.setattr(module, 'hardware', HardwareController(module.sim))
    payload = {'name':'Steam locomotive E','address':None,'decoder':'','functions':[]}
    local = TestClient(module.app, client=('127.0.0.1', 54321))
    tailnet = TestClient(module.app, client=('100.100.101.105', 54321))
    remote = TestClient(module.app, client=('203.0.113.25', 54321))
    assert local.put('/api/roster/Steam locomotive E', json=payload).status_code == 200
    assert tailnet.put('/api/roster/Steam locomotive E', json=payload).status_code == 200
    assert remote.put('/api/roster/Steam locomotive E', json=payload).status_code == 403
    assert remote.post('/api/locomotives', json={**payload,'address':24}).status_code == 403
    assert remote.put('/api/layout', json={'name':'test','segments':[]}).status_code == 403
    module.hardware.mode = 'HARDWARE'
    module.hardware.power_on = True
    assert local.put('/api/roster/Steam locomotive E',json={**payload,'address':23}).status_code == 400


def test_roster_address_can_be_saved_without_decoder(tmp_path):
    sim = Simulator(tmp_path / 'workshop.db')
    sim.update_roster('Steam locomotive E', {'name': 'Steam locomotive E', 'address': 600, 'decoder': '', 'functions': []})
    saved = Simulator(tmp_path / 'workshop.db').snapshot()
    assert next(l for l in saved['locomotives'] if l['address'] == 600)['decoder'] == ''
    assert next(r for r in saved['roster'] if r['id'] == 'Steam locomotive E')['address'] == 600


def test_direct_locomotive_can_be_added_without_decoder(tmp_path):
    sim = Simulator(tmp_path / 'workshop.db')
    sim.add_locomotive({'name': 'Test', 'address': 601, 'functions': []})
    assert next(l for l in sim.snapshot()['locomotives'] if l['address'] == 601)['decoder'] == ''
