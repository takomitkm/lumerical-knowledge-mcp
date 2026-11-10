# 运行时存在但两套文档源都未记录的符号(2024 R1,getcommands 606)

> 2026-11-11。来源:`capabilities/snapshots/lumerical-2024r1-school-20261110`(606 符号)
> × v241 docs.json(665)× 最新 KB 命令页(767)。探针证据:`compat/undocumented_probe.json`
> (21 条逐个调用,干净 lumapi 会话)。。

## 运算符/控制符(14)

`!=, *, +, -, /, :, <, <=, ==, >, >=, ?, ^, |`

## 关键字/常量(推断,19)

`append, assert, catch, clc, cls, else, false, getid, history, isnull, monitors, new2d, new3d, pop, remove, sources, structures, true, viewundo`

## 真·未记录命令(24)——存在但两套文档都没有

**行为实测**(2024 R1 build 2024.0104,干净 lumapi 会话):

| 命令 | 可调用? | 实测行为 | 用途(推断) |
|---|---|---|---|
| `getobjectlist` | ✅ | 返回 `['::model::']`——只列**顶层组**,不递归子对象 | 对象树枚举(有限) |
| `getlicenseversion` | ✅ | 返回 `2024.0104` | 安装 build 号(比 `version()` 更细) |
| `getassertresults` | ✅ | 返回断言/错误缓冲列表(捕获了同会话此前 `setglobal` 的报错文本!) | **错误诊断利器** |
| `queryanalysisresult` | ✅ | 返回 `[]`(无分析结果时) | 分析结果枚举 |
| `addstack` | ✅ | 创建了 stack 对象(未报错) | 堆叠对象(可能是 layer builder 家族) |
| `addrcwafieldmonitor` | ✅ | 创建了对象(未报错) | RCWA 场监视器(`addrcwa` 配套,RCWA 本身在 2024 R1 已原生) |
| `setmemorycheck` | ✅ | `setmemorycheck(1)` 接受并返回 1 | 内存检查开关 |
| `setparallel` | ✅ | 无参调用返回空(可能有参数签名) | 并行设置 |
| `setglobal` / `getglobal` | ❌ | **三种签名全部语法错**——在 getcommands 里但当前产品不可用 | 全局变量(疑为 INTERCONNECT 专属) |
| `getmeshfaces` | ❌ | 调用失败(需要网格/参数) | 网格面数据 |
| `getasapdata` | ❌ | 调用失败 | ASAP 互操作 |
| `querynamed` | ❌ | 调用失败(签名不对) | 命名对象查询 |
| `gdsaddellipse` / `gdsaddmultipoly` | ❌ | 调用失败(需要参数) | GDS 图元 |
| `h5write` / `h5writeattr` | ❌ | 调用失败(需要参数) | HDF5 写入 |
| `showdata` | ❌ | 调用失败 | 数据显示 |
| `encryptprocess` / `exportassertasjunit` | ❌ | 调用失败 | 进程加密 / JUnit 导出 |
| `topoparamsto*`(4 条) | ❌ | 调用失败(需要拓扑优化上下文) | lumopt 拓扑优化桥 |

### 对你第一个问题的直接回答:"文档没有但运行时存在"是否真的和文档一个行为?

**不存在"和文档一个行为"的问题——这些命令根本没有文档**。分三种情况(实测):
1. **`getobjectlist`/`getlicenseversion`/`getassertresults`**:行为可复现、签名可摸清——是**未文档化但稳定**的内部命令。
2. **`setglobal/getglobal` 等**:在清单里但**调用即失败**——疑似"安装级清单混入了其他产品的命令",印证 getcommands 是 installation-wide 的。
3. **`topoparamsto*`**:需要特定上下文(lumopt)——有条件可用。

所以你说的"厂商做出来还不成熟所以没写文档"对一部分成立(如 `addstack`/`addrcwafieldmonitor` 这类配套对象),
但另一部分是**跨产品清单混入**或**需要上下文**——三种情况都不等于"行为与文档一致",因为压根没有文档承诺。

### 意义

- `getassertresults` 是本次最大的意外收获:它把 LSF 会话的**错误缓冲**暴露出来,以后写探针可以主动读取它来判断失败原因(比 lumapi 的 'Failed to evaluate code' 详细得多)。
- `getlicenseversion` 返回 build 号,可以写进 capability snapshot 的 environment.json,替代手工填的 build 号。
- `getobjectlist` 只列顶层——之前"枚举对象树"的需求它解决不了,仍然是靠 `getnamednumber` 逐名探测。
