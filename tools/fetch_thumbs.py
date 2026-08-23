"""picker の227件のサムネをローカルに落とす（解析用）。

クラスタリングのラベルを私の主観で付けると、そこに「AIの平均」が入り込む。
それを避けるため画像そのものから実測する。その素材集め。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import io, json, os, re, urllib.request
from concurrent.futures import ThreadPoolExecutor

CAND = paths.CANDIDATES
OUT = paths.THUMBS
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

def load(n):
    p = os.path.join(CAND, n)
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else []

def targets():
    out = []
    for i, r in enumerate(load("godly.json")):
        # thumbnail.webp が無い3件は hero-desktop.webp が代替（picker と同じ挙動）
        out.append((f"g{i+1:02d}", f"https://cdn.godly.design/sites/{r[0]}/thumbnail.webp",
                    f"https://cdn.godly.design/sites/{r[0]}/hero-desktop.webp"))
    for i, r in enumerate(load("lapa.json")):
        out.append((f"l{i+1:02d}",
                    f"https://cdn.lapa.ninja/assets/images/2x/{r[1]}-thumb.{r[2]}", None))
    for i, r in enumerate(load("awwwards.json")):
        out.append((f"a{i+1:02d}", r[1], None))
    return out

def grab(t):
    pid, url, alt = t
    dst = os.path.join(OUT, pid + ".img")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return ("skip", pid)
    for u in [x for x in (url, alt) if x]:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": "https://godly.design/"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            os.makedirs(OUT, exist_ok=True)
            open(dst, "wb").write(data)
            return ("ok", pid)
        except Exception:
            continue
    return ("fail", pid)

if __name__ == "__main__":
    ts = targets()
    counts = {}
    fails = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for status, pid in ex.map(grab, ts):
            counts[status] = counts.get(status, 0) + 1
            if status == "fail":
                fails.append(pid)
    print(f"対象 {len(ts)} 件 -> {counts}")
    if fails:
        print("取得できず:", " ".join(fails))
