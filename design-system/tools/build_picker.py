"""candidates/*.json から design-lab/picker.html のデータ行を差し替える。

収集スクリプトを回したあとにこれを実行すれば picker が追従する。
"""
import io, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAND = os.path.join(ROOT, "design-system", "refs", "candidates")
PICKER = os.path.join(ROOT, "design-lab", "picker.html")

def load(name):
    p = os.path.join(CAND, name)
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else []

def main():
    data = {"GODLY": load("godly.json"), "LAPA": load("lapa.json"), "AWW": load("awwwards.json")}

    # クラスタは refs/clusters.json（candidates の外）にある
    cpath = os.path.join(ROOT, "design-system", "refs", "clusters.json")
    clusters = json.load(io.open(cpath, encoding="utf-8"))["clusters"] if os.path.exists(cpath) else []
    data["CLUSTERS"] = clusters

    html = io.open(PICKER, encoding="utf-8").read()

    for var, rows in data.items():
        line = f"const {var}=" + json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + ";"
        pat = re.compile(rf"^const {var}=.*?;$", re.M)
        if not pat.search(html):
            raise SystemExit(f"picker.html に const {var}= が見つからない")
        html = pat.sub(lambda _: line, html, count=1)

    # サムネは 2x を使う（1x は粗くて構図が読めない）
    html = html.replace("assets/images/1x/", "assets/images/2x/")

    io.open(PICKER, "w", encoding="utf-8").write(html)
    total = sum(len(v) for k, v in data.items() if k != "CLUSTERS")
    for k, v in data.items():
        print(f"{k:10s} {len(v):>4d}")
    print(f"{'候補合計':10s} {total:>4d}  -> {os.path.relpath(PICKER, ROOT)}")
    covered = sum(len(c["members"]) for c in clusters)
    if clusters and covered != total:
        print(f"注意: クラスタの合計 {covered} 件が候補 {total} 件と一致しない（再クラスタリングが要る）")

if __name__ == "__main__":
    main()
