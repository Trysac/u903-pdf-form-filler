"""Hand-written PDF object tokenizer conforming to ISO 32000-1:2008 section 7.3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pdf_form_filler.errors import FormError


@dataclass(frozen=True)
class IndirectRef:
    num: int
    gen: int


@dataclass(frozen=True)
class PdfName:
    value: str


@dataclass(frozen=True)
class PdfString:
    raw: bytes
    is_hex: bool = False

    def decode_text(self) -> str:
        data = self.raw
        if data.startswith(b"\xfe\xff"):
            return data[2:].decode("utf-16-be", errors="replace")
        if data.startswith(b"\xff\xfe"):
            return data[2:].decode("utf-16-le", errors="replace")
        if data.startswith(b"\xef\xbb\xbf"):
            return data[3:].decode("utf-8", errors="replace")
        # Fallback PDFDocEncoding ASCII range
        return data.decode("latin1", errors="replace")


@dataclass
class StreamObj:
    dict_val: dict[str, Any]
    data: bytes


_WHITESPACE = {b" ", b"\t", b"\r", b"\n", b"\f", b"\x00"}
_DELIMITERS = {b"(", b")", b"<", b">", b"[", b"]", b"{", b"}", b"/", b"%"}


class Tokenizer:
    def __init__(self, data: bytes, start: int = 0) -> None:
        self.data = data
        self.pos = start
        self.length = len(data)

    def skip_whitespace_and_comments(self) -> None:
        while self.pos < self.length:
            b = self.data[self.pos : self.pos + 1]
            if b in _WHITESPACE:
                self.pos += 1
            elif b == b"%":
                while self.pos < self.length and self.data[self.pos : self.pos + 1] not in (
                    b"\r",
                    b"\n",
                ):
                    self.pos += 1
            else:
                break

    def parse_token(self) -> Any:
        self.skip_whitespace_and_comments()
        if self.pos >= self.length:
            return None

        ch = self.data[self.pos : self.pos + 1]
        if ch == b"/":
            self.pos += 1
            start = self.pos
            while self.pos < self.length:
                b = self.data[self.pos : self.pos + 1]
                if b in _WHITESPACE or b in _DELIMITERS:
                    break
                self.pos += 1
            raw_name = self.data[start : self.pos]
            # Decode #xx escapes in names
            parts: list[bytes] = []
            i = 0
            while i < len(raw_name):
                if raw_name[i : i + 1] == b"#" and i + 2 < len(raw_name):
                    try:
                        parts.append(bytes([int(raw_name[i + 1 : i + 3], 16)]))
                        i += 3
                        continue
                    except ValueError:
                        pass
                parts.append(raw_name[i : i + 1])
                i += 1
            return PdfName(b"".join(parts).decode("latin1", errors="replace"))

        if ch == b"(":
            return self._parse_literal_string()
        if ch == b"<":
            if self.pos + 1 < self.length and self.data[self.pos + 1 : self.pos + 2] == b"<":
                self.pos += 2
                return "<<"
            return self._parse_hex_string()
        if ch == b">":
            if self.pos + 1 < self.length and self.data[self.pos + 1 : self.pos + 2] == b">":
                self.pos += 2
                return ">>"
            self.pos += 1
            return ">"
        if ch == b"[":
            self.pos += 1
            return "["
        if ch == b"]":
            self.pos += 1
            return "]"

        start = self.pos
        while self.pos < self.length:
            b = self.data[self.pos : self.pos + 1]
            if b in _WHITESPACE or b in _DELIMITERS:
                break
            self.pos += 1
        token = self.data[start : self.pos].decode("latin1", errors="replace")
        return token

    def _parse_literal_string(self) -> PdfString:
        self.pos += 1  # skip '('
        depth = 1
        buf = bytearray()
        while self.pos < self.length and depth > 0:
            b = self.data[self.pos : self.pos + 1]
            if b == b"\\":
                self.pos += 1
                if self.pos >= self.length:
                    break
                esc = self.data[self.pos : self.pos + 1]
                if esc == b"n":
                    buf.append(10)
                elif esc == b"r":
                    buf.append(13)
                elif esc == b"t":
                    buf.append(9)
                elif esc == b"b":
                    buf.append(8)
                elif esc == b"f":
                    buf.append(12)
                elif esc in (b"(", b")", b"\\"):
                    buf.append(esc[0])
                elif esc in (b"\r", b"\n"):
                    if (
                        esc == b"\r"
                        and self.pos + 1 < self.length
                        and self.data[self.pos + 1 : self.pos + 2] == b"\n"
                    ):
                        self.pos += 1
                elif esc in b"01234567":
                    oct_digits = [esc]
                    for _ in range(2):
                        if (
                            self.pos + 1 < self.length
                            and self.data[self.pos + 1 : self.pos + 2] in b"01234567"
                        ):
                            self.pos += 1
                            oct_digits.append(self.data[self.pos : self.pos + 1])
                        else:
                            break
                    buf.append(int(b"".join(oct_digits), 8))
                else:
                    buf.append(esc[0])
                self.pos += 1
            elif b == b"(":
                depth += 1
                buf.append(b[0])
                self.pos += 1
            elif b == b")":
                depth -= 1
                if depth > 0:
                    buf.append(b[0])
                self.pos += 1
            else:
                buf.append(b[0])
                self.pos += 1
        return PdfString(bytes(buf), is_hex=False)

    def _parse_hex_string(self) -> PdfString:
        self.pos += 1  # skip '<'
        start = self.pos
        while self.pos < self.length and self.data[self.pos : self.pos + 1] != b">":
            self.pos += 1
        hex_bytes = self.data[start : self.pos]
        if self.pos < self.length:
            self.pos += 1  # skip '>'
        cleaned = [chr(c) for c in hex_bytes if chr(c) not in " \t\r\n\f\x00"]
        if len(cleaned) % 2 != 0:
            cleaned.append("0")
        try:
            raw = bytes.fromhex("".join(cleaned))
        except ValueError:
            raw = b""
        return PdfString(raw, is_hex=True)


def parse_pdf_object(tok: Tokenizer, depth: int = 0) -> Any:
    if depth > 64:
        raise FormError("malformed", "Nesting depth limit exceeded")
    t = tok.parse_token()
    if t is None:
        return None

    if isinstance(t, (PdfName, PdfString)):
        return t

    if t == "<<":
        d: dict[str, Any] = {}
        while True:
            tok.skip_whitespace_and_comments()
            if tok.pos >= tok.length:
                break
            if tok.data[tok.pos : tok.pos + 2] == b">>":
                tok.pos += 2
                break
            key = parse_pdf_object(tok, depth + 1)
            if key is None:
                break
            if not isinstance(key, PdfName):
                if key == ">>" or key == ">":
                    break
                raise FormError("malformed", f"Expected name key in dictionary, got {key}")
            val = parse_pdf_object(tok, depth + 1)
            d[key.value] = val
        return d

    if t == "[":
        arr: list[Any] = []
        while True:
            tok.skip_whitespace_and_comments()
            if tok.pos >= tok.length:
                break
            if tok.data[tok.pos : tok.pos + 1] == b"]":
                tok.pos += 1
                break
            val = parse_pdf_object(tok, depth + 1)
            if val == "]":
                break
            arr.append(val)
        return arr

    if t == "true":
        return True
    if t == "false":
        return False
    if t == "null":
        return None

    if isinstance(t, str):
        try:
            int_val = int(t)
            # Check if this could be an indirect reference: N M R
            saved_pos = tok.pos
            tok.skip_whitespace_and_comments()
            next_tok = tok.parse_token()
            if isinstance(next_tok, str) and next_tok.isdigit():
                tok.skip_whitespace_and_comments()
                r_tok = tok.parse_token()
                if r_tok == "R":
                    return IndirectRef(int_val, int(next_tok))
            tok.pos = saved_pos
            return int_val
        except ValueError:
            pass
        try:
            return float(t)
        except ValueError:
            return t

    return t
