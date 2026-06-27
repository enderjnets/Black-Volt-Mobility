"""Versioned legal documents (client terms & driver IC agreement).

The document TEXT lives as markdown files next to this module
(``<doc_type>.<lang>.md``); the authoritative VERSION lives here in code.
Bumping a version forces every affected user to re-sign on their next session,
which automatically covers existing users.
"""
from __future__ import annotations

from pathlib import Path

CLIENT_TERMS = "client_terms"
DRIVER_AGREEMENT = "driver_agreement"

# audience: which user type must sign. version: bump to force re-consent.
LEGAL_DOCS: dict[str, dict[str, str]] = {
    CLIENT_TERMS: {"audience": "client", "version": "1.0"},
    DRIVER_AGREEMENT: {"audience": "driver", "version": "1.0"},
}

_DIR = Path(__file__).resolve().parent
_DEFAULT_LANG = "en"
_SUPPORTED_LANGS = ("en", "es")


def is_known_doc(doc_type: str) -> bool:
    return doc_type in LEGAL_DOCS


def current_version(doc_type: str) -> str:
    return LEGAL_DOCS[doc_type]["version"]


def audience(doc_type: str) -> str:
    return LEGAL_DOCS[doc_type]["audience"]


def normalize_lang(lang: str | None) -> str:
    return lang if lang in _SUPPORTED_LANGS else _DEFAULT_LANG


def _first_heading(md: str) -> str | None:
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip()
    return None


def load_doc(doc_type: str, lang: str = _DEFAULT_LANG) -> tuple[str, str]:
    """Return ``(title, markdown_content)`` for a document in the requested
    language, falling back to English if the localized file is missing."""
    if doc_type not in LEGAL_DOCS:
        raise KeyError(doc_type)
    lang = normalize_lang(lang)
    path = _DIR / f"{doc_type}.{lang}.md"
    if not path.exists():
        path = _DIR / f"{doc_type}.{_DEFAULT_LANG}.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    title = _first_heading(text) or doc_type.replace("_", " ").title()
    return title, text
