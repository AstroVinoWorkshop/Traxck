"""Read-only checks for the workshop operator network boundary.

Network addresses below are synthetic test fixtures, not deployment settings.
The LAN subnet is invented; the example.invalid hostname and RFC 5737
public address are reserved for documentation. The 100.100.101.x values
exercise CGNAT/Tailscale-range logic and are not connected to a network.
"""
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app import app


class OperatorNetworkTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'WORKSHOP_LAN_SUBNET': '10.77.88.0/24',
            'WORKSHOP_TAILSCALE_IP': '100.100.101.102',
            'WORKSHOP_TAILSCALE_HOSTNAME': 'railway.example.invalid',
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def status(self, peer, host, origin=None):
        headers = {'Host': host}
        if origin:
            headers['Origin'] = origin
        with TestClient(app, client=(peer, 43210)) as client:
            return client.get('/api/hardware', headers=headers).status_code

    def test_pinned_tailscale_dns_name(self):
        self.assertEqual(self.status('100.100.101.105', 'railway.example.invalid:8768'), 200)
        self.assertEqual(self.status('100.100.101.105', '100.100.101.102:8768'), 200)
        self.assertEqual(self.status('10.77.88.27', '10.77.88.10:8768'), 200)

    def test_rejects_untrusted_hosts_and_peers(self):
        self.assertEqual(self.status('100.100.101.105', 'evil.example:8768'), 403)
        self.assertEqual(self.status('100.100.101.105', 'railway.example.invalid.evil.example:8768'), 403)
        self.assertEqual(self.status('203.0.113.2', 'railway.example.invalid:8768'), 403)
        self.assertEqual(self.status('10.77.88.27', 'railway.example.invalid:8768'), 403)
        self.assertEqual(self.status('100.100.101.105', 'railway.example.invalid:8768', 'http://evil.example'), 403)

    def test_dns_name_requires_explicit_configuration(self):
        with patch.dict(os.environ, {'WORKSHOP_TAILSCALE_HOSTNAME': ''}):
            self.assertEqual(self.status('100.100.101.105', 'railway.example.invalid:8768'), 403)


if __name__ == '__main__':
    unittest.main()
