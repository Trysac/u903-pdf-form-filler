# Architecture

`trysac-pdf-form-filler` is a zero-runtime-dependency Python library for parsing, validating, filling, and flattening AcroForms in PDF documents according to ISO 32000-1:2008 (PDF 1.7).

## Core Components

1. **Tokenizer & Parser (`tokenizer.py`, `parser.py`)**:
   - Hand-written lexical tokenizer handling PDF names, literals, hex strings, numbers, references, dictionaries, and arrays.
   - Handles both traditional cross-reference tables (section 7.5.4) and cross-reference streams (7.5.8) with object streams (7.5.7).
   - Implements FlateDecode with PNG predictors (10-15) via stdlib `zlib`.
   - Enforces nesting depth limits (64) and object counts (< 1,000,000).

2. **Field Hierarchy Walker (`ops.py`)**:
   - Walks AcroForm `/Fields` and `/Kids` hierarchies up to a recursion depth of 32.
   - Collects inherited attributes (`/FT`, `/Ff`, `/V`, `/DA`, `/Opt`, `/MaxLen`).
   - Constructs typed `Field` models (`text`, `checkbox`, `radio`, `choice`, `signature`).

3. **Incremental Writer (`writer.py`, `ops.py`)**:
   - Emits incremental updates conforming to section 7.5.6.
   - Original PDF bytes remain unaltered.
   - Generates appearance streams (`/AP`) for widgets and appends changed objects and a trailer with `/Prev`.

4. **Flattener (`ops.py`)**:
   - Transforms widget appearances into normal page `/Resources /XObject` form streams and appends `/FlatN Do` content stream operators to each page.
   - Clears `/AcroForm /Fields` and removes `/Widget` annotations from `/Annots`.
