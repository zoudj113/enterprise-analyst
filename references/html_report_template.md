# HTML 分析报告 — 单文件模板（默认输出）

**HTML 是本技能的默认输出格式**，写 HTML 报告时**直接复用本骨架**，只替换内容与数据，不要从零写 CSS。
文件名固定为 `{公司简称}_分析报告_{YYYYMMDD}.html`。
源文件范本：`中烟香港_分析报告_20260917.html`（2026-09，9 图 21 表）。

## 硬性约束

1. **单文件**：CSS 全部内联在 `<style>`，图表用 CDN，不拆 `styles.css` / `app.js`。
2. **必联网**：`<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>`，离线时图表不渲染（属已知限制，需在交付时说明）。
3. **浅色主题**：--bg 白 / 文字深色。除非用户明确要暗色，不得改。
4. **涨跌配色按 A 股习惯**：`.up` 红、`.down` 绿。（地区约定）
5. **每个 `<canvas>` 必须有 `role="img"` + `aria-label`**，且 fallback 文字写在标签内。
6. **TOC 锚点**与 `<h2 id="sN">` 一一对应；`<h2>` 内用 `<span class="num">九</span>` 显示中文序号。
7. 表格必须有 `<thead>`；数值列统一 `class="num-c"`；合计行放 `<tfoot>`。
   **`<thead>` 中数值列的 `<th>` 也必须加 `class="num-c"`**（`th` 默认 `text-align:left`，
   若只有数据格右对齐而表头左对齐，长表头下的短数字会显得既不居中也不对齐——2026-09-17 云铝报告返工教训）。
   自检方法：任意一列的表头右边缘应与该列数据右边缘基本对齐。
8. **必须有常驻侧边目录**：`<div class="layout">` 下并列 `<aside class="sidebar">` 与 `<div class="content">`；
   侧栏 `position:sticky`。滚动高亮脚本必须放在**独立的 `<script>` 块**（与 Chart.js 初始化分开），
   否则图表初始化失败会连带导航失效。
9. `<header id="top">` 提供「回到顶部」锚点。
10. **页头必带「财年口径」说明**（2026-09-28 新增，`check_report.py [17]`）：美股等可自选财年月份的市场，
    必须在正文最前面写明**财年截止日**，并给出 **`FY20xx` 标签 ↔ 起止日期**的映射
    （例：`FY2026 指 2025 年 6 月 1 日至 2026 年 5 月 31 日`）。财年 = 自然年的公司写一句
    「财年与自然年一致」即可。写法与判定口径见 `pre_write_checklist.md [17]`。

## 完整骨架（复制即用）

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{公司名}（{代码}）分析报告</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
:root{
  --bg:#ffffff; --bg-soft:#f7f7f5; --bg-soft2:#f1efe8;
  --text:#2C2C2A; --text-2:#5F5E5A; --text-3:#888780;
  --line:#e3e2dd; --line-2:#d3d1c7;
  --blue:#185FA5; --blue-soft:#E6F1FB; --blue-bar:#378ADD;
  --amber:#854F0B; --amber-bar:#BA7517;
  --red:#A32D2D; --red-soft:#FCEBEB; --red-bar:#E24B4A;
  --green:#3B6D11; --green-soft:#EAF3DE;
  --teal:#0F6E56; --teal-soft:#E1F5EE;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg-soft); color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  font-size:15px; line-height:1.75; -webkit-font-smoothing:antialiased;
}
/* 两栏布局：左侧常驻目录 + 右侧正文 */
.layout{
  display:grid; grid-template-columns:212px minmax(0,1fr); gap:36px;
  max-width:1240px; margin:0 auto; padding:0 24px 80px; align-items:start;
}
.content{min-width:0}                 /* 必须，否则宽表格撑破栅格 */
.sidebar{
  position:sticky; top:24px;
  max-height:calc(100vh - 48px); overflow-y:auto; overscroll-behavior:contain;
}
.sidebar::-webkit-scrollbar{width:6px}
.sidebar::-webkit-scrollbar-thumb{background:var(--line-2); border-radius:3px}
header{
  background:var(--bg); border-bottom:1px solid var(--line); padding:40px 0 32px; margin-bottom:28px;
}
header .inner{max-width:1240px; margin:0 auto; padding:0 24px}
h1{font-size:27px; font-weight:600; margin:0 0 8px; letter-spacing:-.3px}
.sub{color:var(--text-2); font-size:14px; margin:0}
.meta{margin-top:16px; display:flex; flex-wrap:wrap; gap:8px}
.tag{font-size:12px; color:var(--text-2); background:var(--bg-soft2); border-radius:6px; padding:3px 10px}
h2{font-size:20px; font-weight:600; margin:44px 0 14px; padding-bottom:10px; border-bottom:1px solid var(--line); letter-spacing:-.2px; scroll-margin-top:20px}
h2 .num{color:var(--text-3); font-weight:400; margin-right:8px}
h3{font-size:16px; font-weight:600; margin:26px 0 10px}
h4{font-size:14px; font-weight:600; margin:18px 0 8px; color:var(--text-2)}
p{margin:0 0 12px}
.card{background:var(--bg); border:1px solid var(--line); border-radius:12px; padding:20px 22px; margin:16px 0}
.grid{display:grid; gap:12px; margin:16px 0}
.g6{grid-template-columns:repeat(6,minmax(0,1fr))}
.g4{grid-template-columns:repeat(4,minmax(0,1fr))}
.g3{grid-template-columns:repeat(3,minmax(0,1fr))}
.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
@media(max-width:820px){.g6,.g4,.g3,.g2{grid-template-columns:repeat(2,minmax(0,1fr))}}
.kpi{background:var(--bg-soft2); border-radius:10px; padding:14px 16px}
.kpi .k{font-size:12px; color:var(--text-2); margin-bottom:4px}
.kpi .v{font-size:21px; font-weight:600; letter-spacing:-.4px}
.kpi .d{font-size:12px; color:var(--text-3); margin-top:2px}
.up{color:var(--red)} .down{color:var(--green)}
table{width:100%; border-collapse:collapse; font-size:13.5px; margin:14px 0}
th{text-align:left; font-weight:600; color:var(--text-2); font-size:12.5px; padding:9px 10px; border-bottom:1px solid var(--line-2); white-space:nowrap}
td{padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top}
tbody tr:hover{background:var(--bg-soft)}
.num-c{text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap}
tfoot td{font-weight:600; border-top:1px solid var(--line-2); border-bottom:none}
.chart-box{background:var(--bg); border:1px solid var(--line); border-radius:12px; padding:18px 20px 14px; margin:18px 0}
.chart-title{font-size:14px; font-weight:600; margin-bottom:2px}
.chart-sub{font-size:12px; color:var(--text-3); margin-bottom:12px}
.chart-wrap{position:relative; width:100%; height:300px}
.legend{display:flex; flex-wrap:wrap; gap:16px; font-size:12px; color:var(--text-2); margin-bottom:10px}
.legend span{display:flex; align-items:center; gap:5px}
.dot{width:10px; height:10px; border-radius:2px; display:inline-block}
.note{background:var(--blue-soft); border-left:3px solid var(--blue); padding:12px 16px; border-radius:0 8px 8px 0; margin:16px 0; font-size:14px}
.note.warn{background:var(--red-soft); border-left-color:var(--red)}
.note.good{background:var(--teal-soft); border-left-color:var(--teal)}
.note b{font-weight:600}
pre{background:var(--bg-soft2); border:1px solid var(--line); border-radius:10px; padding:16px; overflow-x:auto; font-size:12.5px; line-height:1.55; font-family:"SF Mono",Consolas,"Courier New",monospace}
ul{margin:0 0 12px; padding-left:20px}
li{margin-bottom:6px}
.stars{color:var(--amber-bar); letter-spacing:2px; font-size:15px}
.dim{color:var(--text-3)}
.risk-h{color:var(--red); font-weight:600}
.risk-m{color:var(--amber); font-weight:600}
.risk-l{color:var(--green); font-weight:600}
/* 侧边目录（常驻 + 滚动高亮） */
.toc{background:var(--bg); border:1px solid var(--line); border-radius:12px; padding:14px 0}
.toc-title{font-size:12px; color:var(--text-3); padding:0 16px 10px; letter-spacing:.5px}
.toc ol{margin:0; padding:0; list-style:none; font-size:13.5px}
.toc a{
  display:block; padding:5px 16px; color:var(--text-2); text-decoration:none;
  border-left:2px solid transparent; line-height:1.5;
}
.toc a:hover{background:var(--bg-soft); color:var(--blue)}
.toc a.active{color:var(--blue); font-weight:600; border-left-color:var(--blue); background:var(--blue-soft)}
.toc-foot{padding:10px 16px 0; margin-top:8px; border-top:1px solid var(--line)}
.toc-foot a{font-size:12px; color:var(--text-3); text-decoration:none}
.toc-foot a:hover{color:var(--blue)}
@media(max-width:1080px){
  .layout{grid-template-columns:1fr; max-width:1000px; gap:0}
  .sidebar{position:static; max-height:none; overflow:visible; margin-bottom:20px}
  .toc ol{columns:2; column-gap:28px}
}
footer{margin-top:48px; padding-top:20px; border-top:1px solid var(--line); font-size:12.5px; color:var(--text-3); line-height:1.8}
.src{font-size:12px; color:var(--text-3); margin-top:-6px}
</style>
</head>
<body>

<header id="top">
  <div class="inner">
    <h1>{公司名}（{代码}）分析报告</h1>
    <p class="sub">{公司全称} · {英文名}</p>
    <!-- 财年口径（[17] 必写）：财年非自然年时改写成真实截止日与 FY 映射；自然年则写「与自然年一致」 -->
    <div class="note" style="margin:14px 0 0">
      <b>先看财年口径——不先弄清这一条，后面所有年份都会读错一年。</b>
      {公司简称}的财年截止日为每年 <b>{M 月 D 日}</b>，<b>{与自然年一致 / 与自然年不一致}</b>。
      本报告中的 <b>FY2026 指 {YYYY 年 M 月 D 日} 至 {YYYY 年 M 月 D 日}</b>{；相应地 FY2025 指 …，FY2027 Q1 指 …}。全文的年份标签、同比与估值口径均按此定义。
    </div>
    <div class="meta">
      <span class="tag">报告日期：{YYYY年M月D日}</span>
      <span class="tag">财年截止：每年 {M 月 D 日}（{非自然年 / 与自然年一致}）</span>
      <span class="tag">财务数据源：{ima 知识库「XX」（xxxx–xxxx 年报、xxxx 中期报告、招股书）}</span>
      <span class="tag">行情数据：公开市场（{日期} 收盘）</span>
      <span class="tag">会计准则：{HKFRS / CAS}（{货币}列示）</span>
    </div>
  </div>
</header>

<div class="layout">

<aside class="sidebar">
  <nav class="toc">
    <div class="toc-title">目录</div>
    <ol>
      <li><a href="#s0">核心速览</a></li>
      <li><a href="#s1">一、企业概况</a></li>
      <!-- 与 <h2 id="sN"> 一一对应 -->
    </ol>
    <div class="toc-foot"><a href="#top">↑ 回到顶部</a></div>
  </nav>
</aside>

<div class="content">

<!-- 核心速览 KPI 卡 -->
<h2 id="s0" style="margin-top:0">核心速览</h2>
<div class="grid g3">
  <div class="kpi"><div class="k">最新期收入</div><div class="v">{值}</div><div class="d up">+{x}%</div></div>
</div>

<h2 id="s1"><span class="num">一</span>企业概况</h2>
<!-- ... -->

<footer>
  <h4>数据来源</h4>
  <p>① 财务与经营数据：...</p>
  <p>② 市场行情数据：...</p>
  <p>③ 外部交叉验证数据：...（非公司披露内容，仅用于交叉验证）</p>
  <h4>免责声明</h4>
  <p>...</p>
  <p style="margin-top:12px" class="dim">生成时间：{YYYY 年 M 月 D 日}</p>
</footer>

</div><!-- /.content -->
</div><!-- /.layout -->

<script>
/* Chart.js 初始化：每个 new Chart(...) 一个块 */
const F = {color:'#5F5E5A', font:{size:11}};
Chart.defaults.color = '#5F5E5A';
Chart.defaults.font.size = 11;
Chart.defaults.font.family = '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif';

new Chart(document.getElementById('cX'), {
  type:'bar',
  data:{labels:[...], datasets:[{label:'...', data:[...], backgroundColor:'#378ADD', borderRadius:4}]},
  options:{
    responsive:true, maintainAspectRatio:false,
    plugins:{legend:{display:false}, tooltip:{callbacks:{label:c=>c.dataset.label+'：'+c.parsed.y+' 亿'}}},
    scales:{x:{grid:{display:false}}, y:{grid:{color:'#eeeeec'}}}
  }
});
</script>

<!-- 导航脚本必须独立成块：图表 CDN 失败时目录仍能正常跳转与高亮 -->
<script>
(function(){
  var links = Array.prototype.slice.call(document.querySelectorAll('.toc a[href^="#"]'));
  var targets = links.map(function(a){ return document.querySelector(a.getAttribute('href')); });
  function spy(){
    var best = -1;
    for (var i=0; i<targets.length; i++){
      if (targets[i] && targets[i].getBoundingClientRect().top - 90 <= 0) best = i;
    }
    if (best < 0) best = 0;
    links.forEach(function(a,i){ a.classList.toggle('active', i===best); });
  }
  var raf = null;
  window.addEventListener('scroll', function(){
    if (raf) return;
    raf = requestAnimationFrame(function(){ raf = null; spy(); });
  }, {passive:true});
  window.addEventListener('resize', spy);
  spy();
})();
</script>
</body>
</html>
```

## 配色语义（不得混用）

| 用途 | 变量 | 十六进制 |
|---|---|---|
| 主数据柱 / 收入 | `--blue-bar` | `#378ADD` |
| 次数据柱 / 利润·股息 | `--amber-bar` | `#BA7517` |
| 下降 · 亏损 · 高风险 | `--red-bar` | `#E24B4A` |
| 上升 · 增长 | `--green` | `#3B6D11` |
| 中性 | `--text-3` | `#888780` |

## 常用片段

**归因瀑布图**（Chart.js floating bar，data 用 `[min,max]`）：
```js
labels:['2025H1','分部A','分部B','合计X','2026H1'],
data:[[0,103.16],[69.10,103.16],[69.10,75.19],[73.79,75.19],[0,75.40]],
backgroundColor:['#378ADD','#3B6D11','#E24B4A','#3B6D11','#378ADD']
```
> 瀑布图属**流程型**图表，横轴是推导路径而非并列期间，**豁免「最新在最左」规则**，但须在副标题说明。

**正负值堆叠**（利润构成）：
```js
labels:['2026 上半年','2025 上半年'],   // 遵守最新在最左
datasets:[
  {label:'经营贡献', data:[7.73,8.67], backgroundColor:'#378ADD', stack:'s'},
  {label:'融资成本', data:[-0.80,-0.83], backgroundColor:'#E24B4A', stack:'s'}
]
```

**双轴混合图**（收入柱 + 利润率线）：`yAxisID:'y'` / `'y1'`，`order:2` / `order:1` 控制叠放次序。

## 融资与分红章节版式（固定 · 照抄）

第四章「融资与分红情况」里的表格**统一为「指标为行、期间为列」**（左列写指标名，表头写期间且最新期在最左），
与核心财务指标表、资产负债表等章节方向一致——读者才能沿同一个方向扫读，不必每换一张表就重新找轴。
**这份版式是硬规则，不是风格偏好**：同一技能产出的报告之间不得再出现两种方向（自检 `[18]` 会拦）。

### 4.1 融资表（事件流水，时间可留作第一列）

融资是**事件**而非并列期间，所以「时间」留在第一列；但**行必须自上而下由新到旧**，
未提用的授信额度等**非事件行**排在事件行之后。

```html
<h3>4.1 历次重大融资与资金用途</h3>
<table>
<thead><tr><th>时间</th><th>融资方式</th><th class="num-c">规模</th><th>用途与说明</th></tr></thead>
<tbody>
<tr><td>2026 年前三季</td><td>短期债务净增加</td><td class="num-c">+4.95 亿美元</td><td>短期借款净额</td></tr>
<tr><td>2025 年 5 月</td><td>发行无担保固定利率票据</td><td class="num-c">15 亿美元</td><td>净额用于一般公司用途</td></tr>
<tr><td>长期额度（未动用）</td><td>循环信贷额度</td><td class="num-c">40 亿美元上限</td><td>2029 年 8 月到期，期末无余额</td></tr>
</tbody>
</table>
<p class="src">数据来源：… 10-K「Liquidity and Capital Resources — Debt」。</p>
```

### 4.2 分红与回购表（**强制纵向版式**）

**左列 = 指标名，表头 = 期间，最新期在最左。** 这是本技能唯一的合法形态。

```html
<h3>4.2 分红与回购</h3>
<table>
<thead><tr><th>项目</th><th class="num-c">FY2025</th><th class="num-c">FY2024</th><th class="num-c">FY2023</th><th class="num-c">FY2022</th></tr></thead>
<tbody>
<tr><td>每股股息（美元，当期实际发放口径）</td><td class="num-c">3.48</td><td class="num-c">3.30</td><td class="num-c">3.10</td><td class="num-c">2.86</td></tr>
<tr><td>其中：按 20xx 年 N 拆 1 拆股后口径折算</td><td class="num-c">3.48</td><td class="num-c">3.30</td><td class="num-c">…</td><td class="num-c">…</td></tr>
<tr><td>股息支付总额（亿美元）</td><td class="num-c">38.05</td><td class="num-c">36.87</td><td class="num-c">34.62</td><td class="num-c">32.12</td></tr>
<tr><td>股份回购金额（亿美元）</td><td class="num-c">87.91</td><td class="num-c">41.21</td><td class="num-c">29.73</td><td class="num-c">31.29</td></tr>
<tr><td>回购股数（百万股）</td><td class="num-c">56</td><td class="num-c">25</td><td class="num-c">25</td><td class="num-c">21</td></tr>
<tr><td>分红 + 回购合计（亿美元）</td><td class="num-c">125.96</td><td class="num-c">78.08</td><td class="num-c">64.35</td><td class="num-c">63.41</td></tr>
<tr><td>合计 ÷ 当年净利润</td><td class="num-c">…</td><td class="num-c">…</td><td class="num-c">…</td><td class="num-c">…</td></tr>
<tr><td>合计 ÷ 当年经营现金流</td><td class="num-c">89.9%</td><td class="num-c">…</td><td class="num-c">…</td><td class="num-c">…</td></tr>
</tbody>
</table>
<p class="src">数据来源：各财年 10-K 的「Capital Returns」与「Dividends」附注。表中「合计」= 分红 + 回购合计；两行比率的分子都是该「合计」。</p>
```

**指标行基线清单**（可按公司情况增减，但这几行是下限）：每股股息 / 股息支付总额 / 股份回购金额 /
回购股数（或回购均价）/ 分红 + 回购合计 / **合计 ÷ 当年净利润** / 合计 ÷ 当年经营现金流。
口径特殊处写在**指标名里**（括号内注明），不要另开一列。

> **末两行的顺序固定**：`合计 ÷ 当年净利润` 在**上**，`合计 ÷ 当年经营现金流` 在**下**。
> 两行的分子都是上一行的「分红 + 回购合计」，只换分母，例：
> FY2025 分红 + 回购合计 125.96 亿美元 ÷ 经营现金流 140.12 亿美元 = **89.9%**。
>
> - **合计 ÷ 当年净利润**——股东回报占「账面赚到多少」的比例。净利润含非现金损益（公允价值变动、
>   减值、汇兑），所以这一行反映的是**分配意愿**，不是现金能力。
> - **合计 ÷ 当年经营现金流**——股东回报占「实际收回多少现金」的比例。经营现金流才是分红与回购的真钱来源，
>   所以**这一行是可持续性的硬约束**；超过 100% 意味着当年回报动用了账上现金或新增借款。
> - 两行并列看才有信息：净利润口径低、现金流口径高 → 利润里有大量非现金收益，回报其实靠现金存量撑；
>   反之则是利润被非现金项目压低。**净利润为负时该行写「不适用（当年净利润为负）」，不要留空或写负比率。**

**禁止形态**（自检 `[18]` 判 FAIL）：

```html
<!-- ✗ 错：财年做行、指标做列 —— 读任何一个指标都要横向跨表，且与全文其他表格方向相反 -->
<thead><tr><th>财年</th><th class="num-c">股份回购金额</th><th class="num-c">回购股数</th><th class="num-c">每股分红</th><th class="num-c">合计返还</th></tr></thead>
```

**四条配套纪律**：

- **拆股 / 口径变更另起一行**（如「其中：按 20xx 年 N 拆 1 拆股后口径折算」），不要靠「横向多一列」承载——
  加列会让表头脱离期间序列，读者会误读成两个不同口径的期间。
- **指标只有两三个也不退回横向版式**：指标少不是理由，全报告一致性才是。
- 期间标签用公司自己的财年标签（`FY2025`）或日期（`2025-12-31`）均可，但**同一章内保持一致**。
- **4.3 匹配度评价**用 `<ul>` 分条，每条自带主语与数字（覆盖率、与债务的取舍、股东回报诚意、融资效率）；
  分红政策可用 `<div class="note good">` 单独引出。

## 交付前必做

运行 `python scripts/check_report.py <报告文件>`，全部 PASS 才可交付。详见 Step 3.5。
