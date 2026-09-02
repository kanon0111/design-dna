"""参照の配置と、生成した案の配置がどれだけ合っているかを測る。

色の一致は palette.py で測れていたが、人が「似ている」と言うときに見ているのは
文字と画像の位置。それを数字にする。

    python tools/layout_diff.py <参照の画像 or layout.json> <案の画像> [<案の画像> ...]

塊（文字/画像/色面のかたまり）どうしを位置で組にして測る。
セクション数はほとんど見ない。切れ目1本の増減で変わるので、
そこに一致度を預けると物差しのほうがぶれる。

出す数字:
  写せた   参照の塊のうち、案の中に対応するものがあった割合
  余計     案の塊のうち、参照に対応するものが無かった割合
  横ずれ   組になった塊の x と幅の差（ページ幅比）
  縦ずれ   組になった塊の y と高さの差（ページ高さ比）
  種類     組になった塊の 文字/画像/色面 が一致した割合
  縦横比   案のページの形。参照とかけ離れていれば配置は合っていない
  一致度   0〜100
"""
import io, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout

FAR = 0.28            # これ以上離れていたら「対応するものは無い」


def _blocks(lay):
    return [b for s in lay["sections"] for b in s["blocks"]]


def _dist(a, b):
    return (abs(a["x"] - b["x"]) + abs(a["w"] - b["w"]) +
            abs(a["y"] - b["y"]) + abs(a["h"] - b["h"])) / 2


def compare(ref, got):
    rb, gb = _blocks(ref), _blocks(got)
    if not rb:
        return None

    # 位置が近い順に1対1で組にする。近いものから取らないと、
    # 参照の塊が全部おなじ1つに吸い寄せられて、ずれが小さく見えてしまう。
    pairs = sorted(((_dist(r, g), i, j) for i, r in enumerate(rb)
                    for j, g in enumerate(gb)), key=lambda t: t[0])
    usedr, usedg, m = set(), set(), []
    for d, i, j in pairs:
        if d > FAR or i in usedr or j in usedg:
            continue
        usedr.add(i); usedg.add(j); m.append((rb[i], gb[j]))

    # 写せた割合（参照のうち再現できた）と、余計に足した割合（参照に無いのに作った）。
    # 片方だけ見ると、中身が少ないページは「短いから低い」、
    # 中身が多いページは「詰め込めば高い」になってしまう。
    recall = len(m) / len(rb)
    prec = len(m) / max(len(gb), 1)
    if m:
        dx = sum(abs(r["x"] - g["x"]) + abs(r["w"] - g["w"]) for r, g in m) / len(m) / 2
        dy = sum(abs(r["y"] - g["y"]) + abs(r["h"] - g["h"]) for r, g in m) / len(m) / 2
        kind = sum(1 for r, g in m if r["kind"] == g["kind"]) / len(m)
    else:
        dx = dy = 1.0
        kind = 0.0

    nr, ng = len(ref["sections"]), len(got["sections"])
    # 縦横比。ページの高さが参照の半分なら、位置を比率で合わせても同じ配置ではない。
    # y を 0〜1 に正規化して測る以上、これを入れないと
    # 「短いページに少しだけ置いたもの」が満点近くまで行ってしまう。
    ar, ag = ref.get("aspect", 0) or 1, got.get("aspect", 0) or 1
    asp = min(ar, ag) / max(ar, ag)

    f1 = 2 * recall * prec / (recall + prec) if (recall + prec) else 0.0
    pos = max(0.0, 1 - (dx * 2.6 + dy * 2.6))
    score = 100 * f1 * pos * asp * (0.75 + 0.25 * kind)

    return {"sections": (nr, ng), "blocks": (len(rb), len(gb)),
            "recall": recall, "prec": prec,
            "dx": dx, "dy": dy, "kind": kind,
            "aspect": (ref.get("aspect", 0), got.get("aspect", 0)),
            "score": max(0.0, min(100.0, score))}


def _load(p):
    if p.lower().endswith(".json"):
        return json.load(io.open(p, encoding="utf-8"))
    return layout.extract(p)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    ref = _load(sys.argv[1])
    if ref is None:
        print("参照が読めない", file=w); w.flush(); return 1
    print("参照: セクション %d ／ 塊 %d ／ 縦横比 %.2f" % (
        len(ref["sections"]), len(_blocks(ref)), ref.get("aspect", 0)), file=w)
    print("", file=w)
    print("%-12s %8s %6s %6s %7s %6s %6s %6s %7s" % (
        "", "塊", "写せた", "余計", "縦横比", "横ずれ", "縦ずれ", "種類", "一致度"), file=w)

    rows = []
    for p in sys.argv[2:]:
        got = _load(p)
        if got is None:
            print("読めない: %s" % p, file=w); continue
        r = compare(ref, got)
        name = os.path.splitext(os.path.basename(p))[0]
        rows.append((name, r))
        print("%-12s %3d→%-4d %5.0f%% %5.0f%% %7.2f %6.3f %6.3f %5.0f%% %7.1f" % (
            name[:12], r["blocks"][0], r["blocks"][1],
            r["recall"] * 100, (1 - r["prec"]) * 100, r["aspect"][1],
            r["dx"], r["dy"], r["kind"] * 100, r["score"]), file=w)

    if len(rows) > 1:
        best = max(rows, key=lambda x: x[1]["score"])
        print("\n参照に一番近い: %s（%.1f）" % (best[0], best[1]["score"]), file=w)
    print("\nずれはページに対する比率。0 に近いほど同じ位置。", file=w)
    try:
        w.flush()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
