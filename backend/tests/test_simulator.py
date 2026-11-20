import tempfile
import unittest
from pathlib import Path
from backend.simulator import Simulator, POINTS


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sim = Simulator(Path(self.temp.name) / 'workshop.db')

    def tearDown(self):
        self.temp.cleanup()

    def test_roster_is_persisted_without_guessed_addresses(self):
        state = self.sim.snapshot()
        self.assertEqual([item['name'] for item in state['roster']], [
            'Steam locomotive A', 'Steam locomotive B', 'Steam locomotive C',
            'Steam locomotive D', 'Steam locomotive E', 'Diesel locomotive A',
            'Shunter A', 'Shunter B'])
        self.assertEqual(state['locomotives'], [])
        self.assertTrue(all(item['address'] is None for item in state['roster']))
        self.assertEqual(len(state['points']), len(POINTS))
        self.assertEqual(state['mode'], 'SIMULATION')
        self.assertFalse(state['hardware_connected'])
        restarted = Simulator(Path(self.temp.name) / 'workshop.db').snapshot()
        self.assertEqual(restarted['roster'], state['roster'])
        self.assertEqual(restarted['locomotives'], [])

    def configure_test_locomotive(self):
        self.sim.add_locomotive({'name':'Test','address':88,'decoder':'Test decoder','functions':[]})
        return 88

    def test_throttle_requires_power_and_emergency_reset(self):
        address = self.configure_test_locomotive()
        with self.assertRaises(ValueError): self.sim.throttle(address, 40, 1)
        self.sim.power(True)
        self.sim.throttle(address, 40, 1)
        self.assertEqual(self.sim.snapshot()['speeds'][str(address)]['speed'], 40)
        self.sim.emergency_stop()
        self.assertEqual(self.sim.snapshot()['speeds'][str(address)]['speed'], 0)
        with self.assertRaises(ValueError): self.sim.throttle(address, 20, 1)
        self.sim.reset_emergency()
        self.assertFalse(self.sim.snapshot()['track_power'])
        with self.assertRaises(ValueError): self.sim.throttle(address, 20, 1)

    def test_restart_fails_safe_without_resuming_motion(self):
        address = self.configure_test_locomotive()
        self.sim.power(True)
        self.sim.throttle(address, 65, -1)
        restarted = Simulator(Path(self.temp.name) / 'workshop.db').snapshot()
        self.assertFalse(restarted['track_power'])
        self.assertEqual(restarted['speeds'][str(address)]['speed'], 0)

    def test_point_position_is_never_physically_verified(self):
        self.sim.point('P1', 'diverging')
        state = self.sim.snapshot()['points'][0]
        self.assertEqual(state['commanded'], 'diverging')
        self.assertEqual(state['verified'], None)
        with self.assertRaises(ValueError): self.sim.point('P1', 'invalid')

    def test_registry_and_function_mapping(self):
        self.sim.add_locomotive({'name':'Test','address':88,'decoder':'ROS-6D','functions':[{'key':0,'label':'Lights','momentary':False,'source':'Test fixture','confidence':'verified'}]})
        self.assertEqual(self.sim.snapshot()['locomotives'][-1]['name'], 'Test')
        self.sim.power(True)
        self.sim.function(88, 0, True)
        self.assertTrue(self.sim.snapshot()['functions']['88']['0'])
        with self.assertRaises(ValueError): self.sim.function(88, 99, True)
        with self.assertRaises(ValueError): self.sim.add_locomotive({'name':'Duplicate','address':88,'decoder':'X','functions':[]})


if __name__ == '__main__': unittest.main()
