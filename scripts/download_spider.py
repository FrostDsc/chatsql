"""下载 Spider 数据集（上一代 Text-to-SQL 基准）并转换为 mini_dev 兼容格式。

数据源：HF SALT-NLP/spider_VALUE 的 data.zip（官方 Google Drive 国内不可达；
该镜像含完整原版 Spider：dev.json + database/*.sqlite）。
用法：uv run python scripts/download_spider.py
产物：data/spider_data/spider_dev.json + data/spider_data/dev_databases/<db>/<db>.sqlite
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chatsql.eval.hardness import estimate_hardness  # noqa: E402

DATA_DIR = PROJECT_ROOT / "data"
ZIP_PATH = DATA_DIR / "spider_value_data.zip"
OUT_DIR = DATA_DIR / "spider_data"
OUT_JSON = OUT_DIR / "spider_dev.json"
OUT_DB_ROOT = OUT_DIR / "dev_databases"
REPO_ID = "SALT-NLP/spider_VALUE"
URL = f"https://huggingface.co/datasets/{REPO_ID}/resolve/main/data.zip"

MANUAL_HINT = f"""\
自动下载失败，请手动获取：
  1. 下载 {URL}（或设 HF_ENDPOINT 镜像后重试；官方渠道 yale-lily.github.io/spider）
  2. 解压后将 dev.json 与 database/ 目录放到 {DATA_DIR}/spider_raw/ 下，重跑本脚本
"""


def _download(dest: Path) -> None:
    """优先 huggingface_hub（断点续传 + 重试 + HF_ENDPOINT 镜像），失败退回裸 urllib。"""
    try:
        from huggingface_hub import hf_hub_download
        print("通过 huggingface_hub 下载（支持断点续传）...")
        src = hf_hub_download(repo_id=REPO_ID, filename="data.zip", repo_type="dataset")
        shutil.copy2(src, dest)
        return
    except Exception as e:
        print(f"hf_hub 下载失败（{e}），退回直接下载")
    print(f"下载 {URL} ...")
    with urllib.request.urlopen(URL, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        with open(dest, "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    print(f"\r  {downloaded / 1e6:.1f}/{total / 1e6:.1f} MB ({downloaded * 100 // total}%)",
                          end="", flush=True)
    print()


def _find_dev_json(root: Path) -> Path:
    """在解压目录里找 Spider 的 dev.json（排除 spider-realistic 等变体的同名文件）。"""
    candidates = [p for p in root.rglob("dev.json") if "realistic" not in str(p).lower()]
    if not candidates:
        raise FileNotFoundError("解压目录中找不到 dev.json")
    return min(candidates, key=lambda p: len(p.parts))  # 最浅的那个是主文件


def _find_database_dir(root: Path) -> Path:
    """找 database/ 目录：特征是下面有 <db_id>/<db_id>.sqlite 结构。"""
    for d in root.rglob("database"):
        if d.is_dir() and list(d.glob("*/*.sqlite")):
            return d
    raise FileNotFoundError("解压目录中找不到 database/<db>/<db>.sqlite 结构")


def _normalize(extract_root: Path, out_dir: Path = OUT_DIR) -> tuple[int, int]:
    """从解压目录归一化出 mini_dev 兼容格式，返回 (题目数, 库数)。"""
    dev_json = _find_dev_json(extract_root)
    db_src = _find_database_dir(extract_root)
    print(f"发现题目文件 {dev_json}\n发现库目录 {db_src}")

    samples = json.loads(dev_json.read_text(encoding="utf-8"))
    dev_db_ids = sorted({s["db_id"] for s in samples})
    missing = [d for d in dev_db_ids if not (db_src / d / f"{d}.sqlite").exists()]
    if missing:
        raise FileNotFoundError(f"以下 dev 库缺少 sqlite 文件：{missing}")

    out_json = out_dir / "spider_dev.json"
    out_db_root = out_dir / "dev_databases"
    out_db_root.mkdir(parents=True, exist_ok=True)
    converted = []
    for i, s in enumerate(samples):
        converted.append({
            "question_id": i,
            "db_id": s["db_id"],
            "question": s["question"],
            "evidence": "",  # Spider 无 evidence
            "SQL": s["query"],
            "difficulty": estimate_hardness(s["query"]),  # 启发式自算，与 BIRD 口径不同
        })
    out_json.write_text(json.dumps(converted, ensure_ascii=False, indent=1), encoding="utf-8")

    for db_id in dev_db_ids:
        dst = out_db_root / db_id
        dst.mkdir(exist_ok=True)
        shutil.copy2(db_src / db_id / f"{db_id}.sqlite", dst / f"{db_id}.sqlite")

    for db_id in dev_db_ids:  # 校验：每个 sqlite 能打开
        conn = sqlite3.connect(f"file:{out_db_root / db_id / f'{db_id}.sqlite'}?mode=ro", uri=True)
        conn.execute("SELECT 1")
        conn.close()
    return len(converted), len(dev_db_ids)


def main() -> int:
    if OUT_JSON.exists() and OUT_DB_ROOT.is_dir():
        print(f"已存在 {OUT_JSON}，跳过。如需重建请删除 {OUT_DIR}")
        return 0

    DATA_DIR.mkdir(exist_ok=True)
    raw = DATA_DIR / "spider_raw"
    tmp = None
    try:
        if raw.exists():  # 手动放置的解压目录
            extract_root = raw
        else:
            if not ZIP_PATH.exists():
                try:
                    _download(ZIP_PATH)
                except Exception as e:
                    print(f"\n{e}\n{MANUAL_HINT}")
                    return 1
            print("解压中...")
            tmp = Path(tempfile.mkdtemp(prefix="spider_extract_"))
            with zipfile.ZipFile(ZIP_PATH) as zf:
                zf.extractall(tmp)
            extract_root = tmp
        n_q, n_db = _normalize(extract_root)
    except FileNotFoundError as e:
        print(f"{e}\n{MANUAL_HINT}")
        return 1
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        ZIP_PATH.unlink(missing_ok=True)

    print(f"完成：{n_q} 题 / {n_db} 个库，位于 {OUT_DIR}")
    print("难度为启发式自算（easy/medium/hard/extra），与 BIRD 标注口径不同")
    return 0


if __name__ == "__main__":
    sys.exit(main())
