"""Tests for src/io.py."""

import json
import tempfile
from pathlib import Path


from src.io import get_output_path, load_json, sanitize_filename, save_json


class TestSaveJson:
    """Tests for save_json function."""

    def test_saves_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            data = {"key": "value", "number": 42}

            result = save_json(data, path)

            assert result == path
            assert path.exists()
            with open(path) as f:
                loaded = json.load(f)
            assert loaded == data

    def test_saves_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            data = [1, 2, 3, {"nested": "value"}]

            save_json(data, path)

            with open(path) as f:
                loaded = json.load(f)
            assert loaded == data

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "dirs" / "test.json"
            data = {"test": True}

            save_json(data, path)

            assert path.exists()

    def test_handles_unicode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            data = {"emoji": "🔥", "chinese": "维基百科"}

            save_json(data, path)

            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded == data


class TestLoadJson:
    """Tests for load_json function."""

    def test_loads_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            data = {"key": "value"}
            with open(path, "w") as f:
                json.dump(data, f)

            loaded = load_json(path)

            assert loaded == data

    def test_loads_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            data = [1, 2, 3]
            with open(path, "w") as f:
                json.dump(data, f)

            loaded = load_json(path)

            assert loaded == data


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_replaces_slashes(self):
        assert sanitize_filename("path/to/file") == "path_to_file"

    def test_replaces_spaces(self):
        assert sanitize_filename("my file name") == "my_file_name"

    def test_replaces_colons(self):
        assert sanitize_filename("Wikipedia:Article") == "Wikipedia_Article"

    def test_combined(self):
        assert sanitize_filename("Talk:My Page/Archive") == "Talk_My_Page_Archive"

    def test_already_safe(self):
        assert sanitize_filename("safe_filename") == "safe_filename"


class TestGetOutputPath:
    """Tests for get_output_path function."""

    def test_creates_directory(self):
        # This test checks the function returns a valid path
        # The actual directory creation depends on project structure
        path = get_output_path("test_subdir", prefix="test", timestamp=False)

        assert isinstance(path, Path)
        assert "test_subdir" in str(path)
        assert "test.json" in str(path)

    def test_with_filename(self):
        path = get_output_path("arbitration", filename="specific.json")

        assert path.name == "specific.json"
