/* 区块标题吸顶：每个菜单页的区块标题行在滚动时钉在顶栏下沿。
 *
 * 为什么值得一个套件：
 * - 「标题跟着滚走」只有真的滚一下才看得出来，静态读 CSS 会漏掉两类失效：
 *   ① 区块被 max-height + overflow 截成内部滚动框（标题钉在区块顶部而不是
 *      顶栏下沿，看起来像没吸顶）；② --sticky-top 写死一个值，窄屏顶栏 60px、
 *      桌面 68px、经典布局又是另一个高度，对不齐就露出一条内容缝。
 * - 吸顶配方（section padding-top 归零 + 首行 padding-top 顶上 + margin 折成
 *   padding）少一条都会漏内容，且不会报错。
 *
 * 这里钉住三件事：
 *   1. CSS 契约：顶层 section 的 sec-scope 首行 sticky、top 用 --sticky-top；
 *      限高但没超高的区块（.section-fits）走整页滚动；窄屏不内部滚动。
 *   2. 分类逻辑：syncSectionSticky() 只给顶层 section 打 sec-scope（嵌套
 *      section 不参与），并按顶栏实际高度写 --sticky-top。
 *   3. 挂载点：切页、resize、改限高都会重算，否则换页后新页区块没有类。
 *
 * Run with Node: node tests/_test_section_sticky_headers.js
 */
'use strict';
const assert = require('assert');
const {dashboardHtml, dashboardScript} = require('./_dashboard_source.js');

const html = dashboardHtml();
const script = dashboardScript();

let checks = 0;
function check(label, ok, detail) {
  checks++;
  assert.ok(ok, label + (detail === undefined ? '' : '  -> ' + detail));
}

/* ---- 1. CSS 契约 ------------------------------------------------------- */

check(/\.main-page section\.sec-scope\{padding-top:0\}/.test(html),
  '顶层区块要把自带 padding-top 归零，否则吸顶后顶部漏出一条滚动内容');
check(/\.main-page section\.sec-scope>:first-child\{position:sticky;top:var\(--sticky-top,0px\);[^}]*padding-top:18px;margin-bottom:0!important;padding-bottom:14px\}/.test(html),
  '首行必须 sticky、用 --sticky-top、把 padding-top 挪上来并把 margin 折成 padding');
check(/body\.win-capped \.main-page section\.sec-scope\.section-fits\{max-height:none!important;overflow:clip!important\}/.test(html),
  '限高但没超高的区块必须还原成整页滚动，否则标题钉在区块顶部而不是顶栏下沿');
check(/body\.win-capped \.main-page section\.sec-scope\.section-fits>:first-child\{top:var\(--sticky-top,0px\)\}/.test(html),
  '整页滚动的区块，首行 top 要跟着顶栏高度，而不是 0');
check(/#pageAnalytics section\.panel\.sec-scope>\.phead\{position:sticky;top:var\(--sticky-top,0px\);z-index:5\}/.test(html),
  '看板面板的 .phead 要从 relative 改成 sticky（它是该面板的标题行）');
check(/@media \(max-width:860px\)\{\s*body\.win-capped \.main-page section\.sec-scope\{max-height:none!important;overflow:clip!important\}/.test(html),
  '窄屏不该启用区块内部滚动：触屏上双层滚动很难用');
check(/@media \(max-width:860px\)\{[\s\S]{0,200}?\.main-page section\.sec-scope>:first-child\{padding-top:14px\}/.test(html),
  '窄屏区块 padding 是 14px，吸顶首行的 padding-top 要跟着缩');

/* ---- 2. 分类与高度 ----------------------------------------------------- */

check(/function syncSectionSticky\(\)/.test(script),
  '缺少 syncSectionSticky()，CSS 里的 sec-scope / section-fits 就没人打');
check(script.indexOf("sec.classList.toggle('sec-scope', !nested)") >= 0,
  '只有顶层 section 该打 sec-scope（嵌套 section 的标题不参与吸顶）');
check(script.indexOf("if(p.tagName === 'SECTION'){ nested = true; break; }") >= 0,
  '嵌套判定要按祖先里有没有 SECTION');
check(script.indexOf("sec.classList.toggle('section-fits', fits)") >= 0,
  '要按「限高开着且区块确实超高」决定是否保留内部滚动');
check(script.indexOf("const narrow = window.matchMedia('(max-width:860px)').matches") >= 0,
  '窄屏要单独判定，和 CSS 的 860px 断点对齐');
check(script.indexOf("root.style.setProperty('--sticky-top'") >= 0,
  '--sticky-top 必须按顶栏实际高度写入，写死会对不齐');
check(script.indexOf("document.getElementById('nextTopbar')") >= 0
      && script.indexOf("document.querySelector('header')") >= 0,
  '顶栏在 next 布局是 #nextTopbar、经典布局是 header，两种都要量');

/* ---- 3. 挂载点 --------------------------------------------------------- */

const switchAt = script.indexOf('function switchMainTab(');
const switchEnd = script.indexOf('\nfunction ', switchAt + 10);
const switchBody = script.slice(switchAt, switchEnd > switchAt ? switchEnd : undefined);
check(switchBody.indexOf('syncSectionSticky') >= 0,
  '切页后必须重算：否则新页的区块没有 sec-scope，标题不吸顶');

const applyAt = script.indexOf('function applyWinMaxHeight(');
const applyEnd = script.indexOf('\nasync function ', applyAt + 10);
const applyBody = script.slice(applyAt, applyEnd > applyAt ? applyEnd : undefined);
check(applyBody.indexOf('syncSectionSticky') >= 0,
  '改限高会改变「哪些区块超高」，必须重算分类');

check(/window\.addEventListener\('resize', function\(\)\{[\s\S]{0,300}?syncSectionSticky\(\)/.test(script),
  'resize 会改变顶栏高度（窄屏 60px / 桌面 68px），要重算 --sticky-top');

/* ---- 4. 三语：新开关的文案 -------------------------------------------- */

check(/'模型别名开关': 'Model alias switch'/.test(html), '英文词典缺「模型别名开关」');
check(/"模型别名开关": "模型別名開關"/.test(html), '正體詞典缺「模型別名開關」');
check(/'已启用：模型别名（别名与原名都可调用）'/.test(html), '英文词典缺启用别名的 toast');
check(/"已关闭：模型别名（只按原名调用）"/.test(html), '正體詞典缺关闭别名的 toast');

process.stdout.write('section sticky headers: ' + checks + ' checks passed\n');
