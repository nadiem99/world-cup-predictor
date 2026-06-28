"""Generate a single self-contained static site: output/index.html

Four views (tabs): Leaderboard (the one-shot bracket standings), Bracket (connected
knockout tree of the real tournament), Predictions (each entrant's one-shot bracket
vs. reality), and About/methodology. All data is embedded as JSON and rendered
client-side with vanilla JS, so the file works opened locally (file://) or hosted
anywhere. No dependencies, no external assets (flags load from flagcdn.com).

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
from .flags import FLAGS


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

    for row in scores["bracket"]["rows"]:
        row["provider"] = meta.get(row["slug"], {}).get("provider", "")

    fixtures, results = {}, {}
    for rl in ROUND_ORDER:
        fx = load_json(FIXTURES_DIR / ("%s.json" % rl))
        if fx and fx.get("matches"):
            fixtures[rl] = [{"id": m["id"], "home": m.get("home"), "away": m.get("away")}
                            for m in fx["matches"]]
        res = scoring._round_results(rl)
        if res:
            results[rl] = {mid: {"home_goals": r["home_goals"], "away_goals": r["away_goals"],
                                 "advances": r.get("advances", "")} for mid, r in res.items()}

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scoring": {"stage": scoring.BRACKET_STAGE_POINTS,
                    "champion": scoring.CHAMPION_BONUS, "third": scoring.THIRD_BONUS},
        "round_order": ROUND_ORDER,
        "round_labels": ROUND_LABELS,
        "bracket_board": scores["bracket"],
        "actual_bracket": _actual_bracket_display(),
        "fixtures": fixtures,
        "results": results,
        "bracket_predictions": _bracket_predictions(meta),
        "flags": FLAGS,
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
  .match .row{ display:flex; justify-content:space-between; align-items:center; gap:8px; }
  .match .go{ color:var(--muted); font-variant-numeric:tabular-nums; flex:none; }
  .tm{ display:inline-flex; align-items:center; gap:8px; min-width:0; }
  .tn{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .flag{ width:21px; height:15px; border-radius:2px; object-fit:cover; flex:none;
         background:var(--surface-2); vertical-align:middle;
         box-shadow:0 0 0 1px rgba(0,0,0,.4), 0 1px 2px rgba(0,0,0,.4); }
  .win{ font-weight:700; color:var(--gold-soft); }
  .chips{ display:flex; flex-wrap:wrap; gap:7px; }
  .chip{ display:inline-flex; align-items:center; gap:6px;
         background:var(--surface-2); border:1px solid var(--line-2); border-radius:999px; padding:5px 11px;
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
  function normTeam(s){ return String(s==null?'':s).normalize('NFD').replace(/[\u0300-\u036f]/g,'')
    .toLowerCase().replace(/[^a-z0-9]+/g,''); }
  var FLAGN={}; (function(){ var f=D.flags||{}; for(var k in f){ FLAGN[normTeam(k)]=f[k]; } })();
  function flagImg(team){ var c=FLAGN[normTeam(team)]; if(!c) return '';
    return '<img class="flag" alt="" width="21" height="15" '+
      'src="https://flagcdn.com/28x21/'+c+'.png" srcset="https://flagcdn.com/56x42/'+c+'.png 2x">'; }
  function badge(p){ if(!p) return ''; return '<span class="badge" style="background:'+pcolor(p)+'">'+esc(p)+'</span>'; }
  function modelCell(name,prov){ return '<div class="model">'+badge(prov)+'<span>'+esc(name)+'</span></div>'; }
  function norm(s){ return String(s==null?'':s).trim().toLowerCase(); }
  function lname(rl){ return D.round_labels[rl]||rl; }

  /* ---------- Leaderboard (one-shot bracket) ---------- */
  function leaderboard(){
    document.getElementById('lb').innerHTML=bracketBoard();
  }
  function bracketBoard(){
    var rows=D.bracket_board.rows||[];
    if(!rows.length) return '<div class="empty">No bracket predictions collected yet — run <code>collect bracket</code> and add your own with <code>make enter</code>.</div>';
    var note=D.bracket_board.have_results?'':' <span class="muted">(no knockout results yet — all zero until matches are played)</span>';
    var max=Math.max.apply(null,rows.map(function(r){return r.points;}))||1;
    var h='<div class="legend" style="margin-bottom:10px">One-shot full bracket, locked before the Round of 32.'+note+'</div>'+
      '<div class="tw"><table><tr><th class="rk">#</th><th class="l">Entrant</th><th>Points</th><th class="l">Champion pick</th></tr>';
    rows.forEach(function(r,i){
      var w=Math.round(r.points/max*100);
      h+='<tr'+(i===0&&D.bracket_board.have_results?' class="rank1"':'')+'><td class="rk">'+(i+1)+'</td><td class="l">'+modelCell(r.name,r.provider)+'</td>'+
        '<td><span class="pts">'+r.points+'</span><div class="bar" style="width:'+w+'%"></div></td>'+
        '<td class="l">'+teamInline(r.champion_pick)+'</td></tr>';
    });
    return h+'</table></div>';
  }

  /* ---------- Actual bracket tree (the real tournament) ---------- */
  function actualBracketTree(){
    var cols=D.round_order.filter(function(rl){ return rl!=='TP' && D.fixtures[rl]; });
    if(!cols.length) return '<div class="empty">No fixtures entered yet. Add them in data/fixtures/&lt;ROUND&gt;.json.</div>';
    var html='<div class="bracket">';
    cols.forEach(function(rl){
      html+='<div class="col"><h3>'+esc(lname(rl))+'</h3><div class="col-body">';
      D.fixtures[rl].forEach(function(m){ html+=matchCard(m,(D.results[rl]||{})[m.id]); });
      html+='</div></div>';
    });
    return html+'</div>';
  }
  function bracketView(){
    document.getElementById('br').innerHTML=actualBracketTree();
  }
  function teamName(t){ return t?esc(t):'<span class="muted">TBD</span>'; }
  function teamLabel(t,win){ return '<span class="tm'+(win?' win':'')+'">'+flagImg(t)+
    '<span class="tn">'+teamName(t)+'</span></span>'; }
  function teamInline(t,cls){ return '<span class="tm '+(cls||'')+'">'+flagImg(t)+
    '<span class="tn">'+(t?esc(t):'—')+'</span></span>'; }
  function matchCard(m,r){
    if(r){
      var hw=norm(r.advances)===norm(m.home), aw=norm(r.advances)===norm(m.away);
      return '<div class="match"><div class="row">'+teamLabel(m.home,hw)+'<span class="go">'+r.home_goals+'</span></div>'+
        '<div class="row">'+teamLabel(m.away,aw)+'<span class="go">'+r.away_goals+'</span></div></div>';
    }
    return '<div class="match"><div class="row">'+teamLabel(m.home,false)+'<span class="go">·</span></div>'+
      '<div class="row">'+teamLabel(m.away,false)+'<span class="go">·</span></div></div>';
  }
  /* ---------- Predictions (each entrant's bracket vs. the actual bracket) ---------- */
  function predictions(){
    var el=document.getElementById('pr');
    var bp=D.bracket_predictions||[];
    if(!bp.length){ el.innerHTML='<div class="empty">No bracket predictions collected yet.</div>'; return; }
    el.innerHTML='<select id="prmodel"></select><div id="prbody"></div>'+
      '<h2 class="section">Actual bracket</h2>'+
      '<div class="legend" style="margin-bottom:10px">How the real tournament is unfolding — compare it against the picks above.</div>'+
      actualBracketTree();
    var msel=document.getElementById('prmodel');
    msel.innerHTML=bp.map(function(x){ return '<option value="'+esc(x.slug)+'">'+esc(x.name)+'</option>'; }).join('');
    function render(){
      var b=bp.filter(function(x){return x.slug===msel.value;})[0];
      document.getElementById('prbody').innerHTML=b?bracketPredTable(b):'';
    }
    msel.onchange=render; render();
  }
  function bracketPredTable(b){
    var ab=D.actual_bracket||{};
    function row(key,label){
      var actual=(ab[key]||[]).map(norm);
      var chips=(b.rounds[key]||[]).map(function(t){
        var hit=actual.indexOf(norm(t))>=0;
        return '<span class="chip'+(hit?' hit':'')+'">'+flagImg(t)+esc(t)+(hit?' ✓':'')+'</span>';
      }).join('')||'<span class="muted">—</span>';
      return '<tr><td class="l muted">'+label+'</td><td class="l"><div class="chips">'+chips+'</div></td></tr>';
    }
    return '<div class="legend" style="margin-bottom:10px">'+esc(b.name)+' — one-shot bracket — '+b.points+' pts</div>'+
      '<div class="tw"><table>'+row('R16','Round of 16')+row('QF','Quarter-finals')+row('SF','Semi-finals')+
      row('F','Finalists')+'<tr><td class="l muted">Champion</td><td class="l">'+teamInline(b.rounds.champion)+'</td></tr>'+
      '<tr><td class="l muted">Third place</td><td class="l">'+teamInline(b.rounds.third)+'</td></tr></table></div>';
  }

  /* ---------- About / methodology ---------- */
  function about(){
    var s=D.scoring;
    var stageTxt=Object.keys(s.stage).map(function(k){return k+' +'+s.stage[k];}).join(', ');
    document.getElementById('ab').innerHTML=
      '<h2 class="section">How it works</h2>'+
      '<p class="copy">Before the Round of 32, every AI model — and Nadiem — calls the <strong>entire '+
      '2026 World Cup bracket once</strong>, all the way to the champion. That single prediction is locked '+
      'in; there is no re-picking each round. As the real tournament plays out, every bracket is scored '+
      'against what actually happened.</p>'+
      '<h2 class="section">Scoring</h2>'+
      '<p class="copy">You earn points for every team you correctly placed into a stage, weighted by how '+
      'deep it goes: <strong>'+esc(stageTxt)+'</strong> per correct team. Calling the '+
      '<strong>champion</strong> is worth <strong>+'+s.champion+'</strong> and <strong>third place</strong> '+
      '<strong>+'+s.third+'</strong>. Highest total wins — one leaderboard, winner takes all.</p>'+
      '<p class="legend">Generated '+esc(D.generated)+'.</p>';
  }

  /* ---------- init ---------- */
  document.getElementById('subtitle').innerHTML=
    'One-shot bracket challenge — AI models vs. Nadiem · generated '+esc(D.generated);
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
