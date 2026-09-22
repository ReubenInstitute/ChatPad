"""One-off/rerunnable script: download a favicon per model provider (the id prefix
before '/' in models.json) into static/model-icons/, by scraping each provider's
openrouter.ai/<slug> page for its "Favicon for <slug>" <img src>.

Usage: python3 fetch_model_icons.py
"""
import json
import re
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ICON_DIR = HERE / "static" / "model-icons"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def providers_from_models_json():
    data = json.loads((HERE / "models.json").read_text())
    slugs = set()
    for m in data["data"]:
        slug = m["id"].split("/")[0].lstrip("~")
        slugs.add(slug)
    return sorted(slugs)


def find_icon_src(page_html, slug):
    m = re.search(r'Favicon for %s"[^>]*src="([^"]+)"' % re.escape(slug), page_html)
    return m.group(1).replace("&amp;", "&") if m else None


def main():
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    slugs = providers_from_models_json()
    print(f"{len(slugs)} providers")
    ok, failed = [], []
    for slug in slugs:
        dest_existing = list(ICON_DIR.glob(f"{slug}.*"))
        if dest_existing:
            print(f"skip {slug} (already have {dest_existing[0].name})")
            ok.append(slug)
            continue
        try:
            page = fetch(f"https://openrouter.ai/{slug}").decode("utf-8", "ignore")
            src = find_icon_src(page, slug)
            if not src:
                raise ValueError("no Favicon <img> found on author page")
            if src.startswith("/"):
                src = "https://openrouter.ai" + src
            ext = src.split("?")[0].rsplit(".", 1)[-1].lower()
            if ext not in ("svg", "png", "webp", "jpg", "jpeg", "ico"):
                ext = "png"
            img = fetch(src)
            (ICON_DIR / f"{slug}.{ext}").write_bytes(img)
            print(f"ok   {slug} <- {src}")
            ok.append(slug)
        except Exception as e:
            print(f"FAIL {slug}: {e}")
            failed.append(slug)
        time.sleep(0.3)
    print(f"\n{len(ok)} ok, {len(failed)} failed: {failed}")


if __name__ == "__main__":
    main()
