# RAG-102 部署计划(v1,执行中)

> 决策来源:2026-11-10 会话裁决 —— 校机永不当服务器(只做一次性解析);102 常驻服务;
> embedding/rerank 走 SiliconFlow 云 API;笔记本+校机为最终使用者;RAGFlow 整体放弃。
>
> **执行状态**
> - ✅ Phase 1 完成(2026-11-10 08:07):Qdrant 1.20.0,**用户级** systemd 已 active,
>   `healthz check passed`,`/collections` 返回空,监听 127.0.0.1:6333/6334,RSS 33MB(峰值 17MB cgroup)。
> - ⚠️ 部署方式由「系统级(/opt + /etc + sudo + swap)」改为**用户级**(见 §2/§3):
>   102 的 sudo 需交互密码,且 `Linger=yes` 已开 → 用户级服务开机自启、无需登录,等价常驻。
>   代价:**+2G swap 加不了**(swapon 需 root)。Qdrant/shim 均有 MemoryMax 兜底,风险低。
> - ✅ Phase 2 完成(08:09):rag-shim active,`/health` ok,端到端 ingest→search 冒烟通过。
> - ✅ Phase 3 完成(08:35):抓 optics.ansys.com **2485 篇** → 切块 **13152 块**(12792 KB + 360 .lsf 片),
>   全量入库,**零失败**,BM25 对齐 13152;重启后数据仍在、查询正常。
> - ✅ Phase 4 完成(部分):`rag-query.ps1` 单文件查询器(延迟 ~0.74s);A/B 见 §6。
> - ✅ Phase 5 完成:MCP 服务(`rag-mcp` :8901)已接 magpie(`library.json` 登记 `lumerical-rag`)→ dsh。
> - ✅ **扩库完成**(08:5x):加入 Zemax 432 + Speos 45 → **2962 篇**。
> - ✅ **GPU/HPC 补库(后又删)**(09:3x):按用户要求移除了那 38 篇 Lumerical GPU 文档(他用 fdtdx)。
> - ✅ **版本对齐 + MCP 扩展**(10:4x):校机 v241 自带 `docs.json` → 新集合 `lumerical_v241`(743 块);
>   MCP 加 `get_document` / `list_collections`,`search_lumerical_docs` 支持 collection+doc_type。
> - ✅ **兼容层上线**(12:2x):SQLite `compatibility.db`(785 feature / 3 recipe / 25 依赖)+ 集合
>   `lumerical_compat`;shim 加 `/compat/lookup`、`/compat/recipe`,rag-mcp 加 `lookup_lumerical_compatibility`、
>   `get_lumerical_compat_recipe`。**仍是 3 个进程、无新端口**;全库 16416 块(4 集合)。
> - ✅ **切分调参 v2**(09:13):表格/代码/段落/列表超长切段 + 碎块合并 → 最大块 12651→**4445 字符**,
>   >6000 块 19→**0**,<200 碎块 2318→**28**。
> - 🔴 **硬件关键约束(必读)**:102 CPU = **Intel Celeron G1610(2013,无 AVX/AVX2/FMA)**。
>   Qdrant 1.20 的 **int8 标量量化走 AVX SIMD → SIGILL(SIGILL 崩溃循环)**。
>   **建集合必须:关量化 + `optimizers_config.indexing_threshold=1000000`(不建 HNSW)**;
>   13k 向量纯暴力检索足够。若日后重建集合务必照此,否则会崩。

---

## 0. 结论速览

```
[一次性摄取] 校机(或笔记本)                      [常驻] 102 (2C/3.7G, Debian 13)
  Lumerical v241 docs + examples/*.lsf            ┌─────────────────────────────┐
  + optics.ansys.com 爬取                         │ Qdrant (127.0.0.1:6333)     │ ← 向量索引
        │                                         │ rag-shim (0.0.0.0:8900)     │ ← /search /ingest /mcp
        ▼                                         │  · hybrid RRF(向量+BM25)   │
  Docling 解析 → 层级切块 → SiliconFlow           │  · query embed(云API)      │
  bge-m3 embed → POST /ingest ──────────────────▶ │  · rerank(云API)           │
                                                  └─────────────────────────────┘
[使用者] 笔记本 dsh ──→ http://RAG_HOST:8900 (LAN + token)
[使用者] 校机 ──→ ssh -L 8900 隧道 → 127.0.0.1:8900 (校园网→家庭走既有 18322 转发)
```

**预算**:常驻 RAM ~250-400MB(102 现有可用 1.2G,不停你任何应用);磁盘 <1G(98G 富余)。
**回滚**:约 2 分钟干净卸载(见 §9)。

---

## 1. 机器角色与网络路径

| 机器 | 角色 | 访问 102 的方式 |
|---|---|---|
| 笔记本 (MEOW R16) | 使用者(dsh)+ 解析备选 | 直连 `http://RAG_HOST:8900`(家庭 LAN)+ token |
| 校机 (24C/125G, Win11) | **仅一次性解析** + 使用者 | SSH 隧道:`ssh -N -L 8900:127.0.0.1:8900 -p 18322 user@RAG_HOST`(走既有路由器转发,零新暴露面) |
| 102 (PC2, Debian 13) | 常驻服务宿主 | — |

## 2. 端口 / 路径 / 凭据约定(用户级部署)

| 项 | 值 | 说明 |
|---|---|---|
| Qdrant | `127.0.0.1:6333`(REST)/`6334`(gRPC) | **仅回环**,只有 shim 是它的客户端 |
| rag-shim | `0.0.0.0:8900` + Bearer token | 家庭 LAN 可直连;校园网走隧道;token 防裸奔 |
| **rag-mcp** | `0.0.0.0:8901`(MCP streamable-http,路径 `/mcp`) | 薄封装:调用本机 shim `/search`,供 **magpie → dsh** 当工具调用;工具名 `search_lumerical_docs` |
| 安装根 | `~/rag/`(`bin/` qdrant 二进制、`storage/` 索引;Phase 2 加 `shim/` venv) | 98G 空闲盘,占用 <1G |
| 配置/密钥 | `~/.config/rag/qdrant.yaml`(600)、`~/.config/rag/rag.env`(600) | 含 SiliconFlow key;均属 user(1000) |
| systemd | `~/.config/systemd/user/{rag-qdrant,rag-shim,rag-mcp}.service` | **用户级**(`systemctl --user`);`Linger=yes` → 开机自启 |
| swap | 不加(swapon 需 root) | 常驻总量 ≤1.1G(Qdrant 700M + shim 400M 硬上限),102 现有 swap 4G 兜底 |

⚠️ **密钥副本风险**:SiliconFlow key 会多一份落在 102 的 `~/.config/rag/rag.env`(600 权限)。
接受与否你说了算;不接受则 shim 改为「客户端传 key」模式(校机侧就得持 key,二选一)。

## 3. Phase 1 — Qdrant 上 102(✅ 已完成 2026-11-10)

脚本:`rag-102/phase1-qdrant.sh`(scp 到 `~/rag-phase1.sh` 执行)。用户级,无 sudo:
```bash
mkdir -p ~/rag/bin ~/rag/storage ~/.config/rag ~/.config/systemd/user
cd ~/rag/bin && curl -fL -o q.tar.gz \
  https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-musl.tar.gz \
  && tar xzf q.tar.gz && chmod +x qdrant    # 直连 GitHub 已通,ghproxy 仅作 fallback
```
`~/.config/rag/qdrant.yaml`:`service:{host: 127.0.0.1, http_port: 6333, grpc_port: 6334}`;
`storage:{storage_path: ~/rag/storage}`。

`~/.config/systemd/user/rag-qdrant.service`(要点):`ExecStart=~/rag/bin/qdrant --config-path ~/.config/rag/qdrant.yaml`,
`Restart=on-failure`,`MemoryMax=700M`/`MemoryHigh=600M`,`ProtectSystem=strict` + `ReadWritePaths=~/rag/storage`,
`WantedBy=default.target`。`systemctl --user daemon-reload && systemctl --user enable --now rag-qdrant`。

**验证实测**:`qdrant 1.20.0`;unit `active`(MainPID);`curl 127.0.0.1:6333/healthz` → `healthz check passed`;
`/collections` → `{"result":{"collections":[]}}`;`ss` 显示 6333/6334 均仅 127.0.0.1;cgroup MemoryCurrent 16MB / Peak 17MB。
日志仅两条无害 WARN(默认 `config/config`、WebUI `./static` 不存在)。

集合在 Phase 3 首次摄取时创建:`lumerical`(int8 标量量化 + mmap,预留 `papers`)。

> swap:原计划 +2G,因无 sudo 作废(§10-4)。

## 4. Phase 2 — rag-shim(✅ 已完成 2026-11-10)

脚本:`rag-102/phase2-shim.sh` + `shim/app.py` + `shim/requirements.txt` + `rag-102/phase2-mkenv.ps1`(本机生成 env)。
`~/rag/shim/venv`(**注意**:102 缺 `python3.13-venv` 包的 ensurepip,`python3 -m venv` 会失败;
已改为 `venv --without-pip` + 官方 `get-pip.py` 自举 pip,全程无 sudo)。
依赖:`fastapi uvicorn httpx tantivy`(manylinux 轮子,无编译,`deps ok`)。

端点设计(单进程,单 worker,目标常驻 ≤150MB):
- `GET /search?q=...&top_k=8&collection=lumerical`
  流程:query → SiliconFlow embed(bge-m3)→ Qdrant top50 + tantivy BM25 top50 → RRF(k=60)→ top20 →
  SiliconFlow rerank(bge-reranker-v2-m3)→ 返回 top_k(带 section 面包屑、来源、分数)。
  **rerank 输入已加料(2026-11-10)**:每条候选送 rerank 的是 `面包屑 + (reference)/(example script) 标签 + 正文`,
  让"命令/API 参考页"能压过"应用示例";索引不变、无需重灌。
  实测:`add a refractive index monitor` 的 `Refractive index monitor` 页从第 4(0.776)→ 第 2(0.972)。
- `POST /ingest` `{collection, chunks:[{id, text, meta}]}`:批量 embed → Qdrant upsert(幂等,按 id)→ tantivy 索引重建
- `GET /health`、`POST /admin/rebuild-bm25`(**从所有 collection 一起重建**,否则会清掉其它库的 BM25)
- **新增(2026-11-10)**:`GET /collections`(列集合/点数)、`GET /document?url=...`(按 URL 取整篇、按 chunk_idx 拼回)、
  `/search` 支持 `doc_type` / `version` 过滤;MCP 侧对应新增工具 `get_document`、`list_collections`,
  `search_lumerical_docs` 增加 `collection` / `doc_type` 参数。
- 鉴权:所有端点要求 `Authorization: Bearer <token>`(token 在 rag.env)
- (可选)`/mcp`:FastMCP streamable-http 挂同一 ASGI,dsh 可直接挂 MCP;**dsh 的 MCP 客户端配置格式我执行时现场核对**,不通就用 REST 兜底(笔记本侧小脚本包一层)

`~/.config/systemd/user/rag-shim.service`:同风格,`EnvironmentFile=~/.config/rag/rag.env`,`MemoryMax=400M`。

**验证实测**:unit `active`(MainPID);`/health` → `{"shim":"ok","qdrant":"healthz check passed","bm25_docs":0}`;
监听 `0.0.0.0:8900`;MemoryMax=400M 生效。端到端冒烟(`rag-102/phase2-smoketest.sh`):
ingest 3 块 → `{"inserted":3}`;`search?q=how to set mesh accuracy` → 正确命中 `c3`
(rerank 0.9919 / RRF 0.0328 / vscore 0.714 / bscore 4.12),无关 c1/c2 rerank≈0;测试集合已删除、bm25 已清回 0。
`RAG_TOKEN` 存于 `~/.config/rag/rag.env`(600),另已单独交你一份。

## 5. Phase 3 — 摄取管线(✅ 实现完成;HTML 用 lxml,docling 留作 PDF)

**决策(2026-11-10 用户定)**:首版 = Lumerical 全量去掉 Installation/Licensing = **2485 篇**;
**同日扩库**:再加 **Zemax 432 + Speos 45** → 合计 **2962 篇**(仅排除 ACE-Internal 1)。
解析 = **HTML 原生 lxml 抽取**(保 `<h1-4>`/`<pre><code>`/`<table>` 最忠实、无重型依赖),docling 仍装好留作将来 PDF。

**来源与获取(实测)**
- **在线 KB**:`optics.ansys.com` 是 Zendesk,裸 HTML 对本机/校机均 **403**,但其**公共 API 可直连 200**:
  `GET /api/v2/help_center/categories.json`、`/sections.json`、`/categories/{id}/articles.json?per_page=100`
  → 结构化 `{id,title,body(HTML),section_id,html_url,updated_at}`。抓取脚本 `rag-102/crawl_zendesk.py`,
  原始 JSON 落 `corpus/zendesk/cat_*.json`(可复跑/溯源)。抓取结果 **2962 篇**(11 个分类)。
- ~~**GPU/HPC 子集(已删)**~~:曾从 Installation & Licensing 筛 38 篇加入,2026-11-10 按用户要求**删除**
  (用户用的是开源 `fdtdx`,Lumerical 的 GPU/许可文档对他无用)→ 删 212 块,Qdrant 回到 14468。
- **本地 .lsf**:校机 `C:\Program Files\Lumerical\v241` 全树 215 个(`.lsf` 167 个真文本 + `.lsfx` 48 个
  **加密 XML,已剔除**)。打包 → `corpus/lsf-examples.zip` → 解压 `corpus/lsf/`。

**切块(结构优先,`rag-102/build_chunks.py`)**
- lxml 递归走 DOM:heading 建栈→chunk 边界;`pre` 代码整块;**`table`→`a | b | c` 行;`ul/ol`→`• 项`;`p`→段落**。
  仅当块 > ~1024 token(≈4096 字符)才在段落边界续切。
- **调参(2026-11-10,v2)**:① 表格 >4000 字符按行切段、每段重复表头 + `[table part k/n]`;
  ② 代码块 >6000 字符按**行**切(不切半行)+ `[code part k/n]`;③ 单段落 >4000 字符按**句**切;
  ④ 列表 >4000 字符按项切段(超长单项按句切);⑤ <200 字符的碎块**并入相邻块**(消孤块噪声)。
  常量:`PARA_SPLIT/TABLE_SPLIT=4000`、`CODE_SPLIT=6000`、`TINY_MERGE=200`。
  效果:最大块 **12651→4445 字符**;>6000 字符块 **19→0**;碎块<200 **2318→28**;块数 16697→14468。
- 每块 meta:`{source,doc_type,category,section,title,url,article_id,updated_at,parser=lxml-html,breadcrumb,chunk_idx}`;
  `.lsf` 整文件一块 `doc_type=example`。过滤 <80 字符且无代码的碎块。
- 产出 `corpus/chunks.jsonl`:**14320 KB 块 + 360 示例片 = 14680 块**(≈415 万 token;p50 ~800 / max 4445 字符)。
  `.lsf` 大文件(>4000 字符,最大 30KB)按**行**切段(embedding 8192 token 上限),小块整文件;`.lsfx` 加密剔除。
- 「跨文档重组」查询时做:小块召回 → RRF → rerank → 拼装(§4)。

**推送(实测)**:`rag-102/ingest.py` 批量 `POST /ingest`(48/批;示例块用 12/批防 embedding 超限),
断点续传 `corpus/sent_ids.txt`,失败落 `failed_batches.jsonl`;含 400 时自动拆单条并对超长块截断重试。
12959 块首次 ~487s,补 360 示例片 26s,**扩库 3545 块 114s**;推完 `POST /admin/rebuild-bm25` 从 Qdrant
重建 tantivy(去重 + 对齐 → **16697**)。论文线(以后):PaperQA2 + 同一套 102 服务。
(备查:若日后 PDF 类文档切块质量不满意,可评估一次性 RAGFlow/DeepDoc 补充——默认不用。)

## 6. Phase 4 — 接入(✅ 基本完成)

- **笔记本**:`rag-102/rag-query.ps1`(单文件,`-Query/-TopK/-Base/-Collection/-Token`)。
  直接 `.\rag-query.ps1 "how to set mesh accuracy in FDTD" -TopK 8`;token 存 `%USERPROFILE%\.rag\token`。
  实测单次查询 **~0.74s**(含云 embed + 向量 + BM25 + 云 rerank)。
- **校机**:先开隧道 `ssh -N -L 8900:127.0.0.1:8900 -p 18322 user@RAG_HOST`,再
  `.\rag-query.ps1 "..." -Base http://127.0.0.1:8900`(token 文件同样放 `%USERPROFILE%\.rag\token`)。
- **A/B(实测,2026-11-10)**:同一问题打 `dsh-knowledge` 工具 → **完全无 Lumerical 内容**
  (返回 Vitis FFT / 电机控制等无关片段,score 0.01–0.02);打新服务 → 精确命中
  (mode source→`addmode` 命令页 0.997;s-parameter→S-param sweep 0.998;ring resonator→相关示例)。
  结论:新服务填补了 dsh 知识库的空白,且带面包屑+URL+正文,可直接引用。
- **MCP(magpie → dsh,✅ 已接)**:102 上另起 `rag-mcp.service`(`~/rag/shim/mcp_server.py`,
  FastMCP streamable-http `0.0.0.0:8901/mcp`,工具 `search_lumerical_docs(query, top_k)`),薄封装调本机 shim。
  已验证:102 本地客户端 + 笔记本跨机客户端均握手成功并取回结果。
  在 **magpie `~/.config/magpie/library.json`** 的 `mcp` 数组登记
  `{name:"lumerical-rag", transport:"http", url:"http://RAG_HOST:8901/mcp", agents:[...]}` 并加入
  `applied.dsh.mcp`;dsh `cordis.patch.yml` 对应条目 `magpie-mcp-lumerical-rag`(与 `lumerical-lab` 同款)。
  **重启 dsh / 新开会话**后生效,工具名 `mcp__lumerical-rag__search_lumerical_docs`。
  (踩坑:mcp SDK 2.x 把 FastMCP 改名 MCPServer → 必须钉 `mcp<2`;客户端断开的 SSE 报错无害。)

## 6b. 独立集合 `fdtdx`(2026-11-10,用户用开源 fdtdx + JAX GPU)

**背景**:用户跑的是开源 [fdtdx](https://github.com/ymahlau/fdtdx)(JAX 可微 FDTD),不是 Lumerical;
所以 Lumerical 的 GPU 文档无用(已删),单独建 `fdtdx` 集合。

- **来源**:① readthedocs `en/stable` 全站(BFS 链接爬,**166 页**,含 API 参考与 tutorials);
  ② GitHub tarball(`codeload`,不走 API 限流)→ `examples/*.py` **9 个**、README/docs `.md|.rst` **12 个**;
  ③ 白皮书 arXiv:2412.12360 的 **HTML 版**(PDF 下载卡,故用 HTML)。
  脚本:`crawl_fdtdx.py`、`fetch_paper.py`、`build_fdtdx.py`(复用 `build_chunks.py` 的 `chunk_blocks`)。
- **产出**:179 篇源 + **581 个 API 符号**(从 WSL 已装包 `<WSL venv>/fdtdx` 抽 docstring,
  `extract_fdtdx_api.py` + `filter_fdtdx_api.py`,删继承/无文档冗余 9566→581)→ **1202 块**
  (568 doc + 34 example + 19 paper + **581 api**);源文件 `corpus/fdtdx/`。
- **校机访问(实测)**:校机 → `http://RAG_HOST:8901/mcp` 直连 OPEN,可 initialize/tools/list/tools/call;
  已在 `~/.dsh/profiles/web/cordis.patch.yml` 加 `magpie-mcp-lumerical-rag`(备份 `.bak-lumericalrag-*`),
  校机通过桌面 `DeepSeek Harness.lnk` 启动 dsh,下次启动即加载。
- **查询**:`GET /search?collection=fdtdx`;MCP 工具 `search_lumerical_docs(..., collection="fdtdx")`。
  实测:`install fdtdx cuda` → README 安装段(0.994);`XLA_PYTHON_CLIENT_ALLOCATOR NCCL_PROTO`
  → README Multi-GPU 段(BM25 83.9);bloch 示例、gaussian source 示例均精确命中。
- **BM25 跨库修复**:索引是共享的,`/admin/rebuild-bm25` 已改成**从 Qdrant 所有 collection 一起重建**
  (原来只重建指定 collection 会清掉另一个);现 `bm25_docs=15089`(14468 + 621)。
- WSL 里装的那份 fdtdx 未读取;若要"精确 API 签名"语料,以后可从 WSL 提取 docstrings 单独补。

## 6c. 版本对齐集合 `lumerical_v241`(2026-11-10)

- **试抓结论**:公网**没有 v241 存档文档**(`kb.lumerical.com` 只是 docs.json 里的旧链接引用);
  但**校机安装目录自带权威 v241 文档**:`C:\Program Files\Lumerical\v241\api\python\docs.json`
  (1.18MB,**665 条命令**的 `name` + `link` + 全文语法表/docstring)。
- 已复制到 `corpus/lumerical_v241/docs.json`,脚本 `build_v241.py` → **743 块**(>3500 字符按行切);
  meta `doc_type=command, version=v241`,集合 `lumerical_v241`。
- **用途**:回答"这条命令在 v241 上到底有没有/签名是什么"时以它为准;
  `lumerical`(14468)是**最新版**叙述性文档(更全更新,但可能含 v241 没有的新特性,如新增对象/参数)。
  推荐查询顺序:**先 `lumerical_v241`(精确/可用性)→ 再 `lumerical`(用法/示例)→ 需要旧功能复刻时按 v241 命令近似实现**。

- **版本差集(实测)**:最新 KB 有 **120 个命令是 v241 没有的**(`findresonances`、`modeoverlap`、`json*`、
  `sort/median`、`addrcwa`、`gds*`、`addimportnk`、`adddopinglayer` …);v241 有 18 个后来消失/改名的
  (`addport`、`importschematic/exportschematic`、`setcompositionfraction` …)。脚本 `diff_commands.py`。
- **v241 积木复刻(2026-11-10)**:用 v241 原语复刻新版命令 → `v241-recipes/v241_compat_recipes.lsf`
  ① `findresonances`(findpeaks+abs+max+length+两点插值 → 峰/FWHM/Q)
  ② `sort` / `median`(冒泡 + 奇偶取中)
  ③ `modeoverlap`(dot/conj/sum/abs → 归一化重叠;注明是仅 E 场近似)
  每段都是"输入变量→输出变量"代码块(v241 **没有 `function` 关键字**,用 `eval` 亦可)。
  所有 v241 命令已用 `add_recipe.py` 对 docs.json 逐条核实;并以 `doc_type=recipe` 入 `lumerical_v241`
  集合(现有 3 条,可被检索,例:查 `findresonances Q factor` → 命中该配方 0.957)。

## 6d. 兼容层(Compatibility Layer,2026-11-10)

**目标**:回答"这个新版命令在我的 v241 上能不能用?不能用有没有旧版实现?"——**不新增进程/端口**,只扩 shim。

- **结构化关系 → SQLite**:`rag-102/compat/compatibility.db`(构建脚本 `build_compat_db.py`),
  部署到 102 `~/rag/shim/data/compatibility.db`(可用 `COMPAT_DB` 覆盖)。表:
  - `features(name, in_v241, in_latest, v241_url, latest_url, description, status)`
  - `recipes(id, feature, title, target_version, equivalence, source_path, code, notes)`
  - `recipe_deps(recipe_id, command)`  ← 配方依赖的 **v241 原语**
  - `version_map(feature, relation, counterpart)` ← `new_in_latest` / `removed_or_renamed_in_latest`
  现状:**785 个 feature**(665 `available` / 116 `no_recipe_yet` / 4 `recipe_available`)、**3 个 recipe**、25 条依赖。
- **配方文本 → 向量库**:新集合 `lumerical_compat`(现 3 块,`doc_type=recipe`),沿用现有入库 + 全库 BM25 重建。
- **shim 新增 2 个接口**(原有 API 全保留):
  - `GET /compat/lookup?feature=&version=v241` → 该特性在不在 v241、状态、文档链接、可用配方(含等价程度)
  - `GET /compat/recipe?id=recipe_001` → 配方代码 + 依赖的 v241 命令列表
- **rag-mcp 新增 2 个工具**(同一 FastMCP):
  - `lookup_lumerical_compatibility(feature, version)`
  - `get_lumerical_compat_recipe(recipe_id)`
- **边界**:`no_recipe_yet` 的 116 个新版命令**还没有配方**——写配方是人工/半自动工作,按需追加即可
  (接口会如实返回"无配方",不编造等价实现)。

## 6e. 兼容层 v2(kit 规范版,2026-11-11)

依据 `S:\Downloads\lumerical_compat_backport_kit.zip`(AGENT_BRIEF + PHASE_PLAN + schema + 模板),
**仍是 3 进程,无新端口**。集成点图:`COMPAT_INTEGRATION_MAP.md`;备份:`compat/backups/20261110-043404`。

### 已实现
- **SQLite 10 表**(kit `schema/compatibility.sql`,v1):`shim/compat/{schema.sql,db.py,repo.py,api.py}`;
  shim 挂载 `/compat/lookup`、`/compat/recipe`、`/compat/capabilities`(复用 `_auth` 与 `meta.doc_id` 取回整篇)。
- **MCP 工具 v2 签名**:`lookup_lumerical_compatibility(feature, target_version, product, solver)`、
  `get_lumerical_compat_recipe(implementation_id)`。缺证据一律 `unknown` + `required_next_evidence`。
- **注册表**:`build_compat_registry.py` → 786 features;665 条 docs.json 证据标 `native`(仅"文档证据");
  kit `evidence_seed.sql` 已并入(13 个 source);sort/findresonances/modeoverlap 三条记 `unknown`
  + "发布版本早于 2024 R1 → docs.json 缺失是文档缺口"注记。
- **资产**:`compat/assets/resonance_fwhm_v241/`(recipe.md + implementation.lsf + implementation.yaml +
  静态 passed / runtime blocked 两份 test-report)。**workaround / approximate / L1 / static_checked**,
  文档明确"2019a 引入,运行时先试原生命令"。
  `build_compat_assets.py` 校验枚举+依赖存在性→写 SQLite→生成**整篇不切分**检索文档(7941 字符)。
- **快照管线**:`import_capability_snapshot.py`(幂等,哈希校验,只认 commands.json/syntax_probes 为证据,
  不自动翻转 availability);`make_capture_kit.py` → `capabilities/capture-kit/`(校机采集脚本 + 7 个语法探针 .lsf,
  默认不执行)。
- **测试**:16/16 通过(`tests/test_compat_registry.py` 9 + `tests/test_compat_api.py` 7;
  API 测试用 TestClient + 临时库,不碰 102)。

### 运维
- **部署**:改完本地 → `scp shim/app.py shim/mcp_server.py shim/compat/* compat/compatibility.db` 到
  102 对应位置(`~/rag/shim/…`)→ `sed -i "s/\r$//"` → `systemctl --user restart rag-shim rag-mcp`。
- **迁移**:schema 是 `CREATE IF NOT EXISTS`,重跑 `build_compat_registry.py`/`build_compat_assets.py` 即等价迁移;
  旧库先备份。
- **快照导入**:校机跑 `capture-capability.ps1`(需打开的 CAD 会话;无许可则全部 not_run)→ zip 带回 →
  `import_capability_snapshot.py <dir>` → `/compat/capabilities` 即有 provenance。
- **回滚**:`compat/backups/<ts>/` 覆盖回 `shim/data/compatibility.db` + `shim/*.py`,重启两服务;
  `lumerical_compat` 集合可整删不影响其他三个集合。

### 边界(诚实)
- ~~无运行时快照~~ → **2026-11-10 已在校机实测采集**(lumapi FDTD 隐藏会话,build 8.31.3633):
  `capabilities/snapshots/lumerical-2024r1-school-20261110/`(606 个 getcommands 符号 + 11 条语法探针),
  已导入注册表并可经 `/compat/capabilities` 查 provenance。**L2+ 仍 pending**(无差分参考输出)。
- **运行时实测结论**(2024 R1, build 8.31.3633):
  - `findresonances` / `sort` **native**(getcommands 在列;sort([3,1,2])→[1,2,3] 活探针通过)——
    docs.json 缺失确认为**文档缺口**,此前"120 条 v241 没有"的说法对这类命令不成立;
  - `median` **absent**(不在 getcommands,直接调用语法错,docs.json 也没有——确实是后期引入);
  - `function` / `while` / `elseif` / `switch` / `continue` **absent**(隔离 feval 探针逐个语法错;
    v241 LSF 无用户函数、无 while,循环只有 for);
  - `modeoverlap` FDTD 会话 absent(其域为 FEEM/DGTD,不得外推);`python` LSF 命令 absent(2024 R1.1 引入,自洽)。
- **L2 运行时验证(2026-11-10 校机 lumapi 会话,raw 输出在 compat/assets/)**:
  - `median` **5/5 fixture 零容差全过** → `compat.median.sort.v241.exact` 升 **L2/runtime_verified**(equivalence=exact);
  - `resonance_fwhm` 差分双参照全过:R1 解析真值 rel err **1.16e-6**(预声明容差 1.23e-3 内),
    R3 vs 原生 `findresonances` **gap 2.5e-7** → 升 **L2**(仅限声明域:孤立洛伦兹、df≪FWHM、**功率谱**输入);
  - 验证过程修了两处夹具错误(留档为证据):官方返回是 **Nx6 矩阵**[f,α,Q,A,φ,err],不是 dataset;
    FFT 必须零填充到 df≪FWHM 且喂**功率谱**(幅度谱会引入 √3 倍半宽偏差——第一次跑就栽在这)。
- **L3 实测差分(2026-11-11,自建 DBR 法布里-珀罗腔,真实 FDTD 全流程)**:
  - 工程 `fpcavity.fsp`(2D FDTD,Si/SiO₂ 4 对 1/4 波 DBR + 1.5λ 腔,偶极子宽带脉冲,13.5 ps 环 down);
  - **主峰 267.366 THz(1121.3 nm):原生 Q=636.71(err 1.2e-9) vs 配方 Q=636.72,gap 2.4e-5** →
    resonance_fwhm 的 L2 在真实数据(含 PML/网格/色散)上成立;
  - 过程教训(留档为证据):v241 FDTD 属性名 `simulation time`(非 time span);新建对象默认名
    dipole→`source`、time monitor→`monitor`;环 down 必须从脉冲结束后截取(阈值走停在包络内部
    截断导致源谱污染,Q=7.6 假象);**early shutoff 会在 870fs 砍掉 15ps 仿真**(Q=200 需要 >5 个
    衰减周期,必须 `use early shutoff=0`);<外部工程目录> 工程只读探测未改任何文件(时间戳核验过)。
- **B 类适配 2 条完成(L2)**:
  - `compat.adddftmonitor.v241.adapter`(domain_equivalent):addpower + 1:1 属性映射,
    fpcavity 上实测——监视器建成、命名、run 后 Ex/Ey/Ez 场数据齐全(71 空间 × 5 频点);
    2D 拓扑的 `z span` 与变量名设 `frequency points` 的 eval 怪癖均记录为 skip;
  - `compat.reportmeshstatistics_v241.adapter`(partial):**关键发现**——FDTD 对象的
    `nx/ny/nz/dx/dy/dz` 是 mesh-override 参数(默认 1/1e-7),真实网格在 **`mesh cells x/y/z`**
    (267×132×47=1.66M cells),步长=span/cells;适配器实测输出一致;
  - 其余 3 条(modeexpansion/modeoverlap、cadimport、setmodes/setiir 族)按用户同意转走:
    FDTD 有内建 expansion monitor、GDS 原生命令已覆盖、其余是 INTERCONNECT 域——
    清单见 `compat/absent_commands_inventory.md`。
  - T1 `median` **干净会话重探通过**(`median([-3,5,-1])=-1.0` 精确)→ 此前 absent 判断是**探针会话错误累积**的假象,
    registry 改回 native(basis=multiple);教训:探针必须独立会话,错误日志会跨 eval 累积;
  - T2 `sort` 复数语义运行时验证:**按模排序**([3-3i,1+1i,2+2i,4]→[1+1i,2+2i,4,3-3i],与官方文档一致)、降序 flag 有效;
  - T3 **2012 斜率法差分**:解析高斯带通+40–60% 窗斜率 → Q=499.832(rel 3.4e-4),FWHM 配方 rel 5.3e-7,
    **两法 gap 3.4e-4**——斜率法在干净合成信号上稍逊,但其价值在真实噪声 monitor 数据的误差估计;
    注意 LSF `fftw` 返回**双边轴**(0→1/dt),独立 LSF 端口极易踩坑(2012 脚本原依赖 analysis group 上下文);
  - T4 `jsonwrite/jsonload` 往返签名验证通过(struct→save→load 逐字段相等)——json* 九件套确认原生可用,无需配方。
- **运行时交叉核对修正(606 符号 × KB-only 120)**:68 条"KB 独有"其实**原生存在**(全部 json*、
  sort、print、end、resume、addrcwa、gds*、zbf*、mqw*、fit*pdf、poly* 等)→ registry 批量补
  `native (basis=getcommands)`;真缺席仅 52 条,清单+分类见 `compat/absent_commands_inventory.md`
  (A 其他求解器物理 17 / B 有 FDTD 适配路径 16 / C 语言构造 5 / D 工具链 14)。
- 技术教训:lumapi `eval` 不回传 `?` 打印;探测一律"变量赋值 + `getv` 取回",脚本文件用 **`fdtd.feval(path)`
  对象方法**执行;PowerShell 写的 JSON 带 BOM,导入器用 `utf-8-sig` 容错。
- `lumerical_compat` 现 1 篇资产;`json*` 等仍未探,保持 `unknown`。
## 7. 安全要点
- Qdrant 仅回环;shim 有 token;**不新增任何路由器端口转发**;
- SiliconFlow key 新副本在 102(`~/.config/rag/rag.env`,600)——见 §2 警示;
- 校机→家庭流量全程 SSH 加密。

## 8. 资源预算(实测)

| 项 | 102 实测 | 占用 | 结论 |
|---|---|---|---|
| RAM 可用 | ~1.2G(常压) | Qdrant ~126M + shim ~229M + mcp ~44M | ✅ 未杀你任何应用 |
| swap | 4G(常用 ~3.1G) | 无新增(无 sudo) | ⚠️ 机器本就吃紧,服务已设 MemoryMax 上限 |
| 磁盘 | 98G 空闲 | `~/rag/storage` **132M** | ✅ |
| CPU | 2 核 Celeron G1610(**无 AVX**) | 暴力检索;单次查询 ~0.74s | ✅ 但**禁用 Qdrant 量化/HNSW** |

## 9. 回滚(约 2 分钟,干净)
```bash
systemctl --user disable --now rag-shim rag-qdrant
rm -rf ~/rag ~/.config/rag ~/.config/systemd/user/rag-{qdrant,shim}.service
systemctl --user daemon-reload
```
(用户级,无需 sudo;不残留系统文件。)

## 10. 执行时才定稿的开放项
1. ~~dsh 的 MCP 客户端配置~~ → ✅ **已做**:`rag-mcp`(:8901) + magpie `library.json` 登记 `lumerical-rag` → dsh(工具 `search_lumerical_docs`);
2. ~~校机 python~~ → 校机 3.15 太新,docling 装本机(3.12);解析(lxml)也在本机跑;
3. ~~chunker 参数~~ → 已定:结构优先切分(见 Phase 3),非定长;
4. ~~swapfile~~ → **作废:无 sudo,不加**;Qdrant/shim 设 MemoryMax(700M/400M)兜底;
5. ~~token 值~~ → 已生成,存 102 `~/.config/rag/rag.env`(600)+ 本机 `~/.rag/token`,已交你一份;
6. ~~key 落点~~ → 已定:key 落 102 `~/.config/rag/rag.env`(600);
7. ~~解析器~~ → 已定:**HTML 用 lxml 原生抽取**;docling 2.149.0 已装本机留作 PDF 线;
8. **Qdrant 量化/AVX(新增关键项)**:Celeron G1610 无 AVX → 集合**禁 int8 量化 + 不建 HNSW**
   (`indexing_threshold=1000000`),否则 SIGILL 崩溃。已在 shim `_ensure_collection` 固化;
9. **.lsf 切段(新增)**:>4000 字符的 .lsf 按行切段(embedding 8192 token 上限),小块整文件;
10. **切分调参 v2(新增,已完成)**:表格/代码/段落/列表超长切段 + <200 碎块合并(见 §5);旧快照留
    `corpus/chunks.v1-before-tune.jsonl` 可回滚。

---

**审批点**:你确认本计划(或改任何一条),我就按 Phase 1→4 顺序执行,**每阶段跑完回报验证输出再进下一阶段**。
