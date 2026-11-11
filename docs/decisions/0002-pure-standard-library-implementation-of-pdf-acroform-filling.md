# Pure standard library implementation of PDF AcroForm filling and incremental updates

Status: accepted (generated, pending human review)

## Context

Back offices need to fill AcroForms reliably with strict field validation without depending on heavy third-party runtimes or external binaries like pdftk. Incremental updates must preserve original file integrity.

## Decision

Implement a self-contained PDF 1.7 parser, object tokenizer, appearance generator, and incremental writer using Python's standard library (with zlib for FlateDecode decompression). Use pypdf only as a dev-time test oracle.

## Consequences

Zero runtime dependencies, precise typed error codes, high security against untrusted files through depth/size limits, and guaranteed byte-level incremental updates.
