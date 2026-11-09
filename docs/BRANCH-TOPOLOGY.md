# 分支拓扑与多机安全更新（改历史前必读）

> 这份文档存在的唯一目的：**在改写 git 历史（rebase / force-push）之前，先讲清楚每个分支是什么、哪些机器跟哪个分支、以及别的机器该怎么更新才不会出问题。**
>
> 如果你在一台**新服务器**上部署、或者准备对**任何已有部署**做 `git pull`，先读完第 2、3 节。

---

## 1. 分支拓扑（截至 2026-11-09）

```
upstream/main  (ardeyouxipianyi/workbuddy2api-hub)   f8736b3  release: v2.0.6
        │
        │  fork
        ▼
origin/main    (qq928820655/workbuddy2api-hub)        0a0dc25  perf(deploy): 启动入口改用 python3 -m wb_proxy
        │                                                    ▲
        │                                                    │ 这是「干净可部署」基线：
        │                                                    │ 上游 v1.10.11 + 本机 ops 改造，
        │                                                    │ 但【不含】mihomo 节点映射 / 别名开关等新功能
        │
        │  10 个提交（mihomo 槽位系列 + 4 项 dashboard 修复）
        ▼
261106-feat-proxy-slot-node-name                     b8af4a3  docs(proxy): hub×mihomo-pool 结合方式
        │                                                    ▲
        │                                                    │ 这是【当前实际部署运行】的分支：
        │                                                    │ = origin/main + 10 个新功能提交
        │
        └── 261106-feat-proxy-slot-node-name.backup    b8af4a3  （rebase 前的回退点，与上面同 commit）
```

### 关键事实（务必记住）

| 事实 | 影响 |
|---|---|
| **`origin/HEAD -> origin/main`**，即 `git clone` 默认拿的是 `main` | 新服务器若不指定分支，拿到的**没有** mihomo 节点下拉/别名开关等 10 个功能 → 面板显示「图一」 |
| mihomo 功能（`WB_PROXY_NODE_MAP_URL`、`proxy_node_map`、`/proxy/ports`、槽位节点名）**只在 `261106-feat-proxy-slot-node-name`** | `origin/main` 上 `grep WB_PROXY_NODE_MAP_URL wb_proxy.py` 结果为 **0** |
| 4 项 dashboard 修复（别名开关/吸顶/账号卡完整/切视图重置）同样**只在 feature 分支** | `origin/main` 上无 `model_aliases_enabled` |
| feature 分支 = `main` + **10 个提交** | 见第 4 节清单 |

> 一句话：**`main` 是「保守基线」，`261106-feat-proxy-slot-node-name` 是「带新功能的部署分支」。两者内容不同，不要混用。**

---

## 2. 其他服务器怎么更新才不出问题

### 2.1 先确认这台机器跟的是哪个分支

```bash
cd /path/to/workbuddy2api-hub
git rev-parse --abbrev-ref HEAD          # 当前分支
git rev-parse --abbrev-ref @{u}          # 跟踪的远端分支
git log -1 --oneline                     # 当前 commit
```

- 若显示 `main` / `origin/main` → 这台机器**没有** mihomo 新功能，是保守基线。
- 若显示 `261106-feat-proxy-slot-node-name` → 这台机器**有** mihomo 新功能。

### 2.2 常规更新（历史没被改写时）

```bash
git fetch origin
git status                                # 确认无本地未提交改动
git pull --ff-only                        # 只允许快进，避免意外合并
```

> **用 `--ff-only`**：如果远端历史被改写过（rebase / force-push），`--ff-only` 会直接报错而不是悄悄制造一个乱七八糟的 merge。看到报错就跳到 2.3。

### 2.3 远端历史被改写后（rebase / force-push 之后）

本仓库对 feature 分支做 rebase 后会用 `--force-with-lease` 推送，**历史被改写**。已部署的机器不能再 `git pull`（会分叉）。两种安全做法，**二选一**：

**做法 A：放弃本地历史，直接对齐远端（推荐，部署机通常无本地提交）**

```bash
# 1) 备份运行数据（accounts/ usage/ 被 gitignore，不会被覆盖，但稳妥起见）
BK="/tmp/wb-backup-$(date +%Y%m%d_%H%M%S)"; mkdir -p "$BK"
cp -a accounts usage "$BK/" 2>/dev/null

# 2) 确认工作区干净（有本地改动先 stash 或提交）
git status

# 3) 硬对齐远端分支（会丢弃本地提交历史，但工作区文件变成远端最新）
git fetch origin
git reset --hard origin/261106-feat-proxy-slot-node-name

# 4) 重启
./stop.sh && sleep 3 && ./start.sh
```

**做法 B：保留本地改动，用 stash 迁移**

```bash
git stash push -u -m "pre-rebase-local-changes"
git fetch origin
git reset --hard origin/261106-feat-proxy-slot-node-name
git stash pop          # 冲突则手动解
./stop.sh && sleep 3 && ./start.sh
```

> ⚠️ **绝对不要**在部署机直接 `git pull`（不带 `--ff-only`）去合并一个被改写的历史——会产生重复提交和幽灵冲突。

### 2.4 想从保守基线切到新功能分支

```bash
cd /path/to/workbuddy2api-hub
git fetch origin
git checkout 261106-feat-proxy-slot-node-name   # 或 rebase 后的新分支名
git pull --ff-only
./stop.sh && sleep 3 && ./start.sh
```

切分支**不会**丢运行数据（`accounts/`、`usage/` 是 gitignore 的），但会切换 `dashboard.html` / `wb_proxy.py` 的版本。

---

## 3. 部署机切换分支的注意事项

> 与 UPGRADE.md「提 PR 不要切主工作区分支」同源：服务实时读取部署目录的 `dashboard.html`，`git checkout` 会**立即**改变线上面板。

1. **切分支前先停服**：`./stop.sh`，避免进程读到半新半旧的文件。
2. **切完再起**：`./start.sh`。
3. **不要在正在跑服务的目录里做 rebase**：rebase 过程中工作区会反复变动，线上会读到中间态。正确做法是在独立 worktree / 独立目录做 rebase，验证通过后再让部署机对齐（见 2.3）。

```bash
# 独立目录做 rebase 的正确姿势（不影响线上）
git worktree add /tmp/opencode/hub-rebase -b 261109-rebase-v2.0.6 261106-feat-proxy-slot-node-name
cd /tmp/opencode/hub-rebase
git rebase upstream/main
# 解冲突、跑测试都在这里；线上 8788 完全不受影响
```

---

## 4. feature 分支独有的 10 个提交（`origin/main` 没有）

```
b8af4a3 docs(proxy): 记录 hub×mihomo-pool 结合方式，start.sh 自动接上节点映射
1342269 feat(dashboard): 模型别名开关 + 区块标题吸顶 + 账号卡完整显示 + 切视图重置筛选
3b55a2d fix(dashboard): 手机端账号区三处布局修正（批量按钮/账号卡第二行/操作区空块）
0f82a2c fix(accounts): 网关重启后旧筛选不再把账号列表过滤成空
1be63d7 fix(proxy): 槽位名称显示实际节点名，出口信息标注旧节点快照
2933b5c feat(proxy): 槽位名称下方实时显示当前节点名
e49866f feat(proxy): 槽位编辑器可直接从下拉里选端口
c606914 fix(proxy): 槽位指向节点专属口时显示节点名
1ae414a feat(proxy): 自动发现覆盖每节点端口，探测改并行
f1a2475 feat(proxy): 出口下拉显示 mihomo 当前节点名
```

涉及文件：`wb_proxy.py`、`wb_settings.py`、`dashboard.html`、`start.sh`、`README.md`、`docs/MIHOMO-POOL-INTEGRATION.md` 及 7 个测试文件。

> 其中 `3b55a2d`（手机端布局）、`0f82a2c`（账号筛选）两个补丁**已被上游 v2.0.x 吸收**，rebase 到 v2.0.6 后可丢弃本地版本；其余（mihomo 槽位系列、别名开关、对外名称、吸顶/账号卡）上游没有，必须保留。详见 `docs/REBASE-V2.0.6.md`（若存在）。

---

## 5. 改历史前的固定检查清单

每次准备 rebase / force-push 前，逐条打勾：

- [ ] 已确认**哪些机器跟哪个分支**（2.1），特别是 `main` 和 feature 分支的部署机
- [ ] 已在独立 worktree 做 rebase，**没有**在运行中的部署目录操作（3.3）
- [ ] 已建**回退分支**（如 `261106-...backup`），记下回退 commit
- [ ] rebase 后测试全过 + 隔离端口（非 8788）冒烟通过
- [ ] 推送用 `--force-with-lease`（不是 `--force`），避免覆盖别人刚推的提交
- [ ] 已把「历史被改写」这件事通知其他机器的维护者，或确认它们用 2.3 的做法 A 对齐

---

## 6. 一句话总结

> `origin/main` 是**保守基线**（新服务器默认拿到，无 mihomo 功能 → 图一）；`261106-feat-proxy-slot-node-name` 是**带新功能的部署分支**（图二）。**改历史前**先确认每台机器跟哪个分支；**改历史后**，其他机器用 `git reset --hard origin/<分支>` 对齐（2.3 做法 A），**不要**裸 `git pull`。
