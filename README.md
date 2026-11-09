# pdf-form-filler

[![PyPI version](https://img.shields.io/pypi/v/trysac-pdf-form-filler)](https://pypi.org/project/trysac-pdf-form-filler/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-pdf-form-filler)](LICENSE)
[![CI](https://github.com/Trysac/u903-pdf-form-filler/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u903-pdf-form-filler/actions/workflows/ci.yml)

Fill PDF AcroForm fields with validation against each field definition, write an incremental update and optionally flatten the result

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-pdf-form-filler
# or
uv add trysac-pdf-form-filler
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import pdf_form_filler

# normalize() trims surrounding whitespace and lower-cases the text.
print(pdf_form_filler.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    pdf_form_filler.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
