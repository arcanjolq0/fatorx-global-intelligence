"""Minimal FastAPI composition for the technical foundation."""

from typing import Final, Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

APP_NAME: Final = "Fator X Global Intelligence API"
SERVICE_NAME: Final = "fatorx-global-intelligence-api"


class HealthResponse(BaseModel):
    """Typed response returned by the health endpoint."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"
    service: Literal["fatorx-global-intelligence-api"] = SERVICE_NAME


app = FastAPI(
    title=APP_NAME,
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def get_health() -> HealthResponse:
    """Report process health without consulting any external dependency."""

    return HealthResponse()
