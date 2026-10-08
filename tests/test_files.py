import pytest

from travel_assistant.files import write_note


def test_create_and_never_overwrite(tmp_path):
    assert write_note(tmp_path, "行程.md", "北京行程")["saved"]
    assert "error" in write_note(tmp_path, "行程.md", "覆盖")
    assert (tmp_path / "行程.md").read_text(encoding="utf-8") == "北京行程"


@pytest.mark.parametrize(
    "name",
    [
        "../secret.txt",
        "/tmp/file.md",
        "a/b.txt",
        "a\\b.txt",
        "C:secret.txt",
        "CON.txt",
        "script.py",
        "file.txt:ads",
    ],
)
def test_reject_unsafe_names(tmp_path, name):
    assert "error" in write_note(tmp_path, name, "test")
    assert not list(tmp_path.iterdir())


def test_content_limit(tmp_path):
    assert "error" in write_note(tmp_path, "a.md", "好" * 40_000)
    assert "error" in write_note(tmp_path, "a.md", "  ")
