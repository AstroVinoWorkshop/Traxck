import tempfile
from pathlib import Path
import pytest


def test_point_motor_and_pillar_round_trip(tmp_path):
    from backend.simulator import Simulator
    sim = Simulator(tmp_path / 'markers.db')
    pieces = [dict(id=f'marker-{kind}', kind=kind, x=200, y=120,
                   rotation=0, length=50, curve=0)
              for kind in ('point-motor', 'pillar')]
    sim.save_layout(dict(name='Markers', segments=[], pieces=pieces,
                         buildings=[], diagramVersion=2))
    assert Simulator(tmp_path / 'markers.db').layout()['pieces'] == pieces


def test_marker_palette_and_duplicate_control():
    root = Path(__file__).resolve().parents[2] / 'frontend' / 'src'
    editor = (root / 'TrackEditor.tsx').read_text()
    diagram = (root / 'TrackDiagram.tsx').read_text()
    for kind in ('point-motor', 'pillar'):
        assert kind in editor and kind in diagram
    assert 'Duplicate selected' in editor


def test_editable_scenery_kinds_and_migration_marker_round_trip(tmp_path):
    from backend.app import Layout
    from backend.simulator import Simulator
    piece = dict(id='scenery-1', kind='level-crossing', x=80, y=60, rotation=0, length=90, curve=0)
    assert Layout(name='Shelf', segments=[], pieces=[piece], diagramVersion=2).model_dump()['diagramVersion'] == 2
    sim = Simulator(tmp_path / 'scenery.db')
    for kind in ('tunnel-portal','bridge','level-crossing','elevated-line','shelf-outline','platform-pair','plan-label'):
        piece['kind'] = kind
        if kind == 'plan-label': piece['text'] = 'Test label'
        sim.save_layout(dict(name='Shelf', segments=[], pieces=[piece], buildings=[], diagramVersion=2))
        assert sim.layout()['pieces'][0]['kind'] == kind
        assert sim.layout()['diagramVersion'] == 2
from backend.simulator import Simulator
from backend.app import Layout


def test_api_layout_schema_preserves_pieces():
    piece = {'id': 'turntable', 'kind': 'roco-35900', 'x': 270, 'y': 96, 'rotation': 0, 'length': 90, 'curve': 0}
    assert Layout(name='test', segments=[], pieces=[piece]).model_dump()['pieces'] == [piece]


def test_layout_pieces_survive_restart_without_changing_simulation_controls():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'layout.db'
        sim = Simulator(path)
        pieces = [
            {'id': 'bend-1', 'kind': 'peco-flex', 'x': 180, 'y': 110, 'rotation': 15, 'length': 180, 'curve': 48},
            {'id': 'table-1', 'kind': 'roco-35900', 'x': 270, 'y': 96, 'rotation': 0, 'length': 90, 'curve': 0},
        ]
        sim.save_layout({'name': 'My railway', 'pieces': pieces, 'segments': []})
        state = Simulator(path).snapshot()
        assert state['layout']['pieces'] == pieces
        assert state['layout']['name'] == 'My railway'
        assert state['track_power'] is False


@pytest.mark.parametrize('pieces', [
    [{'id': 'x', 'kind': 'unknown', 'x': 50, 'y': 40, 'rotation': 0, 'length': 80, 'curve': 0}],
    [{'id': 'x', 'kind': 'straight', 'x': float('nan'), 'y': 40, 'rotation': 0, 'length': 80, 'curve': 0}],
    [{'id': 'x', 'kind': 'straight', 'x': 50, 'y': 40, 'rotation': 0, 'length': 80, 'curve': 0}] * 2,
])
def test_layout_rejects_invalid_pieces(pieces):
    with tempfile.TemporaryDirectory() as tmp:
        sim = Simulator(Path(tmp) / 'layout.db')
        with pytest.raises(ValueError):
            sim.save_layout({'name': 'Test', 'pieces': pieces, 'segments': []})


def test_perimeter_and_canvas_survive_restart_without_moving_saved_parts(tmp_path):
    path = tmp_path / 'layout.db'
    sim = Simulator(path)
    part = dict(id='saved-part', kind='straight', x=870, y=475, rotation=0, length=120, curve=0)
    plan = dict(name='Expanded', segments=[], pieces=[part], buildings=[], diagramVersion=2,
                canvas={'width': 1400, 'height': 800}, perimeter=[{'x': 10, 'y': 10}, {'x': 1300, 'y': 10}, {'x': 1300, 'y': 700}, {'x': 10, 'y': 700}])
    sim.save_layout(plan)
    assert Simulator(path).layout() == plan
    assert Layout.model_validate(plan).model_dump(exclude_none=True)['perimeter'] == plan['perimeter']


@pytest.mark.parametrize('patch', [
    {'canvas': {'width': 890, 'height': 500}},
    {'canvas': {'width': 1400, 'height': 800}, 'perimeter': [{'x': 0, 'y': 0}]},
    {'canvas': {'width': 1400, 'height': 800}, 'perimeter': [{'x': 0, 'y': 0}, {'x': 1500, 'y': 0}, {'x': 0, 'y': 800}]},
    {'canvas': {'width': 1400, 'height': 800}, 'perimeter': [{'x': 0, 'y': 0}, {'x': float('nan'), 'y': 0}, {'x': 0, 'y': 500}]},
])
def test_invalid_perimeter_or_canvas_cannot_replace_existing_layout(tmp_path, patch):
    sim = Simulator(tmp_path / 'layout.db')
    old = dict(name='Untouched', segments=[], pieces=[], buildings=[])
    sim.save_layout(old)
    with pytest.raises(ValueError):
        sim.save_layout({**old, **patch})
    assert sim.layout() == old
