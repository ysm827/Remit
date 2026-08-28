"""HTTP contracts for runtime model configuration and problem ingestion."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiProbeRequest(BaseModel):
    """Connection details supplied by the settings dialog."""

    api_key: str
    model_id: str
    base_url: str = "https://api.openai.com/v1"
    api_type: str = "openai-chat"


class ValidationResult(BaseModel):
    """Uniform result returned by lightweight external-service probes."""

    valid: bool
    message: str


class OpenAlexProbeRequest(BaseModel):
    email: str


class AgentConfigurationStatus(BaseModel):
    """Effective, non-secret configuration for one workflow role."""

    configured: bool
    api_key_configured: bool
    context_window: int
    source: Literal["environment", "runtime", "missing"]
    api_type: str | None = None
    model_id: str | None = None
    base_url: str | None = None


class ConfigurationStatus(BaseModel):
    configured: bool
    model_council_enabled: bool
    agents: dict[str, AgentConfigurationStatus]


class SaveConfigurationRequest(BaseModel):
    coordinator: dict[str, Any]
    modeler: dict[str, Any]
    coder: dict[str, Any]
    writer: dict[str, Any]
    openalex_email: str
    model_scout: dict[str, Any] = Field(default_factory=dict)
    model_critic: dict[str, Any] = Field(default_factory=dict)
    model_council_enabled: bool | None = None

    def role_payloads(self) -> tuple[tuple[str, dict[str, Any]], ...]:
        """Return role settings in their backend-prefix order."""
        return (
            ("COORDINATOR", self.coordinator),
            ("MODELER", self.modeler),
            ("CODER", self.coder),
            ("WRITER", self.writer),
            ("MODEL_SCOUT", self.model_scout),
            ("MODEL_CRITIC", self.model_critic),
        )


class ProblemDocumentResult(BaseModel):
    filename: str
    text: str
    page_count: int
    char_count: int
    figure_count: int = 0
    vision_status: Literal["completed", "partial", "failed", "skipped", "disabled"] = (
        "skipped"
    )
    vision_error: str = ""
    figures: list[dict[str, Any]] = Field(default_factory=list)


# Public aliases keep the HTTP/router API stable while the implementation owns
# a smaller set of reusable contracts.
ValidateApiKeyRequest = ApiProbeRequest
ValidateApiKeyResponse = ValidationResult
ValidateOpenalexEmailRequest = OpenAlexProbeRequest
ValidateOpenalexEmailResponse = ValidationResult
AgentApiConfigStatus = AgentConfigurationStatus
ApiConfigStatusResponse = ConfigurationStatus
SaveApiConfigRequest = SaveConfigurationRequest
ProblemPdfParseResponse = ProblemDocumentResult
