# trysac-pdf-form-filler

Fill PDF AcroForm fields with validation against field definitions, write an incremental update and optionally flatten the result.

## Installation

```bash
pip install trysac-pdf-form-filler
```

## Usage

```python
from pdf_form_filler import fill, read_fields

with open("form.pdf", "rb") as f:
    pdf_data = f.read()

fields = read_fields(pdf_data)
print([f.name for f in fields.values()])

filled_pdf = fill(pdf_data, {"name": "Ada", "agree": True})
with open("filled.pdf", "wb") as f:
    f.write(filled_pdf)
```

## CLI

Inspect form fields:
```bash
python -m pdf_form_filler fields in.pdf
```

Fill form fields:
```bash
python -m pdf_form_filler fill in.pdf --set name=Ada --set agree=true --out out.pdf
```

Flatten form widgets:
```bash
python -m pdf_form_filler fill in.pdf --set name=Ada --flatten --out flattened.pdf
```

## Features & Limitations

- **Incremental updates**: Original byte contents are preserved verbatim.
- **AcroForm validation**: Validates values against defined choices, character limits (`MaxLen`), and read-only flags with typed errors.
- **Conformance**: Compliant with ISO 32000-1:2008.
- **Out of Scope**: Encryption, digital signatures, XFA forms, rich text fields, comb fields, font embedding, and rotated widgets.
