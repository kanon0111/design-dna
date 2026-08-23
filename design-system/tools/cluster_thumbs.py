"""metrics.json を k-means でクラスタに分け、centroid から機械的に名前を付ける。

「〇〇系」を私の主観でラベル付けすると、避けたかった「AIの平均」がそこに入る。
なので分類は実測値だけで決め、名前も centroid の値から導出する。
"""
import io, json, os, sys
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REFS = os.path.join(ROOT, "design-system", "refs")
KEYS = ["lightness", "sat", "contrast", "hue_spread", "density", "whitespace"]


def name_of(c):
    """centroid（元スケール）から日本語のラベルを組み立てる。"""
    light, sat, contrast, hue, dens, ws = (c[k] for k in KEYS)
    if light < 0.35:
        base = "ダーク"
    elif light < 0.75:
        base = "ミッドトーン"
    else:
        base = "ライト"
    if sat > 0.20 or hue > 0.60:
        color = "多色・高彩度"
    elif sat > 0.06:
        color = "差し色あり"
    else:
        color = "ほぼ無彩色"
    if ws > 0.72:
        space = "余白たっぷり"
    elif ws > 0.55:
        space = "余白ふつう"
    else:
        space = "密"
    punch = "パンチ強" if contrast > 0.60 else ("トーナル" if contrast < 0.42 else "")
    parts = [base, color, space] + ([punch] if punch else [])
    return " / ".join(parts)


def short_of(c):
    """一覧に出す短い呼び名。これも centroid からの導出で、主観を入れない。"""
    light, sat, contrast, hue, dens, ws = (c[k] for k in KEYS)
    dark = light < 0.35
    vivid = sat > 0.20
    dense = ws < 0.50 or dens > 0.060
    punch = contrast > 0.60
    if dark and vivid:   return "ダーク・鮮色"
    if dark:             return "ダーク・静"
    if vivid:            return "カラフル"
    if dense:            return "情報密度"
    if punch:            return "明快コントラスト"
    return "静かな余白"


def main():
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    m = json.load(io.open(os.path.join(REFS, "metrics.json"), encoding="utf-8"))
    ids = sorted(m)
    X = np.array([[m[i][key] for key in KEYS] for i in ids], np.float32)

    mu, sd = X.mean(0), X.std(0) + 1e-6
    Z = (X - mu) / sd
    # 明度は分布がはっきり割れていて分類の骨になるので重めに見る
    Z[:, 0] *= 1.8

    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-4)
    _, labels, centers = cv2.kmeans(Z, k, None, crit, 20, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()

    centers_raw = centers.copy()
    centers_raw[:, 0] /= 1.8
    centers_raw = centers_raw * sd + mu

    groups = []
    for ci in range(k):
        members = [ids[j] for j in range(len(ids)) if labels[j] == ci]
        c = {key: float(centers_raw[ci][n]) for n, key in enumerate(KEYS)}
        groups.append({"label": name_of(c), "short": short_of(c),
                       "centroid": {key: round(v, 3) for key, v in c.items()},
                       "members": members})
    # 明るい順に並べると人が見て納得しやすい
    groups.sort(key=lambda g: -g["centroid"]["lightness"])
    for n, g in enumerate(groups):
        g["id"] = f"c{n+1}"

    json.dump({"clusters": groups}, io.open(os.path.join(REFS, "clusters.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    print(f"k={k}  合計 {len(ids)} 件\n", file=w)
    for g in groups:
        c = g["centroid"]
        print(f"{g['id']}  {len(g['members']):>3d}件  {g['short']}  —  {g['label']}", file=w)
        print(f"        明度{c['lightness']:.2f} 彩度{c['sat']:.2f} コントラスト{c['contrast']:.2f} "
              f"色数{c['hue_spread']:.2f} 密度{c['density']:.3f} 余白{c['whitespace']:.2f}", file=w)
    w.flush()


if __name__ == "__main__":
    main()
