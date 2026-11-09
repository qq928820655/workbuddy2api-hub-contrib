#!/bin/bash
# 启动 workbuddy2api-hub 网关（LAN 模式）。
#
# 面板密码不在脚本里硬编码：
#   - 首次运行请设置 WB_PANEL_PASSWORD（会写入 accounts/settings.json，PBKDF2 存储）；
#   - 之后重启可不再传，沿用已保存的密码。
#
# 环境变量：
#   WB_PORT            监听端口（默认 8788）
#   WB_PANEL_PASSWORD  面板密码（首次设置用；已设置过可省略）
#   WB_TZ              时区（默认 Asia/Shanghai，调度器按此排程）
#   WB_ENABLE_ANTHROPIC_MESSAGES
#                      是否启用 Anthropic Messages（/v1/messages）。上游 v1.7.8
#                      起因缓存兼容性未验证而**默认关闭**，本机一直对外提供该接口，
#                      故这里默认开启以保持行为不变；设为 0 可关闭。
#   WB_MAX_CONCURRENT_CHAT
#                      同时处理的对话请求上限（上游默认 32）。本机 24 个账号，
#                      32 个槽偏紧：槽满后请求排队 WB_CHAT_SLOT_WAIT 秒就 503。
#                      这里按「账号数 × 4」放大到 96。
#   WB_CHAT_SLOT_WAIT  槽满时最多排队多少秒（上游默认 30），这里放宽到 60。
#   WB_TRANSPARENT_RETRY_WAIT
#                      整池都在冷却时，最多原地等多少秒再回 429（默认 30）。
#                      下游（CPA / Claude Code / 各种 harness）拿到 429 只会中断
#                      这一轮、要人手动重发，而这些冷却窗口大多只有几十秒，等一会
#                      儿就能自己继续。设 0 恢复上游行为（立刻 429）。
#   WB_PROXY_DISCOVER_HOST / WB_PROXY_DISCOVER_PORTS
#                      账号代理槽的自动发现目标（mihomo-pool 的逐节点端口）。
#                      本机 8006 池子暴露 127.0.0.1:17901-17932。仅在面板/配置
#                      里启用 proxy_slots 后才会实际使用；未配置时行为与关闭一致。
#   WB_PROXY_NODE_MAP_URL / WB_PROXY_NODE_MAP_TOKEN
#                      接 mihomo-pool 面板，让槽位显示节点下拉与真实节点名。
#                      本脚本在未显式设置时，若 8006 在听会自动接上（token 从
#                      mihomo-pool/.env 的 MPOOL_TOKEN 读，可用 MPOOL_ENV 指定
#                      路径）。找不到则保持为空，行为与旧版一致（只有地址框）。
#                      详见 docs/MIHOMO-POOL-INTEGRATION.md。
DIR=$(cd "$(dirname "$0")" && pwd)
cd "$DIR"
PORT="${WB_PORT:-8788}"
TZ="${WB_TZ:-Asia/Shanghai}"
WB_ENABLE_ANTHROPIC_MESSAGES="${WB_ENABLE_ANTHROPIC_MESSAGES:-1}"
WB_MAX_CONCURRENT_CHAT="${WB_MAX_CONCURRENT_CHAT:-96}"
WB_CHAT_SLOT_WAIT="${WB_CHAT_SLOT_WAIT:-60}"
WB_TRANSPARENT_RETRY_WAIT="${WB_TRANSPARENT_RETRY_WAIT:-30}"
WB_PROXY_DISCOVER_HOST="${WB_PROXY_DISCOVER_HOST:-127.0.0.1}"
WB_PROXY_DISCOVER_PORTS="${WB_PROXY_DISCOVER_PORTS:-17901-17932}"
# 机场节点跨洋握手 300-600ms 起步，上游默认 300ms 会全拒；放宽到 1000ms。
WB_PROXY_RTT_LIMIT_MS="${WB_PROXY_RTT_LIMIT_MS:-1000}"
WB_PROXY_LATENCY_LIMIT_MS="${WB_PROXY_LATENCY_LIMIT_MS:-2000}"
export TZ WB_ENABLE_ANTHROPIC_MESSAGES WB_MAX_CONCURRENT_CHAT WB_CHAT_SLOT_WAIT
export WB_TRANSPARENT_RETRY_WAIT WB_PROXY_DISCOVER_HOST WB_PROXY_DISCOVER_PORTS
export WB_PROXY_RTT_LIMIT_MS WB_PROXY_LATENCY_LIMIT_MS

# 自动接上同机 mihomo-pool，让「账号代理槽」显示节点下拉与真实节点名（图二）。
# 未显式指定 WB_PROXY_NODE_MAP_URL 时，若 8006 在听，就从同目录的
# mihomo-pool/.env 读 MPOOL_TOKEN 一并注入。找不到面板或 token 时保持为空，
# hub 行为与旧版一致（只有地址框=图一）。显式设了就以显式值为准。
if [ -z "${WB_PROXY_NODE_MAP_URL:-}" ] && ss -tln 2>/dev/null | grep -q ":8006 "; then
  WB_PROXY_NODE_MAP_URL="http://127.0.0.1:8006"
  if [ -z "${WB_PROXY_NODE_MAP_TOKEN:-}" ]; then
    # token 从 mihomo 的 .env 现场读，按常见布局依次尝试，避免手抄出错。
    for _env in "${MPOOL_ENV:-}" ../mihomo-pool/.env ../mihomo/.env /opt/mihomo-pool/.env; do
      [ -n "$_env" ] && [ -r "$_env" ] || continue
      WB_PROXY_NODE_MAP_TOKEN="$(grep '^MPOOL_TOKEN=' "$_env" 2>/dev/null | head -1 | cut -d= -f2-)"
      [ -n "$WB_PROXY_NODE_MAP_TOKEN" ] && break
    done
  fi
  if [ -n "${WB_PROXY_NODE_MAP_TOKEN:-}" ]; then
    export WB_PROXY_NODE_MAP_URL WB_PROXY_NODE_MAP_TOKEN
    echo "[start] 已接上 mihomo-pool ${WB_PROXY_NODE_MAP_URL}（槽位将显示节点名）"
  else
    echo "[start] 8006 在听但未找到 MPOOL_TOKEN，跳过节点名映射（设 MPOOL_ENV 或 WB_PROXY_NODE_MAP_TOKEN）"
    WB_PROXY_NODE_MAP_URL=""
  fi
fi

PANEL_ARGS=()
if [ -n "${WB_PANEL_PASSWORD:-}" ]; then
  PANEL_ARGS=(--panel-password "${WB_PANEL_PASSWORD}")
fi

ss -tlnp 2>/dev/null | grep -q ":${PORT} " && { echo "端口 ${PORT} 已被占用"; exit 1; }
# 用 `-m wb_proxy` 而不是 `wb_proxy.py`：上游 #777 实测同一份代码常驻内存
# 少 47-54MB（本机 python3.11 实测 78MB -> 72MB）。`-m` 把当前目录放进
# sys.path，脚本里已经 cd 到仓库根，所以行为不变。
setsid nohup python3 -m wb_proxy --host 0.0.0.0 --port "${PORT}" --lan "${PANEL_ARGS[@]}" > server.log 2>&1 &
echo "workbuddy2api-hub 已启动, pid=$!, port=${PORT}"
