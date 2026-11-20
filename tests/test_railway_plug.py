import os
import unittest
import tempfile
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend import railway_plug


class PlugTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(FastAPI())
        self.client.app.include_router(railway_plug.router)
        self.config_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.config_dir.cleanup)
        self.env = patch.dict(os.environ, {'RAILWAY_HA_TOKEN': 'test', 'RAILWAY_HA_URL': 'http://ha', 'RAILWAY_PLUG_ENTITY_ID': 'switch.model_railway', 'RAILWAY_PLUG_CONFIG_FILE': self.config_dir.name + '/plug.json'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        from backend import app as app_module
        self.operator = patch.object(app_module, 'require_inventory')
        self.operator.start()
        self.addCleanup(self.operator.stop)

    def test_denies_untrusted_peer(self):
        from backend import app as app_module
        with patch.object(app_module, 'require_inventory', side_effect=__import__('fastapi').HTTPException(403, 'Denied')):
            with patch.object(railway_plug, '_ha') as ha:
                response = self.client.post('/api/railway-plug', json={'on': True, 'confirmed': True})
        self.assertEqual(response.status_code, 403)
        ha.assert_not_called()

    def test_missing_credentials_disables_plug(self):
        with patch.dict(os.environ, {'RAILWAY_HA_TOKEN': ''}):
            result = self.client.get('/api/railway-plug').json()
        self.assertFalse(result['configured'])
        self.assertFalse(result['available'])

    def test_unique_name_discovery_and_ambiguous_refusal(self):
        with patch.dict(os.environ, {'RAILWAY_PLUG_ENTITY_ID': ''}):
            with patch.object(railway_plug, '_ha', return_value=[{'entity_id': 'switch.model_railway', 'state': 'off', 'attributes': {'friendly_name': 'Model Railway'}}]):
                self.assertEqual(self.client.get('/api/railway-plug').json()['entity_id'], 'switch.model_railway')
            with patch.object(railway_plug, '_ha', return_value=[]):
                self.assertFalse(self.client.get('/api/railway-plug').json()['available'])

    def test_off_to_on_verified(self):
        calls = []
        def ha(method, path, token, url, data=None):
            calls.append((method, path, data))
            return {'entity_id': 'switch.model_railway', 'state': 'on' if len(calls) == 3 else 'off'} if method == 'GET' else []
        with patch.object(railway_plug, '_ha', side_effect=ha):
            response = self.client.post('/api/railway-plug', json={'on': True, 'confirmed': True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['on'])
        self.assertEqual(calls[1], ('POST', 'services/switch/turn_on', {'entity_id': 'switch.model_railway'}))

    def test_refuses_blind_command_and_unconfirmed(self):
        with patch.object(railway_plug, '_ha', return_value={'entity_id': 'switch.model_railway', 'state': 'unavailable'}):
            self.assertEqual(self.client.post('/api/railway-plug', json={'on': True, 'confirmed': True}).status_code, 502)
        self.assertEqual(self.client.post('/api/railway-plug', json={'on': True, 'confirmed': False}).status_code, 400)
        self.assertEqual(self.client.post('/api/railway-plug', headers={'Origin': 'https://evil.example'}, json={'on': True, 'confirmed': True}).status_code, 403)

    def test_setup_persists_without_exposing_token_or_switching(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {'RAILWAY_PLUG_CONFIG_FILE': temp + '/plug.json'}):
                with patch.object(railway_plug, '_ha') as ha:
                    saved = self.client.put('/api/railway-plug/config', json={'url': 'http://ha.local:8123', 'entity_id': 'switch.railway', 'token': 'private-key'})
                    self.assertEqual(saved.status_code, 200)
                    self.assertNotIn('private-key', str(saved.json()))
                    self.assertEqual(saved.json()['entity_id'], 'switch.railway')
                    self.assertTrue(saved.json()['credential_configured'])
                    self.assertEqual(os.stat(temp + '/plug.json').st_mode & 0o777, 0o600)
                    self.assertEqual(self.client.get('/api/railway-plug/config').json(), saved.json())
                    self.assertEqual(railway_plug._settings(), ('http://ha.local:8123', 'private-key', 'switch.railway'))
                    self.client.put('/api/railway-plug/config', json={'url': 'http://ha.local:8123', 'entity_id': 'light.railway', 'token': ''})
                    self.assertEqual(railway_plug._settings()[1:], ('private-key', 'light.railway'))
                    ha.assert_not_called()

    def test_setup_validation_and_peer_restriction(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'RAILWAY_PLUG_CONFIG_FILE': temp + '/plug.json'}):
            for url, entity in [('file:///etc/passwd', 'switch.railway'), ('http://ha.local', 'sensor.railway'), ('http://user:pass@ha.local', 'switch.railway')]:
                self.assertEqual(self.client.put('/api/railway-plug/config', json={'url': url, 'entity_id': entity, 'token': 'x'}).status_code, 422)
            self.assertEqual(self.client.put('/api/railway-plug/config', headers={'Origin': 'https://evil.example'}, json={'url':'http://ha.local','entity_id':'switch.railway','token':'x'}).status_code, 403)
            self.assertFalse(os.path.exists(temp + '/plug.json'))

if __name__ == '__main__': unittest.main()
