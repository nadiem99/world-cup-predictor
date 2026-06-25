"""Generate a single self-contained static site: output/index.html

Three views (tabs): Leaderboard (Design-Arena inspired), Bracket, and a browsable
Predictions archive. All data is embedded as JSON and rendered client-side with
vanilla JS, so the file works opened locally or hosted anywhere. No dependencies.

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
<title>World Cup 2026 — AI Models vs. You</title>
<style>
  :root{ color-scheme:dark; }
  *{ box-sizing:border-box; }
  body{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
        background:#0a0c12; color:#e7ecf6; }
  a{ color:inherit; }
  .wrap{ max-width:1040px; margin:0 auto; padding:26px 20px 80px; }
  header h1{ font-size:1.6rem; margin:0 0 4px; letter-spacing:-.01em; }
  header .sub{ color:#8893ab; font-size:.9rem; }
  .tabs{ display:flex; gap:6px; margin:22px 0 18px; border-bottom:1px solid #1e2433; }
  .tab{ padding:10px 16px; cursor:pointer; color:#8893ab; font-weight:600; font-size:.92rem;
        border-bottom:2px solid transparent; user-select:none; }
  .tab:hover{ color:#cdd6ea; }
  .tab.active{ color:#fff; border-bottom-color:#5ee0a0; }
  .panel{ display:none; } .panel.active{ display:block; }
  .seg{ display:inline-flex; background:#141823; border:1px solid #232a3a; border-radius:9px;
        padding:3px; margin-bottom:16px; gap:2px; }
  .seg button{ background:none; border:0; color:#8893ab; padding:7px 14px; border-radius:7px;
        cursor:pointer; font-weight:600; font-size:.85rem; }
  .seg button.on{ background:#222b3d; color:#fff; }
  select{ background:#141823; color:#e7ecf6; border:1px solid #232a3a; border-radius:8px;
          padding:8px 10px; font-size:.9rem; margin:0 8px 14px 0; }
  table{ width:100%; border-collapse:collapse; background:#10141e; border:1px solid #1e2433;
         border-radius:12px; overflow:hidden; font-size:.93rem; }
  th,td{ padding:11px 12px; border-bottom:1px solid #1a2030; text-align:center; }
  th{ background:#141a28; color:#9aa6c2; font-size:.72rem; text-transform:uppercase;
      letter-spacing:.05em; font-weight:700; }
  td.l,th.l{ text-align:left; } tr:last-child td{ border-bottom:none; }
  tr.rank1 td{ background:linear-gradient(90deg,rgba(244,196,90,.10),transparent); }
  .rk{ font-weight:800; color:#9aa6c2; width:34px; }
  .model{ display:flex; align-items:center; gap:10px; }
  .badge{ font-size:.66rem; font-weight:800; padding:2px 7px; border-radius:999px;
          color:#0a0c12; text-transform:uppercase; letter-spacing:.03em; white-space:nowrap; }
  .pts{ font-weight:800; color:#7ee2a8; font-variant-numeric:tabular-nums; }
  .bar{ height:6px; border-radius:3px; background:#5ee0a0; opacity:.5; margin-top:4px; }
  .muted{ color:#8893ab; }
  .empty{ padding:22px; background:#10141e; border:1px solid #1e2433; border-radius:12px;
          color:#8893ab; text-align:center; }
  /* bracket */
  .bracket{ display:flex; gap:14px; overflow-x:auto; padding-bottom:8px; }
  .col{ min-width:172px; flex:0 0 auto; }
  .col h3{ font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; color:#9aa6c2;
           margin:0 0 8px; text-align:center; }
  .match{ background:#10141e; border:1px solid #1e2433; border-radius:9px; padding:8px 9px;
          margin-bottom:8px; font-size:.84rem; }
  .match .row{ display:flex; justify-content:space-between; gap:8px; }
  .match .go{ color:#9aa6c2; font-variant-numeric:tabular-nums; }
  .win{ font-weight:800; color:#fff; }
  .chips{ display:flex; flex-wrap:wrap; gap:6px; }
  .chip{ background:#141a28; border:1px solid #232a3a; border-radius:999px; padding:4px 10px;
         font-size:.8rem; }
  .chip.hit{ background:rgba(94,224,160,.16); border-color:#2e6b50; color:#aef3cf; }
  .ok{ color:#7ee2a8; } .no{ color:#6b7488; }
  h2.section{ font-size:1.05rem; margin:26px 0 12px; color:#c7d0e6; }
  .legend{ font-size:.8rem; color:#8893ab; margin:10px 2px 0; }
</style></head>
<body><div class="wrap">
  <header>
    <h1>🏆 World Cup 2026 — AI Models vs. You</h1>
    <div class="sub" id="subtitle"></div>
  </header>
  <div class="tabs">
    <div class="tab active" data-tab="lb">Leaderboard</div>
    <div class="tab" data-tab="br">Bracket</div>
    <div class="tab" data-tab="pr">Predictions</div>
  </div>
  <div class="panel active" id="lb"></div>
  <div class="panel" id="br"></div>
  <div class="panel" id="pr"></div>
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
  function leaderboard(){
    var el=document.getElementById('lb');
    var roundsTxt=(D.leaderboard.rounds||[]).map(lname).join(', ')||'none yet';
    var html='<div class="seg"><button class="on" data-v="main">Per-round</button>'+
             '<button data-v="bracket">Bracket bonus</button></div>'+
             '<div id="lbbody"></div>';
    el.innerHTML=html;
    function render(v){
      var box=document.getElementById('lbbody');
      if(v==='main') box.innerHTML=mainTable();
      else box.innerHTML=bracketTable();
    }
    el.querySelectorAll('.seg button').forEach(function(b){
      b.onclick=function(){ el.querySelectorAll('.seg button').forEach(function(x){x.classList.remove('on');});
        b.classList.add('on'); render(b.dataset.v); };
    });
    render('main');
  }
  function mainTable(){
    var rows=D.leaderboard.rows||[];
    if(!rows.length) return '<div class="empty">No scored matches yet — collect predictions and enter results.</div>';
    var max=Math.max.apply(null,rows.map(function(r){return r.points;}))||1;
    var h='<table><tr><th class="rk">#</th><th class="l">Model</th><th>Points</th>'+
      '<th>Exact scores</th><th>Correct results</th><th>Matches</th></tr>';
    rows.forEach(function(r,i){
      var w=Math.round(r.points/max*100);
      h+='<tr class="rank'+(i+1)+'"><td class="rk">'+(i+1)+'</td>'+
        '<td class="l">'+modelCell(r.name,r.provider)+'</td>'+
        '<td><span class="pts">'+r.points+'</span><div class="bar" style="width:'+w+'%"></div></td>'+
        '<td>'+r.exact+'</td><td>'+r.correct+'</td><td>'+r.scored+'</td></tr>';
    });
    return h+'</table><div class="legend">Exact regulation/ET scoreline = +'+D.scoring.exact+
      ', correct advancing team = +'+D.scoring.result+' (best of the two per match).</div>';
  }
  function bracketTable(){
    var rows=D.bracket_board.rows||[];
    if(!rows.length) return '<div class="empty">No one-shot bracket predictions collected yet.</div>';
    var note=D.bracket_board.have_results?'':' <span class="muted">(no knockout results yet — all zero so far)</span>';
    var max=Math.max.apply(null,rows.map(function(r){return r.points;}))||1;
    var h='<div class="legend" style="margin-bottom:10px">One-shot full bracket, locked before the Round of 32.'+note+'</div>'+
      '<table><tr><th class="rk">#</th><th class="l">Model</th><th>Points</th><th class="l">Champion pick</th></tr>';
    rows.forEach(function(r,i){
      var w=Math.round(r.points/max*100);
      h+='<tr class="rank'+(i+1)+'"><td class="rk">'+(i+1)+'</td><td class="l">'+modelCell(r.name,r.provider)+'</td>'+
        '<td><span class="pts">'+r.points+'</span><div class="bar" style="width:'+w+'%"></div></td>'+
        '<td class="l">'+esc(r.champion_pick||'—')+'</td></tr>';
    });
    return h+'</table>';
  }

  /* ---------- Bracket ---------- */
  function bracketView(){
    var el=document.getElementById('br');
    var cols=D.round_order.filter(function(rl){ return rl!=='TP' && D.fixtures[rl]; });
    var html='';
    if(!cols.length){ html='<div class="empty">No fixtures entered yet. Add them in data/fixtures/&lt;ROUND&gt;.json.</div>'; }
    else{
      html='<div class="bracket">';
      cols.forEach(function(rl){
        html+='<div class="col"><h3>'+esc(lname(rl))+'</h3>';
        D.fixtures[rl].forEach(function(m){
          var r=(D.results[rl]||{})[m.id];
          html+=matchCard(m,r);
        });
        html+='</div>';
      });
      html+='</div>';
    }
    // model bracket comparison
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
  function matchCard(m,r){
    var home=esc(m.home), away=esc(m.away);
    if(r){
      var hw=norm(r.advances)===norm(m.home), aw=norm(r.advances)===norm(m.away);
      return '<div class="match"><div class="row"><span class="'+(hw?'win':'')+'">'+home+'</span><span class="go">'+r.home_goals+'</span></div>'+
        '<div class="row"><span class="'+(aw?'win':'')+'">'+away+'</span><span class="go">'+r.away_goals+'</span></div></div>';
    }
    return '<div class="match"><div class="row"><span>'+home+'</span><span class="go">·</span></div>'+
      '<div class="row"><span>'+away+'</span><span class="go">·</span></div></div>';
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
      var v=rsel.value, list;
      if(v==='__bracket') list=D.bracket_predictions;
      else list=D.round_predictions[v];
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
      '<table><tr><th class="l">Match</th><th>Predicted</th><th>Advances</th>'+
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
    return h+'</table>';
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
      '<table>'+row('R16','Round of 16')+row('QF','Quarter-finals')+row('SF','Semi-finals')+
      row('F','Finalists')+'<tr><td class="l muted">Champion</td><td class="l">'+esc(b.rounds.champion||'—')+'</td></tr>'+
      '<tr><td class="l muted">Third place</td><td class="l">'+esc(b.rounds.third||'—')+'</td></tr></table>';
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
  leaderboard(); bracketView(); predictions();
})();
</script>
</body></html>
"""


if __name__ == "__main__":
    main(sys.argv[1:])
