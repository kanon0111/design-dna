"""Godly の Websites エントリ（18件）の静止画アセットを一括取得する。

thumbnail だけでなく desktop-full（フルページ丸ごと）とセクション単位の切り出しを
取りに行く。存在しない組合せは 404 が返るだけなので黙って飛ばす。
"""
import os, sys, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

SLUGS = ["auxia","serro","coderabbit","arrakis","weav","vessa","lightspark","pryzm","set",
         "clears","spade","round","solidroad","deck","rerun","rulebase","teak","melius"]

KINDS = ["desktop-full","mobile-full","thumbnail",
         "hero-desktop","hero-mobile","cta-desktop","cta-mobile","cta2-desktop",
         "footer-desktop","footer-mobile","feature-desktop","feature-mobile",
         "testimonial-desktop","testimonial-mobile"]

BASE = "https://cdn.godly.design/sites/{slug}/{kind}.webp"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "refs", "images", "godly")

def one(job):
    slug, kind = job
    dst = os.path.join(OUT, slug, kind + ".webp")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return ("skip", slug, kind, os.path.getsize(dst))
    url = BASE.format(slug=slug, kind=kind)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://godly.design/"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        return ("404", slug, kind, e.code)
    except Exception as e:
        return ("err", slug, kind, str(e)[:60])
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as fh:
        fh.write(data)
    return ("ok", slug, kind, len(data))

def main():
    jobs = [(s, k) for s in SLUGS for k in KINDS]
    got, missing, failed, total = [], 0, [], 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for status, slug, kind, info in ex.map(one, jobs):
            if status in ("ok", "skip"):
                got.append((slug, kind, info)); total += info
            elif status == "404":
                missing += 1
            else:
                failed.append((slug, kind, info))
    per = {}
    for slug, kind, size in got:
        per.setdefault(slug, []).append(kind)
    for slug in SLUGS:
        ks = per.get(slug, [])
        print(f"{slug:12s} {len(ks):2d}  {' '.join(sorted(ks))}")
    print(f"\n取得 {len(got)} 枚 / {total/1024/1024:.1f} MB   （存在しなかった組合せ {missing}）")
    for slug, kind, err in failed:
        print(f"FAILED {slug}/{kind}: {err}")

if __name__ == "__main__":
    main()
