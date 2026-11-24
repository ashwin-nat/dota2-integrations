import json
from pathlib import Path

PATH = Path(__file__).parent.parent / "src" / "config_ui" / "static" / "permanent_buffs.json"


def test_permanent_buffs_file_is_well_formed():
    # The editor builds its permanent-buff triggers from this file, so a typo here breaks them silently.
    buffs = json.loads(PATH.read_text(encoding="utf-8"))
    assert buffs
    keys = [b["key"] for b in buffs]
    assert len(keys) == len(set(keys))
    for b in buffs:
        assert set(b) == {"key", "name", "tooltip", "description", "kind", "icon"}, b
        assert all(isinstance(v, str) and v for v in b.values()), b
        assert b["kind"] in ("monotonic", "bidirectional"), b
        assert b["key"].startswith("modifier_"), b
        assert b["icon"].split(":")[0] in ("ability", "item", "hero"), b  # the sources BUFF_ICON in app.js knows
