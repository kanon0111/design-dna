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

    # ---- 経路の合成 ----
    def translate_path(self, path):
        clean = path.split("?")[0].split("#")[0]
        if clean.startswith("/gen/"):
            rel = clean[len("/gen/"):].replace("/", os.sep)
            return os.path.join(paths.gen_dir(), rel)
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
        print("  %s.json <- %s" % (name, self._summary(name, data)), flush=True)

        # 選定・生成はここで Claude Code を起こす（押しただけで完結させるため）
        if name in JOB_FOR:
            job, mk, tools, limit = JOB_FOR[name]
            ok, msg = jobs.start(job, mk(data), tools, timeout=limit)
            print("  %s ジョブ: %s" % (job, msg), flush=True)
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
