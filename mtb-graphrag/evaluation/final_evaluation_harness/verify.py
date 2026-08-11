"""Static identity verification entry point."""

from __future__ import annotations

import json

from .common.protocol_loader import load_protocol


def main() -> None:
    protocol = load_protocol()
    print(json.dumps({"protocol": protocol.hashes, "frozen": True, "final_results": False}, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
