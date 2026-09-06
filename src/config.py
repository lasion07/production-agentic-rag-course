import os
from pathlib import Path
from typing import List, Literal, Optional
from urllib.parse import parse_qs, urlparse

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


def _is_placeholder_secret(value: str, *, min_length: int = 16) -> bool:
    normalized = value.strip().lower()
    markers = ("changeme", "replace-me", "replace_me", "example", "password", "secret")
    return len(value.strip()) < min_length or any(marker in normalized for marker in markers)


class BaseConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        extra="ignore",
        frozen=True,
        env_nested_delimiter="__",
        case_sensitive=False,
    )


class ArxivSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="ARXIV__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    base_url: str = "https://export.arxiv.org/api/query"
    pdf_cache_dir: str = "./data/arxiv_pdfs"
    rate_limit_delay: float = 3.0
    timeout_seconds: int = 30
    max_results: int = 15
    search_category: str = "cs.AI"
    download_max_retries: int = 3
    download_retry_delay_base: float = 5.0
    max_concurrent_downloads: int = 5
    max_concurrent_parsing: int = 1

    namespaces: dict = {
        "atom": "http://www.w3.org/2005/Atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
        "arxiv": "http://arxiv.org/schemas/atom",
    }

    @field_validator("pdf_cache_dir")
    @classmethod
    def validate_cache_dir(cls, v: str) -> str:
        os.makedirs(v, exist_ok=True)
        return v


class PDFParserSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="PDF_PARSER__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    max_pages: int = 30
    max_file_size_mb: int = 20
    do_ocr: bool = False
    do_table_structure: bool = True


class ChunkingSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="CHUNKING__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    chunk_size: int = 600  # Target words per chunk
    overlap_size: int = 100  # Words to overlap between chunks
    min_chunk_size: int = 100  # Minimum words for a valid chunk
    section_based: bool = True  # Use section-based chunking when available


class OpenSearchSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="OPENSEARCH__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    host: str = "http://localhost:9200"
    username: str = ""
    password: SecretStr = SecretStr("")
    verify_certs: bool = False
    ca_certs: Optional[str] = None
    index_name: str = "arxiv-papers"
    chunk_index_suffix: str = "chunks"  # Creates single hybrid index: {index_name}-{suffix}
    index_generation: str = Field("v1", pattern=r"^[a-zA-Z0-9._-]+$")
    read_alias_suffix: str = Field("read", pattern=r"^[a-zA-Z0-9._-]+$")
    write_alias_suffix: str = Field("write", pattern=r"^[a-zA-Z0-9._-]+$")
    max_text_size: int = 1000000

    # Vector search settings
    vector_dimension: int = 1024  # Jina embeddings dimension
    vector_space_type: str = "cosinesimil"  # cosinesimil, l2, innerproduct

    # Hybrid search settings
    rrf_pipeline_name: str = "hybrid-rrf-pipeline"
    hybrid_search_size_multiplier: int = 4  # Candidate depth before returning final K


class LangfuseSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
        populate_by_name=True,
    )

    # Prefer the official SDK environment variables while retaining legacy
    # double-underscore aliases used by earlier course versions.
    public_key: str = Field(
        "", validation_alias=AliasChoices("LANGFUSE_PUBLIC_KEY", "LANGFUSE__PUBLIC_KEY")
    )
    secret_key: str = Field(
        "",
        validation_alias=AliasChoices("LANGFUSE_SECRET_KEY", "LANGFUSE__SECRET_KEY"),
        repr=False,
    )
    base_url: str = Field(
        "https://cloud.langfuse.com",
        validation_alias=AliasChoices(
            "LANGFUSE_BASE_URL",
            "LANGFUSE_HOST",
            "LANGFUSE__BASE_URL",
            "LANGFUSE__HOST",
        ),
    )
    enabled: bool = Field(True, validation_alias=AliasChoices("LANGFUSE_ENABLED", "LANGFUSE__ENABLED"))
    flush_at: int = Field(15, validation_alias=AliasChoices("LANGFUSE_FLUSH_AT", "LANGFUSE__FLUSH_AT"))
    flush_interval: float = Field(
        1.0, validation_alias=AliasChoices("LANGFUSE_FLUSH_INTERVAL", "LANGFUSE__FLUSH_INTERVAL")
    )
    timeout: int = Field(5, validation_alias=AliasChoices("LANGFUSE_TIMEOUT", "LANGFUSE__TIMEOUT"))
    debug: bool = Field(False, validation_alias=AliasChoices("LANGFUSE_DEBUG", "LANGFUSE__DEBUG"))
    sample_rate: float = Field(
        1.0, validation_alias=AliasChoices("LANGFUSE_SAMPLE_RATE", "LANGFUSE__SAMPLE_RATE"), ge=0.0, le=1.0
    )
    capture_content: bool = Field(
        False,
        validation_alias=AliasChoices("LANGFUSE_CAPTURE_CONTENT", "LANGFUSE__CAPTURE_CONTENT"),
    )


class RedisSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="REDIS__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    host: str = "localhost"
    port: int = 6379
    password: str = Field("", repr=False)
    ssl: bool = False
    ssl_ca_certs: Optional[str] = None
    ssl_cert_reqs: Literal["required", "optional", "none"] = "required"
    db: int = 0
    decode_responses: bool = True
    socket_timeout: int = 30
    socket_connect_timeout: int = 30

    # Cache settings
    ttl_hours: int = 6  # Cache TTL in hours


class TelegramSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="TELEGRAM__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    bot_token: str = Field("", repr=False)
    enabled: bool = False


class Settings(BaseConfigSettings):
    app_version: str = "0.1.0"
    debug: bool = True
    environment: Literal["development", "staging", "production"] = "development"
    service_name: str = "rag-api"
    service_role: Literal["api", "ingestion"] = "api"
    opensearch_schema_management_enabled: bool = True

    # Public API perimeter. Development remains backwards compatible, while
    # production validation below refuses to start without both controls.
    api_auth_enabled: bool = False
    api_keys: List[SecretStr] = Field(default_factory=list)
    api_rate_limit_enabled: bool = False
    api_rate_limit_requests: int = Field(60, ge=1, le=100000)
    api_global_rate_limit_requests: int = Field(600, ge=1, le=1000000)
    api_rate_limit_window_seconds: int = Field(60, ge=1, le=86400)
    api_security_redis_timeout_seconds: float = Field(0.25, gt=0.0, le=5.0)
    feedback_ownership_ttl_seconds: int = Field(86400, ge=60, le=2592000)
    trust_incoming_request_id: bool = False
    allow_production_content_capture: bool = False

    postgres_database_url: str = Field(
        "postgresql://rag_user:rag_password@localhost:5432/rag_db",
        repr=False,
    )
    postgres_echo_sql: bool = False
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 0

    index_reconciliation_batch_size: int = Field(100, ge=1, le=1000)
    index_reconciliation_max_attempts: int = Field(3, ge=1, le=20)
    index_reconciliation_retry_base_seconds: int = Field(300, ge=1, le=86400)
    index_reconciliation_lease_seconds: int = Field(900, ge=30, le=86400)

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:1b"
    ollama_timeout: int = 300

    # Provider-neutral LLM configuration. Ollama remains the default so an
    # existing deployment keeps working until LLM_PROVIDER is changed.
    llm_provider: Literal["ollama", "openai"] = "ollama"
    llm_model: Optional[str] = None
    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.4-mini-2026-03-17"
    openai_timeout: float = 120.0
    openai_max_retries: int = 2
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh"] = "none"
    openai_allowed_models: List[str] = Field(
        default_factory=lambda: ["gpt-5.4-mini-2026-03-17"]
    )
    openai_max_output_tokens: int = Field(512, ge=1, le=128000)

    # Jina AI embeddings configuration
    jina_api_key: str = Field("", repr=False)

    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)
    pdf_parser: PDFParserSettings = Field(default_factory=PDFParserSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)

    @property
    def selected_llm_model(self) -> str:
        """Return the configured model for the active provider."""
        if self.llm_model:
            return self.llm_model
        if self.llm_provider == "openai":
            return self.openai_model
        return self.ollama_model

    @model_validator(mode="after")
    def validate_openai_model_policy(self) -> "Settings":
        """Fail startup when the configured hosted model bypasses policy."""
        if self.llm_provider == "openai" and self.selected_llm_model not in self.openai_allowed_models:
            raise ValueError(
                f"Configured OpenAI model '{self.selected_llm_model}' is not in OPENAI_ALLOWED_MODELS"
            )
        if self.environment == "production":
            violations = []
            if self.debug:
                violations.append("DEBUG must be false")
            if self.opensearch_schema_management_enabled:
                violations.append("OPENSEARCH_SCHEMA_MANAGEMENT_ENABLED must be false")
            database_url = urlparse(self.postgres_database_url)
            database_query = parse_qs(database_url.query)
            if not database_url.hostname or not database_url.username or not database_url.password:
                violations.append("POSTGRES_DATABASE_URL must include an authenticated remote database")
            elif _is_placeholder_secret(database_url.password):
                violations.append("POSTGRES_DATABASE_URL must not contain a placeholder password")
            if database_query.get("sslmode", [""])[0] not in {"require", "verify-ca", "verify-full"}:
                violations.append("POSTGRES_DATABASE_URL must require TLS with sslmode")

            opensearch_password = self.opensearch.password.get_secret_value()
            opensearch_url = urlparse(self.opensearch.host)
            if opensearch_url.scheme != "https":
                violations.append("OPENSEARCH__HOST must use HTTPS")
            if opensearch_url.username or opensearch_url.password:
                violations.append("OpenSearch credentials must not be embedded in OPENSEARCH__HOST")
            if not self.opensearch.verify_certs:
                violations.append("OPENSEARCH__VERIFY_CERTS must be true")
            if not self.opensearch.username or _is_placeholder_secret(opensearch_password):
                violations.append("OpenSearch production authentication must be configured")

            if _is_placeholder_secret(self.jina_api_key):
                violations.append("JINA_API_KEY must be a non-placeholder secret")

            if self.service_role == "api":
                if not self.api_auth_enabled:
                    violations.append("API_AUTH_ENABLED must be true")
                api_key_values = [secret.get_secret_value() for secret in self.api_keys]
                if not api_key_values:
                    violations.append("API_KEYS must contain at least one key")
                elif any(
                    len(value) < 24 or "changeme" in value.lower() for value in api_key_values
                ):
                    violations.append("API_KEYS must not contain short or placeholder keys")
                if not self.api_rate_limit_enabled:
                    violations.append("API_RATE_LIMIT_ENABLED must be true")

                if not self.redis.ssl or self.redis.ssl_cert_reqs != "required":
                    violations.append("Redis TLS with certificate verification is required")
                if _is_placeholder_secret(self.redis.password):
                    violations.append("REDIS__PASSWORD must be a non-placeholder secret")

                if self.llm_provider == "openai":
                    if not self.openai_base_url.startswith("https://"):
                        violations.append("OPENAI_BASE_URL must use HTTPS")
                    if _is_placeholder_secret(self.openai_api_key.get_secret_value()):
                        violations.append("OPENAI_API_KEY must be a non-placeholder secret")
                elif not self.ollama_host.startswith("https://"):
                    violations.append("OLLAMA_HOST must use HTTPS in production")

                if self.langfuse.enabled:
                    if not self.langfuse.base_url.startswith("https://"):
                        violations.append("LANGFUSE_BASE_URL must use HTTPS")
                    if not self.langfuse.public_key or _is_placeholder_secret(
                        self.langfuse.secret_key
                    ):
                        violations.append("Langfuse production credentials must be configured")
                if self.langfuse.capture_content and not self.allow_production_content_capture:
                    violations.append(
                        "LANGFUSE_CAPTURE_CONTENT requires ALLOW_PRODUCTION_CONTENT_CAPTURE=true"
                    )
                if self.telegram.enabled and _is_placeholder_secret(self.telegram.bot_token):
                    violations.append("TELEGRAM__BOT_TOKEN must be a non-placeholder secret")
            if violations:
                raise ValueError("Unsafe production configuration: " + "; ".join(violations))
        return self

    @field_validator("postgres_database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not (v.startswith("postgresql://") or v.startswith("postgresql+psycopg2://")):
            raise ValueError("Database URL must start with 'postgresql://' or 'postgresql+psycopg2://'")
        return v


def get_settings() -> Settings:
    return Settings()
