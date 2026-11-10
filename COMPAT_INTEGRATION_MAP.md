# Phase 0 — 侦察与集成点(不改变任何行为)

> 依据 `tasks/PHASE_PLAN.md` Phase 0。本文件只记录现状与最小改动点;**此阶段未改代码**。

## 1. 现有部署(实测基线,2026-11-10)

| 项 | 值 |
|---|---|
| 进程/端口 | `rag-qdrant` 127.0.0.1:6333/6334 · `rag-shim` 0.0.0.0:8900 · `rag-mcp` 0.0.0.0:8901 `/mcp` |
| 用户级 systemd | 102 `~/.config/systemd/user/{rag-qdrant,rag-shim,rag-mcp}.service`,`Linger=yes` |
| 集合 | `lumerical` 14468 · `lumerical_v241` 743 · `fdtdx` 1202 · `lumerical_compat` 3(本 kit 的前置实验) |
| BM25 | 单一 tantivy 索引,`bm25_docs=16416`,按 payload `collection` 分区 |
| Qdrant 设定 | **禁量化、无 HNSW**(`indexing_threshold=1e6`)——Celeron G1610 无 AVX,不可改 |
| embed/rerank | SiliconFlow `bge-m3`(1024) / `bge-reranker-v2-m3` |
| 现有 REST | `/search`(collection,doc_type,version)/`/document?url=`/`/collections`/`/health`/`POST /ingest`/`POST /admin/rebuild-bm25` |
| 现有 MCP 工具 | `search_lumerical_docs` · `get_document` · `list_collections`(+ 本 kit 前置实验的 `lookup_lumerical_compatibility`/`get_lumerical_compat_recipe`,**签名与规范不符,将替换**) |
| 鉴权 | `Authorization: Bearer $RAG_TOKEN`,token 在 102 `~/.config/rag/rag.env`(600) |

## 2. 代码结构(集成点定位)

| 文件 | 作用 | 本 kit 的改动 |
|---|---|---|
| `shim/app.py` | FastAPI:检索、入库、文档、集合、BM25 重建;`_ensure_collection` 建集合(禁量化) | **新增** `compat/` 子模块并挂 3 条路由;`/search` 增加 compat 相关过滤字段 |
| `shim/mcp_server.py` | FastMCP,薄转发到 shim | **替换** 2 个 compat 工具签名(加 `target_version`/`product`/`solver`),保留其余 3 个工具签名 |
| `shim/data/compatibility.db` | 前置实验的 4 表最小库(676KB) | 迁移到 `schema/compatibility.sql`(10 表),旧库备份不删 |
| `corpus/compat/chunks.jsonl` `build_compat_db.py` `v241-recipes/` | 前置实验资产 | 改为 kit 目录布局 + 带完整 metadata 的资产;旧文件归档 |
| `crawl_zendesk.py`/`build_chunks.py`/`build_fdtdx.py`/`build_v241.py`/`ingest.py` | 现有抓取/切块/入库 | **不改**;新增 compat 资产构建脚本复用 `ingest.py` |
| `rag-query.ps1` | CLI | 增加 compat 用法示例(可选) |

## 3. payload 约定(必须延续,不另造键)

现有 chunk payload:`{cid, collection, text, meta:{source, doc_type, version, title, url, breadcrumb, chunk_idx, ...}}`。
compat 资产在此基础上**新增**:`doc_id`、`implementation_id`、`feature_id`、`target_version`、`product`、`solver`、`equivalence`、`verification_level`、`status`、`dependencies`、`preconditions`、`limitations`、`source_type`、`authority`、`source_url`。
`/document` 走 `meta.url`;compat 文档同时写 `meta.doc_id`,以支持按稳定 ID 取回。

## 4. 与规范不符、必须修正的既有做法

1. **"docs.json 里没有" ≠ `absent`** → 现库把未收录直接当"新版才有";新实现:无运行时快照 → `unknown`,并返回 `required_next_evidence`。
2. **名称不得冒充原生命令** → `findresonances_v241` 改名 `resonance_fwhm_v241`(FWHM 法 ≠ 滤波器对角化)。
3. **`sort` 不能标 exact** → 官方语义为"复数按模、再按相位排序;输入按线性数组、输出保持形状",冒泡实现只覆盖实数列 → `partial`。
4. **`modeoverlap` 只能标 partial** → 仅 E 场归一化,缺 E×H 功率归一。
5. **`target_version` 必须精确**(`2024 R1`,而非 `v241`);product/solver 显式,不做模糊升级匹配。
6. **无任意文件路径入参** → `/compat/recipe` 只接受 `implementation_id`(或 feature+target),经 `recipe_doc_id` 走既有检索。
7. **不新增进程/端口/服务**;SQLite 只由 shim 进程打开(foreign_keys=ON、busy_timeout、短事务)。

## 5. 落地顺序(对应 PHASE_PLAN)

| Phase | 产出 | 验收 |
|---|---|---|
| 0(本文件) | 基线 + 集成点 + 备份 | 不改代码 ✅ |
| 1 | `compat/{__init__,db,repo,migrate}.py` + 10 表 schema + 单元测试 | 建库/迁移可重复;`unknown` 默认 |
| 2 | `lumerical_compat` 资产构建(每配方 1 个逻辑文档,LSF 完整)+ 入库 + 全库 BM25 重建 | 4 集合都可检索 |
| 3 | `/compat/lookup`、`/compat/recipe`、`/compat/capabilities`(Bearer) | 参数校验/404/unknown 隔离 |
| 4 | MCP 2 工具(新签名) | 老 3 工具不变 |
| 5 | 能力快照目录 + 导入脚本(哈希入库);无 Lumerical 运行环境 → 快照为空,状态如实 `unknown` | 存在性与"文档缺口"可区分 |
| 6 | 首批资产:`resonance_fwhm_v241`(近似分析)、`sort`/`median` 审计、`overlap/expand` 输入 API 分析 | 至少一个通过静态检查,L1;运行态 pending |
| 7 | 全套测试 + 备份/迁移/部署/回滚文档 | §11 验收 |

## 6. 备份(Phase 0 要求)

`rag-102/compat/backups/<UTC 时间戳>/` 保存:`shim/app.py`、`shim/mcp_server.py`、`shim/data/compatibility.db`(前置实验库)、`corpus/compat/*.jsonl`、`compat/compatibility.db`。
恢复方式:直接覆盖回原位并 `systemctl --user restart rag-shim rag-mcp`;不触碰三个旧集合。

## 7. 已知风险 / 待决

- **无 Lumerical 运行/许可环境** → 无法产出 `?getcommands` 快照,`L2+` 一律 pending;本机不发明运行时证据。
- 校机有 v241 安装但需要许可与 GUI 交互,是否要采集快照需另行批准(采集脚本会写在 `capabilities/` 但默认不执行)。
- `lumerical_compat` 现有 3 条前置实验数据将被新资产取代(先备份,删点按 `meta.doc_type=recipe` 精确过滤)。
