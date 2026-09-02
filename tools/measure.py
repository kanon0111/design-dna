"""生成した案が参照にどれだけ似ているかを、実測で出す。

227件の分類に使ったのと同じ6指標（明度・彩度・コントラスト・色相の散らばり・
密度・余白）で、参照画像と生成結果を同じ物差しに乗せる。
「似ている気がする／しない」を数字にするためのもの。

    python tools/measure.py <参照画像> <比べる画像> [<比べる画像> ...]

参照はページ上部の切り抜きであることが多いので、比べる側も上から
同じ縦横比だけを見る（analyze_thumbs.py と同じ切り方）。
"""
import io, os, sys

import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

W = 480
KEYS = ["lightness", "sat", "contrast", "hue_spread", "density", "whitespace"]
LABEL = {"lightness": "明度", "sat": "彩度", "contrast": "コントラスト",
         "hue_spread": "色数", "density": "密度", "whitespace": "余白"}
# 軸の重みに寄せた重要度（見た目の近さへの効き方）
WEIGHT = {"lightness": 2.0, "sat": 1.5, "contrast": 1.0,
          "hue_spread": 0.8, "density": 1.0, "whitespace": 1.2}


def imread(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def measure(path):
    img = imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    keep = min(h, int(w * 4 / 3))          # 上から4:3ぶん（参照と同じ切り方）
    img = img[:keep]
    img = cv2.resize(img, (W, max(1, int(img.shape[0] * W / img.shape[1]))),
                     interpolation=cv2.INTER_AREA)

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    H, S, V = (hsv[..., i].astype(np.float32) for i in range(3))

    ang = H * 2 * np.pi / 180.0
    wgt = (S / 255.0) ** 2
    if wgt.sum() > 1e-6:
        cx = float((np.cos(ang) * wgt).sum() / wgt.sum())
        cy = float((np.sin(ang) * wgt).sum() / wgt.sum())
        hue_spread = 1.0 - min(1.0, (cx * cx + cy * cy) ** 0.5)
    else:
        hue_spread = 0.0

    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 60, 160)
    flat = img.reshape(-1, 3).astype(np.int32)
    key = (flat[:, 0] >> 4) << 8 | (flat[:, 1] >> 4) << 4 | (flat[:, 2] >> 4)
    top = int(np.bincount(key, minlength=4096).argmax())
    bg = np.array([((top >> 8) & 15) * 16 + 8, ((top >> 4) & 15) * 16 + 8,
                   (top & 15) * 16 + 8], np.float32)
    dist = np.linalg.norm(flat.astype(np.float32) - bg, axis=1)

    return {"lightness": float(np.median(V)) / 255.0,
            "sat": float(np.median(S)) / 255.0,
            "contrast": float(np.std(gray)) / 128.0,
            "hue_spread": hue_spread,
            "density": float((edges > 0).mean()),
            "whitespace": float((dist < 40).mean())}


def distance(a, b):
    """重み付きの差。0 に近いほど似ている。"""
    tot = sum(WEIGHT[k] * abs(a[k] - b[k]) for k in KEYS)
    return tot / sum(WEIGHT.values())


def main():
    if len(sys.argv) < 3:
        print(__doc__); return 1
    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    ref_path = sys.argv[1]
    ref = measure(ref_path)
    if ref is None:
        print("参照が読めない: %s" % ref_path, file=w); w.flush(); return 1

    rows = [("参照 " + os.path.basename(ref_path), ref, 0.0)]
    for p in sys.argv[2:]:
        m = measure(p)
        if m is None:
            print("読めない: %s" % p, file=w); continue
        rows.append((os.path.basename(os.path.dirname(p)) or os.path.basename(p),
                     m, distance(ref, m)))

    head = "%-22s" % "" + "".join("%8s" % LABEL[k] for k in KEYS) + "%10s" % "参照との差"
    print(head, file=w)
    print("-" * len(head), file=w)
    for name, m, d in rows:
        line = "%-22s" % name[:22] + "".join("%8.3f" % m[k] for k in KEYS)
        line += "%10s" % ("—" if d == 0 else "%.3f" % d)
        print(line, file=w)

    if len(rows) > 2:
        best = min(rows[1:], key=lambda r: r[2])
        print("\n参照に一番近い: %s（%.3f）" % (best[0], best[2]), file=w)
    w.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
