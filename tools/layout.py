"""参照画像から「配置」そのものを取り出す。

軸（構図＝左寄せ／中央対称…）は4択のラベルでしかなく、そこから元の見た目は
復元できない。人が「このデザインに似せて」と言うとき指しているのは、
文字と画像がどこにどれだけの大きさで置かれているか＝空間配置そのもの。
それを画像から直接読む。

読み方:
  1. 横いっぱいの空白が続くところで**セクション**に切る
     （Webページの区切りは色ではなく余白で作られていることが多い）
  2. 地の色が「長く続けて」変わるところも切る。短い揺れは切らない
     （大きな画像の上下で行の最頻色が揺れるのを区切りと誤認しないため）
  3. セクションの中をさらに空白で**行**に分け、行の中を横に切って**塊**にする
  4. 塊ごとに 文字／画像／色面 を見分ける

しきい値はすべてページ幅（W）に対する比。余白は幅に比例して設計されるので、
ページが縦に長くても短くても同じ構造が出る。

    python tools/layout.py <画像> [--out overlay.png] [--json out.json]
    python tools/layout.py --check <画像>    抽出が安定しているか自己検査
"""
import io, json, os, sys

import numpy as np
import cv2

W = 1000              # この幅に正規化してから読む

GAP_FLOOR = 58        # これ未満の空白は行間。セクションの切れ目にはしない
ROW_GAP = 15          # セクションの中で行を切る空白
COL_GAP = 26          # 行の中で塊を切る横の空白
MIN_BLOCK = 22        # これより細い塊は無視
MIN_ROW = 7           # これより低い行は無視
MIN_SECTION = 26      # これより低いセクションは隣に併合

BG_RUN = 46           # 地の色がこれだけ続いて初めて「色の帯」とみなす
BG_DIFF = 20          # 地の色がこれだけ違えば別の色
INK = 28              # 地の色からこれだけ離れた画素を「中身」とみなす
EMPTY = 0.004         # 行の中身がこの割合未満なら空白行


def imread(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def _smooth(a, k=9):
    """行ごとの値を縦に中央値でならす。画像の中の1行だけの揺れを消す。"""
    if a.shape[0] < k * 2:
        return a
    pad = k // 2
    p = np.pad(a, ((pad, pad), (0, 0)), mode="edge")
    out = np.empty_like(a)
    for c in range(a.shape[1]):
        v = np.lib.stride_tricks.sliding_window_view(p[:, c], k)
        out[:, c] = np.median(v, axis=1)
    return out


def _row_bg(img):
    """行ごとの地の色。行の中で一番多い色を量子化して取り、縦にならす。"""
    thin = img[:, ::3]                     # 最頻色を見るだけなので間引いてよい
    q = (thin // 24).astype(np.int32)
    key = q[:, :, 0] * 121 + q[:, :, 1] * 11 + q[:, :, 2]
    K = int(key.max()) + 1
    rows = np.repeat(np.arange(key.shape[0]), key.shape[1])
    cnt = np.bincount(rows * K + key.ravel(), minlength=key.shape[0] * K)
    top = cnt.reshape(key.shape[0], K).argmax(axis=1)
    sel = key == top[:, None]
    n = sel.sum(axis=1, keepdims=True).astype(np.float32)
    out = (thin.astype(np.float32) * sel[:, :, None]).sum(axis=1) / n
    return _smooth(out.astype(np.float32))


def _bg_runs(bg):
    """地の色が続いている区間。短い揺れは前の区間に吸わせる。"""
    runs, s = [], 0
    acc, n = bg[0].astype(np.float64).copy(), 1
    for y in range(1, len(bg)):
        if np.linalg.norm(bg[y] - acc / n) > BG_DIFF:
            runs.append([s, y])
            s, acc, n = y, bg[y].astype(np.float64).copy(), 1
        else:
            acc += bg[y]
            n += 1
    runs.append([s, len(bg)])

    merged = []
    for r in runs:
        if merged and r[1] - r[0] < BG_RUN:
            merged[-1][1] = r[1]           # 短すぎる帯は色の変化として扱わない
        else:
            merged.append(r)
    if len(merged) > 1 and merged[0][1] - merged[0][0] < BG_RUN:
        merged[1][0] = merged[0][0]
        merged.pop(0)
    return merged


def _runs(flags, gap, minlen):
    """True が続いている区間。gap 以下の切れ目はつなぐ。"""
    idx = np.where(flags)[0]
    if not len(idx):
        return []
    out, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > gap:
            if prev - start + 1 >= minlen:
                out.append((int(start), int(prev)))
            start = i
        prev = i
    if prev - start + 1 >= minlen:
        out.append((int(start), int(prev)))
    return out


def _gaps(rowfrac, minlen):
    """中身が無い行が minlen 以上続く区間。その真ん中が切れ目。"""
    empty = rowfrac < EMPTY
    out, start = [], None
    for y, e in enumerate(empty):
        if e and start is None:
            start = y
        elif not e and start is not None:
            if y - start >= minlen:
                out.append((start, y))
            start = None
    if start is not None and len(empty) - start >= minlen:
        out.append((start, len(empty)))
    return out


def _section_gap(gaps):
    """このページで「セクションの切れ目」と呼ぶ空白の大きさを、ページ自身から決める。

    固定のしきい値だと、ちょうど境目の空白が明るさや縮小で行ったり来たりして、
    セクション数が毎回1〜2ずれる。ずれる物差しで測った一致度は意味を持たない。
    空白の長さを並べると「行間の群れ」と「帯間の群れ」に分かれるので、
    その2つの群れを分ける位置（大津の方法）を境にする。
    """
    g = np.array(sorted(l for _, _, l in gaps), dtype=np.float64)
    if len(g) < 5:
        return GAP_FLOOR
    x = np.log(g)                          # 空白の長さは裾が長いので対数で見る
    best, thr = -1.0, GAP_FLOOR
    for i in range(1, len(x)):
        w0 = i / len(x)
        v = w0 * (1 - w0) * (x[:i].mean() - x[i:].mean()) ** 2
        if v > best:
            best, thr = v, g[i]
    return max(GAP_FLOOR, float(thr))


def _cuts(bg, rowfrac, H):
    """セクションの切れ目。空白の帯と、長く続く地の色の変わり目の合わせ技。"""
    all_gaps = [(a, b, b - a) for a, b in _gaps(rowfrac, ROW_GAP)]
    sg = _section_gap(all_gaps)
    cut = {0, H}
    for a, b, _ in [x for x in all_gaps if x[2] >= sg]:
        if a == 0:
            cut.add(b)                     # 冒頭の余白は中身の始まりまで飛ばす
        elif b >= H:
            cut.add(a)
        else:
            cut.add((a + b) // 2)
    for r in _bg_runs(bg)[1:]:
        cut.add(r[0])

    c = sorted(cut)
    keep = [c[0]]
    for v in c[1:]:
        if v - keep[-1] >= MIN_SECTION:
            keep.append(v)
    if keep[-1] != H:
        keep[-1] = H
    return [(keep[i], keep[i + 1]) for i in range(len(keep) - 1)]


def _kind(cell, mask):
    if mask.mean() < 0.015:
        return "空"
    px = cell[mask.astype(bool)].astype(np.float32)
    if len(px) < 12:
        return "空"
    var = float(px.std(axis=0).mean())
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    edge = float((cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 60, 160) > 0).mean())
    fill = float(mask.mean())
    if edge > 0.045 and fill < 0.55:
        return "文字"                       # 細い線が多く、面は埋まっていない
    if var > 26 and fill > 0.45:
        return "画像"                       # 面が埋まっていて色がばらける
    if fill > 0.60 and var < 18:
        return "色面"
    if edge > 0.020:
        return "文字"
    return "画像" if var > 20 else "色面"


def extract(path_or_img):
    img = imread(path_or_img) if isinstance(path_or_img, str) else path_or_img
    if img is None:
        return None
    h0, w0 = img.shape[:2]
    img = cv2.resize(img, (W, max(1, int(h0 * W / w0))), interpolation=cv2.INTER_AREA)
    H = img.shape[0]

    bg = _row_bg(img)
    ink = np.linalg.norm(img.astype(np.float32) - bg[:, None, :], axis=2)
    rowfrac = (ink > INK).mean(axis=1)

    secs = []
    for (y0, y1) in _cuts(bg, rowfrac, H):
        strip = img[y0:y1]
        if strip.size == 0:
            continue
        base = np.median(bg[y0:y1], axis=0)
        d = np.linalg.norm(strip.astype(np.float32) - base, axis=2)
        mask = (d > INK).astype(np.uint8)

        blocks = []
        # セクションの中をまず横帯（行）に割る。行を挟まないと、
        # 縦に離れた別物が同じ x にあるだけで1つの塊になってしまう。
        for (a, b) in _runs(mask.mean(axis=1) > EMPTY, ROW_GAP, MIN_ROW):
            band, mband = strip[a:b + 1], mask[a:b + 1]
            for (x0, x1) in _runs(mband.mean(axis=0) > 0.03, COL_GAP, MIN_BLOCK):
                cell, mcell = band[:, x0:x1 + 1], mband[:, x0:x1 + 1]
                ys = np.where(mcell.mean(axis=1) > 0.03)[0]
                if not len(ys):
                    continue
                p, q = int(ys[0]), int(ys[-1])
                blocks.append({
                    "x": round(x0 / W, 3), "w": round((x1 - x0 + 1) / W, 3),
                    "y": round((y0 + a + p) / H, 4), "h": round((q - p + 1) / H, 4),
                    "kind": _kind(cell[p:q + 1], mcell[p:q + 1])})

        secs.append({"y": round(y0 / H, 4), "h": round((y1 - y0) / H, 4),
                     "bg": "#%02x%02x%02x" % (int(base[2]), int(base[1]), int(base[0])),
                     "blocks": blocks})

    return {"aspect": round(H / W, 3), "sections": _absorb(secs)}


def _absorb(secs):
    """中身の無いセクションを隣に吸わせる。

    細い区切り線は MIN_ROW で落ちるので、その線を挟んだ2つの空白が
    「何も入っていないセクション」を作る。それは区切りであって帯ではない。
    """
    out = []
    for s in secs:
        if not s["blocks"] and out:
            out[-1]["h"] = round(s["y"] + s["h"] - out[-1]["y"], 4)
        else:
            out.append(s)
    while len(out) > 1 and not out[0]["blocks"]:
        out[1]["h"] = round(out[1]["y"] + out[1]["h"] - out[0]["y"], 4)
        out[1]["y"] = out[0]["y"]
        out.pop(0)
    return out


def overlay(path, lay, dst):
    img = imread(path)
    h0, w0 = img.shape[:2]
    img = cv2.resize(img, (W, max(1, int(h0 * W / w0))), interpolation=cv2.INTER_AREA)
    H = img.shape[0]
    color = {"文字": (80, 220, 80), "画像": (60, 160, 255),
             "色面": (200, 120, 255), "空": (120, 120, 120)}
    for s in lay["sections"]:
        y0 = int(s["y"] * H)
        cv2.line(img, (0, y0), (W, y0), (0, 0, 255), 2)
        for k in s["blocks"]:
            x0, x1 = int(k["x"] * W), int((k["x"] + k["w"]) * W)
            a, b = int(k["y"] * H), int((k["y"] + k["h"]) * H)
            cv2.rectangle(img, (x0, a), (x1, b), color.get(k["kind"], (255, 255, 255)), 2)
    cv2.imencode(".png", img)[1].tofile(dst)


def _nblocks(lay):
    return sum(len(s["blocks"]) for s in lay["sections"])


def check(path, out=sys.stdout):
    """同じ絵を少し変えて読み直し、同じ構造が出るか見る。

    抽出が揺れるなら、その抽出で測った「似ている／似ていない」は意味を持たない。
    前にセクション検出が地の色の揺れを拾っていたのを見逃したので、常に見る。
    """
    img = imread(path)
    if img is None:
        print("読めない: %s" % path, file=out)
        return None
    h, w = img.shape[:2]
    cases = [
        ("そのまま", img),
        ("0.7倍に縮小", cv2.resize(img, (int(w * .7), int(h * .7)), interpolation=cv2.INTER_AREA)),
        ("1.4倍に拡大", cv2.resize(img, (int(w * 1.4), int(h * 1.4)), interpolation=cv2.INTER_LINEAR)),
        ("明るさ+8", np.clip(img.astype(np.int16) + 8, 0, 255).astype(np.uint8)),
        ("左右2px削る", img[:, 2:w - 2]),
    ]
    res = []
    for name, im in cases:
        lay = extract(im)
        res.append((name, len(lay["sections"]), _nblocks(lay)))
        print("  %-12s セクション %2d ／ 塊 %3d" % (name, res[-1][1], res[-1][2]), file=out)
    sec = [r[1] for r in res]
    blk = [r[2] for r in res]
    # 塊は一致度の土台なので厳しく、セクション数は切れ目1本で変わるので緩く見る
    ok = (max(sec) - min(sec) <= max(1, int(np.mean(sec) * 0.12)) and
          max(blk) - min(blk) <= max(2, int(np.mean(blk) * 0.08)))
    print("  → %s" % ("安定（この抽出で測ってよい）" if ok else
                      "不安定（この抽出で測った数字は信用できない）"), file=out)
    return ok


def _flush(w):
    try:
        w.flush()
    except OSError:                        # head などでパイプを閉じられたとき
        pass


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1

    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    if a[0] == "--check":
        ok = True
        for src in a[1:]:
            print("%s" % os.path.basename(src), file=w)
            _flush(w)
            ok = check(src, w) and ok
        _flush(w)
        return 0 if ok else 2

    src = a[0]
    lay = extract(src)
    if lay is None:
        print("読めない: %s" % src, file=w)
        _flush(w)
        return 1

    print("縦横比 %.2f ／ セクション %d ／ 塊 %d" % (
        lay["aspect"], len(lay["sections"]), _nblocks(lay)), file=w)
    for i, s in enumerate(lay["sections"], 1):
        print("  %2d) y%.3f h%.3f 地%s" % (i, s["y"], s["h"], s["bg"]), file=w)
        for k in s["blocks"]:
            print("      %-4s x%.2f→%.2f  y%.3f h%.3f" % (
                k["kind"], k["x"], k["x"] + k["w"], k["y"], k["h"]), file=w)
    _flush(w)

    if "--out" in a:
        overlay(src, lay, a[a.index("--out") + 1])
        print("overlay -> %s" % a[a.index("--out") + 1], file=w)
    if "--json" in a:
        json.dump(lay, io.open(a[a.index("--json") + 1], "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("json -> %s" % a[a.index("--json") + 1], file=w)
    _flush(w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
