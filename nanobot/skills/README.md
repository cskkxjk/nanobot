# nanobot Skills

This directory contains built-in skills that extend nanobot's capabilities.

## Skill Format

Each skill is a directory containing a `SKILL.md` file with:
- YAML frontmatter (name, description, metadata)
- Markdown instructions for the agent

## Attribution

These skills are adapted from [OpenClaw](https://github.com/openclaw/openclaw)'s skill system.
The skill format and metadata structure follow OpenClaw's conventions to maintain compatibility.

## Available Skills

| Skill | Description |
|-------|-------------|
| `github` | Interact with GitHub using the `gh` CLI |
| `weather` | Get weather info using wttr.in and Open-Meteo |
| `summarize` | Summarize URLs, files, and YouTube videos |
| `tmux` | Remote-control tmux sessions |
| `clawhub` | Search and install skills from ClawHub registry |
| `skill-creator` | Create new skills |
| `file_reader` | Read and summarize text-based files only (migrated from CoPaw) |
| `news` | Look up latest news from specified news sites (migrated from CoPaw) |
| `browser_visible` | Use visible (headed) browser when user requests it (migrated from CoPaw) |
| `xlsx` | Spreadsheet .xlsx/.csv/.tsv create, read, edit (migrated from CoPaw) |
| `pptx` | PPT create, edit, parse (migrated from CoPaw) |
| `pdf` | PDF read, merge, split, forms, OCR (migrated from CoPaw) |
| `docx` | Word document create, read, edit (migrated from CoPaw) |

See [MIGRATION_VERIFY.md](MIGRATION_VERIFY.md) for verification samples for migrated CoPaw skills and tools.