"""Pydantic request/response schemas for the Ingress API."""

from typing import Literal

from pydantic import BaseModel, field_validator


class ClassifierResponse(BaseModel):
    intent: Literal["execution", "decomposition", "novel_reasoning", "ambiguous"]
    confidence: float


class IngestRequest(BaseModel):
    input: str

    @field_validator("input")
    @classmethod
    def input_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("input must not be empty or whitespace")
        return v


class IngestResponse(BaseModel):
    intent: str
    confidence: float
    response: str
