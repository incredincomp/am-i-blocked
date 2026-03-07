"""Application configuration via Pydantic v2 BaseSettings."""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -----------------------------------------------------------------------
    # Infrastructure
    # -----------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://app:app@localhost:5432/amiblockeddb",
        description="SQLAlchemy async database URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for task queue",
    )

    # -----------------------------------------------------------------------
    # Application identity
    # -----------------------------------------------------------------------
    app_identity_header: str = Field(
        default="X-Forwarded-User",
        description="HTTP header injected by reverse proxy that carries the requester identity",
    )
    anonymous_user: str = Field(
        default="anonymous",
        description="Fallback identity when header is absent",
    )

    # -----------------------------------------------------------------------
    # Feature flags
    # -----------------------------------------------------------------------
    enable_bounded_probes: bool = Field(
        default=True,
        description="Allow lightweight DNS/TCP/TLS/HTTP probes",
    )
    probe_dns_timeout_s: float = Field(default=3.0)
    probe_tcp_timeout_s: float = Field(default=3.0)
    probe_tls_timeout_s: float = Field(default=5.0)
    probe_http_timeout_s: float = Field(default=8.0)

    # -----------------------------------------------------------------------
    # PAN-OS
    # -----------------------------------------------------------------------
    panos_fw_hosts: list[str] = Field(
        default_factory=list,
        description="Comma-separated list of PAN-OS management plane hostnames/IPs",
    )
    panos_api_key: str | None = Field(default=None, description="PAN-OS API key")
    panos_verify_ssl: bool = Field(default=True)
    panos_max_concurrent: int = Field(
        default=2,
        description="Max concurrent management-plane requests per firewall",
    )

    # -----------------------------------------------------------------------
    # Strata Cloud Manager (SCM) / Prisma
    # -----------------------------------------------------------------------
    scm_client_id: str | None = Field(default=None)
    scm_client_secret: str | None = Field(default=None)
    scm_tsg_id: str | None = Field(default=None)
    scm_auth_url: str = Field(default="https://auth.apps.paloaltonetworks.com/oauth2/access_token")
    scm_api_base_url: str = Field(default="https://api.sase.paloaltonetworks.com")

    # -----------------------------------------------------------------------
    # SD-WAN
    # -----------------------------------------------------------------------
    sdwan_api_url: str | None = Field(default=None, description="SD-WAN OpsCenter API base URL")
    sdwan_api_key: str | None = Field(default=None)
    sdwan_verify_ssl: bool = Field(default=True)

    # -----------------------------------------------------------------------
    # LogScale / Falcon
    # -----------------------------------------------------------------------
    logscale_url: str | None = Field(default=None, description="LogScale cluster base URL")
    logscale_repo: str | None = Field(default=None, description="LogScale repository / view name")
    logscale_token: str | None = Field(default=None, description="LogScale ingest/query token")

    # -----------------------------------------------------------------------
    # Torq (outbound only)
    # -----------------------------------------------------------------------
    torq_client_id: str | None = Field(default=None)
    torq_client_secret: str | None = Field(default=None)
    torq_api_base_url: str = Field(default="https://api.torq.io")

    # -----------------------------------------------------------------------
    # Worker / job settings
    # -----------------------------------------------------------------------
    worker_concurrency: int = Field(default=4)
    job_timeout_s: int = Field(default=120)

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json", description="'json' or 'console'")

    @field_validator("panos_fw_hosts", mode="before")
    @classmethod
    def split_hosts(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [h.strip() for h in v.split(",") if h.strip()]
        return v  # type: ignore[return-value]


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
