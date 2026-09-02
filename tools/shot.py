"""ページを画像に撮る。配置の一致を測るために要る。

playwright を入れなくても、Windows に最初から入っている Edge が
Chromium なのでヘッドレスで撮れる。

    python tools/shot.py <URL> <出力.png> [高さ]

高さを省くと、ページの実際の高さを測ってから撮り直す（全体が入る）。
"""
import io, os, re, shutil, subprocess, sys, urllib.request

WIDTH = 1280
MAXH = 20000

CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def browser():
    for c in ("chromium", "google-chrome", "chrome", "msedge"):
        p = shutil.which(c)
        if p:
            return p
    for p in CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def _guess_height(url):
    """CSS に書かれたページ全体の高さを拾う。無ければ既定。"""
    try:
        html = urllib.request.urlopen(url, timeout=8).read().decode("utf-8", "replace")
    except Exception:
        return 3000
    css = ""
    for m in re.finditer(r'href="([^"]+\.css)"', html):
        try:
            css += urllib.request.urlopen(
                url.rstrip("/") + "/" + m.group(1).lstrip("./"), timeout=8
            ).read().decode("utf-8", "replace")
        except Exception:
            pass
    hs = [int(x) for x in re.findall(r"(?:min-)?height:\s*(\d{3,5})px", css + html)]
    return min(MAXH, max(3000, max(hs) + 200)) if hs else 3000


def _trim(path):
    """下に続く一様な余白を切り落とす。

    ヘッドレスはウィンドウの高さぶんしか撮れないので、いったん十分高く撮って、
    中身が終わったところで切る。こうすればページの実寸が分からなくても全体が入る。
    """
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        a = np.asarray(im.convert("RGB"))
    if a.shape[0] < 40:
        return
    # 最下行の色を「終わったあとの色」とみなす
    tail = a[-1].astype(np.int16)
    same = (np.abs(a.astype(np.int16) - tail).max(axis=2) < 6).all(axis=1)
    end = a.shape[0]
    while end > 40 and same[end - 1]:
        end -= 1
    end = min(a.shape[0], end + 24)          # 少し余白を残す
    if end < a.shape[0]:
        Image.fromarray(a[:end]).save(path)


def shoot(url, dst, height=None):
    exe = browser()
    if not exe:
        return None
    h = height or MAXH
    dst = os.path.abspath(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    cmd = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--force-device-scale-factor=1",
           "--window-size=%d,%d" % (WIDTH, h),
           "--screenshot=%s" % dst, url]
    subprocess.run(cmd, capture_output=True, timeout=180)
    if not os.path.exists(dst):
        return None
    if height is None:
        _trim(dst)
    return dst


def main():
    if len(sys.argv) < 3:
        print(__doc__); return 1
    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    h = int(sys.argv[3]) if len(sys.argv) > 3 else None
    out = shoot(sys.argv[1], sys.argv[2], h)
    if not out:
        print("撮れなかった（ブラウザが見つからない）", file=w); w.flush(); return 1
    from PIL import Image
    with Image.open(out) as im:
        print("%s  %dx%d" % (out, im.size[0], im.size[1]), file=w)
    w.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
