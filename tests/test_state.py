"""Unit tests for the state module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawagentskill.state import StateManager, infer_publisher, slugify


class TestSlugify:
    def test_slugify_basic(self):
        """Simple space-separated words become kebab-case."""
        assert slugify("stripe integration") == "stripe-integration"

    def test_slugify_special_chars(self):
        """Non-alphanumeric chars (except hyphens) are stripped."""
        result = slugify("foo@bar.com/baz")
        assert "@" not in result
        assert "." not in result
        assert "/" not in result
        # The slug should contain only lowercase alphanumerics and hyphens
        assert all(c.isalnum() or c == "-" for c in result)

    def test_slugify_truncation(self):
        """Strings longer than 64 chars get truncated."""
        long_text = "a" * 100
        result = slugify(long_text)
        assert len(result) <= 64

    def test_slugify_preserves_short_strings(self):
        """Strings under 64 chars are not truncated."""
        short_text = "hello-world"
        assert slugify(short_text) == "hello-world"

    def test_slugify_collapses_multiple_hyphens(self):
        """Multiple consecutive separators become a single hyphen."""
        result = slugify("foo   bar---baz")
        assert "--" not in result

    def test_slugify_lowercases(self):
        """Output is always lowercase."""
        assert slugify("Hello World") == "hello-world"


class TestInferPublisher:
    def test_infer_publisher_skills_sh_url(self):
        """skills.sh URL extracts the publisher segment."""
        url = "https://skills.sh/wshobson/agents/stripe"
        assert infer_publisher(url) == "wshobson"

    def test_infer_publisher_empty(self):
        """Empty string returns 'unknown'."""
        assert infer_publisher("") == "unknown"

    def test_infer_publisher_non_skills_sh(self):
        """Non-skills.sh URL returns 'unknown'."""
        assert infer_publisher("https://github.com/user/repo") == "unknown"

    def test_infer_publisher_http_skills_sh(self):
        """HTTP (non-HTTPS) skills.sh URL still works."""
        url = "http://skills.sh/acme-corp/tools/helper"
        assert infer_publisher(url) == "acme-corp"


class TestStateManagerYAML:
    def test_read_write_yaml_roundtrip(self, tmp_path: Path):
        """write_yaml then read_yaml returns the same data."""
        sm = StateManager(tmp_path / "run-001")
        data = {"key": "value", "count": 42, "nested": {"a": 1}}

        sm.write_yaml("test.yaml", data)
        result = sm.read_yaml("test.yaml")

        assert result == data

    def test_read_yaml_missing_file(self, tmp_path: Path):
        """Reading a non-existent file returns empty dict."""
        sm = StateManager(tmp_path / "run-002")
        assert sm.read_yaml("does-not-exist.yaml") == {}

    def test_save_load_meta_roundtrip(self, tmp_path: Path):
        """save_meta then load_meta returns the same data."""
        sm = StateManager(tmp_path / "run-003")
        meta = {"run_id": "test-123", "query": "example", "tier": "B"}

        sm.save_meta(meta)
        result = sm.load_meta()

        assert result == meta


class TestStateManagerEnvelope:
    def test_emit_parse_envelope_roundtrip(self, tmp_path: Path):
        """emit_envelope then parse_envelope returns the same run_dir."""
        sm = StateManager(tmp_path / "run-004")
        envelope = sm.emit_envelope()
        parsed_dir = StateManager.parse_envelope(envelope)

        assert parsed_dir == sm.run_dir

    def test_envelope_is_valid_json(self, tmp_path: Path):
        """Emitted envelope is valid JSON with run_dir key."""
        sm = StateManager(tmp_path / "run-005")
        envelope = sm.emit_envelope()
        obj = json.loads(envelope)

        assert "run_dir" in obj
        assert obj["run_dir"] == str(sm.run_dir)


class TestStateManagerCreateRun:
    def test_create_run_creates_meta(self, tmp_path: Path):
        """create_run creates run dir and meta.yaml file."""
        sm = StateManager.create_run(tmp_path, "stripe integration")

        assert sm.run_dir.exists()
        assert (sm.run_dir / "meta.yaml").exists()

    def test_create_run_meta_has_required_fields(self, tmp_path: Path):
        """meta.yaml contains all required fields."""
        sm = StateManager.create_run(
            tmp_path,
            "stripe integration",
            skill_url="https://skills.sh/wshobson/agents/stripe",
            scan_mode="quality",
        )
        meta = sm.load_meta()

        required_fields = [
            "run_id",
            "query",
            "skill_url",
            "skill_slug",
            "publisher",
            "tier",
            "scan_mode",
            "install_count",
            "started_at",
        ]
        for field_name in required_fields:
            assert field_name in meta, f"meta.yaml missing field: {field_name}"

    def test_create_run_uses_skill_url_publisher(self, tmp_path: Path):
        """Publisher is inferred from skill_url when provided."""
        sm = StateManager.create_run(
            tmp_path,
            "stripe",
            skill_url="https://skills.sh/wshobson/agents/stripe",
        )
        meta = sm.load_meta()
        assert meta["publisher"] == "wshobson"

    def test_create_run_uses_query_publisher(self, tmp_path: Path):
        """Publisher is inferred from query when it contains a slash."""
        sm = StateManager.create_run(tmp_path, "acme/stripe-tools")
        meta = sm.load_meta()
        assert meta["publisher"] == "acme"

    def test_create_run_unknown_publisher(self, tmp_path: Path):
        """Publisher defaults to 'unknown' for plain queries."""
        sm = StateManager.create_run(tmp_path, "stripe")
        meta = sm.load_meta()
        assert meta["publisher"] == "unknown"

    def test_create_run_scan_mode_preserved(self, tmp_path: Path):
        """scan_mode is stored in meta."""
        sm = StateManager.create_run(tmp_path, "test", scan_mode="efficiency")
        meta = sm.load_meta()
        assert meta["scan_mode"] == "efficiency"
