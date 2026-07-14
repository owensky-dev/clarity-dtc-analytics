# Clarity DTC Analytics

面向 Shopify 独立站的本地数据分析 Skill：将 Microsoft Clarity、GA4、Google Search Console、Google Ads 和 Shopify 订单数据保存到本地仓库，生成可审计的中文 CRO 周报。

## 能做什么

- 初始化按店铺隔离的数据仓库，密钥仅保存在本地 `.env`
- 每日采集 Clarity 的行为快照，以及 GA4、GSC、Google Ads、Shopify 四类经营数据
- GA4 使用独立日期级事件查询保存 `add_to_cart` 与 `begin_checkout`，避免与渠道 Sessions 粒度混合
- 强制以四源都完整覆盖的连续 14 天生成周报：当前 7 天对比前一完整周
- 以 Shopify 作为营收和订单事实来源；把 Clarity 作为行为证据层，不将聚合行为数据表述为因果
- 输出 HTML、Markdown、JSON 和供可选 AI 叙事使用的结构化分析上下文
- 在 HTML 与 Markdown 顶部清晰标注“周报周期”和“对比周期”
- 周报按本周与上周展示 Sessions → 加购 → 开始结账 → Shopify 订单漏斗

## 使用方式

将本仓库中的 `clarity-dtc-analytics` 目录安装到 Codex Skills 目录后，在任务中调用：

```text
$clarity-dtc-analytics 为 <你的店铺> 初始化数据仓库并生成中文周报
```

在任意已安装目录中，先创建项目：

```bash
python scripts/init_project.py --target /path/to/store-analytics
cd /path/to/store-analytics
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/validate_config.py --project-root .
```

填写 `.env` 后运行每日采集与周报：

```bash
python scripts/run_daily_ingestion.py --project-root .
python scripts/generate_weekly_report.py --project-root .
```

## 数据与隐私原则

- 不提交 `.env`、OAuth Token、Shopify Access Token 或任何原始凭据。
- 周报只有在 GA4、Shopify、Google Ads、GSC 对当前周和对比周都存在完整日级覆盖时才生成。
- Clarity 的 UTC 滚动 24 小时快照与店铺自然日口径分开处理；它用于提出可验证的 CRO 假设，而不是直接声称因果。

## 目录说明

- `SKILL.md`：Skill 使用说明与运行约束
- `scripts/template/`：初始化到每个店铺项目的可执行模板
- `references/`：配置、数据契约、追踪与报告政策
- `scripts/tests/`：模板的回归测试

## 开发验证

```bash
python -m unittest discover -s scripts/tests -p 'test_*.py' -v
```

## 适用场景

Shopify 独立站的周度增长复盘、广告与自然搜索协同诊断、Clarity 行为摩擦排查，以及可复用的本地 DTC 分析基础设施。
