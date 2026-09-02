"""生成のための隔離環境をつくる／片づける。

既存のコードが見えていると、参照画像は数ある入力の1つに薄まる。
「構造を引き継ぐな」と指示しても、見えているものには引っ張られる。
だから物理的に見せない。

隔離環境に入れるのは4つだけ:

    ref-1.png ...   参照画像（並び順そのまま。1枚目が軸）
    content.md      載せる文言（HTMLではなくテキスト）
    axes.md         軸と重み
    brief.json      自由度・案数・読み取れない軸

既存の index.html / styles.css / 過去の案 / 他の適用先は**置かない**。
生成後、できた案だけを `.design/gen/` へ回収する。

    python tools/isolate.py build     隔離環境をつくる（パスを表示）
    python tools/isolate.py collect   できた案を .design/gen/ へ回収する
"""
import io, json, os, re, shutil, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import layout

def work_dir(create=False):
    """作業場は OneDrive の外（システムの一時領域）に置く。

    プロジェクト配下だと同期がファイルを掴んで、掃除も回収も
    WinError 5 で落ちる。作業場は使い捨てなので外に出してよい。
    プロジェクトごとに分けたいので、パスのハッシュで名前を作る。
    """
    import hashlib, tempfile
    tag = hashlib.sha1(paths.project_root().encode("utf-8")).hexdigest()[:10]
    d = os.path.join(tempfile.gettempdir(), "design-dna", tag)
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def _retry(fn, tries=5, wait=0.4):
    """OneDrive やブラウザが一時的にハンドルを掴むことがあるので粘る。"""
    import time
    for i in range(tries):
        try:
            return fn()
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(wait * (i + 1))


# ---------------------------------------------------------------- 文言の抽出

def _text_from_html(path):
    """HTML から文言だけを取り出す。構造は捨てる。"""
    s = io.open(path, encoding="utf-8").read()
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", s, flags=re.S | re.I)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    body = s[s.find("<body"):] if "<body" in s else s
    out, seen = [], set()
    for m in re.finditer(r">([^<>]+)<", body):
        t = re.sub(r"\s+", " ", m.group(1)).strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _godly_fullpage(ref_id):
    """Godly の ref なら、フルページ画像のパスを返す。無ければ None。"""
    if not ref_id.startswith("g"):
        return None
    try:
        rows = json.load(io.open(os.path.join(paths.CANDIDATES, "godly.json"), encoding="utf-8"))
        slug = rows[int(ref_id[1:]) - 1][0]
    except Exception:
        return None
    p = os.path.join(paths.IMAGES, "godly", slug, "desktop-full.webp")
    return p if os.path.exists(p) else None


def _slice(src, out_dir, stem, width=760, chunk=1000):
    """縦に長い画像を、読める高さに切って並べる。"""
    from PIL import Image
    im = Image.open(src).convert("RGB")
    im = im.resize((width, max(1, int(im.height * width / im.width))), Image.LANCZOS)
    names = []
    for k in range((im.height + chunk - 1) // chunk):
        part = im.crop((0, k * chunk, width, min(im.height, (k + 1) * chunk)))
        name = "%s-%d.png" % (stem, k + 1)
        part.save(os.path.join(out_dir, name))
        names.append(name)
    return names


def _entry_page():
    """適用先の入口ページを探す。"""
    root = paths.project_root()
    for name in ("index.html", "index.htm", "public/index.html", "src/index.html"):
        p = os.path.join(root, name.replace("/", os.sep))
        if os.path.isfile(p):
            return p
    return None


def build():
    d = work_dir(create=True)
    # OneDrive やブラウザがハンドルを掴んでいることがある。消せないものは残す。
    for f in os.listdir(d):
        p = os.path.join(d, f)
        try:
            _retry(lambda: shutil.rmtree(p)) if os.path.isdir(p) else _retry(lambda: os.remove(p))
        except OSError:
            print("消せず（掴まれている）: %s" % f, file=sys.stderr)

    picks = json.load(io.open(paths.p("picks.json"), encoding="utf-8"))["picks"]
    req = json.load(io.open(paths.p("request.json"), encoding="utf-8"))

    # 参照画像。並び順を保つ（1枚目が軸）
    from PIL import Image
    refs = []
    for i, p in enumerate(picks):
        n = i + 1
        full = _godly_fullpage(p["id"])
        if full:
            # Godly はフルページがある。構図を読ませたいので縦に切って全部渡す。
            files = _slice(full, d, "ref-%d" % n)
            note = "フルページ（%d分割）。ページ全体の構図が読める" % len(files)
        else:
            src = os.path.join(paths.THUMBS, p["id"] + ".img")
            if not os.path.exists(src):
                print("参照画像が無い: %s" % p["id"], file=sys.stderr)
                continue
            dst = os.path.join(d, "ref-%d.png" % n)
            Image.open(src).convert("RGB").save(dst)
            files = [os.path.basename(dst)]
            note = "ページ上部の切り抜きのみ。全体の構図と密度は写っていない"
        refs.append({"files": files, "id": p["id"], "note": note,
                     "name": p.get("name", ""), "src": p.get("src", ""),
                     "hint": p.get("hint", ""), "primary": i == 0})

        # 軸の参照からは「配置そのもの」を取り出して渡す。
        # 軸のラベル（構図＝左寄せ 等）では元の見た目は復元できないため。
        if i == 0:
            whole = full or os.path.join(paths.THUMBS, p["id"] + ".img")
            lay = layout.extract(whole)
            if lay:
                lay["source"] = p["id"]
                lay["whole_page"] = bool(full)
                json.dump(lay, io.open(os.path.join(d, "layout.json"), "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
                layout.overlay(whole, lay, os.path.join(d, "layout-overlay.png"))

    # 文言。HTML ではなくテキストで渡す
    page = _entry_page()
    lines = _text_from_html(page) if page else []
    brief = ""
    if os.path.exists(paths.p("brief.md")):
        brief = io.open(paths.p("brief.md"), encoding="utf-8").read().strip()

    with io.open(os.path.join(d, "content.md"), "w", encoding="utf-8") as fh:
        fh.write("# 載せる文言（これがすべて。ここに無いものを足さない）\n\n")
        for t in lines:
            fh.write("- %s\n" % t)
        if brief:
            fh.write("\n## この案件について\n\n%s\n" % brief)
        fh.write("\n**ここに無い要素（ナビゲーション、SNSリンク、キャンペーン等）を"
                 "作らないこと。** 材料が少なく見えても、それがこのページの全部。\n")

    shutil.copy(paths.AXES, os.path.join(d, "axes.md"))
    if os.path.exists(paths.p("dna.md")):
        shutil.copy(paths.p("dna.md"), os.path.join(d, "dna.md"))

    json.dump({
        "freedom": req.get("freedom"),
        "released": req.get("released") or [],
        "unreadable": req.get("unreadable") or [],
        "effectiveFreedom": req.get("effectiveFreedom"),
        "variants": req.get("variants") or 1,
        "refs": refs,
        "layout": "layout.json",
    }, io.open(os.path.join(d, "brief.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=1)

    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    print(d, file=w)
    print("  参照 %d枚 / 文言 %d行 / 自由度 %s%%（実質 %s%%）/ %s案" % (
        len(refs), len(lines), req.get("freedom"),
        req.get("effectiveFreedom", req.get("freedom")), req.get("variants")), file=w)
    print("  既存のHTML・CSS・過去の案は置いていない", file=w)
    w.flush()
    return d


# ---------------------------------------------------------------- 回収


def _copy_dir(src, dst):
    """ディレクトリごと消さずに、ファイル単位で上書きする。

    rmtree は掴まれていると WinError 5 で落ちる。案の中身は数ファイルなので
    1つずつ置き換えるほうが確実。
    """
    os.makedirs(dst, exist_ok=True)
    names = set()
    for f in os.listdir(src):
        sp, dp = os.path.join(src, f), os.path.join(dst, f)
        if os.path.isdir(sp):
            _copy_dir(sp, dp)
        else:
            _retry(lambda: shutil.copyfile(sp, dp))
        names.add(f)
    # 今回作られなかったファイルだけ消す
    for f in os.listdir(dst):
        if f not in names:
            p2 = os.path.join(dst, f)
            try:
                shutil.rmtree(p2) if os.path.isdir(p2) else os.remove(p2)
            except OSError:
                pass
    return names


def collect():
    d = work_dir()
    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    if not os.path.isdir(d):
        print("隔離環境が無い。先に build を回すこと。", file=w); w.flush(); return 1

    gen = paths.gen_dir(create=True)
    variants, notes = [], []
    for name in sorted(os.listdir(d)):
        src = os.path.join(d, name)
        # 案は 1文字のディレクトリ（a, b, c …）
        if os.path.isdir(src) and len(name) == 1 and name.isalpha():
            _copy_dir(src, os.path.join(gen, name))
            variants.append(name)
        elif name == "variants.json":
            _retry(lambda: shutil.copyfile(src, os.path.join(gen, name)))
            notes.append(name)
        elif name in ("dna.md", "axis-values.md", "notes.md", "dna-source.json"):
            # 隔離の中で書かれた読み取り結果を持ち帰る
            _retry(lambda: shutil.copyfile(src, paths.p(name)))
            notes.append(name)

    # 今回作られなかった案が gen に残っていたら消す（前回の残骸）
    for name in sorted(os.listdir(gen)):
        if len(name) == 1 and name.isalpha() and name not in variants:
            try:
                shutil.rmtree(os.path.join(gen, name))
                print("前回の残骸を削除: gen/%s" % name, file=w)
            except OSError as e:
                print("残骸を消せず（掴まれている）: gen/%s" % name, file=w)

    print("回収: 案 %s / %s" % (" ".join(variants) or "なし", " ".join(notes) or "なし"), file=w)
    w.flush()
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    sys.exit(collect() if cmd == "collect" else (build() and 0))
