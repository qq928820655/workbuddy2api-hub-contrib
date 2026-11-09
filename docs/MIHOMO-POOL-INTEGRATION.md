# hub × mihomo-pool 结合方式（部署必读）

> 这份文档回答一个问题：**为什么同一份 hub，在有的服务器上「账号代理槽」能看到 mihomo 节点下拉、能显示每个槽位当前的节点名（图二），在另一些服务器上只有一行地址框、名称要手填（图一）？**
>
> 答案不在代码里，在**启动方式**里。hub 本身不内置 mihomo，它通过一组环境变量去「问」外部的 mihomo-pool 面板。这些变量只有在上层编排脚本（`apps/stack.sh` / `apps/supervise.sh`）里注入；单独跑 hub 自己的 `start.sh` 时它们为空，于是退化成图一。

---

## 1. 两张图对应什么

| 现象 | 触发条件 | 说明 |
|---|---|---|
| **图一**（只有「名称 + 代理地址」两列，名称手填，无节点下拉） | `WB_PROXY_NODE_MAP_URL` **为空** | hub 没连 mihomo-pool，槽位只知道自己的别名，不知道端口背后是哪个节点。这是**默认行为**，旧版一致。 |
| **图二**（「代理地址」上方多一个端口下拉，选项形如 `17902 · pro-家庭宽带-马来西亚-5x`；「出口」列显示真实节点名 + 国家/类型标签；出现「旧节点快照」提示） | `WB_PROXY_NODE_MAP_URL` 指向 mihomo-pool（如 `http://127.0.0.1:8006`）且 `WB_PROXY_NODE_MAP_TOKEN` 与 mihomo 的 `MPOOL_TOKEN` 一致 | hub 每次渲染槽位表时向 mihomo 拉「端口→节点名」映射，端口下拉与出口列都用这份数据。 |

**结论**：要图二，就让 hub 进程带上 `WB_PROXY_NODE_MAP_URL` 和 `WB_PROXY_NODE_MAP_TOKEN` 这两个环境变量。代码不需要改。

---

## 2. 数据流（谁问谁）

```
┌──────────────────────────┐        ① 渲染槽位表时           ┌──────────────────────────┐
│  hub 前端 dashboard.html │ ──────────────────────────────▶ │  hub 后端 wb_proxy.py     │
│  （设置页「账号代理槽」） │   GET /proxy/slots               │                          │
│                          │   GET /proxy/ports               │  proxy_slots_view()      │
│                          │ ◀────────────────────────────── │  proxy_port_options()    │
└──────────────────────────┘   返回 {ports:[{port,node}],     └───────────┬──────────────┘
                                  slots:[{...,node}]}                     │
                                                                          │ ② 带 Bearer token
                                                                          │   GET /api/v1/hub-exits
                                                                          │   缓存 15s（NODE_MAP_TTL）
                                                                          ▼
                                                              ┌──────────────────────────┐
                                                              │ mihomo-pool server.py     │
                                                              │ 8006                      │
                                                              │  hub_exits()              │
                                                              │  共享口 7890/7891/7892 →   │
                                                              │    组当前选中的节点        │
                                                              │  专属口 17901+ →           │
                                                              │    该口绑定的节点（固定）  │
                                                              └───────────┬──────────────┘
                                                                          │ ③ controller API
                                                                          │   127.0.0.1:9090
                                                                          ▼
                                                              ┌──────────────────────────┐
                                                              │ mihomo 内核               │
                                                              │ 监听 7890/7891/7892       │
                                                              │      17901…17932          │
                                                              └──────────────────────────┘
```

- **①** hub 前端不直接访问 mihomo。它只打 hub 后端的 `/proxy/slots` 和 `/proxy/ports`（都在 `wb_proxy.py`，需要面板密码登录）。
- **②** hub 后端按 `WB_PROXY_NODE_MAP_URL` 拼出 `.../api/v1/hub-exits`，带 `Authorization: Bearer <WB_PROXY_NODE_MAP_TOKEN>` 去拉映射。结果缓存 `WB_PROXY_NODE_MAP_TTL`（默认 15 秒）。拉取失败 → 退回空映射 → 前端只显示槽位别名，绝不显示过期节点名。
- **③** mihomo-pool 自己去问 mihomo 内核 controller（`MPOOL_CONTROLLER`，默认 `127.0.0.1:9090`），把每个监听端口当前对应的节点名报给 hub。

### 关键端口一览（默认值，均在 mihomo-pool/.env 与 hub 环境变量里可覆盖）

| 端口 | 归属 | 用途 |
|---|---|---|
| `8006` | mihomo-pool 面板 | hub 拉 `/api/v1/hub-exits` 的目标（`WB_PROXY_NODE_MAP_URL`） |
| `9090` | mihomo 内核 controller | mihomo-pool 用它查节点/切换（`MPOOL_CONTROLLER`） |
| `7890` | mihomo 共享出口 | HUB-FIXED：固定节点 |
| `7891` | mihomo 共享出口 | HUB-ROTATE：定时随机轮换 |
| `7892` | mihomo 共享出口 | HUB-ASSIGN：API 粘性分配 |
| `17901`–`17932` | mihomo 专属口 | 每节点一个，硬绑定，永远同一节点（`MPOOL_LISTEN_BASE`=17901，`MPOOL_LISTEN_MAX`=32） |

---

## 3. 用到的环境变量

### 3.1 hub 侧（`wb_proxy.py`）

| 变量 | 默认 | 作用 |
|---|---|---|
| `WB_PROXY_NODE_MAP_URL` | 空 | **开关**。填 mihomo-pool 面板地址（`http://127.0.0.1:8006`）才启用节点名映射；留空 = 图一。 |
| `WB_PROXY_NODE_MAP_TOKEN` | 空 | 调 `/api/v1/hub-exits` 的 Bearer token，必须等于 mihomo 的 `MPOOL_TOKEN`。 |
| `WB_PROXY_NODE_MAP_TTL` | `15` | 节点名缓存秒数。 |
| `WB_PROXY_DISCOVER_HOST` | `cli-proxy-mihomo` | 「自动发现 mihomo 端口」按钮探测的主机。本机部署应为 `127.0.0.1`。 |
| `WB_PROXY_DISCOVER_PORTS` | `17901-17910` | 自动发现探测的端口范围，支持逗号分段，如 `7890-7892,17901-17932`（共享口 + 全部专属口）。 |
| `WB_PROXY_RTT_LIMIT_MS` | `300` | 出口延迟门禁：握手耗时上限。机场跨洋握手 300–600ms 起，本机放宽到 `1000`。 |
| `WB_PROXY_LATENCY_LIMIT_MS` | `800` | 整请求耗时兜底上限（SOCKS 无法计握手时用）。本机放宽到 `2000`。 |

> `WB_PROXY_NODE_MAP_URL` 为空时，`proxy_node_map()` 直接返回 `{}`，`proxy_port_options()` 返回空列表，前端 `SLOT_PORTS` 为空 → `slotUrlCellHtml()` 只画地址输入框。这就是图一。

### 3.2 mihomo-pool 侧（`mihomo-pool/.env`）

| 变量 | 本机值 | 作用 |
|---|---|---|
| `MPOOL_PORT` | `8006` | 面板监听端口 |
| `MPOOL_TOKEN` | （私有） | 面板 API 令牌，hub 的 `WB_PROXY_NODE_MAP_TOKEN` 要填同一个 |
| `MPOOL_CONTROLLER` | `127.0.0.1:9090` | mihomo 内核 controller 地址 |
| `MPOOL_LISTEN_BASE` | `17901` | 专属口起点 |
| `MPOOL_LISTEN_MAX` | `32` | 专属口数量 → 17901–17932 |
| `MPOOL_HUB_PORTS` | `7890,7891,7892` | 共享出口端口 |

---

## 4. 部署方式：怎样才能稳定复现图二

### 4.1 推荐：用上层编排脚本（已内置注入）

`apps/stack.sh` 的 `start_hub()` 与 `apps/supervise.sh` 已经把这组变量连同 token 一起注入，token 从 `mihomo-pool/.env` 的 `MPOOL_TOKEN` 现场读取，不用手工填：

```bash
# apps/stack.sh 片段（节选）
WB_PROXY_DISCOVER_HOST=127.0.0.1 \
WB_PROXY_DISCOVER_PORTS=7890-7892,17901-17932 \
WB_PROXY_RTT_LIMIT_MS=1000 \
WB_PROXY_LATENCY_LIMIT_MS=2000 \
WB_PROXY_NODE_MAP_URL=http://127.0.0.1:8006 \
WB_PROXY_NODE_MAP_TOKEN="$(grep '^MPOOL_TOKEN=' "$MIHOMO/.env" 2>/dev/null | cut -d= -f2-)" \
WB_PORT=8788 \
  setsid nohup python3 -m wb_proxy --host 0.0.0.0 --port 8788 --lan
```

所以：**新服务器部署整套栈时，走 `apps/stack.sh up` 或 `apps/supervise.sh`，不要单独跑 hub 的 `start.sh`。** 单独跑 `hub/start.sh` 时它只设了 `WB_PROXY_DISCOVER_*` 和延迟门禁，**没有设 `WB_PROXY_NODE_MAP_URL`/`TOKEN`**，于是呈现图一。

### 4.2 只用 hub 自己的 `start.sh` 时

如果部署拓扑里没有 `apps/` 这层编排、必须单独起 hub，就在启动前把两个变量导出来：

```bash
cd /path/to/workbuddy2api-hub
export WB_PROXY_NODE_MAP_URL=http://127.0.0.1:8006
export WB_PROXY_NODE_MAP_TOKEN="$(grep '^MPOOL_TOKEN=' /path/to/mihomo-pool/.env | cut -d= -f2-)"
./start.sh
```

或者写进 hub 进程的 systemd unit / 容器 `environment:` / shell profile。只要 hub 进程的环境里有这两个变量，重启后就是图二。

### 4.3 自检：确认当前 hub 是否已接上

```bash
# 1) 看 hub 进程环境里有没有 NODE_MAP
PID=$(ss -ltnp 2>/dev/null | grep ':8788' | grep -oP 'pid=\K[0-9]+' | head -1)
tr '\0' '\n' < /proc/$PID/environ | grep WB_PROXY_NODE_MAP

# 2) 直接问 mihomo 要映射（应返回 exits 数组，含 shared + node 两类）
curl -s -H "Authorization: Bearer <MPOOL_TOKEN>" http://127.0.0.1:8006/api/v1/hub-exits | python3 -m json.tool

# 3) 登录面板后看 /proxy/ports 是否有数据（有数据 = 下拉会出现）
#    未登录会返回 401 {"message":"panel password required"}，属正常
```

三项都通过 → 面板就是图二。

---

## 5. 常见故障对照

| 现象 | 根因 | 处理 |
|---|---|---|
| 槽位只有地址框，无节点下拉（图一） | hub 环境缺 `WB_PROXY_NODE_MAP_URL` | 按 4.1 / 4.2 注入后重启 hub |
| 下拉出现但「出口」列只有别名、没有节点名 | `WB_PROXY_NODE_MAP_TOKEN` 与 `MPOOL_TOKEN` 不一致 → 401 → 退回空映射 | 用同一份 token；token 从 mihomo `.env` 现场读，别手抄 |
| 节点名短暂显示后又变回别名 | mihomo-pool 8006 不可达，`proxy_node_map()` 拉取失败并按 TTL 缓存了空映射 | 先 `curl 8006/health`；恢复后最多等 `WB_PROXY_NODE_MAP_TTL` 秒 |
| 共享口（7890-7892）节点名会变、专属口（17901+）不变 | 设计如此：共享口是组当前选中，专属口硬绑定 | 要固定出口就用专属口；要轮换用 7891 |
| 「出口」列出现「旧节点快照」橙字 | 槽位存的探测快照（ip/国家）与当前实际节点不一致（端口轮换过） | 点「测试」重新探测即刷新快照 |
| 自动发现按钮探测很慢或报全超门禁 | `WB_PROXY_DISCOVER_HOST` 填了主机名而非本机；或门禁阈值太低 | 本机部署设 `WB_PROXY_DISCOVER_HOST=127.0.0.1`；跨洋握手放宽 `WB_PROXY_RTT_LIMIT_MS` |
| 名称列为空、保存后不显示 | 未接 mihomo 时槽位名称需手填；接了 mihomo 时名称留空会按「国家 类型」自动命名 | 图二模式下名称可留空，出口探测后自动补 |

---

## 6. 代码位置索引

| 功能 | 位置 |
|---|---|
| 环境变量定义 | `wb_proxy.py:7173`（`PROXY_DISCOVER_HOST`）、`:7177`（`PROXY_NODE_MAP_URL/TOKEN`）、`:7180`（TTL）、`:7187`（延迟门禁） |
| 端口范围解析 | `wb_proxy.py:7195` `_proxy_port_range()` |
| 自动发现（并行探测） | `wb_proxy.py:7371` `discover_proxy_slots()` |
| 拉 mihomo 端口→节点映射 | `wb_proxy.py:7428` `proxy_node_map()`（15s 缓存，失败退空） |
| 槽位当前节点名 | `wb_proxy.py:7479` `slot_node_name()` |
| 端口下拉数据源 | `wb_proxy.py:7488` `proxy_port_options()` → `GET /proxy/ports`（`:21275`） |
| 槽位视图（含 node / exit_stale） | `wb_proxy.py:7500` `proxy_slots_view()` → `GET /proxy/slots`（`:21269`） |
| 前端端口下拉渲染 | `dashboard.html:18131` `slotUrlCellHtml()`（`SLOT_PORTS` 为空则只画地址框） |
| 前端槽位显示名 | `dashboard.html` `slotDisplayName()`（node → label → name → id） |
| mihomo 侧映射接口 | `mihomo-pool/server.py:383` `/api/v1/hub-exits` → `mihomo_mgr.py:1613` `hub_exits()` |
| mihomo 侧鉴权 | `mihomo-pool/server.py:273` `_authed()`（Bearer / X-Token / query token） |

---

## 7. 一句话总结

> **图一 = hub 没连 mihomo-pool（`WB_PROXY_NODE_MAP_URL` 为空）；图二 = 连上了。** 连上的方式是在启动 hub 时注入 `WB_PROXY_NODE_MAP_URL` + `WB_PROXY_NODE_MAP_TOKEN`（= mihomo 的 `MPOOL_TOKEN`）。上层 `apps/stack.sh` / `apps/supervise.sh` 已经这么做了；单独用 `hub/start.sh` 部署时要自己补这两个变量，否则每次新服务器都会回到图一。
