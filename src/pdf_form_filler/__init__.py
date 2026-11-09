"""pdf_form_filler: Fill PDF AcroForm fields with validation and incremental updates."""

from __future__ import annotations

import logging

from pdf_form_filler.errors import FormError
from pdf_form_filler.models import Field
from pdf_form_filler.ops import fill, read_fields

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "Field",
    "FormError",
    "fill",
    "read_fields",
]
