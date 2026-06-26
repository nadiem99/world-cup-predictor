"""Generate a single self-contained static site: output/index.html

Four views (tabs): Leaderboard (Design-Arena inspired, sortable, with per-round
sparklines), Bracket (connected knockout tree), a browsable Predictions archive, and
About/methodology. All data is embedded as JSON and rendered client-side with vanilla
JS, so the file works opened locally (file://) or hosted anywhere. No dependencies, no
external assets.

  python -m src.site
"""
import json
import sys
from datetime import datetime, timezone

from .common import (
    FIXTURES_DIR, OUTPUT_DIR, PRED_DIR, ROUND_LABELS, ROUND_ORDER,
    load_json, load_models_config,
)
from . import score as scoring


def _meta_map():
    cfg = load_models_config()
    meta = {}
    for m in cfg.get("models", []):
        meta[m["slug"]] = {"name": m["name"], "provider": m.get("provider", "")}
    h = cfg.get("human")
    if h:
        meta[h["slug"]] = {"name": h.get("name", "You"), "provider": h.get("provider", "You")}
    return meta


def _info(slug, meta, pred):
    m = meta.get(slug)
    if m:
        return m["name"], m["provider"]
    return pred.get("name", slug), pred.get("provider", "")


def _round_predictions(round_label, meta):
    out = []
    d = PRED_DIR / round_label
    if not d.exists():
        return out
    results = scoring._round_results(round_label)
    for f in sorted(d.glob("*.json")):
        if f.name.endswith(".error.json"):
            continue
        pred = load_json(f) or {}
        slug = pred.get("slug", f.stem)
        name, provider = _info(slug, meta, pred)
        rows, total = [], 0
        for p in pred.get("predictions", []):
            r = results.get(p.get("id"))
            entry = {"id": p.get("id"), "home": p.get("home"), "away": p.get("away"),
                     "ph": p.get("home_goals"), "pa": p.get("away_goals"),
                     "adv": p.get("advances", "")}
            if r:
                pts, adv_ok, sc_ok = scoring._score_match(p, r)
                entry.update({"rh": r["home_goals"], "ra": r["away_goals"],
                              "radv": r.get("advances", ""), "pts": pts,
                              "adv_ok": adv_ok, "sc_ok": sc_ok})
                total += pts
            rows.append(entry)
        out.append({"slug": slug, "name": name, "provider": provider,
                    "predictions": rows, "total": total, "scored": bool(results)})
    out.sort(key=lambda x: (-x["total"], x["name"].lower()))
    return out


def _bracket_predictions(meta):
    out = []
    d = PRED_DIR / "bracket"
    if not d.exists():
        return out
    detail_by_slug = {r["slug"]: r for r in scoring.compute_bracket()["rows"]}
    for f in sorted(d.glob("*.json")):
        if f.name.endswith(".error.json"):
            continue
        pred = load_json(f) or {}
        slug = pred.get("slug", f.stem)
        name, provider = _info(slug, meta, pred)
        db = detail_by_slug.get(slug, {})
        out.append({"slug": slug, "name": name, "provider": provider,
                    "rounds": pred.get("rounds", {}),
                    "points": db.get("points", 0), "detail": db.get("detail", {})})
    out.sort(key=lambda x: (-x["points"], x["name"].lower()))
    return out


def _actual_bracket_display():
    def adv(rl):
        return [m.get("advances") for m in scoring._round_results(rl).values()
                if m.get("advances")]
    champ, third = adv("F"), adv("TP")
    return {"R16": adv("R32"), "QF": adv("R16"), "SF": adv("QF"), "F": adv("SF"),
            "champion": champ[0] if champ else None,
            "third": third[0] if third else None}


def gather_data():
    meta = _meta_map()
    scores = scoring.get_scores()

    # enrich leaderboard rows with provider
    for row in scores["main"]["rows"]:
        row["provider"] = meta.get(row["slug"], {}).get("provider", "")
    for row in scores["bracket"]["rows"]:
        row["provider"] = meta.get(row["slug"], {}).get("provider", "")

    fixtures, results, round_preds = {}, {}, {}
    for rl in ROUND_ORDER:
        fx = load_json(FIXTURES_DIR / ("%s.json" % rl))
        if fx and fx.get("matches"):
            fixtures[rl] = [{"id": m["id"], "home": m.get("home"), "away": m.get("away")}
                            for m in fx["matches"]]
        res = scoring._round_results(rl)
        if res:
            results[rl] = {mid: {"home_goals": r["home_goals"], "away_goals": r["away_goals"],
                                 "advances": r.get("advances", "")} for mid, r in res.items()}
        rp = _round_predictions(rl, meta)
        if rp:
            round_preds[rl] = rp

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scoring": {"exact": scoring.EXACT_POINTS, "result": scoring.RESULT_POINTS,
                    "stage": scoring.BRACKET_STAGE_POINTS,
                    "champion": scoring.CHAMPION_BONUS, "third": scoring.THIRD_BONUS},
        "round_order": ROUND_ORDER,
        "round_labels": ROUND_LABELS,
        "leaderboard": scores["main"],
        "bracket_board": scores["bracket"],
        "actual_bracket": _actual_bracket_display(),
        "fixtures": fixtures,
        "results": results,
        "round_predictions": round_preds,
        "bracket_predictions": _bracket_predictions(meta),
    }


def build_html(data):
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("/*__DATA__*/", "window.DATA = " + blob + ";")


def main(argv=None):
    out = OUTPUT_DIR / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(gather_data()), encoding="utf-8")
    print("Wrote %s" % out)


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>World Cup 2026 — AI Models vs. Nadiem</title>
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
  html{ scroll-behavior:smooth; }
  body{ margin:0; font-family:var(--serif); color:var(--ink); letter-spacing:.004em;
        background:radial-gradient(1100px 560px at 50% -180px,#2c2213,transparent 70%),
                   radial-gradient(900px 500px at 90% 110%,#1f1a10,transparent 60%), var(--bg);
        background-attachment:fixed; }
  a{ color:var(--gold); text-decoration:none; transition:color .2s var(--ease); }
  a:hover{ color:var(--gold-soft); }
  ::selection{ background:rgba(227,183,95,.28); }
  *::-webkit-scrollbar{ height:10px; width:10px; }
  *::-webkit-scrollbar-thumb{ background:var(--line-2); border-radius:10px; }
  *::-webkit-scrollbar-thumb:hover{ background:var(--gold-dim); }
  *::-webkit-scrollbar-track{ background:transparent; }
  .wrap{ max-width:1060px; margin:0 auto; padding:40px 22px 96px; }
  header{ animation:fadeUp .8s var(--ease) both; }
  header h1{ font-size:2.15rem; font-weight:600; margin:0 0 8px; letter-spacing:-.02em; line-height:1.1; }
  header .sub{ color:var(--muted); font-size:.96rem; font-style:italic; }
  .tabs{ display:flex; gap:4px; margin:30px 0 22px; border-bottom:1px solid var(--line);
         overflow-x:auto; animation:fadeUp .8s var(--ease) .08s both; }
  .tab{ padding:11px 18px; cursor:pointer; color:var(--muted); font-weight:600; font-size:1rem;
        border-bottom:2px solid transparent; user-select:none; white-space:nowrap;
        transition:color .22s var(--ease), border-color .22s var(--ease); }
  .tab:hover{ color:var(--ink); }
  .tab.active{ color:var(--gold-soft); border-bottom-color:var(--gold); }
  .panel{ display:none; } .panel.active{ display:block; animation:panelFade .45s var(--ease) both; }
  .seg{ display:inline-flex; background:var(--surface); border:1px solid var(--line-2); border-radius:11px;
        padding:3px; margin-bottom:18px; gap:2px; }
  .seg button{ background:none; border:0; color:var(--muted); padding:8px 16px; border-radius:8px;
        cursor:pointer; font-weight:600; font-size:.9rem; font-family:var(--serif);
        transition:background .2s var(--ease), color .2s var(--ease); }
  .seg button:hover{ color:var(--ink); }
  .seg button.on{ background:var(--surface-2); color:var(--gold-soft); box-shadow:inset 0 0 0 1px var(--line-2); }
  select{ background:var(--surface); color:var(--ink); border:1px solid var(--line-2); border-radius:9px;
          padding:9px 12px; font-size:.94rem; font-family:var(--serif); margin:0 8px 16px 0;
          transition:border-color .2s var(--ease); }
  select:hover,select:focus{ border-color:var(--gold-dim); outline:none; }
  .tw{ overflow-x:auto; border-radius:14px; }
  table{ width:100%; border-collapse:collapse; background:var(--surface); border:1px solid var(--line);
         border-radius:14px; overflow:hidden; font-size:.97rem; }
  th,td{ padding:13px 14px; border-bottom:1px solid var(--line); text-align:center; }
  th{ background:var(--surface-2); color:var(--muted); font-size:.7rem; text-transform:uppercase;
      letter-spacing:.09em; font-weight:700; }
  th.sortable{ cursor:pointer; transition:color .2s var(--ease); }
  th.sortable:hover{ color:var(--gold-soft); }
  td.l,th.l{ text-align:left; } tr:last-child td{ border-bottom:none; }
  td{ transition:background .22s var(--ease); }
  tbody tr:hover td, table tr:hover td{ background:rgba(227,183,95,.05); }
  tr.rank1 td{ background:linear-gradient(90deg,rgba(227,183,95,.14),transparent 75%); }
  tr.rank1:hover td{ background:linear-gradient(90deg,rgba(227,183,95,.2),transparent 75%); }
  .rk{ font-weight:700; color:var(--gold); width:36px; font-variant-numeric:tabular-nums; }
  .model{ display:flex; align-items:center; gap:11px; }
  .badge{ font-size:.62rem; font-weight:800; padding:3px 8px; border-radius:999px;
          color:#15110b; text-transform:uppercase; letter-spacing:.04em; white-space:nowrap;
          font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  .pts{ font-weight:700; color:var(--green); font-variant-numeric:tabular-nums; font-size:1.05rem; }
  .bar{ height:5px; border-radius:3px; background:linear-gradient(90deg,var(--green),var(--gold));
        opacity:.55; margin-top:5px; transition:width .5s var(--ease); }
  .muted{ color:var(--muted); }
  .empty{ padding:30px 22px; background:var(--surface); border:1px solid var(--line); border-radius:14px;
          color:var(--muted); text-align:center; font-style:italic; font-size:1.02rem; }
  p.copy{ color:#d8d0bf; line-height:1.78; max-width:680px; font-size:1.05rem; }
  p.copy strong{ color:var(--ink); }
  /* bracket tree */
  .bracket{ display:flex; overflow-x:auto; padding-bottom:14px; }
  .col{ display:flex; flex-direction:column; min-width:188px; padding:0 13px; }
  .col:not(:last-child){ border-right:1px solid var(--line); }
  .col h3{ font-size:.7rem; text-transform:uppercase; letter-spacing:.09em; color:var(--gold-dim);
           margin:0 0 10px; text-align:center; font-weight:700; }
  .col-body{ flex:1; display:flex; flex-direction:column; justify-content:space-around; }
  .match{ position:relative; background:var(--surface); border:1px solid var(--line-2); border-radius:11px;
          padding:9px 11px; margin:6px 0; font-size:.88rem;
          transition:transform .2s var(--ease), border-color .2s var(--ease), box-shadow .2s var(--ease); }
  .match:hover{ transform:translateY(-3px); border-color:var(--gold-dim);
          box-shadow:0 12px 28px rgba(0,0,0,.5); z-index:2; }
  .col:not(:last-child) .match::after{ content:''; position:absolute; top:50%; right:-14px;
          width:13px; height:2px; background:var(--line-2); }
  .col:not(:first-child) .match::before{ content:''; position:absolute; top:50%; left:-14px;
          width:13px; height:2px; background:var(--line-2); }
  .match .row{ display:flex; justify-content:space-between; gap:8px; }
  .match .go{ color:var(--muted); font-variant-numeric:tabular-nums; }
  .win{ font-weight:700; color:var(--gold-soft); }
  .chips{ display:flex; flex-wrap:wrap; gap:7px; }
  .chip{ background:var(--surface-2); border:1px solid var(--line-2); border-radius:999px; padding:5px 11px;
         font-size:.84rem; transition:transform .16s var(--ease), border-color .16s var(--ease); }
  .chip:hover{ transform:translateY(-1px); border-color:var(--gold-dim); }
  .chip.hit{ background:rgba(111,215,163,.16); border-color:#3a6b54; color:#b6f0d4; }
  .ok{ color:var(--green); } .no{ color:var(--muted-2); }
  h2.section{ font-size:1.3rem; font-weight:600; margin:30px 0 14px; color:var(--ink); letter-spacing:-.01em; }
  h2.section::before{ content:''; display:inline-block; width:24px; height:2px; background:var(--gold);
          vertical-align:middle; margin-right:12px; transform:translateY(-3px); }
  .legend{ font-size:.86rem; color:var(--muted); font-style:italic; margin:12px 2px 0; }
  /* scroll reveal */
  .reveal-on tr{ opacity:0; transition:opacity .55s var(--ease); }
  .reveal-on tr.in{ opacity:1; }
  .reveal-on .col,.reveal-on h2.section,.reveal-on p.copy,.reveal-on .empty{
        opacity:0; transform:translateY(18px);
        transition:opacity .6s var(--ease), transform .6s var(--ease); }
  .reveal-on .col.in,.reveal-on h2.section.in,.reveal-on p.copy.in,.reveal-on .empty.in{
        opacity:1; transform:none; }
  .reveal-on .bracket .col:nth-child(2){ transition-delay:.08s; }
  .reveal-on .bracket .col:nth-child(3){ transition-delay:.16s; }
  .reveal-on .bracket .col:nth-child(4){ transition-delay:.24s; }
  .reveal-on .bracket .col:nth-child(5){ transition-delay:.32s; }
  @keyframes fadeUp{ from{ opacity:0; transform:translateY(20px); } to{ opacity:1; transform:none; } }
  @keyframes panelFade{ from{ opacity:0; transform:translateY(8px); } to{ opacity:1; transform:none; } }
  @media (max-width:560px){
    .wrap{ padding:26px 14px 64px; }
    header h1{ font-size:1.6rem; }
    th,td{ padding:9px 8px; font-size:.9rem; }
    .badge{ font-size:.58rem; }
    .spk{ display:none; }
  }
  @media (prefers-reduced-motion:reduce){
    html{ scroll-behavior:auto; }
    .reveal-on tr,.reveal-on .col,.reveal-on h2.section,.reveal-on p.copy,.reveal-on .empty{
          opacity:1 !important; transform:none !important; transition:none !important; }
    *{ animation:none !important; }
  }
</style></head>
<body><div class="wrap">
  <header>
    <h1>🏆 World Cup 2026 — AI Models vs. Nadiem</h1>
    <div class="sub" id="subtitle"></div>
  </header>
  <div class="tabs">
    <div class="tab active" data-tab="lb">Leaderboard</div>
    <div class="tab" data-tab="br">Bracket</div>
    <div class="tab" data-tab="pr">Predictions</div>
    <div class="tab" data-tab="ab">About</div>
  </div>
  <div class="panel active" id="lb"></div>
  <div class="panel" id="br"></div>
  <div class="panel" id="pr"></div>
  <div class="panel" id="ab"></div>
</div>
<script>
/*__DATA__*/
(function(){
  var D = window.DATA;
  var PROV = {anthropic:'#d97757',openai:'#10a37f',google:'#4285f4',xai:'#aeb6c2',
    qwen:'#a45cff',deepseek:'#4d6bfe',meta:'#0866ff',mistral:'#ff7000',
    moonshot:'#19c3b2',kimi:'#19c3b2',zhipu:'#7c9cff',glm:'#7c9cff',minimax:'#e879f9',
    amazon:'#ff9f43',cohere:'#d6a4ff',you:'#f4c45a',human:'#f4c45a'};
  function pcolor(p){ p=(p||'').toLowerCase(); for(var k in PROV){ if(p.indexOf(k)>=0) return PROV[k]; } return '#5b657a'; }
  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function badge(p){ if(!p) return ''; return '<span class="badge" style="background:'+pcolor(p)+'">'+esc(p)+'</span>'; }
  function modelCell(name,prov){ return '<div class="model">'+badge(prov)+'<span>'+esc(name)+'</span></div>'; }
  function norm(s){ return String(s==null?'':s).trim().toLowerCase(); }
  function lname(rl){ return D.round_labels[rl]||rl; }

  /* ---------- Leaderboard ---------- */
  var lbSort={key:'points',dir:-1};
  function leaderboard(){
    var el=document.getElementById('lb');
    el.innerHTML='<div class="seg"><button class="on" data-v="main">Per-round</button>'+
      '<button data-v="bracket">Bracket bonus</button></div><div id="lbbody"></div>';
    function render(v){
      document.getElementById('lbbody').innerHTML=(v==='main')?mainBoard():bracketBoard();
      if(v==='main') bindSort();
    }
    el.querySelectorAll('.seg button').forEach(function(b){
      b.onclick=function(){ el.querySelectorAll('.seg button').forEach(function(x){x.classList.remove('on');});
        b.classList.add('on'); render(b.dataset.v); };
    });
    render('main');
  }
  function sparkline(r,rounds){
    var vals=rounds.map(function(rl){ return (r.by_round&&r.by_round[rl]!=null)?r.by_round[rl]:0; });
    var mx=Math.max.apply(null,vals.concat([1])), w=8, gap=3, H=18, tw=vals.length*(w+gap);
    var bars=vals.map(function(v,i){ var bh=Math.max(1,Math.round(v/mx*H));
      return '<rect x="'+(i*(w+gap))+'" y="'+(H-bh)+'" width="'+w+'" height="'+bh+'" rx="1" fill="#5ee0a0"></rect>'; }).join('');
    return '<svg width="'+tw+'" height="'+H+'" viewBox="0 0 '+tw+' '+H+'" aria-hidden="true">'+bars+'</svg>';
  }
  function mainBoard(){
    var rows=(D.leaderboard.rows||[]).slice();
    if(!rows.length) return '<div class="empty">No scored matches yet — collect predictions and enter results.</div>';
    rows.sort(function(a,b){ var av=a[lbSort.key], bv=b[lbSort.key];
      if(av<bv) return -lbSort.dir; if(av>bv) return lbSort.dir;
      return a.name.toLowerCase()<b.name.toLowerCase()?-1:1; });
    var max=Math.max.apply(null,rows.map(function(r){return r.points;}))||1;
    var rounds=D.leaderboard.rounds||[], multi=rounds.length>1;
    function arr(k){ return lbSort.key===k?(lbSort.dir<0?' ▾':' ▴'):''; }
    var h='<div class="tw"><table><tr><th class="rk">#</th><th class="l">Model</th>'+
      '<th class="sortable" data-k="points">Points'+arr('points')+'</th>'+
      '<th class="sortable" data-k="exact">Exact'+arr('exact')+'</th>'+
      '<th class="sortable" data-k="correct">Results'+arr('correct')+'</th>'+
      '<th>Matches</th>'+(multi?'<th class="spk">By round</th>':'')+'</tr>';
    rows.forEach(function(r,i){
      var w=Math.round(r.points/max*100);
      var lead=(i===0 && lbSort.key==='points' && lbSort.dir<0)?' class="rank1"':'';
      h+='<tr'+lead+'><td class="rk">'+(i+1)+'</td><td class="l">'+modelCell(r.name,r.provider)+'</td>'+
        '<td><span class="pts">'+r.points+'</span><div class="bar" style="width:'+w+'%"></div></td>'+
        '<td>'+r.exact+'</td><td>'+r.correct+'</td><td>'+r.scored+'</td>'+
        (multi?'<td class="spk">'+sparkline(r,rounds)+'</td>':'')+'</tr>';
    });
    return h+'</table></div><div class="legend">Click a column to sort. Exact regulation/ET scoreline = +'+
      D.scoring.exact+', correct advancing team = +'+D.scoring.result+' (best of the two per match).</div>';
  }
  function bindSort(){
    document.querySelectorAll('#lbbody th.sortable').forEach(function(th){
      th.onclick=function(){ var k=th.dataset.k;
        if(lbSort.key===k) lbSort.dir=-lbSort.dir; else { lbSort.key=k; lbSort.dir=-1; }
        document.getElementById('lbbody').innerHTML=mainBoard(); bindSort(); };
    });
  }
  function bracketBoard(){
    var rows=D.bracket_board.rows||[];
    if(!rows.length) return '<div class="empty">No one-shot bracket predictions collected yet.</div>';
    var note=D.bracket_board.have_results?'':' <span class="muted">(no knockout results yet — all zero so far)</span>';
    var max=Math.max.apply(null,rows.map(function(r){return r.points;}))||1;
    var h='<div class="legend" style="margin-bottom:10px">One-shot full bracket, locked before the Round of 32.'+note+'</div>'+
      '<div class="tw"><table><tr><th class="rk">#</th><th class="l">Model</th><th>Points</th><th class="l">Champion pick</th></tr>';
    rows.forEach(function(r,i){
      var w=Math.round(r.points/max*100);
      h+='<tr'+(i===0?' class="rank1"':'')+'><td class="rk">'+(i+1)+'</td><td class="l">'+modelCell(r.name,r.provider)+'</td>'+
        '<td><span class="pts">'+r.points+'</span><div class="bar" style="width:'+w+'%"></div></td>'+
        '<td class="l">'+esc(r.champion_pick||'—')+'</td></tr>';
    });
    return h+'</table></div>';
  }

  /* ---------- Bracket tree ---------- */
  function bracketView(){
    var el=document.getElementById('br');
    var cols=D.round_order.filter(function(rl){ return rl!=='TP' && D.fixtures[rl]; });
    var html='';
    if(!cols.length){ html='<div class="empty">No fixtures entered yet. Add them in data/fixtures/&lt;ROUND&gt;.json.</div>'; }
    else{
      html='<div class="bracket">';
      cols.forEach(function(rl){
        html+='<div class="col"><h3>'+esc(lname(rl))+'</h3><div class="col-body">';
        D.fixtures[rl].forEach(function(m){ html+=matchCard(m,(D.results[rl]||{})[m.id]); });
        html+='</div></div>';
      });
      html+='</div>';
    }
    var bp=D.bracket_predictions||[];
    if(bp.length){
      var opts=bp.map(function(b){ return '<option value="'+esc(b.slug)+'">'+esc(b.name)+'</option>'; }).join('');
      html+='<h2 class="section">Compare a one-shot bracket</h2>'+
        '<select id="brsel">'+opts+'</select><div id="brcmp"></div>';
    }
    el.innerHTML=html;
    var sel=document.getElementById('brsel');
    if(sel){ sel.onchange=function(){ renderCmp(sel.value); }; renderCmp(sel.value); }
  }
  function teamName(t){ return t?esc(t):'<span class="muted">TBD</span>'; }
  function matchCard(m,r){
    if(r){
      var hw=norm(r.advances)===norm(m.home), aw=norm(r.advances)===norm(m.away);
      return '<div class="match"><div class="row"><span class="'+(hw?'win':'')+'">'+teamName(m.home)+'</span><span class="go">'+r.home_goals+'</span></div>'+
        '<div class="row"><span class="'+(aw?'win':'')+'">'+teamName(m.away)+'</span><span class="go">'+r.away_goals+'</span></div></div>';
    }
    return '<div class="match"><div class="row"><span>'+teamName(m.home)+'</span><span class="go">·</span></div>'+
      '<div class="row"><span>'+teamName(m.away)+'</span><span class="go">·</span></div></div>';
  }
  function renderCmp(slug){
    var b=(D.bracket_predictions||[]).filter(function(x){return x.slug===slug;})[0];
    var box=document.getElementById('brcmp'); if(!b){ box.innerHTML=''; return; }
    var ab=D.actual_bracket||{};
    function stage(key,label){
      var actual=(ab[key]||[]).map(norm);
      var chips=(b.rounds[key]||[]).map(function(t){
        var hit=actual.indexOf(norm(t))>=0;
        return '<span class="chip'+(hit?' hit':'')+'">'+esc(t)+(hit?' ✓':'')+'</span>';
      }).join('');
      return '<div style="margin:10px 0"><div class="muted" style="font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">'+label+'</div><div class="chips">'+(chips||'<span class="muted">—</span>')+'</div></div>';
    }
    var champHit=ab.champion&&norm(b.rounds.champion)===norm(ab.champion);
    box.innerHTML='<div class="legend">Green = team actually reached that stage. Points: '+b.points+'.</div>'+
      stage('R16','Round of 16')+stage('QF','Quarter-finals')+stage('SF','Semi-finals')+stage('F','Finalists')+
      '<div style="margin-top:8px">Champion pick: <span class="'+(champHit?'ok':'')+'">'+esc(b.rounds.champion||'—')+(champHit?' ✓':'')+'</span></div>';
  }

  /* ---------- Predictions ---------- */
  function predictions(){
    var el=document.getElementById('pr');
    var rounds=D.round_order.filter(function(rl){ return D.round_predictions[rl]; });
    var hasBracket=(D.bracket_predictions||[]).length>0;
    if(!rounds.length && !hasBracket){ el.innerHTML='<div class="empty">No predictions collected yet.</div>'; return; }
    var ropts=rounds.map(function(rl){ return '<option value="'+rl+'">'+esc(lname(rl))+'</option>'; }).join('');
    if(hasBracket) ropts+='<option value="__bracket">Baseline bracket</option>';
    el.innerHTML='<select id="prround">'+ropts+'</select><select id="prmodel"></select><div id="prbody"></div>';
    var rsel=document.getElementById('prround'), msel=document.getElementById('prmodel');
    function fillModels(){
      var v=rsel.value, list=(v==='__bracket')?D.bracket_predictions:D.round_predictions[v];
      msel.innerHTML=list.map(function(x){ return '<option value="'+esc(x.slug)+'">'+esc(x.name)+'</option>'; }).join('');
    }
    function render(){
      var v=rsel.value, slug=msel.value, box=document.getElementById('prbody');
      if(v==='__bracket'){
        var b=(D.bracket_predictions||[]).filter(function(x){return x.slug===slug;})[0];
        box.innerHTML=b?bracketPredTable(b):'';
      } else {
        var p=(D.round_predictions[v]||[]).filter(function(x){return x.slug===slug;})[0];
        box.innerHTML=p?roundPredTable(p):'';
      }
    }
    rsel.onchange=function(){ fillModels(); render(); };
    msel.onchange=render;
    fillModels(); render();
  }
  function roundPredTable(p){
    var scored=p.scored;
    var h='<div class="legend" style="margin-bottom:10px">'+esc(p.name)+
      (scored?(' — '+p.total+' pts this round'):' — not yet played')+'</div>'+
      '<div class="tw"><table><tr><th class="l">Match</th><th>Predicted</th><th>Advances</th>'+
      (scored?'<th>Actual</th><th>Pts</th>':'')+'</tr>';
    p.predictions.forEach(function(m){
      var pred=esc(m.home)+' '+m.ph+'–'+m.pa+' '+esc(m.away);
      var actual='', pts='';
      if(scored && m.rh!=null){
        actual=esc(m.home)+' '+m.rh+'–'+m.ra+' '+esc(m.away);
        pts='<span class="pts">'+m.pts+'</span>';
      }
      var advCls=(scored&&m.rh!=null)?(m.adv_ok?'ok':'no'):'';
      h+='<tr><td class="l muted">'+esc(m.home)+' v '+esc(m.away)+'</td>'+
        '<td>'+pred+'</td><td class="'+advCls+'">'+esc(m.adv)+'</td>'+
        (scored?('<td class="muted">'+actual+'</td><td>'+pts+'</td>'):'')+'</tr>';
    });
    return h+'</table></div>';
  }
  function bracketPredTable(b){
    var ab=D.actual_bracket||{};
    function row(key,label){
      var actual=(ab[key]||[]).map(norm);
      var chips=(b.rounds[key]||[]).map(function(t){
        var hit=actual.indexOf(norm(t))>=0;
        return '<span class="chip'+(hit?' hit':'')+'">'+esc(t)+(hit?' ✓':'')+'</span>';
      }).join('')||'<span class="muted">—</span>';
      return '<tr><td class="l muted">'+label+'</td><td class="l"><div class="chips">'+chips+'</div></td></tr>';
    }
    return '<div class="legend" style="margin-bottom:10px">'+esc(b.name)+' — one-shot bracket — '+b.points+' pts</div>'+
      '<div class="tw"><table>'+row('R16','Round of 16')+row('QF','Quarter-finals')+row('SF','Semi-finals')+
      row('F','Finalists')+'<tr><td class="l muted">Champion</td><td class="l">'+esc(b.rounds.champion||'—')+'</td></tr>'+
      '<tr><td class="l muted">Third place</td><td class="l">'+esc(b.rounds.third||'—')+'</td></tr></table></div>';
  }

  /* ---------- About / methodology ---------- */
  function about(){
    var s=D.scoring;
    var stageTxt=Object.keys(s.stage).map(function(k){return k+' +'+s.stage[k];}).join(', ');
    document.getElementById('ab').innerHTML=
      '<h2 class="section">How it works</h2>'+
      '<p class="copy">Each knockout round of the 2026 World Cup, every AI model — and Nadiem — predicts '+
      'the score and who advances. Two leaderboards run at once.</p>'+
      '<h2 class="section">Per-round contest (main)</h2>'+
      '<p class="copy">Before each round, every model sees the real fixtures and predicts only that round, '+
      'so early mistakes don\'t compound. Scoring per match is <strong>non-stacking</strong>: '+
      '<strong>+'+s.exact+'</strong> for the exact regulation/extra-time scoreline (penalty shootouts '+
      'ignored), otherwise <strong>+'+s.result+'</strong> for the correct advancing team.</p>'+
      '<h2 class="section">One-shot bracket bonus</h2>'+
      '<p class="copy">Collected once before the Round of 32: each model calls the entire bracket to the '+
      'champion. Points for every team correctly predicted to reach a stage ('+esc(stageTxt)+' per correct '+
      'team), champion <strong>+'+s.champion+'</strong>, third place <strong>+'+s.third+'</strong>.</p>'+
      '<p class="legend">Generated '+esc(D.generated)+'.</p>';
  }

  /* ---------- init ---------- */
  document.getElementById('subtitle').innerHTML=
    'Knockout predictions. Rounds scored: '+((D.leaderboard.rounds||[]).map(lname).join(', ')||'none yet')+
    ' · generated '+esc(D.generated);
  document.querySelectorAll('.tab').forEach(function(t){
    t.onclick=function(){
      document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});
      document.querySelectorAll('.panel').forEach(function(x){x.classList.remove('active');});
      t.classList.add('active'); document.getElementById(t.dataset.tab).classList.add('active');
    };
  });
  /* ---------- scroll reveal ---------- */
  document.body.classList.add('reveal-on');
  var __io=('IntersectionObserver' in window)?new IntersectionObserver(function(es){
    es.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('in'); __io.unobserve(e.target); } });
  },{ threshold:0.06, rootMargin:'0px 0px -6% 0px' }):null;
  function arm(){
    var nodes=document.querySelectorAll('tr:not(.in), .col:not(.in), h2.section:not(.in), p.copy:not(.in), .empty:not(.in)');
    if(!__io){ Array.prototype.forEach.call(nodes,function(n){ n.classList.add('in'); }); return; }
    Array.prototype.forEach.call(nodes,function(n){ __io.observe(n); });
  }
  if(window.MutationObserver){
    new MutationObserver(arm).observe(document.querySelector('.wrap'),{ childList:true, subtree:true });
  }
  leaderboard(); bracketView(); predictions(); about();
  arm();
})();
</script>
</body></html>
"""


if __name__ == "__main__":
    main(sys.argv[1:])
