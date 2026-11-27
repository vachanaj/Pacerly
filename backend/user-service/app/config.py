from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "user-service"
    database_url: str = (
        "postgresql+asyncpg://user_svc:ChangeMeUserDb!@postgresql.pacerly-app.svc.cluster.local:5432/user_db"
    )
    keycloak_issuer_url: str = "https://group-4-m7011e-ltu.se/auth/realms/pacerly"
    keycloak_internal_jwks_url: str = (
        "http://keycloak.pacerly-app.svc.cluster.local:8080/auth/realms/pacerly/protocol/openid-connect/certs"
    )

    class Config:
        env_file = ".env"


settings = Settings()