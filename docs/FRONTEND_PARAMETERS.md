# HighFold-C2C 前端参数说明

> 本文档面向前端开发者，详细说明用户提交 HighFold-C2C 任务时需要传递的所有参数、验证规则和推荐的 UI 设计。

---

## 1. 背景

HighFold-C2C 是一个三阶段的环肽设计与结构预测 pipeline：

| 阶段 | 功能 | 关键输入 |
|------|------|---------|
| Stage 1 — C2C 序列生成 | 使用 T5 模型，从核心肽段生成环肽候选序列 | `core_sequence`, `span_len`, `num_sample` |
| Stage 2 — HighFold 结构预测 | 使用 CycPOEM 增强的 AlphaFold2 预测 3D 结构 | `model_type`, `disulfide_bond_pairs` |
| Stage 3 — 理化性质评估 | 计算 pLDDT、分子量、等电点等 | 无额外输入 |

原始 C2C 项目（[tjliao/C2C_demo](https://github.com/tjliao/C2C_demo)）仅需三个参数：**core**、**span length**、**number of sample**。HighFold-C2C 在此基础上扩展了结构预测和二硫键支持等参数。

---

## 2. 参数总览

### 2.1 任务创建流程

前端提交任务后，AstraMolecula 后端会：

1. 在 `tasks` 表中创建一条记录（`task_type = 'highfold_c2c'`, `status = 'pending'`）
2. 在 `highfold_task_params` 表中写入该任务的具体参数
3. HighFold-C2C 微服务轮询数据库，取出 pending 任务并执行

因此，前端需要将用户输入的参数传递给后端 API，由后端写入这两张表。

### 2.2 参数分类

| 分类 | 说明 | 数量 |
|------|------|------|
| 🔴 必填参数 | 用户必须提供，无默认值 | 1 个 |
| 🟡 基础参数 | 有默认值，但建议在表单中暴露给用户 | 3 个 |
| 🔵 高级参数 | 有合理默认值，可放在折叠面板中 | 9 个 |
| ⚪ 阶段控制 | 控制跳过某个阶段，一般用户不需要 | 3 个 |

---

## 3. 参数详细说明

### 3.1 🔴 必填参数

#### `core_sequence` — 核心肽段序列

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.core_sequence` |
| **类型** | `string` (VARCHAR(50)) |
| **默认值** | 无 — **必须由用户提供** |
| **示例** | `"NNN"`, `"CNNNC"`, `"ACDEFG"` |
| **说明** | 核心肽段氨基酸序列。C2C 模型会在此序列两端各延伸 `span_len` 个残基，生成完整的环肽序列。 |

**前端 UI 建议：** 单行文本输入框，placeholder 为 `"请输入核心肽段序列，如 NNN"`

**验证规则：**
- 不能为空
- 只能包含 20 种标准氨基酸单字母编码：`A, C, D, E, F, G, H, I, K, L, M, N, P, Q, R, S, T, V, W, Y`
- 正则表达式：`/^[ACDEFGHIKLMNPQRSTVWY]+$/i`
- 长度建议 ≥ 1，实际有效长度受总长度约束（见第 4 节）

---

### 3.2 🟡 基础参数（建议在主表单中展示）

#### `span_len` — 延伸长度

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.span_len` |
| **类型** | `int` |
| **默认值** | `5` |
| **范围** | 1 ~ 15（推荐） |
| **说明** | 在核心序列两端各延伸的残基数量。总环肽长度 = `len(core_sequence) + span_len × 2` |

**前端 UI 建议：** 数字输入框或滑块（Slider），默认值 5

---

#### `num_sample` — 采样数量

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.num_sample` |
| **类型** | `int` |
| **默认值** | `20` |
| **范围** | 1 ~ 100（推荐） |
| **说明** | 希望 C2C 模型输出的候选环肽序列总数。其中第 1 条为贪心解码（greedy），其余为随机采样（sampling）。数值越大，计算时间越长。 |

**前端 UI 建议：** 数字输入框，默认值 20

---

#### `disulfide_bond_pairs` — 二硫键位置对

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.disulfide_bond_pairs` |
| **类型** | `string | null` (VARCHAR(255)) |
| **默认值** | `null`（无二硫键） |
| **格式** | `"A,B"` 或 `"A,B:C,D"` — 0-based 索引，多对用 `:` 分隔 |
| **示例** | `"0,4"` 表示第 0 位和第 4 位半胱氨酸形成二硫键；`"0,4:2,7"` 表示两对 |
| **说明** | 指定环肽中二硫键的位置对。只有当核心序列包含半胱氨酸 (C) 时才需要设置。设置后，HighFold 结构预测阶段会启用 CycPOEM 二硫键约束。 |

**前端 UI 建议：**
- 可选输入框，placeholder 为 `"如 0,4 或 0,4:2,7（可选）"`
- 或提供可视化的残基位置选择器
- 当用户未输入时传 `null`

---

### 3.3 🔵 高级参数（建议放在可折叠/展开面板中）

#### `temperature` — 采样温度

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.temperature` |
| **类型** | `float` |
| **默认值** | `1.0` |
| **范围** | 0.1 ~ 2.0 |
| **说明** | 控制序列采样的随机性。值越高，生成的序列越多样但可能质量下降；值越低，序列越保守。 |

---

#### `top_p` — 核采样阈值

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.top_p` |
| **类型** | `float` |
| **默认值** | `0.9` |
| **范围** | 0.1 ~ 1.0 |
| **说明** | Nucleus sampling 参数。每一步只从累计概率达到 `top_p` 的 token 中采样。值越小，结果越保守。 |

---

#### `seed` — 随机种子

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.seed` |
| **类型** | `int` |
| **默认值** | `42` |
| **说明** | 随机数种子，用于结果可复现。相同种子 + 相同参数 = 相同输出。 |

---

#### `model_type` — 结构预测模型类型

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.model_type` |
| **类型** | `string` |
| **默认值** | `"alphafold2"` |
| **可选值** | `alphafold2`, `alphafold2_ptm`, `alphafold2_multimer_v1`, `alphafold2_multimer_v2`, `alphafold2_multimer_v3`, `deepfold_v1` |
| **说明** | AlphaFold 模型变体。对于单体环肽，`alphafold2` 即可；多聚体需选择 multimer 版本。 |

**前端 UI 建议：** 下拉选择框（Select）

---

#### `msa_mode` — MSA 搜索模式

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.msa_mode` |
| **类型** | `string` |
| **默认值** | `"single_sequence"` |
| **可选值** | `single_sequence`, `mmseqs2_uniref`, `mmseqs2_uniref_env` |
| **说明** | 多序列比对模式。`single_sequence` 不做 MSA 搜索（速度最快），其他选项会搜索数据库生成 MSA。 |

**前端 UI 建议：** 下拉选择框

---

#### `num_models` — 预测模型数量

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.num_models` |
| **类型** | `int` |
| **默认值** | `5` |
| **可选值** | `1, 2, 3, 4, 5` |
| **说明** | AlphaFold 使用几个模型进行预测。每个模型独立预测一个结构，更多模型 = 更多结果但更慢。 |

---

#### `num_recycle` — 循环次数

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.num_recycle` |
| **类型** | `int | null` |
| **默认值** | `null`（使用 AlphaFold 内部默认值，通常为 3） |
| **说明** | AlphaFold 的 recycling 迭代次数。更多次数可能提高预测质量但增加计算时间。 |

---

#### `use_templates` — 使用模板

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.use_templates` |
| **类型** | `boolean` |
| **默认值** | `false` |
| **说明** | 是否使用 PDB 模板辅助结构预测。对于新序列通常不需要。 |

---

#### `amber` — AMBER 精修

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.amber` |
| **类型** | `boolean` |
| **默认值** | `false` |
| **说明** | 是否使用 AMBER 力场对预测结构进行能量最小化。启用后结构更合理但耗时增加。 |

#### `num_relax` — 精修结构数

| 属性 | 值 |
|------|-----|
| **数据库字段** | `highfold_task_params.num_relax` |
| **类型** | `int` |
| **默认值** | `0` |
| **说明** | 当 `amber = true` 时，对排名前 N 的结构进行 AMBER relax。 |

---

### 3.4 ⚪ 阶段控制参数（一般用户不需要，可不展示）

| 参数 | 数据库字段 | 类型 | 默认值 | 说明 |
|------|-----------|------|--------|------|
| `skip_generate` | `skip_generate` | `boolean` | `false` | 跳过 C2C 序列生成。需配合上传 FASTA 文件使用 |
| `skip_predict` | `skip_predict` | `boolean` | `false` | 跳过结构预测（仅生成序列） |
| `skip_evaluate` | `skip_evaluate` | `boolean` | `false` | 跳过评估阶段 |

> 如果 `skip_generate = true`，用户需要上传一个 FASTA 文件到 SeaweedFS 的 `{job_dir}/input/predict.fasta` 路径，此时 `core_sequence` 可以不填。

---

## 4. 前端验证规则

### 4.1 序列约束（来自原始 C2C 训练数据限制）

```
总环肽长度 = len(core_sequence) + span_len × 2
```

| 规则 | 公式 | 说明 |
|------|------|------|
| **最大长度** | `len(core) + span_len × 2 ≤ 20` | 训练数据多为 ≤15 aa，不建议超过 20 |
| **核心比例** | `len(core) / (len(core) + span_len × 2) ≥ 0.3` | 核心太短、延伸太长会导致生成质量下降 |

### 4.2 前端验证伪代码

```typescript
function validateParams(core: string, spanLen: number, numSample: number): string | null {
  // 1. core_sequence 必填
  if (!core || core.trim().length === 0) {
    return "请输入核心肽段序列";
  }

  // 2. 只允许标准氨基酸
  if (!/^[ACDEFGHIKLMNPQRSTVWY]+$/i.test(core)) {
    return "序列只能包含标准氨基酸字母 (A,C,D,E,F,G,H,I,K,L,M,N,P,Q,R,S,T,V,W,Y)";
  }

  // 3. 总长度限制
  const totalLength = core.length + spanLen * 2;
  if (totalLength > 20) {
    return `总环肽长度 (${totalLength} aa) 超过上限 20。请缩短核心序列或减小延伸长度。`;
  }

  // 4. 核心比例检查
  const coreRatio = core.length / totalLength;
  if (coreRatio < 0.3) {
    return `核心序列占比 (${(coreRatio * 100).toFixed(0)}%) 低于 30%。请增加核心长度或减小延伸长度。`;
  }

  // 5. 采样数量
  if (numSample < 1 || numSample > 100) {
    return "采样数量应在 1~100 之间";
  }

  return null; // 验证通过
}
```

### 4.3 有效参数组合示例

| core | span_len | 总长度 | 核心占比 | 是否有效 |
|------|----------|--------|----------|---------|
| `NNN` (3 aa) | 5 | 13 | 23% | ❌ 核心占比 < 30% |
| `NNN` (3 aa) | 3 | 9 | 33% | ✅ |
| `NNNNN` (5 aa) | 5 | 15 | 33% | ✅ |
| `NNN` (3 aa) | 7 | 17 | 18% | ❌ 核心占比 < 30% |
| `ACDEFG` (6 aa) | 7 | 20 | 30% | ✅ 刚好 |
| `ACDEFG` (6 aa) | 8 | 22 | 27% | ❌ 总长度 > 20 |
| `N` (1 aa) | 10 | 21 | 5% | ❌ 两个规则都违反 |

---

## 5. 前端提交 JSON 示例

### 5.1 最简提交（仅填必填 + 基础参数）

```json
{
  "core_sequence": "NNN",
  "span_len": 5,
  "num_sample": 20
}
```

> 其余参数全部使用服务端默认值。

### 5.2 带二硫键的提交

```json
{
  "core_sequence": "CNNNC",
  "span_len": 5,
  "num_sample": 20,
  "disulfide_bond_pairs": "0,4"
}
```

### 5.3 完整参数提交（高级用户）

```json
{
  "core_sequence": "CNNNC",
  "span_len": 5,
  "num_sample": 30,
  "disulfide_bond_pairs": "0,4",
  "temperature": 0.8,
  "top_p": 0.95,
  "seed": 123,
  "model_type": "alphafold2",
  "msa_mode": "single_sequence",
  "num_models": 5,
  "num_recycle": 3,
  "use_templates": false,
  "amber": true,
  "num_relax": 1
}
```

---

## 6. 推荐的前端 UI 布局

```
┌─────────────────────────────────────────────────────────┐
│           HighFold-C2C 环肽设计                          │
│  Cyclic Peptide Design & Structure Prediction            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  核心肽段序列 *                                          │
│  ┌───────────────────────────────────────────────┐      │
│  │ NNN                                           │      │
│  └───────────────────────────────────────────────┘      │
│  仅限标准氨基酸 (A-Y)，如 NNN、CNNNC                     │
│                                                         │
│  延伸长度 (span_len)           采样数量 (num_sample)      │
│  ┌──────────┐                ┌──────────┐               │
│  │    5     │                │    20    │               │
│  └──────────┘                └──────────┘               │
│                                                         │
│  二硫键位置对（可选）                                     │
│  ┌───────────────────────────────────────────────┐      │
│  │ 如 0,4 或 0,4:2,7                             │      │
│  └───────────────────────────────────────────────┘      │
│                                                         │
│  📊 预估：总环肽长度 = 3 + 5×2 = 13 aa ✅               │
│         核心占比 = 23% ⚠️ (建议 ≥30%)                   │
│                                                         │
│  ▸ 高级参数                                              │
│  ┌─────────────────────────────────────────────────┐    │
│  │ 温度: [1.0]  Top-p: [0.9]  种子: [42]          │    │
│  │ 模型: [alphafold2 ▾]  MSA: [single_sequence ▾]  │    │
│  │ 模型数: [5 ▾]                                    │    │
│  │ □ AMBER 精修   □ 使用模板                         │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│           ┌──────────────────┐                          │
│           │   🚀 提交任务     │                          │
│           └──────────────────┘                          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 7. 数据库表结构参考

前端提交的参数最终写入 `highfold_task_params` 表：

```sql
CREATE TABLE IF NOT EXISTS highfold_task_params (
  id                   CHAR(32)      NOT NULL,
  task_id              CHAR(36)      NOT NULL,

  -- C2C 序列生成参数（Stage 1）
  core_sequence        VARCHAR(50)   DEFAULT NULL,     -- ★ 用户必填
  span_len             INT           DEFAULT 5,        -- ★ 基础参数
  num_sample           INT           DEFAULT 20,       -- ★ 基础参数
  temperature          DECIMAL(4,2)  DEFAULT 1.0,
  top_p                DECIMAL(4,2)  DEFAULT 0.9,
  seed                 INT           DEFAULT 42,

  -- HighFold 结构预测参数（Stage 2）
  model_type           VARCHAR(50)   DEFAULT 'alphafold2',
  msa_mode             VARCHAR(50)   DEFAULT 'single_sequence',
  disulfide_bond_pairs VARCHAR(255)  DEFAULT NULL,     -- ★ 基础参数（可选）
  num_models           INT           DEFAULT 5,
  num_recycle          INT           DEFAULT NULL,
  use_templates        BOOLEAN       DEFAULT FALSE,
  amber                BOOLEAN       DEFAULT FALSE,
  num_relax            INT           DEFAULT 0,

  -- 阶段控制
  skip_generate        BOOLEAN       DEFAULT FALSE,
  skip_predict         BOOLEAN       DEFAULT FALSE,
  skip_evaluate        BOOLEAN       DEFAULT FALSE,

  PRIMARY KEY (id),
  FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
```

---

## 8. 与原始 C2C Demo 的参数对应关系

| 原始 C2C (tjliao/C2C_demo) | HighFold-C2C 字段 | 说明 |
|---|---|---|
| `core` | `core_sequence` | 完全一致 |
| `span length` | `span_len` | 完全一致 |
| `number of sample` | `num_sample` | 完全一致 |
| _(无)_ | `disulfide_bond_pairs` | HighFold 扩展，支持二硫键约束 |
| _(无)_ | `temperature`, `top_p`, `seed` | HighFold 扩展，采样控制参数 |
| _(无)_ | `model_type`, `msa_mode` 等 | HighFold 扩展，结构预测参数 |

**核心结论：** 原始 C2C 只需要 3 个参数（core, span_len, num_sample），HighFold-C2C 在此基础上增加了二硫键和结构预测控制，但所有新增参数都有合理默认值，前端最少只需收集这 3 个参数即可运行。
