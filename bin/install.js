#!/usr/bin/env node
/**
 * hj633-aqi skill 安装器。
 * `npm install -g hj633-aqi` 后由 postinstall 自动执行；也可手动运行：
 *   npx hj633-aqi             安装 / 更新到最新已下载版本
 *   npx hj633-aqi --force     覆盖已是 git 仓库/开发目录的目标（慎用）
 *   npx hj633-aqi uninstall   移除已安装的 skill
 * 目标目录：$CLAUDE_CONFIG_DIR/skills/hj633-aqi（未设置时为 ~/.claude/skills/hj633-aqi）
 */
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

const SKILL_NAME = "hj633-aqi";
const COPY_ITEMS = ["SKILL.md", "references", "scripts", "evals"];
const EXCLUDES = [/^__pycache__$/, /\.pyc$/];

function install() {
  const src = path.resolve(__dirname, "..");
  const claudeDir =
    process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), ".claude");
  const dest = path.join(claudeDir, "skills", SKILL_NAME);
  const force = process.argv.includes("--force") || process.argv.includes("-f");

  // 在本仓库内开发时源即目标，跳过
  if (path.relative(src, dest) === "") {
    console.log("[hj633-aqi] 源目录即目标目录（本仓库内开发），跳过安装。");
    return;
  }

  // 目标目录是开发仓库（git clone / 本仓库）时拒绝覆盖，防止误删 .git
  if (
    !force &&
    fs.existsSync(dest) &&
    (fs.existsSync(path.join(dest, ".git")) ||
      fs.existsSync(path.join(dest, "package.json")))
  ) {
    console.error(
      `[hj633-aqi] ${dest} 看起来是 git 仓库/开发目录，拒绝覆盖以免丢失 .git 等文件。`
    );
    console.error("[hj633-aqi] 确要覆盖请运行：npx hj633-aqi --force");
    process.exitCode = 1;
    return;
  }

  for (const item of COPY_ITEMS) {
    const s = path.join(src, item);
    if (!fs.existsSync(s)) continue;
    const d = path.join(dest, item);
    fs.rmSync(d, { recursive: true, force: true });
    fs.mkdirSync(path.dirname(d), { recursive: true });
    if (fs.statSync(s).isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
  console.log(`[hj633-aqi] skill 已安装到 ${dest}`);
  console.log("[hj633-aqi] 重启 Claude Code 会话后生效，试试问一个 AQI 计算问题。");
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    if (EXCLUDES.some((re) => re.test(entry.name))) continue;
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

function uninstall() {
  const claudeDir =
    process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), ".claude");
  const dest = path.join(claudeDir, "skills", SKILL_NAME);
  if (!fs.existsSync(dest)) {
    console.log(`[hj633-aqi] 未发现已安装的 skill（${dest}）。`);
    return;
  }
  fs.rmSync(dest, { recursive: true, force: true });
  console.log(`[hj633-aqi] 已移除 ${dest}`);
}

const cmd = process.argv[2];
if (cmd === "uninstall" || cmd === "--uninstall") uninstall();
else install();
