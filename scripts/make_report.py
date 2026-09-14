"""聚合三次评测运行，生成消融对比报告。

用法：
    uv run python scripts/make_report.py direct_xxx agent_xxx agent_rag_xxx
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chatsql.config import load_settings  # noqa: E402
from chatsql.eval.report import build_report, load_details  # noqa: E402

REPORTS_ROOT = PROJECT_ROOT / "eval" / "reports"


def main() -> int:
    tags = sys.argv[1:]
    if not tags:
        print("用法：uv run python scripts/make_report.py <tag1> <tag2> [tag3 ...]")
        print("可用运行：")
        for d in sorted(REPORTS_ROOT.glob("*/details.jsonl")):
            n = len(load_details(d.parent))
            print(f"  {d.parent.name}  ({n} 题)")
        return 1

    run_dirs = []
    for tag in tags:
        d = REPORTS_ROOT / tag
        if not (d / "details.jsonl").exists():
            print(f"未找到 {d}/details.jsonl")
            return 1
        run_dirs.append(d)

    settings = load_settings()
    report = build_report(run_dirs, model_name=settings.model.name,
                          report_date=datetime.now().strftime("%Y-%m-%d"))
    out = REPORTS_ROOT / f"compare_{datetime.now():%Y%m%d-%H%M%S}.md"
    out.write_text(report, encoding="utf-8")
    print(f"报告已生成：{out}")
    print()
    # 终端预览总表
    in_table = False
    for line in report.splitlines():
        if line.startswith("## 总体结果"):
            in_table = True
        elif line.startswith("## ") and in_table:
            break
        if in_table:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
