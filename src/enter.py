"""Build a PRIVATE, local-only prediction input tool: local/enter.html

This is the editing counterpart to the public read-only site. It is written to
``local/`` which is git-ignored and never part of the deployed artifact (the
GitHub Pages workflow only runs ``score`` + ``site`` and uploads ``output/``), so
it exists only on your machine — nobody else can see or use it.

It embeds the current Round-of-32 fixtures + bracket wiring and renders a guided
picker: choose the winner of every Round-of-32 match, the winners flow into the
Round of 16, and so on up to the champion, plus a third-place pick. This guarantees
a structurally consistent one-shot bracket.

It produces exactly the JSON the scoring engine expects. Download (or copy) the
file, drop it into ``data/predictions/bracket/<slug>.json``, then commit + push so
the public site shows your bracket (read-only) for everyone.

  python -m src.enter            # build local/enter.html
"""
import json
import sys
import webbrowser

from .common import DATA_DIR, FIXTURES_DIR, ROOT, load_json, load_models_config
from .flags import FLAGS

LOCAL_DIR = ROOT / "local"


def gather():
    cfg = load_models_config()
    human = cfg.get("human") or {"slug": "you", "name": "You"}
    fx = load_json(FIXTURES_DIR / "R32.json") or {}
    r32 = [{"id": m["id"], "home": m.get("home"), "away": m.get("away")}
           for m in fx.get("matches", [])]
    bracket = load_json(DATA_DIR / "bracket.json") or {}
    return {
        "human": {"slug": human.get("slug", "you"), "name": human.get("name", "You")},
        "bracket": {"slots": bracket.get("slots", {}), "r32": r32},
        "flags": FLAGS,
    }


def build_html(data):
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("/*__DATA__*/", "window.DATA = " + blob + ";")


def main(argv=None):
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    out = LOCAL_DIR / "enter.html"
    out.write_text(build_html(gather()), encoding="utf-8")
    print("Wrote %s" % out)
    if "--open" in (argv or []):
        webbrowser.open(out.as_uri())


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Enter your bracket — private</title>
<style>
  :root{
    color-scheme:dark;
    --bg:#15110b; --surface:#1e1912; --surface-2:#251f16;
    --line:#2f2719; --line-2:#3d3322;
    --ink:#f1ebdd; --muted:#aa9f89; --muted-2:#82775f;
    --gold:#e3b75f; --gold-dim:#c9a04a; --gold-soft:#f1d8a0;
    --green:#6fd7a3;
    --serif:ui-serif,"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,"Times New Roman",serif;
    --ease:cubic-bezier(.2,.7,.2,1);
  }
  *{ box-sizing:border-box; }
  body{ margin:0; font-family:var(--serif); color:var(--ink); letter-spacing:.004em;
        background:radial-gradient(1100px 560px at 50% -180px,#2c2213,transparent 70%), var(--bg);
        background-attachment:fixed; }
  .wrap{ max-width:1100px; margin:0 auto; padding:34px 22px 96px; }
  h1{ font-size:1.8rem; font-weight:600; margin:0 0 6px; letter-spacing:-.02em; }
  .lock{ display:inline-block; font-size:.72rem; font-weight:800; text-transform:uppercase;
         letter-spacing:.08em; color:#15110b; background:var(--gold); padding:3px 9px;
         border-radius:999px; vertical-align:middle; margin-left:8px;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  .sub{ color:var(--muted); font-style:italic; font-size:.96rem; margin-bottom:20px; }
  .who{ color:var(--gold-soft); font-style:normal; }
  .note{ font-size:.86rem; color:var(--muted); font-style:italic; margin:0 0 16px; }
  .warn{ background:rgba(227,183,95,.1); border:1px solid var(--line-2); color:var(--gold-soft);
         border-radius:10px; padding:10px 13px; font-size:.86rem; font-style:normal; margin:0 0 16px; }
  .tn{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .flag{ width:21px; height:15px; border-radius:2px; object-fit:cover; flex:none;
         background:var(--surface-2); box-shadow:0 0 0 1px rgba(0,0,0,.4),0 1px 2px rgba(0,0,0,.4); }
  /* bracket picker */
  .bracket{ display:flex; overflow-x:auto; padding-bottom:14px; }
  .col{ display:flex; flex-direction:column; min-width:194px; padding:0 12px; }
  .col:not(:last-child){ border-right:1px solid var(--line); }
  .col h3{ font-size:.7rem; text-transform:uppercase; letter-spacing:.09em; color:var(--gold-dim);
           margin:0 0 10px; text-align:center; font-weight:700; }
  .col-body{ flex:1; display:flex; flex-direction:column; justify-content:space-around; gap:8px; }
  .pmatch{ display:flex; flex-direction:column; gap:4px; background:var(--surface);
           border:1px solid var(--line-2); border-radius:10px; padding:5px; }
  .opt{ display:flex; align-items:center; gap:8px; width:100%; text-align:left; cursor:pointer;
        background:var(--surface-2); color:var(--ink); border:1px solid transparent; border-radius:7px;
        padding:7px 9px; font-family:var(--serif); font-size:.86rem; transition:all .15s var(--ease); }
  .opt:hover:not(:disabled){ border-color:var(--gold-dim); }
  .opt.sel{ background:rgba(227,183,95,.16); border-color:var(--gold); color:var(--gold-soft); font-weight:700; }
  .opt.empty,.opt:disabled{ color:var(--muted-2); cursor:default; font-style:italic; }
  .champ{ margin-top:14px; font-size:1.05rem; }
  .champ .tm{ display:inline-flex; align-items:center; gap:9px; }
  .champ b{ color:var(--gold-soft); }
  /* output */
  .out{ margin-top:26px; border-top:1px solid var(--line); padding-top:20px; }
  .path{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.84rem; color:var(--gold-soft);
         background:var(--surface); border:1px solid var(--line-2); border-radius:8px; padding:8px 11px;
         display:inline-block; margin:6px 0 12px; }
  pre{ background:#0f0c08; border:1px solid var(--line); border-radius:10px; padding:14px; overflow:auto;
       font-size:.8rem; color:#d8d0bf; max-height:320px; }
  .btns{ display:flex; gap:10px; flex-wrap:wrap; margin:6px 0 4px; }
  button.act{ background:var(--gold); color:#15110b; border:0; border-radius:9px; padding:10px 18px;
        font-weight:700; cursor:pointer; font-family:var(--serif); font-size:.95rem; }
  button.act.ghost{ background:transparent; color:var(--gold-soft); box-shadow:inset 0 0 0 1px var(--line-2); }
  button.act:disabled{ opacity:.4; cursor:not-allowed; }
  .status{ font-size:.86rem; color:var(--muted); margin-left:4px; align-self:center; }
  .status.ok{ color:var(--green); } .status.err{ color:#e08f7a; }
</style></head>
<body><div class="wrap">
  <h1>Enter your bracket <span class="lock">Private · local only</span></h1>
  <div class="sub">Editing as <span class="who" id="who"></span> — one-shot bracket. This page lives only on your machine and is never deployed.</div>
  <div id="br"></div>
</div>
<script>
/*__DATA__*/
(function(){
  var D=window.DATA, H=D.human;
  document.getElementById('who').textContent=H.name+' ('+H.slug+')';

  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function normTeam(s){ return String(s==null?'':s).normalize('NFD').replace(/[\u0300-\u036f]/g,'')
    .toLowerCase().replace(/[^a-z0-9]+/g,''); }
  var FLAGN={}; (function(){ var f=D.flags||{}; for(var k in f){ FLAGN[normTeam(k)]=f[k]; } })();
  function flagImg(t){ var c=FLAGN[normTeam(t)]; if(!c) return '';
    return '<img class="flag" alt="" width="21" height="15" '+
      'src="https://flagcdn.com/28x21/'+c+'.png" srcset="https://flagcdn.com/56x42/'+c+'.png 2x">'; }
  function nowISO(){ return new Date().toISOString(); }
  function isPlaceholder(t){ if(!t) return true; return /^(winner|runner|runners|runner-?up|3rd|third|tbd|best )/i.test(String(t).trim()); }
  function download(name,text){ var a=document.createElement('a');
    a.href='data:application/json;charset=utf-8,'+encodeURIComponent(text);
    a.download=name; document.body.appendChild(a); a.click(); a.remove(); }
  function outBlock(id,path){
    return '<div class="out"><div>Save this file to <span class="path">'+esc(path)+'</span>'+
      ' then commit + push so it shows on the public site.</div>'+
      '<div class="btns"><button class="act" id="'+id+'dl" disabled>Download '+esc(H.slug)+'.json</button>'+
      '<button class="act ghost" id="'+id+'cp" disabled>Copy JSON</button>'+
      '<span class="status" id="'+id+'st"></span></div>'+
      '<pre id="'+id+'pre">Fill everything in to generate the file.</pre></div>';
  }
  function wireOut(id,path,build){
    var dl=document.getElementById(id+'dl'), cp=document.getElementById(id+'cp'),
        st=document.getElementById(id+'st'), pre=document.getElementById(id+'pre');
    function refresh(){
      var r=build();
      if(r.error){ dl.disabled=cp.disabled=true; st.className='status err'; st.textContent=r.error;
        pre.textContent=r.partial||'Fill everything in to generate the file.'; return; }
      var text=JSON.stringify(r.obj,null,2);
      pre.textContent=text; dl.disabled=cp.disabled=false; st.className='status'; st.textContent='';
      dl.onclick=function(){ download(H.slug+'.json',text); st.className='status ok';
        st.textContent='Downloaded — move it to '+path; };
      cp.onclick=function(){ if(navigator.clipboard){ navigator.clipboard.writeText(text).then(function(){
        st.className='status ok'; st.textContent='Copied to clipboard.'; }); } };
    }
    return refresh;
  }

  /* ===================== One-shot bracket ===================== */
  var SLOTS=D.bracket.slots||{}, R32M=D.bracket.r32||[];
  var r32byId={}; R32M.forEach(function(m){ r32byId[m.id]=m; });
  function slotIds(p){ return Object.keys(SLOTS).filter(function(k){return k.indexOf(p+'-')===0;})
    .sort(function(a,b){ return (+a.split('-')[1])-(+b.split('-')[1]); }); }
  var R32=R32M.map(function(m){return m.id;});
  var R16=slotIds('R16'), QF=slotIds('QF'), SF=slotIds('SF'), FIN=slotIds('F');
  var DOWN=[].concat(R16,QF,SF,FIN);
  var picks={};

  function teamsFor(slot){
    if(slot.indexOf('R32-')===0){ var m=r32byId[slot]; return m?[m.home,m.away]:[undefined,undefined]; }
    var fe=SLOTS[slot]||[]; return [picks[fe[0]], picks[fe[1]]];
  }
  function thirdCands(){
    if(SF.length<2) return null;
    if(picks[SF[0]]===undefined||picks[SF[1]]===undefined) return null;
    var s1=teamsFor(SF[0]), s2=teamsFor(SF[1]);
    if(s1[0]===undefined||s1[1]===undefined||s2[0]===undefined||s2[1]===undefined) return null;
    var l1=(picks[SF[0]]===s1[0])?s1[1]:s1[0];
    var l2=(picks[SF[1]]===s2[0])?s2[1]:s2[0];
    return [l1,l2];
  }
  function prune(){
    var changed=true;
    while(changed){ changed=false;
      DOWN.forEach(function(slot){
        if(picks[slot]!==undefined){ var t=teamsFor(slot);
          if(t[0]===undefined||t[1]===undefined||(picks[slot]!==t[0]&&picks[slot]!==t[1])){
            delete picks[slot]; changed=true; } }
      });
      if(picks.third!==undefined){ var c=thirdCands();
        if(!c||c.indexOf(picks.third)<0){ delete picks.third; changed=true; } }
    }
  }
  function optBtn(slot,team){
    if(team===undefined||team===null||team===''){ return '<button class="opt empty" disabled>—</button>'; }
    var sel=picks[slot]===team;
    return '<button class="opt'+(sel?' sel':'')+'" data-slot="'+esc(slot)+'" data-team="'+esc(team)+'">'+
      flagImg(team)+'<span class="tn">'+esc(team)+'</span></button>';
  }
  function pickCard(slot){ var t=teamsFor(slot);
    return '<div class="pmatch">'+optBtn(slot,t[0])+optBtn(slot,t[1])+'</div>'; }
  function column(title,ids){
    var body=ids.map(function(s){ return pickCard(s); }).join('');
    return '<div class="col"><h3>'+esc(title)+'</h3><div class="col-body">'+body+'</div></div>';
  }
  function bracketComplete(){
    var need=[].concat(R32,DOWN);
    for(var i=0;i<need.length;i++){ if(picks[need[i]]===undefined) return false; }
    return picks.third!==undefined;
  }
  function buildBracket(){
    if(!R32.length) return {error:'No Round-of-32 fixtures found in data/fixtures/R32.json.'};
    if(!bracketComplete()){
      var done=[].concat(R32,DOWN).filter(function(s){return picks[s]!==undefined;}).length;
      var tot=R32.length+DOWN.length+1;
      return {error:'Pick all winners to generate ('+(done+(picks.third!==undefined?1:0))+'/'+tot+' done).'};
    }
    var rounds={ R16:R32.map(function(s){return picks[s];}),
                 QF:R16.map(function(s){return picks[s];}),
                 SF:QF.map(function(s){return picks[s];}),
                 F:SF.map(function(s){return picks[s];}),
                 champion:picks[FIN[0]], third:picks.third };
    return {obj:{ model:'human', slug:H.slug, name:H.name, collected_at:nowISO(),
                  rounds:rounds, raw:'' }};
  }
  var refreshBracket=null;
  function renderBracket(){
    var el=document.getElementById('br');
    if(!R32.length){ el.innerHTML='<div class="warn">No Round-of-32 fixtures yet. Fill data/fixtures/R32.json and rebuild (python -m src.enter).</div>'; return; }
    var hasPlaceholders=R32M.some(function(m){ return isPlaceholder(m.home)||isPlaceholder(m.away); });
    var champ=picks[FIN[0]];
    var third=picks.third, tc=thirdCands();
    var html=(hasPlaceholders?'<div class="warn">Some Round-of-32 slots still show group-position placeholders (e.g. “Winner E”). Fill the real teams in data/fixtures/R32.json and rebuild for flags + real names.</div>':'')+
      '<div class="note">Pick the winner of each match; winners flow to the next round automatically. Changing an earlier pick clears the picks that depended on it.</div>'+
      '<div class="bracket">'+column('Round of 32',R32)+column('Round of 16',R16)+
      column('Quarter-finals',QF)+column('Semi-finals',SF)+column('Final',FIN)+'</div>'+
      '<div class="champ">Champion: '+(champ?('<span class="tm">'+flagImg(champ)+'<b>'+esc(champ)+'</b></span>'):'<span class="muted-2" style="color:var(--muted-2)">— pick the final —</span>')+'</div>'+
      '<div class="champ" style="margin-top:8px">Third place: '+
        (tc? ('<span class="pmatch" style="display:inline-flex;flex-direction:row;gap:6px;vertical-align:middle">'+optBtn('third',tc[0])+optBtn('third',tc[1])+'</span>')
           : '<span style="color:var(--muted-2)">— decide both semi-finals first —</span>')+'</div>'+
      outBlock('b','data/predictions/bracket/'+H.slug+'.json');
    el.innerHTML=html;
    el.querySelectorAll('.opt[data-slot]').forEach(function(btn){
      btn.onclick=function(){ var slot=btn.getAttribute('data-slot'), team=btn.getAttribute('data-team');
        if(slot==='third'){ picks.third=team; } else { picks[slot]=team; prune(); }
        renderBracket(); };
    });
    refreshBracket=wireOut('b','data/predictions/bracket/'+H.slug+'.json',buildBracket);
    refreshBracket();
  }

  /* ===================== init ===================== */
  renderBracket();
})();
</script>
</body></html>
"""


if __name__ == "__main__":
    main(sys.argv[1:])
