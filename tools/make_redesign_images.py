"""picker 自身のデザイン案（web/_redesign/）で使う画像を作り直す。

参照サムネの縮小版なのでリポジトリには含めない（他サイトのスクリーンショット）。
`fetch_thumbs.py` でキャッシュを埋めたあと、これを走らせると復元できる。
"""
import io, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

OUT = os.path.join(paths.WEB, "_redesign")
WIDTH = 340

# 各系統の代表1件と、picker のモックで使う2件
PICKS = ["l134", "l162"]


def main():
    from PIL import Image

    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    if not os.path.isdir(paths.THUMBS):
        print("サムネのキャッシュがありません。先に fetch_thumbs.py を回してください。", file=w)
        w.flush(); return 1

    clusters = json.load(io.open(paths.CLUSTERS, encoding="utf-8"))["clusters"]
    jobs = [(c["members"][0], "cat%d" % (i + 1)) for i, c in enumerate(clusters)]
    jobs += [(pid, "pick%d" % (i + 1)) for i, pid in enumerate(PICKS)]

    os.makedirs(OUT, exist_ok=True)
    made, missing = 0, []
    for pid, name in jobs:
        src = os.path.join(paths.THUMBS, pid + ".img")
        if not os.path.exists(src):
            missing.append(pid); continue
        im = Image.open(src).convert("RGB")
        im = im.resize((WIDTH, int(im.height * WIDTH / im.width)), Image.LANCZOS)
        # カード表示は object-position:top なので上部だけ使う
        im = im.crop((0, 0, WIDTH, min(im.height, int(WIDTH * 4 / 3))))
        dst = os.path.join(OUT, name + ".jpg")
        im.save(dst, "JPEG", quality=72, optimize=True)
        made += 1
        print("%-6s %-5s %dx%d  %dKB" % (name, pid, im.width, im.height,
                                         os.path.getsize(dst) // 1024), file=w)
    print("\n%d 枚 -> %s" % (made, os.path.relpath(OUT, paths.PLUGIN_ROOT)), file=w)
    if missing:
        print("キャッシュに無かった: %s" % " ".join(missing), file=w)
    w.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
