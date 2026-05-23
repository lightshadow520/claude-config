"""Web search via DuckDuckGo — free, no API key needed."""
import json
import sys
from ddgs import DDGS

# Fix encoding issues on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def search(query: str, max_results: int = 10):
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
        return results

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python websearch.py <query> [--count N] [--json]", file=sys.stderr)
        sys.exit(1)

    query_parts = []
    count = 10
    as_json = False
    i = 0
    while i < len(args):
        if args[i] == "--count" and i + 1 < len(args):
            count = int(args[i + 1])
            i += 2
        elif args[i] == "--json":
            as_json = True
            i += 1
        else:
            query_parts.append(args[i])
            i += 1

    query = " ".join(query_parts)

    try:
        results = search(query, max_results=count)
    except Exception as e:
        print(f"Search failed: {e}", file=sys.stderr)
        sys.exit(1)

    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    for j, r in enumerate(results, 1):
        print(f"[{j}] {r['title']}")
        print(f"    {r['href']}")
        print(f"    {r['body']}")
        print()

if __name__ == "__main__":
    main()
