"""Settings dell'applicazione, caricati da variabili d'ambiente / .env."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_ENV: Literal["development", "production", "test"] = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "change-me"

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://dental:changeme_in_production@db:5432/dental_ai"

    # AI providers
    DEFAULT_AI_PROVIDER: Literal["claude", "openai", "gemini", "deepseek"] = "claude"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    GOOGLE_API_KEY: Optional[str] = None
    # Chiave dedicata Gemini AI Studio (per Gemini Image / Nano Banana). Se vuota,
    # fallback su GOOGLE_API_KEY. Permette di tenere chiavi separate quando una
    # ha billing/accesso al modello immagine e l'altra no.
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-pro"
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Ingest
    PUBMED_EMAIL: str = "dev@example.com"
    PUBMED_API_KEY: Optional[str] = None
    PUBMED_QUERY: str = (
        "(artificial intelligence[Title/Abstract] OR deep learning[Title/Abstract] OR "
        "machine learning[Title/Abstract]) AND (dentistry[Title/Abstract] OR dental[Title/Abstract] "
        "OR orthodontic[Title/Abstract] OR endodontic[Title/Abstract] OR periodont[Title/Abstract] "
        "OR implant[Title/Abstract])"
    )
    INGEST_INTERVAL_HOURS: int = 12
    INGEST_MAX_PER_RUN: int = 20

    # Validation thresholds
    CAPTION_MAX_CHARS: int = 2200
    HASHTAG_MAX_COUNT: int = 30
    CAROUSEL_MIN_SLIDES: int = 4
    CAROUSEL_MAX_SLIDES: int = 10
    REQUIRE_CLINICAL_DISCLAIMER: bool = True

    # Personal brand
    AUTHOR_NAME: str = "Dr. Example"
    INSTAGRAM_HANDLE: str = "@dr.example"
    BRAND_TAGLINE: str = "Dentistry × Artificial Intelligence"
    BRAND_VOICE: str = "scientific yet accessible, professional, modern, elegant"
    CONTENT_LANGUAGE: Literal["en", "it"] = "en"

    # --- Instagram publishing (Meta Graph API) ---
    # Setup richiesto:
    # 1. Crea una App su developers.facebook.com (tipo "Business")
    # 2. Aggiungi prodotto "Instagram"
    # 3. Collega un Instagram Business/Creator account a una Facebook Page
    # 4. Ottieni App ID + App Secret
    # 5. Ottieni un Long-Lived Access Token (60gg) tramite OAuth flow
    # 6. Ottieni l'Instagram Business Account ID
    META_APP_ID: Optional[str] = None
    META_APP_SECRET: Optional[str] = None
    META_REDIRECT_URI: str = "http://localhost:8000/api/publish/oauth/callback"
    IG_LONG_LIVED_TOKEN: Optional[str] = None
    IG_BUSINESS_ACCOUNT_ID: Optional[str] = None
    # URL pubblico raggiungibile da Meta per le immagini caricate
    # In dev: usa ngrok / cloudflared. In prod: dominio HTTPS.
    PUBLIC_BASE_URL: Optional[str] = None

    # Image generation / search
    # "pollinations" = Flux FREE no-auth (default); "ai" = Imagen 3 (billing);
    # "gemini_image" = Nano Banana (billing); "wikimedia"/"unsplash" = ricerca;
    # "none" = solo dark navy gradient brand
    DEFAULT_IMAGE_SOURCE: Literal[
        "pollinations", "ai", "gemini_image", "wikimedia", "unsplash", "none"
    ] = "pollinations"
    IMAGEN_MODEL: str = "imagen-3.0-generate-002"
    GEMINI_IMAGE_MODEL: str = "gemini-2.5-flash-image"
    POLLINATIONS_MODEL: str = "flux"
    UNSPLASH_ACCESS_KEY: Optional[str] = None

    @property
    def gemini_image_key(self) -> Optional[str]:
        """Chiave effettiva da usare per Gemini Image: GEMINI_API_KEY se presente,
        altrimenti GOOGLE_API_KEY come fallback."""
        return self.GEMINI_API_KEY or self.GOOGLE_API_KEY

    @property
    def configured_providers(self) -> list[str]:
        out = []
        if self.ANTHROPIC_API_KEY:
            out.append("claude")
        if self.OPENAI_API_KEY:
            out.append("openai")
        if self.GOOGLE_API_KEY:
            out.append("gemini")
        if self.DEEPSEEK_API_KEY:
            out.append("deepseek")
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
