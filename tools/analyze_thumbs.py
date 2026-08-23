"""サムネから軸の値を実測して metrics.json に書く。

axes.md の軸のうち、画像から機械的に測れるのは
  密度 / コントラスト / （色の性格）
の3つ。構図と主役は見ないと分からないので、ここでは測らない。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import io, json, os, sys
import numpy as np
import cv2

THUMBS = paths.THUMBS
OUT = paths.METRICS

W = 480  # 密度を比較可能にするため横幅を揃える


def imread(path):
    buf = np.fromfile(path, dtype=np.uint8)   # 非ASCIIパス対策
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def measure(path):
    img = imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    # 縦長のフルページ的サムネは上から4:3ぶんだけ見る（ヒーロー相当）
    keep = min(h, int(w * 4 / 3))
    img = img[:keep]
    img = cv2.resize(img, (W, max(1, int(img.shape[0] * W / img.shape[1]))), interpolation=cv2.INTER_AREA)

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    H, S, V = hsv[..., 0].astype(np.float32), hsv[..., 1].astype(np.float32), hsv[..., 2].astype(np.float32)

    lightness = float(np.median(V)) / 255.0          # 明るさ
    sat = float(np.median(S)) / 255.0                # 彩度
    contrast = float(np.std(gray)) / 128.0           # コントラスト

    # 色相の散らばり: 彩度で重み付けした円周分散（0=単色 1=多色）
    ang = H * 2 * np.pi / 180.0
    wgt = (S / 255.0) ** 2
    if wgt.sum() > 1e-6:
        cx = float((np.cos(ang) * wgt).sum() / wgt.sum())
        cy = float((np.sin(ang) * wgt).sum() / wgt.sum())
        hue_spread = 1.0 - min(1.0, (cx * cx + cy * cy) ** 0.5)
    else:
        hue_spread = 0.0

    # 密度: エッジが立っている画素の割合
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 60, 160)
    density = float((edges > 0).mean())

    # 余白率: 最頻色から近い画素の割合
    # np.unique(axis=0) は 70万行で数秒かかるので、色を12bitに詰めて bincount する
    flat = img.reshape(-1, 3).astype(np.int32)
    key = (flat[:, 0] >> 4) << 8 | (flat[:, 1] >> 4) << 4 | (flat[:, 2] >> 4)
    top = int(np.bincount(key, minlength=4096).argmax())
    bg = np.array([((top >> 8) & 15) * 16 + 8, ((top >> 4) & 15) * 16 + 8, (top & 15) * 16 + 8], np.float32)
    dist = np.linalg.norm(flat.astype(np.float32) - bg, axis=1)
    whitespace = float((dist < 40).mean())

    return dict(lightness=round(lightness, 4), sat=round(sat, 4), contrast=round(contrast, 4),
                hue_spread=round(hue_spread, 4), density=round(density, 4),
                whitespace=round(whitespace, 4))


def main():
    out, bad = {}, []
    for fn in sorted(os.listdir(THUMBS)):
        pid = os.path.splitext(fn)[0]
        m = measure(os.path.join(THUMBS, fn))
        if m is None:
            bad.append(pid); continue
        out[pid] = m
    json.dump(out, io.open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    print(f"測定 {len(out)} 件" + (f" / 失敗 {len(bad)}: {bad}" if bad else ""), file=w)
    print(f"\n{'指標':12s} {'p10':>7s} {'p25':>7s} {'p50':>7s} {'p75':>7s} {'p90':>7s}", file=w)
    for k in ["lightness", "sat", "contrast", "hue_spread", "density", "whitespace"]:
        v = np.array([m[k] for m in out.values()])
        ps = np.percentile(v, [10, 25, 50, 75, 90])
        print(f"{k:12s} " + " ".join(f"{x:7.3f}" for x in ps), file=w)
    w.flush()


if __name__ == "__main__":
    main()
