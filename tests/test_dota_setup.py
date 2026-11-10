from src import dota_setup


def _install(tmp_path, monkeypatch, port=6969):
    monkeypatch.setattr(dota_setup, "dota_cfg_dirs", lambda: [tmp_path])
    return dota_setup.install_gsi_config(port)


def test_writes_when_missing(tmp_path, monkeypatch):
    assert _install(tmp_path, monkeypatch) == [tmp_path / "gamestate_integration" / dota_setup.CFG_NAME]


def test_leaves_current_cfg_alone(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch)
    assert _install(tmp_path, monkeypatch) == []


def test_upgrades_own_cfg_missing_topics(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch)
    cfg = tmp_path / "gamestate_integration" / dota_setup.CFG_NAME
    cfg.write_text('"soundbo"\n{\n "uri" "http://127.0.0.1:6969/"\n "data"\n {\n "map" "1"\n "items" "1"\n }\n}\n')
    assert _install(tmp_path, monkeypatch) == [cfg]
    assert cfg.read_text() == dota_setup.CFG_TEMPLATE.format(port=6969)


def test_ignores_other_tools_cfg_on_our_port(tmp_path, monkeypatch):
    folder = tmp_path / "gamestate_integration"
    folder.mkdir()
    other = folder / "gamestate_integration_other.cfg"
    other.write_text('"x" { "uri" "http://127.0.0.1:6969/" "data" { "map" "1" } }')
    assert _install(tmp_path, monkeypatch) == []
    assert not (folder / dota_setup.CFG_NAME).exists()
