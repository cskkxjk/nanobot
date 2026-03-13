---
name: file_reader
description: "Scope and workflow for reading text-based files only. Use read_file (already available) for .txt/.md/.json/.yaml/.csv etc. PDF/Office/images/archives are handled by other skills. This skill adds: type check, large-file handling, and out-of-scope boundaries."
metadata:
  {
    "copaw": { "emoji": "📄", "requires": {} },
    "nanobot": { "emoji": "📄", "requires": {} }
  }
---
# File Reader Scope and Workflow

Use this skill when the user asks to read or summarize **text-based** local files. It does not implement reading—use the existing **read_file** tool. This skill defines scope and workflow only.

## Scope (text-based only)

Preferred for: `.txt`, `.md`, `.json`, `.yaml/.yml`, `.csv/.tsv`, `.log`, `.sql`, `ini`, `toml`, `py`, `js`, `html`, `xml` source code. For JSON/YAML: list top-level keys and important fields. For CSV/TSV: show header + first few rows, then summarize columns.

## Type check (when uncertain)

Use a type probe before reading:

```bash
file -b --mime-type "/path/to/file"
```

## Large files

If the file is large, avoid dumping the whole content: extract a small, relevant portion and summarize.

## Large logs

If the file is huge, use a tail window:

```bash
tail -n 200 "/path/to/file.log"
```

Summarize the last errors/warnings and notable patterns.

## Out of scope

Do not handle the following in this skill (they are covered by other skills):

- PDF
- Office (docx/xlsx/pptx)
- Images
- Audio/Video

## Safety

- Never execute untrusted files.
- Prefer reading the smallest portion necessary.
- If a tool is missing, explain the limitation and ask the user for an alternate format.
