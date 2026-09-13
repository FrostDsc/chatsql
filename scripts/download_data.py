"""下载 BIRD mini_dev 数据集（SQLite 版）到 data/ 目录。

来源：bird-bench 官方 OSS 直链（与 GitHub README 中的下载入口一致）。
用法：uv run python scripts/download_data.py
"""
from __future__ import annotations

import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ZIP_PATH = DATA_DIR / "minidev.zip"
URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip"

EXPECTED_JSON = "mini_dev_data/mini_dev_sqlite.json"
MANUAL_HINT = f"""\
自动下载失败，请手动下载：
  1. 打开 {URL}（或 GitHub bird-bench/mini_dev README 中的 Complete Package 链接）
  2. 解压后将 mini_dev_data/ 目录放到 {DATA_DIR}/ 下
  3. 确认存在 {EXPECTED_JSON} 和 mini_dev_data/dev_databases/ 目录
"""


def _download(url: str, dest: Path) -> None:
    print(f"下载 {url} ...")
    with urllib.request.urlopen(url, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        with open(dest, "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r  {downloaded / 1e6:.1f}/{total / 1e6:.1f} MB ({pct}%)", end="", flush=True)
    print()


def _verify() -> list[str]:
    problems = []
    json_path = DATA_DIR / EXPECTED_JSON
    if not json_path.exists():
        problems.append(f"缺少 {EXPECTED_JSON}")
    db_root = DATA_DIR / "mini_dev_data" / "dev_databases"
    if not db_root.is_dir():
        problems.append("缺少 mini_dev_data/dev_databases/")
    else:
        dbs = sorted(db_root.glob("*/*.sqlite"))
        if len(dbs) < 11:
            problems.append(f"dev_databases 下仅找到 {len(dbs)} 个 .sqlite（预期 11 个）")
    return problems


def _normalize_layout() -> None:
    """zip 实际结构为 minidev/MINIDEV（SQLite）+ MINIDEV_mysql/_postgresql。
    只保留 SQLite 部分并移到 data/mini_dev_data/，删除其余约 2GB 内容。"""
    src = DATA_DIR / "minidev" / "MINIDEV"
    dest = DATA_DIR / "mini_dev_data"
    if src.exists() and not dest.exists():
        src.rename(dest)
    shutil.rmtree(DATA_DIR / "minidev", ignore_errors=True)


def main() -> int:
    DATA_DIR.mkdir(exist_ok=True)

    if not (DATA_DIR / EXPECTED_JSON).exists():
        if not (DATA_DIR / "minidev" / "MINIDEV").exists():
            try:
                _download(URL, ZIP_PATH)
                print("解压中...")
                with zipfile.ZipFile(ZIP_PATH) as zf:
                    zf.extractall(DATA_DIR)
            except Exception as e:
                print(f"\n{e}\n{MANUAL_HINT}")
                return 1
            finally:
                ZIP_PATH.unlink(missing_ok=True)
        _normalize_layout()

    problems = _verify()
    if problems:
        print("校验未通过：")
        for p in problems:
            print(f"  - {p}")
        print(MANUAL_HINT)
        return 1

    db_count = len(list((DATA_DIR / "mini_dev_data" / "dev_databases").glob("*/*.sqlite")))
    print(f"完成：{db_count} 个 SQLite 数据库 + 500 条问答对，位于 data/mini_dev_data/")
    return 0


if __name__ == "__main__":
    shutil.rmtree(DATA_DIR / "__MACOSX", ignore_errors=True)
    sys.exit(main())
