"""Incremental PDF writer serializing PDF data types."""

from __future__ import annotations

from typing import Any

from pdf_form_filler.tokenizer import IndirectRef, PdfName, PdfString, StreamObj


def escape_pdf_literal_string(s: str) -> str:
    # ASCII printable only
    res: list[str] = ["("]
    for ch in s:
        if ch == "\\":
            res.append("\\\\")
        elif ch == "(":
            res.append("\\(")
        elif ch == ")":
            res.append("\\)")
        elif ch == "\r":
            res.append("\\r")
        elif ch == "\n":
            res.append("\\n")
        elif ch == "\t":
            res.append("\\t")
        else:
            res.append(ch)
    res.append(")")
    return "".join(res)


def to_pdf_string_literal(val: str) -> str:
    try:
        # Check if printable ASCII
        for c in val:
            if ord(c) < 32 or ord(c) > 126:
                raise ValueError()
        return escape_pdf_literal_string(val)
    except ValueError:
        # UTF-16BE hex string with BOM
        raw = b"\xfe\xff" + val.encode("utf-16-be")
        return f"<{raw.hex().upper()}>"


def serialize_obj(obj: Any) -> str:
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, float):
        if obj.is_integer():
            return str(int(obj))
        return f"{obj:.4f}".rstrip("0").rstrip(".")
    if isinstance(obj, IndirectRef):
        return f"{obj.num} {obj.gen} R"
    if isinstance(obj, PdfName):
        return f"/{obj.value}"
    if isinstance(obj, PdfString):
        if obj.is_hex:
            return f"<{obj.raw.hex().upper()}>"
        try:
            text = obj.raw.decode("latin1")
            return escape_pdf_literal_string(text)
        except Exception:
            return f"<{obj.raw.hex().upper()}>"
    if isinstance(obj, str):
        return to_pdf_string_literal(obj)
    if isinstance(obj, list):
        items = " ".join(serialize_obj(item) for item in obj)
        return f"[ {items} ]"
    if isinstance(obj, dict):
        parts: list[str] = ["<<"]
        for k, v in obj.items():
            parts.append(f"/{k} {serialize_obj(v)}")
        parts.append(">>")
        return "\n".join(parts)
    if isinstance(obj, StreamObj):
        d = dict(obj.dict_val)
        d["Length"] = len(obj.data)
        dict_str = serialize_obj(d)
        return f"{dict_str}\nstream\n{obj.data.decode('latin1')}endstream"
    raise ValueError(f"Unsupported object for serialization: {type(obj)}")
