from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("TRENDWATCH_ROOT", Path(__file__).resolve().parent.parent))


@dataclass
class Field:
    key: str
    label: str
    arxiv_categories: list[str]
    news_query: str
    keywords: list[str]
    _kw_re: re.Pattern | None = None

    def matches(self, text: str) -> bool:
        if self._kw_re is None:
            parts = [re.escape(k.lower()) for k in self.keywords]
            self._kw_re = re.compile(r"(?<![a-z0-9])(" + "|".join(parts) + r")(?![a-z0-9])")
        return bool(self._kw_re.search(text.lower()))


@dataclass
class Config:
    raw: dict
    fields: dict[str, Field] = field(default_factory=dict)

    @property
    def windows(self) -> dict:
        return self.raw.get("windows", {})

    @property
    def discovery(self) -> dict:
        return self.raw.get("discovery", {})

    @property
    def tracked_terms(self) -> list[dict]:
        return self.raw.get("tracked_terms") or []

    def exclude_regexes(self) -> list[re.Pattern]:
        pats = list(self.raw.get("exclude_patterns") or [])
        ex_file = data_dir() / "exclude.txt"
        if ex_file.exists():
            for line in ex_file.read_text(encoding="utf-8").splitlines():
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    pats.append("^" + re.escape(line) + "$")
        return [re.compile(p, re.I) for p in pats]

    def fields_for_arxiv(self, categories: list[str]) -> list[str]:
        out = []
        for f in self.fields.values():
            if any(c in f.arxiv_categories for c in categories):
                out.append(f.key)
        return out

    def fields_for_text(self, text: str) -> list[str]:
        return [f.key for f in self.fields.values() if f.matches(text)]


def data_dir() -> Path:
    d = ROOT / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def docs_dir() -> Path:
    d = ROOT / "docs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_config(path: Path | None = None) -> Config:
    path = path or ROOT / "config.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg = Config(raw=raw)
    for key, f in (raw.get("fields") or {}).items():
        cfg.fields[key] = Field(
            key=key,
            label=f.get("label", key),
            arxiv_categories=list(f.get("arxiv_categories") or []),
            news_query=f.get("news_query", ""),
            keywords=[str(k) for k in (f.get("keywords") or [])],
        )
    return cfg
