#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a self-contained mobile-first HTML gate-review page for memory candidates."""

import argparse
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path

try:
    from .memory_evidence import dataset_fingerprint, validate_legacy_freeze, decision_is_current, digest, preflight_outputs
except ImportError:
    from memory_evidence import dataset_fingerprint, validate_legacy_freeze, decision_is_current, digest, preflight_outputs

VALID_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def ascii_print(msg: str) -> None:
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def err(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def die(msg: str, code: int = 2) -> None:
    err(msg)
    sys.exit(code)


def compute_source_dataset(candidate_ids: list[str]) -> str:
    sorted_ids = sorted(candidate_ids)
    joined = "\n".join(sorted_ids)
    return hashlib.md5(joined.encode("utf-8")).hexdigest()[:12]


def load_patterns(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    patterns = data.get("patterns", []) if isinstance(data, dict) else data
    compiled = []
    for p in patterns or []:
        try:
            compiled.append(
                {
                    "name": str(p.get("name", "")),
                    "regex": re.compile(str(p.get("regex", "")), re.IGNORECASE),
                    "severity": str(p.get("severity", "")),
                }
            )
        except re.error:
            continue
    return compiled


def format_duration(ms: int) -> str:
    try:
        secs = max(1, round(int(ms) / 1000))
    except (ValueError, TypeError):
        return "[媒体]"
    return f"[语音 {secs}秒]"


def format_timestamp(ts: str) -> str:
    # ts like 2022-07-18T17:46:22+08:00
    m = re.search(r"T(\d{2}):(\d{2})", ts or "")
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    return ""


def load_candidates(path: str) -> list[dict]:
    candidates = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            candidates.append(json.loads(line))
    return candidates


def build_flag_matches(cand: dict, patterns: list[dict]) -> list[str]:
    title = str(cand.get("title", "") or "")
    texts = [title]
    for ex in cand.get("excerpts", []) or []:
        t = ex.get("text", "") if isinstance(ex, dict) else ""
        if t:
            texts.append(str(t))
    haystack = "\n".join(texts)
    matches = []
    for p in patterns:
        if p["severity"] in ("high", "medium") and p["regex"].search(haystack):
            matches.append(p["name"])
    return matches


def initial_state_for(cand: dict) -> str:
    if cand.get('schema_version') == 2 and not decision_is_current(cand):
        return 'pending'
    saved = str(cand.get("status", "") or "").strip().lower()
    if saved in ("confirmed", "rejected"):
        return "confirm" if saved == "confirmed" else "reject"
    return "pending"


def escape_html(s: str) -> str:
    return html.escape(str(s), quote=True)


def build_excerpt_html(excerpts: list[dict]) -> str:
    parts = []
    for idx, ex in enumerate(excerpts or []):
        if not isinstance(ex, dict):
            continue
        ts = format_timestamp(str(ex.get("timestamp", "") or ""))
        text = str(ex.get("text", "") or "").strip()
        if text:
            if len(text) > 280:
                visible = escape_html(text[:280])
                hidden = escape_html(text[280:])
                parts.append(
                    f'<div class="excerpt"><span class="ex_time">{escape_html(ts)}</span>'
                    f'<span class="ex_text"><span class="exc-head">{visible}</span>'
                    f'<span class="exc-tail" style="display:none">{hidden}</span>'
                    f'<span class="exc-ellipsis">…</span></span>'
                    f' <button class="expandbtn" type="button">展开</button></div>'
                )
            else:
                parts.append(
                    f'<div class="excerpt"><span class="ex_time">{escape_html(ts)}</span>'
                    f'<span class="ex_text">{escape_html(text)}</span></div>'
                )
        else:
            dur = ex.get("duration_ms")
            label = format_duration(dur) if dur is not None else "[媒体]"
            parts.append(
                f'<div class="excerpt"><span class="ex_time">{escape_html(ts)}</span>'
                f'<span class="ex_media">{label}</span></div>'
            )
    return "".join(parts)


def build_card(cand: dict, flagged_names: list[str], initial_state: str) -> dict:
    cid = str(cand.get("candidate_id", ""))
    date = str(cand.get("date", "") or "")
    kind_label = str(cand.get("kind_label", "") or cand.get("kind", "") or "")
    title = str(cand.get("title", "") or "")
    excerpts_html = build_excerpt_html(cand.get("excerpts", []) or [])

    flagged_html = ""
    if flagged_names:
        names = "、".join(escape_html(n) for n in flagged_names)
        flagged_html = f'<div class="flaggedbadge">⚠️ 疑似敏感 ({names})</div>'

    user_title = cand.get("user_title")
    user_note = cand.get("user_note")

    return {
        "id": cid,
        "schema_version": cand.get('schema_version', 1),
        "person": cand.get('person'),
        "relationship_id": cand.get('relationship_id'),
        "evidence_revision": cand.get('evidence_revision') if cand.get('schema_version') == 2 else digest(cand),
        "date": date,
        "kind_label": kind_label,
        "title": title,
        "excerpts_html": excerpts_html,
        "flagged_html": flagged_html,
        "flagged": bool(flagged_names),
        "initial": initial_state,
        "user_title": user_title if user_title is not None and str(user_title).strip() else None,
        "user_note": user_note if user_note is not None and str(user_note).strip() else None,
    }


def render_page(
    slug: str,
    cards: list[dict],
    source_dataset: str,
    total: int,
) -> str:
    payload = json.dumps(cards, ensure_ascii=False).replace("</", "<\\/")

    # Escape the slug for the header
    slug_html = escape_html(slug)

    # Single file template (the "no placeholder other than __DATA__" rule)
    template = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>记忆卡片人工闸门 · __SLUG__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;background:#f4f5f7;color:#222;padding-bottom:90px}
header{background:#fff;padding:14px 16px;border-bottom:1px solid #e0e0e0;position:relative}
header h1{font-size:18px;font-weight:700;margin-bottom:6px}
.meta{font-size:13px;color:#666;margin-bottom:4px}
.progressline{font-size:13px;color:#1a73e8;font-weight:600}
.instructions{font-size:12px;color:#777;margin-top:6px;line-height:1.5}
.tabs{position:sticky;top:0;z-index:50;background:#fff;border-bottom:1px solid #e0e0e0;display:flex;overflow-x:auto;padding:6px 8px}
.tab{flex:0 0 auto;font-size:13px;padding:8px 14px;border:1px solid #d0d0d0;border-radius:18px;margin:0 4px;background:#fafafa;cursor:pointer;white-space:nowrap}
.tab.active{background:#1a73e8;color:#fff;border-color:#1a73e8}
.tab .cnt{font-weight:700}
.cardwrap{margin:10px 12px;background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.12);padding:12px 14px;border-left:4px solid #d0d0d0}
.cardwrap.state-confirm{border-left-color:#1e8e3e;background:#f0faf0}
.cardwrap.state-reject{border-left-color:#aaa;background:#f3f3f3;opacity:.85}
.cardwrap.state-edited{border-left-color:#1e8e3e;background:#f0faf0}
.cardtop{display:flex;align-items:center;gap:6px;margin-bottom:6px}
.chip{font-size:11px;background:#e8f0fe;color:#1a56c4;padding:2px 8px;border-radius:10px;white-space:nowrap}
.date{font-size:13px;color:#555;font-weight:600}
.title{font-size:15px;font-weight:700;margin:4px 0 6px;line-height:1.4;word-break:break-word}
.state-reject .title{text-decoration:line-through;color:#888}
.flaggedbadge{display:inline-block;background:#fff2cc;color:#8a6d00;border:1px solid #e5c453;font-size:11px;padding:2px 8px;border-radius:4px;margin:4px 0}
.excerptlist{margin:6px 0 8px}
.excerpt{font-size:13px;line-height:1.5;margin:4px 0;display:flex;gap:8px;align-items:flex-start}
.ex_time{color:#888;flex:0 0 42px;font-family:ui-monospace,monospace;font-size:12px}
.ex_text{white-space:pre-wrap;word-break:break-word;flex:1}
.exc-head,.exc-tail{white-space:pre-wrap;word-break:break-word}
.ex_media{color:#c05d00;background:#fef3e8;padding:1px 8px;border-radius:4px;font-size:12px}
.expandbtn{background:none;border:1px solid #aaa;border-radius:4px;font-size:12px;padding:2px 6px;color:#555;cursor:pointer;flex:0 0 auto}
.editedchip{display:inline-block;background:#d9f2dc;color:#1e8e3e;font-size:11px;padding:1px 8px;border-radius:10px;margin-left:6px;font-weight:600}
.actions{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
.actbtn{flex:1;min-width:88px;min-height:44px;border-radius:8px;border:1px solid #ccc;font-size:13px;cursor:pointer;background:#fafafa}
.actbtn.confirm-btn.active{background:#1e8e3e;color:#fff;border-color:#1e8e3e}
.actbtn.reject-btn.active{background:#777;color:#fff;border-color:#777}
.actbtn.edit-btn.active{background:#f9ab00;color:#fff;border-color:#f9ab00}
.editarea{margin-top:8px;background:#fafafa;border:1px solid #e0e0e0;border-radius:8px;padding:8px}
.editarea textarea,.editarea input{width:100%;border:1px solid #ccc;border-radius:6px;padding:8px;font-size:14px;margin-bottom:6px;font-family:inherit}
.editbtns{display:flex;gap:8px}
.editbtns button{flex:1;min-height:40px;border-radius:6px;border:1px solid #ccc;background:#fff;cursor:pointer;font-size:13px}
.editbtns .savebtn{background:#1e8e3e;color:#fff;border-color:#1e8e3e}
.bottombar{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #ddd;padding:8px 12px calc(8px + env(safe-area-inset-bottom));display:flex;align-items:center;gap:10px;z-index:100}
.bottomcounts{font-size:13px;flex:1}
#genbtn{background:#1a73e8;color:#fff;border:none;border-radius:24px;min-height:44px;padding:0 20px;font-size:15px;cursor:pointer;font-weight:600;box-shadow:0 2px 4px rgba(0,0,0,.2)}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:200;align-items:center;justify-content:center;padding:16px}
.modal.show{display:flex}
.modalbox{background:#fff;border-radius:12px;padding:16px;max-width:100%;width:100%;box-shadow:0 8px 24px rgba(0,0,0,.3);position:relative;max-height:80vh;overflow-y:auto}
.modalbox h3{margin-bottom:8px;font-size:16px}
.modalbox textarea{width:100%;height:120px;border:1px solid #ccc;border-radius:8px;padding:8px;font-family:ui-monospace,monospace;font-size:12px;word-break:break-all;white-space:pre-wrap}
.modalbox .charcnt{font-size:12px;color:#777;margin:6px 0}
.modalbox .modalbtns{display:flex;gap:8px}
.modalbox .modalbtns button{flex:1;min-height:44px;border-radius:8px;border:1px solid #ccc;background:#fff;cursor:pointer;font-size:14px}
.modalbox .copybtn{background:#1a73e8;color:#fff;border-color:#1a73e8}
.closebtn{position:absolute;top:8px;right:12px;font-size:22px;background:none;border:none;cursor:pointer;color:#888}
.toast{position:fixed;top:16px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,.8);color:#fff;padding:10px 20px;border-radius:20px;font-size:13px;z-index:300;display:none}
.hidden{display:none}
</style>
</head>
<body>
<header>
<h1>记忆卡片人工闸门 · __SLUG__</h1>
<div class="instructions">关系范围：__RELATIONSHIP__</div>
<div class="meta">数据集 <span id="datasetid">__DATASET__</span> · 共 <span id="totalcnt">__TOTAL__</span> 条</div>
<div class="progressline">已决定 <span id="decidedcnt">0</span> / <span id="totalcnt2">__TOTAL__</span></div>
<div class="instructions">✅ 确认 = 进入 Tier-1 记忆册；🚫 剔除 = 不进入；✏️ 改写 = 修改标题后确认。点按当前状态可撤销。</div>
</header>
<div class="tabs" id="tabbar"></div>
<div id="cardlist"></div>
<div class="bottombar">
<span class="bottomcounts" id="bottomcounts">确认 0 · 剔除 0 · 待定 0</span>
<button id="genbtn">📋 生成回贴码</button>
</div>
<div class="modal" id="modal"><div class="modalbox">
<button class="closebtn" id="modalclose">×</button>
<h3 id="modalh3">回贴码</h3>
<div id="modalbody"></div>
</div></div>
<div class="toast" id="toast"></div>

<script>
"use strict";
var DATA = __DATA__;
var DATASET = "__DATASET__";
var SLUG = "__SLUG__";
var VERSION = DATA.length ? DATA[0].schema_version : 2;
var RELATIONSHIP = DATA.length ? DATA[0].relationship_id : null;
var STORE_KEY = "gate_" + DATASET;
var state = {};       // id -> {action:'confirm'|'reject'|'pending', title:?, note:?}

function findCard(id){for(var i=0;i<DATA.length;i++){if(DATA[i].id===id)return DATA[i]}return null}

function trimStr(s){return String(s==null?"":s).trim()}

function normState(raw){
    var s={action:raw.action,evidence_revision:raw.evidence_revision};
    if(raw.title!==undefined&&raw.title!==null&&trimStr(raw.title)!==""){s.title=trimStr(raw.title)}
    if(raw.note!==undefined&&raw.note!==null&&trimStr(raw.note)!==""){s.note=trimStr(raw.note)}
    return s;
}

function initState(){
    var stored=null;
    try{var raw=localStorage.getItem(STORE_KEY); if(raw){var obj=JSON.parse(raw); if(obj && obj.v===VERSION && obj.person===SLUG && obj.relationship_id===RELATIONSHIP && obj.dataset===DATASET && obj.state){stored=obj.state;}} }catch(e){}
    if(stored){
        for(var k in stored){ if(Object.prototype.hasOwnProperty.call(stored,k)){
            var c=findCard(k), s=stored[k];
            if(c && s && s.evidence_revision===c.evidence_revision && ["confirm","reject","pending"].indexOf(s.action)>=0){state[k]=normState(s);}
        } }
        showToast("草稿已恢复");
    }
    for(var i=0;i<DATA.length;i++){
        var c=DATA[i];
        if(!(c.id in state)){
            if(c.initial==="confirm"||c.initial==="reject"){
                state[c.id]={action:c.initial};
            } else {
                // pending initial; sensitive pre-flag rule: flagged pending cards start as reject
                if(c.flagged){ state[c.id]={action:"reject"}; }
                // otherwise no state entry = pending
            }
        }
    }
}

function cardState(id){
    var s=state[id];
    if(!s || s.action==="pending") return "pending";
    return s.action;
}

// true if this card currently has edits different from its base (for chip display)
function hasEdits(id){
    var s=state[id];
    if(!s || s.action!=="confirm") return false;
    var c=findCard(id);
    if(!c) return false;
    if(deltaTitle(id)!=="" && deltaTitle(id)!==trimStr(c.title)) return true;
    if(deltaNote(id)!=="") return true;
    return false;
}

function isEdited(id){
    var s=state[id];
    return s && s.action==="confirm" && hasEdits(id);
}

function saveDraft(){
    for(var k in state){var c=findCard(k);if(c){state[k].evidence_revision=c.evidence_revision;}}
    var out={v:VERSION,person:SLUG,relationship_id:RELATIONSHIP,dataset:DATASET,state:state};
    try{localStorage.setItem(STORE_KEY,JSON.stringify(out));}catch(e){}
}

function escapeHtmlObj(s){
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

// display title for UI prefill/rendering: live edited title if set, else user_title, else base title
function displayTitle(id){
    var c=findCard(id);
    if(!c) return "";
    var s=state[id];
    if(s && s.title!==undefined && s.title!==null && trimStr(s.title)!=="") return trimStr(s.title);
    if(c.user_title) return trimStr(c.user_title);
    return trimStr(c.title);
}

function displayNote(id){
    var c=findCard(id);
    if(!c) return "";
    var s=state[id];
    if(s && s.note!==undefined && s.note!==null && trimStr(s.note)!=="") return trimStr(s.note);
    return c.user_note ? trimStr(c.user_note) : "";
}

// delta title for export comparison ONLY: live edited title if set, else initial user_title, else ""
function deltaTitle(id){
    var c=findCard(id);
    if(!c) return "";
    var s=state[id];
    if(s && s.title!==undefined && s.title!==null && trimStr(s.title)!=="") return trimStr(s.title);
    if(c.user_title) return trimStr(c.user_title);
    return "";
}

function deltaNote(id){
    var c=findCard(id);
    if(!c) return "";
    var s=state[id];
    if(s && s.note!==undefined && s.note!==null && trimStr(s.note)!=="") return trimStr(s.note);
    return c.user_note ? trimStr(c.user_note) : "";
}

function renderCard(c){
    var id=c.id;
    var st=cardState(id);
    var cls="cardwrap state-"+st;
    if(isEdited(id)) cls="cardwrap state-edited";

    var editedChip="";
    if(isEdited(id)){ editedChip='<span class="editedchip">已改写</span>'; }

    var titleHtml=escapeHtmlObj(displayTitle(id));
    var noteHtml="";
    var effNote=displayNote(id);
    if(effNote){ noteHtml='<div class="excerpt" style="color:#888;font-size:12px">备注：'+escapeHtmlObj(effNote)+'</div>'; }

    var confirmCls = (st==="confirm")?"active":"";
    var rejectCls = (st==="reject")?"active":"";
    var editCls = (isEdited(id))?"active":"";

    return '<div class="'+cls+'" data-id="'+escapeHtmlObj(id)+'">'+
      '<div class="cardtop"><span class="date">'+escapeHtmlObj(c.date)+'</span><span class="chip">'+escapeHtmlObj(c.kind_label)+'</span>'+editedChip+'</div>'+
      '<div class="title">'+titleHtml+'</div>'+
      c.flagged_html+
      '<div class="excerptlist">'+c.excerpts_html+'</div>'+
      noteHtml+
      '<div class="actions">'+
        '<button class="actbtn confirm-btn '+confirmCls+'" data-act="confirm" type="button">✅ 确认</button>'+
        '<button class="actbtn edit-btn '+editCls+'" data-act="edit" type="button">✏️ 改写</button>'+
        '<button class="actbtn reject-btn '+rejectCls+'" data-act="reject" type="button">🚫 剔除</button>'+
      '</div>'+
      '<div class="editarea hidden" data-editarea="1">'+
        '<textarea data-titleinput="1" placeholder="标题（留空=原标题）">'+escapeHtmlObj(displayTitle(id))+'</textarea>'+
        '<input type="text" data-noteinput="1" placeholder="备注，可空" value="'+escapeHtmlObj(effNote)+'">'+
        '<div class="editbtns"><button class="savebtn" data-saveedit="1" type="button">保存</button><button data-canceledit="1" type="button">取消</button></div>'+
      '</div>'+
    '</div>';
}


function render(){
    var list=document.getElementById("cardlist");
    var htmls="";
    var arr=DATA.slice();
    arr.sort(function(a,b){ if(a.date<b.date)return -1; if(a.date>b.date)return 1; return a.id<b.id?-1:1; });
    var counts={all:arr.length,pending:0,confirm:0,reject:0,flag:0};
    var shown=[];
    for(var i=0;i<arr.length;i++){ var st=cardState(arr[i].id); if(st==="pending")counts.pending++; else if(st==="confirm")counts.confirm++; else if(st==="reject")counts.reject++; }
    for(var j=0;j<arr.length;j++){ if(arr[j].flagged_html){ counts.flag++; } }
    var currentTab=document.body.getAttribute("data-tab")||"all";
    for(var k=0;k<arr.length;k++){
        var c=arr[k];
        var st2=cardState(c.id);
        var show=false;
        if(currentTab==="all")show=true;
        else if(currentTab==="pending"&&st2==="pending")show=true;
        else if(currentTab==="confirm"&&st2==="confirm")show=true;
        else if(currentTab==="reject"&&st2==="reject")show=true;
        else if(currentTab==="flag"&&c.flagged_html)show=true;
        if(show){ shown.push(c); }
    }
    for(var m=0;m<shown.length;m++){ htmls+=renderCard(shown[m]); }
    list.innerHTML=htmls;

    // tabs
    var tabHtml='<div class="tab'+(currentTab==="all"?" active":"")+'" data-tab="all">全部 <span class="cnt">'+counts.all+'</span></div>'+
        '<div class="tab'+(currentTab==="pending"?" active":"")+'" data-tab="pending">待定 <span class="cnt">'+counts.pending+'</span></div>'+
        '<div class="tab'+(currentTab==="confirm"?" active":"")+'" data-tab="confirm">已确认 <span class="cnt">'+counts.confirm+'</span></div>'+
        '<div class="tab'+(currentTab==="reject"?" active":"")+'" data-tab="reject">已剔除 <span class="cnt">'+counts.reject+'</span></div>'+
        '<div class="tab'+(currentTab==="flag"?" active":"")+'" data-tab="flag">⚠️敏感 <span class="cnt">'+counts.flag+'</span></div>';
    document.getElementById("tabbar").innerHTML=tabHtml;

    var decided=counts.confirm+counts.reject;
    document.getElementById("decidedcnt").textContent=decided;
    document.getElementById("bottomcounts").textContent="确认 "+counts.confirm+" · 剔除 "+counts.reject+" · 待定 "+counts.pending;
}

function showToast(msg){
    var t=document.getElementById("toast");
    t.textContent=msg;
    t.style.display="block";
    setTimeout(function(){t.style.display="none";},2000);
}

function setState(id,action){
    var c=findCard(id);
    if(action==="pending"){
        // explicit revert to undecided
        state[id]={action:"pending"};
    } else {
        var prev=state[id]||{};
        var ns={action:action};
        // keep title/note when possible (for undo or re-confirm)
        if(action==="confirm"){
            if(prev.title!==undefined){ns.title=prev.title}
            if(prev.note!==undefined){ns.note=prev.note}
        }
        state[id]=ns;
    }
    saveDraft();
    render();
}

function toggleExpand(btn){
    var btnText=btn.textContent.trim();
    var exText=btn.previousElementSibling;
    if(!exText) return;
    var head=exText.querySelector(".exc-head");
    var tail=exText.querySelector(".exc-tail");
    var ell=exText.querySelector(".exc-ellipsis");
    if(btnText==="展开"){
        if(tail){tail.style.display="inline";}
        if(ell){ell.style.display="none";}
        btn.textContent="收起";
    } else {
        if(tail){tail.style.display="none";}
        if(ell){ell.style.display="";}
        btn.textContent="展开";
    }
}

document.addEventListener("click",function(ev){
    var btn=ev.target.closest(".actbtn");
    if(btn){
        var card=ev.target.closest(".cardwrap");
        var id=card.getAttribute("data-id");
        var act=btn.getAttribute("data-act");
        var cur=cardState(id);
        if(act==="confirm"){
            if(cur==="confirm"){ setState(id,"pending"); }
            else { setState(id,"confirm"); }
            var ea=card.querySelector("[data-editarea='1']"); if(ea){ea.classList.add("hidden");}
        } else if(act==="reject"){
            if(cur==="reject"){ setState(id,"pending"); }
            else { setState(id,"reject"); }
            var ea2=card.querySelector("[data-editarea='1']"); if(ea2){ea2.classList.add("hidden");}
        } else if(act==="edit"){
            var ea3=card.querySelector("[data-editarea='1']");
            if(ea3){ ea3.classList.toggle("hidden"); }
        }
        return;
    }

    var saveBtn=ev.target.closest("[data-saveedit='1']");
    if(saveBtn){
        var card2=ev.target.closest(".cardwrap");
        var id2=card2.getAttribute("data-id");
        var tinput=card2.querySelector("[data-titleinput='1']");
        var ninput=card2.querySelector("[data-noteinput='1']");
        var title=trimStr(tinput?tinput.value:"");
        var note=trimStr(ninput?ninput.value:"");
        var ns={action:"confirm"};
        if(title!==""){ns.title=title;}
        if(note!==""){ns.note=note;}
        state[id2]=ns;
        saveDraft();
        card2.querySelector("[data-editarea='1']").classList.add("hidden");
        render();
        return;
    }

    var cancelBtn=ev.target.closest("[data-canceledit='1']");
    if(cancelBtn){
        var card3=ev.target.closest(".cardwrap");
        var ea4=card3.querySelector("[data-editarea='1']");
        if(ea4){ea4.classList.add("hidden");}
        return;
    }

    var tab=ev.target.closest(".tab");
    if(tab){
        var t=tab.getAttribute("data-tab");
        document.body.setAttribute("data-tab",t);
        render();
        return;
    }

    var expand=ev.target.closest(".expandbtn");
    if(expand){
        toggleExpand(expand);
        return;
    }

    var gen=ev.target.closest("#genbtn");
    if(gen){
        openModal();
        return;
    }

    var copyBtn=ev.target.closest("[data-copybtn]");
    if(copyBtn){
        var ta=document.getElementById("pastecode");
        var code=ta.value;
        if(navigator.clipboard && navigator.clipboard.writeText){
            navigator.clipboard.writeText(code).then(function(){showToast("已复制");},function(){fallbackCopy(code);});
        } else {
            fallbackCopy(code);
        }
        return;
    }

    var close=ev.target.closest("#modalclose");
    if(close){closeModal();return;}

    var mk=ev.target.closest(".modal");
    if(mk && ev.target===mk){closeModal();}
});

function fallbackCopy(text){
    var ta=document.getElementById("pastecode");
    ta.removeAttribute("readonly");
    ta.focus();ta.select();
    try{document.execCommand("copy");showToast("已复制");}catch(e){showToast("复制失败，请手动复制");}
    ta.setAttribute("readonly","readonly");
}

function closeModal(){
    document.getElementById("modal").classList.remove("show");
}

function computeDecisions(){
    var decisions=[];
    for(var i=0;i<DATA.length;i++){
        var c=DATA[i];
        var id=c.id;
        var s=state[id];
        var action=s?cardState(id):"pending";
        var dTitle=deltaTitle(id);
        var dNote=deltaNote(id);
        var initAction=c.initial||"pending";
        var initTitle=c.user_title?trimStr(c.user_title):"";
        var initNote=c.user_note?trimStr(c.user_note):"";
        if(action===initAction && dTitle===initTitle && dNote===initNote) continue;
        if(action==="pending"){
            decisions.push({id:id,action:"pending",evidence_revision:c.evidence_revision});
            continue;
        }
        var obj={id:id,action:action,evidence_revision:c.evidence_revision};
        // For confirm: include title only when it differs from base title, note if non-empty
        if(action==="confirm"){
            if(dTitle!=="" && dTitle!==trimStr(c.title)){
                obj.title=dTitle;
            }
            if(dNote!==""){
                obj.note=dNote;
            }
        }
        decisions.push(obj);
    }
    return decisions;
}

function openModal(){
    var decisions=computeDecisions();
    var payload={v:VERSION,person:SLUG,relationship_id:RELATIONSHIP,page:1,source_dataset:DATASET,total:DATA.length,decisions:decisions};
    var code=JSON.stringify(payload);
    document.getElementById("modalh3").textContent = decisions.length===0?"尚无改动":"回贴码";
    if(decisions.length===0){
        document.getElementById("modalbody").innerHTML='<p style="color:#999;margin-bottom:8px">尚无改动</p>';
    } else {
        document.getElementById("modalbody").innerHTML='<textarea id="pastecode" readonly>'+escapeHtmlObj(code)+'</textarea><div class="charcnt">共 '+code.length+' 字符</div><div class="modalbtns"><button class="copybtn" data-copybtn="1" type="button">📋 复制</button><button id="modalclose2" type="button">关闭</button></div>';
        var c2=document.getElementById("modalclose2");
        c2.addEventListener("click",function(){closeModal();});
    }
    document.getElementById("modal").classList.add("show");
}

initState();
render();
</script>
</body>
</html>
"""
    template = template.replace("__SLUG__", slug_html)
    template = template.replace('__RELATIONSHIP__', escape_html(cards[0].get('relationship_id') or 'legacy' if cards else ''))
    template = template.replace("__DATASET__", escape_html(source_dataset))
    template = template.replace("__TOTAL__", str(total))
    template = template.replace("__DATA__", payload)
    return template


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a gate-review HTML page.")
    parser.add_argument("--person", required=True)
    parser.add_argument('--relationship-id', required=True)
    parser.add_argument('--legacy-freeze', type=Path)
    parser.add_argument("--candidates")
    parser.add_argument("--patterns")
    parser.add_argument("--out")
    parser.add_argument("--max-kb", type=int, default=900)
    args = parser.parse_args()

    slug = args.person.strip().lower()
    if not VALID_SLUG_RE.match(slug):
        die("error: invalid slug")

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    people_root = os.path.join(repo_root, "people")

    cand_path = args.candidates or os.path.join(people_root, slug, "memories", "candidates.jsonl")
    pat_path = args.patterns or os.path.join(repo_root, "tools", "sensitive_patterns.json")
    out_path = args.out or os.path.join(people_root, slug, "memories", "gate_page.html")

    cand_path = os.path.abspath(cand_path)
    pat_path = os.path.abspath(pat_path)
    out_path = os.path.abspath(out_path)

    raw_root = os.path.abspath(os.path.join(people_root, slug, "raw"))
    for p in (cand_path, pat_path, out_path):
        if p == raw_root or p.startswith(raw_root + os.sep):
            die("error: refusing to touch people/<slug>/raw/")

    if not os.path.isfile(cand_path):
        die("error: candidates file not found: " + str(cand_path))

    candidates = load_candidates(cand_path)
    if not candidates:
        die("error: no candidates")

    try:
        preflight_outputs([out_path], [cand_path, pat_path, args.legacy_freeze])
        if candidates[0].get('schema_version', 1) == 2:
            source_dataset = dataset_fingerprint(candidates)
            if any(c['person'] != slug or c['relationship_id'] != args.relationship_id for c in candidates):
                raise ValueError('scope mismatch')
        else:
            source_dataset = validate_legacy_freeze(candidates, Path(cand_path).read_bytes(),
                                                    args.legacy_freeze, slug, args.relationship_id)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        die('error: invalid dataset: ' + str(exc))

    patterns = load_patterns(pat_path)

    cards = []
    flag_count = 0
    for c in candidates:
        flagged_names = build_flag_matches(c, patterns)
        flagged = bool(flagged_names)
        if flagged:
            flag_count += 1
        init_state = initial_state_for(c)
        card = build_card(c, flagged_names, init_state)
        card['person'] = slug
        card['relationship_id'] = args.relationship_id
        cards.append(card)

    total = len(cards)
    html_content = render_page(slug, cards, source_dataset, total)
    size_bytes = len(html_content.encode("utf-8"))
    size_kb = round(size_bytes / 1024)

    max_kb = args.max_kb
    if size_kb > max_kb:
        die(f"error: page exceeds max-kb ({size_kb}KB); split not implemented, raise --max-kb consciously")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Print out= as repo-relative posix path when under repo root, else absolute
    try:
        rel = os.path.relpath(out_path, repo_root)
        if not rel.startswith(".."):
            out_display = rel.replace(os.sep, "/")
        else:
            out_display = out_path.replace(os.sep, "/")
    except ValueError:
        out_display = out_path.replace(os.sep, "/")

    ascii_print(f"cards={total} flagged={flag_count} size_kb={size_kb} out={out_display}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
