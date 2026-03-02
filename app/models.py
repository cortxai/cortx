"""Pydantic request/response schemas for the Ingress API."""

from pydantic import BaseModel


class IngestRequest(BaseModel):
    input: str


class IngestResponse(BaseModel):
    intent: str
    response: str
