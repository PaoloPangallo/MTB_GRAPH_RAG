"""Print the complete execution plan without executing any run."""

from __future__ import annotations

import json

from .common.runner import dry_run


def main() -> None:
    kinds = ["rq1", "rq2", "rq3", "rq4", "narrative", "operational", "reliability", "latency"]
    print(json.dumps({kind: dry_run(kind) for kind in kinds}, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
