import pytest
from backend.simulator import Simulator


def test_sequence_round_trip_and_preview(tmp_path):
    sim = Simulator(tmp_path / 'test.db')
    data = {'name': 'Station arrival', 'steps': [
        {'kind': 'note', 'label': 'Check platform is clear'},
        {'kind': 'wait', 'seconds': 12},
        {'kind': 'point', 'point_id': 'P1', 'position': 'straight'},
        {'kind': 'move', 'roster_id': 'Steam locomotive A', 'direction': 'forward', 'speed': 22, 'seconds': 8, 'distance_mm': None},
    ]}
    saved = sim.save_sequence('arrival', data)
    assert saved['steps'] == [*data['steps'][:2], {**data['steps'][2], 'settle_seconds': 2}, data['steps'][3]]
    assert sim.sequences()[0]['id'] == 'arrival'
    timeline = sim.preview_sequence('arrival')
    assert timeline['duration_seconds'] == 22
    assert timeline['steps'][-1]['end_seconds'] == 22
    assert timeline['steps'][-1]['estimated_distance_mm'] is None
    sim.delete_sequence('arrival')
    assert sim.sequences() == []


def test_sequence_rejects_unsafe_or_invalid_steps(tmp_path):
    sim = Simulator(tmp_path / 'test.db')
    for steps in ([{'kind': 'point', 'point_id': 'missing', 'position': 'straight'}],
                  [{'kind': 'move', 'roster_id': 'absent', 'direction': 'forward', 'speed': 20, 'seconds': 10}],
                  [{'kind': 'wait', 'seconds': 0}],
                  [{'kind': 'command', 'address': 3}]):
        with pytest.raises(ValueError):
            sim.save_sequence('bad', {'name': 'Bad', 'steps': steps})
    assert sim.sequences() == []


def test_sequence_does_not_change_simulated_power_or_speed(tmp_path):
    sim = Simulator(tmp_path / 'test.db')
    sim.save_sequence('draft', {'name': 'Draft', 'steps': [{'kind': 'wait', 'seconds': 5}]})
    sim.preview_sequence('draft')
    assert sim.track_power is False
    assert all(value['speed'] == 0 for value in sim.speeds.values())
