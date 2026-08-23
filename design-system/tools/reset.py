"""1回分の試行をリセットして、ref 選択からやり直せる状態に戻す。

**残すもの**（集め直すのが高い）:
  refs/candidates/*.json   候補227件
  refs/thumbs/             解析用サムネ
  refs/metrics.json        実測値
  refs/clusters.json       クラスタ
  refs/images/godly/       Godly のフルページ159枚

**消すもの**（1回分の状態）:
  refs/picks.json / request.json / decision.json / assist.json
  design-lab/gen/          生成した案 -> _runs/run-NN/ へ退避
  refs/notes.md            ref ごとの読み取り -> テンプレへ
  dna.md                   -> テンプレへ
  ledger.md の行           -> 見出しだけ残す

生成案は消さずに `design-lab/_runs/run-NN/` へ移す。
同じ座標を再利用しないための記録（ledger の趣旨）に使えるため。
"""
import io, os, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DS = os.path.join(ROOT, "design-system")
REFS = os.path.join(DS, "refs")
LAB = os.path.join(ROOT, "design-lab")

STATE_FILES = ["picks.json", "request.json", "decision.json", "assist.json"]

NOTES_TEMPLATE = """# 参照メモ

各 ref の「どこが好きか」。ここが薄いと DNA が一般論に戻る。

**進め方**: 私が実物を見て草案を書く。あなたは各行に `○`（合ってる）/ `×`（違う）/
一言修正を入れるだけでいい。ゼロから説明を求めると人は後付けの理屈を書いてしまうので、
叩き台に反応する形にしている。

`×` が付いた行は DNA に入れない。修正が入った行は修正後の文言を採用する。

---

<!-- 選ばれた ref ごとに、軸の読み / 借りたい属性 / 借りない部分 を書く -->
"""

DNA_TEMPLATE = """# DNA

`picks.json` の選択から抽出した不変条件。**自由度100%でも壊さない核**。
DNA を変えたいときは自由度ではなく ref を足して再抽出する。

> **DNA に軸の値を書かないこと**（`axes.md` ルール4）。
> ここに書いたものは自由度で永久に動かなくなる。方針だけを書き、
> 「左寄せ」「ダーク」のような具体値は軸に置く。

（未抽出。ref を選び、notes.md に ○× を入れたあとで生成する）
"""

LEDGER_TEMPLATE = """# 生成台帳

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
    runs = os.path.join(LAB, "_runs")
    os.makedirs(runs, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(runs, f"run-{n:02d}")):
        n += 1
    return os.path.join(runs, f"run-{n:02d}")


def main():
    out = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")
    done = []

    for name in STATE_FILES:
        p = os.path.join(REFS, name)
        if os.path.exists(p):
            os.remove(p); done.append(f"削除  refs/{name}")

    gen = os.path.join(LAB, "gen")
    if os.path.isdir(gen) and os.listdir(gen):
        dst = next_run_dir()
        shutil.move(gen, dst)
        done.append(f"退避  design-lab/gen/ -> {os.path.relpath(dst, ROOT)}")

    for path, tpl, label in [
        (os.path.join(REFS, "notes.md"), NOTES_TEMPLATE, "refs/notes.md"),
        (os.path.join(DS, "dna.md"), DNA_TEMPLATE, "dna.md"),
        (os.path.join(DS, "ledger.md"), LEDGER_TEMPLATE, "ledger.md"),
    ]:
        io.open(path, "w", encoding="utf-8").write(tpl)
        done.append(f"初期化 {label}")

    # 残っているものを確認して出す（集め直すと高いので消えていないこと）
    keep = {
        "候補": os.path.join(REFS, "candidates"),
        "サムネ": os.path.join(REFS, "thumbs"),
        "実測値": os.path.join(REFS, "metrics.json"),
        "クラスタ": os.path.join(REFS, "clusters.json"),
        "Godly画像": os.path.join(REFS, "images", "godly"),
    }

    for d in done:
        print(d, file=out)
    print("\n残したもの:", file=out)
    for k, p in keep.items():
        if os.path.isdir(p):
            n = sum(len(f) for _, _, f in os.walk(p))
            print(f"  {k:10s} {n} ファイル", file=out)
        else:
            print(f"  {k:10s} {'あり' if os.path.exists(p) else '無し'}", file=out)
    print("\nブラウザ側は picker.html を開いて『クリア』を押すか、"
          "localStorage の refs-picks-v2 を消す。", file=out)
    out.flush()


if __name__ == "__main__":
    main()
