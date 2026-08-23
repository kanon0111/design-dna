"""picker のボタンから Claude Code を headless (`claude -p`) で起動する。

これが無いと「依頼を書き出しました」で止まり、利用者はチャットへ移って
続きを頼む必要があった。ボタンだけで完結させるためのもの。

注意: 実際に Claude Code を走らせるので利用量を消費する。
プロンプトはプラグイン側（参照・軸）とプロジェクト側（.design/）の
両方を触るので、--add-dir に両方を渡す。
"""
import os, shutil, subprocess, sys, threading, time

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


def _run(name, prompt, tools, timeout):
    _set(name, status="running", started=time.time(), message="Claude Code を起動中…")
    cmd = [CLAUDE, "-p",
           "--allowedTools", *tools,
           "--permission-mode", "acceptEdits",
           "--add-dir", paths.PLUGIN_ROOT,
           "--add-dir", paths.project_root()]
    try:
        r = subprocess.run(cmd, input=prompt, cwd=paths.project_root(), timeout=timeout,
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


def start(name, prompt, tools, timeout=900):
    """同名のジョブが動いていれば拒否する。"""
    with _lock:
        cur = JOBS.get(name)
        if cur and cur.get("status") == "running":
            return False, "すでに実行中です"
    if not available():
        return False, "claude コマンドが見つかりません"
    threading.Thread(target=_run, args=(name, prompt, tools, timeout), daemon=True).start()
    return True, "開始しました"


# ---------------------------------------------------------------- プロンプト

def _where():
    return (f"参照プール（読むだけ）: {paths.PLUGIN_ROOT}\n"
            f"このプロジェクト       : {paths.project_root()}\n"
            f"書き出し先             : {paths.design_dir()}\n")


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


def generate_prompt():
    return f"""あなたはデザイン参照システムを操作している。

{_where()}
## やること
`.design/request.json`（自由度・案数・適用先）と `.design/picks.json`（選ばれた ref）に
従って、このプロジェクトのデザイン案を生成する。

## 手順
1. 参照プールの `axes.md` を読む。軸と重み、そして**ルール4**（DNAに軸の値を書かない）を守る。
2. `.design/dna.md` を読む。未抽出なら、picks の ref の実物画像を見て抽出し、書く。
   - Godly の ref は参照プールの `cache/images/godly/<slug>/desktop-full.webp` にフルページがある。
     縦に長いので PIL で4分割して `.design/_slices/` に出してから Read で見る。
   - Lapa / Awwwards の ref は `cache/thumbs/<id>.img` のみ
     （756x1000 のヒーロー切り抜き。**ページ全体の構図は写っていない**）。
   - DNA には**方針だけ**書く。「左寄せ」「ダーク」のような軸の値を書かない（ルール4）。
   - 両方の ref に**共通して**現れた方針だけを不変条件にする。
   - 「借りない部分」も明記する。ref 固有の芸を移植すると滑るため。

3. **`.design/axis-values.md` を書く。これが無いと「固定」が機能しない。**
   `axes.md` の全7軸について、参照から**実際に読み取れた値**を1行ずつ書く。

   `picks.json` は**並び順だけ**を持つ（先頭が軸）。役割は割り当てられていないので、
   **どの軸をどの参照から取るかはあなたが決める**。決めた結果を「出どころ」に記録する。

   ```
   | 軸 | 値 | 出どころ | 根拠 |
   |---|---|---|---|
   | 構図 | 左寄せ非対称 | l134 | ヒーローの見出しが左の柱に揃い、被写体が右 |
   | 地の明度 | ライト基調 | l162 | hint に「この生成りが欲しい」とあったため |
   | 主役 | 読み取れず | — | ヒーロー切り抜きのみで、ページ全体の主従が判断できない |
   ```

   **1つの軸に2つの参照を混ぜない**（`axes.md` ルール7）。混ぜた瞬間に平均になる。
   どちらか一方を選び、選んだ理由を根拠に書く。
   2枚目以降に `hint` があれば、その軸はその参照から取る。

   **読み取れない軸に推測で値を入れない。**「読み取れず」と正直に書く。
   ヒーロー切り抜きしか無い ref から構図や密度を断定しないこと。

4. 案を生成する。`request.json` の `variants` の数だけ、`.design/gen/a/`, `b/`, `c/` … に
   `index.html` と `styles.css` を書く。

   **文言は引き継ぐ。構造は引き継がない。**
   - 適用先のページから**文言だけ**を取る（店名・見出し・本文・住所など）。
     ダミーテキストにしない。
   - **既存ページの DOM 構造をなぞらない。** セクションの順序、見出しの階層、
     リストの組み方は、軸が決めること。元のページと同じ骨格になったら失敗と思うこと。

   **「固定」は「触らない」ではない。「参照の値を再現する」である。**
   - 固定された軸は、`axis-values.md` に書いた**参照の値を積極的に適用する**。
     手をつけずに放置すると元ページの値が残り、自由度を下げるほど参照ではなく
     元デザインに近づくという逆転が起きる。
   - 値が「読み取れず」の軸は**固定できない**。その軸は案ごとに違う値を選び、
     `variants.json` の `note` に「参照から読み取れなかったので案ごとに変えた」と書く。

   - `axes.md` のルール2に従い、**案ごとに解放する軸をずらす**。
     自由度の予算内で別の組合せに割り当て直す。全案で同じ軸を動かすと似た案が並ぶ。
   - 各 css の冒頭に、その案で解放した軸と固定した軸をコメントで書く。
   - 和文の折り返しに `ch` を使わない（欧文基準で幅が足りない）。`em` を使う。
   - 画像素材が無ければ、色調を ref に寄せた CSS のプレースホルダを置く。
   - **前回の生成物が `gen/` に残っていたら、今回作らない案のディレクトリは削除する。**
5. `.design/gen/variants.json` を書く。比較画面はここを読んで見出しと説明を出す。

```json
{{"variants":[
 {{"id":"a","label":"地の明度をライト基調へ振る",
  "released":"装飾2＋階層4＋コントラスト9＋密度15＋地の明度20＝50",
  "fixed":"構図・主役",
  "note":"地を反転してライト基調に。黒は営業時間の帯だけ。","freedom":50}}
]}}
```

`id` は `gen/` 配下のディレクトリ名と一致させる。`label` はその案が
**何を振ったか**が分かる短い言葉にする。
6. `.design/ledger.md` に今回の行を追記する（id / 自由度 / 解放した軸 / 参照ref）。

## 重要
- 生成した案は必ず `.design/gen/<x>/index.html` として実際に開ける状態にする
  （サーバは `/gen/<x>/` で配信する）。
- 参照プール側のファイルは**書き換えない**。書き込みは `.design/` の中だけ。
- 最後に、各案が「何を振ったか」を1行ずつ日本語で簡潔に報告する。それ以外は出力しない。
"""
