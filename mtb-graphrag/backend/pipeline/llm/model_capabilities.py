"""Rilevazione delle capacita' di un modello Ollama.

Le capacita' vengono **osservate** interrogando l'istanza, non dedotte dal nome. Un
modello che si chiama come uno noto per supportare i tool non necessariamente li
supporta nella build servita, e il cloud espone metadati diversi dal locale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ollama_adapter import JSON_SCHEMA, PROMPT_VALIDATED, OllamaEndpoint

# Ollama accetta un JSON Schema nel campo `format` a partire dalla 0.5.
_STRUCTURED_OUTPUT_MIN_VERSION = (0, 5, 0)

UNSUPPORTED = "unsupported"


def parse_version(raw: str) -> tuple[int, int, int]:
    parts: list[int] = []
    for chunk in str(raw or "").split(".")[:3]:
        digits = "".join(character for character in chunk if character.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


@dataclass(frozen=True)
class ModelCapabilities:
    model_name: str
    tag: str
    digest: str
    parameter_size: str
    quantization: str
    family: str
    context_length: int | None
    tool_calling: bool
    structured_output_mode: str
    raw_capabilities: tuple[str, ...] = ()
    modified_at: str = ""
    size_bytes: int = 0
    local_or_cloud: str = "local"
    endpoint: str = ""
    ollama_version: str = ""
    detection_notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def supports_structured_output(self) -> bool:
        return self.structured_output_mode == JSON_SCHEMA

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "tag": self.tag,
            "digest": self.digest,
            "parameter_size": self.parameter_size,
            "quantization": self.quantization,
            "family": self.family,
            "context_length": self.context_length,
            "tool_calling": self.tool_calling,
            "structured_output_mode": self.structured_output_mode,
            "supports_structured_output": self.supports_structured_output,
            "raw_capabilities": list(self.raw_capabilities),
            "modified_at": self.modified_at,
            "size_bytes": self.size_bytes,
            "local_or_cloud": self.local_or_cloud,
            "endpoint": self.endpoint,
            "ollama_version": self.ollama_version,
            "detection_notes": list(self.detection_notes),
        }


def _context_length(model_info: dict[str, Any]) -> int | None:
    for key, value in (model_info or {}).items():
        if key.endswith(".context_length"):
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


def detect_structured_output_mode(
    endpoint: OllamaEndpoint, ollama_version: str
) -> tuple[str, str]:
    """Modalita' disponibile, con la ragione della scelta.

    Locale con Ollama >= 0.5: JSON Schema imposto dal server, che vincola il
    decoding. Cloud: lo schema non e' garantito, quindi il JSON va chiesto nel prompt
    e validato localmente. Sono due garanzie diverse e vanno registrate come tali.
    """
    if endpoint.is_cloud:
        return (
            PROMPT_VALIDATED,
            "endpoint cloud: schema non imposto dal server, JSON richiesto nel prompt "
            "e validato localmente",
        )
    if parse_version(ollama_version) >= _STRUCTURED_OUTPUT_MIN_VERSION:
        return (JSON_SCHEMA, f"Ollama {ollama_version} accetta un JSON Schema in `format`")
    return (
        PROMPT_VALIDATED,
        f"Ollama {ollama_version} precedente alla 0.5: nessun structured output nativo",
    )


def from_show_response(
    model: str,
    listing: dict[str, Any],
    show: dict[str, Any],
    *,
    endpoint: OllamaEndpoint,
    ollama_version: str,
) -> ModelCapabilities:
    """Costruisce le capacita' dalle risposte di /api/tags e /api/show."""
    details = show.get("details") or listing.get("details") or {}
    capabilities = tuple(show.get("capabilities") or ())
    name = show.get("model") or listing.get("name") or model
    tag = name.partition(":")[2] or "latest"

    mode, reason = detect_structured_output_mode(endpoint, ollama_version)
    notes = [reason]

    tool_calling = "tools" in capabilities
    if not capabilities:
        # Fallback osservabile: il template dichiara i tool quando il modello li usa.
        tool_calling = "tools" in str(show.get("template") or "")
        notes.append("capabilities non esposte: tool_calling dedotto dal template")

    return ModelCapabilities(
        model_name=name,
        tag=tag,
        digest=str(show.get("digest") or listing.get("digest") or ""),
        parameter_size=str(details.get("parameter_size") or ""),
        quantization=str(details.get("quantization_level") or ""),
        family=str(details.get("family") or ""),
        context_length=_context_length(show.get("model_info") or {}),
        tool_calling=tool_calling,
        structured_output_mode=mode,
        raw_capabilities=capabilities,
        modified_at=str(show.get("modified_at") or listing.get("modified_at") or ""),
        size_bytes=int(listing.get("size") or 0),
        local_or_cloud=endpoint.kind,
        endpoint=endpoint.sanitized,
        ollama_version=ollama_version,
        detection_notes=tuple(notes),
    )
