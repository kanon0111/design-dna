"""プラグイン側とプロジェクト側の置き場所を一箇所で決める。

線引きはこう:

  プラグイン側（全プロジェクト共通・読むだけ）
    refs/candidates/  候補のURL一覧
    refs/metrics.json  refs/clusters.json   実測値とクラスタ
    axes.md            軸と重み
    web/               picker.html / compare.html
    cache/             収集した画像（gitignore・各自で取り直す）

  プロジェクト側（1回分・適用先ごと）
    <project>/.design/
      brief.md  content.md  target.json  picks.json  request.json  decision.json
      dna.md  notes.md  ledger.md
      gen/                 生成した案
      runs/                過去の生成案

プロジェクトの場所は「コマンドを実行したディレクトリ」。
環境変数 DESIGN_DNA_PROJECT で上書きできる。
"""
import os

# tools/ の親＝プラグインのルート
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REFS = os.path.join(PLUGIN_ROOT, "refs")
CANDIDATES = os.path.join(REFS, "candidates")
METRICS = os.path.join(REFS, "metrics.json")
CLUSTERS = os.path.join(REFS, "clusters.json")
AXES = os.path.join(PLUGIN_ROOT, "axes.md")
POLISH = os.path.join(PLUGIN_ROOT, "polish.md")
SHOOT = os.path.join(PLUGIN_ROOT, "tools", "shoot.py")
WEB = os.path.join(PLUGIN_ROOT, "web")
PICKER = os.path.join(WEB, "picker.html")
COMPARE = os.path.join(WEB, "compare.html")

CACHE = os.path.join(PLUGIN_ROOT, "cache")
THUMBS = os.path.join(CACHE, "thumbs")
IMAGES = os.path.join(CACHE, "images")
SLICES = os.path.join(CACHE, "_slices")


def project_root():
    """適用先のプロジェクト。実行したディレクトリを既定とする。"""
    return os.path.abspath(os.environ.get("DESIGN_DNA_PROJECT") or os.getcwd())


def design_dir(create=False):
    d = os.path.join(project_root(), ".design")
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def p(name, create=False):
    """<project>/.design/<name> を返す。"""
    return os.path.join(design_dir(create=create), name)


def gen_dir(create=False):
    d = p("gen")
    if create:
        os.makedirs(d, exist_ok=True)
    return d
