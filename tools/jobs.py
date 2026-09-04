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

def _where():
    return (f"参照プール（読むだけ）: {paths.PLUGIN_ROOT}\n"
            f"このプロジェクト       : {paths.project_root()}\n"
            f"書き出し先             : {paths.design_dir()}\n")


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


def assist_prompt(brief):
    return f"""あなたはデザイン参照システムを操作している。

{_where()}
## やること
利用者の作りたいもの: **{brief}**

参照プールの `refs/candidates/`（Godly 18 / Lapa 208 / Awwwards 1、計227件）から、
**基本は1枚**選び、`.design/picks.json` に書く。

**役割（骨格・色・文字）を割り当てない。** 何をどこから借りるかは生成時に決める。
利用者は「こういう感じにしたい」でしか選ばないので、こちらもその粒度で選ぶ。

## 何枚選ぶか
- **既定は1枚。** 1枚なら定義上どの属性も出どころが1つで、混ざりようがない。
- brief に「この要素とこの要素」と読める具体的な要求が**2つ以上**あるときだけ、
  2枚目・3枚目を足す。足した理由を `hint` に短く書く。
- 迷ったら1枚。**増やすほど平均に近づく。**

## 手順
1. 参照プールの `refs/clusters.json` と `refs/metrics.json` を読む。
   clusters は実測値（明度・彩度・コントラスト・色数・密度・余白）による分類。
   id は candidates の並び順に対応する（Godly=g01..g18 / Lapa=l01..l208 / Awwwards=a01）。
2. brief に合いそうな系統を1〜2つに絞り、その中から**候補を5件程度**に絞る。
3. 絞った候補は参照プールの `cache/thumbs/<id>.img` を実際に **Read で見る**
   （拡張子は .img だが中身は画像。Read で表示できる）。見ずに決めない。
   ファイルが無ければ `python tools/fetch_thumbs.py` で取得できる。
4. **構図まで似せたい brief なら GODLY を優先する。**
   Lapa / Awwwards は手元にヒーロー切り抜き（756x1000）しか無く、
   ページ全体の構図が読めない。Lapa を1枚目にするなら、構図は借りられないと承知で選ぶ。
5. `.design/picks.json` を次の形で**上書き**する。**並び順が意味を持ち、先頭が軸**。

```json
{{"picks":[
 {{"id":"g08","src":"GODLY","name":"Pryzm",
  "site":"https://pryzm.design/","thumb":"https://cdn.godly.design/sites/pryzm/thumbnail.webp",
  "by":"ai","reason":"40字程度で、実物のどこを見てそう判断したか","hint":""}}
]}}
```

`src` / `name` / `site` / `thumb` は candidates の各 json から正確に引く。
thumb の作り方: Godly=`https://cdn.godly.design/sites/{{slug}}/thumbnail.webp`、
Lapa=`https://cdn.lapa.ninja/assets/images/2x/{{imageSlug}}-thumb.{{ext}}`、
Awwwards=json の2番目の要素。

## 重要
- `"by":"ai"` を必ず付ける。これが付いている間は「未確定の提案」として扱われ、
  利用者が承認して初めて確定する。
- `reason` は必須。実物を見た上での判断を書く。一般論を書かない。
- 候補227件の外から選ばない。
- **無理に複数枚選ばない。** 1枚で足りるなら1枚。
- 参照プール側のファイルは**書き換えない**。書き込みは `.design/` の中だけ。
- 最後に、選んだ枠を1行ずつ日本語で簡潔に報告する。それ以外は出力しない。
"""


def _dna_line():
    state, ids = dna_state()
    who = "／".join(ids) if ids else "なし"
    return f"{state}（いまの参照: {who}）"


def generate_prompt():
    """隔離環境の中で走る前提のプロンプト。参照プールもプロジェクトも見えない。"""
    return """このディレクトリにある材料だけで、1ページのWebページを作る。
**ここに無いものは存在しない。** 他のディレクトリを探しに行かない。

材料:
  layout.json        参照の**配置**。これが一番大事
  layout-overlay.png 配置の検出結果を参照画像に描いたもの（目で確かめる用）
  ref-1-*.png        参照デザインの実物（ref-1 が軸。複数枚ならページを縦に切ったもの）
  content.md         載せる文言。これがすべて
  axes.md            軸と重み
  brief.json         自由度・案数・読み取れない軸・文言が足りているか
  dna.md             （あれば）前に抽出した不変条件

## 自由度は「配置をどれだけ動かしてよいか」

`layout.json` は参照のセクションとブロックを**比率**で持っている
（`x` `w` `y` `h` はページ幅・高さに対する 0〜1）。

    自由度  0-10%   複製。座標をそのまま使い、中身だけ差し替える。
                    参照と並べて見分けがつかないところまで持っていく。案は1つ
    自由度 15-35%   セクションの数と順序、塊の左右関係は保つ。
                    x と w のずれは ±0.05 まで
    自由度 40-70%   セクションの数は保つが、中の配置は組み替えてよい
    自由度 75-100%  配置は自由。参照は雰囲気の参考

`brief.json` の `freedom` を見て、対応する縛りで作る。
**これが「似ている」の中身**であって、軸のラベル（構図＝左寄せ 等）ではない。
軸のラベルは4択の要約でしかなく、そこから元の見た目は復元できない。

## 自由度が 10% 以下のときにやること

これは「参考にする」ではなく**複製**。次を全部やる。

- `layout.json` の塊を1つ残らず置く。`x` `w` `y` `h` はそのまま使う
- 参照でページ幅いっぱいに散らしてある画像は、案でも同じ位置に同じ大きさで散らす。
  まとめて1列に並べ直さない
- 参照で中央に置かれている文字は、案でも中央に置く。左寄せにしない
- セクションの地の色（`bg`）と、ページ全体の縦横比（`aspect`）も合わせる
- 色・書体・角の丸み・影も参照に寄せる

**文言が足りないとき**（`brief.json` の `contentShort` が true）は、
上から順に埋められるところまで作り、**足りなくなった以降のセクションは丸ごと落とす**。
セクションを残したまま中を空にしない。骨格だけ残って中身が空のページは、
短くても中身の詰まったページより参照から遠い。

## 手順

1. **layout.json を読み、layout-overlay.png と ref-1-*.png を Read で見る。**
   検出が実物と合っているか自分の目で確かめる。ずれていたら実物を優先する。
2. `content.md` の文言を、layout の各ブロックに割り当てる。
   - `kind` が `文字` のブロックには文字を置く
   - `kind` が `画像` のブロックには画像を置く。素材が無いので
     インラインSVGか CSS で、参照のその位置にあるものの**役割**を果たすものを作る
   - `kind` が `色面` のブロックはベタの面。無理に何か置かない
   - 文言が足りなければブロックを減らす。**content.md に無いものを作らない**
3. セクションの地の色は `layout.json` の `bg` を使う。
4. `axis-values.md` に、参照から読み取った値と根拠を書く（全7軸）。
   読み取れない軸は「読み取れず」と正直に書く。
5. `brief.json` の `variants` の数だけ `a/`, `b/`, `c/` … に
   `index.html` と `styles.css` を書く。
   - `variants` が 1 のときは `a/` だけ。無理に案を増やさない
   - 2つ以上のときは、自由度の範囲内で**案ごとに違うずらし方**をする。
     全案が同じ配置になったら、案を分けた意味がない。
   - 各 css の冒頭に、参照の配置をどう使い、どこをどれだけずらしたかを書く。
   - 和文の折り返しに `ch` を使わない。`em` を使う。
   - 幅は 1280px 基準で作る（比較画面がこの幅で撮る）。
6. `variants.json` を書く。

   ```json
   {"variants":[
    {"id":"a","label":"何を振ったか一言","released":"…","fixed":"…",
     "note":"配置をどう使ったか","freedom":30}
   ]}
   ```

## 重要
- **配置を守ることが最優先。** 色や書体より先に、まず物の位置を合わせる。
- 参照画像と content.md 以外に情報源は無い。記憶で補わない。
- 出力は最後に、各案が参照の配置をどう扱ったかを1行ずつ。それ以外は出力しない。
"""
