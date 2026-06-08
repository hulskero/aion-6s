import os
import json
import tempfile
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_init():
    with patch("aion.AION.__init__", return_value=None):
        yield


def test_read_file():
    from aion import AION
    aion = AION()
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    try:
        f.write("hello\nworld\nfoo\n")
        f.close()
        result = aion._read_file(f.name)
        assert "1|hello" in result
        assert "2|world" in result
        assert "3|foo" in result
    finally:
        os.unlink(f.name)


def test_read_file_not_found():
    from aion import AION
    aion = AION()
    result = aion._read_file("/nonexistent/path/file.txt")
    assert "not found" in result


def test_write_file():
    from aion import AION
    aion = AION()
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    fname = f.name
    f.close()
    try:
        result = aion._write_file(fname, "new content here")
        assert "bytes" in result.lower()
        with open(fname) as fh:
            assert fh.read() == "new content here"
    finally:
        os.unlink(fname)


def test_edit_file():
    from aion import AION
    aion = AION()
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    f.write("hello world foo bar")
    fname = f.name
    f.close()
    try:
        result = aion._edit_file(fname, "world", "there")
        assert "Edited" in result
        with open(fname) as fh:
            assert fh.read() == "hello there foo bar"
    finally:
        os.unlink(fname)


def test_edit_file_string_not_found():
    from aion import AION
    aion = AION()
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    f.write("hello world")
    fname = f.name
    f.close()
    try:
        result = aion._edit_file(fname, "nonexistent", "replacement")
        assert "not found" in result
    finally:
        os.unlink(fname)


def test_grep_search(tmp_path):
    from aion import AION
    aion = AION()
    d = tmp_path / "src"
    d.mkdir()
    (d / "foo.py").write_text("def hello():\n    pass\n")
    (d / "bar.py").write_text("# comment\nvalue = 42\n")
    with patch("aion.os.path.dirname", return_value=str(tmp_path)):
        result = aion._grep_search("hello")
        assert "foo.py" in result
        assert "hello" in result
        result2 = aion._grep_search("value")
        assert "bar.py" in result2


def test_grep_search_no_match(tmp_path):
    from aion import AION
    aion = AION()
    d = tmp_path / "src"
    d.mkdir()
    (d / "foo.py").write_text("x = 1\n")
    with patch("aion.os.path.dirname", return_value=str(tmp_path)):
        result = aion._grep_search("nonexistent")
        assert "No matches" in result


def test_glob_search(tmp_path):
    from aion import AION
    aion = AION()
    d = tmp_path / "project"
    d.mkdir()
    (d / "file1.py").write_text("")
    (d / "file2.py").write_text("")
    (d / "data.txt").write_text("")
    old_cwd = os.getcwd()
    try:
        os.chdir(str(d))
        result = aion._glob_search("*.py")
        assert "file1.py" in result
        assert "file2.py" in result
        assert "data.txt" not in result
    finally:
        os.chdir(old_cwd)


def test_glob_search_no_match(tmp_path):
    from aion import AION
    aion = AION()
    d = tmp_path / "project"
    d.mkdir()
    (d / "file1.py").write_text("")
    old_cwd = os.getcwd()
    try:
        os.chdir(str(d))
        result = aion._glob_search("*.rs")
        assert "No files match" in result or "Glob error" in result
    finally:
        os.chdir(old_cwd)
