from pydantic_settings import BaseSettings, SettingsConfigDict


DEVELOPMENT_JWT_SECRET = "development-only-secret-change-before-production-32bytes"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    database_url: str = "sqlite:///./pavepulse.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    simulator_enabled: bool = True
    seed_on_startup: bool = True
    spatial_dedup_meters: float = 30.0
    spatial_dedup_hours: int = 24
    manual_merge_max_meters: float = 100.0
    verification_required_buses: int = 2
    verification_radius_meters: float = 35.0
    jwt_secret: str = DEVELOPMENT_JWT_SECRET
    jwt_expiry_minutes: int = 480
    bootstrap_engineer_password: str | None = None
    device_api_key: str = "dev-device-key-change-me"
    device_offline_minutes: int = 5
    evidence_storage_dir: str = "./data/evidence"
    # Supabase is the identity provider; operational records live in this app's PostgreSQL schema.
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_engineer_emails: str = "engineer@pavepulse.local"
    supabase_worker_emails: str = "worker@pavepulse.local"
    demo_data_enabled: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def use_postgis(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def supabase_role_by_email(self) -> dict[str, str]:
        emails: dict[str, str] = {}
        for email in self.supabase_engineer_emails.split(","):
            normalized = email.strip().lower()
            if normalized:
                emails[normalized] = "engineer"
        for email in self.supabase_worker_emails.split(","):
            normalized = email.strip().lower()
            if normalized:
                # Do not permit one identity to be configured for both roles.
                if normalized in emails and emails[normalized] != "worker":
                    raise RuntimeError(f"Supabase identity {normalized} is configured for more than one role.")
                emails[normalized] = "worker"
        return emails

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    def validate_production_settings(self) -> None:
        if not self.is_production:
            return
        if self.jwt_secret == DEVELOPMENT_JWT_SECRET or len(self.jwt_secret) < 32:
            raise RuntimeError("Production requires a unique JWT_SECRET with at least 32 characters.")
        if not self.supabase_url and (not self.bootstrap_engineer_password or len(self.bootstrap_engineer_password) < 14):
            raise RuntimeError("Set SUPABASE_URL for Supabase Auth, or BOOTSTRAP_ENGINEER_PASSWORD (at least 14 characters) for local API auth.")
        if self.supabase_url and not self.supabase_url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must be the HTTPS project URL, e.g. https://<project-ref>.supabase.co.")
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
            raise RuntimeError("Production requires PostgreSQL. Set DATABASE_URL to your Supabase PostgreSQL connection string.")
        roles = self.supabase_role_by_email
        if self.supabase_url and not any(role == "engineer" for role in roles.values()):
            raise RuntimeError("Configure at least one email in SUPABASE_ENGINEER_EMAILS.")
        if "localhost" in self.cors_origins or "127.0.0.1" in self.cors_origins:
            raise RuntimeError("Production CORS_ORIGINS must not include localhost or loopback hosts.")
        if self.verification_required_buses < 1:
            raise RuntimeError("VERIFICATION_REQUIRED_BUSES must be at least 1.")
        if self.verification_radius_meters <= 0:
            raise RuntimeError("VERIFICATION_RADIUS_METERS must be greater than zero.")
        if self.simulator_enabled:
            raise RuntimeError("SIMULATOR_ENABLED must be false in production to prevent synthetic events entering live data.")
        if self.seed_on_startup:
            raise RuntimeError("SEED_ON_STARTUP must be false in production to prevent demo records being inserted.")


settings = Settings()
settings.validate_production_settings()
