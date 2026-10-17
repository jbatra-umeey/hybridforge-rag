from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, field_validator

ID_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$"


@dataclass(frozen=True)
class Principal:
    tenant: str
    subject: str
    groups: tuple[str, ...] = ()
    scopes: frozenset[str] = frozenset({"rag:read"})

    @property
    def can_write(self):
        return "rag:write" in self.scopes


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    document_id: str = Field(pattern=ID_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    source: str = Field(default="manual", min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=100_000)
    acl_groups: list[str] = Field(default_factory=list, max_length=32)
    expected_version: int = Field(default=0, ge=0)

    @field_validator("acl_groups")
    @classmethod
    def valid_groups(cls, value):
        import re

        if any(not re.fullmatch(ID_PATTERN, group) for group in value):
            raise ValueError("Invalid group identifier")
        return sorted(set(value))


class QueryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=12)
    candidate_k: int = Field(default=30, ge=5, le=100)
    mode: str = Field(default="hybrid", pattern=r"^(hybrid|lexical|dense)$")


@dataclass
class Hit:
    chunk_id: str
    document_id: str
    version: int
    title: str
    source: str
    text: str
    start: int
    end: int
    score: float = 0.0
    ranks: dict = field(default_factory=dict)
    rerank_score: float | None = None


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1500)
    chunk_id: str
    quote: str = Field(min_length=12, max_length=1500)


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[EvidenceClaim] = Field(max_length=8)


class Conflict(Exception):
    pass


class ProviderError(Exception):
    pass
