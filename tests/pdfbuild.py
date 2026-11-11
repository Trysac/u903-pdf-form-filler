"""Fixture generator building minimal valid PDF AcroForms for tests."""

from __future__ import annotations

import zlib


def build_test_pdf(*, use_xref_stream: bool = False, read_only_field: bool = False) -> bytes:
    """Construct a valid PDF 1.7 document containing form fields.

    Fields:
    - name: text, max_len=10
    - addr.city: text
    - agree: checkbox
    - color: choice, options ('red', 'green')
    """
    font_num = 1
    xobj_ap_num = 2
    city_num = 3
    addr_num = 4
    agree_num = 5
    color_num = 6
    name_num = 7
    acro_num = 8
    page_num = 9
    pages_num = 10
    root_num = 11

    ff_name = 1 if read_only_field else 0

    # Construct objects
    objs: dict[int, bytes] = {}
    objs[font_num] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    # AP for checkbox 'agree'
    objs[xobj_ap_num] = (
        b"<< /Type /XObject /Subtype /Form /BBox [0 0 20 20] /Resources << >> /Length 0 >>\n"
        b"stream\nendstream"
    )
    objs[city_num] = (
        f"<< /FT /Tx /T (city) /V (Portland) /Rect [100 650 200 670] /Subtype /Widget "
        f"/P {page_num} 0 R >>".encode("latin1")
    )
    objs[addr_num] = f"<< /T (addr) /Kids [ {city_num} 0 R ] >>".encode("latin1")
    objs[agree_num] = (
        f"<< /FT /Btn /T (agree) /V /Off /AS /Off /Rect [100 600 120 620] /Subtype /Widget /P {page_num} 0 R "
        f"/AP << /N << /Yes {xobj_ap_num} 0 R /Off {xobj_ap_num} 0 R >> >> >>".encode("latin1")
    )
    objs[color_num] = (
        f"<< /FT /Ch /T (color) /V (red) /Opt [ (red) (green) ] /Rect [100 550 200 570] /Subtype /Widget "
        f"/P {page_num} 0 R >>".encode("latin1")
    )
    objs[name_num] = (
        f"<< /FT /Tx /T (name) /MaxLen 10 /Ff {ff_name} /DA (/Helv 12 Tf 0 g) /Rect [100 700 200 720] "
        f"/Subtype /Widget /P {page_num} 0 R >>".encode("latin1")
    )
    objs[acro_num] = (
        f"<< /Fields [ {name_num} 0 R {addr_num} 0 R {agree_num} 0 R {color_num} 0 R ] "
        f"/DR << /Font << /Helv {font_num} 0 R >> >> >>".encode("latin1")
    )
    objs[page_num] = (
        f"<< /Type /Page /Parent {pages_num} 0 R /MediaBox [0 0 612 792] "
        f"/Annots [ {name_num} 0 R {city_num} 0 R {agree_num} 0 R {color_num} 0 R ] >>".encode(
            "latin1"
        )
    )
    objs[pages_num] = f"<< /Type /Pages /Kids [ {page_num} 0 R ] /Count 1 >>".encode("latin1")
    objs[root_num] = f"<< /Type /Catalog /Pages {pages_num} 0 R /AcroForm {acro_num} 0 R >>".encode(
        "latin1"
    )

    pdf = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}

    for num in range(1, root_num + 1):
        offsets[num] = len(pdf)
        pdf.extend(f"{num} 0 obj\n".encode("latin1"))
        pdf.extend(objs[num])
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    total_objs = root_num + 1

    if not use_xref_stream:
        pdf.extend(f"xref\n0 {total_objs}\n0000000000 65535 f \n".encode("latin1"))
        for num in range(1, total_objs):
            pdf.extend(f"{offsets[num]:010d} 00000 n \n".encode("latin1"))
        pdf.extend(b"trailer\n")
        pdf.extend(f"<< /Size {total_objs} /Root {root_num} 0 R >>\n".encode("latin1"))
        pdf.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode("latin1"))
    else:
        xref_stream_num = total_objs
        offsets[xref_stream_num] = xref_offset
        count = total_objs + 1
        record_bytes = bytearray()
        # obj 0
        record_bytes.extend(b"\x00\x00\x00\x00\x00\x00")
        for num in range(1, count):
            record_bytes.append(1)
            record_bytes.extend(offsets[num].to_bytes(4, "big"))
            record_bytes.append(0)
        compressed = zlib.compress(bytes(record_bytes))
        pdf.extend(
            f"{xref_stream_num} 0 obj\n<< /Type /XRef /Size {count} /W [1 4 1] /Filter /FlateDecode ".encode(
                "latin1"
            )
        )
        pdf.extend(f"/Root {root_num} 0 R /Length {len(compressed)} >>\nstream\n".encode("latin1"))
        pdf.extend(compressed)
        pdf.extend(f"\nendstream\nendobj\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin1"))

    return bytes(pdf)


def build_encrypted_pdf() -> bytes:
    """Construct a minimal PDF with an /Encrypt entry in the trailer."""
    base = build_test_pdf()
    return base.replace(b"/Root", b"/Encrypt << /V 1 >> /Root")
