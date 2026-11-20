import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.simulator import Simulator


class FakeSocket:
    def __init__(self, replies=()):
        self.sent = []
        self.replies = list(replies)
        self.closed = False
    def settimeout(self, value): self.timeout = value
    def sendall(self, payload): self.sent.append(payload)
    def recv(self, size):
        if not self.replies: raise TimeoutError('no confirmation')
        value = self.replies.pop(0)
        if isinstance(value, Exception): raise value
        return value
    def close(self): self.closed = True


class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sim = Simulator(Path(self.temp.name) / 'workshop.db')
        from backend.hardware import HardwareController
        self.socket = FakeSocket()
        self.hardware = HardwareController(self.sim, socket_factory=lambda address, timeout: self.socket)
    def tearDown(self):
        self.hardware.disconnect()
        self.temp.cleanup()
    def configure(self): self.hardware.configure({'host':'dcc-ex.local','port':2560})

    def test_config_validation_and_persistence_never_connects(self):
        for host, port in [('http://station',2560),('bad host',2560),('ok',0),('ok',65536),('a\n<1>',2560)]:
            with self.assertRaises(ValueError): self.hardware.configure({'host':host,'port':port})
        self.configure()
        self.assertFalse(self.hardware.state()['hardware_connected'])
        from backend.hardware import HardwareController
        other = HardwareController(Simulator(self.sim.path), socket_factory=lambda *a: self.fail('auto-connected'))
        self.assertEqual(other.state()['connection']['host'], 'dcc-ex.local')
        self.assertEqual(other.state()['mode'], 'SIMULATION')

    def test_connect_is_transport_only_and_mode_requires_explicit_selection(self):
        self.configure()
        self.hardware.connect()
        self.assertEqual(self.socket.sent, [])
        self.assertEqual(self.hardware.state()['mode'], 'SIMULATION')
        self.hardware.set_mode('HARDWARE')
        self.assertEqual(self.hardware.state()['mode'], 'HARDWARE')
        self.hardware.disconnect()
        self.assertEqual(self.hardware.state()['mode'], 'HARDWARE')
        self.assertFalse(self.hardware.state()['track_power'])
        self.assertTrue(self.socket.closed)

    def test_hardware_preference_survives_restart_without_reconnecting_or_powering(self):
        self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
        from backend.hardware import HardwareController
        fresh = HardwareController(Simulator(self.sim.path), socket_factory=lambda *a: self.fail('auto-connected'))
        self.assertEqual(fresh.state()['mode'], 'HARDWARE')
        self.assertFalse(fresh.state()['hardware_connected'])
        self.assertFalse(fresh.state()['track_power'])
        with self.assertRaises(ValueError): fresh.power(True)
        self.assertEqual(self.socket.sent, [])
        fresh.set_mode('SIMULATION')
        again = HardwareController(Simulator(self.sim.path), socket_factory=lambda *a: self.fail('auto-connected'))
        self.assertEqual(again.state()['mode'], 'SIMULATION')

    def test_verified_mains_on_prepares_hardware_without_power_command(self):
        self.configure()
        self.hardware.reconcile_mains(True)
        self.assertTrue(self.hardware.state()['hardware_connected'])
        self.assertEqual(self.hardware.state()['mode'], 'HARDWARE')
        self.assertFalse(self.hardware.state()['track_power'])
        self.assertEqual(self.socket.sent, [])

    def test_mains_off_disconnects_and_next_on_retries_booting_station(self):
        self.configure()
        attempts = 0
        def booting(address, timeout):
            nonlocal attempts
            attempts += 1
            if attempts == 1: raise ConnectionRefusedError('booting')
            return self.socket
        self.hardware.socket_factory = booting
        self.hardware.reconcile_mains(True)
        self.assertFalse(self.hardware.state()['hardware_connected'])
        self.hardware.reconcile_mains(True)
        self.assertTrue(self.hardware.state()['hardware_connected'])
        self.hardware.reconcile_mains(False)
        self.assertFalse(self.hardware.state()['hardware_connected'])
        self.assertFalse(self.hardware.state()['track_power'])
        self.assertEqual(self.socket.sent, [])

    def test_failed_power_confirmation_does_not_auto_reconnect_while_mains_on(self):
        self.configure(); self.hardware.reconcile_mains(True)
        with self.assertRaises(ConnectionError): self.hardware.power(True)
        self.hardware.reconcile_mains(True)
        self.assertFalse(self.hardware.state()['hardware_connected'])
        self.hardware.reconcile_mains(False)
        self.hardware.reconcile_mains(True)
        self.assertTrue(self.hardware.state()['hardware_connected'])

    def test_hardware_power_requires_confirmation_and_blocks_motion_until_then(self):
        self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
        self.sim.add_locomotive({'name':'Test','address':88,'decoder':'Verified','functions':[]})
        with self.assertRaises(ValueError): self.hardware.throttle(88, 20, 1)
        self.socket.replies = [b'<p1>']
        self.hardware.power(True)
        self.hardware.throttle(88, 20, -1)
        self.assertEqual(self.socket.sent, [b'<1>\n', b'<t 88 20 0>\n'])
        self.assertEqual(self.hardware.state()['speeds']['88']['speed'], 20)

    def test_track_power_click_prepares_station_from_verified_mains(self):
        from backend import app as module
        previous_sim, previous_hw = module.sim, module.hardware
        module.sim, module.hardware = self.sim, self.hardware
        self.configure()
        try:
            with patch.dict('os.environ', {'WORKSHOP_LAN_SUBNET': '10.77.88.0/24'}), patch('backend.railway_plug.status', return_value={'available': True, 'on': True}):
                client = TestClient(module.app, base_url='http://127.0.0.1:8768', client=('127.0.0.1', 12345))
                self.socket.replies = [b'<p1>']
                result = client.post('/api/power', json={'on': True})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()['mode'], 'HARDWARE')
                self.assertEqual(self.socket.sent, [b'<1>\n'])
        finally:
            module.sim, module.hardware = previous_sim, previous_hw

    def test_track_power_refuses_simulation_when_configured_mains_off(self):
        from backend import app as module
        previous_sim, previous_hw = module.sim, module.hardware
        module.sim, module.hardware = self.sim, self.hardware
        self.configure()
        try:
            with patch.dict('os.environ', {'WORKSHOP_LAN_SUBNET': '10.77.88.0/24'}), patch('backend.railway_plug.status', return_value={'available': True, 'on': False}):
                client = TestClient(module.app, base_url='http://127.0.0.1:8768', client=('127.0.0.1', 12345))
                result = client.post('/api/power', json={'on': True})
                self.assertEqual(result.status_code, 400)
                self.assertEqual(self.socket.sent, [])
        finally:
            module.sim, module.hardware = previous_sim, previous_hw

    def test_power_timeout_fails_closed_and_disconnects(self):
        self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
        with self.assertRaises(ConnectionError): self.hardware.power(True)
        self.assertIn(b'<0>\n', self.socket.sent)
        self.assertFalse(self.hardware.state()['hardware_connected'])
        self.assertFalse(self.hardware.state()['track_power'])

    def test_no_unmapped_or_unknown_hardware_commands_and_no_points_protocol(self):
        self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
        with self.assertRaises(ValueError): self.hardware.point('P1','straight')
        self.sim.add_locomotive({'name':'Test','address':88,'decoder':'Verified','functions':[{'key':1,'label':'Bell','momentary':False,'source':'Test fixture','confidence':'verified'}]})
        self.socket.replies = [b'<p1>']; self.hardware.power(True)
        with self.assertRaises(ValueError): self.hardware.throttle(99,20,1)
        with self.assertRaises(ValueError): self.hardware.function(88,2,True)
        self.hardware.function(88,1,True)
        self.assertEqual(self.socket.sent[-1], b'<F 88 1 1>\n')

    def test_estop_is_explicit_command_and_latches_even_on_transport_failure(self):
        self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
        self.socket.replies = [b'<p1>']; self.hardware.power(True)
        self.hardware.emergency_stop()
        self.assertEqual(self.socket.sent[-2:], [b'<!>\n',b'<0>\n'])
        self.assertTrue(self.hardware.state()['estop'])
        self.assertFalse(self.hardware.state()['track_power'])
        self.hardware.reset_emergency()
        self.assertFalse(self.hardware.state()['track_power'])

    def test_send_failure_drops_connection_and_requires_fresh_explicit_connect(self):
        self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
        self.sim.add_locomotive({'name':'Test','address':88,'decoder':'Verified','functions':[]})
        self.socket.replies = [b'<p1>']; self.hardware.power(True)
        self.socket.sendall = lambda payload: (_ for _ in ()).throw(OSError('broken pipe'))
        with self.assertRaises(ConnectionError): self.hardware.throttle(88,10,1)
        self.assertEqual(self.hardware.state()['mode'], 'HARDWARE')
        self.assertFalse(self.hardware.state()['hardware_connected'])

    def test_estop_connected_in_simulation_stops_both_planes(self):
        self.configure(); self.hardware.connect()
        self.hardware.emergency_stop()
        self.assertEqual(self.socket.sent, [b'<!>\n',b'<0>\n'])
        self.assertTrue(self.sim.snapshot()['estop'])

    def test_lan_only_hardware_without_token_and_rejects_other_peers(self):
        from backend import app as module
        previous_sim, previous_hw = module.sim, module.hardware
        module.sim, module.hardware = self.sim, self.hardware
        try:
            with patch.dict('os.environ', {'WORKSHOP_LAN_SUBNET': '10.77.88.0/24', 'WORKSHOP_TAILSCALE_IP': '100.100.101.102', 'WORKSHOP_OPERATOR_TOKEN': ''}):
                local = TestClient(module.app, base_url='http://10.77.88.188:8768', client=('10.77.88.42', 12345))
                self.assertEqual(local.get('/api/hardware').status_code, 200)
                self.assertEqual(local.put('/api/hardware/config', json={'host':'dcc-ex.local','port':2560}).status_code, 200)
                self.assertEqual(local.post('/api/hardware/connect').status_code, 200)
                self.assertEqual(local.post('/api/hardware/mode', json={'mode':'HARDWARE'}).status_code, 200)
                self.socket.replies = [b'<p0>']
                self.assertEqual(local.post('/api/power', json={'on':False}).status_code, 200)
                tailnet = TestClient(module.app, base_url='http://100.100.101.102:8768', client=('100.100.101.104', 12345))
                self.assertEqual(tailnet.get('/api/hardware').status_code, 200)
                self.socket.replies = [b'<p0>']
                self.assertEqual(tailnet.post('/api/power', json={'on':False}).status_code, 200)
                remote = TestClient(module.app, base_url='http://100.100.101.102:8768', client=('8.8.8.8', 12345))
                self.assertEqual(remote.post('/api/power', json={'on':True}).status_code, 403)
                self.assertEqual(remote.get('/api/hardware').status_code, 403)
                wrong_host = TestClient(module.app, base_url='http://100.100.101.103:8768', client=('100.100.101.104', 12345))
                self.assertEqual(wrong_host.get('/api/hardware').status_code, 403)
                self.assertEqual(local.post('/api/hardware/disconnect', headers={'Origin':'https://evil.example'}).status_code, 403)
                self.assertEqual(local.post('/api/hardware/disconnect', headers={'Sec-Fetch-Site':'cross-site'}).status_code, 403)
        finally:
            module.sim, module.hardware = previous_sim, previous_hw

    def test_diagnostic_allowlist_and_station_output(self):
        self.configure()
        with self.assertRaises(ValueError): self.hardware.diagnostic('<s>')
        self.hardware.connect()
        self.hardware.set_mode('HARDWARE')
        for command in ('<1>', '<1 JOIN>', '<0 JOIN>', '<t 3 50 1>', '<R 1>', '<s>\n<1>', '<J R 1>'):
            with self.assertRaises(ValueError): self.hardware.diagnostic(command)
        self.assertEqual(self.socket.sent, [])
        self.socket.replies = [b'<iDCC-EX V5>\n', TimeoutError()]
        self.assertEqual(self.hardware.diagnostic('<s>'), {'command':'<s>', 'output':'<iDCC-EX V5>'})
        self.assertEqual(self.socket.sent, [b'<s>\n'])
        self.socket.replies = [b'<a 12>\n', TimeoutError()]
        self.assertEqual(self.hardware.diagnostic('<c>')['output'], '<a 12>')
        self.assertEqual(self.socket.sent, [b'<s>\n', b'<c>\n'])
        from backend.hardware import DIAGNOSTIC_COMMANDS
        for query in sorted(DIAGNOSTIC_COMMANDS - {'<s>', '<c>'}):
            self.socket.replies = [b'<jR>\n', TimeoutError()]
            self.assertEqual(self.hardware.diagnostic(query)['output'], '<jR>')
            self.assertEqual(self.socket.sent[-1], (query+'\n').encode('ascii'))

    def test_diagnostic_timeout_disconnects_without_power_change(self):
        self.configure()
        self.hardware.connect()
        self.hardware.set_mode('HARDWARE')
        self.socket.replies = [TimeoutError(), TimeoutError()]
        with self.assertRaises(ConnectionError): self.hardware.diagnostic('<s>')
        self.assertFalse(self.hardware.state()['hardware_connected'])
        self.assertEqual(self.socket.sent, [b'<s>\n'])

    def test_native_command_safety_and_state(self):
        self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
        self.sim.add_locomotive({'name':'Test','address':88,'decoder':'Verified',
                                 'functions':[{'key':1,'label':'Bell','momentary':False,
                                               'source':'Test','confidence':'verified'}]})
        for value in ('<1>\n<0>', '<0 JOIN>', '<D RESET>', '<= A MAIN>',
                      '<w 88 1 10>', '<C WIFI "ssid" "password">',
                      '</ START 1>', '<t 88 127 1>', '<F 88 2 1>'):
            with self.assertRaises(ValueError): self.hardware.native_command(value, True)
        with self.assertRaises(ValueError): self.hardware.native_command('<1>', False)
        with self.assertRaises(ValueError): self.hardware.native_command('<1 JOIN>', True)
        self.assertEqual(self.socket.sent, [])
        self.socket.replies = [b'<p1 JOIN>']
        result = self.hardware.native_command('<1 JOIN>', True, True)
        self.assertTrue(result['acknowledged'])
        self.assertEqual(result['output'], '<p1 JOIN>')
        result = self.hardware.native_command('<t 88 20 0>', True)
        self.assertFalse(result['acknowledged'])
        self.assertIsNone(result['output'])
        self.assertEqual(self.hardware.speeds['88'], {'speed':20,'direction':-1})
        self.hardware.native_command('<F 88 1 1>', True)
        self.assertTrue(self.hardware.functions['88']['1'])
        self.socket.replies = [b'<p0>']
        self.hardware.native_command('<0>', True)
        self.assertEqual(self.hardware.speeds['88']['speed'], 0)
        self.assertTrue(self.hardware.main_power_off_verified)
        self.assertEqual(self.socket.sent, [b'<1 JOIN>\n', b'<t 88 20 0>\n',
                                           b'<F 88 1 1>\n', b'<0>\n'])

    def test_native_cv_requires_isolation_and_exact_response(self):
        self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
        with self.assertRaises(ValueError): self.hardware.native_command('<R 1>', True, False, True)
        self.assertEqual(self.socket.sent, [])
        self.socket.replies = [b'<p0>']
        self.hardware.native_command('<0>', True)
        for value in ('<W 1 256>', '<R 1 2>', '<W 0 12>'):
            with self.assertRaises(ValueError): self.hardware.native_command(value, True, False, True)
        with self.assertRaises(ValueError): self.hardware.native_command('<R 1>', True)
        self.socket.replies = [b'<v 1 42>']
        result = self.hardware.native_command('<R 1>', True, False, True)
        self.assertEqual(result['output'], '<v 1 42>')
        self.assertEqual(result['value'], 42)
        self.socket.replies = [b'<r 1 12>']
        self.assertEqual(self.hardware.native_command('<W 1 12>', True, False, True)['output'], '<r 1 12>')
        self.socket.replies = [b'<r 1 13>']
        with self.assertRaises(ConnectionError): self.hardware.native_command('<W 1 12>', True, False, True)
        self.assertFalse(self.hardware.state()['hardware_connected'])

    def test_native_track_specific_power_requires_matching_broadcast_and_conservative_state(self):
        self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
        for command, reply, verified in (('<0 MAIN>', b'<p0 MAIN>', True),
                                         ('<1 PROG>', b'<p1 PROG>', True),
                                         ('<0 PROG>', b'<p0 PROG>', True),
                                         ('<1 MAIN>', b'<p1 MAIN>', False)):
            self.socket.replies = [reply]
            result = self.hardware.native_command(command, True)
            self.assertEqual(result['output'], reply.decode())
            self.assertTrue(result['acknowledged'])
            self.assertEqual(self.hardware.main_power_off_verified, verified)
        self.assertTrue(self.hardware.power_on)
        self.assertEqual(self.socket.sent, [b'<0 MAIN>\n', b'<1 PROG>\n',
                                            b'<0 PROG>\n', b'<1 MAIN>\n'])
        self.socket.replies = [b'<p0>']
        self.hardware.native_command('<0>', True)
        self.socket.replies = [b'<p1 JOIN>']
        self.hardware.native_command('<1 JOIN>', True, True)
        self.assertFalse(self.hardware.main_power_off_verified)

    def test_native_track_specific_power_rejects_mismatch_without_claiming_state(self):
        self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
        self.socket.replies = [b'<p0 PROG>', TimeoutError('no matching broadcast')]
        with self.assertRaises(ConnectionError): self.hardware.native_command('<0 MAIN>', True)
        self.assertFalse(self.hardware.main_power_off_verified)
        self.assertFalse(self.hardware.state()['hardware_connected'])

    def test_native_track_power_rejects_undocumented_forms_without_send(self):
        self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
        for command in ('<0 JOIN>', '<1 MAIN EXTRA>', '<2 PROG>', '<0 main>'):
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.hardware.native_command(command, True)
        self.assertEqual(self.socket.sent, [])

    def test_native_api_contract_and_mains_guard(self):
        from backend import app as module
        previous_sim, previous_hw = module.sim, module.hardware
        module.sim, module.hardware = self.sim, self.hardware
        try:
            self.configure(); self.hardware.connect(); self.hardware.set_mode('HARDWARE')
            with patch.dict('os.environ', {'WORKSHOP_OPERATOR_TOKEN':'test-only-secret',
                                           'WORKSHOP_LAN_SUBNET':''}), \
                 patch('backend.railway_plug.status', return_value={'available':True,'on':False}) as plug:
                client = TestClient(module.app)
                body = {'command':'<1 JOIN>', 'confirmed':True, 'wiring_confirmed':True,
                        'programming_track_isolated':False}
                self.assertEqual(client.post('/api/hardware/command', json=body).status_code, 401)
                client.headers.update({'X-Operator-Token':'test-only-secret'})
                self.assertEqual(client.post('/api/hardware/command', json=body).status_code, 400)
                self.assertEqual(client.post('/api/hardware/command', json={**body,'confirmed':'true'}).status_code, 422)
                self.assertEqual(self.socket.sent, [])
                plug.return_value = {'available':True,'on':True}
                self.socket.replies = [b'<p1 JOIN>']
                response = client.post('/api/hardware/command', json=body)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['output'], '<p1 JOIN>')
                self.assertTrue(response.json()['acknowledged'])
                self.assertEqual(client.post('/api/hardware/command', json={**body,'command':'<D RESET>'}).status_code, 400)
                sent_before = list(self.socket.sent)
                self.assertEqual(client.post('/api/hardware/command', json={**body,'command':'<0 JOIN>'}).status_code, 400)
                self.assertEqual(self.socket.sent, sent_before)
        finally:
            module.sim, module.hardware = previous_sim, previous_hw

    def test_api_contract(self):
        from backend import app as module
        previous_sim, previous_hw = module.sim, module.hardware
        module.sim, module.hardware = self.sim, self.hardware
        try:
            client = TestClient(module.app)
            with patch.dict('os.environ', {'WORKSHOP_OPERATOR_TOKEN':''}):
                self.assertEqual(client.get('/api/hardware').status_code, 503)
            auth = patch.dict('os.environ', {'WORKSHOP_OPERATOR_TOKEN':'test-only-secret'})
            auth.start()
            self.assertEqual(client.get('/api/hardware').status_code, 401)
            client.headers.update({'X-Operator-Token':'test-only-secret'})
            self.assertEqual(client.get('/api/hardware').json()['mode'], 'SIMULATION')
            self.assertEqual(client.put('/api/hardware/config',json={'host':'dcc-ex.local','port':2560}).status_code,200)
            self.assertEqual(client.post('/api/hardware/connect').status_code,200)
            self.assertEqual(client.post('/api/hardware/mode',json={'mode':'HARDWARE'}).status_code,200)
            client.headers.clear()
            self.assertEqual(client.post('/api/power',json={'on':True}).status_code,401)
            self.assertEqual(client.post('/api/throttle',json={'address':88,'speed':10,'direction':1}).status_code,401)
            self.assertEqual(client.post('/api/emergency-stop').status_code,401)
            self.assertEqual(self.socket.sent, [])
            client.headers.update({'X-Operator-Token':'test-only-secret'})
            self.assertEqual(client.post('/api/points/P1',json={'position':'straight'}).status_code,400)
            self.assertEqual(client.get('/api/state').json()['mode'],'HARDWARE')
            # No third-party catalogue artwork is bundled with the public source.
            self.assertNotIn('/locomotives', [getattr(route, 'path', None) for route in module.app.routes])
        finally:
            if 'auth' in locals(): auth.stop()
            module.sim, module.hardware = previous_sim, previous_hw
