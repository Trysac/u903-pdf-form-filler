"""CLI interface for pdf_form_filler."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from pdf_form_filler.errors import FormError
from pdf_form_filler.ops import fill, read_fields


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdf_form_filler", description="Fill PDF AcroForm fields")
    subparsers = parser.add_subparsers(dest="command")

    fields_p = subparsers.add_parser("fields", help="List fields in a PDF")
    fields_p.add_argument("pdf", help="Input PDF path")

    fill_p = subparsers.add_parser("fill", help="Fill fields in a PDF")
    fill_p.add_argument("pdf", help="Input PDF path")
    fill_p.add_argument(
        "--set", action="append", dest="sets", default=[], help="Field values as key=value"
    )
    fill_p.add_argument(
        "--flatten", action="store_true", help="Flatten form fields into page content"
    )
    fill_p.add_argument("--out", required=True, help="Output PDF path")

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code != 0 else 0

    if not args.command:
        parser.print_help()
        return 2

    try:
        if args.command == "fields":
            try:
                with open(args.pdf, "rb") as f:
                    data = f.read()
            except OSError as err:
                sys.stderr.write(f"Error reading file: {err}\n")
                return 2
            fields = read_fields(data)
            out_dict = {
                k: {
                    "name": v.name,
                    "kind": v.kind,
                    "value": v.value,
                    "options": list(v.options),
                    "max_len": v.max_len,
                    "read_only": v.read_only,
                    "required": v.required,
                }
                for k, v in sorted(fields.items())
            }
            sys.stdout.write(json.dumps(out_dict, indent=2) + "\n")
            return 0

        if args.command == "fill":
            try:
                with open(args.pdf, "rb") as f:
                    data = f.read()
            except OSError as err:
                sys.stderr.write(f"Error reading file: {err}\n")
                return 2

            values: dict[str, str | bool] = {}
            for item in args.sets:
                if "=" not in item:
                    sys.stderr.write(f"Invalid set format: '{item}', expected key=value\n")
                    return 2
                k, v = item.split("=", 1)
                if v.lower() == "true":
                    values[k] = True
                elif v.lower() == "false":
                    values[k] = False
                else:
                    values[k] = v

            res = fill(data, values, flatten=args.flatten)
            try:
                with open(args.out, "wb") as f:
                    f.write(res)
            except OSError as err:
                sys.stderr.write(f"Error writing output: {err}\n")
                return 2
            return 0
    except FormError as err:
        sys.stderr.write(f"FormError: {err}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
