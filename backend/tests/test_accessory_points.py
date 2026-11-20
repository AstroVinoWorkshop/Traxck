"""Accessory commands use only a simulated socket; never live hardware."""
import json
import tempfile
import unittest
from pathlib import Path
from backend.simulator import Simulator
from backend.hardware import HardwareController

class FakeSocket:
    def __init__(self): self.sent = []; self.replies = []
    def settimeout(self, value): pass
    def sendall(self, payload): self.sent.append(payload)
    def recv(self, size):
        if not self.replies: raise TimeoutError('no confirmation')
        return self.replies.pop(0)
    def close(self): pass


class AccessoryPointsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sim = Simulator(Path(self.tmp.name) / 'rail.db')
        self.sock = FakeSocket()
        self.hw = HardwareController(self.sim, socket_factory=lambda *args: self.sock)
    def tearDown(self):
        self.hw.disconnect()
        self.tmp.cleanup()
    def item(self, ident):
        return next(p for p in self.sim.snapshot()['points'] if p['id'] == ident)

    def test_eight_independent_unconfigured_points_and_persistence(self):
        self.assertEqual([p['id'] for p in self.sim.snapshot()['points']], [f'P{i}' for i in range(1, 9)])
        self.assertTrue(all(p['address'] is None and p.get('hardware_commanded') is None for p in self.sim.snapshot()['points']))
        self.sim.save_point('P2', 'Upper yard', 'DCC decoder', None, 112)
        self.sim.save_point('P6', 'Lower loop', 'DCC decoder', None, 113)
        fresh = Simulator(self.sim.path)
        self.assertEqual(next(p for p in fresh.snapshot()['points'] if p['id'] == 'P2')['address'], 112)
        self.assertEqual(next(p for p in fresh.snapshot()['points'] if p['id'] == 'P6')['label'], 'Lower loop')
        self.assertIsNone(next(p for p in fresh.snapshot()['points'] if p['id'] == 'P1')['address'])

    def test_legacy_point_record_survives_migration(self):
        legacy = {'id': 'P4', 'label': 'Existing yard', 'device': 'old driver',
                  'output': 2, 'commanded': 'diverging', 'verified': None}
        with self.sim._db() as db:
            db.execute('UPDATE points SET data=? WHERE id=?', (json.dumps(legacy), 'P4'))
        fresh = Simulator(self.sim.path)
        point = next(p for p in fresh.snapshot()['points'] if p['id'] == 'P4')
        self.assertEqual(point['label'], 'Existing yard')
        self.assertEqual(point['output'], 2)
        self.assertEqual(point['commanded'], 'diverging')
        self.assertIsNone(point['address'])
        self.assertIsNone(point['hardware_commanded'])

    def test_reject_invalid_and_duplicate_addresses_without_mutation(self):
        self.sim.save_point('P1', 'One', '', None, 2044)
        for invalid in (0, 2045, True, 1.5, -1, '23'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.sim.save_point('P2', 'Two', '', None, invalid)
        with self.assertRaises(ValueError):
            self.sim.save_point('P2', 'Two', '', None, 2044)
        self.assertIsNone(self.item('P2')['address'])
        self.assertEqual(self.item('P1')['address'], 2044)

    def test_hardware_dispatch_requires_address_connection_power_and_no_estop(self):
        self.hw.configure({'host': 'dcc-ex.local', 'port': 2560})
        self.hw.connect(); self.hw.set_mode('HARDWARE')
        with self.assertRaises(ValueError): self.hw.point('P1', 'straight')
        self.sim.save_point('P1', 'One', '', None, 12)
        with self.assertRaises(ValueError): self.hw.point('P1', 'straight')
        self.assertEqual(self.sock.sent, [])
        self.sock.replies = [b'<p1>']; self.hw.power(True)
        self.hw.point('P1', 'straight')
        self.hw.point('P1', 'diverging')
        self.assertEqual(self.sock.sent[-2:], [b'<a 12 0>\n', b'<a 12 1>\n'])
        self.assertEqual(self.item('P1')['hardware_commanded'], 'diverging')
        self.assertIsNone(self.item('P2').get('hardware_commanded'))
        self.assertIsNone(self.item('P1')['verified'])
        with self.assertRaises(ValueError): self.hw.point('P1', 'invalid')
        self.assertEqual(len(self.sock.sent), 3)
        self.hw.emergency_stop()
        with self.assertRaises(ValueError): self.hw.point('P1', 'straight')

    def test_failed_transport_never_changes_recorded_command(self):
        self.sim.save_point('P1', 'One', '', None, 22)
        self.hw.configure({'host':'dcc-ex.local','port':2560})
        self.hw.connect(); self.hw.set_mode('HARDWARE')
        self.sock.replies = [b'<p1>']; self.hw.power(True)
        self.sock.sendall = lambda payload: (_ for _ in ()).throw(OSError('broken'))
        with self.assertRaises(ConnectionError): self.hw.point('P1', 'diverging')
        self.assertIsNone(self.item('P1').get('hardware_commanded'))
        self.assertFalse(self.hw.state()['hardware_connected'])

    def test_simulation_does_not_claim_hardware_command_or_physical_position(self):
        self.sim.save_point('P8', 'Eight', '', None, 56)
        self.hw.point('P8', 'diverging')
        self.assertEqual(self.item('P8')['commanded'], 'diverging')
        self.assertIsNone(self.item('P8').get('hardware_commanded'))
        self.assertIsNone(self.item('P8')['verified'])
        self.assertIsNone(next(p for p in Simulator(self.sim.path).snapshot()['points'] if p['id'] == 'P8').get('hardware_commanded'))


if __name__ == '__main__': unittest.main()
