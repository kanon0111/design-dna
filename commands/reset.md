---
description: design-dna の1回分をリセットして ref 選択からやり直す。生成済みの案は runs/ に退避され、参照プールには触らない
---

# design-dna : reset

このプロジェクトの `.design/` だけを初期化する。参照プール（全プロジェクト共通）には
一切触らない。集め直すのが高いため。

```
python "${CLAUDE_PLUGIN_ROOT}/tools/reset.py"
```

| | |
|---|---|
| 消す | `.design/` の picks / request / decision / target |
| 戻す | `.design/` の notes.md / dna.md / ledger.md をテンプレへ |
| 退避 | `.design/gen/` → `.design/runs/run-NN/`（消さない） |

実行したあと、利用者にこう伝えること: ブラウザ側にも選択が残っているので、
picker を開いて「クリア」を押すか、localStorage の `refs-picks-v2` を消す必要がある。

そのまま選び直すなら `/design-dna:start`。
