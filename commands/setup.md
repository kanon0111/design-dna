---
description: design-dna の初期設定。依存を確認し、参照サムネを収集して、AIが実物を見て選べる状態にする
---

# design-dna : setup

初回だけ必要。**参照の画像はリポジトリに含まれていない**ので、各自の手元に集める。
候補一覧・測定値・クラスタは同梱済みなので、集めるのはサムネだけでいい。

## 1. 依存を確認する

```
python -c "import cv2, numpy, PIL; print('ok')"
```

足りなければ:

```
pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"
```

## 2. サムネを集める

```
python "${CLAUDE_PLUGIN_ROOT}/tools/fetch_thumbs.py"
```

227枚。数分かかる。**取得先は各サイトのCDN**で、集めた画像は各自の手元用。
再配布しないこと（godly.design の robots.txt は `Content-Signal: ai-train=no` を掲げている）。

これで `/design-dna:start` が使える状態になる。

## 参照を増やしたいとき

同梱の227件では足りない、もっと自分の好みに寄せたい場合。

```
python "${CLAUDE_PLUGIN_ROOT}/tools/fetch_lapa.py 20"    # Lapa は全311ページある
python "${CLAUDE_PLUGIN_ROOT}/tools/fetch_thumbs.py"
python "${CLAUDE_PLUGIN_ROOT}/tools/analyze_thumbs.py"
python "${CLAUDE_PLUGIN_ROOT}/tools/cluster_thumbs.py" 6
python "${CLAUDE_PLUGIN_ROOT}/tools/build_picker.py"
```

**プールが一般的でも、選ぶのが本人なら個性は残る** というのがこの仕組みの前提なので、
プールを増やすこと自体は目的ではない。手持ちが偏っていると感じたときだけでいい。
