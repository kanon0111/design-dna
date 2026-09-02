"""参照画像の色と、生成された CSS の色を突き合わせる。

「参照に似ているか」で一番効くのは配色。ページを描画しなくても、
CSS に書かれた色と参照画像の主要色を比べれば、寄せられているかは分かる。

    python tools/palette.py <参照画像> <css> [<css> ...]

出す数字:
  一致率  CSS の色のうち、参照の主要色に近いものの割合
  平均距離 CSS の各色から参照の最寄り色までの距離（Lab、小さいほど近い）
"""
import io, os, re, sys

import numpy as np
import cv2

HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
RGB = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")
# axes.md が oklch を勧めているので、そちらで書かれた CSS も読む
OKLCH = re.compile(r"oklch\(\s*([\d.]+)%?\s+([\d.]+)\s+([\d.]+)")
NEAR = 18.0          # Lab でこれ以内なら「同じ色を使っている」とみなす


def oklch_to_bgr(L, C, Hdeg):
    """oklch -> sRGB(BGR)。CSS Color 4 の変換をそのまま。"""
    import math
    if L > 1.5:          # "72%" のような書き方
        L /= 100.0
    h = math.radians(Hdeg)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    lin = (+4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    out = []
    for v in lin:
        v = max(0.0, min(1.0, v))
        v = 12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055
        out.append(int(round(max(0.0, min(1.0, v)) * 255)))
    r, g, bl = out
    return np.array([bl, g, r], np.uint8)


def imread(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def ref_palette(path, k=8):
    """参照画像の主要色を、面積の大きい順に返す。"""
    img = imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    img = img[:min(h, int(w * 4 / 3))]
    img = cv2.resize(img, (240, max(1, int(img.shape[0] * 240 / img.shape[1]))),
                     interpolation=cv2.INTER_AREA)
    z = img.reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 1e-3)
    _, lab, cen = cv2.kmeans(z, k, None, crit, 8, cv2.KMEANS_PP_CENTERS)
    share = np.bincount(lab.ravel(), minlength=k) / len(lab)
    order = np.argsort(-share)
    return [(cen[i].astype(np.uint8), float(share[i])) for i in order]


def css_colors(path):
    """CSS に書かれている色を拾う（重複は残す＝よく使う色ほど重い）。"""
    s = io.open(path, encoding="utf-8", errors="replace").read()
    out = []
    for m in HEX.finditer(s):
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        out.append(np.array([int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)], np.uint8))
    for m in RGB.finditer(s):
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        out.append(np.array([b, g, r], np.uint8))
    for m in OKLCH.finditer(s):
        out.append(oklch_to_bgr(float(m.group(1)), float(m.group(2)), float(m.group(3))))
    return out


def to_lab(bgr):
    px = np.array([[bgr]], np.uint8)
    return cv2.cvtColor(px, cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)


def hexof(bgr):
    b, g, r = (int(x) for x in bgr)
    return "#%02x%02x%02x" % (r, g, b)


def main():
    if len(sys.argv) < 3:
        print(__doc__); return 1
    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    pal = ref_palette(sys.argv[1])
    if pal is None:
        print("参照が読めない", file=w); w.flush(); return 1

    print("参照の主要色: " + "  ".join(
        "%s(%.0f%%)" % (hexof(c), s * 100) for c, s in pal), file=w)
    ref_lab = [to_lab(c) for c, _ in pal]

    print("", file=w)
    print("%-26s %6s %8s  %s" % ("", "色数", "一致率", "平均距離"), file=w)
    for p in sys.argv[2:]:
        cols = css_colors(p)
        if not cols:
            print("%-26s 色が見つからない" % os.path.basename(p), file=w); continue
        ds = []
        for c in cols:
            l = to_lab(c)
            ds.append(min(float(np.linalg.norm(l - r)) for r in ref_lab))
        hit = sum(1 for d in ds if d <= NEAR) / len(ds)
        name = os.path.basename(os.path.dirname(p)) or os.path.basename(p)
        print("%-26s %6d %7.0f%% %9.1f" % (name, len(cols), hit * 100, sum(ds) / len(ds)), file=w)

    print("\n一致率 = CSS の色のうち参照の主要色に近い（Lab距離 %.0f 以内）ものの割合" % NEAR, file=w)
    w.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
