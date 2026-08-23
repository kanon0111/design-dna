"""picker のボタンから Claude Code を headless (`claude -p`) で起動する。

これが無いと「依頼を書き出しました」で止まり、利用者はチャットへ移って
続きを頼む必要があった。ボタンだけで完結させるためのもの。

注意: 実際に Claude Code を走らせるので利用量を消費する。
"""
import json, os, shutil, subprocess, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REFS = os.path.join(ROOT, "design-system", "refs")

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
           "--add-dir", ROOT]
    try:
        r = subprocess.run(cmd, input=prompt, cwd=ROOT, timeout=timeout,
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

def assist_prompt(brief):
    return f"""あなたはこのリポジトリのデザインシステムを操作している。

## やること
利用者の作りたいもの: **{brief}**

`design-system/refs/candidates/` の候補（Godly 18 / Lapa 208 / Awwwards 1、計227件）から、
以下の3枠に入れる ref を選び、`design-system/refs/picks.json` に書く。

| 枠 | 借りるもの | 必須 |
|---|---|---|
| 骨格 | 構図・余白のリズム | **必須** |
| 色 | 配色のロジック | 任意 |
| 文字 | タイポの態度 | 任意 |

## 手順
1. `design-system/refs/clusters.json` と `metrics.json` を読む。
   clusters は実測値（明度・彩度・コントラスト・色数・密度・余白）による分類。
   id は candidates の並び順に対応する（Godly=g01..g18 / Lapa=l01..l208 / Awwwards=a01）。
2. brief に合いそうな系統を1〜2つに絞り、その中から**候補を5件程度**に絞る。
3. 絞った候補は `design-system/refs/thumbs/<id>.img` を実際に **Read で見る**
   （拡張子は .img だが中身は画像。Read で表示できる）。見ずに決めない。
4. 3枠を決める。骨格は必須、色と文字は「明確に借りたいものがある時だけ」入れる。
   無理に3枠埋めない。
5. `design-system/refs/picks.json` を次の形で**上書き**する。

```json
{{"picks":[
 {{"role":"骨格","id":"g08","src":"GODLY","name":"Pryzm",
  "site":"https://pryzm.design/","thumb":"https://cdn.godly.design/sites/pryzm/thumbnail.webp",
  "by":"ai","reason":"40字程度で、実物のどこを見てそう判断したか"}}
]}}
```

`src` / `name` / `site` / `thumb` は candidates の各 json から正確に引く。
thumb の作り方: Godly=`https://cdn.godly.design/sites/{{slug}}/thumbnail.webp`、
Lapa=`https://cdn.lapa.ninja/assets/images/2x/{{imageSlug}}-thumb.{{ext}}`、
Awwwards=json の2番目の要素。

## 重要
- `by":"ai"` を必ず付ける。これが付いている間は「未採用の提案」として扱われ、
  利用者が承認して初めて確定する。
- `reason` は必須。実物を見た上での判断を書く。一般論を書かない。
- 候補227件の外から選ばない。
- 最後に、選んだ3枠を1行ずつ日本語で簡潔に報告する。それ以外は出力しない。
"""


def generate_prompt():
    return """あなたはこのリポジトリのデザインシステムを操作している。

## やること
`design-system/refs/request.json`（自由度・案数・適用先）と
`design-system/refs/picks.json`（選ばれた ref）に従って、デザイン案を生成する。

## 手順
1. `design-system/axes.md` を読む。軸と重み、そして**ルール4**（DNAに軸の値を書かない）を守る。
2. `design-system/dna.md` を読む。未抽出なら、picks の ref の実物画像を見て抽出し、書く。
   - Godly の ref は `design-system/refs/images/godly/<slug>/desktop-full.webp` にフルページがある。
     縦に長いので PIL で4分割して `refs/_slices/` に出してから Read で見る。
   - Lapa の ref は `design-system/refs/thumbs/<id>.img` のみ（756x1000 のヒーロー切り抜き）。
   - DNA には**方針だけ**書く。「左寄せ」「ダーク」のような軸の値を書かない（ルール4）。
   - 両方の ref に**共通して**現れた方針だけを不変条件にする。
   - 「借りない部分」も明記する。ref 固有の芸を移植すると滑るため。
   - 同時に `design-system/refs/notes.md` に軸ごとの読み取りを書く。
3. 案を生成する。`request.json` の `variants` の数だけ、`design-lab/gen/a/`, `b/`, `c/` … に
   `index.html` と `styles.css` を書く。
   - **中身は `design-lab/index.html` の Cafe Little Leaf の実コンテンツ**を使う
     （店名・キャッチ・営業時間・メニュー3つ・予約ボタン・住所）。ダミーテキストにしない。
   - `axes.md` のルール2に従い、**案ごとに解放する軸をずらす**。
     自由度の予算内で別の組合せに割り当て直す。全案で同じ軸を動かすと似た案が並ぶ。
   - 各 css の冒頭に、その案で解放した軸と固定した軸をコメントで書く。
   - 和文の折り返しに `ch` を使わない（欧文基準で幅が足りない）。`em` を使う。
   - 写真素材は無いので、色調を ref に寄せた CSS のプレースホルダを置く。
4. `design-lab/compare-gen.html` の3枚のカード（見出し・説明文）を、今回の案に合わせて更新する。
   構造は変えず、`.name` と `.note` の中身だけ差し替える。
5. `design-system/ledger.md` に今回の行を追記する（id / 自由度 / 解放した軸 / 参照ref）。

## 重要
- 生成した案は必ず `design-lab/gen/<x>/index.html` として実際に開ける状態にする。
- 最後に、各案が「何を振ったか」を1行ずつ日本語で簡潔に報告する。それ以外は出力しない。
"""
