from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator


class DocumentRuleRequest(BaseModel):
    document_types: list[str] = Field(default_factory=list, max_length=20)
    title_contains: str | None = Field(default=None, max_length=120)
    issuer_contains: str | None = Field(default=None, max_length=120)
    organization_contains: str | None = Field(default=None, max_length=120)
    date_from: date | None = None
    date_to: date | None = None
    tags_any: list[str] = Field(default_factory=list, max_length=20)
    include_archived: bool = False

    @model_validator(mode="after")
    def validate_dates(self) -> DocumentRuleRequest:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from cannot be after date_to")
        return self
