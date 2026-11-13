"""Проверки скелета SDK без сетевых запросов."""

import inspect
from pathlib import Path

import pytest
from pydantic import SecretStr

from damia_sdk import DamiaClient, DamiaSettings


@pytest.mark.asyncio
async def test_client_services_share_settings_and_transport() -> None:
    settings = DamiaSettings(fns_key=SecretStr("synthetic-test-key"))
    async with DamiaClient(settings=settings) as client:
        assert client.settings is settings
        for name in (
            "fns",
            "rosstat",
            "banks",
            "scoring",
            "procurement",
            "arbitration",
            "fssp",
            "spk",
        ):
            service = getattr(client, name)
            assert service._transport is client._transport


def test_every_documented_get_has_async_skeleton() -> None:
    client = DamiaClient()
    methods: dict[str, set[str]] = {
        "fns": {
            "search",
            "ac",
            "egr",
            "multinfo",
            "multcheck",
            "check",
            "nalogbi",
            "nalogbi_file",
            "changes",
            "mon",
            "vyp",
            "mspinfo_file",
            "bo",
            "bo_file",
            "innfl",
            "mvdpass",
            "mvdinfo",
            "fl_status",
            "fsrar",
            "zsk",
            "rom",
            "fias_info",
            "fias_search",
            "stat",
        },
        "rosstat": {"balance", "multbalance", "statcodes"},
        "banks": {
            "bankdata",
            "bankinfo",
            "bankaraits",
            "bankbic",
            "bankotch",
            "banksrait",
            "listdata",
            "pokinfo",
            "stat",
        },
        "scoring": {"score", "info", "fincoefs"},
        "procurement": {
            "zakupka",
            "contract",
            "zakupki",
            "contracts",
            "zsearch",
            "customer",
            "eruz",
            "zfas",
            "rnp",
            "sro",
            "ktru",
            "zmon",
        },
        "arbitration": {"delo", "delopro", "dela", "dsearch"},
        "fssp": {"isp", "isps", "ispfl", "ispsfl"},
        "spk": {"report", "proverki"},
    }
    for service_name, names in methods.items():
        service = getattr(client, service_name)
        for name in names:
            assert inspect.iscoroutinefunction(getattr(service, name)), (
                service_name,
                name,
            )


def test_explicit_settings_ignore_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAMIA_FNS_KEY", "synthetic-environment-key")
    settings = DamiaSettings()
    assert settings.fns_key is None


def test_settings_can_be_loaded_explicitly_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DAMIA_FNS_KEY", "synthetic-environment-key")
    monkeypatch.setenv("DAMIA_BASE_URLS__FNS", "http://127.0.0.1:4010")
    monkeypatch.setenv("DAMIA_TIMEOUT__READ", "12")
    settings = DamiaSettings.from_env()
    assert settings.fns_key is not None
    assert settings.fns_key.get_secret_value() == "synthetic-environment-key"
    assert "synthetic-environment-key" not in repr(settings)
    assert str(settings.base_urls.fns) == "http://127.0.0.1:4010"
    assert settings.timeout.read == 12


def test_settings_do_not_load_dotenv_implicitly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DAMIA_FNS_KEY", raising=False)
    (tmp_path / ".env").write_text("DAMIA_FNS_KEY=synthetic-dotenv-key\n")
    assert DamiaSettings.from_env().fns_key is None


def test_cache_and_retries_are_disabled_by_default() -> None:
    settings = DamiaSettings()
    assert not settings.cache.enabled
    assert not settings.retry.enabled
