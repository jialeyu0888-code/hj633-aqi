# hj633-aqi

[![npm](https://img.shields.io/npm/v/hj633-aqi)](https://www.npmjs.com/package/hj633-aqi)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Claude Code skill：按中国生态环境标准 **HJ 633—2026《环境空气质量指数（AQI）技术规定（试行）》**（2026-02-14 发布，2026-03-01 实施，代替 HJ 633—2012）计算、核对与解释 AQI / IAQI / 首要污染物 / 级别与颜色。

核心是零依赖的 Python 脚本 `scripts/hj633.py`：官方表 3 全部断点、分段线性插值（式 1）、**向上进位取整**（4.2.6）、日报/实时报两种口径（4.2.2 / 4.2.3）、SO₂ 1h 与 O₃ 8h 封顶注 b/c、缺项发布规则（5.3.1）、IAQI 反推浓度、2012 版对照。自带 4875 项审计用例全部通过（`scripts/accuracy_audit.py`）。

## 安装（一键）

```bash
npm install -g hj633-aqi
```

postinstall 会自动把 skill 复制到 `~/.claude/skills/hj633-aqi/`（若设置了 `CLAUDE_CONFIG_DIR` 则装到 `$CLAUDE_CONFIG_DIR/skills/`）。重启 Claude Code 会话后生效。

不想全局安装也可以：

```bash
npx hj633-aqi            # 安装
npx hj633-aqi uninstall  # 移除
```

或手动安装：

```bash
git clone https://github.com/jialeyu0888-code/hj633-aqi ~/.claude/skills/hj633-aqi
```

## 使用

在 Claude Code 里直接问即可自动触发，例如：

- 「PM2.5 日均 75 μg/m³ 对应 IAQI 多少？」
- 「日报口径：PM2.5 55、PM10 90、O₃ 日最大 8h 160、SO₂ 12、NO₂ 35、CO 0.8，算 AQI 和首要污染物」
- 「IAQI=100 时各污染物的浓度限值是多少？」
- 「2026 版和 2012 版断点差在哪？」

skill 会强制走脚本计算，不口算、不套用 2012 断点。

也可以直接用命令行（无需 Claude）：

```bash
# 单污染物 IAQI
python ~/.claude/skills/hj633-aqi/scripts/hj633.py iaqi --pollutant PM2.5 --conc 75 --avg 24h

# 日报 AQI + 首要污染物
python ~/.claude/skills/hj633-aqi/scripts/hj633.py aqi --mode daily \
  --pm25 55 --pm10 90 --o3 160 --so2 12 --no2 35 --co 0.8 --assume-complete

# 实时报（O₃ 为 1h；颗粒物 1h 浓度仍查 24h 断点）
python ~/.claude/skills/hj633-aqi/scripts/hj633.py aqi --mode realtime --pm25 55 --o3 188 --no2 90 --assume-complete

# 由 IAQI 反推浓度 / 全表限值 / 级别 / 敏感人群 / 2012 对照
python ~/.claude/skills/hj633-aqi/scripts/hj633.py reverse --pollutant PM2.5 --iaqi 100 --avg 24h
python ~/.claude/skills/hj633-aqi/scripts/hj633.py limits
python ~/.claude/skills/hj633-aqi/scripts/hj633.py category --aqi 165
python ~/.claude/skills/hj633-aqi/scripts/hj633.py sensitive --pollutant O3
python ~/.claude/skills/hj633-aqi/scripts/hj633.py compare-2012 --pollutant PM2.5 --conc 75 --avg 24h
```

所有子命令支持 `--json`。

## 2026 版相对 2012 版的关键变化

| 项目 | 2012 | 2026 |
|------|------|------|
| PM₂.₅ 24h，IAQI=100 | 75 μg/m³ | **60** μg/m³ |
| PM₁₀ 24h，IAQI=100 | 150 μg/m³ | **120** μg/m³ |
| 取整 | GB/T 8170 修约 | **向上进位** |
| 实时报颗粒物 | 部分实现混用 1h 断点 | 明确用 **24h 断点** |
| 敏感人群 | 无独立表 | 新增表 2 |
| 超标污染物 | 有定义 | **删除** |

其余气态污染物断点与 2012 相同；SO₂ 1h > 800 μg/m³ 时 IAQI 按 200 计（注 b），O₃ 8h > 800 μg/m³ 时按 300 计（注 c）。

## 目录结构

```
├── SKILL.md              # skill 定义（Claude Code 的入口）
├── references/
│   ├── standard.md       # 标准完整条文摘录
│   └── breakpoints.json  # 表 3 断点（机器可读）
├── scripts/
│   ├── hj633.py          # 计算 CLI（标准库，零依赖）
│   ├── test_hj633.py     # 单元测试
│   ├── accuracy_audit.py # 全表准确率审计（可 --compare-iaqi 对照外部实现）
│   └── batch_csv_aqi.py  # CSV 批量计算
├── evals/evals.json      # skill 触发与正确性评测用例
└── bin/install.js        # npm 安装器
```

## 验证

```bash
npm test    # 即 python scripts/accuracy_audit.py，4875 项用例
```

## License

[MIT](LICENSE)

## Disclaimer

本工具按公开发布的标准文本实现，仅供技术参考；正式发布空气质量指数请以生态环境主管部门口径为准。
