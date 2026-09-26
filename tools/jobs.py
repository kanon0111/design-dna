"""picker のボタンから Claude Code を headless (`claude -p`) で起動する。

これが無いと「依頼を書き出しました」で止まり、利用者はチャットへ移って
続きを頼む必要があった。ボタンだけで完結させるためのもの。

注意: 実際に Claude Code を走らせるので利用量を消費する。
プロンプトはプラグイン側（参照・軸）とプロジェクト側（.design/）の
両方を触るので、--add-dir に両方を渡す。
"""
import json, os, shutil, subprocess, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

CLAUDE = shutil.which("claude") or os.path.expanduser(r"~\.local\bin\claude.exe")

# name -> {"status": running|done|error, "started": float, "message": str}
JOBS = {}
_lock = threading.Lock()


def available():
    return bool(CLAUDE and os.path.exists(CLAUDE))


def status(name):
    with _lock:
        return dict(JOBS.get(name) or {"status": "idle"})


def _set(name, **kw):
    with _lock:
        JOBS.setdefault(name, {})
        JOBS[name].update(kw)


def _run(name, prompt, tools, timeout, sandbox=None, after=None):
    """sandbox が指定されたら、そのディレクトリ**だけ**を見せて走らせる。

    既存のコードが見えていると参照画像は数ある入力の1つに薄まるので、
    生成のときは物理的に隔離する。after は終了後に呼ぶ後片づけ（回収）。
    """
    _set(name, status="running", started=time.time(), message="Claude Code を起動中…")
    where = sandbox or paths.project_root()
    dirs = [sandbox] if sandbox else [paths.PLUGIN_ROOT, paths.project_root()]
    cmd = [CLAUDE, "-p",
           "--allowedTools", *tools,
           "--permission-mode", "acceptEdits"]
    for d in dirs:
        cmd += ["--add-dir", d]
    try:
        r = subprocess.run(cmd, input=prompt, cwd=where, timeout=timeout,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            _set(name, status="error",
                 message=(r.stderr or r.stdout or "終了コード %d" % r.returncode)[-400:])
        else:
            _set(name, status="done", message=(r.stdout or "").strip()[-600:])
    except subprocess.TimeoutExpired:
        _set(name, status="error", message="時間切れ（%d秒）" % timeout)
    except Exception as e:
        _set(name, status="error", message=str(e)[:400])
    if after:
        try:
            after()
        except Exception as e:
            _set(name, status="error", message="回収に失敗: %s" % str(e)[:200])


def start(name, prompt, tools, timeout=900, sandbox=None, after=None):
    """同名のジョブが動いていれば拒否する。"""
    with _lock:
        cur = JOBS.get(name)
        if cur and cur.get("status") == "running":
            return False, "すでに実行中です"
    if not available():
        return False, "claude コマンドが見つかりません"
    threading.Thread(target=_run, args=(name, prompt, tools, timeout, sandbox, after),
                     daemon=True).start()
    return True, "開始しました"


# ---------------------------------------------------------------- プロンプト

def _ids(path, key="picks"):
    try:
        with open(path, encoding="utf-8") as fh:
            return [p.get("id") for p in (json.load(fh).get(key) or [])]
    except Exception:
        return None


def dna_state():
    """DNA が今の参照から作られたものかを判定する。

    「未抽出なら抽出する」だけだと、参照を選び直しても古い DNA が残り、
    前の参照の読みで生成されてしまう。判定は Python 側でやる
    （AI に自己申告させると静かに間違う）。迷ったら取り直す側に倒す。
    """
    if not os.path.exists(paths.p("dna.md")):
        return "未抽出", []
    now = _ids(paths.p("picks.json")) or []
    was = _ids(paths.p("dna-source.json"))
    if was is None:
        return "由来不明", now
    if was != now:
        return "古い", now
    return "最新", now


def _dna_line():
    state, ids = dna_state()
    who = "／".join(ids) if ids else "なし"
    return f"{state}（いまの参照: {who}）"


def generate_prompt():
    """隔離環境の中で走る前提のプロンプト。参照プールもプロジェクトも見えない。"""
    return """このディレクトリにある材料だけで、Webページの案を作る。
**ここに無いものは存在しない。** 他のディレクトリを探しに行かない。

材料:
  layout.json        参照の**配置**。一番大事
  layout-overlay.png 配置の検出結果を参照画像に描いたもの（目で確かめる用）
  ref-1-*.png        参照デザインの実物（ref-1 が軸。複数枚ならページを縦に切ったもの）
  content.md         載せる文言。これがすべて。`#` `##` `###` がそのまま階層
  polish.md          仕上げの決まり。**寸法は参照から写さず、内容の役割から決める**
  shoot.py           できた案を描画して撮り、文字サイズを測る
  axes.md            軸と重み
  brief.json         案数・文言が足りているか・画面の分け方・参照の素材（refs）
  dna.md             （あれば）前に抽出した不変条件

## 参照から借りるもの、借りないもの

借りるのは参照の**配置と性格**（物の位置関係、色、書体の組み合わせ、装飾、階層の跳ね方）。
**寸法は借りない。** 参照で飾りだった 10px のラベルにこちらの節の題名を入れたり、
参照で1語だった大見出しの枠にこちらの箇条書きを流し込んだりしない。
文字の大きさ・余白の値・行の長さは polish.md に従って、content.md の階層から決める。
これはどの案でも守る。

## 案は2つ。寄せる方向を変える

`layout.json` は参照のセクションとブロックを**比率**で持っている
（`x` `w` `y` `h` はページ幅・高さに対する 0〜1）。
どちらの案も、参照の**性格**（色、書体の組み合わせ、装飾、階層の跳ね方、地と文字の明暗）は
同じだけ借りる。違うのは**配置をどこまで参照に合わせるか**だけ。

**案a — 参照の配置に近づける**
- layout.json の位置関係をそのまま使う。塊の置き方・散らし方・中央か左かの揃え・
  地の色まで参照に合わせる。まとめて1列に並べ直したり、中央のものを左寄せにしたりしない
- 内容に合わせて変えるのは、寸法（polish.md）と、入りきらない分を同じ組み方で繰り返すことだけ

**案b — 雰囲気のまま、内容が読みやすい組み方にする**
- 性格は案aと同じ。配置は、その画面の内容が一番伝わる組み方に組み替える
  （メンバーなら顔ぶれが一覧できる、取組みなら3件を見比べられる、など）
- 組み替えても、参照にある組み方の語彙（色面の敷き方、罫線、非対称の余白、飾りの置き方）で組む。
  よくあるカードの並びに置き換えない

`brief.json` の `refs` の `note` が「ページ上部の切り抜きのみ」なら、参照から読めるのは
上の方の組み方だけ。2画面目以降は、その語彙を広げて組む。

## 画面の分け方（brief.json の structure）

**`pages`（既定）: 画面を切り替える。** 縦に長い1本にしない。

- 画面は `brief.json` の `pages` の通りに分ける（`id` と `label` と、その画面に入れる
  content.md の見出し）。`pages` が空なら content.md の `##` を単位に、短いものは隣とまとめて
  4〜6画面にする。**案ごとに画面の分け方を変えない**（比べるのは見た目のほう）
- 参照の layout.json のセクションを、画面に割り当てる。1画面目は参照の最初のセクション
  （ヒーロー）の配置。2画面目以降は参照の後ろのセクションの組み方を順に使い、足りなければ
  同じ組み方を繰り返す。**文言は1つも落とさない**
- 1つの HTML の中で切り替える。各画面は `<section class="page" id="…">`。
  見えるのは1つだけで、URL の `#id` で切り替わり、ブラウザの戻る・進むが効き、
  `index.html#id` を直接開いてもその画面が出る。切り替えたら先頭へ戻し、見出しにフォーカス
- どの画面からでも他の画面に行けるナビを常に出し、今いる画面を示す。
  各画面の終わりに次の画面へのボタン。ナビとボタンの見た目は参照の中の要素から借りる
- 切り替えは 0.3 秒前後の短いもの。`prefers-reduced-motion` のときは動かさない
- JS が無くても全画面が縦に並んで読める（`<html>` に `js` クラスが付いたときだけ隠す）
- 各画面は 1〜1.5 画面分の高さに収める努力をする（polish.md の 5）

**`scroll`: 縦に1本。** 画面の切り替えは作らない。

## 手順

1. **layout.json を読み、layout-overlay.png と ref-1-*.png を Read で見る。**
   検出が実物と合っているか自分の目で確かめる。ずれていたら実物を優先する。
2. **polish.md を読む。**
3. content.md の文言を、画面と layout のブロックに割り当てる。
   - `kind` が `文字` のブロックには文字、`画像` のブロックには画像を置く。
     画像は素材が無いので、インラインSVGか CSS で、参照のその位置にあるものの**役割**を果たすものを作る
   - `kind` が `色面` のブロックはベタの面。無理に何か置かない
   - **どのブロックに入れても、文字の大きさはその文言の階層で決める**（polish.md の 1）
4. `axis-values.md` に、参照から読み取った値と根拠を書く（全7軸）。
   読み取れない軸は「読み取れず」と正直に書く。
5. `brief.json` の `variants` の数だけ `a/`, `b/`, `c/` … に
   `index.html` と `styles.css`（画面を切り替えるなら `script.js` も）を書く。
   - a は参照の配置に近づけ、b は内容に合わせて組み替える（上の「案は2つ」）。
   - 各 css の冒頭に、参照の配置をどう使い、どこを内容に合わせて変えたかを書く。
   - 和文の折り返しに `ch` を使わない。`em` を使う。
   - 1280px 幅を基準に作り、390px 幅でも崩れないようにする。
6. **案ごとに描画して見て直す。** polish.md の「見て直す」の通り:

   ```
   python shoot.py a/index.html shots/a
   ```

   「小さすぎる」「本文なのに小さい」を 0 件にし、撮った画像を Read で見て
   polish.md の 1〜5 に反していないか確かめる。直したら撮り直す。最大3周。
   `shots/` は確認用なので消さなくてよい（回収されない）。
7. `variants.json` を書く。

   ```json
   {"variants":[
    {"id":"a","label":"参照の配置に近い（一言で特徴）",
     "note":"配置をどう使い、内容に合わせて何を変えたか",
     "pages":[{"id":"home","label":"トップ"},{"id":"team","label":"チーム"}]}
   ]}
   ```

   `pages` は画面を切り替える案のときだけ。画面の id と、ナビに出している名前。

## 重要
- **配置と性格を守り、寸法は内容から決める。** 物の位置関係を合わせたうえで、
  文字と余白は polish.md で仕上げる。写しただけで読めないページは失敗。
- 参照画像と content.md 以外に情報源は無い。記憶で補わない。
- 出力は最後に、各案が参照の配置をどう扱ったかと、見て直したことを1行ずつ。それ以外は出力しない。
"""


PAGES = """## ページの構成: 画面を切り替える

縦に1本スクロールさせるのではなく、**画面（ページ）を切り替えて見せる**。

- 採用案がすでに画面を切り替える作り（`<section class="page">`）なら、その分け方とナビをそのまま使う
- 縦に長い1本の案なら、content.md の `##` を単位に画面を分ける（短いものは隣とまとめて4〜6画面）。
  1画面目は `#` の見出しとリード文。デザインは採用案から持っていき、**並べ方だけ**を変える
- 1つの HTML の中で切り替える。各画面は `<section class="page" id="英小文字の名前">`。
  見えるのは1つだけ。URL の `#名前` で切り替え、ブラウザの戻る・進むが効き、
  `index.html#名前` を直接開いてもその画面が出る
- どの画面からでも他の画面に行けるナビを常に出し、いまどこにいるかを示す。
  各画面の終わりに次の画面へのボタンを置く
- 切り替えは採用案の雰囲気に合う短いもの（0.3秒前後）。`prefers-reduced-motion` のときは動かさない。
  切り替えたら画面の先頭に戻し、フォーカスを見出しに移す
- ナビやボタンの見た目は、採用案の中にある見出し・リンク・ボタン・ラベルから借りる。新しい部品を発明しない
- JavaScript が動かなくても全部の画面が縦に並んで読めるようにする
  （`<html>` に `js` クラスが付いたときだけ、見えていない画面を隠す）
"""

SCROLL = """## ページの構成: 縦に1本

上から下へスクロールして読む1枚にする。画面の切り替えは作らない。
"""


def implement_prompt(d):
    """採用案から本番のページを作る。プロジェクトの中で走る（隔離しない）。

    チャットに戻らずにボタンだけで完結させるので、チャットで話した内容は
    brief.md / content.md に書かれているものが全て。書く場所は serve.py が先に決めて渡す
    （既存ファイルを上書きしない判定を AI に任せない）。

    前は「作り直さない・整えない」だけを言っていたため、案の寸法の粗さ
    （題名 11px・本文 13px）がそのまま本番に出た。いまは性格を守って寸法を磨かせ、
    描画して見て直させる。
    """
    v = str(d.get("variant", ""))
    out = d.get("out", "index.html")
    layout = SCROLL if d.get("structure") == "scroll" else PAGES
    shots = os.path.join(paths.design_dir(), "shots")
    return f"""採用されたデザイン案で、本番のページを作る。

このプロジェクト       : {paths.project_root()}
採用案                 : {os.path.join(paths.gen_dir(), v)}（案{v.upper()}「{d.get("label", "")}」）
書く場所               : {os.path.join(paths.project_root(), out)}
仕上げの決まり         : {paths.POLISH}

## 材料

| | |
|---|---|
| デザイン | `.design/gen/{v}/` の index.html と css・js（採用案） |
| 何をどう振ったか | `.design/gen/variants.json` の案{v}、`.design/axis-values.md` |
| 何を作るか | `.design/brief.md` |
| 載せる内容 | `.design/content.md`（無ければ採用案の文言をそのまま使う）。`#` `##` `###` が階層 |

## やること

1. 採用案と polish.md を読む。採用案は利用者が選んだデザイン。
   polish.md の「変えない」（色・書体の組み合わせ・装飾・構図の考え方・階層の跳ね方の性格）は
   **そのまま持っていく**。一般的な形に直すと平均に戻り、この仕組みの意味がなくなる。
2. 案で落ちた内容を戻す。content.md にあって案に無いものは、**採用案の中にある
   同じ型のセクション・ブロックを繰り返して**足す。新しい見た目を発明しない。
   content.md に無いものは足さない。
3. **磨く。** 案は参照を写した段階なので、寸法が粗いことがある。polish.md の「決め直す」
   （階層・余白・揃え・読みやすさ・1画面に収める）に従って直す。
   特に、節の題名が小さなラベルだけになっている・箇条書きが題名より大きい・
   本文やナビが 12px を切っている、は必ず直す。
4. 本番として足りないものを直す。仮の文言や `#` だけのリンク、画像の代替テキスト。
5. 下の「ページの構成」に従って組む。
6. `{out}` に書く。CSS（と JS）は同じディレクトリに置き、HTML から相対パスで読む。
   **既にあるファイルは上書きしない。** 名前がぶつかるなら
   `{os.path.splitext(os.path.basename(out))[0]}.css` のように変える。
7. **描画して見て直す。**

   ```
   python "{paths.SHOOT}" "{os.path.join(paths.project_root(), out)}" "{shots}"
   ```

   「小さすぎる」「本文なのに小さい」を 0 件にし、撮った画像を Read で見て
   polish.md に反していないか確かめる。直したら撮り直す。最大3周。
8. 書き込んでよいのは上の HTML と CSS・JS と `{shots}` だけ。
   `.design/` のほかのファイルと参照プールは読むだけ。

{layout}
## 出力

最後に、どう画面を分けたか、採用案から何を足したか・磨いたか（何を何pxにした等）を3行以内で。
それ以外は出力しない。
"""
