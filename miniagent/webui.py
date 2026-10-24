# -*- coding: utf-8 -*-
"""本地 Web 界面：标准库 http.server + SSE，无第三方依赖，Win7 自带浏览器可用。"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from .util import LOG, truncate

INDEX_HTML = u"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>MiniAgent</title>
<style>
  :root{--bg:#f6f7f9;--card:#fff;--line:#e3e6ea;--text:#22252a;--sub:#7b8190;--accent:#3a6df0;--ok:#2f9e63;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 "Microsoft YaHei",Segoe UI,sans-serif}
  header{display:flex;align-items:center;gap:12px;padding:10px 16px;background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
  header h1{font-size:16px;margin:0}
  header .meta{color:var(--sub);font-size:12px}
  main{max-width:900px;margin:0 auto;padding:16px}
  .msg{margin:0 0 14px;padding:12px 14px;border-radius:10px;background:var(--card);border:1px solid var(--line);white-space:pre-wrap;word-break:break-word}
  .msg.user{background:#eaf1ff;border-color:#d5e2ff}
  .msg .who{font-size:12px;color:var(--sub);margin-bottom:4px}
  .tool{margin:6px 0;padding:8px 10px;border-left:3px solid var(--accent);background:#f2f5fb;font-size:12px;color:#41506b}
  .tool .tname{font-weight:600}
  .tool .tout{white-space:pre-wrap;color:#5a6478;margin-top:4px}
  .bar{display:flex;gap:8px;position:sticky;bottom:0;background:var(--bg);padding:12px 0}
  textarea{flex:1;height:64px;resize:vertical;padding:10px;border:1px solid var(--line);border-radius:10px;font:inherit;background:var(--card)}
  button{padding:0 18px;border:0;border-radius:10px;background:var(--accent);color:#fff;font:inherit;cursor:pointer}
  button:disabled{background:#a9b6d8;cursor:default}
  .hint{color:var(--sub);font-size:12px;margin-top:6px}
  .status{color:var(--ok);font-size:12px}
</style>
</head>
<body>
<header>
  <h1>MiniAgent</h1>
  <span class="meta" id="meta">加载中…</span>
  <a id="dl" href="/download" style="display:none;margin-left:auto;font-size:12px;color:var(--accent);text-decoration:none;border:1px solid var(--line);padding:4px 10px;border-radius:8px;background:var(--card)">⬇ Windows 安装包</a>
</header>
<main>
  <div id="log"></div>
  <div class="bar">
    <textarea id="input" placeholder="输入问题，回车发送（Shift+回车换行）"></textarea>
    <button id="send">发送</button>
  </div>
  <div class="hint">Ctrl+Enter 发送 · 工具调用过程会实时显示</div>
</main>
<script>
var log = document.getElementById('log');
var input = document.getElementById('input');
var sendBtn = document.getElementById('send');
var es = null;

function el(cls, html){var d=document.createElement('div');d.className=cls;d.innerHTML=html;return d;}
function addMsg(who, text){var m=el('msg'+(who==='user'?' user':''), '');var h=document.createElement('div');h.className='who';h.textContent=who;var b=document.createElement('div');b.textContent=text;m.appendChild(h);m.appendChild(b);log.appendChild(m);window.scrollTo(0,document.body.scrollHeight);return b;}
function addTool(node){log.appendChild(node);window.scrollTo(0,document.body.scrollHeight);}

function send(){
  var q = input.value.trim();
  if(!q) return;
  input.value='';
  addMsg('你', q);
  var answer = addMsg('MiniAgent', '');
  sendBtn.disabled = true;
  if(es){es.close();es=null;}
  es = new EventSource('/api/chat?q=' + encodeURIComponent(q));
  es.onmessage = function(ev){
    var d;
    try{ d = JSON.parse(ev.data); }catch(e){ return; }
    if(d.type === 'delta'){
      answer.textContent += d.text;
      window.scrollTo(0, document.body.scrollHeight);
    } else if(d.type === 'tool_call'){
      var t = el('tool', '<span class="tname">调用 ' + d.name + '</span>');
      t._pre = document.createElement('div');
      t._pre.className='tout';
      t._pre.textContent = d.args ? JSON.stringify(d.args).slice(0,300) : '';
      t.appendChild(t._pre);
      addTool(t);
      t._node = t;
      window._curTool = t;
    } else if(d.type === 'tool_result'){
      if(window._curTool){
        var p = document.createElement('div');
        p.className='tout';
        p.textContent = '→ ' + (d.output||'').slice(0,600);
        window._curTool.appendChild(p);
      }
    } else if(d.type === 'error'){
      var e2 = el('tool', '<span class="tname" style="color:#c0392b">错误</span>');
      var pe = document.createElement('div'); pe.className='tout'; pe.textContent = d.text||''; e2.appendChild(pe); addTool(e2);
    } else if(d.type === 'done'){
      es.close(); es=null; sendBtn.disabled=false; input.focus();
    }
  };
  es.onerror = function(){ if(es){es.close();es=null;} sendBtn.disabled=false; };
}

sendBtn.onclick = send;
input.onkeydown = function(e){ if(e.key==='Enter' && (e.ctrlKey || !e.shiftKey)){ e.preventDefault(); send(); } };

fetch('/api/status').then(function(r){return r.json();}).then(function(d){
  document.getElementById('meta').textContent = d.model + ' · 工具 ' + d.tools + ' · ' + d.workspace;
  if(d.download){ document.getElementById('dl').style.display = ''; }
}).catch(function(){document.getElementById('meta').textContent='状态获取失败';});
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "MiniAgent/0.1"

    def log_message(self, fmt, *args):  # 静音默认访问日志
        LOG.debug("web %s - %s", self.address_string(), fmt % args)

    # ── GET ──
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if path in ("/", "/index.html"):
            self._html(INDEX_HTML)
        elif path == "/api/status":
            rt = self.server.runtime  # type: ignore[attr-defined]
            self._json({
                "model": rt.cfg.get("model"),
                "provider": rt.cfg.get("provider"),
                "tools": len(rt.registry.names()),
                "skills": len(rt.skills.names()),
                "workspace": os.path.abspath(rt.cfg.get("workspace", ".")),
                "download": bool(_find_portable_zip()),
            })
        elif path == "/api/tools":
            rt = self.server.runtime  # type: ignore[attr-defined]
            self._json([{"name": t.name, "source": t.source, "description": t.description}
                        for t in rt.registry.all()])
        elif path == "/api/chat":
            self._chat((query.get("q") or [""])[0])
        elif path == "/download":
            self._download()
        else:
            self.send_error(404)

    do_POST = do_GET

    # ── SSE 对话 ──
    def _chat(self, question: str) -> None:
        rt = self.server.runtime  # type: ignore[attr-defined]
        agent = rt.agent
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def emit_event(payload: dict) -> None:
            try:
                self.wfile.write(("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

        def on_event(kind: str, data: Any) -> None:
            if kind == "delta":
                emit_event({"type": "delta", "text": data})
            elif kind == "tool_call":
                emit_event({"type": "tool_call", "name": data.get("name"),
                            "args": data.get("arguments")})
            elif kind == "tool_result":
                emit_event({"type": "tool_result", "output": truncate(data.get("output", ""), 1200)})
            elif kind == "error":
                emit_event({"type": "error", "text": str(data)})

        prev = agent.on_event
        agent.on_event = on_event
        agent.auto_confirm = True  # Web 端暂不支持交互确认
        try:
            agent.chat(question, stream=bool(rt.cfg.get("stream", True)))
        except Exception as exc:
            emit_event({"type": "error", "text": "%s: %s" % (type(exc).__name__, exc)})
        finally:
            agent.on_event = prev
        emit_event({"type": "done"})

    # ── 响应 ──
    def _html(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _download(self) -> None:
        zp = _find_portable_zip()
        if not zp:
            self.send_error(404, "安装包不存在")
            return
        with open(zp, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="MiniAgent-portable.zip"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _find_portable_zip() -> Optional[str]:
    env = os.environ.get("MINIAGENT_DOWNLOAD")
    if env and os.path.isfile(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))   # .../miniagent
    root = os.path.dirname(here)                          # 部署根目录
    for base in (root, here, os.getcwd()):
        cand = os.path.join(base, "MiniAgent-portable.zip")
        if os.path.isfile(cand):
            return cand
    return None


def serve(rt, host: str = "127.0.0.1", port: int = 8787, open_browser: bool = True) -> int:
    class _Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    _Server.runtime = rt  # type: ignore[attr-defined]
    httpd = _Server((host, int(port)), _Handler)
    url = "http://%s:%d/" % (host, int(port))
    print("MiniAgent Web 界面: " + url)
    print("按 Ctrl+C 停止")
    if open_browser and rt.cfg.get("webui.open_browser", True):
        try:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
        rt.shutdown()
    return 0
