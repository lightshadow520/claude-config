---
name: opju-extract
description: Extract data from Origin .opju project files. Use when user mentions extracting/reading .opju files, Origin project data extraction, or converting Origin worksheets to CSV/DataFrame.
license: MIT
---

# OPJU Data Extraction

Extract worksheet data from Origin `.opju` project files using Python.

**Prerequisites:** Origin/OriginPro must be installed. The `originpro` Python package communicates with Origin's COM interface in the background.

## Quick Start

```bash
python <scripts_dir>/opju_extract.py "<file.opju>"          # list contents
python <scripts_dir>/opju_extract.py "<file.opju>" --csv     # extract all sheets to CSV
python <scripts_dir>/opju_extract.py "<dir>" --all --csv     # process all .opju in directory
```

Replace `<scripts_dir>` with the actual scripts path (see CLAUDE.md).

## Direct API Usage

For fine-grained control, use `originpro` directly:

```python
import originpro as op

# Suppress Origin UI
if op.oext:
    try: op.set_show(False)
    except Exception: pass

# Open file
op.open(file=r"path\to\file.opju", readonly=True)

# Iterate all workbooks and sheets
for book in op.pages():
    if type(book).__name__ == 'WBook':
        print(f"Book: {book.name} ({len(book)} sheets)")
        for sheet in book:
            print(f"  Sheet: {sheet.name} ({sheet.shape[0]}r x {sheet.shape[1]}c)")
            df = sheet.to_df()
            df.to_csv(f"{book.name}_{sheet.name}.csv", index=False, encoding='utf-8-sig')

# Shutdown
if op.oext:
    op.exit()
```

## Important Notes

- `op.set_show(False)` may fail on first call when Origin is cold-starting — catch and ignore this exception
- `op.find_sheet('w', '')` requires the `'w'` type parameter (not just empty string)
- `WBook` objects are iterable: `for sheet in book:` works directly
- Graphs (`GPage`) contain no tabular data and are skipped during CSV extraction
- `shape` is `(rows, cols)`, `to_df()` returns a full pandas DataFrame
- After extraction, always call `op.exit()` to close the background Origin process
