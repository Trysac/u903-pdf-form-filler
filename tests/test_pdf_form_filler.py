"""Unit and acceptance tests for pdf_form_filler."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pypdf
import pytest

from pdf_form_filler import FormError, fill, read_fields
from pdf_form_filler.__main__ import main
from tests.pdfbuild import build_encrypted_pdf, build_test_pdf


def test_acceptance_read_fields() -> None:
    src = build_test_pdf()
    fields = read_fields(src)
    names = sorted(fields.keys())
    # acceptance: read_fields(src) returns the names ['addr.city', 'agree', 'color', 'name']
    # with kinds 'text', 'checkbox', 'choice' and 'text', 'name' having max_len == 10 and 'color' options ('red', 'green')
    assert names == ["addr.city", "agree", "color", "name"]
    assert fields["addr.city"].kind == "text"
    assert fields["agree"].kind == "checkbox"
    assert fields["color"].kind == "choice"
    assert fields["name"].kind == "text"
    assert fields["name"].max_len == 10
    assert fields["color"].options == ("red", "green")


def test_acceptance_fill_incremental() -> None:
    src = build_test_pdf()
    out = fill(src, {"name": "Ada", "agree": True, "color": "green"})
    # acceptance: keeps out[:len(src)] == src (incremental update)
    assert out[: len(src)] == src
    read_back = read_fields(out)
    assert read_back["name"].value == "Ada"
    assert read_back["agree"].value == "Yes"
    assert read_back["color"].value == "green"

    # Same holds for a fixture that uses a cross-reference stream
    src_stream = build_test_pdf(use_xref_stream=True)
    out_stream = fill(src_stream, {"name": "Ada", "agree": True, "color": "green"})
    assert out_stream[: len(src_stream)] == src_stream
    read_stream = read_fields(out_stream)
    assert read_stream["name"].value == "Ada"
    assert read_stream["agree"].value == "Yes"
    assert read_stream["color"].value == "green"


def test_acceptance_oracle_pypdf() -> None:
    src = build_test_pdf()
    out = fill(src, {"name": "Ada", "agree": True, "color": "green"})
    reader = pypdf.PdfReader(io.BytesIO(out))
    pdf_fields = reader.get_fields()
    assert pdf_fields is not None
    # Oracle: pypdf.PdfReader(io.BytesIO(out)).get_fields()['name']['/V'] == 'Ada' and the widget of 'agree' has '/AS' equal to '/Yes'
    assert pdf_fields["name"]["/V"] == "Ada"

    # Verify the widget of 'agree' has '/AS' equal to '/Yes'
    found = False
    for page in reader.pages:
        annots = page.get("/Annots")
        if annots:
            for annot in annots:
                obj = annot.get_object()
                if obj.get("/T") == "agree":
                    assert obj.get("/AS") == "/Yes"
                    found = True
    assert found


def test_acceptance_validation_errors() -> None:
    src = build_test_pdf()
    with pytest.raises(FormError) as exc_info:
        fill(src, {"name": "Ada Lovelace!"})
    assert exc_info.value.code == "value_too_long"

    with pytest.raises(FormError) as exc_info:
        fill(src, {"color": "blue"})
    assert exc_info.value.code == "invalid_option"

    with pytest.raises(FormError) as exc_info:
        fill(src, {"nope": "x"})
    assert exc_info.value.code == "unknown_field"

    src_ro = build_test_pdf(read_only_field=True)
    with pytest.raises(FormError) as exc_info:
        fill(src_ro, {"name": "Ada"})
    assert exc_info.value.code == "read_only"


def test_acceptance_strings_roundtrip() -> None:
    src = build_test_pdf()
    # fill(src, {'name': 'a(b)' + chr(92) + 'c'}) reads back the same 6 characters
    esc_val = "a(b)" + chr(92) + "c"
    out_esc = fill(src, {"name": esc_val})
    assert read_fields(out_esc)["name"].value == esc_val

    # {'name': 'Zoë'} is written as the UTF-16BE hex string <FEFF005A006F00EB> and reads back 'Zoë'
    out_utf = fill(src, {"name": "Zoë"})
    assert b"<FEFF005A006F00EB>" in out_utf
    assert read_fields(out_utf)["name"].value == "Zoë"


def test_acceptance_flatten() -> None:
    src = build_test_pdf()
    # fill(src, {'name': 'Ada'}, flatten=True) returns a PDF where read_fields(out) == {},
    # the page has no Widget annotations and the page content draws a form XObject whose stream contains '(Ada) Tj'
    out = fill(src, {"name": "Ada"}, flatten=True)
    assert read_fields(out) == {}
    reader = pypdf.PdfReader(io.BytesIO(out))
    page = reader.pages[0]
    annots = page.get("/Annots")
    widget_annots = []
    if annots:
        for a in annots:
            if a.get_object().get("/Subtype") == "/Widget":
                widget_annots.append(a)
    assert len(widget_annots) == 0
    assert b"(Ada) Tj" in out


def test_acceptance_errors_and_cli(tmp_path: Path) -> None:
    # b'hello' raises code 'not_a_pdf'
    with pytest.raises(FormError) as exc:
        fill(b"hello", {"name": "Ada"})
    assert exc.value.code == "not_a_pdf"

    # an encrypted PDF raises 'encrypted'
    enc_pdf = build_encrypted_pdf()
    with pytest.raises(FormError) as exc:
        fill(enc_pdf, {"name": "Ada"})
    assert exc.value.code == "encrypted"

    # an input of 52_428_801 bytes raises 'input_too_large' while max_input_bytes is 52_428_800
    big_pdf = b"%PDF-1.7\n" + b"0" * 52_428_792
    with pytest.raises(FormError) as exc:
        fill(big_pdf, {"name": "Ada"}, max_input_bytes=52_428_800)
    assert exc.value.code == "input_too_large"

    # CLI checks
    p = tmp_path / "cli"
    p.mkdir()
    in_file = p / "in.pdf"
    out_file = p / "out.pdf"
    in_file.write_bytes(build_test_pdf())

    # main(['fill', 'in.pdf', '--set', 'name=Ada', '--out', 'out.pdf']) returns 0
    assert main(["fill", str(in_file), "--set", "name=Ada", "--out", str(out_file)]) == 0
    assert out_file.exists()

    # and a validation error returns 1
    assert main(["fill", str(in_file), "--set", "name=Ada Lovelace!", "--out", str(out_file)]) == 1


def test_cli_fields_and_edge_cases(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "cli_edge"
    p.mkdir()
    in_file = p / "in.pdf"
    in_file.write_bytes(build_test_pdf())

    rc = main(["fields", str(in_file)])
    assert rc == 0
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert "name" in data

    # CLI invalid set format
    rc_bad_set = main(
        ["fill", str(in_file), "--set", "invalid_no_equal", "--out", str(p / "out2.pdf")]
    )
    assert rc_bad_set == 2

    # CLI missing input
    rc_missing = main(["fields", str(p / "nonexistent.pdf")])
    assert rc_missing == 2

    # CLI help / no args
    assert main([]) == 2


def test_cli_errors(tmp_path: Path) -> None:
    # Error in reading file
    rc = main(["fields", "no_file.pdf"])
    assert rc == 2
    # Error in writing file
    in_file = tmp_path / "in.pdf"
    in_file.write_bytes(build_test_pdf())
    # Try to write to a directory
    out_file = tmp_path / "dir"
    out_file.mkdir()
    rc = main(["fill", str(in_file), "--set", "name=Ada", "--out", str(out_file)])
    assert rc == 2

    # Invalid command
    rc = main(["invalid"])
    assert rc == 2


def test_parser_coverage() -> None:
    from pdf_form_filler.errors import FormError
    from pdf_form_filler.parser import PdfDocument, _unpredict_png, decode_stream_data

    # Invalid PDF start
    with pytest.raises(FormError) as exc:
        PdfDocument(b"not_pdf")
    assert exc.value.code == "not_a_pdf"

    # Missing startxref
    with pytest.raises(FormError) as exc:
        PdfDocument(b"%PDF-1.7\n")
    assert exc.value.code == "malformed"

    # Coverage for decode_stream_data
    assert decode_stream_data(None, b"data") == b"data"
    assert decode_stream_data(["None"], b"data") == b"data"

    # Decompression failure
    with pytest.raises(FormError) as exc:
        decode_stream_data("FlateDecode", b"invalid_compressed_data")
    assert exc.value.code == "malformed"

    # Unpredict png filters
    # filter 0 (None): val = x
    assert _unpredict_png(b"\x00" + b"\x01\x02", 2) == b"\x01\x02"
    # filter 1 (Sub): val = (x + a) & 0xFF
    assert _unpredict_png(b"\x01" + b"\x01\x02", 2) == b"\x01\x03"
    # filter 2 (Up): val = (x + b) & 0xFF
    # two rows: row 0 all 0s for prev_row, row 1 with filter 2
    row0 = b"\x00\x05\x05"
    row1 = b"\x02\x02\x03"
    res = _unpredict_png(row0 + row1, 2)
    assert res == b"\x05\x05\x07\x08"
    # filter 3 (Average)
    row_avg = b"\x03\x02\x02"
    res_avg = _unpredict_png(row0 + row_avg, 2)
    assert len(res_avg) == 4
    # filter 4 (Paeth)
    row_paeth = b"\x04\x01\x01"
    res_paeth = _unpredict_png(row0 + row_paeth, 2)
    assert len(res_paeth) == 4


def test_tokenizer_coverage() -> None:
    from pdf_form_filler.tokenizer import Tokenizer

    tok = Tokenizer(b"() <123> /Name")
    assert tok.parse_token().raw == b""
    assert tok.parse_token().raw == b"\x12\x30"
    assert tok.parse_token().value == "Name"

    # Hex string with whitespace
    tok = Tokenizer(b"<1 2 3 >")
    assert tok.parse_token().raw == b"\x12\x30"

    # Literal string escapes
    tok = Tokenizer(b"(a\\n\\r\\t\\b\\f\\(b)")
    assert tok.parse_token().raw == b"a\n\r\t\x08\x0c(b"

    # Literal string octal
    tok = Tokenizer(b"((\\101))")
    assert tok.parse_token().raw == b"(A)"


def test_flatten_unsupported_character() -> None:
    src = build_test_pdf()
    with pytest.raises(FormError) as exc:
        fill(src, {"name": "Zoë"}, flatten=True)
    assert exc.value.code == "unsupported_character"


def test_checkbox_options_and_boolean() -> None:
    src = build_test_pdf()
    # checkbox set to False
    out_false = fill(src, {"agree": False})
    assert read_fields(out_false)["agree"].value == "Off"

    # checkbox set to string "Off"
    out_off = fill(src, {"agree": "Off"})
    assert read_fields(out_off)["agree"].value == "Off"

    # checkbox invalid string
    with pytest.raises(FormError) as exc:
        fill(src, {"agree": "Maybe"})
    assert exc.value.code == "invalid_option"

    # text field invalid type
    with pytest.raises(FormError) as exc:
        fill(src, {"name": 123})  # type: ignore[dict-item]
    assert exc.value.code == "invalid_option"

    # choice field invalid type
    with pytest.raises(FormError) as exc:
        fill(src, {"color": True})  # type: ignore[dict-item]
    assert exc.value.code == "invalid_option"


def test_tokenizer_more_coverage() -> None:
    from pdf_form_filler.tokenizer import PdfString, Tokenizer

    # Name with #20
    tok = Tokenizer(b"/A#20B")
    name = tok.parse_token()
    assert name.value == "A B"

    # String with utf16le and utf8 BOM
    s_le = PdfString(b"\xff\xfeA\x00")
    assert s_le.decode_text() == "A"
    s_utf8 = PdfString(b"\xef\xbb\xbfHello")
    assert s_utf8.decode_text() == "Hello"

    # Delimiters
    tok_d = Tokenizer(b">> [ ]")
    assert tok_d.parse_token() == ">>"
    assert tok_d.parse_token() == "["
    assert tok_d.parse_token() == "]"


def test_writer_coverage() -> None:
    from pdf_form_filler.tokenizer import IndirectRef, PdfName, StreamObj
    from pdf_form_filler.writer import serialize_obj

    assert serialize_obj(None) == "null"
    assert serialize_obj(True) == "true"
    assert serialize_obj(False) == "false"
    assert serialize_obj(42) == "42"
    assert serialize_obj(3.14) == "3.14"
    assert serialize_obj(5.0) == "5"
    assert serialize_obj(IndirectRef(1, 0)) == "1 0 R"
    assert serialize_obj(PdfName("Test")) == "/Test"
    assert serialize_obj([1, 2]) == "[ 1 2 ]"
    assert "<<\n/Key 1\n>>" in serialize_obj({"Key": 1})
    st = StreamObj(dict_val={"Type": PdfName("XObject")}, data=b"hello")
    serialized_st = serialize_obj(st)
    assert "stream\nhelloendstream" in serialized_st
