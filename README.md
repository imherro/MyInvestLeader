# MyInvestLeader

MyInvestLeader 是本地主线龙头研究与影子仓位对接层。它读取主线研究接口，使用项目数据源补充 ETF 与 A 股候选证据，生成可复核的 Markdown/JSON 研究文件，并提供只读 Web 与影子仓位输入接口。

## 生成研究

```powershell
python .\scripts\generate_leader_report.py --write
```

输出位置：

- `research/leaders/leader_review_YYYY-MM-DD_HHMMSS.json`
- `research/leaders/leader_review_YYYY-MM-DD_HHMMSS.md`

## 生成龙头股深研

先生成主线龙头报告，再生成单股深研：

```powershell
python .\scripts\generate_stock_deep_research.py --write
```

输出位置：

- `research/stocks/stock_deep_review_YYYY-MM-DD_HHMMSS.json`
- `research/stocks/stock_deep_review_YYYY-MM-DD_HHMMSS.md`

深研只从 A/B 主线的前排候选中选股，结论是 `S/A/B/C` 研究评级，不是交易指令。

## 龙头证据链

系统把 `config/stock_leader_universe.json` 作为候选种子库，只用于防止漏掉高认知度行业龙头；真正的龙头认定来自 `config/leader_evidence_sources.json` 中的证据规则和运行时数据确认。

当前候选分层：

- `证据确认龙头`：有候选种子或人工角色声明，并且至少两项硬证据确认，证据分不低于 70。
- `强候选龙头`：有候选种子或人工角色声明，但动态证据仍不完整。
- `市场热点候选`：没有行业角色种子，但主线关键词、成交额、资金流等市场证据较强。
- `证据不足候选`：证据链不足，进入研究观察，不作为确认龙头。

当前硬证据主要来自 Tushare 的总市值、成交额、资金流，以及 theme.okbbc 主线与 Tushare 行业/名称的绑定。后续可继续把年报、行业排名、券商研报链接补入证据库。

## 系统规则逻辑

MyInvestLeader 的核心目标是把外部主线数据、结构化行情数据和可追溯龙头证据合成只读研究结果，为后续影子仓位系统提供输入，不直接生成真实交易指令。

规则链路：

1. **主线发现**：读取 `https://theme.okbbc.com/api/latest`，使用最新主线、阶段、生命周期、市场分、政策分、ETF 分和主题映射作为上游主线输入。
2. **数据补充**：优先使用 Tushare 读取 ETF、A 股行情、市值、成交额、资金流、基础证券信息和财务/估值数据；`.env` 只保留在本地，不进入报告、接口或审计包。
3. **候选生成**：ETF 候选来自上游 ETF 列表和主题关键词；A 股候选来自主题关键词匹配、行业/名称匹配、候选种子库和动态行情确认。
4. **候选种子保底**：A 股候选先按 `leader_score`、`evidence_score`、`seed_score` 和成交额保留动态前排，再把 `config/stock_leader_universe.json` 与人工证据声明中的细分龙头并入候选矩阵。这样绿的谐波这类机器人减速器龙头不会因为当日动态排名被截断而完全消失。
5. **候选种子边界**：`config/stock_leader_universe.json` 只负责防漏，不能单独证明“公认龙头”；它的角色是研究先验，不是交易建议。被保底召回的股票仍要经过竞争图谱和深研评分，不会自动成为 L1 或 A 可跟踪龙头。
6. **证据确认**：`config/leader_evidence_sources.json` 定义证据来源和硬证据规则。候选股票必须结合候选种子、主线绑定、市值分位、成交额分位、资金流等证据生成 `evidence_score`、`evidence_count` 和 `hard_evidence_count`。
7. **龙头分层**：
   - `证据确认龙头`：有候选种子或人工角色声明，并且至少两项硬证据确认，证据分不低于 70。
   - `强候选龙头`：有候选种子或人工角色声明，但动态证据仍不完整。
   - `市场热点候选`：没有行业角色种子，但主线关键词、成交额、资金流等市场证据较强。
   - `证据不足候选`：证据链不足，进入研究观察，不作为确认龙头。
8. **深研队列**：A/B 主线内的前排 A/B 个股进入深研；如果主线短期偏弱但个股是 `证据确认龙头`，也允许进入 ResearchFirst 跟踪深研，但不因此直接进入影子池。
9. **深研评级**：单股深研输出 `S/A/B/C` 研究评级，综合主题绑定、证据质量、财务质量、估值安全、交易结构、数据质量和风险标记。
10. **影子仓位输入**：影子接口只输出只读、比例化研究信号；不包含真实资金、股数、下单指令、真实持仓写入或盈亏金额。弱主线环境下，深研可继续但影子池可以为空。
11. **数据缺口处理**：任何行情、财务、估值、资金流或证据缺失必须写入 `data_gaps`，缺失数据不能被当作已验证结论。
12. **审计与同步**：研发完成后默认运行相关测试，确认 `.env`、`temp/`、缓存和敏感文件未进入暂存区，再提交并推送 `origin/main`。

## 启动 Web

```powershell
python .\scripts\run_web.py --port 8014
```

默认地址：

- 首页：`http://127.0.0.1:8014/`
- 统一接口目录：`http://127.0.0.1:8014/api`
- 最新研究：`http://127.0.0.1:8014/api/latest`
- 影子仓位接口：`http://127.0.0.1:8014/api/shadow/latest`
- 最新单股深研：`http://127.0.0.1:8014/api/stocks/deep/latest`
- 单股深研影子池接口：`http://127.0.0.1:8014/api/stocks/deep/shadow/latest`
- 每日推荐龙头历史：`http://127.0.0.1:8014/api/stocks/deep/recommendations/history`

## 集成接口

`/api` 是统一接口目录，只返回说明，不触发研究重算、文件写入、交易、同步或外部调用。它返回：

- `system`：系统名称、版本和说明。
- `base_url`：当前请求的基础地址。
- `docs`：`/docs`、`/redoc`、`/openapi.json`。
- `recommended_entrypoints`：推荐集成入口，优先使用 `/api/index`。
- `safety`：只读、比例化、无交易指令、无真实资金和股数字段等边界。
- `groups`：按文档入口、当前数据、分析结果、历史数据、系统状态分组列出公开接口。
- `total_endpoints`：公开接口总数。

`/api/index` 是页面主接口，也作为其他系统集成 MyInvestLeader 的首选接口。它包含页面主要内容和关键成果：

- `key_results.primary_output.items`：首屏展示的“龙头股深研 A可跟踪龙头”，按股票代码去重，包含代码、名称、雪球链接、所属主线、深研评级、深研分、证据计数、风险和数据缺口。
- `key_results.recommendation_history.records`：每日推荐龙头历史，按基准日保留最近一次 A 可跟踪龙头清单；每只历史股票带 `current_status_label`，用于区分 `仍在A池`、`降为候选`、`已出当前池`，完整时间戳报告仍可从 `/api/stocks/deep/reports` 核对。
- `key_results.integration`：接口边界声明，只读、比例化，不包含交易指令、资金金额或股数。
- `key_results.process_flow`：页面底部“可跟踪龙头产生过程”图示，从最早股票池、候选矩阵、竞争图谱、龙头股深研到 A 可跟踪龙头，逐步说明数据来源、筛选依据、优胜劣汰规则和输出路径。
- `themes`：主线龙头候选矩阵和竞争图谱；股票候选含 `candidate_recall_source` 和 `seed_protected_recall`，用于区分动态前排、种子保底召回等来源。
- `stock_deep_research.stocks`：完整龙头股深研明细。
- `shadow_contract`：只读影子仓位输入信号。

## 边界

- 只输出研究与模拟输入，不连接真实下单。
- 影子仓位接口只给比例化、只读信号，不包含真实资金、股数或盈亏金额。
- Tushare 是结构化主源；缺失数据写入 `data_gaps`，不当作已验证结论。

## 研发完成同步约定

每次研发任务完成后，默认执行以下收尾流程：

- 运行与本次改动相关的检查或测试。
- 确认 `.env`、`temp/`、缓存目录和其他敏感/临时文件未进入暂存区。
- 提交本次研发改动。
- 推送到 `origin/main`，保持本地与 GitHub 仓库同步。

如果测试失败、网络推送失败或存在不应提交的混合改动，需要先说明阻塞点，不把未验证或越界内容同步到远端。
