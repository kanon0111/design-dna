"""このプロジェクトの1回分をリセットして、ref 選択からやり直せる状態に戻す。

触るのは `<project>/.design/` の中だけ。参照プール（プラグイン側）には
一切手を出さない。集め直すのが高いため。

  消す   picks / request / decision / target の各 json（assist は旧版の残り）
  戻す   notes.md / dna.md / ledger.md をテンプレへ
  退避   gen/ -> runs/run-NN/（消さない。同じ座標を再利用しないための記録）

  --reopen  採用（decision.json）だけを外して picker を開き直せる状態にする。
            採用して本番ページができると picker は閉じるので、/design-dna:start を
            もう一度呼んだときに使う。参照の選択・生成済みの案・作ったページは残す。
"""
import io, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

STATE = ["picks.json", "request.json", "decision.json", "assist.json", "target.json"]
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

`picks.json` の選択から抽出した不変条件。**どの案でも壊さない核**。
DNA を変えたいときは ref を足して再抽出する。

> **DNA に軸の値を書かないこと**（`axes.md` ルール4）。
> ここに書いたものはどの案でも動かなくなる。方針だけを書き、
> 「左寄せ」「ダーク」のような具体値は軸に置く。

軸の**値**（左寄せ／ダーク／疎 など）はここではなく `axis-values.md` に置く。
「固定」はその値を再現することであって、触らないことではない。

（未抽出。ref を選び、notes.md に ○× を入れたあとで生成する）
"""

LEDGER = """# 生成台帳

同じ座標・同じ ref 組合せを再利用しないための記録。

| id | 寄せ方 | 参照 ref | 採否 | 選んだ / 落とした理由 |
|---|---|---|---|---|

## 案の寄せ方

案は2つ。a＝参照の配置に近づける / b＝雰囲気のまま内容に合わせて組む。
（自由度で解放軸を配分する方式は 2026-09-26 に廃止）
"""


def next_run_dir():
    runs = paths.p("runs")
    os.makedirs(runs, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(runs, "run-%02d" % n)):
        n += 1
    return os.path.join(runs, "run-%02d" % n)


def reopen(out):
    f = paths.p("decision.json")
    if os.path.exists(f):
        os.remove(f)
        print("削除  .design/decision.json（picker を開き直せます）", file=out)
    else:
        print("採用はまだありません。picker はそのまま使えます", file=out)
    out.flush()


def main():
    out = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    if "--reopen" in sys.argv[1:]:
        return reopen(out)
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
