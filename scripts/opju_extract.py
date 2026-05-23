"""
Extract data from .opju Origin project files into CSV.
Requires: Origin/OriginPro installed + pip install originpro pandas

Usage:
  python opju_extract.py <file.opju>               # list content
  python opju_extract.py <file.opju> --csv         # extract to CSV files
  python opju_extract.py <file.opju> -o <dir>      # extract to specific directory
  python opju_extract.py <path> --all              # extract all .opju in path
"""
import originpro as op
import pandas as pd
import os
import sys
import glob

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def init_origin():
    if op.oext:
        try:
            op.set_show(False)
        except Exception:
            pass


def shutdown_origin():
    if op.oext:
        try:
            op.exit()
        except Exception:
            pass


def list_content(file_path):
    init_origin()
    op.open(file=file_path, readonly=True)

    base = os.path.basename(file_path)
    print(f"=== {base} ===\n")

    book_count = 0
    graph_count = 0

    for p in op.pages():
        ptype = type(p).__name__
        if ptype == 'WBook':
            book_count += 1
            sheets_info = []
            for sheet in p:
                try:
                    shape = sheet.shape
                    sheets_info.append(f"{sheet.name}({shape[0]}r x {shape[1]}c)")
                except Exception:
                    sheets_info.append(f"{sheet.name}(?)")
            sheet_list = ', '.join(sheets_info)
            print(f"  [WBook] '{p.name}' -> {len(p)} sheets: {sheet_list}")

        elif ptype == 'GPage':
            graph_count += 1
            print(f"  [Graph] '{p.name}'")

    print(f"\n  Summary: {book_count} workbooks, {graph_count} graphs\n")
    shutdown_origin()


def extract_to_csv(file_path, output_dir=None):
    init_origin()
    op.open(file=file_path, readonly=True)

    if output_dir is None:
        output_dir = os.path.dirname(file_path)

    basename = os.path.splitext(os.path.basename(file_path))[0]
    # Create subfolder for this file's output
    out = os.path.join(output_dir, f"{basename}_csv")
    os.makedirs(out, exist_ok=True)

    results = []
    for book in op.pages():
        if type(book).__name__ != 'WBook':
            continue

        bk_name = book.name
        for sheet in book:
            try:
                sname = sheet.name
                df = sheet.to_df()
                safe_name = f"{bk_name}_{sname}".replace(' ', '_')
                fpath = os.path.join(out, f"{safe_name}.csv")
                df.to_csv(fpath, index=False, encoding='utf-8-sig')
                info = (fpath, df.shape)
                print(f"  {safe_name}.csv  ({df.shape[0]}r x {df.shape[1]}c)")
                results.append(info)
            except Exception as e:
                print(f"  SKIP {bk_name}/{sheet.name}: {e}")

    shutdown_origin()
    if results:
        print(f"\n  Saved {len(results)} files to: {out}")
    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Extract data from Origin .opju files')
    parser.add_argument('path', help='Path to .opju file or directory containing .opju files')
    parser.add_argument('--csv', action='store_true', help='Extract all sheets to CSV')
    parser.add_argument('--all', action='store_true', help='Process all .opju files in path recursively')
    parser.add_argument('-o', '--output-dir', default=None, help='Output directory for CSV files')
    args = parser.parse_args()

    if os.path.isdir(args.path):
        files = glob.glob(os.path.join(args.path, "**", "*.opju"), recursive=True)
    elif args.all:
        base = os.path.dirname(args.path) or '.'
        files = glob.glob(os.path.join(base, "**", "*.opju"), recursive=True)
    else:
        files = [args.path]

    if not files:
        print("No .opju files found.")
        exit(1)

    for f in files:
        if not os.path.exists(f):
            print(f"File not found: {f}")
            continue
        if args.csv:
            extract_to_csv(f, args.output_dir)
        else:
            list_content(f)
