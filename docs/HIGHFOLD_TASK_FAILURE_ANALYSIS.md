# HighFold-C2C 任务失败分析报告

**日期**: 2026-03-04

---

## 概述

用户提交的两个 HighFold-C2C 任务均执行失败，失败原因相同：Docker 容器内缺少 `colabfold_batch` 可执行文件。

---

## 失败任务详情

### 任务 1

| 字段 | 值 |
|------|-----|
| Task ID | `35d4b931-1d4d-45d7-ab0e-1456e60c5ce7` |
| User ID | `9237b584-d93b-4e5a-9f5b-86eda473b843` |
| Core Sequence | `MNFGA` |
| 创建时间 | 2026-03-04 13:01:49 |
| 开始时间 | 2026-03-04 13:03:52 |
| 失败时间 | 2026-03-04 13:03:55 |
| Stage 1 (C2C 生成) | ✅ 成功，生成 20 条序列 |
| Stage 2 (结构预测) | ❌ 失败 |

**错误日志**:
```
2026-03-04 13:03:55 [ERROR] highfold_c2c.core.task_processor: Task 35d4b931-1d4d-45d7-ab0e-1456e60c5ce7 failed: 'colabfold_batch' not found on PATH. Install LocalColabFold and add it to PATH.
```

### 任务 2

| 字段 | 值 |
|------|-----|
| Task ID | `176cc359-9838-423a-afb3-445becd93836` |
| User ID | `9237b584-d93b-4e5a-9f5b-86eda473b843` |
| Core Sequence | `CNNNC` |
| 创建时间 | 2026-03-04 13:05:13 |
| 开始时间 | 2026-03-04 13:06:55 |
| 失败时间 | 2026-03-04 13:06:55 |
| Stage 1 (C2C 生成) | ✅ 成功，生成 20 条序列 |
| Stage 2 (结构预测) | ❌ 失败 |

**错误日志**:
```
2026-03-04 13:06:55 [ERROR] highfold_c2c.core.task_processor: Task 176cc359-9838-423a-afb3-445becd93836 failed: 'colabfold_batch' not found on PATH. Install LocalColabFold and add it to PATH.
```

---

## 根因分析

两个任务均在 **Stage 2（HighFold 结构预测）** 阶段失败。

Pipeline 在 `src/highfold_c2c/core/pipeline.py` 的 Stage 2 中执行以下检查：

```python
colabfold_bin = config.get("colabfold_bin", "colabfold_batch")
if shutil.which(colabfold_bin) is None:
    raise FileNotFoundError(
        f"'{colabfold_bin}' not found on PATH. "
        "Install LocalColabFold and add it to PATH."
    )
```

`shutil.which("colabfold_batch")` 返回 `None`，说明 Docker 容器 `docker-app-1` 内：

1. **未安装 LocalColabFold**，或
2. 已安装但 `colabfold_batch` **未加入 `PATH` 环境变量**

当前 `.env` 配置：
```
COLABFOLD_BIN=colabfold_batch
```

该值仅是命令名而非绝对路径，依赖 `PATH` 来定位可执行文件。

---

## 解决方案

### 方案 1：在 Dockerfile 中安装 LocalColabFold（推荐）

在 `docker/Dockerfile` 中添加 LocalColabFold 安装步骤，确保 `colabfold_batch` 被正确安装到容器中并加入 `PATH`。

### 方案 2：挂载宿主机 ColabFold

如果宿主机已安装 LocalColabFold，可通过 Docker Volume 挂载：

```yaml
# docker-compose.yml
volumes:
  - /path/to/localcolabfold/colabfold-conda/bin:/opt/colabfold/bin
```

并修改 `.env`：
```
COLABFOLD_BIN=/opt/colabfold/bin/colabfold_batch
```

### 方案 3：临时修改 PATH

进入容器验证：
```bash
sudo docker exec -it docker-app-1 bash
which colabfold_batch   # 确认是否存在
echo $PATH              # 检查 PATH 配置
```

---

## 任务参数参考

两个任务使用的参数（除 `core_sequence` 外完全一致）：

| 参数 | 值 |
|------|-----|
| span_len | 5 |
| num_sample | 20 |
| temperature | 1.00 |
| top_p | 0.90 |
| seed | 42 |
| model_type | alphafold2 |
| msa_mode | single_sequence |
| num_models | 5 |
| amber | false |
| skip_generate | false |
| skip_predict | false |
| skip_evaluate | false |
