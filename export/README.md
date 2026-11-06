# Export

`graph_to_markdown.py` (#8) regenerates `knowledge/colossus-bets/` from the `:KbCurrent` versions, when someone asks for a markdown copy of the KB. It is not run after every write: agents read the graph, and the copy in `knowledge/colossus-bets/` is an old snapshot (#19).

```
uv run skills/knowledge/scripts/kb.py export          # write knowledge/colossus-bets/
uv run skills/knowledge/scripts/kb.py export --check  # compare only; exit 1 if the files differ from the graph
```

Run it through `kb.py export` with `uv run`: that brings `neo4j` (declared inline in `kb.py`). Running `graph_to_markdown.py` directly needs a Python that already has `neo4j`.

It uses the reader login (`COLOSSUS_KB_READER_*`, else the writer). Each run:

1. Runs every integrity check and reads the categories and current facts **in one read transaction**. Any integrity problem: nothing is written.
2. Renders the files:
   - **one file per leaf category with facts** (`<path>.md`). One fact: the file is that fact. Several: the category title and description, then one `##` entry per fact, ordered by title;
   - each entry has `**Added**`, `**Updated**`, `**Context**` and `**Id**` lines, the summary as a `>` lead line (skipped when the statement opens with it), then the statement;
   - **an `index.md` per folder** and the library root: files table, subfolders, and a Quick Reference line per fact (`- kw1 / kw2: file.md - summary`).
3. Writes only files that changed and removes `.md` files it no longer produces. Other files (`.gitkeep`) are kept. It refuses any output folder not named `colossus-bets`, and, before touching anything, a run that would remove more than 3 files unless `--allow-removals` is given (a partial graph would otherwise quietly delete most of the export; check with `--check` first).

| Date | Meaning |
|------|---------|
| Added | Earliest `valid_from` among versions that were in force (not never-valid) and not replaced by a correction |
| Updated | When the current version was recorded, if it replaced another; for a first version, the legacy **Updated** date from the ingest (else omitted). A promoted draft is recorded when it's approved, so Updated is the approval date |

Rules:

- The output is generated. Every file starts with `<!-- Generated from Colossus KB graph; edit via kb.py, not here -->`. Change knowledge with `kb.py write`; the graph is what agents read. Never edit the markdown by hand.
- The output is deterministic (no timestamps): two runs on the same graph give identical files.
- Drafts and retracted facts are not exported. A write run refuses when the graph has no current facts (an empty or wrong database would otherwise delete the whole export).
