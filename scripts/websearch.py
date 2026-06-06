"""Web search via DuckDuckGo + URL fetch fallback — free, no API key needed."""
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


def fetch_url(url: str, timeout: int = 15) -> dict:
    """Fetch a URL and return structured content. Bypasses Claude's WebFetch restrictions."""
    try:
        import urllib.request
        import urllib.error

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            # Try to decode
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                text = raw.decode(charset, errors="replace")
            except Exception:
                text = raw.decode("utf-8", errors="replace")
            return {
                "ok": True,
                "url": resp.url,
                "status": resp.status,
                "content_type": resp.headers.get_content_type(),
                "length": len(raw),
                "text": text,
            }
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code} {e.reason}", "url": url}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"Connection failed: {e.reason}", "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}


def strip_html(text: str) -> str:
    """Basic HTML to plain text conversion."""
    import re
    # Remove scripts and styles
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Replace block elements with newlines
    text = re.sub(r"</?(?:div|p|li|tr|h[1-6]|br|hr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Remove remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python websearch.py <query> [--count N] [--json]", file=sys.stderr)
        print("       python websearch.py --fetch <url> [--html] [--strip]", file=sys.stderr)
        sys.exit(1)

    # ── Fetch mode ──
    if args[0] == "--fetch":
        if len(args) < 2:
            print("Usage: python websearch.py --fetch <url> [--html] [--strip]", file=sys.stderr)
            sys.exit(1)
        url = args[1]
        as_html = "--html" in args
        do_strip = "--strip" in args

        print(f"Fetching {url} ...", file=sys.stderr)
        result = fetch_url(url)

        if not result["ok"]:
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(1)

        if as_html:
            text = result["text"]
        elif do_strip:
            text = strip_html(result["text"])
        else:
            text = result["text"]

        # Summarize: only print meaningful text (first 8000 chars)
        if len(text) > 8000:
            text = text[:8000] + f"\n\n[... truncated, total {len(text)} chars. Use --html for full raw.]"

        print(text)
        return

    # ── Search mode ──
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
