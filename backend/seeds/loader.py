"""Filesystem-backed `ProjectDocument` loader for the stock seeds.

Discovers every `*.json` under `seeds/projects/`, parses it through
`ProjectDocument.model_validate` (so any schema mismatch surfaces at
boot), and exposes them by slug.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from models.project_document import ProjectDocument


SEEDS_DIR = Path(__file__).resolve().parent / "projects"


@lru_cache(maxsize=1)
def load_all_seed_documents() -> dict[str, ProjectDocument]:
    """Returns a {slug: ProjectDocument} map of every bundled seed."""
    out: dict[str, ProjectDocument] = {}
    if not SEEDS_DIR.exists():
        return out
    for path in sorted(SEEDS_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        doc = ProjectDocument.model_validate(payload)
        out[doc.slug] = doc
    return out


def load_seed_document(slug: str) -> ProjectDocument | None:
    return load_all_seed_documents().get(slug)


def seed_slugs() -> list[str]:
    return list(load_all_seed_documents().keys())
