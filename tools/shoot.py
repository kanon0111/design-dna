"""できたページを実際に描画して、スクリーンショットと文字の実測を取る。

生成も本番作成も、書いたきり見ていなかった。見ていないので、ラベルが 10px、
本文が 13px、見出しより箇条書きのほうが大きい、というページがそのまま出ていた。
AI に「見て直せ」と言うための目と物差しがこれ。

    python shoot.py <page.html> [出力先ディレクトリ]

画面切り替えのページ（`<section class="page" id="…">`）なら画面ごとに撮る。
撮るもの（画面ごと）:
    <id>-desktop.png   1280x800 の最初の見え方
    <id>-desktop-full.png  その画面の全体
    <id>-mobile.png    390x844 の最初の見え方
標準出力に、画面ごとの文字サイズの実測と、小さすぎる文字の一覧を出す。

使うのは手元の Chrome / Edge の headless。依存ライブラリは要らない。
このファイルは生成の隔離環境にもそのままコピーされるので、他のモジュールを import しない。
"""
import http.server, io, json, os, re, shutil, socketserver, subprocess, sys, tempfile, threading
from urllib.parse import quote

# 和文でこれ未満は読めない。ラベル・注記でも 12px を下限にする
MIN_BODY = 15
MIN_ANY = 12

AUDIT = r"""<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" style="width:%(w)dpx;height:%(h)dpx;border:0"></iframe>
<pre id="out"></pre>
<script>
const f = document.getElementById("f");
f.onload = () => setTimeout(() => {
  const d = f.contentDocument, win = f.contentWindow, rows = [];
  const walker = d.createTreeWalker(d.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  let n;
  while ((n = walker.nextNode())) {
    const t = n.textContent.replace(/\s+/g, " ").trim();
    const el = n.parentElement;
    if (!t || !el || seen.has(el)) continue;
    const r = el.getBoundingClientRect(), cs = win.getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === "hidden" || +cs.opacity === 0) continue;
    if (el.closest("[aria-hidden=true]")) continue;
    seen.add(el);
    rows.push({px: parseFloat(cs.fontSize), w: cs.fontWeight, tag: el.tagName.toLowerCase(),
               cls: (el.className && el.className.baseVal === undefined ? el.className : "").slice(0, 40),
               y: Math.round(r.top + win.scrollY), text: t.slice(0, 40)});
  }
  document.getElementById("out").textContent = JSON.stringify({
    height: d.documentElement.scrollHeight, rows});
}, 800);
f.src = %(src)s;
</script>"""


def find_browser():
    cands = [shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("msedge")]
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("LOCALAPPDATA")):
        if base:
            cands += [os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                      os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")]
    cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    return next((c for c in cands if c and os.path.exists(c)), None)


def serve(root, audits):
    """ページのあるディレクトリをそのまま配信する。計測用のページはメモリから返す。"""
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def do_GET(self):
            key = self.path.split("?")[0]
            if key in audits:
                body = audits[key].encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return super().do_GET()

        def log_message(self, *a):
            pass

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def run(browser, profile, args):
    cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--no-first-run", "--user-data-dir=" + profile, *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)


def pages_of(html):
    ids = re.findall(r'<section[^>]*class="[^"]*\bpage\b[^"]*"[^>]*id="([^"]+)"', html)
    ids += [i for i in re.findall(r'<section[^>]*id="([^"]+)"[^>]*class="[^"]*\bpage\b', html)
            if i not in ids]
    return ids or [""]


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    page = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(
        tempfile.gettempdir(), "design-dna-shots")
    os.makedirs(out, exist_ok=True)
    w = io.TextIOWrapper(open(1, "wb", closefd=False), encoding="utf-8")

    browser = find_browser()
    if not browser:
        print("Chrome / Edge が見つからないので撮れない。目視の確認は飛ばす", file=w); w.flush()
        return 3

    root, name = os.path.dirname(page), os.path.basename(page)
    ids = pages_of(io.open(page, encoding="utf-8").read())
    audits = {}
    for pid in ids:
        for tag, (vw, vh) in (("desktop", (1280, 800)), ("mobile", (390, 844))):
            src = json.dumps("/" + quote(name) + ("#" + pid if pid else ""))
            audits["/__audit-%s-%s.html" % (pid or "page", tag)] = AUDIT % {"w": vw, "h": vh, "src": src}
    srv = serve(root, audits)
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    profile = tempfile.mkdtemp(prefix="dna-chrome-")

    small_all = []
    try:
        for pid in ids:
            label = pid or "page"
            url = base + "/" + quote(name) + ("#" + pid if pid else "")
            print("\n## 画面 %s" % label, file=w)
            for tag, (vw, vh) in (("desktop", (1280, 800)), ("mobile", (390, 844))):
                r = run(browser, profile, ["--virtual-time-budget=4000", "--dump-dom",
                                           base + "/__audit-%s-%s.html" % (label, tag)])
                m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout, re.S)
                data = {}
                if m:
                    import html as _h
                    try:
                        data = json.loads(_h.unescape(m.group(1)))
                    except ValueError:
                        data = {}
                rows = data.get("rows") or []
                height = int(data.get("height") or vh)

                shots = [("%s-%s.png" % (label, tag), vh)]
                if tag == "desktop":
                    shots.append(("%s-%s-full.png" % (label, tag), min(max(height, vh), 6000)))
                for fn, hh in shots:
                    run(browser, profile, ["--virtual-time-budget=3000",
                                           "--window-size=%d,%d" % (vw, hh),
                                           "--screenshot=" + os.path.join(out, fn), url])

                if not rows:
                    print("- %s: 文字を測れなかった（撮影だけ）" % tag, file=w)
                    continue
                sizes = sorted({round(x["px"]) for x in rows})
                big = max(rows, key=lambda x: x["px"])
                print("- %s: 高さ %dpx（%.1f 画面分） / 文字サイズ %s px / 一番大きいのは %dpx「%s」"
                      % (tag, height, height / vh, ", ".join(map(str, sizes)),
                         round(big["px"]), big["text"]), file=w)
                limit = MIN_ANY if tag == "desktop" else MIN_ANY
                small = [x for x in rows if x["px"] < limit]
                body = [x for x in rows if limit <= x["px"] < MIN_BODY and len(x["text"]) >= 30]
                for x in small:
                    print("  小さすぎる %gpx <%s class=%s>「%s」" % (x["px"], x["tag"], x["cls"], x["text"]), file=w)
                    small_all.append(x)
                for x in body:
                    print("  本文なのに小さい %gpx <%s class=%s>「%s」" % (x["px"], x["tag"], x["cls"], x["text"]), file=w)
                    small_all.append(x)
    finally:
        srv.shutdown()
        shutil.rmtree(profile, ignore_errors=True)

    print("\n撮影先: %s" % out, file=w)
    print("小さすぎる文字: %d 件（下限 %dpx、長い本文は %dpx）" % (len(small_all), MIN_ANY, MIN_BODY), file=w)
    w.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
