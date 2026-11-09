"""Behavior tests for the public API of pdf_form_filler."""

from __future__ import annotations

import pytest

import pdf_form_filler


def test_normalize_trims_and_lowercases() -> None:
    assert pdf_form_filler.normalize("  Hello World ") == "hello world"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_normalize_rejects_blank_input(value: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        pdf_form_filler.normalize(value)


def test_version_is_semver() -> None:
    parts = pdf_form_filler.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
