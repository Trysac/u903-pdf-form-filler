"""High-level form operations: read_fields, fill, and flatten."""

from __future__ import annotations

import re
import zlib
from collections.abc import Mapping
from typing import Any

from pdf_form_filler.errors import FormError
from pdf_form_filler.models import Field, FieldKind
from pdf_form_filler.parser import PdfDocument
from pdf_form_filler.tokenizer import IndirectRef, PdfName, PdfString, StreamObj
from pdf_form_filler.writer import serialize_obj, to_pdf_string_literal


def _decode_val(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, PdfName):
        return val.value
    if isinstance(val, PdfString):
        return val.decode_text()
    if isinstance(val, str):
        return val
    return str(val)


def _parse_options(opt_raw: Any) -> tuple[str, ...]:
    if not opt_raw or not isinstance(opt_raw, list):
        return ()
    opts: list[str] = []
    for item in opt_raw:
        if isinstance(item, list) and len(item) >= 2:
            dec = _decode_val(item[1])
            if dec is not None:
                opts.append(dec)
        else:
            dec = _decode_val(item)
            if dec is not None:
                opts.append(dec)
    return tuple(opts)


class FieldNode:
    def __init__(self, obj_num: int, d: dict[str, Any], parent: FieldNode | None = None) -> None:
        self.obj_num = obj_num
        self.d = d
        self.parent = parent
        self.kids: list[FieldNode] = []

    def get_inherited(self, key: str) -> Any:
        if key in self.d:
            return self.d[key]
        if self.parent:
            return self.parent.get_inherited(key)
        return None


def _walk_field_tree(
    doc: PdfDocument,
    node_ref: Any,
    parent_name: str,
    parent_node: FieldNode | None,
    depth: int,
    collected: dict[str, tuple[Field, FieldNode]],
) -> None:
    if depth > 32:
        raise FormError("malformed", "Field hierarchy depth limit exceeded")
    resolved = doc.resolve(node_ref)
    if not isinstance(resolved, dict):
        return

    node_num = node_ref.num if isinstance(node_ref, IndirectRef) else 0
    node = FieldNode(node_num, resolved, parent_node)

    part_t = resolved.get("T")
    part_name = _decode_val(doc.resolve(part_t)) if part_t else ""
    if parent_name and part_name:
        fqn = f"{parent_name}.{part_name}"
    elif part_name:
        fqn = part_name
    else:
        fqn = parent_name

    kids = doc.resolve(resolved.get("Kids"))
    if isinstance(kids, list) and len(kids) > 0:
        has_named_kids = False
        for k in kids:
            rk = doc.resolve(k)
            if isinstance(rk, dict) and "T" in rk:
                has_named_kids = True
                break
        if has_named_kids:
            for k in kids:
                _walk_field_tree(doc, k, fqn, node, depth + 1, collected)
            return

    # Leaf field node
    ft_raw = doc.resolve(node.get_inherited("FT"))
    ft = ft_raw.value if isinstance(ft_raw, PdfName) else (_decode_val(ft_raw) or "")
    ff = int(doc.resolve(node.get_inherited("Ff")) or 0)

    # Push buttons (bit 17 is 0x10000 = 65536) are skipped
    if ft == "Btn" and (ff & 65536):
        return

    kind: FieldKind
    if ft == "Tx":
        kind = "text"
    elif ft == "Btn":
        kind = "radio" if ff & 32768 else "checkbox"
    elif ft == "Ch":
        kind = "choice"
    elif ft == "Sig":
        kind = "signature"
    else:
        kind = "text"

    v_raw = doc.resolve(node.get_inherited("V"))
    val_str = _decode_val(v_raw)

    opts = _parse_options(doc.resolve(node.get_inherited("Opt")))
    max_len_raw = doc.resolve(node.get_inherited("MaxLen"))
    max_len = int(max_len_raw) if max_len_raw is not None else None

    read_only = bool(ff & 1)
    required = bool(ff & 2)

    if fqn:
        field = Field(
            name=fqn,
            kind=kind,
            value=val_str,
            options=opts,
            max_len=max_len,
            read_only=read_only,
            required=required,
        )
        collected[fqn] = (field, node)


def read_fields(pdf: bytes, *, max_input_bytes: int = 52_428_800) -> dict[str, Field]:
    """Extract AcroForm fields from a PDF."""
    if len(pdf) > max_input_bytes:
        raise FormError("input_too_large", f"Input length {len(pdf)} exceeds {max_input_bytes}")

    doc = PdfDocument(pdf)
    root = doc.resolve(doc.trailer.get("Root"))
    if not isinstance(root, dict):
        return {}
    acro_form = doc.resolve(root.get("AcroForm"))
    if not isinstance(acro_form, dict):
        return {}
    fields_arr = doc.resolve(acro_form.get("Fields"))
    if not isinstance(fields_arr, list):
        return {}

    collected: dict[str, tuple[Field, FieldNode]] = {}
    for f_ref in fields_arr:
        _walk_field_tree(doc, f_ref, "", None, 0, collected)

    return {k: v[0] for k, v in collected.items()}


def _find_checkbox_on_state(widget_dict: dict[str, Any], doc: PdfDocument) -> str:
    ap = doc.resolve(widget_dict.get("AP"))
    if isinstance(ap, dict):
        n_dict = doc.resolve(ap.get("N"))
        if isinstance(n_dict, dict):
            for key in n_dict:
                if key != "Off":
                    return str(key)
    return "Yes"


def _parse_da(da_str: str) -> tuple[str, float]:
    # e.g. "/Helv 12 Tf 0 g"
    font_name = "Helv"
    font_size = 12.0
    m = re.search(r"/([a-zA-Z0-9_\-]+)\s+([0-9.]+)\s+Tf", da_str)
    if not m:
        m = re.search(r"/([a-zA-Z0-9_\-]+)\s+([0-9.]*)", da_str)
    if m:
        font_name = m.group(1)
        try:
            size_val = float(m.group(2))
            if size_val > 0:
                font_size = size_val
        except (ValueError, IndexError):
            pass
    return font_name, font_size


def _create_text_appearance_stream(
    rect: list[Any],
    text: str,
    da_str: str,
    dr_dict: dict[str, Any] | None,
) -> StreamObj:
    x0, y0, x1, y1 = [float(c) for c in rect]
    width = x1 - x0
    height = y1 - y0
    font_name, font_size = _parse_da(da_str)
    baseline_y = (height - font_size) / 2.0 + 2.0
    # Stream commands
    stream_content = (
        f"/Tx BMC\nq\n1 1 {width - 2:.2f} {height - 2:.2f} re\nW\nn\n"
        f"BT\n/{font_name} {font_size:.2f} Tf\n2.00 {baseline_y:.2f} Td\n"
        f"{to_pdf_string_literal(text)} Tj\nET\nQ\nEMC"
    ).encode("latin1")

    xobj_dict: dict[str, Any] = {
        "Type": PdfName("XObject"),
        "Subtype": PdfName("Form"),
        "BBox": [0, 0, width, height],
    }
    if dr_dict:
        xobj_dict["Resources"] = dr_dict

    return StreamObj(dict_val=xobj_dict, data=stream_content)


def fill(
    pdf: bytes,
    values: Mapping[str, str | bool],
    *,
    flatten: bool = False,
    max_input_bytes: int = 52_428_800,
) -> bytes:
    """Fill AcroForm fields incrementally, with validation and optional flattening."""
    if len(pdf) > max_input_bytes:
        raise FormError("input_too_large", f"Input length {len(pdf)} exceeds {max_input_bytes}")

    doc = PdfDocument(pdf)
    root_ref = doc.trailer.get("Root")
    root = doc.resolve(root_ref)
    if not isinstance(root, dict):
        raise FormError("no_form", "No root catalog")
    acro_form_ref = root.get("AcroForm")
    acro_form = doc.resolve(acro_form_ref)
    if not isinstance(acro_form, dict):
        raise FormError("no_form", "No AcroForm in document")
    fields_arr = doc.resolve(acro_form.get("Fields"))
    if not isinstance(fields_arr, list):
        raise FormError("no_form", "No fields array")

    collected: dict[str, tuple[Field, FieldNode]] = {}
    for f_ref in fields_arr:
        _walk_field_tree(doc, f_ref, "", None, 0, collected)

    # Validate field names
    for k in values:
        if k not in collected:
            raise FormError("unknown_field", f"Unknown field '{k}'")

    # Determine next free object number
    max_obj_num = max(doc.xref_locations.keys()) if doc.xref_locations else 0
    next_obj_num = max_obj_num + 1

    updated_objects: dict[int, Any] = {}
    new_need_appearances = False

    dr_dict = doc.resolve(acro_form.get("DR"))
    if not isinstance(dr_dict, dict):
        dr_dict = None

    # Keep track of widgets for flattening
    widgets_to_flatten: list[tuple[dict[str, Any], StreamObj, int, Any]] = []

    for name, val in values.items():
        field, node = collected[name]
        if field.read_only or field.kind == "signature":
            raise FormError("read_only", f"Field '{name}' is read-only")

        target_dict = dict(node.d)
        target_num = node.obj_num
        da_str = _decode_val(doc.resolve(node.get_inherited("DA"))) or "/Helv 12 Tf 0 g"

        if field.kind == "text":
            if not isinstance(val, str):
                raise FormError("invalid_option", f"Text field '{name}' expects a string")
            if field.max_len is not None and len(val) > field.max_len:
                raise FormError("value_too_long", f"Field '{name}' exceeds max_len {field.max_len}")
            target_dict["V"] = val

            # Check for non-printable-ASCII
            has_non_ascii = any(ord(c) < 32 or ord(c) > 126 for c in val)
            if has_non_ascii:
                if flatten:
                    raise FormError(
                        "unsupported_character", "Flattening with non-ASCII text is unsupported"
                    )
                new_need_appearances = True
            else:
                # Generate appearance stream
                rect = doc.resolve(target_dict.get("Rect"))
                if not rect and node.kids:
                    # Check kid widget
                    kid_ref = node.kids[0]
                    kid_dict = doc.resolve(kid_ref)
                    if isinstance(kid_dict, dict):
                        rect = doc.resolve(kid_dict.get("Rect"))
                if rect and isinstance(rect, list) and len(rect) == 4:
                    app_stream = _create_text_appearance_stream(rect, val, da_str, dr_dict)
                    app_obj_num = next_obj_num
                    next_obj_num += 1
                    updated_objects[app_obj_num] = app_stream
                    target_dict["AP"] = {"N": IndirectRef(app_obj_num, 0)}
                    if flatten:
                        page_ref = target_dict.get("P")
                        widgets_to_flatten.append((target_dict, app_stream, app_obj_num, page_ref))

        elif field.kind in ("checkbox", "radio"):
            on_state = _find_checkbox_on_state(target_dict, doc)
            if isinstance(val, bool):
                chosen_state = on_state if val else "Off"
            elif isinstance(val, str):
                if val not in (on_state, "Off"):
                    raise FormError(
                        "invalid_option", f"Invalid option '{val}' for checkbox '{name}'"
                    )
                chosen_state = val
            else:
                raise FormError("invalid_option", f"Invalid value for checkbox '{name}'")

            target_dict["V"] = PdfName(chosen_state)
            target_dict["AS"] = PdfName(chosen_state)

        elif field.kind == "choice":
            if not isinstance(val, str):
                raise FormError("invalid_option", f"Choice field '{name}' expects a string")
            ff = int(doc.resolve(node.get_inherited("Ff")) or 0)
            is_combo_editable = bool((ff & 131072) and (ff & 262144))
            if not is_combo_editable and val not in field.options:
                raise FormError("invalid_option", f"Option '{val}' not in options for '{name}'")
            target_dict["V"] = val
            # Generate appearance
            rect = doc.resolve(target_dict.get("Rect"))
            if rect and isinstance(rect, list) and len(rect) == 4:
                app_stream = _create_text_appearance_stream(rect, val, da_str, dr_dict)
                app_obj_num = next_obj_num
                next_obj_num += 1
                updated_objects[app_obj_num] = app_stream
                target_dict["AP"] = {"N": IndirectRef(app_obj_num, 0)}
                if flatten:
                    page_ref = target_dict.get("P")
                    widgets_to_flatten.append((target_dict, app_stream, app_obj_num, page_ref))

        updated_objects[target_num] = target_dict

    if new_need_appearances:
        acro_form_dict = dict(acro_form)
        acro_form_dict["NeedAppearances"] = True
        acro_num = acro_form_ref.num if isinstance(acro_form_ref, IndirectRef) else next_obj_num
        if not isinstance(acro_form_ref, IndirectRef):
            next_obj_num += 1
        updated_objects[acro_num] = acro_form_dict

    if flatten:
        # 1. Clear AcroForm Fields
        acro_form_dict = dict(acro_form)
        acro_form_dict["Fields"] = []
        acro_num = acro_form_ref.num if isinstance(acro_form_ref, IndirectRef) else next_obj_num
        if not isinstance(acro_form_ref, IndirectRef):
            next_obj_num += 1
        updated_objects[acro_num] = acro_form_dict

        # 2. Add flattened appearances to Pages
        # Find page if not explicitly referenced
        pages_dict_ref = root.get("Pages")
        pages_dict = doc.resolve(pages_dict_ref)
        kids_pages = doc.resolve(pages_dict.get("Kids")) if isinstance(pages_dict, dict) else []
        default_page_ref = (
            kids_pages[0] if (isinstance(kids_pages, list) and len(kids_pages) > 0) else None
        )

        # Group widgets by page
        page_widgets: dict[int, list[tuple[dict[str, Any], StreamObj, int]]] = {}
        for w_dict, _app_stream, app_num, p_ref in widgets_to_flatten:
            target_page_ref = p_ref or default_page_ref
            if isinstance(target_page_ref, IndirectRef):
                page_widgets.setdefault(target_page_ref.num, []).append(
                    (w_dict, _app_stream, app_num)
                )

        flat_counter = 1
        for p_num, w_list in page_widgets.items():
            page_obj = dict(doc.get_object(p_num))
            # Filter out widget annotations
            annots = doc.resolve(page_obj.get("Annots"))
            if isinstance(annots, list):
                new_annots = []
                for a in annots:
                    a_res = doc.resolve(a)
                    if isinstance(a_res, dict) and a_res.get("Subtype") == PdfName("Widget"):
                        continue
                    new_annots.append(a)
                page_obj["Annots"] = new_annots

            # Update Resources /XObject
            res_dict = dict(doc.resolve(page_obj.get("Resources")) or {})
            xobj_dict = dict(doc.resolve(res_dict.get("XObject")) or {})

            append_stream_cmds = bytearray()
            for w_dict, _app_stream, app_num in w_list:
                xname = f"Flat{flat_counter}"
                flat_counter += 1
                xobj_dict[xname] = IndirectRef(app_num, 0)
                rect = doc.resolve(w_dict.get("Rect"))
                x, y = float(rect[0]), float(rect[1])
                cmd = f"\nq 1 0 0 1 {x:.2f} {y:.2f} cm /{xname} Do Q\n".encode("latin1")
                append_stream_cmds.extend(cmd)

            res_dict["XObject"] = xobj_dict
            page_obj["Resources"] = res_dict

            # Append to page contents
            new_content_obj_num = next_obj_num
            next_obj_num += 1
            new_content_stream = StreamObj(dict_val={}, data=bytes(append_stream_cmds))
            updated_objects[new_content_obj_num] = new_content_stream

            old_contents = page_obj.get("Contents")
            if old_contents is None:
                page_obj["Contents"] = IndirectRef(new_content_obj_num, 0)
            elif isinstance(old_contents, list):
                page_obj["Contents"] = [*old_contents, IndirectRef(new_content_obj_num, 0)]
            else:
                page_obj["Contents"] = [old_contents, IndirectRef(new_content_obj_num, 0)]

            updated_objects[p_num] = page_obj

    # Build incremental update
    out = bytearray(pdf)
    new_offsets: dict[int, int] = {}
    for obj_num, obj_data in sorted(updated_objects.items()):
        offset = len(out)
        new_offsets[obj_num] = offset
        serialized = serialize_obj(obj_data)
        out.extend(f"{obj_num} 0 obj\n{serialized}\nendobj\n".encode("latin1"))

    xref_offset = len(out)
    prev_xref = doc.last_xref_offset

    if doc.last_xref_type == "table":
        out.extend(b"xref\n")
        # Group consecutive object numbers
        all_objs = sorted(new_offsets.keys())
        ranges: list[list[int]] = []
        for num in all_objs:
            if not ranges or ranges[-1][-1] + 1 != num:
                ranges.append([num])
            else:
                ranges[-1].append(num)
        for r in ranges:
            start = r[0]
            count = len(r)
            out.extend(f"{start} {count}\n".encode("latin1"))
            for num in r:
                out.extend(f"{new_offsets[num]:010d} 00000 n \n".encode("latin1"))

        # Trailer
        trailer_dict = dict(doc.trailer)
        trailer_dict["Prev"] = prev_xref
        trailer_dict["Size"] = max([*list(new_offsets.keys()), doc.trailer.get("Size", 0)]) + 1
        out.extend(b"trailer\n")
        out.extend(serialize_obj(trailer_dict).encode("latin1"))
        out.extend(f"\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin1"))
    else:
        # Write xref stream
        xref_stream_num = next_obj_num
        all_objs = [*sorted(new_offsets.keys()), xref_stream_num]
        new_offsets[xref_stream_num] = xref_offset

        subsections: list[tuple[int, int]] = []
        cur_start = all_objs[0]
        cur_count = 1
        for i in range(1, len(all_objs)):
            if all_objs[i] == all_objs[i - 1] + 1:
                cur_count += 1
            else:
                subsections.append((cur_start, cur_count))
                cur_start = all_objs[i]
                cur_count = 1
        subsections.append((cur_start, cur_count))

        index_arr: list[int] = []
        for st, cnt in subsections:
            index_arr.extend([st, cnt])

        # W: [1, 4, 1]
        record_bytes = bytearray()
        for num in all_objs:
            record_bytes.append(1)
            record_bytes.extend(new_offsets[num].to_bytes(4, "big"))
            record_bytes.append(0)

        compressed_data = zlib.compress(bytes(record_bytes))
        xref_dict: dict[str, Any] = {
            "Type": PdfName("XRef"),
            "Size": max(all_objs) + 1,
            "Index": index_arr,
            "W": [1, 4, 1],
            "Filter": PdfName("FlateDecode"),
            "Prev": prev_xref,
        }
        if "Root" in doc.trailer:
            xref_dict["Root"] = doc.trailer["Root"]
        if "Info" in doc.trailer:
            xref_dict["Info"] = doc.trailer["Info"]

        stream_obj = StreamObj(dict_val=xref_dict, data=compressed_data)
        out.extend(f"{xref_stream_num} 0 obj\n".encode("latin1"))
        out.extend(serialize_obj(stream_obj).encode("latin1"))
        out.extend(f"\nendobj\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin1"))

    return bytes(out)
