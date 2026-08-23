"""このプロジェクトの1回分をリセットして、ref 選択からやり直せる状態に戻す。

触るのは `<project>/.design/` の中だけ。参照プール（プラグイン側）には
一切手を出さない。集め直すのが高いため。

  消す   picks / request / decision / assist の各 json
  戻す   notes.md / dna.md / ledger.md をテンプレへ
  退避   gen/ -> runs/run-NN/（消さない。同じ座標を再利用しないための記録）
"""
import io, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

STATE = ["picks.json", "request.json", "decision.json", "assist.json"]
DERIVED = ["axis-values.md"]

NOTES = """# 参照メモ

各 ref の「どこが好きか」。ここが薄いと DNA が一般論に戻る。

**進め方**: AI が実物を見て草案を書く。あなたは各行に `○`（合ってる）/ `×`（違う）/
一言修正を入れるだけでいい。ゼロから説明を求めると人は後付けの理屈を書いてしまうので、
叩き台に反応する形にしている。

`×` が付いた行は DNA に入れない。修正が入った行は修正後の文言を採用する。

---

<!-- 選ばれた ref ごとに、軸の読み / 借りたい属性 / 借りない部分 を書く -->
"""

DNA = """# DNA

`picks.json` の選択から抽出した不変条件。**自由度100%でも壊さない核**。
DNA を変えたいときは自由度ではなく ref を足して再抽出する。

> **DNA に軸の値を書かないこと**（`axes.md` ルール4）。
> ここに書いたものは自由度で永久に動かなくなる。方針だけを書き、
> 「左寄せ」「ダーク」のような具体値は軸に置く。

軸の**値**（左寄せ／ダーク／疎 など）はここではなく `axis-values.md` に置く。
「固定」はその値を再現することであって、触らないことではない。

（未抽出。ref を選び、notes.md に ○× を入れたあとで生成する）
"""

LEDGER = """# 生成台帳

同じ座標・同じ ref 組合せを再利用しないための記録。

| id | 自由度 | 解放した軸 | 参照 ref | 採否 | 選んだ / 落とした理由 |
|---|---:|---|---|---|---|

## 軸予算の配分について

picker は自由度Nに対して**軽い軸から順に**解放軸を決める。ただし axes.md の
ルール2「同一自由度で複数案を出すときは案ごとに解放する軸をずらす」に従い、
**生成時は同じ予算内で別の組合せに割り当て直す**。そうしないと3案とも
同じ軸が動いて似た案が並ぶ。
"""


def next_run_dir():
    runs = paths.p("runs")
    os.makedirs(runs, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(runs, "run-%02d" % n)):
        n += 1
    return os.path.join(runs, "run-%02d" % n)


def main():
    out = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    d = paths.design_dir()
    if not os.path.isdir(d):
        print("このプロジェクトにはまだ .design/ がありません: %s" % d, file=out)
        out.flush(); return

    done = []
    for name in STATE + DERIVED:
        f = paths.p(name)
        if os.path.exists(f):
            os.remove(f); done.append("削除  .design/%s" % name)

    gen = paths.gen_dir()
    if os.path.isdir(gen) and os.listdir(gen):
        dst = next_run_dir()
        shutil.move(gen, dst)
        done.append("退避  .design/gen/ -> .design/runs/%s" % os.path.basename(dst))

    for name, tpl in [("notes.md", NOTES), ("dna.md", DNA), ("ledger.md", LEDGER)]:
        io.open(paths.p(name), "w", encoding="utf-8").write(tpl)
        done.append("初期化 .design/%s" % name)

    for line in done:
        print(line, file=out)
    print("\nプロジェクト: %s" % paths.project_root(), file=out)
    print("参照プールには触っていません: %s" % paths.PLUGIN_ROOT, file=out)
    print("\nブラウザ側は picker の「クリア」を押すか、"
          "localStorage の refs-picks-v2 を消す。", file=out)
    out.flush()


if __name__ == "__main__":
    main()
