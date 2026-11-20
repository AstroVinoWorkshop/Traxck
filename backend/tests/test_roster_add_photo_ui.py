from pathlib import Path

EDITOR = Path(__file__).resolve().parents[2] / 'frontend/src/RosterEditor.tsx'


def test_add_dialog_offers_photo_before_save_and_uploads_after_creation():
    source = EDITOR.read_text()
    assert 'Add locomotive image' in source
    assert 'type="file"' in source
    assert "'/api/roster/'+encodeURIComponent(savedId)+'/photo'" in source
    assert "method:'PUT'" in source


def test_missing_create_route_explains_action_instead_of_http_jargon():
    source = EDITOR.read_text()
    assert "response.status===405" in source
    assert 'Method Not Allowed' not in source
    assert 'railway server has not been updated' in source
