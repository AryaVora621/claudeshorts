from __future__ import annotations

import pytest

from claudeshorts import config


def test_supabase_db_url_reads_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://user:pass@host:5432/postgres")
    assert config.supabase_db_url() == "postgresql://user:pass@host:5432/postgres"


def test_supabase_db_url_missing_raises(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_DB_URL"):
        config.supabase_db_url()
