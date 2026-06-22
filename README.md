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

## 启动 Web

```powershell
python .\scripts\run_web.py --port 8014
```

默认地址：

- 首页：`http://127.0.0.1:8014/`
- 最新研究：`http://127.0.0.1:8014/api/latest`
- 影子仓位接口：`http://127.0.0.1:8014/api/shadow/latest`
- 最新单股深研：`http://127.0.0.1:8014/api/stocks/deep/latest`
- 单股深研影子池接口：`http://127.0.0.1:8014/api/stocks/deep/shadow/latest`

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
