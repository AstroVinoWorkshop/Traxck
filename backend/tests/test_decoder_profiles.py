import pytest
from backend.simulator import Simulator
from backend.hardware import HardwareController


def test_profile_round_trip_and_unmapped_rejected(tmp_path):
    sim = Simulator(tmp_path / 'profiles.db')
    ident = 'Steam locomotive E'
    profile = {'name': ident, 'address': 31, 'decoder': 'owner-entered',
               'functions': [{'key': 0, 'label': 'Light', 'momentary': False, 'source': 'decoder manual', 'confidence': 'manual'},
                             {'key': 28, 'label': 'Whistle', 'momentary': True, 'source': 'bench check', 'confidence': 'verified'}]}
    sim.update_roster(ident, profile)
    restored = Simulator(tmp_path / 'profiles.db')
    assert restored.snapshot()['roster'][3]['id'] != ''  # roster remains intact
    loco = next(l for l in restored._locos() if l['address'] == 31)
    assert loco['functions'] == profile['functions']
    assert loco['profile_source'] == 'operator entry'
    restored.power(True)
    with pytest.raises(ValueError, match='not mapped'):
        restored.function(31, 1, True)
    restored.function(31, 28, True)
    with pytest.raises(ValueError, match='Stop|power off'):
        restored.update_roster(ident, {**profile, 'functions': []})


def test_legacy_unproven_mapping_never_commands(tmp_path):
    sim = Simulator(tmp_path / 'profiles.db')
    sim.add_locomotive({'name': 'Legacy', 'address': 4, 'functions': [{'key': 0, 'label': 'Light'}]})
    sim.power(True)
    with pytest.raises(ValueError, match='not mapped'):
        sim.function(4, 0, True)


def test_function_icon_round_trip_without_changing_command_mapping(tmp_path):
    sim = Simulator(tmp_path / 'icons.db')
    mapping = {'key': 2, 'label': 'Whistle', 'momentary': True,
               'source': 'owner decoder manual', 'confidence': 'manual', 'icon': 'whistle'}
    sim.update_roster('Steam locomotive E', {'name': 'Steam locomotive E', 'address': 31, 'functions': [mapping]})
    restored = Simulator(tmp_path / 'icons.db')
    assert restored.snapshot()['roster'][4]['functions'] == [mapping]
    assert restored._locos()[0]['functions'] == [mapping]
    restored.power(True)
    restored.function(31, 2, True)
    assert restored.snapshot()['functions']['31']['2'] is True


@pytest.mark.parametrize('icon', ['<svg onload=alert(1)>', 'not-a-real-icon', 42])
def test_rejects_unknown_or_unsafe_function_icons(tmp_path, icon):
    sim = Simulator(tmp_path / 'icons.db')
    with pytest.raises(ValueError, match='function mapping'):
        sim.update_roster('Steam locomotive E', {'name': 'Steam locomotive E', 'address': 31,
                          'functions': [{'key': 2, 'label': 'Whistle', 'momentary': True,
                                         'source': 'manual', 'confidence': 'manual', 'icon': icon}]})


@pytest.mark.parametrize('mapping', [
    [{'key': 29, 'label': 'Unknown', 'source': 'manual', 'confidence': 'manual'}],
    [{'key': 0, 'label': 'Light', 'source': '', 'confidence': 'verified'}],
    [{'key': 0, 'label': 'Light', 'source': 'guess', 'confidence': 'guessed'}],
])
def test_rejects_unsupported_or_unproven_mapping(tmp_path, mapping):
    sim = Simulator(tmp_path / 'profiles.db')
    with pytest.raises(ValueError, match='function mapping'):
        sim.update_roster('Steam locomotive E', {'name': 'Steam locomotive E', 'address': 3, 'functions': mapping})


def test_cv_commands_disabled_even_with_confirmed_boolean(tmp_path):
    sim = Simulator(tmp_path / 'profiles.db')
    controller = HardwareController(sim)
    with pytest.raises(ValueError, match='disabled'):
        controller.program_cv('Steam locomotive E', 1, None, True)
