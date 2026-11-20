from pathlib import Path
from backend.simulator import Simulator

ROOT = Path(__file__).parents[2] / 'frontend' / 'src'


def test_overview_and_editor_use_shared_persisted_diagram():
    main = (ROOT / 'main.tsx').read_text()
    editor = (ROOT / 'TrackEditor.tsx').read_text()
    diagram = (ROOT / 'TrackDiagram.tsx').read_text()
    assert '<TrackDiagram' in main and '<TrackDiagram' in editor
    assert 'state?.layout.pieces' in main
    assert 'visiblePieces(layout.pieces,layout.diagramVersion)' in editor
    assert 'M 92 421 V 242 Q 92 148 291 148 H 835' in diagram


def test_palette_add_delete_and_sliders_are_visible():
    editor = (ROOT / 'TrackEditor.tsx').read_text()
    assert 'Add '+"'" in editor or 'Add to plan' in editor
    assert 'Delete selected' in editor
    assert 'Track parts' in editor and 'Select part or building' in editor
    assert 'type="range"' in editor
    assert 'palettePointerDown' in editor and 'onPointerUp' in editor


def test_observed_geometry_is_valid_persisted_layout(tmp_path):
    simulator = Simulator(tmp_path / 'rail.db')
    piece = {'id':'observed-main','kind':'observed-main','x':0,'y':0,'rotation':0,'length':360,'curve':0}
    state = simulator.save_layout({'name':'Shelf','segments':[],'pieces':[piece]})
    assert state['layout']['pieces'] == [piece]
    assert state['track_power'] is False


def test_named_buildings_round_trip_and_deliberate_empty_list(tmp_path):
    simulator = Simulator(tmp_path / 'rail.db')
    building = {'id':'station','name':'Station','x':445,'y':75,'width':103,'height':28,'rotation':0}
    saved = simulator.save_layout({'name':'Shelf','segments':[],'pieces':[], 'buildings':[building]})
    assert saved['layout']['buildings'] == [building]
    assert simulator.layout()['buildings'] == [building]
    assert simulator.save_layout({'name':'Shelf','segments':[],'pieces':[], 'buildings':[]})['layout']['buildings'] == []
    assert simulator.layout()['buildings'] == []


def test_building_validation_rejects_unsafe_names_and_geometry(tmp_path):
    import pytest
    simulator = Simulator(tmp_path / 'rail.db')
    building = {'id':'station','name':'Station','x':445,'y':75,'width':103,'height':28,'rotation':0}
    for patch in ({'name':' '},{'name':'<script>'},{'width':0},{'height':501},{'x':901},{'rotation':float('nan')}, {'id':'bad'*30}):
        with pytest.raises(ValueError):
            simulator.save_layout({'name':'Shelf','segments':[],'pieces':[], 'buildings':[{**building,**patch}]})


def test_building_editor_contract():
    editor = (ROOT / 'TrackEditor.tsx').read_text()
    diagram = (ROOT / 'TrackDiagram.tsx').read_text()
    app = (Path(__file__).parents[1] / 'app.py').read_text()
    assert 'buildings: list[dict]' in app
    assert 'buildings={visibleBuildings(state?.layout.buildings)}' in (ROOT / 'main.tsx').read_text()
    assert 'Add building' in editor and 'Building name' in editor
    assert 'buildings' in editor and 'onBuildingPointerDown' in diagram
    assert 'INITIAL_BUILDINGS' in diagram and '<text x="440" y="114">STATION</text>' not in diagram
