from typing import Literal

from pydantic import Field

from cad_to_facts.domain.source import DomainModel


AnswerStatus = Literal[
    "answered", "partial", "ambiguous", "unresolved", "unsupported", "failed"
]


class AnswerGap(DomainModel):
    """Shared answer limitation, independent of the source format profile."""

    code: str
    message: str
    interpretation_ids: list[str] = Field(default_factory=list)
