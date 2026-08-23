# 候補（未選別）

出典と収集条件の記録。選別画面は `design-lab/picker.html`。

## Godly（2026-08-22 再調査で構造が判明）

サイトは中身が2系統に分かれている。

| 系統 | 中身 | 件数 | 形式 |
|---|---|---:|---|
| **Websites** | サイト単位の作品エントリ | **18** | 全部 webp 静止画 |
| Trending（トップ） | X/Twitter 発の UI クリップ | 242 | **mp4 234 / webp 18** |
| Logos | ロゴ画像 | 1,129 | webp |
| Apps / Screenshots / Icons | モバイルアプリ（同一データ） | 約7,200 | webp |

`/trending` は 404。トップページ `/` がトレンド一覧の実体で、
242件すべてがHTMLに埋まっている（ページングは無い。`?page=2` は同一内容）。

### Websites 18件は thumbnail だけではない

初回は `thumbnail.webp`（1280x1600）だけ取っていたが、各サイトに
以下が揃っている。`refs/images/godly/{slug}/` に**159枚 / 23MB 取得済み**。

| アセット | 中身 | 揃い |
|---|---|---:|
| `desktop-full.webp` | **フルページ丸ごと**（1280 x 6,154〜15,000px、平均9,560px） | 18/18 |
| `mobile-full.webp` | モバイル版フルページ | 18/18 |
| `hero-desktop` / `-mobile` | ヒーロー部 | 18/18 |
| `footer-desktop` / `-mobile` | フッター部 | 17/18 |
| `cta-desktop` / `-mobile` | CTA部 | 13/18 |
| `thumbnail.webp` | 一覧用サムネ | 15/18 |
| `cta2-*` / `feature-*` / `testimonial-*` | 追加セクション | 2〜3/18 |

構図（軸の重み30）を学ぶ素材としては `desktop-full` が本命。

## その他の出典

| 出典 | URL | 件数 | 備考 |
|---|---|---:|---|
| Lapa Ninja | https://www.lapa.ninja/post/ | **208** | 全311ページ・約7,462件から年代横断でサンプリング |
| Awwwards | https://www.awwwards.com/sites/oimachi | 1 | 単体エントリ指定のため確定 ref 扱い |

### Lapa のサンプリング方針

最新ページだけ取ると「今の流行の平均」に寄る。それは最初に避けたかった
AI っぽさそのものなので、**1 / 45 / 89 / 133 / 177 / 221 / 265 / 309 / 311**
の9ページから均等に拾って年代の幅を持たせている。
`tools/fetch_lapa.py <ページ数>` で再実行でき、既存分とは slug で重複排除される。

サムネは `cdn.lapa.ninja/assets/images/2x/{imageSlug}-thumb.{ext}`（2x）を使う。
1x は粗くて構図が読めない。

## 選別画面

`design-lab/picker.html` — **227件**（Godly 18 / Lapa 208 / Awwwards 1）。
`python design-system/tools/build_picker.py` で candidates/*.json から再生成する。
サムネは各CDN直参照（ローカル保存はしない）。Godly の3件（rerun / rulebase /
melius）は thumbnail.webp が無いので hero-desktop.webp にフォールバックする。

### クラスタリング（2段階選別）

227件フラットは選べないので、**サムネの実測値**でクラスタに分けてから選ぶ。
「〇〇系」を私の主観でラベル付けすると、そこに避けたかった「AIの平均」が入るため、
分類も名前も画像の測定値だけから導出している。

```
tools/fetch_thumbs.py     227件のサムネをローカルへ（refs/thumbs/）
tools/analyze_thumbs.py   明度/彩度/コントラスト/色数/密度/余白を測る → refs/metrics.json
tools/cluster_thumbs.py   k-means でまとめ centroid から命名 → refs/clusters.json
tools/build_picker.py     picker.html に候補とクラスタを埋め込む
```

| id | 件数 | 呼び名 | centroid の性格 |
|---|---:|---|---|
| c1 | 60 | 静かな余白 | ライト / ほぼ無彩色 / 余白たっぷり / トーナル |
| c2 | 52 | 明快コントラスト | ライト / ほぼ無彩色 / 余白ふつう / パンチ強 |
| c3 | 41 | 情報密度 | ライト / ほぼ無彩色 / 密 / パンチ強 |
| c4 | 20 | カラフル | ライト / 多色・高彩度 / 密 |
| c5 | 33 | ダーク・静 | ダーク / 差し色あり / 余白ふつう |
| c6 | 21 | ダーク・鮮色 | ダーク / 多色・高彩度 / 余白たっぷり / トーナル |

**限界**: この6指標では**構図が測れない**。構図は軸の重みが30で最も重いのに、
画素からは読めない。クラスタは「色と明度と密度の系統」であって構図の系統ではなく、
構図はカテゴリを絞ったあとに本人が目で見て選ぶ前提。

低彩度の画像では色相（色数）の値がノイズに支配されるので、
命名では彩度が十分あるときだけ「多色」を名乗らせている。

### 選択は最大3件・役割つき

「1件だけ」にすると属性の掛け合わせができず、その1サイトの模倣になる。
逆に多く選ぶと同じ属性に複数の ref が入って平均化する。
**平均化が起きるのは「同じ属性に複数の ref が入る」時だけ**なので、
枠を役割で分ければ3件でも平均は起きない。

| 枠 | 借りるもの | 必須 |
|---|---|---|
| 骨格 | 構図・余白のリズム | 必須 |
| 色 | 配色のロジック | 任意 |
| 文字 | タイポの態度 | 任意 |

骨格だけ選べば「色と文字は DNA の範囲で AI が決める」になる。
結果は `refs/picks.json` に `role` つきで入る。

### AIに選んでもらう

picker 上部の「AIに選んでもらう」。作りたいものを一言書いて押すと
`refs/assist.json` に依頼が出る。選定は Claude Code 側でやり、
提案を `picks.json` に `by:"ai"` と `reason` つきで書き戻す。

このプロジェクトの前提は「AIが選ぶ＝平均＝AIっぽさ」なので、
そのまま任せると避けたかったものが戻る。歯止めは3つ:

1. **母集団を限定する。** AIが選べるのは本人が集めた227件の中だけ。
   世間一般から平均を取らせない。
2. **提案どまりにする。** `by:"ai"` が付いている間は未採用。枠は破線＋AIタグで表示され、
   「採用する」を押して初めて確定する（保存時に `by` は落ちる＝本人の選択になる）。
3. **理由を必ず書かせる。** 納得できなければ却下できる。

227件を全部見る代わりに、3件を見て○×する形にするためのもの。フィルタは本人に残る。

### リセット

```
python design-system/tools/reset.py
```

1回分の状態（picks / request / decision / assist / notes / dna / ledger）を初期化し、
`design-lab/gen/` は `design-lab/_runs/run-NN/` へ退避する（消さない）。
候補227件・サムネ・実測値・クラスタ・Godlyのフルページ159枚は**残る**。
ブラウザ側は picker の「クリア」を押すか localStorage の `refs-picks-v2` を消す。

### 起動

```
python design-system/tools/serve.py 8000
```

標準の `http.server` ではなくこれを使う。**クリックした時点で
`refs/picks.json` に直接書き込まれる**ので、選択結果を手でコピペする必要はない。
localStorage にも同時に持つが、正はディスク側（別ブラウザ・再起動後も復元する）。
サーバを立てずに開いた場合はヘッダに「サーバ未接続」と出て localStorage のみになる。

## 動画（Trending 234本）の扱い

技術的には静止画化できる。検証済み：

- ブラウザ内 canvas 抽出は **不可**。`cdn.godly.design` が
  `Access-Control-Allow-Origin` を返さないため canvas が汚染される。
  Cloudflare の `/cdn-cgi/media/`（mode=frame）も未有効で404。
- **ローカル抽出は可**。`tools/grab_frame.py`（OpenCV）でDL済みmp4から
  最良フレームを1枚選ぶ。冒頭の暗転を避けるため12コマ試して
  エッジ量×明度分散が最大のものを採用する。
  サンプル: `refs/_video-sample/post-181.webp`, `post-110.webp`

ただし中身は**モバイルアプリUIとマイクロインタラクションが大半**で、
Webページの構図を学ぶ素材ではない。効くのは装飾量(5)・コントラスト(12)止まり。

## 出典サイトの意向

godly.design の robots.txt は `Content-Signal: search=yes,ai-train=no` を掲げ、
ClaudeBot / GPTBot / CCBot 等を Disallow している。
参照リンクとして持つ分と、234本を一括DLするのは footprint が違うので、
動画側は「選んだものだけ」に留めるのが筋。
