"""Data models for pdf_form_filler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FieldKind = Literal["text", "checkbox", "radio", "choice", "signature"]


@dataclass(frozen=True)
class Field:
    """Represents a field in a PDF AcroForm."""

    name: str
    kind: FieldKind
    value: str | None
    options: tuple[str, ...]
    max_len: int | None
    read_only: bool
    required: bool
