from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class RawItem:
    source: str
    domain: str
    kind: str
    title: str
    content: str
    url: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        if isinstance(self.meta, dict) and self.meta.get("dedup_key"):
            return str(self.meta["dedup_key"])
        base = self.url or (self.source + self.title + self.content[:120])
        return hashlib.sha256(base.encode("utf-8")).hexdigest()


class Collector:
    name = "base"
    domain = "business"

    def collect(self) -> list[RawItem]:
        raise RuntimeError("Collector subclasses must implement collect")
