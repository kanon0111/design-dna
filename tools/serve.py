"""picker と生成案を配信し、選択・依頼をプロジェクト側に書き出すサーバ。

2つの場所を1つのURL空間に合成する:

  /              /picker.html   /compare.html   -> プラグインの web/
  /gen/...                                      -> <project>/.design/gen/
  /api/...                                      -> <project>/.design/*.json

標準の http.server は POST を受けないので、選択結果を渡すのに
「書き出してチャットに貼る」手動コピペが必要だった。それを無くすためのもの。

  POST /api/picks     -> .design/picks.json
  POST /api/request   -> .design/request.json  + 生成ジョブ起動
  POST /api/decision  -> .design/decision.json
  POST /api/assist    -> .design/assist.json   + ref選定ジョブ起動
  GET  /api/job?name= -> ジョブの状態
"""
import json, os, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import jobs
import isolate

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

# ファイル名 -> (ジョブ名, プロンプトの作り方, 使わせるツール, 制限時間)
JOB_FOR = {
    "assist": ("assist", lambda d: jobs.assist_prompt(d.get("brief", "")),
               ["Read", "Write", "Glob", "Grep"], 600),
    "request": ("generate", lambda d: jobs.generate_prompt(),
                ["Read", "Write", "Edit", "Glob", "Grep", "Bash"], 1800),
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=paths.WEB, **kw)

    # picker と生成案は開発中に何度も変わる。古い版を掴ませない。
    def end_headers(self):
        if self.path.split("?")[0].endswith((".html", ".css", ".js", ".json")):
            self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    # ---- 経路の合成 ----
    def translate_path(self, path):
        clean = path.split("?")[0].split("#")[0]
        if clean.startswith("/gen/"):
            rel = clean[len("/gen/"):].replace("/", os.sep)
            return os.path.join(paths.gen_dir(), rel)
        if clean.startswith("/project/"):
            # 適用先の現物。生成案と見比べるために出す。
            rel = clean[len("/project/"):]
            if any(seg.startswith(".") for seg in rel.split("/")):
                return os.path.join(paths.project_root(), "__denied__")
            return os.path.join(paths.project_root(), rel.replace("/", os.sep))
        return super().translate_path(path)

    # ---- 返し方 ----
    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read(self, name, empty):
        f = paths.p(name + ".json")
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                return json.load(fh)
        return empty

    def _write(self, name, data):
        paths.design_dir(create=True)
        with open(paths.p(name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)

    # ---- GET ----
    def do_GET(self):
        route = self.path.split("?")[0]
        if route == "/api/job":
            q = self.path.split("?", 1)[1] if "?" in self.path else ""
            name = dict(kv.split("=", 1) for kv in q.split("&") if "=" in kv).get("name", "")
            return self._json(200, jobs.status(name))
        if route.startswith("/ref/"):
            # 選んだ参照の実物。案の隣に並べて「何を選んで何が出たか」を見せる。
            rid = route[len("/ref/"):].split(".")[0]
            src = os.path.join(paths.THUMBS, rid + ".img")
            if not os.path.exists(src):
                return self._json(404, {"error": "no such ref"})
            with open(src, "rb") as fh:
                body = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/webp")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if route == "/api/baseline":
            # 比較したい既存物（現行サイト、過去の案）をプロジェクト側が宣言する
            f = paths.p("baseline.json")
            if os.path.exists(f):
                with open(f, encoding="utf-8") as fh:
                    return self._json(200, json.load(fh))
            return self._json(200, {})
        if route == "/api/brief":
            # /design-dna:start がプロジェクトを読んで書いた下書き
            f = paths.p("brief.md")
            if os.path.exists(f):
                with open(f, encoding="utf-8") as fh:
                    return self._json(200, {"brief": fh.read().strip()})
            return self._json(200, {"brief": ""})
        if route.startswith("/api/"):
            name = route[len("/api/"):]
            if name not in ("picks", "request", "decision", "assist"):
                return self._json(404, {"error": "not found"})
            return self._json(200, self._read(name, {"picks": []} if name == "picks" else {}))
        return super().do_GET()

    # ---- POST ----
    def do_POST(self):
        route = self.path.split("?")[0]
        if not route.startswith("/api/"):
            return self._json(404, {"error": "not found"})
        name = route[len("/api/"):]
        if name not in ("picks", "request", "decision", "assist"):
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception as e:
            return self._json(400, {"error": str(e)[:120]})

        if name == "picks" and not isinstance(data.get("picks"), list):
            return self._json(400, {"error": "picks は配列であること"})
        if name == "assist" and not (data.get("brief") or "").strip():
            return self._json(400, {"error": "brief が空"})

        self._write(name, data)
        if name == "assist":
            # 手で直した brief を残して、次に開いたときの下書きにする
            with open(paths.p("brief.md"), "w", encoding="utf-8") as fh:
                fh.write(data["brief"].strip() + os.linesep)
        print("  %s.json <- %s" % (name, self._summary(name, data)), flush=True)

        # 選定・生成はここで Claude Code を起こす（押しただけで完結させるため）
        if name in JOB_FOR:
            job, mk, tools, limit = JOB_FOR[name]
            try:
                box = after = None
                if job == "generate":
                    # 既存のコードが見えていると参照が薄まるので、隔離してから走らせる
                    box = isolate.build()
                    after = isolate.collect
                ok, msg = jobs.start(job, mk(data), tools, timeout=limit,
                                     sandbox=box, after=after)
            except Exception as e:
                # ここで例外を外に出すと接続ごと切れて「サーバに届きませんでした」になる
                msg = "%s: %s" % (type(e).__name__, str(e)[:160])
                print("  %s ジョブの準備に失敗: %s" % (job, msg), flush=True)
                return self._json(200, {"ok": True, "job": False, "message": msg})
            print("  %s ジョブ: %s%s" % (job, msg, "（隔離）" if box else ""), flush=True)
            return self._json(200, {"ok": True, "job": ok, "message": msg})
        return self._json(200, {"ok": True})

    @staticmethod
    def _summary(name, d):
        if name == "picks":
            return "%d 件" % len(d.get("picks", []))
        if name == "assist":
            return "「%s」" % (d.get("brief") or "")[:60]
        if name == "request":
            return "自由度%s%% 解放[%s] %s案" % (
                d.get("freedom"), "/".join(d.get("released") or []) or "なし", d.get("variants"))
        if name == "decision":
            return "採用: %s (%s)" % (d.get("variant"), d.get("label"))
        return ""

    def log_message(self, fmt, *args):
        # 画像の GET が大量に流れるとログが読めなくなるので API だけ出す
        if "/api/" in (self.path or ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    print("plugin : %s" % paths.PLUGIN_ROOT)
    print("project: %s" % paths.project_root())
    print("open   : http://localhost:%d/picker.html" % PORT)
    if not jobs.available():
        print("注意: claude コマンドが見つからないので、ボタンからの自動実行は使えません")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
