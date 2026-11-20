from pathlib import Path
from fastapi.testclient import TestClient
from backend import app as api
from backend.simulator import Simulator


def test_create_inventory_without_address_and_preserve_on_restart(tmp_path, monkeypatch):
    sim = Simulator(tmp_path / 'railway.db')
    monkeypatch.setattr(api, 'sim', sim)
    monkeypatch.setattr(api.hardware, 'sim', sim)
    client = TestClient(api.app, client=('100.100.101.105', 54321))
    payload = {'name': 'New shunter', 'address': None, 'class_name': '08', 'running_number': '123', 'decoder': '', 'functions': []}
    response = client.post('/api/roster', json=payload)
    assert response.status_code == 200, response.text
    created = next(item for item in response.json()['roster'] if item['name'] == 'New shunter')
    assert created['address'] is None
    assert created['class_name'] == '08'
    assert all(item['name'] != 'New shunter' for item in response.json()['locomotives'])
    assert next(item for item in Simulator(tmp_path / 'railway.db').snapshot()['roster'] if item['id'] == created['id'])['address'] is None
    assert client.post('/api/roster', json=payload).status_code == 400
    remote = TestClient(api.app, client=('203.0.113.25', 54321))
    assert remote.post('/api/roster', json={**payload, 'name': 'Unauthorized'}).status_code == 403


def test_registry_has_add_action_and_no_duplicate_address_panel():
    source = (Path(__file__).resolve().parents[2] / 'frontend/src/main.tsx').read_text()
    assert 'Add locomotive' in source
    assert 'Configured locomotive addresses' not in source
