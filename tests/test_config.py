"""Tests for config loading — defaults, file overrides, env overrides."""

import json
import os

import pytest

from scout.config import ScoutConfig, load_config


class TestScoutConfigDefaults:
    def test_default_port(self):
        config = ScoutConfig()
        assert config.port == 11436

    def test_default_search_provider(self):
        config = ScoutConfig()
        assert config.search_provider == "duckduckgo"

    def test_default_distill_enabled(self):
        config = ScoutConfig()
        assert config.distill is True

    def test_default_search_expand_enabled(self):
        config = ScoutConfig()
        assert config.search_expand is True

    def test_default_ttls(self):
        config = ScoutConfig()
        assert config.default_ttl_search_hours == 6
        assert config.default_ttl_web_hours == 24
        assert config.default_ttl_media_hours == 168

    def test_resolved_db_path_expands_home(self):
        config = ScoutConfig(db_path="~/.synapses/scout.db")
        resolved = config.resolved_db_path
        assert "~" not in str(resolved)
        assert resolved.is_absolute()

    def test_tavily_api_key_defaults_to_none(self):
        config = ScoutConfig()
        assert config.tavily_api_key is None


class TestLoadConfigFromFile:
    def test_loads_values_from_json_file(self, tmp_path):
        config_file = tmp_path / "scout.json"
        config_file.write_text(json.dumps({
            "port": 9999,
            "search_provider": "tavily",
            "distill": False,
        }))

        config = load_config(str(config_file))

        assert config.port == 9999
        assert config.search_provider == "tavily"
        assert config.distill is False

    def test_missing_file_uses_defaults(self, tmp_path):
        config = load_config(str(tmp_path / "nonexistent.json"))
        assert config.port == 11436

    def test_partial_file_merges_with_defaults(self, tmp_path):
        config_file = tmp_path / "scout.json"
        config_file.write_text(json.dumps({"port": 8080}))

        config = load_config(str(config_file))

        assert config.port == 8080
        assert config.search_provider == "duckduckgo"  # default preserved


class TestLoadConfigEnvOverrides:
    def test_tavily_api_key_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-secret-key")
        config = load_config(str(tmp_path / "nonexistent.json"))
        assert config.tavily_api_key == "tvly-secret-key"

    def test_scout_port_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SCOUT_PORT", "12345")
        config = load_config(str(tmp_path / "nonexistent.json"))
        assert config.port == 12345

    def test_scout_intelligence_url_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SCOUT_INTELLIGENCE_URL", "http://myhost:11435")
        config = load_config(str(tmp_path / "nonexistent.json"))
        assert config.intelligence_url == "http://myhost:11435"

    def test_env_overrides_file_value(self, tmp_path, monkeypatch):
        config_file = tmp_path / "scout.json"
        config_file.write_text(json.dumps({"port": 9000}))
        monkeypatch.setenv("SCOUT_PORT", "7777")

        config = load_config(str(config_file))

        assert config.port == 7777

    def test_scout_config_env_var_selects_file(self, tmp_path, monkeypatch):
        config_file = tmp_path / "custom.json"
        config_file.write_text(json.dumps({"port": 5555}))
        monkeypatch.setenv("SCOUT_CONFIG", str(config_file))

        config = load_config()  # no explicit path — reads SCOUT_CONFIG env var

        assert config.port == 5555
