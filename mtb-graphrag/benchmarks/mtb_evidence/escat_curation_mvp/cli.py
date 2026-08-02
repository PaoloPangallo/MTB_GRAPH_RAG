"""Compatibility entry point for the offline ESCAT workbench."""

from .workbench import export_dossier, main

__all__ = ["export_dossier", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
