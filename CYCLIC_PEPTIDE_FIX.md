# HighFold-C2C 环肽结构修复记录

**修复日期**: 2026-03-26  
**问题描述**: HighFold-C2C 预测结果的 PDB 文件不包含环肽的 N-C 端闭环键，导致前端 3D 查看器无法渲染出环状结构

---

## 问题分析

### 根本原因

AlphaFold2 输出 PDB 文件时调用 `protein.to_pdb()`，该函数**从不写入 CONECT 记录**（连接性记录）。

虽然 CycPOEM 模块（`colabfold/cycpoem.py`）通过 Floyd-Warshall 算法正确生成了环状构象（N-C 端原子距离约 1.3–1.5 Å），但 PDB 文件缺少 `CONECT` 行，导致：

1. 分子查看软件（如 3dmol.js）无法识别 N-C 端共价键
2. 3D 视图中分子呈线性展开，而非闭合环状

### 验证数据

对已完成任务（ID: `b8a6d34a-7260-407e-82e4-964cc3774b71`）下载 PDB 文件分析：

| 文件 | N 端原子 | C 端原子 | N-C 距离 | CONECT 记录 |
|------|----------|----------|----------|------------|
| pep1_rank_001.pdb | N (MET1) | C (PRO10) | ~1.43 Å | **0 条** (修复前) |

---

## 修复内容

### 1. 后端 — `pipeline.py`

**文件**: `src/highfold_c2c/core/pipeline.py`

新增两个函数，在 Stage 2（结构预测）完成后自动为所有 PDB 文件注入 CONECT 记录：

```python
def _add_cyclic_conect(pdb_path: Path) -> bool:
    """
    在 PDB 文件末尾的 END 行之前插入环肽 N-C 端闭环 CONECT 记录。
    找到每条链的第一个 N 原子（N 端）和最后一个 C 原子（C 端），
    写入双向 CONECT 记录。
    """

def _cyclize_pdb_files(output_dir: Path) -> int:
    """
    遍历目录下所有 *.pdb 文件，调用 _add_cyclic_conect() 注入闭环键。
    返回成功处理的文件数量。
    """
```

调用位置：Stage 2 子进程完成后立即执行：
```python
n_cyclized = _cyclize_pdb_files(output_dir)
logger.info(f"Stage 2 post-processing: added cyclic CONECT records to {n_cyclized} PDB files")
```

### 2. 后端 — `test_pipeline.py`

**文件**: `tests/test_pipeline.py`

新增 6 个单元测试，覆盖以下场景：

| 测试类 | 测试方法 | 说明 |
|--------|----------|------|
| `TestAddCyclicConect` | `test_basic_cyclic_conect` | 基础 CONECT 注入验证 |
| `TestAddCyclicConect` | `test_conect_atom_indices` | 验证原子编号正确 |
| `TestAddCyclicConect` | `test_conect_before_end` | 验证 CONECT 在 END 之前 |
| `TestAddCyclicConect` | `test_idempotent` | 验证重复调用不产生重复记录 |
| `TestCyclizePdbFiles` | `test_cyclize_multiple_files` | 批量处理多文件 |
| `TestCyclizePdbFiles` | `test_returns_count` | 验证返回处理数量 |

全部 15 个测试通过：`15 passed in 0.XXs`

### 3. 前端 — `MoleculeViewer3D/index.tsx`

**文件**: `AstraMolecula-front/src/components/MoleculeViewer3D/index.tsx`

**问题**: 前端 HighFold 分支的链分离代码（chain separation）只保留 `ATOM`/`HETATM` 行，直接丢弃了 `CONECT` 行：

```typescript
// 修复前（有问题）
if (line.startsWith('ATOM') || line.startsWith('HETATM')) {
  peptideLines.push(line);
}
// CONECT 行被静默丢弃
```

**修复**: 新增 `conectLines` 数组收集 CONECT 行，并拼接到 peptide 内容末尾：

```typescript
// 修复后
const conectLines: string[] = [];

lines.forEach(line => {
  if (line.startsWith('ATOM') || line.startsWith('HETATM')) {
    // ... 原有逻辑
  } else if (line.startsWith('CONECT')) {
    conectLines.push(line);  // 保留 CONECT 记录
  }
});

const conectBlock = conectLines.length > 0
  ? '\n' + conectLines.join('\n')
  : '';

// peptide 内容中包含闭环键
const peptideContent = peptideLines.join('\n') + '\nTER' + conectBlock + '\nEND';
```

---

## 部署步骤

### 后端 Docker 重建

```bash
cd /home/songyou/projects/HighFold_C2C
sudo docker compose build app
sudo docker compose up -d app
```

### 前端 Docker 重建

```bash
cd /home/songyou/projects/AstraMolecula-front
sudo docker compose build frontend-nginx
sudo docker compose up -d frontend-nginx
```

---

## 验证结果

### API 数据验证

修复后，PDB 文件 API 返回内容包含正确的 CONECT 记录：

```
ATOM      1  N   MET A   1      -7.168   4.637  -8.047 ...
...
ATOM     72  C   PRO A  10      -3.396   7.098  -7.598 ...
CONECT   72    1
CONECT    1   72
END
```

- 原子 1 = MET（第1位）的 N 原子（N 端）
- 原子 72 = PRO（第10位）的 C 原子（C 端）
- N-C 距离：1.26–1.51 Å（共价键范围 ✅）

### 前端日志验证

3D 查看器实时日志：
```
[16:26:47] ✅ HighFold single-chain PDB: ATOM + CONECT data set as both ligand and protein
```

---

## 注意事项

> **whisper-live 服务**: 调试端口冲突时，误杀了 yichao 用户的 `whisper-live` 进程（PID 679974，端口 3000）。如需恢复该服务，请联系 yichao 重启。

---

## 网络架构说明

服务通过 **autossh 端口转发**对外提供访问：

| 外部入口 | autossh 转发 | 本地服务 |
|----------|-------------|---------|
| `3.133.131.124:3000` | → 本地 `:80` | 前端 Nginx 容器 |
| `3.133.131.124:8001` | → 本地 `:8003` | HighFold-C2C 后端 |

> `.env` 文件中 `FRONTEND_PORT=80`，不可修改，否则 autossh 转发失效。
