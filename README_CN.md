# HighFold-C2C：环肽设计与结构预测

HighFold-C2C 是一个统一的流水线工具，结合了 **C2C**（基于 T5 模型的环肽序列生成）与 **HighFold**（基于 CycPOEM 增强的 AlphaFold2 环肽结构预测）。

它既可以作为 **独立 CLI 工具** 运行，也可以部署为 **微服务**，集成 FastAPI、PostgreSQL 任务追踪和 SeaweedFS 对象存储——遵循 AstraMolecula 平台的统一架构。

## 功能特性

- **C2C 序列生成**：给定核心肽段序列，使用预训练 T5 模型生成多样化的环肽候选序列
- **HighFold 结构预测**：通过 CycPOEM（环状位置偏移编码矩阵）预测环肽的 3D 结构，支持头尾相连和二硫键约束
- **ColabFold v1.5.5 支持**：适配最新 ColabFold 模块化架构（`input.py`、`relax.py`、`extra_ptm.py`），支持 `deepfold_v1` 模型。详见 [docs/colabfold-migration.md](docs/colabfold-migration.md)
- **统一流水线**：一条命令完成完整工作流——从序列设计到结构预测再到理化评估
- **微服务模式**：FastAPI 服务器（端口 8003），支持后台任务轮询、多 Worker 并发、RESTful 结果查询
- **对象存储**：SeaweedFS 集成，统一管理输入/输出文件
- **任务追踪**：基于 PostgreSQL 的任务队列（共享 AstraMolecula `tasks` 表，`task_type='highfold_c2c'`）
- **Docker 部署**：支持 GPU 的容器化部署，使用 Docker Compose 编排；连接宿主机上已有的 PostgreSQL 和 SeaweedFS 服务
- **向后兼容**：原有 `colabfold_batch` CLI 工作流完整保留；CycPOEM 仅在提供 `--disulfide-bond-pairs` 参数时激活

## 项目结构

```
HighFold_C2C/
├── alphafold/              # AlphaFold 核心代码（含 CycPOEM 修改）
├── colabfold/              # ColabFold v1.5.5（含 CycPOEM 计算 + --disulfide-bond-pairs）
│   ├── cycpoem.py          # CycPOEM 算法（独立模块）
│   ├── batch.py            # 主入口（注入 CycPOEM）
│   ├── input.py            # 输入解析（v1.5.5 新增）
│   └── relax.py            # 结构松弛（v1.5.5 新增）
├── utils/                  # CycPOEM 构建、二硫键组合、评估工具
├── c2c/                    # C2C T5 模型：环肽序列生成
│   ├── model.py            # T5 模型定义、CharTokenizer、模型加载
│   ├── generate.py         # 序列生成（贪心 + 采样）
│   ├── evaluate.py         # 理化性质 + pLDDT 评分
│   └── config.py           # 默认配置常量
├── scripts/                # CLI 入口（原始用法）
│   ├── run_pipeline.py     # 完整 3 阶段流水线
│   └── run_predict_only.py # 仅结构预测
├── src/highfold_c2c/       # ★ 微服务层（新增）
│   ├── app.py              # FastAPI 应用（端口 8003）
│   ├── __main__.py         # CLI：python -m highfold_c2c
│   ├── config/             # 配置、存储配置、日志
│   ├── database/           # PostgreSQL 连接池与任务查询
│   ├── core/               # 流水线封装、任务处理器、异步处理器
│   └── services/storage/   # SeaweedFS 异步客户端
├── database/               # SQL 迁移脚本
│   └── init_highfold_tables.sql
├── docker/                 # Docker 部署文件
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   └── docker-manage.sh
├── tests/                  # 单元测试（pytest）
├── checkpoints/            # 模型权重目录（c2c_model.pt）
└── HighFold_data/          # 数据集
```

## 安装指南

### 前置条件

- Linux 系统，配备 NVIDIA GPU（CUDA 12.x）
- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) 或 [Mamba](https://mamba.readthedocs.io/)

### 步骤 1：安装 LocalColabFold

参考 [LocalColabFold](https://github.com/YoshitakaMo/localcolabfold) 官方说明：

```bash
cd localcolabfold
pixi install && pixi run setup
```

### 步骤 2：安装 HighFold 覆盖层

将修改后的 AlphaFold 和 ColabFold 源文件复制到 LocalColabFold 安装目录：

```bash
SITE_PACKAGES="path/to/localcolabfold/.pixi/envs/default/lib/python3.12/site-packages"
cp -r HighFold_C2C/alphafold/* "$SITE_PACKAGES/alphafold/"
cp -r HighFold_C2C/colabfold/* "$SITE_PACKAGES/colabfold/"
```

### 步骤 3：创建 C2C 环境

```bash
cd HighFold_C2C
conda env create -f environment.yml
conda activate highfold_c2c
```

### 步骤 4：安装 Python 包（微服务模式需要）

```bash
# 以开发模式安装
pip install -e ".[dev]"
```

### 步骤 5：下载 C2C 模型权重

将 `c2c_model.pt` 文件放入 `checkpoints/` 目录：

```bash
# 从项目维护者处获取 c2c_model.pt
cp /path/to/c2c_model.pt checkpoints/
```

### 步骤 6：确保 `colabfold_batch` 在 PATH 中

```bash
export PATH="path/to/localcolabfold/.pixi/envs/default/bin:$PATH"
# 验证
which colabfold_batch
```

## CLI 用法

### 完整流水线（推荐）

一条命令运行全部三个阶段——序列生成、结构预测和评估：

```bash
conda activate highfold_c2c

python -m scripts.run_pipeline \
    --core NNN \
    --span-len 5 \
    --num-sample 20 \
    --output-dir ./output
```

执行流程：
1. **阶段 1**：生成 20 条环肽序列（1 条贪心 + 19 条采样），在核心序列 `NNN` 基础上延伸 5 个残基
2. **阶段 2**：使用 HighFold/AlphaFold2 预测所有候选序列的 3D 结构
3. **阶段 3**：计算理化性质和 pLDDT 评分，输出 `output.csv`

### 带二硫键的用法

```bash
python -m scripts.run_pipeline \
    --core CNNNC \
    --span-len 5 \
    --num-sample 20 \
    --disulfide-bond-pairs "0,4" \
    --output-dir ./output
```

### 跳过阶段

```bash
# 仅生成序列（不进行结构预测）
python -m scripts.run_pipeline \
    --core NNN --span-len 5 --skip-predict

# 从现有 FASTA 预测（跳过 C2C 生成）
python -m scripts.run_pipeline \
    --skip-generate --fasta-input my_sequences.fasta --output-dir ./output
```

### 仅结构预测（原始 HighFold 用法）

仅需要结构预测的用户（向后兼容 HighFold）：

```bash
python -m scripts.run_predict_only \
    input.fasta ./output/ \
    --model-type alphafold2 \
    --msa-mode single_sequence \
    --disulfide-bond-pairs "1,4"
```

或直接使用 `colabfold_batch`：

```bash
colabfold_batch --model-type alphafold2 --msa-mode single_sequence \
    --disulfide-bond-pairs "1,4" input.fasta output/
```

### 流水线参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--core` | （必填） | 核心肽段序列 |
| `--span-len` | 5 | 延伸残基数量 |
| `--num-sample` | 20 | 候选序列总数 |
| `--checkpoint` | `checkpoints/c2c_model.pt` | C2C 模型权重路径 |
| `--temperature` | 1.0 | 采样温度 |
| `--top-p` | 0.9 | Nucleus 采样阈值 |
| `--output-dir` | `./output` | 输出目录 |
| `--model-type` | `alphafold2` | AlphaFold 模型类型（`alphafold2`、`alphafold2_ptm`、`alphafold2_multimer_v1/v2/v3`、`deepfold_v1`） |
| `--msa-mode` | `single_sequence` | MSA 模式 |
| `--disulfide-bond-pairs` | 无 | 二硫键位置（格式：`"A,B"` 或 `"A,B:C,D"`，0-based） |
| `--num-models` | 5 | AlphaFold 模型数量 |
| `--colabfold-bin` | `colabfold_batch` | colabfold_batch 可执行文件路径 |

## 输出文件

运行完整流水线后，`output/` 目录包含：

| 文件 | 说明 |
|------|------|
| `predict.fasta` | 生成的环肽序列 |
| `pep*_unrelaxed_*.pdb` | 预测的 3D 结构 |
| `pep*_scores_*.json` | 逐残基 pLDDT 评分 |
| `output.csv` | 汇总：序列、pLDDT、分子量、等电点、芳香性、不稳定指数、疏水性、亲水性 |

## 微服务模式

### 概述

HighFold-C2C 可以作为后台微服务运行，自动轮询 PostgreSQL 任务队列并处理任务。此模式专为与 **AstraMolecula** 平台集成而设计。

**架构：**
- **FastAPI** 服务器（端口 8003）—— 健康检查、任务状态查询、结果下载
- **后台轮询** —— 每 180 秒检查数据库中的 `pending` 状态任务
- **SeaweedFS** 对象存储 —— 统一管理输入/输出文件
- **多 Worker** —— `ThreadPoolExecutor` 支持并发任务处理

### 快速启动（服务模式）

```bash
# 1. 复制并配置环境变量
cp .env.example .env
# 编辑 .env，填入数据库和 SeaweedFS 配置

# 2. 启动服务
python -m highfold_c2c --host 0.0.0.0 --port 8003

# 或使用入口点命令
highfold-c2c-server --host 0.0.0.0 --port 8003
```

### API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |
| GET | `/status` | 服务状态（活跃任务数、运行时间） |
| GET | `/results/{task_id}` | 获取任务结果（JSON） |
| GET | `/results/{task_id}/csv` | 下载 output.csv |
| GET | `/structures/{task_id}/{filename}` | 下载 PDB 结构文件 |
| GET | `/sequences/{task_id}` | 获取生成的序列 |

### 任务工作流

1. 外部系统（如 AstraMolecula）在 `tasks` 表中插入一行记录，`task_type='highfold_c2c'`、`status='pending'`，并在 `highfold_task_params` 表中写入参数
2. 后台 Worker 捡起任务，从 SeaweedFS 下载输入文件
3. 运行 3 阶段流水线（C2C 生成 → ColabFold 预测 → 评估打分）
4. 将结果上传至 SeaweedFS，更新任务状态为 `completed` 或 `failed`

### 数据库表

服务使用 AstraMolecula 共享的 `tasks` 表，加上专用的参数表：

```sql
-- 参数表（详见 database/init_highfold_tables.sql）
CREATE TABLE highfold_task_params (
    task_id       INTEGER PRIMARY KEY REFERENCES tasks(id),
    core_sequence VARCHAR(100) NOT NULL,   -- 核心肽段序列
    span_len      INTEGER DEFAULT 5,       -- 延伸长度
    num_sample    INTEGER DEFAULT 20,      -- 采样数量
    temperature   FLOAT DEFAULT 1.0,       -- 采样温度
    top_p         FLOAT DEFAULT 0.9,       -- Nucleus 采样阈值
    model_type    VARCHAR(50) DEFAULT 'alphafold2',
    disulfide_bond_pairs TEXT,             -- 二硫键对
    ...
);
```

### Docker 部署

> **说明：** Docker 部署仅包含 **HighFold-C2C 应用容器**。
> 它连接到 **宿主机上已运行的外部服务**：
> - **PostgreSQL**（默认：宿主机端口 5432）
> - **SeaweedFS**（默认：宿主机端口 8888）
>
> 启动容器前请确保这些服务已在运行。

#### 前置条件

1. Docker 并安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) 以支持 GPU
2. 宿主机上运行 PostgreSQL（与 AstraMolecula 平台共享）
3. 宿主机上运行 SeaweedFS（与 AstraMolecula 平台共享）
4. 将 `c2c_model.pt` 放入 `checkpoints/` 目录

#### 快速启动

```bash
cd docker

# 1. 配置环境变量（Docker 模式下使用 host.docker.internal）
cp ../.env.example ../.env
# 按需编辑 ../.env（默认已配置连接宿主机服务）

# 2. 初始化数据库表（仅首次需要）
./docker-manage.sh init-db

# 3. 构建镜像
./docker-manage.sh build

# 4. 启动应用
./docker-manage.sh up

# 查看日志
./docker-manage.sh logs --follow

# 开发模式（热重载 + 源码挂载）
./docker-manage.sh up --dev

# 停止服务
./docker-manage.sh down
```

#### 手动 Docker Compose 命令

```bash
cd docker

# 构建
docker compose --env-file ../.env build app

# 启动
docker compose --env-file ../.env up -d app

# 日志
docker compose --env-file ../.env logs -f

# 停止
docker compose --env-file ../.env down
```

### 环境变量

详见 [.env.example](.env.example)。主要配置项：

| 变量 | 默认值（Docker） | 说明 |
|------|------------------|------|
| `DB_HOST` | `host.docker.internal` | PostgreSQL 主机地址（非 Docker 模式使用 `127.0.0.1`） |
| `DB_PORT` | `5432` | PostgreSQL 端口 |
| `DB_NAME` | `mydatabase` | 数据库名称 |
| `SEAWEED_FILER_ENDPOINT` | `http://host.docker.internal:8888` | SeaweedFS Filer 地址（非 Docker 模式使用 `http://localhost:8888`） |
| `SEAWEED_BUCKET` | `astramolecula` | 存储桶名称 |
| `TASK_QUERY_INTERVAL` | `180` | 轮询间隔（秒） |
| `MAX_CONCURRENT_TASKS` | `2` | 最大并发任务数 |
| `C2C_CHECKPOINT_PATH` | `checkpoints/c2c_model.pt` | 模型权重路径 |
| `COLABFOLD_BIN` | `colabfold_batch` | colabfold_batch 可执行文件路径 |

## 序列约束

- 环肽总长度应 ≤ 20 个氨基酸（训练数据范围）
- 核心序列长度应 ≥ 总长度的 30%
- 示例：核心 3 aa + 延伸 7 aa = 总共 10 aa（有效）
- 反例：核心 1 aa + 延伸 10 aa = 总共 11 aa（核心比例 9%，过低）

## 引用

如果使用了 HighFold，请引用：

> HighFold: accurately predicting structures of cyclic peptides and complexes with head-to-tail and disulfide bridge constraints

## 测试

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全部测试
python -m pytest tests/ -v

# 运行指定测试模块
python -m pytest tests/test_pipeline.py -v
python -m pytest tests/test_storage.py -v
python -m pytest tests/test_task_processor.py -v
```

## 文档

- [ColabFold v1.5.5 迁移详情](docs/colabfold-migration.md) — CycPOEM 适配新版 ColabFold 的详细说明
- [合并计划](merge-plan.md) — 原始 C2C + HighFold 合并设计文档
- [.env.example](.env.example) — 微服务配置所有环境变量
- [数据库迁移脚本](database/init_highfold_tables.sql) — 建表 SQL
- [English Documentation](README.md) — 英文文档

## 许可证

详见 [LICENSE](LICENSE)。
