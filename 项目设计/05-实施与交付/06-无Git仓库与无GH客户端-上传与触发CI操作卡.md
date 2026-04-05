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
   - git branch -M main
   - git push -u origin main

说明：
1. HTTPS 推送可能要求 Token，按 GitHub 网页指引使用 PAT。
2. 若远程已存在同名仓库且有初始提交，先拉取再推：
   - git pull --rebase origin main
   - git push -u origin main

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
   - ann audit (non-blocking)
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
2. Git Bash 的 python 指向 Microsoft Store：
   - 处理：用绝对路径执行
   - /e/Miniconda03/envs/Heliora/python.exe scripts/validate_env_consistency.py --env-file .env
3. Git Bash 无 conda 命令：
   - 处理：不依赖 conda activate，直接使用解释器绝对路径。
