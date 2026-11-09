"""Typed errors for pdf_form_filler."""

from __future__ import annotations

from typing import Literal

ErrorCode = Literal[
    "not_a_pdf",
    "encrypted",
    "malformed",
    "input_too_large",
    "unknown_field",
    "read_only",
    "value_too_long",
    "invalid_option",
    "unsupported_character",
    "no_form",
]


class FormError(Exception):
    """Base error raised by pdf_form_filler with a machine-readable code."""

    def __init__(self, code: ErrorCode, message: str = "") -> None:
        self.code: ErrorCode = code
        super().__init__(f"{code}: {message}" if message else code)
