"""Explicit, immutable SDK configuration.

Constructing :class:`DamiaSettings` never reads the environment. Use
:meth:`DamiaSettings.from_env` to opt in to environment loading; it does not
read dotenv files. Environment values override defaults. Service-specific
keys take precedence over the shared DaMIA key when a client selects a key;
FNS and Banks have their own keys and do not fall back to the DaMIA key.
"""

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "BaseURLSettings",
    "CacheSettings",
    "DamiaSettings",
    "RetrySettings",
    "TimeoutSettings",
]


class _FrozenSettings(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", allow_inf_nan=False, hide_input_in_errors=True
    )


class TimeoutSettings(_FrozenSettings):
    """HTTP timeout durations in seconds."""

    connect: float = Field(default=5.0, gt=0)
    read: float = Field(default=30.0, gt=0)
    write: float = Field(default=30.0, gt=0)
    pool: float = Field(default=5.0, gt=0)


class CacheSettings(_FrozenSettings):
    """Cache is opt-in; TTL is expressed in seconds."""

    enabled: bool = False
    ttl: float = Field(default=300.0, gt=0)
    max_entries: int = Field(default=256, gt=0)
    max_entry_bytes: int = Field(default=1048576, gt=0)


class RetrySettings(_FrozenSettings):
    """Retries are opt-in and still require operation-specific policies."""

    enabled: bool = False
    max_attempts: int = Field(default=3, gt=0)
    max_elapsed: float = Field(default=30.0, gt=0)
    initial_delay: float = Field(default=0.25, ge=0)
    max_delay: float = Field(default=5.0, gt=0)


class BaseURLSettings(_FrozenSettings):
    """Server base URLs as listed in the research OpenAPI specifications."""

    fns: str = "https://api-fns.ru/api"
    banks: str = "https://analizbankov.ru"
    rosstat: str = "https://api.damia.ru/rs"
    scoring: str = "https://api.damia.ru/scoring"
    procurement: str = "https://api.damia.ru/zakupki"
    arbitration: str = "https://api.damia.ru"
    fssp: str = "https://api.damia.ru/fssp"
    spk: str = "https://api.damia.ru/spk"


class DamiaSettings(_FrozenSettings):
    """SDK settings; missing credentials are allowed until a service is used.

    ``from_env()`` reads ``DAMIA_FNS_KEY``, ``DAMIA_BANKS_KEY``,
    ``DAMIA_API_KEY`` (the shared ``damia_key``), and service overrides such
    as ``DAMIA_SCORING_KEY``. Nested fields use double underscores, for example
    ``DAMIA_BASE_URLS__FNS``, ``DAMIA_TIMEOUT__CONNECT``, and
    ``DAMIA_CACHE__TTL``. Explicit constructor values do not consult the
    environment; to modify loaded settings, use ``model_copy(update=...)``
    only with already validated values or construct a new settings instance.
    """

    fns_key: SecretStr | None = None
    banks_key: SecretStr | None = None
    damia_key: SecretStr | None = None
    rosstat_key: SecretStr | None = None
    scoring_key: SecretStr | None = None
    procurement_key: SecretStr | None = None
    arbitration_key: SecretStr | None = None
    fssp_key: SecretStr | None = None
    spk_key: SecretStr | None = None
    timeout: TimeoutSettings = Field(default_factory=TimeoutSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    retry: RetrySettings = Field(default_factory=RetrySettings)
    base_urls: BaseURLSettings = Field(default_factory=BaseURLSettings)
    max_connections: int = Field(default=100, gt=0)

    @classmethod
    def from_env(cls) -> "DamiaSettings":
        """Load environment variables explicitly, with no dotenv file."""
        loaded = _EnvironmentSettings()
        return cls.model_validate(loaded.model_dump())


class _EnvironmentSettings(DamiaSettings, BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DAMIA_",
        env_nested_delimiter="__",
        env_file=None,
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        hide_input_in_errors=True,
    )

    damia_key: SecretStr | None = Field(default=None, validation_alias="DAMIA_API_KEY")
