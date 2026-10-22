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
DIR=$(cd "$(dirname "$0")" && pwd)
cd "$DIR"
PORT="${WB_PORT:-8788}"
TZ="${WB_TZ:-Asia/Shanghai}"
WB_ENABLE_ANTHROPIC_MESSAGES="${WB_ENABLE_ANTHROPIC_MESSAGES:-1}"
WB_MAX_CONCURRENT_CHAT="${WB_MAX_CONCURRENT_CHAT:-96}"
WB_CHAT_SLOT_WAIT="${WB_CHAT_SLOT_WAIT:-60}"
WB_TRANSPARENT_RETRY_WAIT="${WB_TRANSPARENT_RETRY_WAIT:-30}"
export TZ WB_ENABLE_ANTHROPIC_MESSAGES WB_MAX_CONCURRENT_CHAT WB_CHAT_SLOT_WAIT
export WB_TRANSPARENT_RETRY_WAIT

PANEL_ARGS=()
if [ -n "${WB_PANEL_PASSWORD:-}" ]; then
  PANEL_ARGS=(--panel-password "${WB_PANEL_PASSWORD}")
fi

ss -tlnp 2>/dev/null | grep -q ":${PORT} " && { echo "端口 ${PORT} 已被占用"; exit 1; }
setsid nohup python3 wb_proxy.py --host 0.0.0.0 --port "${PORT}" --lan "${PANEL_ARGS[@]}" > server.log 2>&1 &
echo "workbuddy2api-hub 已启动, pid=$!, port=${PORT}"
