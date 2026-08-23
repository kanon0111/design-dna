"""design-lab を配信しつつ、picker の選択を直接ディスクに書かせるサーバ。

標準の http.server は POST を受けないので、選択結果を渡すのに
「書き出してチャットに貼る」手動の橋が必要だった。それを無くすためのもの。

  POST /api/picks  -> design-system/refs/picks.json に保存
  GET  /api/picks  -> 保存済みの選択を返す（別ブラウザ・再起動後も復元できる）
"""
import json, os, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobs

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(ROOT, "design-lab")
PICKS = os.path.join(ROOT, "design-system", "refs", "picks.json")
REQUEST = os.path.join(ROOT, "design-system", "refs", "request.json")
DECISION = os.path.join(ROOT, "design-system", "refs", "decision.json")
ASSIST = os.path.join(ROOT, "design-system", "refs", "assist.json")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = self.path.split("?")[0]
        if route == "/api/job":
            q = self.path.split("?", 1)[1] if "?" in self.path else ""
            name = dict(kv.split("=", 1) for kv in q.split("&") if "=" in kv).get("name", "")
            return self._json(200, jobs.status(name))
        if route == "/api/assist":
            if os.path.exists(ASSIST):
                with open(ASSIST, encoding="utf-8") as fh:
                    return self._json(200, json.load(fh))
            return self._json(200, {})
        if self.path.split("?")[0] == "/api/decision":
            if os.path.exists(DECISION):
                with open(DECISION, encoding="utf-8") as fh:
                    return self._json(200, json.load(fh))
            return self._json(200, {})
        if self.path.split("?")[0] == "/api/request":
            if os.path.exists(REQUEST):
                with open(REQUEST, encoding="utf-8") as fh:
                    return self._json(200, json.load(fh))
            return self._json(200, {})
        if self.path.split("?")[0] == "/api/picks":
            if os.path.exists(PICKS):
                with open(PICKS, encoding="utf-8") as fh:
                    return self._json(200, json.load(fh))
            return self._json(200, {"picks": []})
        return super().do_GET()

    def do_POST(self):
        route = self.path.split("?")[0]
        if route == "/api/assist":
            return self._save_assist()
        if route == "/api/decision":
            return self._save_decision()
        if route == "/api/request":
            return self._save_request()
        if route != "/api/picks":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            picks = data.get("picks", [])
            if not isinstance(picks, list):
                raise ValueError("picks は配列であること")
        except Exception as e:
            return self._json(400, {"error": str(e)[:120]})

        os.makedirs(os.path.dirname(PICKS), exist_ok=True)
        with open(PICKS, "w", encoding="utf-8") as fh:
            json.dump({"picks": picks}, fh, ensure_ascii=False, indent=1)
        print(f"  picks.json <- {len(picks)} 件", flush=True)
        return self._json(200, {"saved": len(picks)})

    def _save_request(self):
        """picker の「決定」。自由度と案数を添えて生成依頼を書き出す。"""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception as e:
            return self._json(400, {"error": str(e)[:120]})

        os.makedirs(os.path.dirname(REQUEST), exist_ok=True)
        with open(REQUEST, "w", encoding="utf-8") as fh:
            json.dump(req, fh, ensure_ascii=False, indent=1)
        released = "/".join(req.get("released") or []) or "なし"
        print(f"  request.json <- 自由度{req.get('freedom')}% 解放[{released}] "
              f"{req.get('variants')}案 -> {req.get('target')}", flush=True)
        ok, msg = jobs.start("generate", jobs.generate_prompt(),
                             ["Read", "Write", "Edit", "Glob", "Grep", "Bash"], timeout=1800)
        print(f"  生成ジョブ: {msg}", flush=True)
        return self._json(200, {"ok": True, "job": ok, "message": msg})

    def _save_assist(self):
        """「AIに選んでもらう」。作りたいものの説明を渡すだけ。

        選定そのものはここではやらない。Claude Code 側が assist.json を読み、
        候補227件の中から提案を picks.json に書き戻す。母集団は本人が集めたものに
        限定され、提案には理由が付き、採用可否は本人が決める。
        """
        try:
            n = int(self.headers.get("Content-Length") or 0)
            d = json.loads(self.rfile.read(n).decode("utf-8"))
            brief = (d.get("brief") or "").strip()
            if not brief:
                raise ValueError("brief が空")
        except Exception as e:
            return self._json(400, {"error": str(e)[:120]})

        os.makedirs(os.path.dirname(ASSIST), exist_ok=True)
        with open(ASSIST, "w", encoding="utf-8") as fh:
            json.dump({"brief": brief, "status": "requested"}, fh, ensure_ascii=False, indent=1)
        print(f"  assist.json <- 「{brief[:60]}」", flush=True)
        ok, msg = jobs.start("assist", jobs.assist_prompt(brief),
                             ["Read", "Write", "Glob", "Grep"], timeout=600)
        print(f"  ref選定ジョブ: {msg}", flush=True)
        return self._json(200, {"ok": True, "job": ok, "message": msg})

    def _save_decision(self):
        """compare-gen の「この案で実装する」。採用した案を確定させる。"""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            d = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception as e:
            return self._json(400, {"error": str(e)[:120]})

        os.makedirs(os.path.dirname(DECISION), exist_ok=True)
        with open(DECISION, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        print(f"  decision.json <- 採用: {d.get('variant')} ({d.get('label')})", flush=True)
        print("  ※ チャットで一声かけてください（このサーバからは通知できません）", flush=True)
        return self._json(200, {"ok": True})

    def log_message(self, fmt, *args):
        # 静止画の GET が大量に流れるとログが読めなくなるので API だけ出す
        if "/api/" in (self.path or ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    print(f"serving {WEB} on http://localhost:{PORT}/")
    print(f"picks  -> {PICKS}")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
