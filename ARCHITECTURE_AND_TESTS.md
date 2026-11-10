# Lumerical RAG + 兼容层 —— 架构与测试全记录

> 2026-11-11 定稿。机器角色:102(Debian,常驻服务)= 唯一服务;校机(Windows + Lumerical v241)= 数据处理 + 验证环境;笔记本 = 使用端。
> 全程约束:不新增进程/端口;不推翻既有 RAG;无 sudo(全部用户级 systemd);Qdrant 禁量化/禁 HNSW(102 的 Celeron 无 AVX,量化会 SIGILL)。

---

## 1. 系统架构

```
              使用者(笔记本 dsh / 校机 dsh / CLI / REST)
                        │ 唯一对外 MCP 面
                        ▼
        ③ rag-mcp   0.0.0.0:8901/mcp   (FastMCP, mcp>=1.2,<2)
            5 tools:
              search_lumerical_docs(query, top_k, collection, doc_type)
              get_document(url, collection, max_chars)
              list_collections()
              lookup_lumerical_compatibility(feature, target_version, product, solver, target_id)
              get_lumerical_compat_recipe(implementation_id)
                        │ 回环 REST(Bearer)
                        ▼
        ② rag-shim  0.0.0.0:8900       (FastAPI + uvicorn, Bearer token)
            ├── 检索:SiliconFlow bge-m3(1024维)→ Qdrant top50 + Tantivy BM25 top50
            │        → 元数据过滤(collection/doc_type/version)→ RRF(k=60) → top20
            │        → SiliconFlow bge-reranker-v2-m3(输入=面包屑+类型标签+正文)
            ├── 文档:get_document(url=)/_fetch_doc_by_doc_id(稳定ID,LSF/配方整篇不切分)
            ├── 入库:POST /ingest(批量48,400自动拆单+截断)+ POST /admin/rebuild-bm25(全库重建)
            └── 兼容层:shim/compat/{schema.sql,db.py,repo.py,api.py}
                GET /compat/lookup    (feature, target_id | target_version, product, solver, update)
                GET /compat/recipe    (implementation_id 优先;feature+target_version 兜底)
                GET /compat/capabilities  (target_id, symbols → 逐事实 provenance)
                        │
        ┌───────┴────────────────┐
        ▼                        ▼
① rag-qdrant               compatibility.db (SQLite,kit 10表 schema v1)
127.0.0.1:6333/6334        由 shim 进程内打开(foreign_keys=ON, busy_timeout, WAL, thread-local)
用户级 systemd
Linger=yes
```

### 1.1 数据分布(Qdrant 4 集合,合计 16418 块)

| 集合 | 块数 | 内容 | doc_type |
|---|---|---|---|
| `lumerical` | 14469 | optics.ansys.com 最新 KB(2962 篇)+ 167 个 .lsf 示例 + 2012 社区 Q 分析脚本(community_example) | command/tutorial/community_example |
| `lumerical_v241` | 743 | 校机 v241 自带 docs.json(665 命令权威语法) | command (version=v241) |
| `lumerical_compat` | 4 | 自研兼容资产(整篇不切分:recipe.md + 完整 LSF) | compatibility_recipe |
| `fdtdx` | 1202 | 开源 fdtdx:RTD 166 页 + 9 examples + 白皮书 + 581 API docstring(WSL 抽取) | api/page |

### 1.2 SQLite 注册表(kit `schema/compatibility.sql`,v1)

| 表 | 行数 | 内容 |
|---|---|---|
| target_environments | 2 | `lumerical-2024r1-install`(文档推导)+ `lumerical-2024r1-school-capture`(运行时实测,build 8.31.3633) |
| features | 790 | v241 docs.json ∪ 最新 KB 命令页 ∪ 语言构造(function/while…)+ seed 10 条 |
| feature_availability | 741 | 逐 target 的 native/absent/unknown,**每行带 evidence_basis(getcommands/syntax_probe/official_docs/multiple)与 snapshot_id** |
| evidence_sources | 14 | docs.json、KB 语料、9 个官方 release note、运行时快照 |
| capability_snapshots / capability_items | 1 / 615 | 校机采集:606 个 getcommands 符号 + 11 条语法探针(哈希存档) |
| implementations / implementation_dependencies | 4 / 24 | median(exact/L2)、resonance_fwhm(approximate/L2)、adddftmonitor(domain_equivalent/L2)、reportmeshstatistics(partial/L2) |
| validation_runs | 8 | 全部验证轨迹:静态/运行时/differential,passed 与 **blocked** 都留档 |
| document_refs | 4 | 配方 ↔ Qdrant 点(ID 通过 `meta.doc_id` 稳定关联,取回不走文件路径) |

### 1.3 客户端接线

- 笔记本 dsh:magpie `library.json` 登记 `lumerical-rag` → `http://RAG_HOST:8901/mcp` → `mcp__lumerical-rag__*`
- 校机 dsh:`cordis.patch.yml` 同 URL(备份 `…bak-lumericalrag-20261110-102446`)
- CLI:`rag-query.ps1 "…" -Collection lumerical|fdtdx|lumerical_v241|lumerical_compat`
- 裸 REST:`GET :8900/search?q=&collection=&doc_type=` + `Authorization: Bearer <token>`(token 在 102 `~/.config/rag/rag.env` 600 / 笔记本 `%USERPROFILE%\.rag\token`)

---

## 2. 兼容层方法论(为什么这样设计)

三个问题分开回答,不互相冒充:
1. **这个功能是什么** → features.description(来自官方文档,带链接)
2. **目标环境原生有没有** → feature_availability(证据分档:runtime getcommands > syntax_probe > official_docs;**文档缺失 ≠ 运行时缺席**,这是本次最重要的方法论修正)
3. **没有的话有没有可用的替代** → implementations(equivalence: exact/domain_equivalent/approximate/partial/unsupported × verification_level L0-L4,两轴独立;缺证据一律 `unknown` + `required_next_evidence`,**从不编造**)

四类实现不混装(SOP 规定):语法翻译 / API 适配 / 算法回移植 / 近似替代(必须改名,如 `resonance_fwhm` 而非 `findresonances_v241`)。

## 3. 已完成的验证(全部有 raw 输出存档)

### 3.1 能力快照(校机实测,2026-11-10)
- lumapi FDTD 隐藏会话(build 8.31.3633):`?getcommands;` → **606 符号**;11 条语法探针逐条隔离 feval
- 结论:`function/while/elseif/switch/continue` **真缺席**(纯语法错);`sort` 原生在
- 606 清单 × KB-only 120 交叉核对:**68 条是文档缺口(原生存在)**,52 条真缺席
  (分类:A 其他求解器物理 17 / B 有 FDTD 适配路径 16 / C 语言构造 5 / D 工具链 14 → `compat/absent_commands_inventory.md`)

### 3.2 四资产 L2 验证(校机 lumapi 会话)

| 资产 | 等价 | 验证 | 结果 |
|---|---|---|---|
| `compat.median.sort.v241.exact` | **exact** | L2 | 5/5 fixture **零容差全过**([1,2,4]→2,[1,2,3,4]→2.5,[7]→7,[-3,5,-1]→-1,[1.5,2.5,3.5,4.5]→3.0);干净会话重探再次通过 |
| `compat.resonance_fwhm.v241.fwhm` | approximate(workaround) | L2(限声明域) | **R1 解析真值** rel err 1.16e-6(预声明容差 1.23e-3);**R3 原生差分** gap 2.5e-7 |
| `compat.adddftmonitor.v241.adapter` | domain_equivalent | L2 | fpcavity 实测:监视器建成、命名、run 后 Ex/Ey/Ez 场数据齐全(71 空间×5 频点) |
| `compat.reportmeshstatistics_v241.adapter` | partial | L2 | **关键发现**:FDTD 对象的 nx/ny/nz/dx/dy/dz 是 mesh-override 参数(默认 1/1e-7),真网格在 `mesh cells x/y/z`(267×132×47=1.66M);步长=span/cells |

### 3.3 L3 实测差分(2026-11-11,真实 FDTD 全流程)
- 自建 DBR 法布里-珀罗腔:`fpcavity.fsp`(2D FDTD,Si/SiO₂ 4 对 1/4 波镜 + 1.5λ 腔,偶极子宽带脉冲,13.5 ps 环 down,49988 点,early shutoff 关闭)
- **主峰 267.366 THz(1121.3 nm):原生 Q=636.71(err 1.2e-9)vs 配方 Q=636.72 → gap 2.4e-5**
- 附带教训(已写进 recipe/limitations):v241 属性名 `simulation time`;新建对象默认名 dipole→`source`、time monitor→`monitor`;环 down 必须脉冲后截取;early shutoff 会砍长仿真
- R2(2012 斜率法差分):斜率法 Q=499.83(rel 3.4e-4)vs FWHM 5.3e-7,两法 gap 3.4e-4;LSF `fftw` 是双边轴(0→1/dt),独立 LSF 移植易错——原脚本依赖 analysis group 上下文

### 3.4 json* 九件套
`jsonload/jsonloads/jsonread/jsonreads/jsonsave/jsonsaves/jsonvalidate/jsonwrite/jsonwrites` 全部运行时原生存在(getcommands),`jsonwrite→jsonload` 往返逐字段相等——**无需配方**。

### 3.5 测试套件
- `tests/test_compat_registry.py`(9):schema 幂等迁移、FK 约束、CHECK 约束、按名/别名解析、**无可用性行=unknown 而非 absent**、精确版本匹配(v241≠2024 R1)、等价排序、依赖边
- `tests/test_compat_api.py`(7):Bearer 鉴权(401/403)、缺参 400、未知 feature/target 404(附"缺席≠证据"提示)、精确匹配、capabilities 无快照、未知 impl 404
- **16/16 通过**;TestClient + 临时库,不碰 102
- `verify_all.py`(12):全量核验,**12/12 PASS**(本地文件 29 项 / 注册表计数 / 测试套件 / shim 健康 / 集合计数 / lookup×3 / ambiguous 400 / capabilities provenance / 配方全文+验证轨迹 / 检索命中 compat 文档 0.937)

## 4. 部署/迁移/回滚

- **部署**:`scp shim/app.py shim/mcp_server.py shim/compat/* compat/compatibility.db → 102` → `sed -i 's/\r$//'` → `systemctl --user restart rag-shim rag-mcp`
- **迁移**:schema 全 `CREATE IF NOT EXISTS`;重跑 `build_compat_registry.py` / `build_compat_assets.py` 等价幂等;快照导入 `import_capability_snapshot.py`(幂等+哈希校验)
- **回滚**:`compat/backups/<ts>/` 覆盖回原位重启两服务;`lumerical_compat` 集合可整删不伤其他三个集合
- **资源**:三服务内存 shim 43MB / mcp 49MB / Qdrant ~700M 上限;查询 ~0.8s
- **凭据**:RAG_TOKEN + SiliconFlow key 只在 102 `~/.config/rag/rag.env`(600);代码/测试零硬编码

## 5. 文件地图(rag-102/)

```
PLAN.md                    真相源(§0-§10)
COMPAT_INTEGRATION_MAP.md  Phase 0 集成点图
verify_all.py              12 项全量核验(可重复执行)
shim/{app.py,mcp_server.py,compat/,requirements.txt}
shim/data/compatibility.db (102 上的部署副本)
compat/
  schema/(kit 原版)  assets/{median_sort_v241, resonance_fwhm_v241, adddftmonitor_v241, reportmeshstatistics_v241}/
  community/Qanalysis-analysis_script.lsf(2012 官方社区参照)
  runtime_crosscheck.json  absent_commands_inventory.md  backups/<ts>/
capabilities/snapshots/lumerical-2024r1-school-20261110/(606 符号+探针+哈希)
capabilities/capture-kit/(校机采集工具包)
corpus/{zendesk,lumerical_v241,fdtdx,compat}/  _kit/(原版 kit)
tests/{test_compat_registry.py, test_compat_api.py}
build_compat_registry.py  build_compat_assets.py  import_capability_snapshot.py
ingest_community_qanalysis.py  build_compat_db.py(旧实验,归档)
```

## 6. 边界与遗留(诚实)

- 无许可证环境的机器上永远拿不到 L2+;所有运行态结论都注明采集环境
- `lumerical_compat` 只有 4 篇资产;52 条真缺席里 40+ 条"原理上不可移植"(其他求解器物理/工具链),剩余未做的适配约 11 条(B 类里 INTERCONNECT 域为主,无需求)
- `json*` 等原生命令只验证了存在性+签名抽样,未逐条语义差分(官方语义即定义,价值有限)
- R2 斜率法的纯 LSF 独立移植未完成(fftw 双边轴坑),差分用同算法数值实现完成;原脚本仍是参照
- 校机 `lumcap/` 工作区保留(采集证据+L3 工程),<外部工程目录>/<外部工程目录> 只读探测过,时间戳核验未动
