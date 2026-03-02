# C2C + HighFold 合并方案（HighFold_C2C）

> **最终决策**：保持 overlay 安装模式（先装 LocalColabFold，再覆盖 HighFold 源码）；  
> Pipeline 通过 `subprocess` 调用 `colabfold_batch` CLI 完成结构预测阶段；  
> 单一 conda 环境同时包含 PyTorch（C2C）和 JAX（HighFold）依赖。

## 1. 合并动机

| 现状问题 | 合并后改善 |
|----------|-----------|
| 两个独立仓库，安装步骤繁琐（先装 LocalColabFold → 覆盖 HighFold → 再配 C2C 环境） | 一个仓库，统一环境 |
| 通过文件 I/O 松耦合（FASTA + JSON），出错难排查 | 统一 pipeline，自动传参，统一日志和错误处理 |
| 两套独立环境（PyTorch vs JAX），用户需来回切换 | 单一 conda 环境 |
| 三个脚本（`1-predict-cyclic.py` → `2-run-highfold.sh` → `3-final.py`）需手动顺序执行 | 一条命令完成全流程 |

## 2. 合并后项目结构

```
HighFold_C2C/                      # 合并后的项目根目录
├── README.md                      # 统一文档
├── LICENSE                        # [复制自 HighFold]
├── pyproject.toml                 # 项目元数据
├── environment.yml                # 合并后的 conda 环境（PyTorch + JAX）
├── .gitignore
│
├── alphafold/                     # [复制自 HighFold] AlphaFold 核心 + CycPOEM 修改
│   ├── common/
│   ├── data/
│   ├── model/
│   │   ├── modules.py             # 含 offset_ss 替换 relpos 的修改 (L1937)
│   │   └── modules_multimer.py    # 含 multimer CycPOEM 注入 (L518-519)
│   ├── notebooks/
│   └── relax/
│
├── colabfold/                     # [复制自 HighFold] ColabFold 修改版
│   ├── batch.py                   # 含 CycPOEM 计算函数 + --disulfide-bond-pairs CLI 参数
│   ├── ...
│   └── alphafold/
│
├── utils/                         # [复制自 HighFold] CycPOEM、二硫键组合等工具
│   ├── cycpoem.py                 # Floyd-Warshall 最短路径 CycPOEM（独立版本）
│   ├── disulfide_bridge_combination.py  # 生成所有合法二硫键配对组合
│   ├── eval.py                    # PDB 评估：RMSD、DockQ 计算
│   └── fnat/                      # C 级别 fnat/DockQ 实现
│
├── c2c/                           # [新增] 从 C2C_release 重构的 Python 模块
│   ├── __init__.py
│   ├── config.py                  # 默认配置常量
│   ├── model.py                   # T5 模型定义 + CharTokenizer + 加载（从 1-predict-cyclic.py 提取）
│   ├── generate.py                # 序列生成逻辑：sample_c2c_dual + write_fasta（从 1-predict-cyclic.py 提取）
│   └── evaluate.py                # 理化性质计算 + pLDDT 评分收集 + CSV 报告（从 3-final.py 提取）
│
├── scripts/                       # [新增] 用户入口脚本
│   ├── run_pipeline.py            # 统一 pipeline（替代 1→2→3 三步手动执行）
│   └── run_predict_only.py        # 仅运行结构预测（兼容原 HighFold 用法）
│
├── checkpoints/                   # [新增] 模型权重存放目录
│   └── .gitkeep                   # c2c_model.pt 由用户下载放入
│
└── HighFold_data/                 # [复制自 HighFold] 数据集
    ├── monomer_native/
    ├── mul_baseline_native/
    └── mul_ex_native/
```

## 3. 源代码分析

### 3.1 C2C_release 代码分析

#### `1-predict-cyclic.py`

**核心组件**：
| 类/函数 | 说明 |
|---------|------|
| `LETTER_SET` | 20 种标准氨基酸字母集合 |
| `CharTokenizer` | 字符级 tokenizer：vocab = 4 个特殊 token + 排序后的 AA/数字/标点/字母 |
| `make_input_text(core, L)` | 构造 T5 输入 prompt：`<CORE_HEAD> ... </CORE_HEAD> <CORE_TAIL> ... </CORE_TAIL> <LEN> L </LEN>` |
| `BlockEosUntilLetters` | LogitsProcessor：阻止 EOS 直到生成 `span_len` 个 AA 字母，达到后强制 EOS |
| `StopAtLetters` | StoppingCriteria：所有 batch 生成足够 AA 后停止 |
| `load_c2c_model(checkpoint_path, device)` | 构建 T5 (d_model=256, 4层, 4头)，加载权重，< 200MB 显存 |
| `sample_c2c_dual(core, n_greedy, n_sampled, ...)` | 主生成函数：greedy + sampling 两种模式，输出 `core + span` 组装后的完整序列 |

**数据流**：`core` → T5 生成 span → `core + span` → 写入 `./output/predict.fasta`

**已知问题（重构时修复）**：
- `import re` 未使用 → 移除
- 全局变量 `checkpoint` 声明但未使用（调用处硬编码 `'./c2c_model.pt'`）→ 统一为参数
- `file_out` 未关闭 → 改用 `with` 语句
- 无 argparse → 新模块通过函数参数接收

#### `3-final.py`

**核心组件**：
| 函数 | 说明 |
|------|------|
| `hopp_woods` dict | Hopp-Woods 亲水性标度（20 种 AA → float） |
| `calculate_hydrophilicity(seq)` | 计算序列平均亲水性 |
| `cyclic_sequence(fasta_path)` | 读取 FASTA 提取序列列表 |
| `info(seq)` | BioPython ProteinAnalysis：计算 MW/pI/芳香性/不稳定性/GRAVY/亲水性/二级结构 |
| `score(seq_list)` | glob 匹配 `./output/pep{N}_scores_rank_00*_alphafold2_model_*_seed_000.json`，取 pLDDT 均值 |

**数据流**：`predict.fasta` + `pep*_scores_*.json` → PhysChem 属性 + pLDDT 均值 → `output.csv`

**已知问题（重构时修复）**：
- `import os` 未使用 → 移除
- `sec`（二级结构分数）计算但丢弃 → 保留为可选输出列
- `score()` 中 glob 路径硬编码 `./output/` → 改为接受 `output_dir` 参数
- 文件未用 `with` 管理

#### `2-run-highfold.sh`
```bash
colabfold_batch --model-type alphafold2 --msa-mode single_sequence ./output/predict.fasta ./output/
```
仅一行命令，调用 `colabfold_batch` CLI。pipeline 中改为 `subprocess.run()` 调用。

### 3.2 HighFold 代码分析

HighFold 是基于 ColabFold/AlphaFold2 的覆盖式修改，核心创新是 **CycPOEM**（Cyclic Position Offset Encoding Matrix）。

#### CycPOEM 注入点

| 文件 | 位置 | 修改内容 |
|------|------|---------|
| `colabfold/batch.py` L979-1012 | `get_offset()` / `get_offset_monomer()` | 计算 CycPOEM 矩阵，存入 `feat['offset_ss']` 和 `feat['cycpep_index']` |
| `colabfold/batch.py` L1013-1185 | `cpcm()` / `calc_offset_matrix_signal()` / `get_opt_path_signal()` / `mtx_with_upper_negative()` | CycPOEM 核心算法：图构建 → Floyd-Warshall 最短路 → 有向化（上三角取负） |
| `alphafold/model/modules.py` L1937 | `EmbeddingsAndEvoformer.__call__` | **monomer**：`offset = batch['offset_ss']` 替换原始 `offset = pos[:,None] - pos[None,:]` |
| `alphafold/model/modules_multimer.py` L518-519 | relative position 计算 | **multimer**：`offset[:size,:size] = batch['offset_ss']`，仅覆盖环肽部分 |

#### `colabfold/batch.py` 关键函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `get_queries(input_path, sort_by)` | → `(queries, is_complex)` | 读取 FASTA/CSV/TSV/a3m 文件 |
| `predict_structure(disulfide_bond_pairs, ...)` | 完整预测一条序列 | 调用 model_runner，注入 CycPOEM |
| `run(disulfide_bond_pairs, queries, result_dir, ...)` | 主入口 ~40 个参数 | 遍历所有查询，调用 predict_structure |
| `main()` | CLI 入口 | 解析 `--disulfide-bond-pairs` 等参数后调用 `run()` |

> **注意**：HighFold 无 `setup.py` / `pyproject.toml` / `requirements.txt`。它设计为覆盖安装到 LocalColabFold 的 site-packages 中。

## 4. 具体合并步骤

### 步骤一：搭建项目骨架

```bash
# 复制 HighFold 源码（不含 .idea/、__pycache__/）
cp -r HighFold/alphafold HighFold_C2C/
cp -r HighFold/colabfold HighFold_C2C/
cp -r HighFold/utils HighFold_C2C/
cp -r HighFold/HighFold_data HighFold_C2C/
cp HighFold/LICENSE HighFold_C2C/

# 创建新目录
mkdir -p HighFold_C2C/c2c HighFold_C2C/scripts HighFold_C2C/checkpoints
```

### 步骤二：重构 C2C 代码为 Python 模块

将 `1-predict-cyclic.py` 拆分为可导入的模块：

**c2c/config.py** — 默认配置常量：
```python
"""C2C 默认配置常量。"""

DEFAULT_CHECKPOINT_PATH = "checkpoints/c2c_model.pt"
DEFAULT_SPAN_LEN = 5
DEFAULT_NUM_SAMPLE = 20
DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 0.9
DEFAULT_SEED = 42
MAX_TOTAL_LENGTH = 20         # 环肽总长度上限
MIN_CORE_RATIO = 0.3          # core 占总长度的最低比例
```

**c2c/model.py** — 模型定义与加载：
```python
"""C2C T5 模型定义、CharTokenizer、LogitsProcessor、StoppingCriteria、模型加载。"""
import torch
from transformers import T5Config, T5ForConditionalGeneration

LETTER_SET = set(list("ACDEFGHIKLMNPQRSTVWY"))

class CharTokenizer: ...       # 原样提取
class BlockEosUntilLetters: ... # 原样提取
class StopAtLetters: ...        # 原样提取

def make_input_text(core: str, L: int) -> str: ...
def load_c2c_model(checkpoint_path: str, device: str = None) -> tuple: ...
```

**c2c/generate.py** — 序列生成：
```python
"""环肽序列生成：从 core 扩展为完整环肽序列。"""
from c2c.model import load_c2c_model, CharTokenizer, LETTER_SET, ...

def sample_c2c_dual(core, n_greedy, n_sampled, checkpoint_path, ...) -> dict: ...
def write_fasta(sequences: list, output_path: str, prefix: str = "pep"): ...
```

**c2c/evaluate.py** — 理化性质评估：
```python
"""环肽理化性质计算与 pLDDT 评分汇总。"""
from Bio.SeqUtils.ProtParam import ProteinAnalysis

HOPP_WOODS = { ... }  # 亲水性标度

def calculate_hydrophilicity(sequence: str) -> float: ...
def calculate_properties(sequence: str) -> dict: ...
def read_fasta_sequences(fasta_path: str) -> list[str]: ...
def collect_plddt_scores(result_dir: str, seq_list: list) -> dict: ...
def generate_report(seq_list: list, score_dict: dict, output_path: str): ...
```

### 步骤三：创建统一 Pipeline 入口

**scripts/run_pipeline.py** — 三阶段 pipeline：
```
Stage 1: C2C 序列生成 (PyTorch) → 输出 predict.fasta → 释放 GPU 显存
Stage 2: colabfold_batch 结构预测 (subprocess) → 输出 PDB + JSON 文件
Stage 3: 理化性质评估 + pLDDT 收集 → 输出 output.csv
```

Stage 2 使用 `subprocess.run()` 调用 `colabfold_batch` CLI（保持 overlay 模式），而非 Python API 直调：
```python
cmd = ["colabfold_batch", "--model-type", model_type, "--msa-mode", msa_mode]
if disulfide_bond_pairs:
    cmd += ["--disulfide-bond-pairs"] + [str(x) for pair in pairs for x in pair]
cmd += [str(fasta_path), str(output_dir)]
subprocess.run(cmd, check=True)
```

### 步骤四：合并环境依赖

**environment.yml**（合并版）：合并 C2C 的 `torch`/`transformers` 和 HighFold 运行时需要的 `numpy`/`pandas`/`biopython`。

> HighFold/ColabFold 本身的 JAX 等依赖由 LocalColabFold 提供，不在此 environment.yml 中重复安装。
> 此环境仅管理 C2C 生成 + 评估阶段的依赖，结构预测通过 `colabfold_batch`（LocalColabFold 环境）完成。

### 步骤五：保持向后兼容

```bash
# 原 HighFold overlay 用法（不受影响）
colabfold_batch --model-type alphafold2 --msa-mode single_sequence \
    --disulfide-bond-pairs 2 5 input.fasta output/

# 新的一体化用法
python -m scripts.run_pipeline \
    --core NNN --span-len 5 --num-sample 20 \
    --output-dir ./output
```

## 5. 关键技术决策

### 5.1 保持 overlay 模式 + subprocess 调用

| 决策 | 理由 |
|------|------|
| HighFold 继续以覆盖方式安装到 LocalColabFold | 避免重写 ColabFold 的复杂安装逻辑（haiku, jax, openmm 等），已被社区验证稳定 |
| Pipeline 通过 `subprocess.run(["colabfold_batch", ...])` 调用 | 环境隔离清晰：PyTorch 进程退出后 JAX 进程独占 GPU；不需要在同一进程中共存 PyTorch + JAX |
| C2C 阶段用独立 conda 环境 | C2C T5 仅需 `torch` + `transformers`，部署简单 |

### 5.2 GPU 显存管理

C2C T5 模型极小（`d_model=256, 4 layers, ~200MB`），HighFold/AlphaFold 才是显存大户。Pipeline 天然分阶段：
- Stage 1 (PyTorch) 在 Python 主进程中完成后，`del model; torch.cuda.empty_cache()` 释放显存
- Stage 2 (`colabfold_batch`) 作为子进程运行，独占全部 GPU 显存
- Stage 3 纯 CPU 计算

### 5.3 序列长度校验

在 `scripts/run_pipeline.py` 中加入：
```python
total_len = len(core) + span_len
assert total_len <= 20, f"总长度 {total_len} 超过限制（≤ 20 aa）"
assert len(core) / total_len >= 0.3, f"core 占比 {len(core)/total_len:.1%} 过低（≥ 30%）"
```

## 6. 迁移检查清单

- [ ] 复制 HighFold 源码（`alphafold/`, `colabfold/`, `utils/`, `HighFold_data/`, `LICENSE`）
- [ ] 将 `1-predict-cyclic.py` 拆分为 `c2c/model.py` + `c2c/generate.py`
- [ ] 将 `3-final.py` 重构为 `c2c/evaluate.py`
- [ ] 创建 `c2c/__init__.py` 和 `c2c/config.py`
- [ ] 创建 `scripts/run_pipeline.py`（subprocess 调用 colabfold_batch）
- [ ] 创建 `scripts/run_predict_only.py`（向后兼容）
- [ ] 创建合并后的 `environment.yml`
- [ ] 创建 `pyproject.toml` 项目元数据
- [ ] 编写 README.md（安装说明 + 两种使用方式）
- [ ] 创建 `.gitignore` + `checkpoints/.gitkeep`
- [ ] 确保 `colabfold_batch` CLI 入口不受影响

## 7. 合并前后对比

### 合并前（用户操作）
```bash
# 1. 安装 LocalColabFold
cd localcolabfold && pixi install && pixi run setup

# 2. 安装 HighFold（覆盖 colabfold 源码）
cp -r HighFold/alphafold/* .../site-packages/alphafold/
cp -r HighFold/colabfold/* .../site-packages/colabfold/

# 3. 配置 C2C 环境
cd C2C_release && conda env create -f environment.yml && conda activate c2c

# 4. 运行三步 pipeline（需手动切换环境）
python 1-predict-cyclic.py
conda deactivate && export PATH=".../localcolabfold/.pixi/envs/default/bin:$PATH"
bash 2-run-highfold.sh
conda activate c2c
python 3-final.py
```

### 合并后（用户操作）
```bash
# 1. 安装 LocalColabFold + HighFold overlay（同前）
cd localcolabfold && pixi install && pixi run setup
cp -r HighFold_C2C/alphafold/* .../site-packages/alphafold/
cp -r HighFold_C2C/colabfold/* .../site-packages/colabfold/

# 2. 安装 C2C 环境
cd HighFold_C2C && conda env create -f environment.yml && conda activate highfold_c2c

# 3. 下载模型权重
# 将 c2c_model.pt 放入 checkpoints/

# 4. 一条命令运行全流程
python -m scripts.run_pipeline --core NNN --span-len 5 --num-sample 20 --output-dir ./output
```

## 8. 风险与注意事项

1. **`colabfold_batch` 须在 PATH 上**：Pipeline Stage 2 通过 subprocess 调用 `colabfold_batch`。用户需确保 LocalColabFold 的 bin 目录在 `$PATH` 中，或在 `--colabfold-bin` 参数中指定完整路径。
2. **AlphaFold 权重下载**：首次运行 `colabfold_batch` 时会自动下载 AlphaFold 参数（~4GB），需确保网络可用。
3. **C2C 模型权重**：`c2c_model.pt` 不在公开仓库中，需要单独提供下载链接或存放位置。
4. **序列长度限制**：C2C 训练数据大多 < 15 aa，不要生成 > 20 aa 的环肽；core 长度应 ≥ 总长度的 30%。代码中已加入校验。
5. **overlay 文件一致性**：`alphafold/` 和 `colabfold/` 目录需与 LocalColabFold 的 ColabFold 版本相匹配。如 ColabFold 升级需重新适配。
