---
story: "SSH快速连接与操作速查"
updated: 2026-04-01
---

# Heliora SSH快速连接与操作速查

本文档用于以后快速连入 Ubuntu 虚拟机并开始开发，不再重复排障。

---

## 1. 当前可用连接参数

1. 主机: 127.0.0.1
2. 端口: 2026
3. 用户: heliora
4. 项目目录: /home/heliora/heliora_backend
5. 密码: heliora521

安全建议:
1. 本地虚拟机场景可记录密码，但建议仅保留在本地文档，不外发。
2. 使用 SSH 密钥后可免密连接，效率更高。

---

## 2. 最快连接方式

### 2.1 Git Bash 直连

执行:

ssh heliora@127.0.0.1 -p 2026

成功信号:
1. 看到提示符变成 heliora@heliora:~$。

### 2.2 VS Code Remote SSH 连接

前置设置:
1. 在 VS Code 设置中确认 Remote.SSH: Path 指向 Git 自带 ssh.exe。
2. 推荐值示例: E:/Git_A/Git/usr/bin/ssh.exe

连接步骤:
1. 打开命令面板。
2. 选择 Remote-SSH: Connect to Host。
3. 选择 heliora@127.0.0.1:2026。
4. 首次连接输入密码。

成功信号:
1. 左下角出现 SSH: 127.0.0.1。
2. 能打开远端目录 /home/heliora/heliora_backend。

---

## 3. 免密登录版（SSH key + Host 别名）

目标:
1. 以后输入一个短命令就连接: ssh heliora-vm
2. VS Code 里直接选主机别名，不再手敲 IP 和端口。

### 3.1 生成本机 SSH 密钥（Windows Git Bash）

执行:

ssh-keygen -t ed25519 -C "heliora-local-vm"

说明:
1. 连续回车可使用默认路径: ~/.ssh/id_ed25519
2. passphrase 可留空，也可设置。

### 3.2 把公钥写入虚拟机授权列表

执行:

cat ~/.ssh/id_ed25519.pub | ssh heliora@127.0.0.1 -p 2026 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

成功信号:
1. 再次连接时不再要求输入虚拟机密码。

### 3.3 配置 Host 别名

编辑 ~/.ssh/config，写入:

Host heliora-vm
   HostName 127.0.0.1
   Port 2026
   User heliora
   IdentityFile ~/.ssh/id_ed25519
   IdentitiesOnly yes
   ServerAliveInterval 30
   ServerAliveCountMax 3

测试:

ssh heliora-vm

成功信号:
1. 直接进入 heliora@heliora:~$，不再输入密码。

### 3.4 VS Code 直接使用别名

1. 打开命令面板。
2. 选择 Remote-SSH: Connect to Host。
3. 选择 heliora-vm。

---

## 4. 连接后第一组固定命令

执行:

cd /home/heliora/heliora_backend
source .venv/bin/activate
python -V

成功信号:
1. Python 显示 3.11.x 或 3.12.x。

---

## 5. 开发前固定检查

执行:

cd /home/heliora/heliora_backend
docker compose ps
source .venv/bin/activate
pytest

成功信号:
1. compose 服务状态正常。
2. pytest 通过。

---

## 6. 启动与验收（最小闭环）

重启后优先执行（推荐）:

cd /home/heliora/heliora_backend
chmod +x scripts/start_api_bg.sh scripts/stop_api.sh scripts/start_worker_bg.sh scripts/stop_worker.sh
bash scripts/start_api_bg.sh
curl http://127.0.0.1:8000/health

成功信号:
1. 输出包含 API started in background.
2. 输出包含 Worker started in background. 或 Worker already running.
2. /health 返回健康 JSON。

worker 单独控制（可选）:

cd /home/heliora/heliora_backend
bash scripts/start_worker_bg.sh
bash scripts/stop_worker.sh
tail -n 20 .worker.log

Day-3.3 RabbitMQ 联调验收（可选）:

cd /home/heliora/heliora_backend
# .env 中设置 TASK_QUEUE_BACKEND=rabbitmq
bash scripts/stop_api.sh
bash scripts/start_api_bg.sh
bash scripts/smoke_rabbitmq_retry.sh

通过判定:
1. 必须出现 `RabbitMQ retry smoke passed (dead_lettered observed with backend=rabbitmq).`。
2. 若出现 `backend=memory`，说明走了 fail-open 回退，需先排查 RabbitMQ 可用性再重测。

终端A启动服务:

cd /home/heliora/heliora_backend
source .venv/bin/activate
python main.py

终端B验证:

cd /home/heliora/heliora_backend
bash scripts/smoke_api.sh
curl http://127.0.0.1:8000/health

Windows浏览器验证:
1. 打开 http://127.0.0.1:8081/health

成功信号:
1. smoke_api.sh 输出 Smoke tests passed。
2. /health 返回包含 code、data、trace_id 的 JSON。

---

## 7. 本次过程记录（已验证）

1. SSH 已可稳定连接到 Ubuntu 虚拟机。
2. 后端目录与脚本完整可用。
3. pytest 已通过。
4. 后端服务可启动并通过健康检查。
5. 冒烟脚本已通过。
6. Windows 端口转发访问 /health 已通过。
7. 主机重启后 SSH 复连再次验证通过。
8. Day-3.2 实机复测通过：worker 可自动拉起且持续消费循环正常。

---

## 8. 常见问题速修

问题A: python: command not found
1. 原因: 未激活 .venv。
2. 修复:
   - python3 -m venv .venv
   - source .venv/bin/activate

问题B: pytest: command not found
1. 原因: 虚拟环境依赖未安装。
2. 修复:
   - pip install -r requirements.txt

问题C: 浏览器无法访问 8081
1. 先在虚拟机执行 curl http://127.0.0.1:8000/health。
2. 若虚拟机内可通，则检查 VirtualBox 端口转发 8081 -> 8000。

问题D: 免密后仍反复要密码
1. 原因: 常见是权限不对或未命中 IdentityFile。
2. 修复:
   - 在虚拟机检查权限: chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys
   - 本机强制指定密钥测试: ssh -i ~/.ssh/id_ed25519 heliora@127.0.0.1 -p 2026
   - 别名连接调试: ssh -v heliora-vm

问题E: mgt.clearMarks is not a function
1. 原因: 常见于扩展状态异常、版本冲突或工作区缓存损坏。
2. 修复顺序:
   - 执行命令: Developer: Reload Window
   - 仍异常则重启 VS Code
   - 更新相关扩展到最新版本
   - 禁用最近新装扩展后复测
   - 最后清理当前工作区缓存目录后重连

问题F: curl http://127.0.0.1:8000/health 连不上（你当前遇到的）
1. 原因: 虚拟机重启后，Python API 进程不会自动常驻。
2. 修复:
   - cd /home/heliora/heliora_backend
   - chmod +x scripts/start_api_bg.sh scripts/stop_api.sh
   - bash scripts/start_api_bg.sh
   - curl http://127.0.0.1:8000/health

问题G: `.env: line 1: $'Backend\r': command not found`
1. 原因: 旧版 worker 启动脚本使用 `source .env`，当 `.env` 为 CRLF 且存在带空格值（如 `APP_NAME=Heliora Backend`）会被 Bash 拆词。
2. 当前状态: 已修复。worker 现改为 Python 解析 `.env`，不再依赖 Bash `source`。
3. 若远端仍报这个错: 说明脚本未同步，请执行目录同步后重启：
   - `rsync -avz --delete --exclude ".venv" --exclude "__pycache__" --exclude ".pytest_cache" -e "ssh -p 2026" /e/Zero9/Heliora/heliora_backend/ heliora@127.0.0.1:/home/heliora/heliora_backend/`
   - `ssh heliora@127.0.0.1 -p 2026 "cd /home/heliora/heliora_backend && bash scripts/stop_worker.sh && bash scripts/start_api_bg.sh && bash scripts/check_services.sh"`

---

## 9. 推荐下一步（可选）

1. 按第 3 章完成密钥配置后，验证 ssh heliora-vm 可直接登录。
2. 在 SSH 配置里加 Host 别名，例如 heliora-vm，后续直接 ssh heliora-vm。
3. 把 Day-1 常用命令做成脚本，做到一键测试与一键启动。

---

## 10. 文件同步（SSH 断开后最常用）

场景:
1. 你在 Windows 改了文件，需要推到虚拟机。
2. 你在虚拟机调了文件，需要拉回 Windows。

### 10.1 同步单个文件（推荐）

Windows -> 虚拟机（在 Git Bash 执行）:

scp -P 2026 /e/Zero9/Heliora/heliora_backend/.env heliora@127.0.0.1:/home/heliora/heliora_backend/.env

虚拟机 -> Windows（在 Git Bash 执行）:

scp -P 2026 heliora@127.0.0.1:/home/heliora/heliora_backend/.env /e/Zero9/Heliora/heliora_backend/.env

### 10.2 同步整个后端目录（rsync，高效）

先在虚拟机安装 rsync:

sudo apt install -y rsync

Windows Git Bash 推送（排除缓存与虚拟环境）:

rsync -avz --delete --exclude ".venv" --exclude "__pycache__" --exclude ".pytest_cache" -e "ssh -p 2026" /e/Zero9/Heliora/heliora_backend/ heliora@127.0.0.1:/home/heliora/heliora_backend/

### 10.3 同步后快速生效

ssh heliora@127.0.0.1 -p 2026 "cd /home/heliora/heliora_backend && bash scripts/start_api_bg.sh && curl http://127.0.0.1:8000/health"
