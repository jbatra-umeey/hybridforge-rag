import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    mode: str = "demo"
    sqlite_path: str = "data/demo.db"
    database_url: str = ""
    demo_token: str = ""
    provider_key: str = ""
    provider_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    generation_model: str = "gpt-4.1-mini"
    dimensions: int = 1536
    issuer: str = ""
    audience: str = ""
    jwks_url: str = ""
    reranker: str = "none"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    min_dense_score: float = 0.25
    context_chars: int = 16000
    max_inflight: int = 8
    rpm: int = 60

    @classmethod
    def from_env(cls):
        return cls(
            mode=os.getenv("RAG_MODE", "demo"),
            sqlite_path=os.getenv("SQLITE_PATH", "data/demo.db"),
            database_url=os.getenv("DATABASE_URL", ""),
            demo_token=os.getenv("DEMO_TOKEN", ""),
            provider_key=os.getenv("OPENAI_API_KEY", ""),
            provider_url=os.getenv("PROVIDER_URL", "https://api.openai.com/v1"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            generation_model=os.getenv("GENERATION_MODEL", "gpt-4.1-mini"),
            dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "1536")),
            issuer=os.getenv("OIDC_ISSUER", ""),
            audience=os.getenv("OIDC_AUDIENCE", ""),
            jwks_url=os.getenv("OIDC_JWKS_URL", ""),
            reranker=os.getenv("RERANKER", "none"),
            reranker_model=os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
            min_dense_score=float(os.getenv("MIN_DENSE_SCORE", "0.25")),
            max_inflight=int(os.getenv("MAX_INFLIGHT", "8")),
            rpm=int(os.getenv("REQUESTS_PER_MINUTE", "60")),
        )

    def validate(self):
        if self.mode not in {"demo", "production"}:
            raise ValueError("RAG_MODE must be demo or production")
        if self.reranker not in {"none", "cross_encoder"}:
            raise ValueError("Unsupported reranker")
        if self.max_inflight < 1 or self.rpm < 1 or self.context_chars < 1000:
            raise ValueError("Invalid resource bounds")
        if self.dimensions != 1536:
            raise ValueError("Schema v1 requires 1536 dimensions; migrate before changing")
        if not 0 <= self.min_dense_score <= 1:
            raise ValueError("MIN_DENSE_SCORE must be between 0 and 1")
        if self.mode == "demo":
            if len(self.demo_token) < 16:
                raise ValueError("Set a DEMO_TOKEN of at least 16 characters")
        else:
            if not all(
                [self.database_url, self.provider_key, self.issuer, self.audience, self.jwks_url]
            ):
                raise ValueError(
                    "Production requires database, model credentials and OIDC settings"
                )
            for url in [self.provider_url, self.issuer, self.jwks_url]:
                parsed = urlparse(url)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username:
                    raise ValueError("Production identity/model endpoints must use HTTPS")
