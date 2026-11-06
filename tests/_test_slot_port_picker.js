/* 代理槽的端口下拉：地址栏旁边能直接挑 mihomo 端口，选中后写回地址。
 *
 * 背景：槽位的「代理地址」一直是纯文本输入框，把端口从 7890 改成 17926
 * 这类节点专属口虽然能保存生效，但得手敲端口、还得记住哪个端口是哪个节点。
 * 接了 mihomo-pool 后服务端能给出「端口 → 节点名」映射，编辑器据此画下拉。
 *
 * 这个套件钉住四件事：
 *   1. 没有端口列表（没接 mihomo-pool）时只画地址框，行为与旧版一致；
 *   2. 有列表时画下拉，当前地址的端口被选中，选项带节点名；
 *   3. 选中端口后地址被改写成 http://127.0.0.1:<port> 并标记未保存；
 *   4. portOfUrl 只认本机回环地址，远端地址的端口不会被误认。
 *
 * Run with Node: node tests/_test_slot_port_picker.js
 */
'use strict';
const assert = require('assert');
const {dashboardHtml, dashboardScript} = require('./_dashboard_source.js');
const dom = require('./_dom_stub.js');

const html = dashboardHtml();
const script = dashboardScript();

/* ---- 0. 三语词典：新增的两条文案都要有词条 -------------------------- */

assert.ok(script.includes("'选端口…': 'Pick a port…'"),
  'EN 词典应有「选端口…」条目');
assert.ok(script.includes('"选端口…": "選埠…"'),
  'Hant 短语表应有「选端口…」条目');

const legend = '接了 mihomo-pool 时，端口下拉可直接挑节点；节点专属口（17901+）永远绑同一个节点，共享口（7890-7892）会随轮换变化。';
assert.ok(script.includes("'" + legend + "': 'With mihomo-pool connected"),
  'EN 词典应有图例整句条目');
assert.ok(script.includes('"' + legend + '": "接了 mihomo-pool 時'),
  'Hant 短语表应有图例整句条目');

/* ---- 1. 纯函数：portOfUrl 只认本机回环 ------------------------------ */

dom.installDom({
  fetch: () => Promise.resolve({ok: true, status: 200,
    json: () => Promise.resolve({}), text: () => Promise.resolve('{}')}),
});

let api;
const realLog = console.log;
console.log = () => {};
try {
  api = new Function(script + `
    return {
      portOfUrl: portOfUrl,
      slotUrlCellHtml: slotUrlCellHtml,
      slotNameCellHtml: slotNameCellHtml,
      pickSlotPort: pickSlotPort,
      getSlotPorts: function(){ return SLOT_PORTS; },
      setSlotPorts: function(v){ SLOT_PORTS = v; },
      getSlots: function(){ return PROXY_SLOTS; },
      setSlots: function(v){ PROXY_SLOTS = v; },
      isDirty: function(){ return SLOTS_DIRTY; },
      resetDirty: function(){ SLOTS_DIRTY = false; },
      renderProxySlots: renderProxySlots,
    };`)();
} catch(e) {
  console.log = realLog;
  console.error('脚本求值失败:', e.message);
  process.exit(1);
}
console.log = realLog;

assert.strictEqual(api.portOfUrl('http://127.0.0.1:7890'), '7890');
assert.strictEqual(api.portOfUrl('http://127.0.0.1:7890/'), '7890');
assert.strictEqual(api.portOfUrl('http://localhost:17926'), '17926');
assert.strictEqual(api.portOfUrl('http://10.0.0.5:7890'), '',
  '远端地址的端口不能被当成 mihomo 端口');
assert.strictEqual(api.portOfUrl('http://user:pass@127.0.0.1:7890'), '',
  '带凭据的地址不参与端口识别');
assert.strictEqual(api.portOfUrl('socks5://127.0.0.1:7890'), '',
  '只有 http(s) 参与端口识别');
assert.strictEqual(api.portOfUrl(''), '');

/* ---- 2. 没有端口列表时只画地址框 ------------------------------------ */

api.setSlotPorts([]);
{
  const cell = api.slotUrlCellHtml({url: 'http://127.0.0.1:7890'}, 0);
  assert.ok(cell.includes('<input'), '没有端口列表时仍要有地址输入框');
  assert.ok(!cell.includes('<select'), '没有端口列表时不应画下拉');
}

/* ---- 3. 有端口列表时画下拉，当前端口被选中，选项带节点名 ------------ */

api.setSlotPorts([
  {port: 7890, node: '直连-新加坡01'},
  {port: 7891, node: '直连-香港03'},
  {port: 17926, node: 'pro-家庭宽带-日本KDDI-2x'},
]);
{
  const cell = api.slotUrlCellHtml({url: 'http://127.0.0.1:7891'}, 2);
  assert.ok(cell.includes('<select'), '有端口列表时应画下拉');
  assert.ok(cell.includes('value="7891" selected'), '当前地址的端口应被选中');
  assert.ok(cell.includes('直连-香港03'), '选项应带节点名');
  assert.ok(cell.includes('选端口…'), '应有未选占位项');
  assert.ok(cell.includes('pickSlotPort(2,'), '下拉应挂 pickSlotPort 并带上行号');
  assert.ok(cell.includes('http://127.0.0.1:7891'), '地址框仍保留完整地址');
}

/* ---- 4. 选中端口写回地址并标记未保存 -------------------------------- */

api.setSlots([{id: 'slot-1', name: 'a', url: 'http://127.0.0.1:7890', enabled: true}]);
api.resetDirty();
api.pickSlotPort(0, '17926');
assert.strictEqual(api.getSlots()[0].url, 'http://127.0.0.1:17926',
  '选中端口应把地址改写成该端口');
assert.strictEqual(api.isDirty(), true, '改端口后应标记为未保存');

/* ---- 5. 表格里每一行都用同一个单元格渲染器 -------------------------- */

api.setSlots([
  {id: 'slot-1', name: 'a', url: 'http://127.0.0.1:7890', enabled: true},
  {id: 'slot-2', name: 'b', url: 'http://127.0.0.1:17926', enabled: true},
]);
api.renderProxySlots();
{
  const box = document.getElementById('slotList');
  const out = String(box && box.innerHTML);
  assert.ok(out.includes('pickSlotPort(0,'), '第 1 行应有端口下拉');
  assert.ok(out.includes('pickSlotPort(1,'), '第 2 行应有端口下拉');
  assert.ok(out.includes('value="17926" selected'), '第 2 行应选中 17926');
}

/* ---- 6. 名称单元格：手填名称优先，节点名作小字 ---------------------- */

assert.strictEqual(api.slotNameCellHtml({name: 'mihomo-fixed', node: '直连-香港01'}, 0)
  .includes('直连-香港01'), true, '手填名称旁应显示当前节点名');
{
  const cell = api.slotNameCellHtml({name: 'mihomo-fixed', node: '直连-香港01'}, 0);
  assert.ok(cell.includes('value="mihomo-fixed"'), '名称输入框保留手填值');
  assert.ok(cell.includes('直连-香港01'), '节点名以小字跟在下面');
}
{
  const cell = api.slotNameCellHtml({name: '', label: '香港 机房', node: 'pro-香港-03'}, 1);
  assert.ok(cell.includes('placeholder="香港 机房"'), '名称留空时 placeholder 显示自动标签');
  assert.ok(cell.includes('pro-香港-03'), '名称留空时节点名同样显示');
}
{
  const cell = api.slotNameCellHtml({name: '直连-香港01', node: '直连-香港01'}, 2);
  assert.ok(!cell.includes('font-size:11px'), '名称与节点名相同时不重复显示小字');
}
{
  const cell = api.slotNameCellHtml({name: 'mihomo-fixed', node: ''}, 3);
  assert.ok(!cell.includes('font-size:11px'), '拿不到节点名时不画小字');
}

/* ---- 7. 名称单元格随节点轮换更新 ------------------------------------ */

/* 端口下拉的选项里也带节点名，整表断言会被它干扰；这一节只看名称列，
 * 所以先清空端口列表，让表格里只剩名称小字这一处节点名。 */
api.setSlotPorts([]);

api.setSlots([
  {id: 'slot-1', name: 'mihomo-rotate', url: 'http://127.0.0.1:7891', node: '直连-香港03', enabled: true},
]);
api.renderProxySlots();
{
  const box = document.getElementById('slotList');
  const out = String(box && box.innerHTML);
  assert.ok(out.includes('直连-香港03'), '渲染时带上当前节点名');
}
api.setSlots([
  {id: 'slot-1', name: 'mihomo-rotate', url: 'http://127.0.0.1:7891', node: 'pro-日本02', enabled: true},
]);
api.renderProxySlots();
{
  const box = document.getElementById('slotList');
  const out = String(box && box.innerHTML);
  assert.ok(out.includes('pro-日本02'), '节点换掉后小字跟着换');
  assert.ok(!out.includes('直连-香港03'), '旧节点名不应残留');
}

console.log('slot port picker assertions passed');
