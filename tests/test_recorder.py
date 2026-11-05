import pytest

from src.recorder import Recorder


def _recorder():
    recorder = Recorder()
    recorder.record({"a": 1})
    return recorder


def test_save_uses_the_chosen_name_and_adds_the_extension(tmp_path):
    assert _recorder().save(tmp_path, "muerta game") == tmp_path / "muerta game.jsonl"
    assert _recorder().save(tmp_path, "second.jsonl") == tmp_path / "second.jsonl"
    assert (tmp_path / "muerta game.jsonl").read_text().count("\n") == 1


def test_save_without_a_name_uses_a_timestamp(tmp_path):
    assert _recorder().save(tmp_path).name.startswith("gsi_")


def test_a_chosen_name_cannot_leave_the_folder(tmp_path):
    folder = tmp_path / "recordings"
    assert _recorder().save(folder, "../../evil") == folder / "evil.jsonl"


def test_save_refuses_an_existing_file(tmp_path):
    (tmp_path / "taken.jsonl").write_text("keep me")
    with pytest.raises(ValueError):
        _recorder().save(tmp_path, "taken")
    assert (tmp_path / "taken.jsonl").read_text() == "keep me"


def test_save_refuses_a_name_with_nothing_usable(tmp_path):
    with pytest.raises(ValueError):
        _recorder().save(tmp_path, "...")
