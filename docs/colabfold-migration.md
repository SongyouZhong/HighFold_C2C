# ColabFold 新版适配说明

> **日期**：2026-03-02  
> **范围**：HighFold_C2C 项目中 `colabfold/` 和 `alphafold/` 目录  
> **目标**：将 CycPOEM（环肽位置偏移编码矩阵）从旧版 ColabFold 迁移到新版 ColabFold v1.5.5

---

## 1. 背景

### 1.1 旧版架构

HighFold 原本基于旧版 ColabFold 进行修改，CycPOEM 算法的全部代码（约 200 行）直接嵌入在 `colabfold/batch.py` 中，与 ColabFold 业务逻辑深度耦合。

### 1.2 新版 ColabFold 的变化

新版 ColabFold（v1.5.5，Python 3.12，JAX 0.5.3，pixi 管理）对代码结构进行了大规模重构：

| 变化类型 | 具体内容 |
|---------|---------|
| **文件拆分** | `batch.py` 中的 `get_queries()`、`pair_msa()`、`msa_to_str()`、`safe_filename()` 等函数移至新建的 `input.py` |
| **文件拆分** | `relax_me()` 函数从 `batch.py` 移至新建的 `relax.py` |
| **新增模块** | `alphafold/extra_ptm.py` — 新增 pairwise ipTM、actifpTM、chain-wise pTM 计算 |
| **API 变更** | `get_queries()` 返回值从 3 元组 `(name, seq, a3m)` 变为 4 元组 `(name, seq, a3m, other_queries)` |
| **新增参数** | `predict_structure()` 新增 `initial_guess`、`calc_extra_ptm`、`use_probs_extra`、relax 配置参数 |
| **新增参数** | `run()` 新增 `pairing_strategy`、`user_agent`、`max_template_date`、`max_template_hits` |
| **新增功能** | 支持 `deepfold_v1` 模型类型 |
| **工具类变更** | `utils.py` 新增 `MolType` 枚举、`AF3Utils` 类；`safe_filename` 移至 `input.py` |
| **下载逻辑** | `download.py` 使用 `appdirs` 替换硬编码路径；支持 DeepFold 权重的并行下载 |
| **MSA 搜索** | `mmseqs/search.py` 的 import 从 `colabfold.batch` 改为 `colabfold.input` |

### 1.3 可行性评估

CycPOEM 的修改与上游重构是**正交**的：
- CycPOEM 仅在特征字典中注入 `offset_ss`（距离矩阵）和 `cycpep_index`（环肽索引），不修改 ColabFold 的核心逻辑
- AlphaFold 模型层（`modules.py`、`modules_multimer.py`）中读取这两个特征的代码与 ColabFold 版本无关
- 因此只需将 CycPOEM 算法提取为独立模块，在新版 `batch.py` 的相同注入点重新挂载即可

---

## 2. 实施方案

### 2.1 设计原则

1. **解耦**：将 CycPOEM 算法从 `batch.py` 提取为独立模块 `cycpoem.py`
2. **可选注入**：通过 `disulfide_bond_pairs: Optional[List[Tuple[int, int]]] = None` 参数控制，默认 `None` 时行为与原版 ColabFold 完全一致
3. **最小侵入**：在新版 `batch.py` 中只在必要位置添加条件调用，不改变原有控制流

### 2.2 总体架构

```
CLI --disulfide-bond-pairs "2,13:6,20"
  │
  ▼
main()  ─→  解析为 [(2,13), (6,20)]
  │
  ▼
run(disulfide_bond_pairs=...)
  │
  ├─→ generate_input_feature(disulfide_bond_pairs=...)
  │     └─→ process_multimer_features(disulfide_bond_pairs=...)
  │           └─→ get_offset(pairs, feat)  # multimer 分支
  │
  └─→ predict_structure(disulfide_bond_pairs=...)
        └─→ get_offset_monomer(pairs, feat)  # monomer 分支

                    ↓

AlphaFold 模型层条件读取 feat['offset_ss']:
  · modules.py       → if 'offset_ss' in batch: offset = batch['offset_ss']
  · modules_multimer → if 'offset_ss' in batch: offset[:s,:s] = batch['offset_ss']
```

---

## 3. 修改详情

### 3.1 新建文件

#### `colabfold/cycpoem.py`（303 行）

从旧版 `batch.py` 中提取的 CycPOEM 算法独立模块。

**公开 API：**

| 函数 | 用途 |
|------|------|
| `get_offset(disulfide_bond_pairs, feat)` | **multimer** 模式：通过 `residue_index` 找到第一条链的边界，计算 CycPOEM 距离矩阵，写入 `feat['offset_ss']` 和 `feat['cycpep_index']` |
| `get_offset_monomer(disulfide_bond_pairs, feat)` | **monomer** 模式：使用 `aatype` 长度确定序列长度，计算 CycPOEM 距离矩阵 |

**内部函数：**

| 函数 | 用途 |
|------|------|
| `cpcm(seq_len, disulfide_bond_pairs)` | 构建邻接矩阵（线性键 + N-C 环化键 + 二硫键） |
| `calc_offset_matrix_signal(n, c1, c2)` | 带方向标记的 Floyd-Warshall 最短路径计算 |
| `calc_offset_matrix(n, c1, c2)` | 不带方向标记的最短路径（备用） |
| `_get_opt_path_signal(...)` | Floyd-Warshall 核心迭代（带方向） |
| `_mtx_with_upper_negative(...)` | 上三角取负（编码方向性） |
| `_get_opt_path(...)` | Floyd-Warshall 核心迭代（无方向） |
| `_get_path(...)` | 路径回溯 |
| `_mtx_with_signal(...)` | 路径方向标记矩阵构建 |

**与旧版的改进：**
- 清除所有调试用 `print()` 语句
- 内部辅助函数以 `_` 前缀标识
- 添加完整的模块级文档字符串和函数文档字符串

#### `colabfold/input.py`（401 行）

新版 ColabFold 从 `batch.py` 中拆分出的输入处理模块，直接从新版复制，无需修改。

包含：`get_queries()`、`pair_msa()`、`msa_to_str()`、`safe_filename()`、`parse_fasta()`、`classify_molecules()`、`pdb_to_string()`、`decode_structure_sequences()` 等。

#### `colabfold/relax.py`（107 行）

新版 ColabFold 拆分出的结构弛豫模块，直接复制，无需修改。

包含 `relax_me()` 函数，支持可配置的 `max_iterations`、`tolerance`、`stiffness`、`max_outer_iterations` 参数。

#### `colabfold/alphafold/extra_ptm.py`（435 行）

新版 ColabFold 新增的额外 pTM 指标计算模块，直接复制，无需修改。

包含 actifpTM、pairwise ipTM、chain-wise pTM 计算。

### 3.2 替换文件（新版覆盖旧版）

以下文件从新版 ColabFold 复制到项目中，替换旧版：

| 文件 | 主要变化 |
|------|---------|
| `colabfold/batch.py` | 完全使用新版作为基础，添加 CycPOEM 注入（详见 3.3） |
| `colabfold/utils.py` | 新增 `MolType`、`AF3Utils`；`absl` import 改为 try/except |
| `colabfold/download.py` | 使用 `appdirs`；支持 `deepfold_v1` 并行下载 |
| `colabfold/colabfold.py` | `run_mmseqs2()` 新增 `pairing_strategy`、`user_agent` 参数 |
| `colabfold/alphafold/models.py` | `model_type` 字符串调度（替代 `model_suffix`）；支持 `deepfold_v1` |
| `colabfold/mmseqs/search.py` | import 改为 `from colabfold.input` |
| `colabfold/plot.py` | 直接复制 |
| `colabfold/pdb.py` | 直接复制 |
| `colabfold/citations.py` | 直接复制 |

### 3.3 `colabfold/batch.py` CycPOEM 注入点

在新版 `batch.py`（2157 行）中，共修改 6 个位置：

#### ① import 注入（第 79 行）

```python
from colabfold.cycpoem import get_offset, get_offset_monomer
```

#### ② `predict_structure()` 函数（第 320 行起）

- 函数签名添加 `disulfide_bond_pairs: Optional[List[Tuple[int, int]]] = None`
- 在 monomer 分支的 `model_runner.process_features()` 之后添加：

```python
# CycPOEM: inject offset_ss for monomer
if disulfide_bond_pairs:
    get_offset_monomer(disulfide_bond_pairs, input_features)
```

#### ③ `process_multimer_features()` 函数（第 742 行起）

- 函数签名添加 `disulfide_bond_pairs: Optional[List[Tuple[int, int]]] = None`
- 在 `pad_msa()` 之后添加：

```python
# CycPOEM: inject offset_ss for multimer
if disulfide_bond_pairs:
    get_offset(disulfide_bond_pairs, np_example)
```

#### ④ `generate_input_feature()` 函数（第 813 行起）

- 函数签名添加 `disulfide_bond_pairs: Optional[List[Tuple[int, int]]] = None`
- 调用 `process_multimer_features()` 时透传 `disulfide_bond_pairs=disulfide_bond_pairs`

#### ⑤ `run()` 函数（第 1085 行起）

- 函数签名添加 `disulfide_bond_pairs: Optional[List[Tuple[int, int]]] = None`
- 调用 `generate_input_feature()` 时透传 `disulfide_bond_pairs=disulfide_bond_pairs`
- 调用 `predict_structure()` 时透传 `disulfide_bond_pairs=disulfide_bond_pairs`

#### ⑥ `main()` 函数（第 1645 行起）

- 新增 CLI 参数组 "CycPOEM arguments (HighFold)"：

```python
cycpoem_group.add_argument(
    "--disulfide-bond-pairs",
    type=str, default=None,
    help="Disulfide bond residue pairs for CycPOEM offset matrix. "
         "Format: 'A,B' for single pair or 'A,B:C,D' for multiple pairs. "
         "Example: '2,13' or '2,13:6,20'. Residue indices are 0-based.",
)
```

- 解析为元组列表后传入 `run()`：

```python
disulfide_bond_pairs = None
if args.disulfide_bond_pairs is not None:
    disulfide_bond_pairs = []
    for pair_str in args.disulfide_bond_pairs.split(":"):
        parts = pair_str.strip().split(",")
        if len(parts) != 2:
            raise ValueError(f"Each disulfide pair must be 'A,B', got '{pair_str}'")
        disulfide_bond_pairs.append((int(parts[0]), int(parts[1])))
```

### 3.4 AlphaFold 模型层修改

#### `alphafold/model/model.py`（monomer + multimer 共用）

`RunModel.__init__` 新增 `extended_ptm_config` 可选参数，兼容新版 ColabFold `models.py` 中传递的扩展 pTM 配置：

```python
def __init__(self,
             config,
             params=None,
             is_training=False,
             extended_ptm_config: Optional[dict] = None):  # 新增
    self.extended_ptm_config = extended_ptm_config        # 新增
```

> 同时修改 `colabfold/alphafold/model/model.py`（ColabFold 内嵌的副本）。

#### `alphafold/model/modules.py`（monomer，第 1930 行附近）

- **删除**：`print(offset)` 调试语句
- **改为条件访问**：不使用 CycPOEM 时回退到标准线性偏移

修改后代码：
```python
# start of add on 20230823 (CycPOEM offset)
if 'offset_ss' in batch:
  offset = batch['offset_ss']
else:
  offset = pos[:, None] - pos[None, :]
# end of add on 20230823
offset = jnp.clip(offset + c.max_relative_feature, ...)
```

#### `alphafold/model/modules_multimer.py`（multimer，第 518-519 行）

**改为条件访问**（原先无条件访问 `batch['offset_ss']` 和 `batch['cycpep_index']`）：
```python
offset = pos[:, None] - pos[None, :]
if 'offset_ss' in batch and 'cycpep_index' in batch:
  size = len(batch['cycpep_index'])
  offset = offset.at[:size, :size].set(batch['offset_ss'])
```

#### `alphafold/data/mmcif_parsing.py`（Biopython 兼容性）

Biopython ≥ 1.80 移除了 `Bio.Data.SCOPData`，添加 try/except 回退到 `IUPACData`：
```python
try:
    from Bio.Data import SCOPData
except ImportError:
    from Bio.Data import IUPACData as SCOPData
```

> 同时修改 `colabfold/alphafold/data/mmcif_parsing.py`。

### 3.5 脚本更新

#### `scripts/run_pipeline.py`

- `--model-type` 的 `choices` 新增 `"deepfold_v1"`

#### `scripts/run_predict_only.py`

- `--model-type` 的 `choices` 新增 `"deepfold_v1"`

---

## 4. 参数流转图

```
用户命令行
  --disulfide-bond-pairs "2,13:6,20"
         │
         ▼
   main() 解析为 [(2,13), (6,20)]
         │
         ▼
   run(disulfide_bond_pairs=[(2,13),(6,20)])
         │
         ├────────────────────────────────┐
         ▼                                ▼
generate_input_feature(                predict_structure(
  disulfide_bond_pairs=...)              disulfide_bond_pairs=...)
         │                                │
         ▼ (multimer)                     ▼ (monomer)
process_multimer_features(            model_runner.process_features()
  disulfide_bond_pairs=...)            get_offset_monomer(pairs, feat)
         │                                │
         ▼                                ▼
get_offset(pairs, feat)               feat['offset_ss'] = matrix
         │                            feat['cycpep_index'] = index
         ▼
feat['offset_ss'] = matrix
feat['cycpep_index'] = index
         │
         ▼
  AlphaFold JAX Model
  ┌─ modules.py:      if 'offset_ss' in batch → offset = batch['offset_ss']
  └─ modules_multimer: if 'offset_ss' in batch → offset[:s,:s] = batch['offset_ss']
```

---

## 5. 向后兼容性

| 场景 | 行为 |
|------|------|
| 不传 `--disulfide-bond-pairs` | `disulfide_bond_pairs=None`，所有 CycPOEM 代码被跳过，行为与原版 ColabFold 完全一致 |
| 传入 `--disulfide-bond-pairs` | 激活 CycPOEM，计算环肽距离矩阵并注入特征 |
| 使用 `colabfold_batch` CLI | 原有参数全部保留，新增 `--disulfide-bond-pairs` 参数组 |
| 使用 `run()` Python API | 新增可选参数 `disulfide_bond_pairs`，默认 `None` |

---

## 6. 安装方式

适配后的安装方式不变，仍使用 overlay 模式：

```bash
# 1. 安装 LocalColabFold (pixi)
cd localcolabfold && pixi install && pixi run setup

# 2. 覆盖源码
SITE_PACKAGES="localcolabfold/.pixi/envs/default/lib/python3.12/site-packages"
cp -r HighFold_C2C/alphafold/* "$SITE_PACKAGES/alphafold/"
cp -r HighFold_C2C/colabfold/* "$SITE_PACKAGES/colabfold/"

# 3. 验证
colabfold_batch --help | grep disulfide
```

> **注意**：新版 LocalColabFold 使用 Python 3.12（非 3.10），覆盖路径需对应调整。

---

## 7. 验证清单

- [x] 所有修改文件通过 `python -c "import ast; ast.parse(...)"` 语法检查
- [x] `disulfide_bond_pairs` 参数在完整调用链中正确传递（6 个函数 + CLI）
- [x] `alphafold/model/modules.py` 中调试 `print` 已移除
- [x] `colabfold/cycpoem.py` 模块可独立 import
- [x] 不传 `--disulfide-bond-pairs` 时与原版 ColabFold 行为一致
- [x] 端到端功能测试：基线预测（无 CycPOEM）pLDDT=77.9 ✓
- [x] 端到端功能测试：CycPOEM 预测（`--disulfide-bond-pairs "0,7"`）pLDDT=77.8 ✓
- [x] C2C T5 模型推理：greedy + sampling 输出与原版 C2C_release 一致 ✓

---

## 8. 修改文件清单

| 文件 | 操作 | 行数 |
|------|------|------|
| `colabfold/cycpoem.py` | **新建** | 303 |
| `colabfold/batch.py` | 替换后注入 CycPOEM | 2159 |
| `colabfold/input.py` | **新建**（从新版 ColabFold 复制） | 401 |
| `colabfold/relax.py` | **新建**（从新版 ColabFold 复制） | 107 |
| `colabfold/alphafold/extra_ptm.py` | **新建**（从新版 ColabFold 复制） | 435 |
| `colabfold/utils.py` | 替换为新版 | — |
| `colabfold/download.py` | 替换为新版 | — |
| `colabfold/colabfold.py` | 替换为新版 | — |
| `colabfold/alphafold/models.py` | 替换为新版 | — |
| `colabfold/mmseqs/search.py` | 替换为新版 | — |
| `colabfold/plot.py` | 替换为新版 | — |
| `colabfold/pdb.py` | 替换为新版 | — |
| `colabfold/citations.py` | 替换为新版 | — |
| `alphafold/model/model.py` | 新增 `extended_ptm_config` 参数 | 204 |
| `colabfold/alphafold/model/model.py` | 新增 `extended_ptm_config` 参数 | 204 |
| `alphafold/model/modules.py` | 移除调试 print + 条件访问 `offset_ss` | 2283 |
| `alphafold/model/modules_multimer.py` | 条件访问 `offset_ss`/`cycpep_index` | 1139 |
| `alphafold/data/mmcif_parsing.py` | SCOPData → IUPACData 兼容 | — |
| `colabfold/alphafold/data/mmcif_parsing.py` | SCOPData → IUPACData 兼容 | — |
| `scripts/run_pipeline.py` | 新增 deepfold_v1 + 更新 CLI 格式 | 287 |
| `scripts/run_predict_only.py` | 新增 deepfold_v1 + 更新 CLI 格式 | 87 |
