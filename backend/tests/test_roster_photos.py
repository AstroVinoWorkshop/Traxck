import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend import app as api
from backend.simulator import Simulator


class RosterPhotoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sim = Simulator(Path(self.tmp.name) / 'workshop.db')
        self.original_sim = api.sim
        api.sim = self.sim
        self.original_hardware_sim = api.hardware.sim
        api.hardware.sim = self.sim
        self.original_photo_dir = getattr(api, 'PHOTO_DIR', None)
        api.PHOTO_DIR = Path(self.tmp.name) / 'photos'
        self.client = TestClient(api.app, client=('100.100.101.105', 54321))
        self.remote = TestClient(api.app, client=('203.0.113.25', 54321))
        picture = Image.new('RGB', (3, 2), '#184a77')
        out = io.BytesIO()
        picture.save(out, format='PNG')
        self.png = out.getvalue()
        self.headers = {'Content-Type': 'image/png'}

    def tearDown(self):

        api.PHOTO_DIR = self.original_photo_dir
        api.hardware.sim = self.original_hardware_sim
        api.sim = self.original_sim
        self.tmp.cleanup()

    def test_upload_from_tailnet_needs_no_token_but_rejects_remote_and_unknown_roster_id(self):
        path = '/api/roster/Steam%20locomotive%20A/photo'
        self.assertEqual(self.remote.put(path, content=self.png, headers=self.headers).status_code, 403)
        self.assertEqual(self.remote.delete(path).status_code, 403)
        self.assertEqual(self.client.put('/api/roster/Unknown/photo', content=self.png, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get('/api/state').json()['roster'][0].get('photo'), None)

    def test_upload_persists_across_restart_and_serves_image(self):
        response = self.client.put('/api/roster/Steam%20locomotive%20A/photo', content=self.png, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        item = response.json()['roster'][0]
        self.assertTrue(item['photo'].startswith('/user-photos/'))
        image = self.client.get(item['photo'])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers['content-type'], 'image/jpeg')
        self.assertEqual(Image.open(io.BytesIO(image.content)).size, (3, 2))
        self.assertEqual(Simulator(self.sim.path).snapshot()['roster'][0]['photo'], item['photo'])

    def test_rejects_non_image_and_oversize_without_changing_existing_photo(self):
        path = '/api/roster/Steam%20locomotive%20A/photo'
        original = self.client.put(path, content=self.png, headers=self.headers).json()['roster'][0]['photo']
        self.assertEqual(self.client.put(path, content=b'<script>alert(1)</script>', headers=self.headers).status_code, 400)
        self.assertEqual(self.client.put(path, content=b'x' * (api.MAX_IMAGE_BYTES + 1), headers=self.headers).status_code, 413)
        self.assertEqual(self.client.get('/api/state').json()['roster'][0]['photo'], original)
        self.assertEqual(self.client.get(original).status_code, 200)

    def test_replace_and_restore_default_removes_old_file(self):
        path = '/api/roster/Steam%20locomotive%20A/photo'
        old = self.client.put(path, content=self.png, headers=self.headers).json()['roster'][0]['photo']
        new = self.client.put(path, content=self.png, headers=self.headers).json()['roster'][0]['photo']
        self.assertNotEqual(old, new)
        self.assertEqual(self.client.get(old).status_code, 404)
        restored = self.client.delete(path, headers=self.headers)
        self.assertEqual(restored.status_code, 200)
        self.assertIsNone(restored.json()['roster'][0].get('photo'))
        self.assertEqual(self.client.get(new).status_code, 404)
