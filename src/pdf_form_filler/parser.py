"""PDF parser supporting xref tables, xref streams, and object streams."""

from __future__ import annotations

import zlib
from typing import Any, cast

from pdf_form_filler.errors import FormError
from pdf_form_filler.tokenizer import IndirectRef, StreamObj, Tokenizer, parse_pdf_object


def decode_stream_data(filter_name: Any, raw: bytes, params: dict[str, Any] | None = None) -> bytes:
    if not filter_name:
        return raw
    if isinstance(filter_name, list):
        cur = raw
        for f in filter_name:
            cur = decode_stream_data(f, cur, params)
        return cur
    fname = filter_name.value if hasattr(filter_name, "value") else str(filter_name)
    if fname in ("FlateDecode", "Fl"):  # standard flate
        try:
            decomp = zlib.decompress(raw)
        except Exception as err:
            raise FormError("malformed", f"Flate decompression failed: {err}") from err
        if params:
            predictor = params.get("Predictor", 1)
            if predictor >= 10:  # PNG predictor
                columns = params.get("Columns", 1)
                decomp = _unpredict_png(decomp, columns)
        return decomp
    return raw


def _unpredict_png(data: bytes, columns: int) -> bytes:
    row_len = columns + 1
    out = bytearray()
    prev_row = bytearray(columns)
    for i in range(0, len(data), row_len):
        row = data[i : i + row_len]
        if not row:
            break
        filter_byte = row[0]
        raw_row = bytearray(row[1:])
        cur_row = bytearray(columns)
        for c in range(min(len(raw_row), columns)):
            x = raw_row[c]
            a = cur_row[c - 1] if c > 0 else 0
            b = prev_row[c]
            c_diag = prev_row[c - 1] if c > 0 else 0
            if filter_byte == 0:  # None
                val = x
            elif filter_byte == 1:  # Sub
                val = (x + a) & 0xFF
            elif filter_byte == 2:  # Up
                val = (x + b) & 0xFF
            elif filter_byte == 3:  # Average
                val = (x + ((a + b) >> 1)) & 0xFF
            elif filter_byte == 4:  # Paeth
                p = a + b - c_diag
                pa = abs(p - a)
                pb = abs(p - b)
                pc = abs(p - c_diag)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c_diag)
                val = (x + pr) & 0xFF
            else:
                val = x
            cur_row[c] = val
        out.extend(cur_row)
        prev_row = cur_row
    return bytes(out)


class PdfDocument:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.length = len(data)
        if not data.startswith(b"%PDF-1."):
            raise FormError("not_a_pdf", "Does not start with %PDF-1.")
        self.xref_locations: dict[
            int, tuple[int, int | tuple[int, int]]
        ] = {}  # obj_num -> (type, offset_or_objstream_num)
        # type 1: standard (offset, gen)
        # type 2: in objstream (stream_obj_num, index)
        self.trailer: dict[str, Any] = {}
        self.resolved_objects: dict[int, Any] = {}
        self.last_xref_type: str = "table"  # "table" or "stream"
        self.last_xref_offset: int = 0
        self._parse_xref_and_trailer()

    def _find_startxref(self) -> int:
        idx = self.data.rfind(b"startxref")
        if idx == -1:
            raise FormError("malformed", "startxref not found")

        # Scan for the first digit after startxref
        pos = idx + 9
        while pos < self.length:
            b = self.data[pos : pos + 1]
            if b.isdigit():
                break
            pos += 1
        else:
            raise FormError("malformed", "startxref offset not found")

        # Scan until non-digit
        end = pos
        while end < self.length and self.data[end : end + 1].isdigit():
            end += 1

        return int(self.data[pos:end])

    def _parse_xref_and_trailer(self) -> None:
        offset = self._find_startxref()
        self.last_xref_offset = offset
        is_first = True
        visited_offsets: set[int] = set()

        while offset:
            if offset in visited_offsets:
                break
            visited_offsets.add(offset)
            if offset >= self.length:
                raise FormError("malformed", "xref offset beyond end of file")

            # Detect if it's table or stream
            tok = Tokenizer(self.data, offset)
            tok.skip_whitespace_and_comments()
            kw = tok.parse_token()
            if kw == "xref":
                if is_first:
                    self.last_xref_type = "table"
                    is_first = False
                trailer_dict = self._parse_xref_table(tok)
            elif isinstance(kw, str) and kw.isdigit():
                # likely xref stream: 'N M obj << /Type /XRef ... >> stream'
                if is_first:
                    self.last_xref_type = "stream"
                    is_first = False
                trailer_dict = self._parse_xref_stream(offset)
            else:
                raise FormError("malformed", f"Unknown xref marker at {offset}: {kw}")

            if not self.trailer:
                self.trailer = dict(trailer_dict)
            else:
                # Merge trailer keys if not present
                for k, v in trailer_dict.items():
                    if k not in self.trailer:
                        self.trailer[k] = v

            if "Encrypt" in self.trailer:
                raise FormError("encrypted", "Document is encrypted")

            prev = trailer_dict.get("Prev")
            if prev is not None and isinstance(prev, int):
                offset = prev
            else:
                break

    def _parse_xref_table(self, tok: Tokenizer) -> dict[str, Any]:
        while True:
            tok.skip_whitespace_and_comments()
            t = tok.parse_token()
            if t == "trailer" or t is None:
                break
            try:
                first_obj = int(t)
            except ValueError:
                break
            tok.skip_whitespace_and_comments()
            num_objs = int(tok.parse_token())
            for i in range(num_objs):
                tok.skip_whitespace_and_comments()
                entry_offset = int(tok.parse_token())
                tok.skip_whitespace_and_comments()
                int(tok.parse_token())
                tok.skip_whitespace_and_comments()
                entry_type = tok.parse_token()
                obj_num = first_obj + i
                if entry_type == "n":
                    if obj_num not in self.xref_locations:
                        self.xref_locations[obj_num] = (1, entry_offset)
                elif entry_type == "f":
                    pass

        tok.skip_whitespace_and_comments()
        trailer_obj = parse_pdf_object(tok)
        if not isinstance(trailer_obj, dict):
            raise FormError("malformed", "Trailer must be a dictionary")
        return trailer_obj

    def _parse_xref_stream(self, offset: int) -> dict[str, Any]:
        stream_obj = self._read_direct_object_at(offset)
        if not isinstance(stream_obj, StreamObj):
            raise FormError("malformed", "Expected XRef stream object")
        d = stream_obj.dict_val
        w = d.get("W", [1, 2, 1])
        w0, w1, w2 = int(w[0]), int(w[1]), int(w[2])
        record_size = w0 + w1 + w2
        index = d.get("Index", [0, d.get("Size", 0)])
        raw_data = stream_obj.data

        subsections: list[tuple[int, int]] = []
        for i in range(0, len(index), 2):
            subsections.append((int(index[i]), int(index[i + 1])))

        cursor = 0
        for first_obj, count in subsections:
            for i in range(count):
                if cursor + record_size > len(raw_data):
                    break
                record = raw_data[cursor : cursor + record_size]
                cursor += record_size
                f0 = int.from_bytes(record[:w0], "big") if w0 > 0 else 1
                f1 = int.from_bytes(record[w0 : w0 + w1], "big") if w1 > 0 else 0
                f2 = int.from_bytes(record[w0 + w1 : record_size], "big") if w2 > 0 else 0
                obj_num = first_obj + i
                if f0 == 1:
                    if obj_num not in self.xref_locations:
                        self.xref_locations[obj_num] = (1, f1)
                elif f0 == 2 and obj_num not in self.xref_locations:
                    self.xref_locations[obj_num] = (2, (f1, f2))

        return d

    def _read_direct_object_at(self, offset: int) -> Any:
        tok = Tokenizer(self.data, offset)
        tok.skip_whitespace_and_comments()
        _ = tok.parse_token()  # obj num
        tok.skip_whitespace_and_comments()
        _ = tok.parse_token()  # gen
        tok.skip_whitespace_and_comments()
        obj_kw = tok.parse_token()
        if obj_kw != "obj":
            raise FormError("malformed", f"Expected 'obj' at {offset}, got {obj_kw}")
        obj_val = parse_pdf_object(tok)
        tok.skip_whitespace_and_comments()
        saved = tok.pos
        next_t = tok.parse_token()
        if next_t == "stream":
            if tok.data[tok.pos : tok.pos + 2] == b"\r\n":
                stream_start = tok.pos + 2
            elif tok.data[tok.pos : tok.pos + 1] in (b"\r", b"\n"):
                stream_start = tok.pos + 1
            else:
                stream_start = tok.pos
            # find endstream
            stream_dict = obj_val if isinstance(obj_val, dict) else {}
            length = self.resolve(stream_dict.get("Length", 0))
            if isinstance(length, int) and length > 0 and stream_start + length <= len(self.data):
                stream_end = stream_start + length
            else:
                stream_end = self.data.find(b"endstream", stream_start)
                if stream_end == -1:
                    raise FormError("malformed", "Missing endstream")
            raw_stream = self.data[stream_start:stream_end]
            # Decode
            flt = self.resolve(stream_dict.get("Filter"))
            parms = self.resolve(stream_dict.get("DecodeParms"))
            decoded = decode_stream_data(
                flt, raw_stream, parms if isinstance(parms, dict) else None
            )
            return StreamObj(dict_val=stream_dict, data=decoded)
        tok.pos = saved
        return obj_val

    def get_object(self, num: int) -> Any:
        if len(self.resolved_objects) > 1_000_000:
            raise FormError("malformed", "Object count exceeded 1,000,000")
        if num in self.resolved_objects:
            return self.resolved_objects[num]
        if num not in self.xref_locations:
            return None
        loc_type, loc_val = self.xref_locations[num]
        if loc_type == 1:
            obj = self._read_direct_object_at(cast(int, loc_val))
            self.resolved_objects[num] = obj
            return obj
        if loc_type == 2:
            stream_num, index = cast(tuple[int, int], loc_val)
            obj_stream = self.get_object(stream_num)
            if not isinstance(obj_stream, StreamObj):
                raise FormError("malformed", f"Target stream {stream_num} is not a stream object")
            obj = self._read_from_obj_stream(obj_stream, index)
            self.resolved_objects[num] = obj
            return obj
        return None

    def _read_from_obj_stream(self, stream_obj: StreamObj, index: int) -> Any:
        d = stream_obj.dict_val
        first = int(d.get("First", 0))
        raw = stream_obj.data
        tok = Tokenizer(raw)
        header_pairs: list[tuple[int, int]] = []
        n_count = int(d.get("N", 0))
        for _ in range(n_count):
            tok.skip_whitespace_and_comments()
            onum = int(tok.parse_token())
            tok.skip_whitespace_and_comments()
            ooff = int(tok.parse_token())
            header_pairs.append((onum, ooff))
        if index >= len(header_pairs):
            raise FormError("malformed", f"Obj stream index {index} out of range")
        target_offset = first + header_pairs[index][1]
        sub_tok = Tokenizer(raw, target_offset)
        return parse_pdf_object(sub_tok)

    def resolve(self, obj: Any) -> Any:
        visited: set[int] = set()
        while isinstance(obj, IndirectRef):
            if obj.num in visited:
                raise FormError("malformed", "Indirect reference cycle detected")
            visited.add(obj.num)
            obj = self.get_object(obj.num)
        return obj
