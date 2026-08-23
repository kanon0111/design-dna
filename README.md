# design-dna

AI に「モダンでおしゃれに」と頼むと、**AI が良いと思うデザインの平均**が返ってくる。
平均には個性がないので、どれも似た顔になる。これはそれを避けるための仕組み。

要点はひとつだけ。**平均化が起きるのは「同じ属性に複数の参照が入る」時だけ**なので、
参照を役割ごとに1枚ずつに絞り、変えていい範囲を軸の重みで明示的に制御する。

---

## 仕組み

### 1. 参照を集める（自動）

Godly / Lapa Ninja / Awwwards から候補を集める。全部で **227件**。
プールが「世間が良いと思うデザイン」なのは承知の上で、**選ぶのは人間**にする。
プールが一般的でも、フィルタが個人なら個性は残る。

### 2. 実測して分類する

サムネから**明度・彩度・コントラスト・色相の散らばり・エッジ密度・余白率**を測り、
k-means でまとめて centroid から名前を付ける。「〇〇系」を人が主観で付けると
そこに AI の平均が入り込むので、分類も命名も測定値だけから導出する。

| 系統 | 件数 | centroid の性格 |
|---|---:|---|
| 静かな余白 | 60 | ライト / ほぼ無彩色 / 余白たっぷり / トーナル |
| 明快コントラスト | 52 | ライト / ほぼ無彩色 / 余白ふつう / パンチ強 |
| 情報密度 | 41 | ライト / ほぼ無彩色 / 密 / パンチ強 |
| カラフル | 20 | ライト / 多色・高彩度 / 密 |
| ダーク・静 | 33 | ダーク / 差し色あり / 余白ふつう |
| ダーク・鮮色 | 21 | ダーク / 多色・高彩度 / 余白たっぷり |

**限界**: この6指標では構図が測れない。構図は軸の重みが最大（28）なのに画素からは読めないので、
分類は「色と明度と密度の系統」であって構図の系統ではない。構図は人が目で見て選ぶ前提。

### 3. 役割ごとに1枚ずつ選ぶ

| 枠 | 借りるもの | 必須 |
|---|---|---|
| 骨格 | 構図・余白のリズム | 必須 |
| 色 | 配色のロジック | 任意 |
| 文字 | タイポの態度 | 任意 |

1枚だと属性の掛け合わせができず、その1サイトの模倣になる。
多く選ぶと同じ属性に複数入って平均化する。**役割で分ければ3件でも平均は起きない。**

### 4. DNA を抽出する

選んだ参照の実物を見て、**両方に共通して現れた方針だけ**を不変条件にする。
「借りない部分」も明記する。参照固有の芸を移植すると滑るため。

### 5. 自由度で振れ幅を決める

自由度 N% = **軽い軸から順に、重み合計が N を超えない範囲まで解放**。
残りは選んだ参照の値のまま固定する。

| 軸 | 重み |
|---|---:|
| 構図 | 28 |
| 主役 | 22 |
| 地の明度 | 20 |
| 密度 | 15 |
| コントラスト | 9 |
| 階層の跳ね | 4 |
| 装飾量 | 2 |

**ルール4（重要）**: DNA に軸の**値**を書かない。書くとその軸は自由度で永久に動かなくなる。
DNA に入れてよいのは「アクセント色を持たない」のような**方針**だけ。
（実際に「左寄せ非対称」「地は黒と生成り」を DNA に書いてしまい、
自由度をいくら上げても雰囲気が変わらない事故を起こしている。）

**ルール2**: 同じ自由度で複数案を出すときは、**案ごとに解放する軸をずらす**。
同じ予算でも壊す場所が違えば、案同士も似ない。

---

## 構成

```
design-system/
  axes.md              軸と重み、自由度のルール
  dna.md               抽出した不変条件（1回分）
  ledger.md            生成台帳
  refs/
    candidates/*.json  候補227件（URLのみ・26KB）
    metrics.json       実測値
    clusters.json      k-means の結果
    notes.md           参照ごとの読み取り
    picks.json         選んだもの
  tools/
    fetch_godly_sites.py   Godly の全アセット取得
    fetch_lapa.py          Lapa を年代横断サンプリング
    fetch_thumbs.py        解析用サムネ取得
    analyze_thumbs.py      6指標を測る
    cluster_thumbs.py      k-means と命名
    build_picker.py        picker.html にデータを埋め込む
    serve.py               配信 + 保存API + ジョブ起動
    jobs.py                claude -p を headless で叩く
    apply_style.py         picker の見た目を差し替える
    reset.py               1回分を初期化
    grab_frame.py          動画から最良フレームを1枚

design-lab/
  index.html           Cafe Little Leaf（適用先のサンプル）
  picker.html          選別画面
  compare.html         旧3案（曖昧な指示から出したもの・比較対象）
  compare-gen.html     DNA生成案の比較
  _runs/               過去の生成案
  _redesign/           picker 自体のデザイン案
```

## 使い方

```bash
python design-system/tools/serve.py 8000
```

http://localhost:8000/picker.html を開く。

- **自分で選ぶ** — 系統6つ → 詳細 → 骨格枠に1枚（色・文字は任意）
- **おまかせ** — つくりたいものを書いて押す。Claude Code が headless で走り、
  227件から3枠ぶんを理由つきで提案する。提案どまりで、採用するかは人が決める

自由度と案の数を決めて「決定」。生成ジョブが走り、終わると compare-gen.html に飛ぶ。

初回は参照の収集が要る:

```bash
python design-system/tools/fetch_lapa.py 8
python design-system/tools/fetch_godly_sites.py
python design-system/tools/fetch_thumbs.py
python design-system/tools/analyze_thumbs.py
python design-system/tools/cluster_thumbs.py 6
python design-system/tools/build_picker.py
```

## 現状と次

動いているのは「収集 → 分類 → 選別 → 自由度 → 生成 → 比較」まで。

次にやること:

1. `.design/` をプロジェクト側に切り出す（今はプールと1回分の状態が同じ場所にある）
2. Claude Code プラグインの形にする（`~/.claude/plugins/` に置けば全プロジェクトから呼べる）
3. brief の自動下書き — 空欄に書かせず、既存のコードを読んで下書きする
4. 生成した案と最終形の差分を回収して DNA に還す

## 公開に切り替えるときに外すもの

このリポジトリは**プライベート前提**。公開するなら以下を必ず外すこと。

- `design-lab/_redesign/*.jpg` — 他サイトのスクリーンショットの縮小版
- `design-system/refs/candidates/*.json` に含まれる各CDNのURL自体は問題ないが、
  Godly の robots.txt は `Content-Signal: search=yes, ai-train=no` を掲げている。
  収集スクリプトを配ること自体は各自の利用に委ねる形になるので、
  READMEにその旨を書くこと。

（`refs/thumbs/` と `refs/images/` は最初から `.gitignore` 済み。）

## 注意

このフォルダは OneDrive 配下にある。`.git` の同期でまれに競合が起きるので、
気になるなら OneDrive の外へ移すこと。
