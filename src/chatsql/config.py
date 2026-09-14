"""加载 configs/settings.yaml，支持 ${VAR:-default} 环境变量展开。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_ENV_PATTERN = re.compile(r"\$\{(\w+)(?::-(.*?))?\}")


def _expand(value: str) -> str:
    def repl(match: re.Match) -> str:
        var, default = match.group(1), match.group(2)
        return os.environ.get(var, default if default is not None else "")

    return _ENV_PATTERN.sub(repl, value)


def _walk(node):
    if isinstance(node, str):
        return _expand(node)
    if isinstance(node, dict):
        return {k: _walk(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk(v) for v in node]
    return node


@dataclass(frozen=True)
class ModelConfig:
    name: str
    base_url: str
    api_key: str
    temperature: float = 0.0
    max_tokens: int = 2048
    timeout: int = 60


@dataclass(frozen=True)
class RagConfig:
    enabled: bool = True
    top_k_examples: int = 3
    top_k_knowledge: int = 3
    embedding_model: str = "all-MiniLM-L6-v2"
    index_dir: Path = field(default=PROJECT_ROOT / "data" / "index")


@dataclass(frozen=True)
class Settings:
    model: ModelConfig
    db_root: Path
    exec_timeout: int = 30
    exec_max_rows: int = 100
    mock_enabled: bool = field(default=False)
    agent_max_rounds: int = 3
    linking_table_threshold: int = 20
    retry_on_empty: bool = True
    trace_dir: Path = field(default=PROJECT_ROOT / "runs")
    rag: RagConfig = field(default_factory=RagConfig)

    @property
    def use_mock(self) -> bool:
        return self.mock_enabled or not self.model.api_key


def load_settings(config_path: str | Path | None = None) -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    path = Path(config_path) if config_path else PROJECT_ROOT / "configs" / "settings.yaml"
    raw = _walk(yaml.safe_load(path.read_text(encoding="utf-8")))

    model = raw["model"]
    db_root = Path(raw["database"]["root"])
    if not db_root.is_absolute():
        db_root = PROJECT_ROOT / db_root

    agent = raw.get("agent", {})
    trace_dir = Path(agent.get("trace_dir", "runs"))
    if not trace_dir.is_absolute():
        trace_dir = PROJECT_ROOT / trace_dir

    return Settings(
        model=ModelConfig(
            name=model["name"],
            base_url=model["base_url"],
            api_key=model.get("api_key") or "",
            temperature=float(model.get("temperature", 0.0)),
            max_tokens=int(model.get("max_tokens", 2048)),
            timeout=int(model.get("timeout", 60)),
        ),
        db_root=db_root,
        exec_timeout=int(raw.get("execution", {}).get("timeout_seconds", 30)),
        exec_max_rows=int(raw.get("execution", {}).get("max_rows", 100)),
        mock_enabled=str(raw.get("mock", {}).get("enabled", "0")).lower() in ("1", "true", "yes"),
        agent_max_rounds=int(agent.get("max_correction_rounds", 3)),
        linking_table_threshold=int(agent.get("linking_table_threshold", 20)),
        retry_on_empty=str(agent.get("retry_on_empty", True)).lower() in ("1", "true", "yes"),
        trace_dir=trace_dir,
        rag=_parse_rag(raw.get("rag", {})),
    )


def _parse_rag(raw: dict) -> RagConfig:
    index_dir = Path(raw.get("index_dir", "data/index"))
    if not index_dir.is_absolute():
        index_dir = PROJECT_ROOT / index_dir
    return RagConfig(
        enabled=str(raw.get("enabled", True)).lower() in ("1", "true", "yes"),
        top_k_examples=int(raw.get("top_k_examples", 3)),
        top_k_knowledge=int(raw.get("top_k_knowledge", 3)),
        embedding_model=str(raw.get("embedding_model", "all-MiniLM-L6-v2")),
        index_dir=index_dir,
    )


def resolve_db_path(settings: Settings, db_id: str) -> Path:
    """mini_dev 结构：dev_databases/<db_id>/<db_id>.sqlite"""
    path = settings.db_root / db_id / f"{db_id}.sqlite"
    if not path.exists():
        candidates = sorted(p.parent.name for p in settings.db_root.glob("*/*.sqlite"))
        raise FileNotFoundError(
            f"数据库 '{db_id}' 不存在：{path}\n可用数据库：{', '.join(candidates) or '（无，请先运行 scripts/download_data.py）'}"
        )
    return path
