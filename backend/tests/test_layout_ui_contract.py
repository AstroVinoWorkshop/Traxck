from pathlib import Path


def test_editor_space_perimeter_and_group_controls_are_wired():
    root = Path(__file__).resolve().parents[2] / 'frontend' / 'src'
    editor = (root / 'TrackEditor.tsx').read_text()
    diagram = (root / 'TrackDiagram.tsx').read_text()
    main = (root / 'main.tsx').read_text()
    for control in ('Select all', 'Drag selection', 'Perimeter', 'Canvas width', 'Canvas height', 'Parts palette'):
        assert control in editor
    assert 'perimeter={perimeter}' in editor and 'canvas={canvas}' in editor
    assert 'perimeter={state?.layout.perimeter}' in main
    assert 'onBackgroundPointerDown' in diagram
    assert 'sidebar-collapsed' in main


def test_main_navigation_starts_open_and_keeps_navigation_when_collapsed():
    root = Path(__file__).resolve().parents[2] / 'frontend' / 'src'
    main = (root / 'main.tsx').read_text()
    css = (root / 'editor-space.css').read_text()
    assert 'useState(false)' in main
    assert 'aria-label={sidebarCollapsed?' in main
    assert 'aria-expanded={!sidebarCollapsed}' in main
    assert 'setSidebarCollapsed(!sidebarCollapsed)' in main
    assert '.sidebar-collapsed>.sidebar' in css
    assert '.sidebar-collapsed .sidebar nav button' in css
    assert 'aria-label={label}' in main

ROOT = Path(__file__).parents[2] / 'frontend' / 'src'

def test_editor_has_movable_existing_rails_catalog_and_persistent_save():
    src = (ROOT / 'TrackEditor.tsx').read_text()
    assert 'Initial observed rails' in src
    assert 'Peco flex track' in src
    assert 'Roco 35900 turntable' in src
    assert 'onPointerMove' in src
    assert 'Save layout' in src
    assert "method:'PUT'" in src
    assert 'Undo' in src
    assert 'Delete selected' in src


def test_touch_palette_drag_can_add_when_map_is_below_viewport():
    src = (ROOT / 'TrackEditor.tsx').read_text()
    # On a narrow screen the palette and map are stacked: a touch release
    # outside the visible SVG must still create a part, not silently discard it.
    assert 'add(kind,coords(e.clientX,e.clientY));else if(pointerType' in src
    assert "pointerType!=='mouse')add(kind)" in src

def test_mouse_palette_drag_does_not_depend_on_native_html_drop():
    src = (ROOT / 'TrackEditor.tsx').read_text()
    # A mouse pointer released over the map must add/select a part even when
    # the browser never dispatches a native dragstart/drop pair.
    assert "event.pointerType==='mouse')return" not in src
    assert 'draggable onDragStart' not in src
    assert 'pointerType' in src and 'palettePointerDown' in src

def test_palette_add_works_on_insecure_http_tailscale_origin():
    src = (ROOT / 'TrackEditor.tsx').read_text()
    # crypto.randomUUID is absent on HTTP IP origins, even when pointerup succeeds.
    assert 'crypto.getRandomValues' in src
    assert 'crypto.randomUUID()' not in src
    assert 'id:newId()' in src

def test_old_fixed_scenery_becomes_saved_editable_pieces():
    diagram = (ROOT / 'TrackDiagram.tsx').read_text()
    editor = (ROOT / 'TrackEditor.tsx').read_text()
    main = (ROOT / 'main.tsx').read_text()
    assert 'INITIAL_DECORATIONS' in diagram
    assert 'visiblePieces(layout.pieces,layout.diagramVersion)' in editor
    assert 'visiblePieces(state?.layout.pieces,state?.layout.diagramVersion)' in main
    assert 'diagramVersion:2' in editor
    assert 'map-platform"><path' not in diagram
    assert 'map-tunnel"><rect' not in diagram
    for kind in ('tunnel-portal','bridge','level-crossing','elevated-line','shelf-outline','platform-pair'):
        assert kind in diagram and kind in editor
