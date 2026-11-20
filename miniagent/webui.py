# -*- coding: utf-8 -*-
"""本地 Web 界面：标准库 http.server + SSE，单文件 HTML，无 CDN / 无第三方依赖。

面向新手的入口：首次打开弹设置向导、示例任务一键发送、工具调用说人话、
报错给可操作的下一步、危险操作在网页里逐条确认。
Win7 自带浏览器也能开，因此 JS 保持 ES5 写法。
"""

from __future__ import annotations

import json
import os
import threading
import urllib.parse
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from .onboarding import (apply_setup, check_setup, friendly_tool, humanize_error,
                         setup_tips, test_connection)
from .util import LOG, truncate

INDEX_HTML = u"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>MiniAgent - 会自己干活的 AI 助手</title>
<style>
  :root{--bg:#f6f7f9;--card:#fff;--line:#e3e6ea;--text:#22252a;--sub:#7b8190;--accent:#3a6df0;--ok:#2f9e63;--warn:#c96a2e;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font:14px/1.6 "Microsoft YaHei",Segoe UI,sans-serif}
  header{display:flex;align-items:center;gap:12px;padding:10px 16px;background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
  header h1{font-size:16px;margin:0}
  header .ver{font-size:12px;color:var(--sub);font-weight:normal;margin-left:4px}
  header .meta{color:var(--sub);font-size:12px}
  main{max-width:920px;margin:0 auto;padding:16px}
  .panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:16px}
  .panel h2{font-size:17px;margin:0 0 6px}
  .panel p{margin:0 0 12px;color:var(--sub);font-size:13px}
  .cards{display:flex;gap:10px;flex-wrap:wrap}
  .card{flex:1;min-width:200px;border:1px solid var(--line);border-radius:10px;padding:12px;cursor:pointer;background:#fbfcfe}
  .card:hover{border-color:var(--accent);background:#f2f6ff}
  .card .ct{font-weight:600;margin-bottom:4px}
  .card .cs{font-size:12px;color:var(--sub)}
  .card .cn{font-size:12px;color:var(--warn);margin-top:6px}
  .chips{display:flex;gap:8px;flex-wrap:wrap}
  .chip{border:1px solid var(--line);background:#fbfcfe;border-radius:20px;padding:6px 14px;cursor:pointer;font-size:13px}
  .chip:hover{border-color:var(--accent);color:var(--accent);background:#f2f6ff}
  .msg{margin:0 0 14px;padding:12px 14px;border-radius:10px;background:var(--card);border:1px solid var(--line);white-space:pre-wrap;word-break:break-word}
  .msg.user{background:#eaf1ff;border-color:#d5e2ff}
  .msg .who{font-size:12px;color:var(--sub);margin-bottom:4px}
  .tool{margin:6px 0;padding:8px 10px;border-left:3px solid var(--accent);background:#f2f5fb;font-size:12px;color:#41506b;border-radius:0 8px 8px 0}
  .tool .tname{font-weight:600}
  .tool .tout{white-space:pre-wrap;color:#5a6478;margin-top:4px;word-break:break-word}
  .errbox{margin:6px 0;padding:10px 12px;border-left:3px solid #c0392b;background:#fff5f4;font-size:13px;border-radius:0 8px 8px 0}
  .errbox .etitle{font-weight:600;color:#a93226}
  .errbox .edetail{color:#6b4b47;margin-top:3px}
  .confirm{margin:6px 0;padding:10px 12px;border-left:3px solid var(--warn);background:#fff8f0;font-size:13px;border-radius:0 8px 8px 0}
  .confirm .ctitle{font-weight:600;color:var(--warn)}
  .confirm.done{opacity:.6}
  .thinking{color:var(--sub);font-size:12px;padding:4px 0}
  .bar{display:flex;gap:8px;position:sticky;bottom:0;background:var(--bg);padding:12px 0}
  textarea{flex:1;height:64px;resize:vertical;padding:10px;border:1px solid var(--line);border-radius:10px;font:inherit;background:var(--card)}
  button{padding:0 18px;height:38px;border:0;border-radius:10px;background:var(--accent);color:#fff;font:inherit;cursor:pointer}
  button:disabled{background:#a9b6d8;cursor:default}
  button.ghost{background:var(--card);color:var(--text);border:1px solid var(--line)}
  button.small{height:28px;padding:0 12px;font-size:12px;margin-top:8px;margin-right:6px}
  .hint{color:var(--sub);font-size:12px;margin-top:6px}
  .mask{position:fixed;inset:0;background:rgba(20,25,35,.35);z-index:20;display:flex;align-items:center;justify-content:center}
  .sheet{background:var(--card);border-radius:14px;padding:20px;width:440px;max-width:92%;box-shadow:0 12px 40px rgba(0,0,0,.16)}
  .sheet h2{margin:0 0 14px;font-size:18px}
  .sheet label{display:block;font-size:12px;color:var(--sub);margin:10px 0 4px}
  .sheet input,.sheet select{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;font:inherit;background:#fff}
  .sheet .row{display:flex;gap:8px;margin-top:16px}
  .sheet .row button{flex:1}
  #setupMsg{font-size:12px;margin-top:10px;min-height:18px;color:var(--ok)}
  #setupMsg.bad{color:#c0392b}
  .pick{height:28px;padding:0 8px;font-size:12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--text);font:inherit;max-width:190px}
  .mlist{margin-top:10px;border-top:1px solid var(--line);padding-top:8px;max-height:170px;overflow:auto}
  .mrow{display:flex;align-items:center;gap:6px;padding:5px 2px;font-size:12px;border-bottom:1px dashed var(--line)}
  .mrow .mn{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .mrow button{height:24px;padding:0 8px;font-size:11px}
  .mrow.off{opacity:.5}
</style>
</head>
<body>
<header>
  <h1>MiniAgent<span class="ver">灵枢</span></h1>
  <span class="meta" id="meta">加载中…</span>
  <select id="modePick" class="pick" title="运行时模式" style="margin-left:auto"></select>
  <select id="modelPick" class="pick" title="切换模型"></select>
  <button id="setupBtn" class="ghost small" style="margin-left:0;margin-top:0">设置</button>
</header>
<main>
  <section class="panel" id="welcome" style="display:none">
    <h2>欢迎，第一次用先选一个模型</h2>
    <p>它会自己拆任务、动手做、再看结果。选好下面一项就能开始，不用改配置文件、不用记命令。</p>
    <div class="cards" id="presets"></div>
    <p class="hint" id="welcomeTip"></p>
  </section>
  <section class="panel" id="examples" style="display:none">
    <h2>不知道说什么？点一个试试</h2>
    <div class="chips" id="exampleList"></div>
  </section>
  <div id="log"></div>
  <div class="thinking" id="thinking" style="display:none">正在思考…</div>
  <div class="bar">
    <textarea id="input" placeholder="用一句话说清你想让它做什么，回车发送"></textarea>
    <button id="send">发送</button>
  </div>
  <div class="hint">回车发送 · Shift+回车换行 · 默认只能在软件所在文件夹里操作，重要文件请先备份</div>
</main>

<div class="mask" id="setupMask" style="display:none">
  <div class="sheet">
    <h2>设置</h2>
    <label>模型来源</label>
    <select id="fPreset"></select>
    <label>服务地址</label>
    <input id="fBase" type="text">
    <label>模型名</label>
    <input id="fModel" type="text">
    <label>API Key（只有云端模型需要；已保存过就留空表示不修改）</label>
    <input id="fKey" type="password" placeholder="粘贴你的 Key">
    <div class="hint" id="fTip"></div>
    <div class="row">
      <button id="testBtn" class="ghost">测试连接</button>
      <button id="saveBtn">保存</button>
      <button id="closeBtn" class="ghost">取消</button>
    </div>
    <div id="setupMsg"></div>
    <label style="margin-top:14px">模型目录（点「使用」切换，可停用不用的模型）</label>
    <div class="mlist" id="modelList"></div>
  </div>
</div>

<script>
var log = document.getElementById('log');
var input = document.getElementById('input');
var sendBtn = document.getElementById('send');
var thinking = document.getElementById('thinking');
var es = null;
var state = null;
var modelState = null;
var modeState = null;

function el(cls, html){var d=document.createElement('div');d.className=cls;if(html){d.innerHTML=html;}return d;}
function t(tag, cls, s){var e=document.createElement(tag);if(cls){e.className=cls;}e.textContent=s;return e;}
function bottom(){window.scrollTo(0,document.body.scrollHeight);}
function xhr(method, path, data, cb){
  var r = new XMLHttpRequest();
  r.open(method, path, true);
  r.setRequestHeader('Content-Type','application/json; charset=utf-8');
  r.onreadystatechange = function(){
    if(r.readyState === 4){
      var d = {};
      try{ d = JSON.parse(r.responseText); }catch(e){}
      cb(d, r.status);
    }
  };
  r.send(data ? JSON.stringify(data) : null);
}
function addMsg(who, text){
  var m = el('msg' + (who === '你' ? ' user' : ''), '');
  m.appendChild(t('div','who',who));
  var b = t('div','',text);
  m.appendChild(b);
  log.appendChild(m); bottom();
  return b;
}
function addTool(d){
  var box = el('tool','');
  box.appendChild(t('div','tname', d.friendly || ('正在调用 ' + d.name)));
  if(d.args && JSON.stringify(d.args).length > 2){
    box.appendChild(t('div','tout', JSON.stringify(d.args).slice(0,200)));
  }
  log.appendChild(box); bottom();
  window._curTool = box;
}
function addError(d){
  var box = el('errbox','');
  box.appendChild(t('div','etitle', d.title || '出了点问题'));
  box.appendChild(t('div','edetail', d.detail || ''));
  var b = t('button','small', d.action === 'setup' ? '去设置' : '再试一次');
  if(d.action === 'setup'){ b.onclick = function(){ openSetup(''); }; }
  else { b.onclick = function(){ if(window._lastQ){ send(window._lastQ); } }; }
  box.appendChild(b);
  log.appendChild(box); bottom();
}
function addConfirm(d){
  var box = el('confirm','');
  box.appendChild(t('div','ctitle','需要你同意'));
  box.appendChild(t('div','', d.friendly || d.name));
  var yes = t('button','small','允许');
  var no = t('button','small','拒绝');
  yes.onclick = function(){ xhr('POST','/api/confirm',{id:d.id,allow:true},function(){}); box.className='confirm done'; yes.disabled=true; no.disabled=true; };
  no.onclick = function(){ xhr('POST','/api/confirm',{id:d.id,allow:false},function(){}); box.className='confirm done'; yes.disabled=true; no.disabled=true; };
  box.appendChild(yes); box.appendChild(no);
  log.appendChild(box); bottom();
}

function renderWelcome(s){
  var box = document.getElementById('presets');
  box.innerHTML = '';
  for(var i=0;i<s.presets.length;i++){
    (function(p){
      var c = el('card','');
      c.appendChild(t('div','ct',p.title));
      c.appendChild(t('div','cs',p.subtitle));
      c.appendChild(t('div','cn',p.note));
      c.onclick = function(){
        if(p.need_key){ openSetup(p.id); }
        else { postSetup({preset:p.id}); }
      };
      box.appendChild(c);
    })(s.presets[i]);
  }
  document.getElementById('welcomeTip').textContent =
    '设置保存在你自己的用户目录里，不会写进项目文件夹，也不会被提交到 GitHub。';
}
function renderExamples(s){
  var box = document.getElementById('exampleList');
  box.innerHTML = '';
  for(var i=0;i<s.examples.length;i++){
    (function(ex){
      var c = t('div','chip', ex.title);
      c.title = ex.prompt;
      c.onclick = function(){ send(ex.prompt); };
      box.appendChild(c);
    })(s.examples[i]);
  }
}
function refresh(s){
  state = s;
  document.getElementById('welcome').style.display = s.configured ? 'none' : '';
  document.getElementById('examples').style.display = s.configured ? '' : 'none';
  document.getElementById('meta').textContent = s.configured
    ? (s.model + ' · 可用工具 ' + s.tools + ' 个')
    : '还没设置模型';
  if(s.configured){ renderExamples(s); } else { renderWelcome(s); }
}
function setupTip(p){
  if(p === 'mock'){ return '演示模式不联网、不花钱，回答是模拟的。想真正干活请换一个模型来源。'; }
  if(p === 'ollama'){ return '需要本机已安装并启动 Ollama，文件不会离开你的电脑。'; }
  return 'API Key 只保存在你自己的用户目录里，不会发到别处。';
}
function loadSetup(){
  xhr('GET','/api/setup',null,function(d){ if(d && d.presets){ refresh(d); } });
}

/* ── 模型目录：下拉切换 + 设置面板里的清单 ── */
function renderModelPick(){
  var sel = document.getElementById('modelPick');
  sel.innerHTML = '';
  if(!modelState || !modelState.models.length){
    var o = document.createElement('option');
    o.value=''; o.text='（没有模型）'; sel.appendChild(o); return;
  }
  for(var i=0;i<modelState.models.length;i++){
    var m = modelState.models[i];
    var op = document.createElement('option');
    op.value = m.id;
    op.text = (m.active ? '★ ' : '') + m.label + ' · ' + m.model;
    if(m.active){ op.selected = true; }
    sel.appendChild(op);
  }
}
function renderModePick(){
  var sel = document.getElementById('modePick');
  sel.innerHTML = '';
  if(!modeState){ return; }
  for(var i=0;i<modeState.modes.length;i++){
    var m = modeState.modes[i];
    var op = document.createElement('option');
    op.value = m.id;
    op.text = m.label + '模式';
    if(m.active){ op.selected = true; }
    sel.appendChild(op);
  }
}
function renderModelList(){
  var box = document.getElementById('modelList');
  box.innerHTML = '';
  if(!modelState || !modelState.models.length){
    box.appendChild(t('div','hint','还没有模型，先用上面的向导添加。')); return;
  }
  for(var i=0;i<modelState.models.length;i++){
    (function(m){
      var row = el('mrow' + (m.enabled ? '' : ' off'),'');
      row.appendChild(t('span','mn',(m.active?'★ ':'') + m.label + ' · ' + m.model + ' · ' + m.provider));
      var use = t('button','ghost small','使用');
      use.style.margin='0';
      use.disabled = m.active;
      use.onclick = function(){ postModel({action:'use', id:m.id}); };
      row.appendChild(use);
      var tg = t('button','ghost small',m.enabled?'停用':'启用');
      tg.style.margin='0';
      tg.onclick = function(){ postModel({action:'toggle', id:m.id, enabled:!m.enabled}); };
      row.appendChild(tg);
      box.appendChild(row);
    })(modelState.models[i]);
  }
}
function loadCatalog(){
  xhr('GET','/api/models',null,function(d){
    if(d && d.models){ modelState = d; renderModelPick(); renderModelList(); }
  });
  xhr('GET','/api/modes',null,function(d){
    if(d && d.modes){ modeState = d; renderModePick(); }
  });
}
function postModel(payload){
  xhr('POST','/api/models',payload,function(d){
    if(d && d.catalog){ modelState = d.catalog; renderModelPick(); renderModelList(); }
    if(d && d.ok){ addMsg('MiniAgent', d.message); } else { msg((d && d.message)||'操作失败', true); }
  });
}

function fillForm(presetId){
  var sel = document.getElementById('fPreset');
  sel.innerHTML = '';
  var custom = document.createElement('option');
  custom.value = 'custom'; custom.text = '自定义（保留当前设置）';
  sel.appendChild(custom);
  for(var i=0;i<state.presets.length;i++){
    var p = state.presets[i];
    var o = document.createElement('option');
    o.value = p.id; o.text = p.title;
    sel.appendChild(o);
  }
  var pid = presetId || state.preset || 'custom';
  sel.value = pid;
  var conf = null;
  for(var j=0;j<state.presets.length;j++){
    if(state.presets[j].id === pid){ conf = state.presets[j].config; }
  }
  document.getElementById('fBase').value = conf ? conf.api_base : (state.api_base || '');
  document.getElementById('fModel').value = conf ? conf.model : (state.model || '');
  document.getElementById('fKey').value = '';
  document.getElementById('fTip').textContent = setupTip(conf ? conf.provider : state.provider);
  document.getElementById('setupMsg').textContent = '';
}
function openSetup(presetId){
  if(!state){ return; }
  fillForm(presetId);
  document.getElementById('setupMask').style.display = 'flex';
  if(presetId === 'cloud'){ document.getElementById('fKey').focus(); }
}
function closeSetup(){ document.getElementById('setupMask').style.display = 'none'; }
function collectForm(){
  var pid = document.getElementById('fPreset').value;
  var payload = {preset: pid,
    api_base: document.getElementById('fBase').value,
    model: document.getElementById('fModel').value};
  var key = document.getElementById('fKey').value;
  if(key){ payload.api_key = key; }
  for(var i=0;i<state.presets.length;i++){
    if(state.presets[i].id === pid){ payload.provider = state.presets[i].config.provider; }
  }
  if(!payload.provider && pid !== 'custom'){ payload.provider = state.provider || 'openai_compat'; }
  return payload;
}
function msg(text, bad){
  var m = document.getElementById('setupMsg');
  m.textContent = text;
  m.className = bad ? 'bad' : '';
}
function postSetup(payload){
  xhr('POST','/api/setup',payload,function(d){
    if(d && d.ok){
      closeSetup();
      if(d.state){ d.state.tools = state ? state.tools : 0; refresh(d.state); }
      if(d.state && d.state.catalog){ modelState = d.state.catalog; renderModelPick(); renderModelList(); }
      addMsg('MiniAgent','设置好了。点上面的例子试试，或者直接说你想让它做什么。');
    } else {
      msg((d && d.message) || '保存失败，请检查填写内容', true);
    }
  });
}
function testConn(){
  msg('正在检查…');
  var payload = collectForm();
  if(!payload.api_key){
    xhr('GET','/api/test',null,function(d){
      msg((d && d.message) || '没拿到结果', !(d && d.ok));
    });
    return;
  }
  xhr('POST','/api/test',payload,function(d){
    msg((d && d.message) || '没拿到结果', !(d && d.ok));
  });
}

function send(q){
  var text = q || input.value.trim();
  if(!text){ return; }
  input.value = '';
  window._lastQ = text;
  addMsg('你', text);
  var answer = addMsg('MiniAgent', '');
  sendBtn.disabled = true;
  thinking.style.display = '';
  if(es){ es.close(); es = null; }
  es = new EventSource('/api/chat?q=' + encodeURIComponent(text));
  es.onmessage = function(ev){
    var d;
    try{ d = JSON.parse(ev.data); }catch(e){ return; }
    if(d.type === 'delta'){
      answer.textContent += d.text;
      bottom();
    } else if(d.type === 'step'){
      thinking.textContent = '正在思考… 第 ' + d.step + ' 步';
    } else if(d.type === 'tool_call'){
      addTool(d);
    } else if(d.type === 'tool_result'){
      if(window._curTool){
        window._curTool.appendChild(t('div','tout','结果：' + (d.output || '').slice(0,500)));
        bottom();
      }
    } else if(d.type === 'confirm'){
      addConfirm(d);
    } else if(d.type === 'error'){
      addError(d.info || {title:'出了点问题',detail:d.text || '',action:'retry'});
    } else if(d.type === 'done'){
      es.close(); es = null;
      sendBtn.disabled = false;
      thinking.style.display = 'none';
      input.focus();
    }
  };
  es.onerror = function(){
    if(es){ es.close(); es = null; }
    sendBtn.disabled = false;
    thinking.style.display = 'none';
  };
}

sendBtn.onclick = function(){ send(''); };
input.onkeydown = function(e){
  if(e.key === 'Enter' && (e.ctrlKey || !e.shiftKey)){ e.preventDefault(); send(''); }
};
document.getElementById('setupBtn').onclick = function(){ openSetup(''); };
document.getElementById('closeBtn').onclick = closeSetup;
document.getElementById('saveBtn').onclick = function(){ postSetup(collectForm()); };
document.getElementById('testBtn').onclick = testConn;
document.getElementById('fPreset').onchange = function(){ fillForm(this.value); };
document.getElementById('modelPick').onchange = function(){
  if(this.value){ postModel({action:'use', id:this.value}); }
};
document.getElementById('modePick').onchange = function(){
  xhr('POST','/api/modes',{mode:this.value},function(d){
    if(d && d.catalog){ modeState = d.catalog; renderModePick(); }
    if(d && d.ok){ addMsg('MiniAgent', d.message); }
  });
};
loadSetup();
loadCatalog();
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "MiniAgent/0.2"

    def log_message(self, fmt, *args):  # 静音默认访问日志
        LOG.debug("web %s - %s", self.address_string(), fmt % args)

    # ── GET ──
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        rt = self.server.runtime  # type: ignore[attr-defined]
        if path in ("/", "/index.html"):
            self._html(INDEX_HTML)
        elif path == "/api/status":
            self._json({
                "model": rt.cfg.get("model"),
                "provider": rt.cfg.get("provider"),
                "tools": len(rt.registry.names()),
                "skills": len(rt.skills.names()),
                "workspace": os.path.abspath(rt.cfg.get("workspace", ".")),
                "download": bool(_find_portable_zip()),
                "configured": check_setup(rt.cfg)["configured"],
            })
        elif path == "/api/setup":
            state = check_setup(rt.cfg)
            state["tools"] = len(rt.registry.names())
            state["workspace"] = os.path.abspath(rt.cfg.get("workspace", "."))
            state["tips"] = setup_tips(str(rt.cfg.get("provider", "")))
            self._json(state)
        elif path == "/api/test":
            self._json(test_connection(rt.cfg))
        elif path == "/api/tools":
            self._json([{"name": t.name, "source": t.source, "description": t.description}
                        for t in rt.registry.all()])
        elif path == "/api/models":
            self._json(rt.model_catalog())
        elif path == "/api/modes":
            self._json(rt.mode_catalog())
        elif path == "/api/kernel":
            self._json(rt.kernel_status())
        elif path == "/api/chat":
            self._chat((query.get("q") or [""])[0])
        elif path == "/download":
            self._download()
        else:
            self.send_error(404)

    # ── POST ──
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            length = 0
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        try:
            payload = json.loads(raw or "{}")
        except (ValueError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        rt = self.server.runtime  # type: ignore[attr-defined]

        if path == "/api/setup":
            self._json(self._save_setup(rt, payload))
        elif path == "/api/models":
            self._json(self._model_action(rt, payload))
        elif path == "/api/modes":
            name = str(payload.get("mode", "") or "")
            self._json(rt.set_mode(name) if name else rt.mode_catalog())
        elif path == "/api/test":
            # 允许用表单里尚未保存的值试连，避免「必须先保存才能测」
            probe = {}
            for k in ("provider", "api_base", "api_key"):
                if k in payload:
                    probe[k] = payload[k]
            self._json(test_connection(_ProbeConfig(rt.cfg, probe)))
        elif path == "/api/confirm":
            pending = getattr(self.server, "pending_confirm", None) or {}
            cid = str(payload.get("id", "") or "")
            rec = pending.get(cid)
            if rec is None:
                self._json({"ok": False, "message": "这条确认已经过期了"})
            else:
                rec["allow"] = bool(payload.get("allow"))
                rec["event"].set()
                self._json({"ok": True})
        else:
            self.send_error(404)

    @staticmethod
    def _model_action(rt, payload: Dict[str, Any]) -> Dict[str, Any]:
        """模型目录的增删改查。action 白名单，避免写入任意配置键。"""
        action = str(payload.get("action", "list") or "list")
        mid = str(payload.get("id", "") or "")
        if action == "list":
            return rt.model_catalog()
        if action == "use":
            return rt.use_model(mid)
        if action == "remove":
            return rt.remove_model(mid)
        if action == "toggle":
            return rt.toggle_model(mid, bool(payload.get("enabled")))
        if action == "save":
            item = payload.get("model")
            return rt.save_model(item) if isinstance(item, dict) else {
                "ok": False, "message": "模型信息格式不对"}
        return {"ok": False, "message": "不认识的操作：%s" % action}

    def _save_setup(self, rt, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = apply_setup(rt.cfg, payload)
        if not result.get("ok"):
            return result
        # 向导写的是顶层四个标量；同步回模型目录，避免「目录里还是旧模型」。
        # save_model 内部会重建后端并同步内核服务，无需再手工 create_llm。
        try:
            mid = rt.models.active_id() or "default"
            item = {
                "id": mid,
                "label": str(rt.cfg.get("model", "") or mid),
                "provider": str(rt.cfg.get("provider", "") or "openai_compat"),
                "model": str(rt.cfg.get("model", "") or ""),
                "api_base": str(rt.cfg.get("api_base", "") or ""),
                "api_key": str(rt.cfg.get("api_key", "") or ""),
                "enabled": True,
            }
            saved = rt.save_model(item)
            if not saved.get("ok"):
                return {"ok": False, "message": saved.get("message", "模型目录同步失败")}
        except Exception as exc:
            return {"ok": False,
                    "message": "设置已保存，但模型初始化失败：%s" % humanize_error(exc)["title"]}
        result["state"]["tools"] = len(rt.registry.names())
        result["state"]["catalog"] = rt.model_catalog()
        return result

    # ── SSE 对话 ──
    def _chat(self, question: str) -> None:
        rt = self.server.runtime  # type: ignore[attr-defined]
        agent = rt.agent
        provider = str(rt.cfg.get("provider", "") or "")
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
            elif kind == "step":
                emit_event({"type": "step", "step": data.get("step", 1),
                            "max": data.get("max", 1)})
            elif kind == "tool_call":
                name = data.get("name")
                emit_event({"type": "tool_call", "name": name,
                            "friendly": friendly_tool(name, data.get("arguments")),
                            "args": data.get("arguments")})
            elif kind == "tool_result":
                emit_event({"type": "tool_result",
                            "output": truncate(data.get("output", ""), 1200)})
            elif kind == "error":
                emit_event({"type": "error", "info": humanize_error(data, provider)})

        pending = getattr(self.server, "pending_confirm", None)
        if pending is None:
            pending = {}
            self.server.pending_confirm = pending  # type: ignore[attr-defined]

        def confirm_web(tool, arguments) -> bool:
            cid = uuid.uuid4().hex
            ev = threading.Event()
            pending[cid] = {"event": ev, "allow": False}
            emit_event({"type": "confirm", "id": cid, "name": tool.name,
                        "friendly": friendly_tool(tool.name, arguments),
                        "args": arguments})
            ev.wait(90)
            rec = pending.pop(cid, None)
            allowed = bool(rec and rec.get("allow"))
            emit_event({"type": "confirm_done", "id": cid, "allowed": allowed})
            return allowed

        prev_event = agent.on_event
        prev_confirm = agent.confirm
        prev_auto = agent.auto_confirm
        agent.on_event = on_event
        agent.confirm = confirm_web
        # 尊重配置：默认逐条确认，不再无条件放行危险工具
        agent.auto_confirm = bool(rt.cfg.get("auto_confirm", False))
        try:
            agent.chat(question, stream=bool(rt.cfg.get("stream", True)))
        except Exception as exc:
            emit_event({"type": "error", "info": humanize_error(exc, provider)})
        finally:
            agent.on_event = prev_event
            agent.confirm = prev_confirm
            agent.auto_confirm = prev_auto
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


class _ProbeConfig(object):
    """测试连接时用的只读配置视图：表单值覆盖现有配置，不写文件。"""

    def __init__(self, base_cfg, overrides: Dict[str, Any]):
        self._base = base_cfg
        self._over = overrides

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._over and str(self._over[key] or "").strip():
            return self._over[key]
        return self._base.get(key, default)


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
    print("MiniAgent 已启动： " + url)
    print("浏览器会自动打开；没自动打开就手动复制上面的地址到浏览器。")
    print("用完按 Ctrl+C 停止。")
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
