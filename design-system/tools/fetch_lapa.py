"""Lapa Ninja の候補を年代横断でサンプリングして candidates/lapa.json に書く。

最新ページだけ取ると「今の流行の平均」に寄る（＝避けたかった AI っぽさ）ので、
全311ページから均等に間引いて拾う。
"""
import json, os, re, sys, urllib.request
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "refs", "candidates", "lapa.json")

IMG = re.compile(r"cdn\.lapa\.ninja/assets/images/1x/([^\"'\s]+?)-thumb\.(jpg|png|webp)")
CARD = re.compile(
    r'<img src="https://cdn\.lapa\.ninja/assets/images/1x/([^"]+?)-thumb\.(jpg|png|webp)".*?'
    r'href="/post/([a-z0-9][a-z0-9\-]*)/"',
    re.S)
TITLE = re.compile(r'href="/post/([a-z0-9][a-z0-9\-]*)/"[^>]*>\s*([^<]{1,80}?)\s*<')

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")

def page_url(n):
    return "https://www.lapa.ninja/post/" if n == 1 else f"https://www.lapa.ninja/post/page/{n}/"

def scrape(n):
    try:
        html = get(page_url(n))
    except Exception as e:
        return n, [], str(e)[:60]
    titles = dict(TITLE.findall(html))
    rows = []
    for img, ext, slug in CARD.findall(html):
        rows.append([slug, img, ext, titles.get(slug, slug.replace("-", " ").title())])
    # 同一ページ内の重複（カードが複数リンクを持つ）を除く
    seen, uniq = set(), []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0]); uniq.append(r)
    return n, uniq, None

def main():
    total_pages = 311
    want_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    step = max(1, (total_pages - 1) // (want_pages - 1))
    pages = sorted({1 + i * step for i in range(want_pages)} | {total_pages})
    pages = [p for p in pages if p <= total_pages]

    existing = []
    if os.path.exists(OUT):
        existing = json.load(open(OUT, encoding="utf-8"))
    merged, seen = [], set()
    for r in existing:
        if r[0] not in seen:
            seen.add(r[0]); merged.append(r)
    before = len(merged)

    with ThreadPoolExecutor(max_workers=4) as ex:
        for n, rows, err in ex.map(scrape, pages):
            if err:
                print(f"page {n:>3}: FAILED {err}"); continue
            added = 0
            for r in rows:
                if r[0] in seen:
                    continue
                seen.add(r[0]); merged.append(r); added += 1
            print(f"page {n:>3}: {len(rows):>2} 件中 {added:>2} 件が新規")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in merged) + "\n]\n")
    print(f"\n{before} 件 -> {len(merged)} 件（{len(pages)}ページ: {pages}）")

if __name__ == "__main__":
    main()
