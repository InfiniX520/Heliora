# 现代软件工程与 AI 算法通用编程规范 (Universal Coding Guidelines)

**版本**: v1.0
**核心原则**: 可读性第一、高内聚低耦合、绝对的可复现性、防御性编程。

本规范融合了《Clean Code》、Google 开源规范、PEP 8 标准以及顶级 AI 实验室的工程最佳实践，适用于算法研究、后端开发及通用软件工程。

---

## 1. 命名与语义规范 (Naming & Semantics)
> **权威背书**: *《Clean Code》指出：“代码阅读的时间与编写的时间比例超过 10:1。让代码读起来像散文。”*

### 1.1 命名约定
*   **变量与函数**：必须使用**全英文**，Python/C++ 采用 `snake_case`（下划线命名），禁止使用拼音或无意义缩写（如 `a`, `b`, `tmp1`）。
*   **类名**：采用 `PascalCase`（大驼峰命名），必须是名词（如 `EquilibriumRefiner`, `DeepCrackDataset`）。
*   **常量**：采用全大写字母加下划线 `UPPER_SNAKE_CASE`（如 `MAX_ITERATIONS`, `DEFAULT_LR`）。
*   **布尔值**：以 `is_`, `has_`, `can_`, `should_` 开头（如 `is_training`, `has_global_token`）。

### 1.2 消除“魔法数字” (Magic Numbers)
代码中严禁出现未解释的孤立数字或字符串。所有特殊值必须提取为常量或配置项。
```python
# ❌ 反面教材
if image.shape[1] == 384: ...

# ✅ 最佳实践
IMAGE_HEIGHT = 384
if image.shape[1] == IMAGE_HEIGHT: ...
```

---

## 2. 架构与项目结构 (Architecture & Structure)
> **权威背书**: *Google 项目规范要求：“代码的物理结构必须反映其逻辑结构，严禁跨模块的隐藏依赖。”*

### 2.1 路径管理：绝对禁止硬编码
*   **根目录对齐**：永远不要使用绝对路径（如 `D:\data`）或脆弱的相对路径（如 `../../data`）。
*   **工程化寻址**：通过动态获取项目根目录（`ROOT`）来构建所有路径。
*   **导入策略约束**：业务代码中避免通过 `sys.path.append(...)` 注入路径；优先使用包结构与 `python -m package.module` 启动方式。
```python
# ✅ 最佳实践
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data" / "DeepCrack"
```

### 2.2 读写分离与输出隔离
*   **只读区**：原始数据（`data/`）、预训练权重（`mit-b0/`）在程序运行时必须是**绝对只读**的。
*   **产出区**：所有的运行日志、权重保存、预测结果必须按时间戳或实验名称隔离，存入独立目录（如 `runs/<exp_name>/<timestamp>/`）。
*   **防覆盖机制**：系统应自动检测目录冲突并添加后缀（如 `_v2`），严禁静默覆盖历史实验数据。

---

## 3. 代码风格与类型安全 (Style & Type Safety)
> **权威背书**: *PEP 484 &《The Pragmatic Programmer》：“明确的接口契约是构建大型系统的基石。”*

### 3.1 强制类型提示 (Type Hinting)
Python 代码必须为函数的参数和返回值添加类型提示，这不仅是给 IDE 看的，更是最好的接口文档。
```python
# ❌ 反面教材
def make_run_dir(exp, run_name, overwrite): ...

# ✅ 最佳实践
from pathlib import Path

def make_run_dir(exp: str, run_name: str, overwrite: bool = False) -> Path: ...
```

### 3.2 模块化与单一职责 (Single Responsibility)
*   **函数长度**：单个函数最好不要超过一个屏幕（约 40-50 行）。如果超过，说明它做了太多事情，应拆分为子函数。
*   **单一缩进层级**：尽量使用“提前返回 (Early Return)”来减少 `if-else` 的嵌套层级。

---

## 4. 日志、异常与防御性编程 (Logging & Robustness)
> **权威背书**: *分布式系统开发守则：“Fail Fast (快速失败)”。系统应当在检测到错误的第一时间崩溃，而不是带着错误状态继续运行。*

### 4.1 结构化与语义化日志
*   **弃用 Print**：在生产和长周期训练中，禁止使用 `print()`，必须使用标准 `logging` 模块或持久化工具（如将 `dict` 写入 `.jsonl`）。
*   **控制台语义前缀**（本项目优良传统）：
    *   `[+]` 代表成功、初始化完成、加载成功。
    *   `[-]` 代表警告、降级运行或非致命错误。
    *   `[!]` 代表重要提示或强干预操作。
    *   `[阶段]` 明确当前系统处于何种状态（如 `[验证]`, `[训练]`）。

### 4.2 环境与数据自检 (Sanity Checks)
在程序核心逻辑启动前，必须有自检函数，确保环境就绪（防御性编程）：
```python
# ✅ 最佳实践
assert data_dir.exists(), f"[-] 数据集目录未找到: {data_dir}"
assert torch.cuda.is_available(), "[-] 必须使用 GPU 运行此代码！"
```

---

## 5. AI 与算法专用规范 (AI/ML Specifics)
> **权威背书**: *FAIR (Meta AI) 与 OpenAI 的可复现性（Reproducibility）标准。*

### 5.1 绝对的可复现性
*   **种子固定**：所有涉及随机性的模块（PyTorch, NumPy, Random, CUDA 内部算子）必须在脚本开头统一固定 Seed。
*   **配置即代码**：所有的超参数（Epoch, LR, α, T等）必须全部落盘保存为 `config.json`。**只要有 config.json，就必须能 100% 跑出完全一样的权重**。

### 5.2 硬件与平台无关性
*   **跨平台兼容**：Windows 系统下 `num_workers` 通常需设为 0。多进程代码必须包含在 `if __name__ == '__main__':` 保护块中。
*   **设备映射**：禁止写死 `.cuda()`，必须使用动态设备分配：
```python
# ✅ 最佳实践
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)
images = images.to(device, non_blocking=True)
```

### 5.3 现代 API 迭代
*   紧跟框架官方的最佳实践更新。例如，废弃旧版的 `torch.cuda.amp`，强制迁移到 PyTorch 2.0+ 推荐的 `torch.amp`。

---

## 6. 文档与注释 (Documentation & Comments)
> **权威背书**: *《Clean Code》：“注释不是用来解释代码做了什么（What），那是代码本身的职责；注释是用来解释代码为什么这么做（Why）的。”*

### 6.1 注释原则
*   **What (做什么)**：通过良好的命名让代码自解释。
*   **Why (为什么)**：用注释解释业务逻辑、引用的论文公式、或者为何采用这种不寻常的写法（如规避某个框架的 Bug）。

### 6.2 Docstring 标准头 (Google Style)
核心类和复杂函数必须包含标准的多行注释，说明 Args (参数) 和 Returns (返回值)。算法类注释应附带数学公式（使用 LaTeX 语法）。

```python
class EquilibriumRefiner(nn.Module):
    """
    基于平衡态原理的特征精炼模块。
    
    核心公式:
        $z_{t+1} = \mathrm{LN}((1-\alpha) \cdot z_t + \alpha \cdot (x + \Delta_t))$
        
    Args:
        dim (int): 输入特征维度。
        num_iters (int, optional): 迭代次数 T，默认 3。
        alpha (float, optional): 阻尼系数，控制更新步长，默认 0.1。
    """
    def __init__(self, dim: int, num_iters: int = 3, alpha: float = 0.1):
        super().__init__()
        # ...
```

---
**规范结语**：
优秀的工程代码就像一台精密运转的仪器，**“一致性”**是它最美的特征。无论是第一天加入的实习生，还是项目架构师，写出的代码风格都应当高度统一。严格遵守上述规范，将极大降低 Debug 成本，提升研究与开发的效率。