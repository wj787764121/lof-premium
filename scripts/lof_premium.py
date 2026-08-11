# -*- coding: utf-8 -*-
"""
LOF 实时溢价率估算程序（未披露股票同比例涨跌口径）
====================================================
用法：
  python lof_premium.py --code 501200            # 默认口径：未披露股票同比例涨跌
  python lof_premium.py --code 501200 --html      # 额外生成 HTML 报告
  python lof_premium.py --code 160416 --nav 1.234 # 指定净值基准（覆盖自动获取）

估算逻辑：
  估算净值 = 最新单位净值 × (1 + 组合估算涨跌幅)
  组合估算涨跌幅 = Σ(重仓股占净值比 × 个股实时涨跌幅) × (股票仓位 ÷ 前十覆盖占比)
  —— 即"未披露股票仓位与已披露前十同比例涨跌"口径（用户指定）
  估算溢价率 = (场内实时价 - 估算净值) ÷ 估算净值 × 100%

数据源（免 key）：
  腾讯行情 qt.gtimg.cn（场内价/重仓股实时行情）
  天天基金 pingzhongdata（最新净值、股票仓位）
  天天基金 FundArchivesDatas（前十大重仓股）
"""
import urllib.request
import json
import io
import sys
import re
import time
import argparse
import html as H
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0"


# ---------------- 网络 ----------------
def fetch(url, timeout=12, encoding=None, referer=None, retries=2):
    last_err = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", UA)
            if referer:
                req.add_header("Referer", referer)
            resp = urllib.request.urlopen(req, timeout=timeout)
            raw = resp.read()
            if encoding:
                return raw.decode(encoding, errors="replace")
            return raw.decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            time.sleep(1.2)
    raise RuntimeError(f"网络请求失败（{last_err}）：{url[:80]}...")


def market_prefix(code):
    """判断 A 股市场前缀"""
    if code.startswith(("6", "5", "9")):
        return "sh" + code
    return "sz" + code


# ---------------- 数据获取 ----------------
def get_fund_profile(code):
    """最新净值 + 股票仓位（天天基金 pingzhongdata）"""
    text = fetch(
        f"https://fund.eastmoney.com/pingzhongdata/{code}.js?v={int(time.time()*1000)}",
        referer=f"https://fund.eastmoney.com/{code}.html",
    )
    prof = {"nav": None, "nav_date": None, "stock_pct": None, "fullname": None}
    m = re.search(r'fS_name\s*=\s*"([^"]+)"', text)
    prof["fullname"] = m.group(1) if m else code
    m = re.search(r"Data_netWorthTrend\s*=\s*(\[.*?\]);", text)
    if m:
        trend = json.loads(m.group(1))
        if trend:
            last = trend[-1]
            prof["nav"] = last["y"]
            prof["nav_date"] = datetime.fromtimestamp(last["x"] / 1000).strftime("%Y-%m-%d")
    m = re.search(r"Data_assetAllocation\s*=\s*(\{.*?\});", text)
    if m:
        try:
            aa = json.loads(m.group(1))
            cats = aa.get("categories", [])
            if cats:
                latest_i = len(cats) - 1
                for ser in aa.get("series", []):
                    if ser.get("name") == "股票占净比" and latest_i < len(ser["data"]):
                        prof["stock_pct"] = ser["data"][latest_i] / 100.0
                        prof["stock_pct_date"] = cats[latest_i]
                        break
        except Exception:
            pass
    return prof


def get_top10(code):
    """前十大重仓股（天天基金 FundArchivesDatas，返回最新一期）"""
    data = fetch(
        f"https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&topline=10",
        referer=f"https://fundf10.eastmoney.com/ccmx_{code}.html",
    )
    m = re.search(r'content:"(.*?)"', data, re.S)
    content = m.group(1) if m else ""
    qm = re.search(r"(\d{4})年(\d)季度", content)
    report = f"{qm.group(1)}Q{qm.group(2)}" if qm else "?"

    def clean(td):
        return H.unescape(re.sub(r"<[^>]+>", "", td)).strip()

    cur = []
    for tr in re.findall(r"<tr>(.*?)</tr>", content, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 9 or not clean(tds[0]).isdigit():
            continue
        pct = clean(tds[6]).replace("%", "")
        shares = clean(tds[7]).replace(",", "")
        mkt = clean(tds[8]).replace(",", "")
        cur.append({
            "seq": int(clean(tds[0])), "code": clean(tds[1]), "name": clean(tds[2]),
            "pct": float(pct) if pct else None,
            "shares": float(shares) if shares else None,
            "mkt": float(mkt) if mkt else None,
        })
    return cur, report


def get_quotes(codes):
    """腾讯批量行情 {原始代码: {字段}}"""
    url = "https://qt.gtimg.cn/q=" + ",".join(market_prefix(c) for c in codes)
    raw = fetch(url, encoding="gbk")
    out = {}
    for line in raw.strip().split(";"):
        if "=" not in line or '"' not in line:
            continue
        v = line.split('"')[1].split("~")
        if len(v) < 40:
            continue
        out[v[2]] = {
            "name": v[1], "price": float(v[3] or 0), "last_close": float(v[4] or 0),
            "open": float(v[5] or 0), "chg": float(v[31] or 0), "chg_pct": float(v[32] or 0),
            "high": float(v[33] or 0), "low": float(v[34] or 0),
            "vol": v[36], "amount": v[37], "time": v[30],
        }
    return out


# ---------------- 计算 ----------------
def calc_premium(prof, top10, fund_quote, quotes, mode="full"):
    """
    mode:
      full    —— 未披露股票同比例涨跌（默认，用户指定口径）
      neutral —— 未披露仓位视为不变（对照组）
    """
    covered = sum(r["pct"] for r in top10 if r["pct"]) / 100.0
    stock_pct = prof["stock_pct"] or covered  # 取不到股票仓位时退化为全股票假设

    wsum, weighted = 0.0, 0.0
    details = []
    for r in top10:
        q = quotes.get(r["code"])
        if not q or q["price"] <= 0:
            continue
        w = (r["pct"] or 0) / 100.0
        wsum += w
        weighted += w * q["chg_pct"]
        details.append({
            "seq": r["seq"], "code": r["code"], "name": r["name"],
            "price": q["price"], "last_close": q["last_close"], "chg_pct": q["chg_pct"],
            "w_pct": w * 100, "contrib_pp": w * q["chg_pct"],
        })

    if mode == "full":
        scale = stock_pct / covered if covered > 0 else 1.0
        est_chg = weighted * scale          # 未披露股票按同比例涨跌
    else:
        scale = 1.0
        est_chg = weighted                  # 未披露仓位贡献 0

    nav_base = prof["nav"]
    nav_est = nav_base * (1 + est_chg / 100.0) if nav_base else None
    price = fund_quote.get("price") or 0
    prem = (price - nav_est) / nav_est * 100 if nav_est and price else None

    # 静态参考（昨收 vs 最新净值）
    prem_static = ((fund_quote.get("last_close", 0) - nav_base) / nav_base * 100) if nav_base else None

    return {
        "fund_code": None, "mode": mode, "scale": scale,
        "covered": covered, "stock_pct": stock_pct,
        "wsum": wsum, "est_chg_pct": est_chg, "nav_base": nav_base,
        "nav_date": prof["nav_date"], "nav_est": nav_est,
        "price": price, "last_close": fund_quote.get("last_close", 0),
        "premium_pct": prem, "premium_static": prem_static,
        "details": details, "qtime": fund_quote.get("time", ""),
    }


# ---------------- 输出 ----------------
def fmt_time(t):
    return f"{t[8:10]}:{t[10:12]}:{t[12:14]}" if len(t) >= 14 else t


def print_report(r):
    print("=" * 66)
    print(f"估算净值(同比例口径) = {r['nav_est']:.4f}   场内价 = {r['price']:.3f}")
    if r["premium_pct"] is not None:
        tag = "溢价" if r["premium_pct"] >= 0 else "折价"
        print(f"估算溢价率 = {r['premium_pct']:+.2f}%  ({tag} {abs(r['premium_pct']):.2f}%)")
    print("-" * 66)


def gen_html(r, prof, report, out_path):
    def cls(v):
        return "up" if v >= 0 else "down"

    prem = r["premium_pct"]
    prem_txt = f"{prem:+.2f}%" if prem is not None else "—"
    tag_txt = ("溢价" if prem >= 0 else "折价") if prem is not None else ""
    qtime = fmt_time(r["qtime"])
    rows = ""
    for d in r["details"]:
        rows += f'''<tr><td class="c">{d["seq"]}</td><td class="code">{d["code"]}</td>
        <td><b>{d["name"]}</b></td><td class="num">{d["price"]:.2f}</td>
        <td class="num {cls(d['chg_pct'])}">{d["chg_pct"]:+.2f}%</td>
        <td class="num">{d["w_pct"]:.2f}%</td>
        <td class="num {cls(d['contrib_pp'])}">{d["contrib_pp"]:+.3f}pp</td></tr>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{r['fund_code']} 实时溢价率估算（同比例口径）</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"PingFang SC","Microsoft YaHei",sans-serif;background:#f6f8fb;color:#1f2329;padding:24px}}
.wrap{{max-width:960px;margin:0 auto}}
.card{{background:#fff;border-radius:14px;box-shadow:0 1px 4px rgba(16,24,40,.06);padding:22px 24px;margin-bottom:18px}}
.title{{font-size:22px;font-weight:700}}
.sub{{font-size:13px;color:#5f6b7a;margin-top:4px}}
.sec-title{{font-size:15px;font-weight:700;margin-bottom:12px;display:flex;align-items:center;gap:8px}}
.sec-title::before{{content:"";width:4px;height:15px;background:#1971c2;border-radius:2px}}
.main{{display:flex;align-items:center;gap:36px;flex-wrap:wrap;margin-top:16px}}
.big{{font-size:52px;font-weight:800;line-height:1}}
.big.up{{color:#e03131}}.big.down{{color:#2f9e44}}
.tag{{display:inline-block;font-size:14px;padding:4px 14px;border-radius:8px;font-weight:700;margin-top:10px}}
.tag.up{{background:#ffe3e3;color:#e03131}}.tag.down{{background:#d3f9d8;color:#2f9e44}}
.side{{font-size:14px;color:#5f6b7a;line-height:2.1}}
.side b{{color:#1f2329}}
.formula{{background:#f8f9fa;border-radius:10px;padding:14px 16px;font-size:13px;color:#5f6b7a;line-height:2}}
.formula b{{color:#1f2329}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;font-size:12px;color:#868e96;font-weight:500;padding:8px 6px;border-bottom:2px solid #f1f3f5}}
td{{padding:8px 6px;border-bottom:1px solid #f1f3f5}}
td.c{{text-align:center}}td.num{{text-align:right}}
td.code{{font-family:Consolas,monospace;color:#5f6b7a}}
.up{{color:#e03131;font-weight:600}}.down{{color:#2f9e44;font-weight:600}}
.warn{{font-size:12px;color:#5f6b7a;background:#fff9db;border-radius:8px;padding:10px 12px;margin-top:14px;line-height:1.8}}
.foot{{font-size:11px;color:#adb5bd;text-align:center;margin:8px 0 20px}}
</style></head><body><div class="wrap">

<div class="card">
  <div class="title">{prof["fullname"]} · 实时溢价率估算</div>
  <div class="sub">代码 {r["fund_code"]} · 估算时间 {qtime} · 持仓报告期 {report} · 口径：未披露股票同比例涨跌</div>
  <div class="main">
    <div><div class="big {cls(prem) if prem is not None else ''}">{prem_txt}</div>
    <div><span class="tag {cls(prem) if prem is not None else ''}">{tag_txt}</span></div></div>
    <div class="side">
      场内现价 <b>{r["price"]:.3f}</b>（昨收 {r["last_close"]:.3f}）<br>
      估算净值 <b>{r["nav_est"]:.4f}</b>（{r["est_chg_pct"]:+.2f}%）<br>
      净值基准 <b>{r["nav_base"]:.4f}</b>（{r["nav_date"]}）<br>
      股票仓位 {r["stock_pct"]*100:.1f}% ÷ 前十覆盖 {r["covered"]*100:.1f}% → 放大系数 ×{r["scale"]:.2f}<br>
      静态参考（昨收 vs 净值）<b>{r["premium_static"]:+.2f}%</b>
    </div>
  </div>
</div>

<div class="card">
  <div class="sec-title">重仓股实时行情（{qtime}）</div>
  <table><thead><tr><th style="width:36px">#</th><th style="width:76px">代码</th><th>股票</th>
  <th class="num">现价</th><th class="num">涨跌</th><th class="num">权重</th><th class="num">对净值贡献</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <div class="warn">估算公式：估算净值 = 最新净值 × (1 + Σ(重仓股占净值比 × 个股涨跌幅) × 股票仓位/前十覆盖占比)。
  未披露的其余股票仓位假定与已披露前十同比例涨跌。误差来源：持仓为季报时点（可能已调仓）、未披露个股结构未知、场内流动性差。
  估算仅供盘中参考，以收盘后官方净值为准。</div>
</div>

<div class="foot">LOF实时溢价估算程序 · 数据来源：腾讯财经/天天基金 · 不构成投资建议</div>
</div></body></html>'''
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser(description="LOF 实时溢价率估算（未披露股票同比例涨跌口径）")
    ap.add_argument("--code", default="501200", help="LOF 基金代码，默认 501200")
    ap.add_argument("--nav", type=float, default=None, help="手动指定净值基准（默认自动取最新）")
    ap.add_argument("--html", action="store_true", help="生成 HTML 报告")
    ap.add_argument("--neutral", action="store_true", help="改用中性口径（未披露仓位视为不变）")
    args = ap.parse_args()

    code = args.code
    print(f"▶ 获取 {code} 基本信息…")
    prof = get_fund_profile(code)
    if args.nav:
        prof["nav"] = args.nav
        prof["nav_date"] = prof["nav_date"] or "手动指定"
    if not prof["nav"]:
        raise RuntimeError("获取最新净值失败（可能基金代码有误或接口暂不可用），可用 --nav 手动指定净值基准")

    time.sleep(0.8)
    print(f"▶ 获取 {code} 前十大重仓…")
    top10, report = get_top10(code)
    if not top10:
        raise RuntimeError("获取持仓失败：该基金可能不披露个股持仓（如 QDII/债券基金）或接口异常")

    time.sleep(0.8)
    codes = [code] + [r["code"] for r in top10]
    print(f"▶ 拉取 {len(codes)} 只证券实时行情…")
    quotes = get_quotes(codes)
    fund_quote = quotes.get(code, {})
    if not fund_quote.get("price"):
        fund_quote["price"] = fund_quote.get("last_close", 0)  # 未成交时回退昨收

    mode = "neutral" if args.neutral else "full"
    res = calc_premium(prof, top10, fund_quote, quotes, mode=mode)
    res["fund_code"] = code

    print("\n" + "=" * 66)
    print(f"{prof['fullname']}  ({code})   持仓报告期 {report}")
    print(f"净值基准 {res['nav_base']:.4f}（{res['nav_date']}）  股票仓位 {res['stock_pct']*100:.1f}%")
    print(f"场内现价 {res['price']:.3f}（昨收 {res['last_close']:.3f}）  @{fmt_time(res['qtime'])}")
    print(f"前十覆盖净值 {res['covered']*100:.1f}%，放大系数 ×{res['scale']:.2f}")
    print(f"组合估算涨跌 {res['est_chg_pct']:+.2f}%  →  估算净值 {res['nav_est']:.4f}")
    if res["premium_pct"] is not None:
        tag = "溢价" if res["premium_pct"] >= 0 else "折价"
        print(f"\n★ 估算溢价率 = {res['premium_pct']:+.2f}%  （{tag} {abs(res['premium_pct']):.2f}%）")
    if res["premium_static"] is not None:
        print(f"  静态参考(昨收) = {res['premium_static']:+.2f}%")
    print("-" * 66)
    print(f"{'代码':<8}{'名称':<10}{'现价':>10}{'涨跌%':>9}{'权重%':>8}{'贡献pp':>9}")
    for d in res["details"]:
        print(f"{d['code']:<8}{d['name']:<10}{d['price']:>10.2f}{d['chg_pct']:>9.2f}{d['w_pct']:>8.2f}{d['contrib_pp']:>9.3f}")
    print("=" * 66)

    # 保存 JSON
    with open(f"{code}_premium_latest.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    print(f"✔ 结果已保存 {code}_premium_latest.json")

    if args.html:
        out = f"{code}_实时溢价率估算.html"
        gen_html(res, prof, report, out)
        print(f"✔ HTML 报告已生成 {out}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print()
        print("=" * 52)
        print(f"✗ 程序出错：{e}")
        print("  排查建议：")
        print("  1) 检查网络是否可用（本程序需联网拉取行情）")
        print("  2) 确认基金代码正确，且是可披露持仓的 LOF")
        print("  3) 数据接口偶发失效，稍后重试")
        print("=" * 52)
        try:
            input("按回车键退出...")
        except EOFError:
            pass
        sys.exit(1)
