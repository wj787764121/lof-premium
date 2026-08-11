# -*- coding: utf-8 -*-
"""
生成手机端纯前端实时 LOF 溢价看板
================================
- 抓取各基金静态数据（净值/仓位/前十重仓）硬编码进 HTML
- 前端 JS 通过 <script> 标签实时拉腾讯行情 qt.gtimg.cn
- 只取数字字段（价格/涨跌幅）规避 GBK 编码问题
- 部署一次即可手机随时访问 + 自动刷新
"""
import sys, os, json, time, importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("lp", os.path.join(_HERE, "lof_premium.py"))
lp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lp)

ROOT = os.path.dirname(_HERE)
OUT_DIR = os.path.join(ROOT, "mobile")

DEFAULT_CODES = [
    "501200", "501099", "501096", "501015", "501026",
    "501085", "501073", "501079", "501082", "501076",
]


def prefix(code):
    return "sh" if code[0] in "569" else "sz"


def gather(codes):
    """只抓静态数据（profile + top10），不拉实时行情"""
    funds = []
    for i, code in enumerate(codes, 1):
        print(f"[{i}/{len(codes)}] {code} …")
        try:
            prof = lp.get_fund_profile(code)
            time.sleep(0.5)
            top10, report = lp.get_top10(code)
            if not prof.get("nav") or len(top10) < 3:
                print(f"  ✗ 数据不足，跳过")
                continue
            stock_pct = prof.get("stock_pct") or (sum(r["pct"] for r in top10 if r["pct"]) / 100.0)
            covered = sum(r["pct"] for r in top10 if r["pct"]) / 100.0
            holdings = [{
                "code": r["code"], "name": r["name"], "pct": r["pct"] or 0,
                "prefix": prefix(r["code"]),
            } for r in top10]
            funds.append({
                "code": code, "name": prof["fullname"], "prefix": prefix(code),
                "nav": round(prof["nav"], 4), "navDate": prof["nav_date"],
                "stockPct": round(stock_pct, 4), "covered": round(covered, 4),
                "scale": round(stock_pct / covered, 3) if covered > 0 else 1.0,
                "report": report, "holdings": holdings,
            })
            print(f"  ✓ {prof['fullname']}  净值{prof['nav']:.4f}  仓位{stock_pct*100:.1f}%  前十{len(top10)}只")
            time.sleep(0.5)
        except Exception as e:
            print(f"  ✗ {type(e).__name__}: {e}")
    return funds


HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>LOF 实时溢价看板</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f6f8fb;color:#1f2329;padding:12px;padding-bottom:40px}
.wrap{max-width:760px;margin:0 auto}
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px}
.topbar h1{font-size:18px;font-weight:800}
.topbar .qt{font-size:12px;color:#868e96}
.btn{background:#1971c2;color:#fff;border:none;border-radius:8px;padding:7px 14px;font-size:13px;font-weight:600;cursor:pointer}
.btn:active{opacity:.8}
.btn.off{background:#868e96}
.btn.sm{padding:7px 10px;font-size:12px;background:#2f9e44}
.stats{display:flex;gap:8px;margin-bottom:12px}
.stat{flex:1;background:#fff;border-radius:10px;padding:8px 4px;text-align:center;box-shadow:0 1px 3px rgba(16,24,40,.05)}
.stat .v{font-size:18px;font-weight:800}
.stat .l{font-size:10px;color:#868e96;margin-top:2px}
.market-bar{display:flex;gap:14px;flex-wrap:wrap;padding:10px 14px;align-items:center}
.mkt-item{font-size:11px;color:#868e96;white-space:nowrap}
.mkt-item b{font-size:13px;margin-left:2px}
.card{background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(16,24,40,.05);padding:14px;margin-bottom:10px}
.sum-tbl{width:100%;border-collapse:collapse;font-size:12px}
.sum-tbl th{font-size:10px;color:#868e96;font-weight:500;padding:6px 3px;border-bottom:2px solid #f1f3f5;text-align:right}
.sum-tbl th:nth-child(1),.sum-tbl th:nth-child(2){text-align:left}
.sum-tbl td{padding:7px 3px;border-bottom:1px solid #f1f3f5;text-align:right}
.sum-tbl td:nth-child(1){font-family:monospace;font-size:11px;color:#5f6b7a}
.sum-tbl td:nth-child(2){text-align:left;font-size:11px}
.sum-tbl tr:active{background:#f8f9fa}
.tbl-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
.sum-tbl th,.sum-tbl td{white-space:nowrap}
.up{color:#e03131;font-weight:600}
.down{color:#2f9e44;font-weight:600}
.expand{display:none;margin-top:10px;border-top:1px solid #f1f3f5;padding-top:8px}
.expand.show{display:block}
.cholder{font-size:11px;color:#5f6b7a;margin-bottom:6px;line-height:1.6}
.err-hist{margin-bottom:10px;padding:8px;background:#f8f9fa;border-radius:8px}
.err-title{font-size:11px;font-weight:700;color:#5f6b7a;margin-bottom:4px}
.holder-tbl{width:100%;border-collapse:collapse;font-size:11px}
.holder-tbl th{font-size:10px;color:#adb5bd;font-weight:500;padding:4px 3px;border-bottom:1px solid #f1f3f5;text-align:right}
.holder-tbl th:nth-child(1),.holder-tbl th:nth-child(3){text-align:left}
.holder-tbl td{padding:4px 3px;border-bottom:1px solid #f8f9fa;text-align:right}
.holder-tbl td:nth-child(1){font-family:monospace;font-size:10px;color:#5f6b7a}
.holder-tbl td:nth-child(3){text-align:left}
.spinner{display:inline-block;width:13px;height:13px;border:2px solid #dee2e6;border-top-color:#1971c2;border-radius:50%;animation:sp .7s linear infinite;vertical-align:-2px}
@keyframes sp{to{transform:rotate(360deg)}}
.foot{font-size:10px;color:#adb5bd;text-align:center;margin-top:16px;line-height:1.8}
.warn{font-size:11px;color:#5f6b7a;background:#fff9db;border-radius:8px;padding:8px 10px;margin-top:8px;line-height:1.6}
.tag{display:inline-block;font-size:10px;padding:1px 5px;border-radius:4px;font-weight:700;margin-left:3px}
.tag.up{background:#ffe3e3;color:#e03131}.tag.down{background:#d3f9d8;color:#2f9e44}
.bigp{font-size:22px;font-weight:800}
</style></head><body><div class="wrap">

<div class="topbar">
  <h1>LOF 实时溢价看板</h1>
  <div><span id="status" class="qt"></span> <button class="btn sm" id="navBtn" onclick="refreshNav()">更新净值</button> <button class="btn" id="refreshBtn" onclick="toggleRefresh()">自动刷新</button></div>
</div>
<div class="stats">
  <div class="stat"><div class="v up" id="nUp">-</div><div class="l">溢价</div></div>
  <div class="stat"><div class="v down" id="nDn">-</div><div class="l">折价</div></div>
  <div class="stat"><div class="v" id="avgP">-</div><div class="l">均值</div></div>
  <div class="stat"><div class="v" id="nFunds">-</div><div class="l">基金数</div></div>
</div>

<div class="card market-bar" id="marketBar"><span class="qt"><span class="spinner"></span> 市场指数加载中…</span></div>

<div class="card">
<div class="tbl-wrap">
<table class="sum-tbl" id="sumTbl">
<thead><tr><th>代码</th><th>基金</th><th>场内</th><th>估净值</th><th>净值涨跌</th><th>溢价</th><th>误差</th></tr></thead>
<tbody id="sumBody"><tr><td colspan="7" style="text-align:center;padding:20px"><span class="spinner"></span> 加载中…</td></tr></tbody>
</table>
</div>
<div class="warn">同比例口径：未披露股票按前十同比例涨跌。<b>净值涨跌</b>=组合估算涨跌；<b>误差</b>=当日估算净值 vs 次日官方实际净值的偏差（每日自动记录，次日公布净值后计算）。红涨绿跌，仅供盘中参考。</div>
</div>

<div id="cards"></div>

<div class="foot">LOF实时溢价看板 · 数据：腾讯财经/天天基金 · 持仓基准：__REPORT__ · 不构成投资建议</div>
</div>

<script>
const FUNDS = __FUNDS__;
const MARKET_INDICES = [
  {code:"sh000001", name:"上证"},
  {code:"sz399001", name:"深成"},
  {code:"sz399006", name:"创业板"},
  {code:"sh000688", name:"科创50"},
];

// ---- 腾讯行情：script 标签加载（只取数字字段，规避GBK）----
function loadBatch(qcodes){
  return new Promise((resolve,reject)=>{
    const url="https://qt.gtimg.cn/q="+qcodes.join(",")+"&_="+Date.now();
    const s=document.createElement("script");
    s.charset="gbk";
    s.onload=()=>{
      const r={};
      for(const c of qcodes){
        const v=window["v_"+c];
        if(typeof v==="string"&&v.indexOf("~")>0){r[c]=v.split("~");}
      }
      s.remove(); resolve(r);
    };
    s.onerror=()=>{s.remove();reject(new Error("行情加载失败"));};
    s.src=url; document.head.appendChild(s);
  });
}

async function fetchAllQuotes(){
  const all=[];
  for(const f of FUNDS){all.push(f.prefix+f.code); for(const h of f.holdings){all.push(h.prefix+h.code);}}
  for(const idx of MARKET_INDICES){all.push(idx.code);}
  const uniq=[...new Set(all)];
  const out={};
  for(let i=0;i<uniq.length;i+=40){
    const sub=uniq.slice(i,i+40);
    try{const r=await loadBatch(sub); Object.assign(out,r);}catch(e){console.warn(e);}
    if(i+40<uniq.length) await new Promise(r=>setTimeout(r,200));
  }
  return out;
}

// ---- 天天基金净值：pingzhongdata 也是 JS，script 标签可跨域加载 ----
function fetchNav(code){
  return new Promise((resolve)=>{
    const s=document.createElement("script");
    s.charset="utf-8";
    s.onload=()=>{
      let r=null;
      try{
        const t=window.Data_netWorthTrend;
        if(t&&t.length){const last=t[t.length-1];
          r={nav:last.y,navDate:new Date(last.x).toISOString().slice(0,10)};}
      }catch(e){}
      s.remove(); resolve(r);
    };
    s.onerror=()=>{s.remove();resolve(null);};
    s.src="https://fund.eastmoney.com/pingzhongdata/"+code+".js?_="+Date.now();
    document.head.appendChild(s);
  });
}

async function fetchAllNavs(){
  const navs={};
  for(const f of FUNDS){
    const r=await fetchNav(f.code);
    if(r){navs[f.code]=r;}
    await new Promise(r=>setTimeout(r,150)); // 间隔避免风控
  }
  return navs;
}

// idx: 3=现价 4=昨收 32=涨跌幅 30=时间
function qz(arr){
  if(!arr||arr.length<40) return null;
  return {price:parseFloat(arr[3])||0,lastClose:parseFloat(arr[4])||0,
    chgPct:parseFloat(arr[32])||0,time:arr[30]||""};
}

function calc(f,q){
  const fq=qz(q[f.prefix+f.code]);
  if(!fq) return null;
  let wsum=0,weighted=0;
  const hd=[];
  for(const h of f.holdings){
    const hq=qz(q[h.prefix+h.code]);
    const cp=hq?hq.chgPct:0;
    const w=h.pct/100;
    wsum+=w; weighted+=w*cp;
    hd.push({...h,price:hq?hq.price:0,chgPct:cp,contrib:w*cp});
  }
  const estChg=weighted*f.scale;
  const navEst=f.nav*(1+estChg/100);
  const price=fq.price||fq.lastClose;
  const prem=navEst>0?(price-navEst)/navEst*100:null;
  const premStatic=f.nav>0?(fq.lastClose-f.nav)/f.nav*100:null;
  const priceChg=fq.lastClose>0?(price-fq.lastClose)/fq.lastClose*100:0;
  const err=priceChg-estChg;
  return {fund:f,price,lastClose:fq.lastClose,navEst,estChg,prem,premStatic,priceChg,err,
    details:hd,qtime:fq.time};
}

function cls(v){return v==null?"":(v>=0?"up":"down");}
function fmt(v,p,s){return v==null?"—":(s||"")+v.toFixed(p)+(s?"":"");}
function fmtT(t){return t&&t.length>=14?t.slice(8,10)+":"+t.slice(10,12)+":"+t.slice(12,14):t||"";}

// ---- 估值误差：localStorage 记录每日估算，次日官方净值公布后对比 ----
function loadLog(){try{return JSON.parse(localStorage.getItem("lof_premium_log")||"{}");}catch(e){return{};}}
function saveLog(log){try{localStorage.setItem("lof_premium_log",JSON.stringify(log));}catch(e){}}
function updateLog(results){
  const log=loadLog();
  const today=new Date().toISOString().slice(0,10);
  for(const r of results){
    if(!r) continue;
    const c=r.fund.code;
    if(!log[c]) log[c]={estimates:{},errors:[]};
    log[c].estimates[today]=r.navEst;  // 存今日盘中估算
    const nd=r.fund.navDate;            // 官方净值日期
    if(nd && log[c].estimates[nd]!=null){
      const est=log[c].estimates[nd], actual=r.fund.nav;
      const err=(est-actual)/actual*100;
      if(!log[c].errors.find(e=>e.date===nd)){
        log[c].errors.push({date:nd,est:est,actual:actual,err:err});
        if(log[c].errors.length>60) log[c].errors=log[c].errors.slice(-60);
      }
    }
  }
  saveLog(log);
  return log;
}
function lastErr(log,code){
  const e=log[code]&&log[code].errors;
  return e&&e.length?e[e.length-1]:null;
}

function renderMarket(q){
  let html="";
  for(const idx of MARKET_INDICES){
    const arr=q[idx.code];
    if(arr&&arr.length>40){
      const price=parseFloat(arr[3])||0;
      const chgPct=parseFloat(arr[32])||0;
      html+=`<span class="mkt-item">${idx.name} <b class="${cls(chgPct)}">${price.toFixed(2)} ${fmt(chgPct,2,'+')+'%'}</b></span>`;
    }
  }
  document.getElementById("marketBar").innerHTML=html||'<span class="qt">市场指数暂不可用</span>';
}

function render(results, log){
  log=log||{};
  const ranked=results.filter(r=>r).sort((a,b)=>(b.prem||-999)-(a.prem||-999));
  // 汇总表
  let rows="";
  for(const r of ranked){
    const tag=r.prem>=0?'<span class="tag up">溢</span>':'<span class="tag down">折</span>';
    const le=lastErr(log,r.fund.code);
    const errTxt=le?fmt(le.err,2,'+')+'%':'—';
    rows+=`<tr onclick="toggle('${r.fund.code}')" style="cursor:pointer">
    <td>${r.fund.code}</td><td>${r.fund.name.slice(0,10)}</td>
    <td>${r.price.toFixed(3)}</td><td><b>${r.navEst.toFixed(4)}</b></td>
    <td class="${cls(r.estChg)}">${fmt(r.estChg,2,'+')+'%'}</td>
    <td class="${cls(r.prem)}"><b>${fmt(r.prem,2,'+')+'%'}</b>${tag}</td>
    <td class="${cls(le?le.err:null)}">${errTxt}</td></tr>`;
  }
  document.getElementById("sumBody").innerHTML=rows;
  // 统计
  const nUp=ranked.filter(r=>r.prem!=null&&r.prem>=0).length;
  const nDn=ranked.length-nUp;
  const avg=ranked.reduce((s,r)=>s+(r.prem||0),0)/Math.max(1,ranked.length);
  document.getElementById("nUp").textContent=nUp;
  document.getElementById("nDn").textContent=nDn;
  document.getElementById("avgP").textContent=fmt(avg,2,'+')+'%';
  document.getElementById("avgP").className="v "+cls(avg);
  document.getElementById("nFunds").textContent=ranked.length;
  // 详情卡片
  let cards="";
  for(const r of ranked){
    let hrows="";
    for(const d of r.details){
      hrows+=`<tr><td>${d.code}</td><td style="text-align:left">${d.name}</td>
      <td>${d.price?d.price.toFixed(2):'—'}</td>
      <td class="${cls(d.chgPct)}">${fmt(d.chgPct,2,'+')+'%'}</td>
      <td>${d.pct.toFixed(2)}%</td>
      <td class="${cls(d.contrib)}">${fmt(d.contrib,3,'+')}</td></tr>`;
    }
    const le=lastErr(log,r.fund.code);
    const errs=(log[r.fund.code]&&log[r.fund.code].errors)||[];
    let erows="";
    for(const e of errs.slice(-7).reverse()){
      erows+=`<tr><td>${e.date.slice(5)}</td><td>${e.est.toFixed(4)}</td><td>${e.actual.toFixed(4)}</td><td class="${cls(e.err)}">${fmt(e.err,2,'+')+'%'}</td></tr>`;
    }
    const errTbl=erows?`<div class="err-hist"><div class="err-title">估值误差历史（估算 vs 实际净值）</div>
      <table class="holder-tbl"><thead><tr><th>日期</th><th>估算</th><th>实际</th><th>误差</th></tr></thead>
      <tbody>${erows}</tbody></table></div>`:'<div class="err-hist"><div class="err-title">估值误差历史</div><div style="font-size:11px;color:#adb5bd">尚无数据（每日盘中打开本页自动记录估算，次日官方净值公布后自动计算误差）</div></div>';
    cards+=`<div class="card" id="c${r.fund.code}">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div><b style="font-size:14px">${r.fund.name}</b>
        <span style="font-family:monospace;font-size:11px;color:#868e96;margin-left:4px">${r.fund.code}</span></div>
        <div style="text-align:right"><span class="bigp ${cls(r.prem)}">${fmt(r.prem,2,'+')+'%'}</span></div>
      </div>
      <div class="cholder">场内<b>${r.price.toFixed(3)}</b>(昨收${r.lastClose.toFixed(3)} ${fmt(r.priceChg,2,'+')+'%'})｜估净值<b>${r.navEst.toFixed(4)}</b>(净值涨跌${fmt(r.estChg,2,'+')+'%'})｜昨误差<b class="${cls(le?le.err:null)}">${le?fmt(le.err,2,'+')+'%':'—'}</b>${le?'('+le.date.slice(5)+')':''}｜基准${r.fund.nav}(${r.fund.navDate})｜仓位${(r.fund.stockPct*100).toFixed(0)}%÷前十${(r.fund.covered*100).toFixed(1)}%=×${r.fund.scale}｜@${fmtT(r.qtime)}</div>
      <div class="expand" id="e${r.fund.code}">
        ${errTbl}
        <table class="holder-tbl"><thead><tr><th>代码</th><th>股票</th><th>现价</th><th>涨跌</th><th>权重</th><th>贡献</th></tr></thead>
        <tbody>${hrows}</tbody></table>
      </div>
    </div>`;
  }
  document.getElementById("cards").innerHTML=cards;
  document.getElementById("status").textContent="更新 "+fmtT(ranked[0]?ranked[0].qtime:"");
}

function toggle(code){const e=document.getElementById("e"+code);if(e)e.classList.toggle("show");}

let loading=false,timer=null,navLoaded=false;
async function refresh(){
  if(loading) return;
  loading=true;
  document.getElementById("status").innerHTML='<span class="spinner"></span> '+(navLoaded?'刷新行情':'加载中');
  try{
    if(!navLoaded){
      document.getElementById("status").innerHTML='<span class="spinner"></span> 拉取最新净值…';
      const navs=await fetchAllNavs();
      let cnt=0;
      for(const f of FUNDS){if(navs[f.code]){f.nav=navs[f.code].nav;f.navDate=navs[f.code].navDate;cnt++;}}
      navLoaded=true;
      document.getElementById("status").textContent="净值 "+cnt+"/"+FUNDS.length+" 已更新";
    }
    const q=await fetchAllQuotes();
    const results=FUNDS.map(f=>calc(f,q));
    const log=updateLog(results);
    render(results,log);
    renderMarket(q);
  }catch(e){
    document.getElementById("status").textContent="❌ "+e.message;
  }
  loading=false;
}

async function refreshNav(){
  if(loading) return;
  const btn=document.getElementById("navBtn");
  btn.textContent="拉取中…";btn.disabled=true;
  document.getElementById("status").innerHTML='<span class="spinner"></span> 重新拉取净值';
  const navs=await fetchAllNavs();
  let cnt=0;
  for(const f of FUNDS){if(navs[f.code]){f.nav=navs[f.code].nav;f.navDate=navs[f.code].navDate;cnt++;}}
  btn.textContent="更新净值";btn.disabled=false;
  document.getElementById("status").textContent="净值已更新 "+cnt+"/"+FUNDS.length;
  await refresh();
}

function toggleRefresh(){
  if(timer){clearInterval(timer);timer=null;document.getElementById("refreshBtn").textContent="自动刷新";document.getElementById("refreshBtn").classList.add("off");}
  else{timer=setInterval(refresh,20000);document.getElementById("refreshBtn").textContent="刷新中(20s)";document.getElementById("refreshBtn").classList.remove("off");refresh();}
}
document.getElementById("refreshBtn").classList.add("off");
refresh();
</script>
</body></html>
'''


def main():
    codes = DEFAULT_CODES
    print(f"▶ 生成手机看板，{len(codes)} 只基金\n")
    funds = gather(codes)
    if not funds:
        print("✗ 无数据"); sys.exit(1)

    reports = sorted(set(f["report"] for f in funds))
    os.makedirs(OUT_DIR, exist_ok=True)

    funds_json = json.dumps(funds, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__FUNDS__", funds_json).replace("__REPORT__", "/".join(reports))

    out = os.path.join(OUT_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✔ 已生成 {out}（{len(funds)} 只基金）")
    # 同时保存数据快照
    with open(os.path.join(OUT_DIR, "funds.json"), "w", encoding="utf-8") as f:
        json.dump(funds, f, ensure_ascii=False, indent=1)
    print(f"✔ 数据快照 {OUT_DIR}/funds.json")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ 出错：{e}")
        try: input("回车退出...")
        except: pass
        sys.exit(1)
