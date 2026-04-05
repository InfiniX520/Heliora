# 无 Git 仓库与无 gh 客户端：上传与触发 CI 操作卡

适用场景：
1. 本地目录还不是 git 仓库。
2. 本机未安装 gh 客户端。
3. 需要通过 GitHub 网页触发 PR CI，并回填执行单证据。

---

## 1. 本地初始化仓库（PowerShell）

1. 进入项目根目录：
   - cd E:\Zero9\Heliora
2. 初始化仓库：
   - git init
3. 检查状态：
   - git status
4. 首次提交：
   - git add .
   - git commit -m "chore: initialize heliora workspace and release evidence"

说明：若提示 user.name/user.email 未配置，先执行：
1. git config --global user.name "你的名字"
2. git config --global user.email "你的邮箱"

---

## 2. 在 GitHub 创建远程仓库并推送

1. 在 GitHub 网页新建仓库（例如 Heliora）。
2. 复制远程 URL（HTTPS）。
3. 绑定并推送：
   - git remote add origin <你的仓库URL>
   - git branch -M master
   - git push -u origin master

说明：
1. HTTPS 推送可能要求 Token，按 GitHub 网页指引使用 PAT。
2. 若远程默认分支是 `main`，将上述命令中的 `master` 替换为 `main`。
3. 若远程已存在同名仓库且有初始提交，先拉取再推：
   - git pull --rebase origin master
   - git push -u origin master

---

## 3. 创建 PR 分支并提交本轮改动

1. 新建分支：
   - git checkout -b feature/release-window-gate
2. 提交改动：
   - git add .
   - git commit -m "feat: add release preflight automation and ci ann audit"
3. 推送分支：
   - git push -u origin feature/release-window-gate
4. 在 GitHub 网页点击 Compare & pull request 创建 PR。

如果出现“base 与 compare 无差异，无法创建 PR”：
1. 在功能分支创建空提交：
   - git commit --allow-empty -m "chore: trigger backend rabbitmq gate"
2. 再次推送：
   - git push
3. 返回 GitHub 页面重新创建 PR。

---

## 4. 在网页触发并获取 CI 证据

1. 触发方式 A（推荐）：PR 页面 -> Checks。
2. 触发方式 B（无 PR 时可用）：直接 push 到 `master/main/develop`，然后在 Actions 页面查看 `Backend RabbitMQ Gate`。
3. 等待或点击 Re-run all jobs，确保工作流 Backend RabbitMQ Gate 完整执行。
4. 在 run 页面确认 Summary 包含：
   - ann audit (blocking)
5. 复制两类链接：
   - CI 运行链接（run 页面 URL）
   - Artifact 链接（backend-rabbitmq-gate-reports 页面 URL）

---

## 5. 回填执行单并做 Go/No-Go

将链接回填到：
1. 项目设计/05-实施与交付/05-发布窗口切流执行单.md 的 8.1 项。

判定规则：
1. CI 链接齐全 + artifact 可访问 + VM 预检报告 PASS -> 可进入 Go 评审。
2. 任一核心项缺失或失败 -> No-Go，不切流，保持 sqlite。

---

## 6. 常见报错快速处理

1. 在根目录执行找不到脚本：
   - 报错示例：can't open file 'E:\\Zero9\\Heliora\\scripts\\validate_env_consistency.py'
   - 处理：先进入后端目录再执行。
   - 正确示例（在 `heliora_backend` 目录）：
     - python scripts/validate_env_consistency.py --env-file .env
   - 正确示例（在 `heliora_backend/scripts` 目录）：
     - python validate_env_consistency.py --env-file ../.env
    - 兼容说明（2026-04-05 已增强脚本）：
       - 在 `heliora_backend/scripts` 目录执行 `python validate_env_consistency.py --env-file .env` 也会自动回退到 `heliora_backend/.env`
2. Git Bash 的 python 指向 Microsoft Store：
   - 处理：用绝对路径执行
   - /e/Miniconda03/envs/Heliora/python.exe scripts/validate_env_consistency.py --env-file .env
3. Git Bash 无 conda 命令：
   - 处理：不依赖 conda activate，直接使用解释器绝对路径。

---

## 7. FAQ：本地化部署为什么仍要测云端 CI？

1. 本地化部署关注“系统运行在哪里”；云端 CI 关注“改动是否被统一验证并可追溯”。
2. 云端 CI 不会改变部署位置，只负责标准化门禁（lint/type/test/coverage/integration）与证据归档（run + artifact）。
3. 如果只有本地通过、没有云端 run/artifact 证据，发布评审很难做跨人复核，风险不可见。
4. 结论：本地部署与云端测试并不冲突，发布窗口需要两者同时成立。

---

## 8. 2026-04-05 实操复盘（可复用模板）

### 8.1 本地四项检查执行记录

| 命令 | 目的 | 结果 |
| --- | --- | --- |
| `bash scripts/preflight_release_window_vm.sh` | 一键预检 | PASS |
| `bash scripts/run_task_persistence_pg_matrix_vm.sh` | VM 矩阵回归 | PASS |
| `bash scripts/rehearse_task_persistence_cutover_rollback_vm.sh` | 切换 + 回滚演练 | PASS |
| `python scripts/validate_env_consistency.py --env-file .env` | 环境一致性校验 | PASS |

阶段结论：VM 侧前置条件已满足；若需要发布签字，仍需补齐云端 CI run 与 artifact 证据。

### 8.2 Git 配置与推送问题处理

问题 1：`git commit` 报错 `Author identity unknown`。

处理命令：
1. `git config --global user.name "InfiniX520"`
2. `git config --global user.email "172117778+InfiniX520@users.noreply.github.com"`

问题 2：首次推送被 GitHub 拒绝（GH007 隐私邮箱策略）。

根因：提交作者邮箱为主机默认邮箱（`Administrator@DESKTOP-...`），不符合 GitHub 隐私策略。

处理命令：
1. `git config --global user.email "172117778+InfiniX520@users.noreply.github.com"`
2. `git commit --amend --reset-author --no-edit`
3. `git push -u origin master --force`

结果：推送成功，仓库地址为 `https://github.com/InfiniX520/Heliora`。

### 8.3 PR 无差异与 CI 触发判定

现象：`base: master` 与 `compare: master` 无差异，PR 页面无法形成有效对比。

说明：这不代表 CI 不会触发。当前 workflow 已监听 `master` push，直接推送到 `master` 也会触发 `Backend RabbitMQ Gate`。

关键前提：该 workflow 配置了 `paths` 过滤，仅当改动命中 `heliora_backend/**` 或 `.github/workflows/backend-rabbitmq-gate.yml` 时才会在 push 时触发。

因此，若本次只改了 `项目设计/**` 文档，push 成功也可能不会产生新的 `Backend RabbitMQ Gate` run，这是预期行为。

确认方式：
1. 打开 Actions 页面，核对最新 run（如 `23993195493`）状态与结论。
2. 若需要立即复测门禁：
   - 在已有 run 页面点击 `Re-run all jobs`；或
   - 提交一个命中路径过滤的最小改动（`heliora_backend/**` 或 workflow 文件）后再 push。

### 8.4 文档回填位置

1. 发布执行单：`项目设计/05-实施与交付/05-发布窗口切流执行单.md`（8.1）
2. 证据总索引：`项目设计/05-实施与交付/07-发布证据索引与检索指南.md`

### 8.5 观察窗口与最终签字

1. 观察窗口建议不少于 15 分钟，期间持续检查：
   - `/health` 返回 `OK`
   - worker 进程持续存活
   - API/worker 日志关键错误签名命中为 0
2. 推荐检查命令（宿主机执行）：
   - `ssh Heliora-VM "cd /home/heliora/heliora_backend; echo 'api_error_hits='$(grep -Ei 'task state/event persistence failed|traceback|\[error\]|connection timeout|psycopg\.errors' .api.log | wc -l); echo 'worker_error_hits='$(grep -Ei 'task state/event persistence failed|traceback|\[error\]|connection timeout|psycopg\.errors' .worker.log | wc -l); tail -n 20 .api.log; echo '---'; tail -n 20 .worker.log"`
3. 观察窗口通过后：
   - 生成观察窗口报告到 `heliora_backend/.release-reports/`
   - 在执行单 8.1 更新结论为“观察窗口通过并签字归档”
   - 在证据索引文档补充观察窗口证据条目

### 8.6 第二发布窗口启动模板（可直接复用）

1. 先做低风险启动预检（不扰动运行态）：
   - `cd E:\Zero9\Heliora\heliora_backend`
   - `bash scripts/preflight_release_window_vm.sh --skip-sql-review --skip-matrix --skip-rehearsal`
2. 预检通过后，立即记录两项证据：
   - 新报告路径（`heliora_backend/.release-reports/release_preflight_*.md`）
   - 当前 backend gate 快照（最近 5 次 run 的 `id/status/conclusion`）
3. 进入第二窗口正式复核前，执行全量预检：
   - `bash scripts/preflight_release_window_vm.sh`
4. 正式复核完成后，统一回填以下文档：
   - `05-发布窗口切流执行单.md`
   - `03-当前进度与下一步.md`
   - `02-测试计划.md`
   - `07-发布证据索引与检索指南.md`
5. 当第二窗口稳定性确认完成（满足“2 个窗口稳定”）后，执行 ANN 审计升级：
   - 将 CI 中 ANN 审计从 non-blocking 调整为 blocking
   - 关键校验：workflow 不再包含 `continue-on-error`，Summary 显示 `ann audit (blocking)`
   - 同步更新执行单、测试计划与证据索引口径

### 8.7 ANN 阻塞门禁升级实跑记录（样例）

1. workflow 变更：`.github/workflows/backend-rabbitmq-gate.yml`
2. 云端复验 run：`https://github.com/InfiniX520/Heliora/actions/runs/23994866186`
3. artifact：`https://github.com/InfiniX520/Heliora/actions/runs/23994866186/artifacts/6275299443`
4. 关键步骤：`Run ANN audit (blocking)` = success
