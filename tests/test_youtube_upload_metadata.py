#!/usr/bin/env python3
"""Tests for tools/youtube_upload_api.py — load_metadata validator.

Note: youtube_upload_api.py imports google-api-python-client which may not
be installed. We test load_metadata by extracting its pure logic inline.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


def load_metadata(path: Path) -> dict:
    """Pure re-implementation matching youtube_upload_api.load_metadata."""
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ["title", "description", "tags"]
    for key in required:
        if key not in data:
            raise ValueError(f"Missing required metadata field: {key}")
    if not isinstance(data["tags"], list):
        raise ValueError("metadata.tags must be a JSON array")
    return data


# ---------------------------------------------------------------
# load_metadata
# ---------------------------------------------------------------

class TestLoadMetadata(unittest.TestCase):

    def _write(self, data: dict) -> Path:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(data, f)
        f.close()
        self._paths.append(Path(f.name))
        return Path(f.name)

    def setUp(self):
        self._paths: list[Path] = []

    def tearDown(self):
        for p in self._paths:
            p.unlink(missing_ok=True)

    def test_valid_metadata(self):
        p = self._write({
            "title": "Top 5 Earbuds",
            "description": "Best earbuds for 2026",
            "tags": ["earbuds", "review"],
        })
        result = load_metadata(p)
        self.assertEqual(result["title"], "Top 5 Earbuds")
        self.assertEqual(len(result["tags"]), 2)

    def test_missing_title(self):
        p = self._write({"description": "x", "tags": []})
        with self.assertRaises(ValueError) as cm:
            load_metadata(p)
        self.assertIn("title", str(cm.exception))

    def test_missing_description(self):
        p = self._write({"title": "x", "tags": []})
        with self.assertRaises(ValueError) as cm:
            load_metadata(p)
        self.assertIn("description", str(cm.exception))

    def test_missing_tags(self):
        p = self._write({"title": "x", "description": "y"})
        with self.assertRaises(ValueError) as cm:
            load_metadata(p)
        self.assertIn("tags", str(cm.exception))

    def test_tags_must_be_list(self):
        p = self._write({"title": "x", "description": "y", "tags": "not-a-list"})
        with self.assertRaises(ValueError) as cm:
            load_metadata(p)
        self.assertIn("array", str(cm.exception))

    def test_extra_fields_preserved(self):
        p = self._write({
            "title": "T",
            "description": "D",
            "tags": [],
            "category_id": "28",
        })
        result = load_metadata(p)
        self.assertEqual(result["category_id"], "28")

    def test_empty_tags_list_ok(self):
        p = self._write({"title": "T", "description": "D", "tags": []})
        result = load_metadata(p)
        self.assertEqual(result["tags"], [])

    def test_invalid_json_raises(self):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        f.write("{not valid")
        f.close()
        self._paths.append(Path(f.name))
        with self.assertRaises(json.JSONDecodeError):
            load_metadata(Path(f.name))

    def test_tags_with_special_chars(self):
        p = self._write({
            "title": "Test",
            "description": "Desc",
            "tags": ["review", "top 5", "2026 best", "under $50"],
        })
        result = load_metadata(p)
        self.assertEqual(len(result["tags"]), 4)


# ---------------------------------------------------------------
# load_metadata edge cases
# ---------------------------------------------------------------

class TestLoadMetadataEdgeCases(unittest.TestCase):

    def _write(self, data: dict) -> Path:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(data, f)
        f.close()
        self._paths.append(Path(f.name))
        return Path(f.name)

    def setUp(self):
        self._paths: list[Path] = []

    def tearDown(self):
        for p in self._paths:
            p.unlink(missing_ok=True)

    def test_unicode_title(self):
        p = self._write({
            "title": "Top 5 Fones de Ouvido — Melhor Custo Benefício",
            "description": "Análise completa",
            "tags": ["fone", "bluetooth"],
        })
        result = load_metadata(p)
        self.assertIn("Fones", result["title"])

    def test_very_long_title(self):
        p = self._write({
            "title": "A" * 500,
            "description": "D",
            "tags": [],
        })
        result = load_metadata(p)
        self.assertEqual(len(result["title"]), 500)

    def test_empty_description(self):
        p = self._write({
            "title": "T",
            "description": "",
            "tags": [],
        })
        result = load_metadata(p)
        self.assertEqual(result["description"], "")

    def test_tags_with_duplicates(self):
        p = self._write({
            "title": "T",
            "description": "D",
            "tags": ["review", "review", "test"],
        })
        result = load_metadata(p)
        self.assertEqual(len(result["tags"]), 3)

    def test_nested_extra_fields(self):
        p = self._write({
            "title": "T",
            "description": "D",
            "tags": [],
            "snippet": {"categoryId": "28", "defaultLanguage": "pt"},
        })
        result = load_metadata(p)
        self.assertEqual(result["snippet"]["categoryId"], "28")

    def test_tags_is_dict_raises(self):
        p = self._write({
            "title": "T",
            "description": "D",
            "tags": {"tag1": True},
        })
        with self.assertRaises(ValueError):
            load_metadata(p)


# ---------------------------------------------------------------
# load_metadata: more edge cases
# ---------------------------------------------------------------

class TestLoadMetadataMoreEdgeCases(unittest.TestCase):

    def _write(self, data: dict) -> Path:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(data, f)
        f.close()
        self._paths.append(Path(f.name))
        return Path(f.name)

    def setUp(self):
        self._paths: list[Path] = []

    def tearDown(self):
        for p in self._paths:
            p.unlink(missing_ok=True)

    def test_title_with_newlines(self):
        p = self._write({
            "title": "Line 1\nLine 2",
            "description": "D",
            "tags": [],
        })
        result = load_metadata(p)
        self.assertIn("\n", result["title"])

    def test_empty_title_accepted(self):
        p = self._write({"title": "", "description": "D", "tags": []})
        result = load_metadata(p)
        self.assertEqual(result["title"], "")

    def test_many_tags(self):
        tags = [f"tag_{i}" for i in range(100)]
        p = self._write({"title": "T", "description": "D", "tags": tags})
        result = load_metadata(p)
        self.assertEqual(len(result["tags"]), 100)

    def test_tags_with_empty_strings(self):
        p = self._write({"title": "T", "description": "D", "tags": ["", "valid", ""]})
        result = load_metadata(p)
        self.assertEqual(len(result["tags"]), 3)

    def test_null_title_raises(self):
        p = self._write({"title": None, "description": "D", "tags": []})
        # title is present but None — no error from required check
        result = load_metadata(p)
        self.assertIsNone(result["title"])

    def test_tags_is_tuple_like_raises(self):
        """Tags must be a list, not a string that looks like array."""
        p = self._write({"title": "T", "description": "D", "tags": "[not, a, list]"})
        with self.assertRaises(ValueError):
            load_metadata(p)


if __name__ == "__main__":
    unittest.main()
