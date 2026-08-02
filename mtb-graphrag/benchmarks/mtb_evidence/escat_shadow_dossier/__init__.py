"""Offline, read-only ESCAT dossier shadow adapter."""

from .adapter import build_shadow_dossier, present_assessment, resolve_assessment

__all__ = ["build_shadow_dossier", "present_assessment", "resolve_assessment"]
