# HTML 深度分析报告 — 单文件模板（默认输出）

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

## 完整骨架（复制即用）

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{公司名}（{代码}）深度分析报告</title>
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
    <h1>{公司名}（{代码}）深度分析报告</h1>
    <p class="sub">{公司全称} · {英文名}</p>
    <div class="meta">
      <span class="tag">报告日期：{YYYY年M月D日}</span>
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

## 交付前必做

运行 `python scripts/check_report.py <报告文件>`，全部 PASS 才可交付。详见 Step 3.5。
