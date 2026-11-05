import pytest

from src.recorder import Recorder


def _saved(tmp_path):
    recorder = Recorder()
    recorder.record({"a": 1})
    return recorder, recorder.save(tmp_path)


def test_rename_keeps_the_contents_and_adds_the_extension(tmp_path):
    recorder, path = _saved(tmp_path)
    contents = path.read_text()
    renamed = recorder.rename(path.name, "muerta game", tmp_path)
    assert renamed == tmp_path / "muerta game.jsonl"
    assert renamed.read_text() == contents
    assert not path.exists()


def test_a_renamed_recording_can_be_renamed_again(tmp_path):
    recorder, path = _saved(tmp_path)
    recorder.rename(path.name, "first", tmp_path)
    assert recorder.rename("first.jsonl", "second.jsonl", tmp_path) == tmp_path / "second.jsonl"


def test_rename_cannot_leave_the_folder(tmp_path):
    folder = tmp_path / "recordings"
    recorder, path = _saved(folder)
    assert recorder.rename(path.name, "../../evil", folder) == folder / "evil.jsonl"


def test_rename_refuses_an_existing_file(tmp_path):
    recorder, path = _saved(tmp_path)
    (tmp_path / "taken.jsonl").write_text("keep me")
    with pytest.raises(ValueError):
        recorder.rename(path.name, "taken", tmp_path)
    assert (tmp_path / "taken.jsonl").read_text() == "keep me"
    assert path.exists()


def test_rename_refuses_files_from_other_sessions_and_empty_names(tmp_path):
    recorder, path = _saved(tmp_path)
    (tmp_path / "old.jsonl").write_text("x")
    with pytest.raises(ValueError):
        recorder.rename("old.jsonl", "new", tmp_path)
    with pytest.raises(ValueError):
        recorder.rename(path.name, "...", tmp_path)
