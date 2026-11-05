# workbuddy2api-hub 运维版 —— 升级与部署指南

本仓库是 **WorkBuddy2API-Hub 的运维定制版**，在上游基础上叠加了本机（Firecracker microVM）部署所需的
**本地改造**与**部署脚本**。

## 仓库关系

| 角色 | 仓库 | 用途 |
|---|---|---|
| **上游（只读参考）** | `ardeyouxipianyi/workbuddy2api-hub` | 作者原仓库，**永远从这里拉取新版本** |
| **本仓库（origin）** | `qq928820655/workbuddy2api-hub` | 上游 + 本地改造 + 部署脚本，**升级产物同步到这里** |

```
git remote -v
# origin    https://github.com/qq928820655/workbuddy2api-hub.git   (推送目标)
# upstream  https://github.com/ardeyouxipianyi/workbuddy2api-hub.git (只读参考)
```

> 本仓库**私有**。运行数据（`accounts/`、`usage/`、`server.log`）已被 `.gitignore` 排除，
> 不会随提交上传。

## 一、当前基线

- 基于上游 **v1.10.11**（commit `6e1e548`），2026-11-05 升级（v1.10.8 → v1.10.11，55 个上游提交）
- 其上是**按主题拆开的**本地提交（`ops:` 基线提交 + 补丁 7/9/10/11/12/13 + 补丁 14 各自的 feat/fix + docs），标签 `ops-20261105`
- 升级时**重放这一串提交**即可（`git log upstream/main..main`）

> v1.10.8 → v1.10.11 的上游要点：**仍然没有收编任何本地补丁**（补丁 7 透明等待 / 9 affinity 落盘 /
> 10 chat head / 11 代理门禁+自动分配 / 12 task-only 保留出口 / 13 对外名称，在 `v1.10.11` 里
> `grep` 全为 0；**补丁 14 的 400 名额归还在上游同样缺**——`if exc.code == 400` 前无 release）。
> 上游新能力：**面板控制台式外壳**（左侧菜单 + 图表 + 筛选，`feat/console-ui-shell` #725，
> v1.10.9 起成为默认布局，可用 `window.__NEXT_UI__` 切回旧版）、**账号表分页 + 轮询指纹跳过 +
> 自动补积分按需点名**（#786）、**添加账号时可指定或随机分配登录出口代理槽**（#788）、
> 用量 checkpoint 遇状态锁忙即跳过（#787）、**国际版每日活跃总开关 `daily_activity`**（#789，
> 缺省开）、**`WB_DUMP_11_128` 出站 body 取证开关**（#778）、**启动入口改 `python3 -m wb_proxy`
> 省 47-54MB 常驻**（#777）、**风控连坐暂停保护自定义时长 + 一键立即解除**（#785）、
> CodeArts 一大串（模型目录透传倍率 #773、视觉 #760、推理强度 #761、账号备注与任务开关 #759、
> 429 状态保持 #758、签到与 token 保活 #762）、端口探活拒绝「能连不答」的占端口（#779）、
> Claude Code intro 指纹中和（#780）、侧栏 active 与 aria-current 同步（#768）、
> 删除废弃的 `WB_DEEPSEEK_FLASH_FORCE_SG`（#776）、账号分组（v1.10.11）、413 响应修复。
>
> **rebase 冲突 2 处**：`wb_proxy.py` 1 处（`_route_accounts_set_all` —— 上游新增了按 `group`
> 批量启停，我们的补丁 11 在同一函数末尾加了 `maybe_auto_assign_slots()`；**两侧合并**：保留上游
> 的分组逻辑 + 我们的自动分配钩子）、`README.md` 1 处（套件计数行，取上游侧后按 tree 重算为
> **276 = 209 Python + 67 JS**）。其余 20 个提交零冲突。
>
> **测试基线 273 过 / 3 挂**（`_test_breaker_fairness` / `_test_egress_backoff` /
> `_test_pool_backoff`，三个上游既有失败，纯 upstream worktree 同样挂）。
>
> v1.10.7 → v1.10.8 的上游要点：**仍然没有收编任何本地补丁**（补丁 7 透明等待 / 9 affinity 落盘 /
> 10 chat head / 11 代理门禁+自动分配 / 12 task-only 保留出口 / 13 对外名称，在 `upstream/main`
> 里 `grep` 全为 0，继续保留；**补丁 14 的 400 名额归还在上游同样是缺的**，见下方）。
> 上游新能力：CodeArts 出口工具定义归一化（修 `Tool function cannot empty`，#750/#752）、
> CodeArts `save_config` 读-改-写加锁（#751）、CodeArts 账号 UID 内联 handler 白名单（#757）、
> 每日用量折叠按 inode + 尾签名校验 offset（修 `logrotate copytruncate` 后日限算错，#755）、
> **出站身份诊断脚本 `scripts/diagnose_identity.py` + `docs/TROUBLESHOOTING-11-128.md`**（#756）、
> 嵌套 namespace 丢父路径与 `responses_to_chat()` 的 `tool_choice` 回写修复（#736）、
> 账号删除时清任务快照（#745）、模型列表长文本折行（#749）。
> **上游删除了 `deepseek_flash_force_sg` 出站开关**（函数改恒 False、面板卡片与模型列表胶囊全删，
> 国际版 `deepseek-v4.1-flash` 统一按真实 0.11x 计费）——本机 `settings.json` 里该键本来就是 `None`，
> 无数据迁移问题；rebase 时该行与我们的 `transparent_retry_wait` 同区，**取我们这行、丢掉 force_sg**。
>
> **rebase 冲突 6 处**：`wb_proxy.py` 1 处（`runtime_settings_view` 里 force_sg 行与我们补丁 7 的
> `transparent_retry_wait` 同区）、`README.md` 5 处（历史提交的 changelog 段落上下文已过期，
> 与上游 v1.10.8 把 README 大改（656 行 → 241 行，正文搬进 `docs/CHANGELOG.md`）叠加）。
> **README 冲突一律取上游侧**（`git checkout --ours README.md`），本地条目在 rebase 完成后
> 统一补进 `docs/CHANGELOG.md` 的「未发布」段 + 重算套件计数行。
>
> v1.10.1 → v1.10.7 的上游要点：**仍然没有收编任何本地补丁**（补丁 7 透明等待 / 9 affinity 落盘 /
> 10 chat head / 11 代理门禁+自动分配 / 12 task-only 保留出口 / 13 对外名称，在 `upstream/main`
> 里 `grep` 全为 0，继续保留）。上游新能力：**国际版目录补回 `deepseek-v4.1-flash`**（#741/#742，
> 附带 `deepseek_flash_force_sg` 出站开关）、生图与异步生视频媒体能力（#728）、
> 设置页二级分类胶囊导航、CodeArts 签到活动识别与自动签到（#747）、
> 国内版 deepseek-v4.1-flash 计费与出站路由修复（#748）、Codex 首段渠道指纹与 400 账号归因（#744）、
> 成长中心全能任务扩充、账本原子追加（并发下不再丢行）、`_test_rate_limit_reset_at` 夹具改相对时钟（#737）。
>
> **rebase 冲突 5 处**：`wb_proxy.py` 3 处（补丁 11 的 `proxy_auto_assign_*` 与上游新增
> `media*` 字段同区、补丁 12 的 `_slot_active`、补丁 13 的 `alias_model_entries` 与上游
> `model_entry(..., realm)` 新签名同区）、`README.md` 2 处（套件计数行）。两处 `wb_proxy`
> 冲突都是**两侧合并**（上游字段 + 我们的字段都要保留），`README` 计数取上游侧、最后按 tree 重算。
>
> **测试基线 260 过 / 3 挂**：全部是上游既有失败（`_test_breaker_fairness` /
> `_test_egress_backoff` / `_test_pool_backoff`，纯 upstream worktree 同样挂）。
> `_test_rate_limit_reset_at` 已被上游 #737 修好（相对时钟），不再是挂项。
>
> **本轮唯一的测试改动**：上游 v1.10.5 在**国际版 `deepseek-v4.1-flash` 那一行的 ID 单元格**
> 里加了「原生免费 / 强制 -sg」出站切换按钮，ID 单元格的纯文本因此变成
> `deepseek-v4.1-flash原生免费强制 -sg`。`_test_models_catalog_source.js` 与
> `_test_model_probes.js` 都用「ID 单元格纯文本」当行键，会整体错位。改为优先取 `<b>` 里的 id
> （`idOf()`），纯上游 worktree 不受影响。

> v1.8.0 → v1.9.2 的上游要点：**没有收编我们剩余的本地补丁**（补丁 7 透明等待 / 9 affinity 落盘 /
> 10 chat head / 11 代理门禁+自动分配在 `upstream/main` 里 `grep` 均为 0，继续保留）。
> 上游新增：#658（pbkdf2 缺失明确 500 + `crypto_ok`）、`WB_STOP_AT_SSE_DONE=1` 流式终止、
> `WB_CACHE_HTTP_ERROR_BODY=1` 错误正文缓存、`/health` 按区域与模型报可用数、
> **下拉误判全宽竖排改为只认显式 `width:100%`**（= 我们 a390078 的 ①，已被上游收编）、
> 活动表短标签不折行、昵称列分档截断、DSH 文件引用段 11-128 指纹中和、池空报错说清等多久、
> 6004 也保住「配额用尽」、跨出口回退等。rebase 冲突：`wb_proxy.py` 3 处（补丁 7 ×2、
> 补丁 10 ×1）、`dashboard.html` 1 处（词典区）、`README.md` 3 处；启动处取
> `maybe_auto_assign_slots("startup") + POOL.apply_reserve_credits()` 两侧合并。
> 测试基线：237 个套件（178 Python + 59 JS），**234 过 / 3 挂**——仅 `_test_breaker_fairness`
> /`_test_egress_backoff`/`_test_pool_backoff` 三个上游既有失败（纯上游同样挂）。

> v1.7.29 → v1.8.0 的上游要点：**我们提的 PR 全部被收编**——#607（流式单 chunk id，
> 对应旧补丁 6.5）、#612（账号级并发上限 + 更稳的会话粘滞键，对应旧补丁 5/6），
> 这三个本地补丁**自本版起作废勿重打**。上游另有：**SSE 心跳**（#578，15s 静默发
> `: keepalive`，三条流式路径共用）、**Token 保活提前量 2h→48h**（`WB_KEEPALIVE_LEAD_HOURS`）、
> **成功请求解除凭证失效标记**、**重启后恢复 429 模型级限流窗口**、**静态 API Key 账号**
> （企业微信 WorkBuddy / CodeBuddy CLI，#572）、**版本回退 + 更新备份**（默认留 1 份）、
> **修复调度器日志黑洞**（读错模块副本）、**修复签到把业务失败记成成功**、
> **修复面板 keep-alive `{}GET 501`**、**修复 10105 活跃会话 10 条上限**（网页活跃收尾释放）、
> **Codex remote compaction v2**、**跨出口回退（国际版→国内版，默认关）**、
> **11-128 GUI 指纹修复**、**minimax CN 专属判定收窄 + OpenCode 真实上下文上限**、
> **会员档位胶囊**、**看板自绘下拉框**。rebase 冲突集中在 `wb_proxy.py`（补丁 7 透明等待
> ×2 处、补丁 10 chat head ×1 处）、`dashboard.html`（补丁 5/6 词典区 ×1 处）、
> `README.md` ×3 处；**已被上游收编的补丁内容一律取上游侧**。
> 已知坑：dc2013b 里旧补丁 5/6 的设置卡 HTML 会在 rebase 时**悄悄重复插入**
> （`账号级并发上限`/`更稳的会话粘滞键` 卡片出现两份、元素 id 重复）——升级后必须
> `diff <(git show upstream/main:dashboard.html) dashboard.html` 核对卡片数量与上游一致。
> 测试基线：229 个套件（170 Python + 59 JS），**225 过 / 4 挂**——`_test_breaker_fairness`
> /`_test_egress_backoff`/`_test_pool_backoff` 为上游既有失败（纯上游同样挂），
> `_test_release_engineering` 需要把 README 套件计数改成实际值。

> 想随时看「本地到底改了哪些东西」：
> ```bash
> git show ops-20261030              # 完整 diff
> git diff upstream/main ops-20261030 # 同上，指定区间
> ``

## 二、本地改造清单（从上游拉新版后必须重做）

**重要**：本地改造是**代码逻辑/部署编排**，不是配置。升级到上游新版后必须重新叠加，否则会退化。
而且**上游每个版本都要重新确认**——它可能已经自己修了（v1.7.8 收编了旧 max_tokens clamp、
v1.7.9 的 `08c274d` 收编了旧 P0 归位补丁）。

| # | 改造 | 不改的后果 |
|---|---|---|
| ~~1~~ | ~~`_dispatch_chat_post` 归位 Handler 类~~ | **已被上游收编**（v1.7.9 `08c274d`），勿重打；见下方「上游可能已自行修复」 |
| ~~2~~ | ~~Anthropic `input_tokens` 缓存口径~~ | **已被上游收编**（v1.7.17 `bf921a6` / PR #479），勿重打；`grep -c "prompt_tokens - cache_read - cache_creation" wb_proxy.py` 应为 1 |
| ~~3~~ | ~~看板移动端 3a–3h 全部八项~~ | **已被上游收编**（v1.7.17–v1.7.20，PR #480/#481/#482/#496/#497/#498/#501），勿重打；判定命令见下方 3a–3h 各节 |
| ~~3i~~ | ~~打卡按钮组补回 `tb-checkin` 类~~ | **已被上游收编**（v1.7.29 / PR #585），勿重打；`grep -c "tb-group tb-checkin" dashboard.html` 应为 1（上游自带） |
| 4 | 部署脚本 + `.gitignore` + 显式开启 Messages（`start.sh` 等） | 服务不便启停；**v1.7.8 起 Anthropic Messages 默认关闭**，客户端会 400 |
| ~~5~~ | ~~账号级并发上限~~ | **已被上游收编**（v1.8.0 / PR #612，`feat(dispatch): per-account concurrency cap and stable affinity key`），勿重打；`grep -c "def account_slot_acquire" wb_proxy.py` 应为 1（上游自带） |
| ~~6~~ | ~~更稳的会话粘滞键~~ | **已被上游收编**（v1.8.0 / PR #612，与补丁 5 同一提交），勿重打；`grep -c "def affinity_stable_key_enabled" wb_proxy.py` 应为 1（上游自带） |
| 7 | 整池冷却时的透明等待（`wb_proxy.py` + `start.sh`） | 一次短暂 429 会让下游（CPA / Claude Code / harness）中断整轮、要人手动重发。默认等 30s，窗口内恢复就接着发，客户端看不到 429 |
| ~~8~~ | ~~看板用量统计窄屏排版（仅 ≤640px）~~ | **已被上游收编**（v1.7.29 / PR #588），勿重打；判定：`grep -c "#pageAnalytics .kpi .s .kvi{display:block}" dashboard.html` 应为 1（上游自带） |
| 9 | 会话绑定落盘 + `body_wait` 日志（`wb_accounts.py` + `wb_proxy.py`） | 重启后所有长会话被重新分到别的账号、整段前缀重算（180k 上下文缓存 99.9%→15%，ttft 2.5s→15.4s）；上传慢与上游慢无法从日志区分 |
| 10 | 请求到达即记日志 `chat head`（`wb_proxy.py`） | 客户端上传慢时那段窗口日志全空白，分不清「请求没到本进程」与「网关慢」 |
| 11 | 代理出口握手延迟门禁 + 每 N 个账号自动分配（`wb_proxy.py` + `wb_settings.py` + `dashboard.html`） | 跨洋整请求口径把可用出口全判死或全放行；账号多了要一个个手工绑出口 |
| 12 | 任务型账号（`enabled=false, tasksEnabled=true`）也保留代理出口（`wb_proxy.py`） | 关掉转发只留任务的号被释放出口 → 签到/成长/旅行/打卡全从本机 IP 出去，多号同 IP 关联 |
| 13 | 面板「对外名称」列（对外名 → 上游原名）+ `/v1/models` 宣告别名 + key 限制接受两种写法 + 回复回显别名（`wb_proxy.py` + `wb_settings.py` + `dashboard.html`） | 别名只能手改 `accounts/settings.json`；客户端清单里看不到别名、回显 model 与请求不符 |
| 14 | 400 / 未处理 4xx 透传前归还账号并发名额（`wb_proxy.py`） | 一次 400（如 11-128）就让账号在 `account_max_concurrent` 里永久 +1；上限为 1 时该号从此「已在服务 1 个请求」，面板健康、测试也绿，但派发永远轮不到，只有重启进程才恢复 |

### ~~补丁 5：账号级并发上限~~（**已被上游收编** v1.8.0 / PR #612，勿重打）

**要解决的问题**：上游按「账号 + 分钟」计 token，而一个大上下文会话单请求就带十几万 token。
两个会话同时压在一个账号上很容易过百万 token/分钟 → 上游 429 → 网关停放该账号并换号 →
新账号没有这段对话的前缀缓存 → 缓存命中率 99% → 0，首字 1.5s → 5-6s。
根因不在网关并发槽位（全局闸门 96 槽没满），也不在 CPA。

**设计**：可选开关，默认 `0`（不限）——关闭时 `account_slot_acquire()` 恒真且不记账，
派发路径与上游逐字节一致。设为 `1..10` 时每个账号同时最多接这么多个请求；
名额满时**换一个账号**（不是排队），保证两个会话各走各的账号、各自保留缓存。

**三个文件**：

1. `wb_settings.py`：`ACCOUNT_MAX_CONCURRENT_KEY` / `ACCOUNT_MAX_CONCURRENT_MAX=10` /
   `account_max_concurrent(accounts_dir)`（0=不限，坏数据回退 0）/
   `set_account_max_concurrent(accounts_dir, value)`（严格 int，0..10，否则 `ValueError`）。
2. `wb_proxy.py`：
   - `_ACCOUNT_INFLIGHT` / `_ACCOUNT_INFLIGHT_LOCK`、
     `account_slot_acquire(account, limit=None)` / `account_slot_release(account)` /
     `account_inflight_snapshot()`、`ACCOUNT_SLOT_WAIT_MAX = 2.0`；
   - `bind_account_slot_to_response(response, account)`：名额挂到响应对象的 `close()` 上，
     一次性保护防重复扣减。**必须占到 body 读完**，不能停在「拿到响应头」——流式回复拿到头
     之后还要读几十秒，那段时间上游仍算该账号在跑。`response is None` 时立刻归还（否则泄漏）。
   - `open_upstream()`：新增 `busy` 集合（与 `tried` 分开，名额满 ≠ 失败，不影响熔断/亲和）、
     `slot_held` 标记、内嵌 `pick_account()`（循环换号直到占到名额，全满返回 None）；
     循环开头统一归还、成功路径绑定后置空、循环耗尽后兜底归还；
     `pinned` / `refresh_uid`（固定账号没法换号）用 `ACCOUNT_SLOT_WAIT_MAX` 有界等待。
   - 名额全满时报 `RateLimited`，文案明说「每个可用账号都在跑 N 个请求」——
     不能落到「全部停用/冷却/过期」，否则排查的人会去查账号状态。
   - `/settings/save` 接受 `account_max_concurrent`；`runtime_settings_view()` 返回
     `account_max_concurrent` / `account_max_concurrent_max` / `account_inflight`。
3. `dashboard.html`：设置页新增「账号级并发上限」数字输入（0–10）+ 保存按钮
   （`saveAccountConcurrent()`），`loadSettings()` 里回填；中英对照表同步。

**验证**：`python3 tests/_test_account_concurrency.py`（19 个用例，含真实 `open_upstream` +
打桩池的调度测试：满号跳过、名额占到 close、全满报池忙、失败路径不泄漏、关闭时行为不变）。

### ~~补丁 6：更稳的会话粘滞键~~（**已被上游收编** v1.8.0 / PR #612，勿重打）

**要解决的问题**：`affinity_route()` 只用 `msgs[:2]`（system + 首条 user）算会话键。
两个开场白相同的会话（同一客户端、同一模板首问）算出同一个 `pfx-xxx`，共享同一个
`SessionAffinity` 绑定槽 → 每轮互相覆盖 → 两个会话轮流换账号 → 缓存每轮归零。
`account_max_concurrent` 对此**无效**：它只保证两个请求不在同一时刻撞同一号，
下一轮照样换。

**设计**：`affinity_stable_key_enabled` 开关（默认关）。关着时 `affinity_route()`
与上游一字不差；打开后哈希头从 `msgs[:2]` 扩到 `msgs[:3]`（多算首条 assistant 回复），
两个会话从第 2 轮起算出不同键、各走各的账号。同一段对话每轮仍算出同一个键（粘滞成立）。
第 1 轮还没有 assistant 回复，仍退回前两条消息，两会话会撞一次——已知且可接受。

**三个文件**：

1. `wb_settings.py`：`AFFINITY_STABLE_KEY_ENABLED_KEY` /
   `affinity_stable_key_enabled()`（只有 JSON `true` 才算开）/ 
   `set_affinity_stable_key_enabled()`（**严格** `isinstance(enabled, bool)`，
   `bool("false")` 是真值，静默转换会把开关悄悄打开）。
2. `wb_proxy.py`：`affinity_stable_key_enabled()` 包装器；`affinity_route()` 里
   `if affinity_stable_key_enabled() and len(msgs) > 2: head = msgs[:3]`；
   `/settings/save` 与 `runtime_settings_view()` 各加一处。
3. `dashboard.html`：设置页「更稳的会话粘滞键」勾选框 + `saveAffinityStableKey()`，
   `loadSettings()` 回填；中英对照表同步。

**验证**：`python3 tests/_test_affinity_stable_key.py`（14 个用例：开关读写严格性、
关闭时键等于老算法、打开后同开场白分开、同一对话每轮稳定、可回退、池子里两会话各钉各号）。

**回退**：面板取消勾选即可，立刻回到上游逻辑，无需改代码。

### ~~补丁 6.5：流式回复只带一个 chunk id~~（**已被上游收编** v1.8.0 / PR #607，勿重打）

**要解决的问题**：一次流式回复同时带**两个 chunk id**——上游原始帧用上游 id（`01a1…`），
而网关重写的正文帧用自己的 `chatcmpl-wb-*`，于是同一轮回复在客户端看来是两条交错的流。
思考那条流**永远不带 `finish_reason`**，按 id 管理流状态的客户端（很多 SDK / harness 都是）
会一直等它 → 界面永久停在「生成回复中」，思考区不再更新，而网关日志里这一轮几秒前就完成了。
用户体感是「不是慢，是彻底没反应、后台也没反应」。

**设计**：出站前把每一帧的 id 统一成网关自己的 id（思考、正文、结束、usage 帧一致）。

```python
# _chat_stream_response() 里，clean_chunk() 之前
if isinstance(maybe, dict) and maybe.get("id"):
    maybe["id"] = stream_chunk_id
```

**验证**：`python3 tests/_test_stream_single_id.py`（15 项断言）。真机复现：修复前
`2 distinct ids`、首条流 `finish=None`；修复后 `1 distinct id`、`finish=stop`。
调试脚本 `/tmp/opencode/finalproof.py <port>` 可直接对比。

**状态**：已提上游 **PR #607**（未合）。若上游合入 → 本补丁作废，勿重打
（判定：`grep -c "One response must carry one id" wb_proxy.py`，上游合入后由上游自带）。

### 补丁 7：整池冷却时的透明等待（默认 30 秒）

**要解决的问题**：上游偶尔会在短时间内把整个池子都打成「模型冷却」（每个号 60s 起）。
上游原来的行为是立刻回 429，但**下游拿不到「这是暂时的」这个信息**——CPA、Claude Code、
各种 harness 收到 429 只会中断这一轮，要人手动重发。而这些窗口大多只有几十秒，
等一会儿本来就能自己继续。

**设计**：`WB_TRANSPARENT_RETRY_WAIT`（默认 30 秒，设 0 关闭）。只在**进循环时**
整池已经在冷却的情况下等：每 `TRANSPARENT_RETRY_POLL`（0.25s）重新挑一次号，
有号恢复就接着发这一轮——此时客户端连一个字节都还没收到，感觉不到这次重试。
超过预算才真的报 429。

**刻意不等的三种情况**（等下去不会变好，必须立刻如实上报）：

- 日限额 / 模型额度耗尽 / 手工禁用 / 没有账号：`transparent_wait_reason()` 只看
  `throttle_wait()`，这些原因会让某个账号 `wait == 0`，直接回空串；
- **本轮自己打出来的 429**（`last_error` / `last_429` 非空）：重试同一个号只会让
  上游的软限阶梯继续升级（60s → 120s → 240s），越等越久；
- 固定账号（`/u/<ref>/`、令牌刷新后的原地重试）：没有「换一个」的余地。

**两个文件**：

1. `wb_proxy.py`：`TRANSPARENT_RETRY_WAIT` / `TRANSPARENT_RETRY_POLL` 常量；
   `open_upstream()` 内 `transparent_deadline`、`transparent_wait_reason()`、
   `wait_for_pool()`（清 `tried`/`busy` 后重挑，**不清 `charged`**——它防的是同一次
   请求给同一个账号记好几笔失败）；`account is None` 分支改成有界等待；
   重试循环从 `for _attempt in range(max_attempts)` 改成 `while` + 手动计数
   （等待不消耗尝试次数）；`runtime_settings_view()` 只读暴露 `transparent_retry_wait`。
2. `start.sh`：`WB_TRANSPARENT_RETRY_WAIT="${WB_TRANSPARENT_RETRY_WAIT:-30}"` 并 export。
3. `dashboard.html`：「自动切换出站身份」卡片加一行说明，读 `transparent_retry_wait` 展示。

**验证**：`python3 tests/_test_transparent_retry.py`（10 个用例，假时钟：等到恢复后成功、
预算外不空等、总等待不超预算、日限额/无账号立刻上报、设 0 恢复旧行为、固定账号不等、
日志只打一次、等过之后能重新挑到同一个号）。

**回退**：`WB_TRANSPARENT_RETRY_WAIT=0` 重启即回到上游行为。

### 补丁 8：【已被上游收编，勿重打】看板用量统计窄屏排版（仅 ≤640px）

**要解决的问题**：窄屏（3 列、每卡约 80–100px）沿用桌面那两行副行时，「输入/输出/思考/缓存」
会被截断成「等...」或长短不齐；第一行三张卡的副行行数不同（2/1/2 行）、「生成速度」还没有
占比色条，sparkline 各自紧跟文字往下排，第二三张的图比第一张高、卡片底部空一块。

**设计**：只改**排版**，字号/颜色/文案/分隔符口径与桌面端一致（**不缩小字号**）：

1. 副行按「桌面端原本的行」分组，每项一个 `.kvi`。桌面端 `.kline` 是 block、`.ksep`
   显示「 · 」，渲染结果与上游逐字一致；窄屏 `.kvi` 各占一行、`.ksep` 隐藏（独占一行后
   分隔符会孤零零落在行首）。
2. 第一行三张卡改成纵向 flex，`.spark` 用 `margin-top:auto` 贴到卡片底部 → 三张图等高
   44px、顶边底边对齐。缺对比行/色条的卡只是上方文字短一点，图仍在同一条线。
3. `.kvi b`（数值+单位）在第一行三张卡里 `white-space:nowrap`，避免「179」与「tok/s」
   在数字和单位之间断开。

**两个文件**：

1. `dashboard.html`（CSS，全部在 `@media (max-width:640px)` 内 + 一条桌面端 `.kline{display:block}`）：
   `#pageAnalytics .kpi .s .kline/.kvi/.ksep` 三条窄屏规则、
   `#pageAnalytics .kpi.big:nth-child(-n+3){display:flex;flex-direction:column}`、
   `... .spark{margin-top:auto}`、`... .s .kvi b{white-space:nowrap}`。
2. `dashboard.html`（JS `renderKpis()`）：`subItems(lines)` 把每条桌面行包成 `.kline`、
   每项包成 `.kvi`、项间 `.ksep`；`kTokensSub` / `kReqsSub` / `kSpeedSub` 都改用它。

**验证**：CDP 逐属性对照（fontSize / color / display / top / height / width）——
1280/1100/900/700/641px 与「注入上游 CSS」的同一页面 **IDENTICAL**；390px 下
`req items=2 lines=2`、`spd items=4 lines=4`、三张 `sparkTop` 相同且 `sparkH=44`。

**回退**：删掉那个 `@media (max-width:640px)` 块与 `.kline` 规则，JS 换回 `<br>` 拼接。

下面逐项给出**改哪个文件、哪个函数、改成什么**，可直接照抄。

### 补丁 1：【已被上游收编，勿重打】`_dispatch_chat_post` 归位 Handler 类

上游 v1.7.8 的每 key 并发改造（#359）曾把该方法错误缩进成模块级 `_release_key_slot` 里的嵌套函数，
导致 `/v1/chat/completions`、`/v1/responses` 全部 `AttributeError` 断连（预览代理表现为 530）。
**上游 v1.7.9 的 `08c274d` 已把并发 helper 移回模块级、方法归位 Handler 类**，本仓库不再携带此补丁。
若未来版本又复现（判定命令见下），按同样方式归位即可：

```bash
python3 -c "import wb_proxy; print(hasattr(wb_proxy.Handler,'_dispatch_chat_post'))"   # 必须 True
```

### 补丁 2：【已被上游收编，勿重打】Anthropic `input_tokens` 缓存口径（`wb_proxy.py`）

> **2026-10-20 起作废**：上游 v1.7.17 `bf921a6`（PR #479）已合并同一改法，`_anthropic_usage` 内直接是
> `out["input_tokens"] = max(0, prompt_tokens - cache_read - cache_creation)`。升级后只需判定
> `grep -c "prompt_tokens - cache_read - cache_creation" wb_proxy.py` 为 1，不要重复改。以下保留作历史参考。

**位置**：函数 `def _anthropic_usage(usage):`
**背景**：上游 `prompt_tokens` 是 OpenAI 口径的**总输入（含缓存命中）**；Anthropic 客户端按
`input_tokens + cache_read + cache_creation` 计算上下文，直接透传会把缓存算两次。
**改法**：先算 `cache_read/cache_creation`，再用 `max(0, prompt_tokens - cache_read - cache_creation)`
得出 `input_tokens`：

```python
def _anthropic_usage(usage):
    # ...（上游原有的 out 初始化与 `if not isinstance(usage, dict): return out` 保持不变）...

    def _as_int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    prompt_tokens = _as_int(usage.get("prompt_tokens"))
    out["output_tokens"] = _as_int(usage.get("completion_tokens"))
    cached = usage.get("prompt_cache_hit_tokens")
    if cached is None:
        cached = _best_cached_tokens(usage)
    cache_read = _as_int(cached)
    cache_creation = _as_int(usage.get("prompt_cache_write_tokens"))
    out["cache_read_input_tokens"] = cache_read
    out["cache_creation_input_tokens"] = cache_creation
    # 上游 prompt_tokens 是 OpenAI 口径的总输入（含缓存命中）。Anthropic 客户端按
    # input + cache_read + cache_creation 计算上下文，直接透传会把缓存算两次。
    out["input_tokens"] = max(0, prompt_tokens - cache_read - cache_creation)
    # ...（service_tier 等后续逻辑不变）...
```

**只改 Anthropic `/v1/messages`**；OpenAI `/v1/chat/completions`、`/v1/responses` 不动。
**判定**：`grep -n "max(0, prompt_tokens - cache_read - cache_creation)" wb_proxy.py`

### 补丁 3：【已被上游收编，勿重打】看板 `dashboard.html` 移动端（3a–3h）

> **2026-10-20 起作废**：上游 v1.7.17–v1.7.20 已把我们提的 7 个移动端 PR 全部合并
> （#480 缝隙、#481 header、#482 今日活动、#496 KPI delta、#497 账号卡徽章、#498 打卡按钮、#501 积分格）。
> 升级后逐项判定即可，全部命中就说明无需重打。唯一例外见 **3i**（#498 的类名在合并时丢了，需补一行）。
> 以下保留作历史参考。

**3a. 二级导航 14px 缝隙**——`--page-nav-top` 恒为 `header 高度 + 14`。窄屏（≤860px）下二级导航条
（`.page-sidebar`）同样吸顶在 header 下方，那 14px 就成了缝隙，滚动时正文从缝里穿过。
改两处内联脚本，窄屏不留缝（0）、宽屏保持 14：

```javascript
function pageNavHeaderOffset(page){
  const header = document.querySelector('header');
  const narrow = window.matchMedia('(max-width:860px)').matches;
  // 窄屏下二级导航条紧贴 header 底边（见 syncPageNavOffset），不再留 14px 缝，
  // 否则内容会从两条吸顶栏之间的缝隙里穿过去。
  const base = (header ? header.offsetHeight : 64) + (narrow ? 0 : 14);
  const sidebar = page ? page.querySelector('.page-sidebar') : null;
  if(sidebar && narrow){
    return base + sidebar.offsetHeight + 10;
  }
  return base;
}

function syncPageNavOffset(){
  const header = document.querySelector('header');
  const narrow = window.matchMedia('(max-width:860px)').matches;
  const top = (header ? header.offsetHeight : 64) + (narrow ? 0 : 14);
  document.documentElement.style.setProperty(PAGE_NAV_TOP_VAR, top + 'px');
}
```

**3b. header 四元素同行（≤640px）**——标题、GitHub、语言、主题全在顶部一行，页签独占下一整行。
在 `/* ===== Phone: ≤640px ===== */` 媒体块里，把上游的 `.header-left`/`.header-right`/`h1`/
`.main-nav`/`.meta` 几条规则改成（`display:contents` 让子项直接参与 header 的 flex 排布，
只在本断点生效，PC 不受影响）：

```css
  .header-left,.header-right{display:contents!important}
  h1{font-size:15px;flex:1 1 auto;min-width:0;order:1}
  .gh-link{width:36px;height:36px;flex-shrink:0;order:2}
  .lang-btn{order:3}
  .theme-dropdown-wrap{order:4}
  .main-nav{display:flex;width:100%;flex-basis:100%;gap:2px;padding:3px;order:5;overflow-x:auto;
    -webkit-overflow-scrolling:touch;scrollbar-width:thin}
  .meta{width:100%;text-align:left;font-size:11px;line-height:1.5;order:6}
```
（`h1 span`、`.theme-btn` 两条上游已有，保留即可。）

**~~3c. 账号卡积分格~~【已被上游收编，勿重打】**——上游 v1.7.16 自带
`.credit-stack` 两行结构（`.credit-main` 数值行 + `.credit-meta` 徽章行，明细按钮独占一行），
本机旧补丁（`.cred-val`/`.cred-sub`/`.cred-sub-label` 三段 CSS + credText 模板）已**作废删除**。

**~~3d. 概况卡布局~~【已被上游收编，勿重打】**——上游 v1.7.16 重设计了国际版/国内版概况卡：
大数字改为「可用积分」（`tabIntlAvailCred`，限额护栏口径）、`/ 总积分`、账号数内联、
KeyBadge 移到上方「版本中枢控制栏」。本机旧 3d 挪位补丁已**作废删除**（v1.7.16 升级时
4 处冲突均采用上游新结构，并修复 credit-row 少一个 `</div>` 的闭合）。

**3e. 移动端账号卡「今日活动」行内化（≤640px）**——上游默认把该格排成两行
（::before 标签一行、状态徽章 `align-items:stretch` 又独占一行），浪费一整行。
在 `≤640px` 媒体块里把 `td:nth-child(4)`（今日活动）改回行内：

```css
  table.account-cards td:nth-child(4){order:4;grid-column:span 6;justify-content:flex-start;flex-wrap:wrap;gap:4px 6px}
```

效果：`今日活动 [今日活跃·成功]` 同排一行（国内版双徽章靠 flex-wrap 自动换行）。
桌面表格视图不受影响（规则在媒体块内）。

**判定**：`grep -n 'td:nth-child(4){order:4;grid-column:span 6;justify-content:flex-start' dashboard.html`（1 处）。

**3f. 移动端三处真机反馈修正（≤640px，2026-10-19）**——浏览器手机模拟测不出、真机才复现：

1. **header 又有一个图标另起一行**：真机标题字宽更大，`h1` 的 `min-content` 把 GitHub/语言/主题挤下去。改 `h1{flex:1 1 0%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}`，并给 `.lang-btn`/`.theme-dropdown-wrap` 加 `flex-shrink:0`。
2. **数据看板 KPI 标题被对比百分比挤成竖排**：`.delta` 原在标题行内。把 4 个 `delta*` span 移出 `.k`、放进数值 `.v` 下方的 `.kdelta` 行；标题加 `white-space:nowrap`。同时「API 等价花费」改「API 等价」（英文 `API-equivalent`、繁体 `API 等價`）。
3. **账号卡版本/状态徽章挪到账号名右侧同行**：手机卡里隐藏 `td:nth-child(1)`（版本）与 `td:nth-child(3)`（状态）两列，在 `.acct-name-row` 末尾加 `.acct-mobile-badges`（内含版本+状态徽章，桌面 `display:none`）。

**判定**：`grep -c "acct-mobile-badges" dashboard.html`（≥3）、`grep -c "kdelta" dashboard.html`（≥5）、`grep -c "API 等价</div>" dashboard.html`（1）。

**3g. 移动端打卡按钮与「添加」同行居右（≤640px，2026-10-19）**——「每日活跃打卡 (国际版)」/「Buddy 加油站签到」原先在独立 `tb-group` 里、手机端另起一行。把该组移到「添加」之后并加 `.tb-checkin`，手机端 `margin-left:auto` 靠右；桌面端 margin 为 0，仅按钮顺序变化。

**判定**：`grep -c "tb-checkin" dashboard.html`（2：HTML + CSS）。

**3i.【已被上游收编，勿重打】打卡按钮组 `tb-checkin` 类（≤640px）**——上游合并 #498 时，CSS 规则
`#accountsBody .toolbar .tb-checkin{margin-left:auto;flex-shrink:0}` 进去了，但 HTML 里的类名被并成
了 `<div class="tb-group">`，规则悬空，手机端打卡按钮回到独立一行。**我们提的 PR #585 已于 v1.7.29
合入上游**（`9425263`），本地不再需要补。

**判定**：`grep -c "tb-group tb-checkin" dashboard.html`（1）。

**3h. 移动端积分格「积分 / 明细」错行（≤640px，2026-10-19）**——账号卡第 6/7/8 列用 `flex-direction:column-reverse` 把 `::before` 列标签排到底部，导致「积分」标签与「明细」按钮分处两行。第 7 列（积分）隐藏列标签，改在 `.credit-meta` 上用 `::before` 生成「积分」，与明细同行；数值行在上。

```css
  table.account-cards td:nth-child(7)::before{content:none}
  table.account-cards td:nth-child(7) .credit-meta::before{content:'积分';font-size:10px;color:var(--dim);font-weight:600}
```

**判定**：`grep -c "td:nth-child(7) .credit-meta::before" dashboard.html`（1）。

> **⚠️ 提 PR 不要切主工作区分支**：本服务实时读取部署目录的 `dashboard.html`，`git checkout` 到基于上游的 PR 分支会让线上立刻丢失全部本地补丁（样式「回退」）。用 `git worktree add /tmp/opencode/wb-pr -b tmp/xxx upstream/main` 在独立目录做 PR。

**判定**：`grep -n "narrow ? 0 : 14" dashboard.html`（2 处）、
`grep -c "display:contents" dashboard.html`（≥1）、
`grep -c "cred-sub" dashboard.html`（**必须 0**，旧 3c 已删）、
`grep -c "credit-stack" dashboard.html`（≥3，上游自带）。

### 补丁 4：部署编排（**本机新增，不是改上游**）

这些是上游没有、我们新增/修改的内容，升级时按下面的状态保证它们仍在：

- `start.sh` / `stop.sh`：启停脚本（**不含硬编码密码**，支持 `WB_PORT` / `WB_PANEL_PASSWORD` /
  `WB_TZ` / `WB_ENABLE_ANTHROPIC_MESSAGES`）。`start.sh` 需设：
  ```bash
  WB_ENABLE_ANTHROPIC_MESSAGES="${WB_ENABLE_ANTHROPIC_MESSAGES:-1}"
  export TZ WB_ENABLE_ANTHROPIC_MESSAGES
  ```
  **原因**：上游 `afab635`（v1.7.8）因 Messages 转换会丢 `cache_control`、缓存命中和积分消耗
  存疑，**默认关闭** `/v1/messages`。本机一直对外提供该接口，故在这里显式开启以保持行为不变
  （设 `WB_ENABLE_ANTHROPIC_MESSAGES=0` 可关闭）。
- **并发上限（2026-10-21，`start.sh`）**：上游 `wb_proxy.py:51` 的
  `WB_MAX_CONCURRENT_CHAT` 默认 **32**，与账号数无关；槽满后排队 `WB_CHAT_SLOT_WAIT`
  （默认 30s）就返回 503。本机 24 个账号共用 32 个槽偏紧，实测 120 并发长请求时有
  41 个 503。`start.sh` 里按「账号数 × 4」放大：
  ```bash
  WB_MAX_CONCURRENT_CHAT="${WB_MAX_CONCURRENT_CHAT:-96}"
  WB_CHAT_SLOT_WAIT="${WB_CHAT_SLOT_WAIT:-60}"
  export ... WB_MAX_CONCURRENT_CHAT WB_CHAT_SLOT_WAIT
  ```
  验证：80 并发短请求 **80/80 成功**、wall 2.4s、峰值 100 线程、0 个 503；
  `tr '\0' '\n' < /proc/<pid>/environ | grep WB_MAX` 应为 96。
  **调更高的代价**：上限只是网关侧闸门，真正的瓶颈是上游账号级 429 —— 压测时
  单个账号被打到 429 并冷却 60→120s（`account <uid> throttled ... retry in 120s`）。
  并发再高只会让更多账号进入冷却，不会提升有效吞吐。**注意：不要用长请求做压力
  测试**，会长时间占满槽位、拖慢真实用户请求（2026-10-21 踩过）。
- `.gitignore`：上游自带一份，我们**追加**忽略 `server.log`。

### 补丁 5：测试期望值（`tests/`）

补丁 2 改了 usage 口径，两个测试的期望值要同步（否则测试会「正确地」报错）：

- `tests/_test_anthropic_http.py`：两处 `input_tokens == 11` → **`== 7`**（原 11 含缓存 3+1）
- `tests/_test_anthropic_messages.py`：一处 `"input_tokens": 10` → **`"input_tokens": 4`**
  （该用例 `cache_read=4, cache_creation=2`，原 10 含缓存 6）

### 一次性总览：本地全部改动 = 那一个 `ops:` 提交

以上仍在生效的 4 / 5 / 6 / 6.5 / 7 全部包含在标签 `ops-20261022b` 指向的那个 `ops:` 提交里
（另有独立提交 `8a227bc` 携带 6.5）。升级时**优先用第三节的 rebase 自动重放**；
只有冲突或想手改时，才按上面逐项对照。

### 上游可能已自行修复——每版都要先确认

拉取新版后先看上游是否已经做了同样的修复，避免重复：
```bash
git log upstream/main --oneline -30
git log upstream/main -p -- wb_proxy.py | grep -n "input_tokens\|max_output_tokens\|ANTHROPIC_MESSAGES\|_dispatch_chat_post"
```

- **已被上游收编（不要重打）**：
  - gpt-* 的 `max_tokens ≤ 15 → 400` 下限问题：上游 `50ddd72`（v1.7.8）已在
    `build_upstream_body` 里对 `gpt-` 前缀模型 clamp 到 16。**旧补丁与
    `tests/_test_max_output_tokens.py` 已作废**。
  - `_dispatch_chat_post` 归位 Handler 类：上游 `08c274d`（v1.7.9）已修，**本仓库不再携带**
    （见补丁 1）。
  - 账号卡积分格两行结构：上游 v1.7.16 自带 `.credit-stack`（`.credit-main`+`.credit-meta`），
    **旧补丁 3c 已作废**（见补丁 3）。
  - 概况卡布局：上游 v1.7.16 重设计（大数字=可用积分、KeyBadge 入上方控制栏），
    **旧补丁 3d 已作废**（见补丁 3）。
  - `/v1/messages` 的开关：上游 v1.7.9 起**设置页可开关**（`enable_anthropic_messages` 落盘），
    判定逻辑是「面板设置 || `WB_ENABLE_ANTHROPIC_MESSAGES` 环境变量」，两者任一为真即启用；
    本仓库仍保留 start.sh 的环境变量默认开启（补丁 4）。
  - `/v1/messages` 的 `input_tokens` 双计：上游的处理是**默认关闭**该入口（`afab635`），
    并未改口径。我们选择**开启并保留补丁 2**（见补丁 4）。
- **上游 v1.7.8 曾有的缺陷 `_dispatch_chat_post` 缩进错误**：v1.7.9 `08c274d` 已修。
  每次升级仍建议按补丁 1 的判定命令自检一次，若复现则按同样方式归位。
- 若上游某版**自己修了** `_anthropic_usage` 的缓存口径 → 跳过补丁 2，并回退补丁 5 的期望值。
- 若上游某版**自己修了**二级导航间隙（`narrow ? 0 : 14` 那种判断）→ 跳过补丁 3a。
- 若上游把 `_dispatch_chat_post` / `_anthropic_usage` / `pageNavHeaderOffset` **改名或搬走** →
  rebase 会冲突；按新位置套用同样逻辑。

## 三、从上游升级的标准流程

本仓库 = 「上游 + 一个 `ops:` 提交」，所以升级最干净的做法是 **rebase**（把 `ops:` 提交重放到上游新版之上）。

```bash
cd /workspace/workbuddy2api-hub

# 0) 备份运行数据（补丁不含数据，稳妥起见）
BK="/tmp/opencode/wb-backup-$(date +%Y%m%d_%H%M%S)"; mkdir -p "$BK"
cp -a accounts usage "$BK/" 2>/dev/null
git bundle create "$BK/pre-upgrade.bundle" --all >/dev/null; echo "备份 -> $BK"

# 1) 拉上游新版本
git fetch upstream --tags
git log --oneline -1 upstream/main

# 2) 把本地 ops 提交重放到上游新版之上
git rebase upstream/main
#   - 若提示冲突：按第二节 1–4 手动解决（冲突通常就在补丁涉及的那几行），
#     然后 `git add <文件> && git rebase --continue`
#   - 想放弃重来：`git rebase --abort`

# 3) 逐项确认补丁仍在（对照第二节的「判定」命令）
grep -c "account_slot_acquire" wb_proxy.py                  # 上游自带（原补丁 5），应 >= 7
grep -c "affinity_stable_key_enabled" wb_proxy.py wb_settings.py   # 上游自带（原补丁 6），应 >= 11 / 4
grep -c "One response must carry one id" wb_proxy.py        # 上游自带（原补丁 6.5 / PR #607）
grep -c "transparent_wait_reason" wb_proxy.py               # 补丁 7，应 2
grep -c "body_wait" wb_proxy.py                             # 补丁 9，应 >= 2
grep -c "_maybe_flush" wb_accounts.py                       # 补丁 9，应 >= 3
grep -c "chat head" wb_proxy.py                             # 补丁 10，应 2
grep -c "def plan_slot_assignment" wb_proxy.py              # 补丁 11，应 1
grep -c "handshake_ms" wb_proxy.py                          # 补丁 11，应 >= 3（实测 13）
grep -c 'width:78px">权重' dashboard.html                    # 权重列修复，应 1
grep -c "cs-panel{position:fixed" dashboard.html             # 补丁（面板脱离祖先裁剪），应 1
grep -c "function placePanel" dashboard.html                 # 同上，应 1
grep -c "narrow ? 0 : 14" dashboard.html                    # 补丁 3a，应 2 处
grep -c "tb-group tb-checkin" dashboard.html                # 3i，上游 v1.7.29 起自带，应 1
grep -n "WB_ENABLE_ANTHROPIC_MESSAGES" start.sh             # 补丁 4
grep -c "def _slot_active" wb_proxy.py                       # 补丁 12，应 1
grep -c "hand the concurrency seat back first" wb_proxy.py  # 补丁 14，应 1
grep -c "Same leak as the 400 branch above" wb_proxy.py     # 补丁 14，应 1
grep -c "def alias_model_entries" wb_proxy.py                # 补丁 13，应 1
grep -c "def client_facing_model" wb_proxy.py                # 补丁 13，应 1
grep -c "def set_model_aliases" wb_settings.py               # 补丁 13，应 1
grep -c "function saveModelMapFromCell" dashboard.html       # 补丁 13，应 1
grep -c "function externalNamesFor" dashboard.html           # 补丁 13，应 1
grep -c "saveModelAliases" dashboard.html                    # 旧设置页入口已删，应 0
grep -c "modelMapTargets" dashboard.html                     # datalist 已删，应 0

# 4) 依赖：本仓库纯标准库、无 requirements.txt；若上游新增依赖则 pip 装（本机走清华源）

# 5) 跑测试（见第五节；本机基线为「除下述既有失败外全过」）
python3 tests/run_all.py --jobs 2 --timeout 300
python3 tests/_test_account_concurrency.py     # 上游自带（原补丁 5），24 例
python3 tests/_test_affinity_stable_key.py     # 上游自带（原补丁 6），14 例
python3 tests/_test_stream_single_id.py        # 补丁 6.5，15 断言
python3 tests/_test_transparent_retry.py       # 补丁 7
python3 tests/_test_proxy_gate_autoassign.py   # 补丁 11 + 12
python3 tests/_test_model_alias_and_realm.py   # 补丁 13

# 6) 重启服务并验证（见第五节）
./stop.sh && sleep 3 && ./start.sh

# 7) 把升级后的产物同步回本仓库（rebase 改写了历史，用 --force-with-lease）
git add -A && git commit --amend --no-edit      # 保持「单一 ops 提交」
git push --force-with-lease origin main
git tag -f -a ops-$(date +%Y%m%d) -m "ops baseline $(date +%F)" && git push --force origin --tags
```

**备选方案**（不想改写历史时）：

```bash
# 方案 B：merge（产生合并提交，可普通 push，不必 force）
git merge upstream/main
# 方案 C：cherry-pick 当前 ops 提交到新的上游基线
git checkout -b upgrade upstream/main
git cherry-pick ops-20261022b
git checkout main && git merge upgrade
```

> **关键点**：无论哪种方式，**升级后产物必须推回 origin**，这样本仓库始终是
> 「可直接部署」的完整状态，以后从本仓库 `git clone` 即可用。

## 四、部署（从本仓库直接下载使用）

```bash
git clone https://github.com/qq928820655/workbuddy2api-hub.git
cd workbuddy2api-hub

# 首次：设置面板密码（写入 accounts/settings.json，PBKDF2 存储；脚本不硬编码密码）
WB_PANEL_PASSWORD='<你的面板密码>' ./start.sh
# 之后重启可省略密码：
./start.sh

# 停止
./stop.sh
```

环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `WB_PORT` | `8788` | 监听端口 |
| `WB_PANEL_PASSWORD` | 无 | 面板密码，**仅首次设置时需要** |
| `WB_TZ` | `Asia/Shanghai` | 时区；调度器按此排程（本机系统时区是 UTC，必须设对） |
| `WB_ENABLE_ANTHROPIC_MESSAGES` | `1` | 是否启用 `/v1/messages`。上游 v1.7.8 起**默认关闭**，本脚本默认开启 |

运行数据目录（均被 `.gitignore` 排除，不随仓库分发）：
- `accounts/` —— 账号凭证（`*.json`）+ `settings.json`（面板密码/API key 哈希）
- `usage/` —— 用量流水 `usage.jsonl`

访问：`/`（看板）、`/health`、`/v1/models`、`/v1/chat/completions`、`/v1/responses`、
原生 Anthropic `/v1/messages`（需 `WB_ENABLE_ANTHROPIC_MESSAGES=1`）、`/panel/login`。

> **API Key 说明**：`/v1/*` 只认**面板里配置的 key**（设置页可复制）。`accounts/settings.json`
> 里的 `launcher_key`（`wb-...`）**仅在该面板还没有任何 key 时**才作为兜底，一旦面板配了 key
> 就被忽略——别拿它当日常 key 用。

## 五、升级后验证清单

1. `curl -s 127.0.0.1:8788/health` → `{"ok":true,...,"accounts":N,"accounts_ready":N}`
2. 带**面板 Key** 打 `/v1/models` → 200；不带 Key → 401
3. **`/v1/chat/completions` 与 `/v1/responses` 各打一次 → 200 且有 body**（补丁 1；空响应=补丁丢失）
4. `/v1/messages` 真实请求 200，且 `usage.input_tokens` 不含缓存双计
   （`input_tokens + cache_read + cache_creation` == 上游 `prompt_tokens`）
5. `gpt-*` 传 `max_tokens=1` → 200（上游 clamp 生效）
6. 看板移动端（≤640px）：标题/GitHub/语言/主题同一行、页签整行；账号卡积分格为上游
   `.credit-stack` 两行结构（数值行 + 明细徽章行）；概况卡为上游新版（大数字=可用积分、
   KeyBadge 在上方控制栏）；`--page-nav-top` 等于 header 高度（无 14px 缝隙）；宽屏仍为 +14
7. 进程环境：`tr '\0' '\n' < /proc/<pid>/environ | grep -E 'TZ|WB_ENABLE_ANTHROPIC_MESSAGES'`
   → `TZ=Asia/Shanghai`、`WB_ENABLE_ANTHROPIC_MESSAGES=1`
8. **流式单 id**：`python3 /tmp/opencode/finalproof.py 8788` → `1 distinct ids` 且 `finish=stop`
   （补丁 6.5；出现 2 个 id 说明补丁丢失，客户端会卡「生成中」）
9. **账号级并发上限**：面板设 1 → 6 路并发应落到 6 个不同账号；设 0 → 仍落 1 个账号
10. **更稳的会话粘滞键**：两个同开场白会话，开关关 → 同账号；开 → 两个账号
11. `/` 响应头 `Server: wb-proxy/1.9.2`

**测试基线**：`tests/run_all.py` 在本机 v1.9.2 基线为 **234 通过 / 3 失败**（共 237 套件），
与本地改造无关：
- `_test_anthropic_http.py`（38）/ `_test_anthropic_messages.py`（58）：必须 **全过**（本地补丁相关）
- 上游自带（勿重打）：`_test_account_concurrency.py`（24）、`_test_affinity_stable_key.py`（14）、
  `_test_stream_single_id.py`（15 断言）
- 本地补丁自建套件必须全过：`_test_transparent_retry.py`（补丁 7）、
  `_test_affinity_persistence.py`（补丁 9）、`_test_proxy_gate_autoassign.py`（补丁 11）
- 已知既有失败（**纯净 upstream v1.9.2 同样 3 挂**，与本地改造无关）：
  `_test_breaker_fairness.py`、`_test_egress_backoff.py`、`_test_pool_backoff.py`。
  三者都是上游 v1.7.18「模型级 5xx 不再计入账号熔断」改行为后测试未同步。

## 六、排查提示

- **时区**：本机系统时区是 UTC。若日志时间戳是 UTC 或调度器在错误的钟点跑，
  检查 `WB_TZ=Asia/Shanghai` 是否生效（`tr '\0' '\n' < /proc/<pid>/environ | grep TZ`）。
- **`/v1/chat/completions`、`/v1/responses` 空响应/连接被断（经预览代理表现为 530）**：
  补丁 1 丢失——`_dispatch_chat_post` 又被嵌进 `_release_key_slot` 了，按补丁 1 归位。
- **`/v1/messages` 返回 400 `invalid_request_error`（提示 `WB_ENABLE_ANTHROPIC_MESSAGES`）**：
  上游 v1.7.8 起默认关闭该入口；确认 `start.sh` 里 `WB_ENABLE_ANTHROPIC_MESSAGES=1` 且已重启。
- **缓存口径**：若 Anthropic 客户端上下文用量显示偏大（约 2 倍），多半是补丁 1 没生效。
- **`gpt-*` 400 `integer_below_min_value`**：`max_tokens` 低于 16；上游已自带 clamp，
  若复现说明上游又移除了，按 `git log upstream/main -p -- wb_proxy.py | grep max_tokens` 找。
- **API key 401**：确认用的是面板设置页里的 key，而不是 `launcher_key`（`wb-...`，见第四节说明）。
- **本机是浅克隆**：若 `git push` 报 `did not receive expected object`，先 `git fetch --unshallow upstream`。
- **gh token 缺 `workflow` scope**：仓库历史含 `.github/workflows/*.yml`，push 会被拒；
  用 `gh auth refresh -h github.com -s workflow` 补授权。

### 补丁 9（2026-10-23）：会话绑定落盘 + body 上传耗时日志

- **`SessionAffinity` 落盘**（`wb_accounts.py`）：`state_path` 默认由 `AccountPool` 传 `accounts/affinity.json`，
  请求路径最多每 10s 写一次、进程退出再写一次；启动时恢复未过期绑定（`history` 上限照旧、坏文件当空）。
  文件已加入 `NON_ACCOUNT_FILES`，不会被当成账号解析。目的：重启后长会话不再整段重算前缀
  （180k 上下文冷启动 10–15s，缓存命中从 99.9% 掉到 15%）。
- **`body_wait` 日志**（`wb_proxy.py`）：`handle_one_request` 记 `_arrived_at`，`_read_payload` 记读完 body
  的耗时，`chat:` 行在 ≥1s 时追加 ` body_wait=Nms`。此前这行只在 body 读完后才写，客户端上传慢
  与上游慢无法区分，日志里表现为"请求几分钟后才出现"甚至不出现。
- 判定：`grep -c "_maybe_flush" wb_accounts.py`>=3（v1.9.2 实测 5）；`grep -c "body_wait" wb_proxy.py`>=2（实测 4）；
  `python3 tests/_test_affinity_persistence.py` 10 例全过；重启后 `accounts/affinity.json` 条目数 >0。

### 补丁 10（2026-10-23）：请求到达即记日志（`chat head`）

`chat:` 行只在 body 读完后才写，所以客户端上传慢时那段窗口在日志里完全空白。
`do_POST` 现在对模型路由（chat/completions/responses/messages）在**读 body 之前**写一行
`chat head: <path> content_length=<n> key=<k>`。配合 `body_wait` 可区分三种情况：

- 有 `chat head`、`body_wait` 很大 → 请求到了，客户端/网络上传慢；
- 有 `chat head`、很快出现 `chat:` → 网关正常；
- **整段窗口没有 `chat head`** → 请求根本没到本进程。

实测（1MB body，客户端慢速发 10.1s）：直连 8788 记 `body_wait=9499ms`；
经公网预览域名（Cloudflare）只记 `body_wait=1051ms`——**CF 会把 body 收完再转给我们**，
所以经 CDN 的上传时间在网关日志里不可见。判定：`grep -c "chat head" wb_proxy.py`=2。

### 补丁 11（2026-10-24）：代理出口延迟门禁 + 每 N 个账号自动分配

- **握手延迟口径**（`wb_proxy.py`）：新增 `probe_proxy_route()`，用
  `http.client.HTTPSConnection` + `set_tunnel()` 一次连接里量两段——`handshake_ms`
  （TCP→CONNECT→到目标 TLS 握手完成）与 `latency_ms`（再取回 api.ipify.org 的响应）。
  `probe_proxy_intel()` 增加 `handshake_ms / healthy / gate_ok / gate /
  rtt_limit_ms / latency_limit_ms`；`probe_proxy_exit()` 保持原签名（内部转调）。
  `proxy_gate()` 判定：握手 ≤ `WB_PROXY_RTT_LIMIT_MS`（默认 300）为主，握不了手
  （SOCKS）时才用整请求 ≤ `WB_PROXY_LATENCY_LIMIT_MS`（默认 800）。
- **自动分配**（`wb_settings.py` + `wb_proxy.py` + `dashboard.html`）：
  `proxy_auto_assign_per_slot`（0=关，默认关）；`plan_slot_assignment()` 按 uid 排序、
  每 N 个账号一个已启用槽、槽位用尽后循环（不会把余数全压到最后一个槽）。
  `assign_proxy_slots()` 可先探测、只用通过门禁的出口；`maybe_auto_assign_slots()`
  在保存槽位 / 导入账号 / 启停账号 / 批量启停 / 删除账号 / 启动时触发。新接口
  `POST /panel/api/proxy/slots/autoassign {per_slot, probe, remember, only_unbound}`
  （409 = 没有可用出口）。设置页「账号代理槽」新增「每槽账号数」+「自动分配」，
  自动发现列表显示「握手 / 全程」并且超限出口不可勾选。
- **启停即重排（2026-10-24 二次补充）**：绑定只属于启用账号——`assign_proxy_slots()`
  开头先释放所有停用账号占着的槽位（报告 `released` 计数、日志
  `released N disabled account(s)`），其余启用账号随即按 N/槽 重新均分；账号重新启用后
  下一次分配自动纳入。自动模式关着时不做任何释放，手动绑定不受启停影响。
- 判定：`grep -c "def plan_slot_assignment" wb_proxy.py`=1、
  `grep -c "handshake_ms" wb_proxy.py`≥3、
  `grep -c "released %d disabled account" wb_proxy.py`=1、
  `python3 tests/_test_proxy_gate_autoassign.py`
  86 例全过。升级后 `accounts/settings.json` 里没有该键 = 关闭，行为不变。

### 补丁 12（2026-11-02）：任务型账号也保留代理出口

- **问题**：绑定只属于「启用」账号，而 `enabled=false, tasksEnabled=true` 的号仍会
  自己发请求（签到 / 成长 / 旅行 / 每日活跃打卡）——它的出口被释放后，这些请求全从
  本机 IP 出去，多号同 IP 就是关联特征。
- **改法**（`wb_proxy.py`）：新增 `_slot_active(account)` = `enabled or task_active()`；
  `assign_proxy_slots()` / `proxy_slots_view()` / `plan_slot_assignment()` 的候选全改用它；
  `POST /accounts/set` 的 `tasksEnabled` 分支也触发 `maybe_auto_assign_slots()`（与
  `enabled` 一致，开关任务即重平衡）；释放日志由 "disabled" 改为 "inactive"。
- **语义**：两个开关都关 = 释放出口；只开任务 = 保留出口。
- 判定：`grep -c "def _slot_active" wb_proxy.py`=1、
  `python3 tests/_test_proxy_gate_autoassign.py`（+6 例：task-only 保留 / 全停释放 /
  切任务重平衡）。

### 补丁 13（2026-11-02）：面板「对外名称」列（对外名 → 上游原名）

- **为什么要客户端可见**：别名是**客户端要发的名字**，不是内部别名。所以三件事必须
  一起做，否则会出现「能调用但客户端清单里没有」「回显 model 与请求不符」：
  1. `/v1/models` 宣告别名（`alias_model_entries()`，仅当目标在清单里）；
  2. key 的模型白名单同时接受别名与真名（`_key_model_error` 靠 `self._client_model`）；
  3. 回复里回显**客户端发的名字**（模块级 `client_facing_model(handler, model)`，
     流式 chunk 与非流式 body 都改）。
- **存储**（`wb_settings.py`）：`set_model_aliases()` / `model_aliases()`，
  `MAX_MODEL_ALIASES=200`（超长报错而不是静默截断）；`settings/save` 接受
  `model_aliases`，`runtime_settings_view` 暴露它。
- **面板**（`dashboard.html`，2026-11-03 改版）：入口是「网关模型清单」表末列
  **「对外名称」**——每行一个**纯 `<input>`**（无 datalist：对外名称本来就可以是
  清单里没有的名字，塞候选只会诱导用户误选成「另一个真实模型」），`change`
  （失焦/回车）时 `saveModelMapFromCell()` 整表覆盖写
  `/settings/save {model_aliases}`。**设置页那张 textarea 卡已删除**
  （`saveModelAliases()` 一并移除），避免两个入口写同一份配置。表头 9 列，
  `SORT_COL_KINDS.modelsTable` 末列 `null`（输入框不排序），空态 `colspan="9"`。
- **列语义（2026-11-03 反转，务必按这个理解）**：列里填的是**对外名称**
  （客户端发的名字），网关收到后按**本行模型 ID** 实际调用。存表方向因此是
  `对外名称 → 模型 ID`（`model_aliases[name] = id`）。行内输入框显示的是
  **指向本行模型的那些对外名称**——`externalNamesFor(id)` 反查别名表；一个模型
  有多个对外名称时第一个填进框、其余进 `title`（「也对外提供：…」）。保存时
  `saveModelMapFromCell()` 先删旧名再写新名，名字等于模型 ID 时直接不写
  （清洗器也会丢）。
- **注意**：`client_facing_model` 必须是**模块级函数**，不能写成 Handler 方法——
  `tests/_test_sse_termination.py` 用 stub handler 驱动 `_chat_stream_response`，
  方法版会 AttributeError。
- 判定：`grep -c "def alias_model_entries" wb_proxy.py`=1、
  `grep -c "def client_facing_model" wb_proxy.py`=1、
  `grep -c "def set_model_aliases" wb_settings.py`=1、
  `grep -c "function saveModelMapFromCell" dashboard.html`=1、
  `grep -c "function externalNamesFor" dashboard.html`=1、
  `grep -c "saveModelAliases" dashboard.html`=0（旧入口已删）、
  `grep -c "modelMapTargets" dashboard.html`=0（datalist 已删）、
  `grep -c 'data-label="对外名称"' dashboard.html`=3（2 条 CSS + 1 个单元格）、
  `python3 tests/_test_model_alias_and_realm.py`（26 例）、
  `node tests/_test_models_catalog_source.js`（含对外名称列 7 条断言）。

### 补丁 14（2026-11-03）：400 / 未处理 4xx 透传前归还账号并发名额

- **症状**：某个账号（线上是 `b98b079c`）突然「消失」——`/health` 里仍 `ready`、面板测试也绿，
  但每个请求都跳过它；池子只剩一个号时直接报 503，报错只列「其余号已停用」，极具误导。
  重启进程立刻恢复，过一阵又复发。
- **根因**：`open_upstream()` 的重试循环里，`if exc.code == 400: raise`（原 wb_proxy.py:16449）
  与末尾未单独处理的 4xx 兜底 `raise`（原 16495）都**直接跳出循环**，跳过了循环之后的统一
  `account_slot_release(slot_held)`。账号在 `_ACCOUNT_INFLIGHT` 里永久 +1。
  `account_max_concurrent=1` 时一个漏掉的名额就是致命的：`pick_account()` 每次都把它当满号跳过。
  上游 v1.10.8 同样有这处泄漏（并发上限是上游 v1.8.0 收编的能力，400 分支原样保留）。
- **修法**：两处 `raise` 之前先 `account_slot_release(slot_held)` 并把 `slot_held` 置空。
  只归还名额，**不改 400 的透传语义**——400 是请求级错误，换号也会撞同一堵墙，
  不应该罚号或轮转。
- **排查口诀**：面板「号是好的，但请求总是 503/502 且报错只列别的号」→ 先查
  `GET /settings` 的 `account_inflight`：非空、且对应账号根本没有在飞请求 = 名额泄漏。
  重启进程可临时清零，根治靠本补丁。
- 判定：`grep -c "hand the concurrency seat back first" wb_proxy.py`=1、
  `grep -c "Same leak as the 400 branch above" wb_proxy.py`=1、
  `python3 tests/_test_account_concurrency.py`（26 例，含 2 例泄漏回归）。
