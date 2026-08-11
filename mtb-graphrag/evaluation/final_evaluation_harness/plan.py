"""Print the complete execution plan without executing any run."""

from __future__ import annotations

import json

from .common.runner import build_full_plan, dry_run, execution_plan_sha256
from .common.protocol_loader import load_protocol


def main() -> None:
    kinds = ["rq1", "rq2", "rq3", "rq4", "narrative", "operational", "reliability", "latency"]
    protocol=load_protocol()
    reports={kind: dry_run(kind) for kind in kinds}
    plans=build_full_plan(protocol)
    reports["execution_plan"]=[plan.__dict__ for plan in plans]
    reports["execution_plan_sha256"]=execution_plan_sha256(plans)
    reports["planned_executions"]=len(plans)
    print(json.dumps(reports, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
