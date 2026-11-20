from pathlib import Path


def test_roster_editor_is_available_per_train_and_separate_from_hardware_token():
    source = (Path(__file__).resolve().parents[2] / 'frontend/src/main.tsx').read_text()
    editor = (Path(__file__).resolve().parents[2] / 'frontend/src/RosterEditor.tsx').read_text()
    assert 'Edit train details' in source and 'Edit train details' in editor
    assert 'Save train details' in editor
    assert 'inventoryToken' not in source and 'X-Inventory-Token' not in editor
    assert 'Inventory token' not in source and 'Enter the inventory token' not in editor
    assert 'l.address==null' in source
    assert 'Function mapping' in editor
    assert 'operatorToken' not in source[source.index('async function uploadPhoto'):source.index('function closeCamera')]
