"""picker.html の <style> ブロックを、別ファイルのスタイルで丸ごと差し替える。

クラス名と DOM 構造は触らない（JS がそのまま動くように）。
見た目の方向を変えるときはこのスクリプトで入れ替える。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import io, os, sys

TARGET = paths.PICKER


def main():
    part = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        paths.WEB, "_redesign", "picker.css.part")
    new = io.open(part, encoding="utf-8").read().strip()
    html = io.open(TARGET, encoding="utf-8").read()

    i = html.find("<style>")
    j = html.find("</style>")
    if i < 0 or j < 0:
        raise SystemExit("picker.html に <style> ブロックが見つからない")
    j += len("</style>")

    # <style> の直前に <link> が残っていれば一緒に差し替える
    link = html.rfind("<link rel=\"stylesheet\"", 0, i)
    if link >= 0 and html[link:i].strip().endswith(">"):
        i = link

    out = html[:i] + new + html[j:]
    io.open(TARGET, "w", encoding="utf-8").write(out)

    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    print("%s -> picker.html （%d文字 -> %d文字）" % (
        os.path.basename(part), j - i, len(new)), file=w)
    w.flush()


if __name__ == "__main__":
    main()
