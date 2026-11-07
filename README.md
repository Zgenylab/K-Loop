# K-Loop｜长项目分轮推进与可恢复交付法

把长任务组织成可核对、可恢复、能够持续推进的工作回合。保持用户目标、真实成果和当前状态一致；通过文件保存执行约定，避免只依赖长聊天中的记忆。

## Overview

K-Loop is a reusable ChatGPT Skill for long-running tasks. It separates planning, batch execution, review, integration, acceptance, and delivery; checkpoints real work to files so the next turn or window can resume from evidence, not assumptions.

- Plan first. Begin K0 only after the user approves the plan.
- Execute K1 in verified, recoverable rounds; do not count unverified work as done.
- Keep `KLOOP_HANDOFF.md` as the stable recovery entrypoint.
- Continue K1 as needed, then review in K2, integrate in K3, verify in K4, and deliver in K5.
- Show a next-step action when the host supports real message actions; otherwise give a copyable prompt. A Skill alone cannot guarantee a clickable button in every client.

## Workflow

| Phase | Purpose | Exit criteria |
| --- | --- | --- |
| K0 初始化 | 按已确认计划登记输入、稳定编号、工作队列、验收要求、状态和恢复入口；建立首个真实检查点 | 基础文件可读、输入清楚、下一工作单元明确；不得把初始化说成主体任务完成 |
| K1 分批执行 | 恢复最新状态，完成合理数量的内部单元，验证并保存累计成果 | 本轮产物、证据和状态一致，真实剩余范围明确 |
| K2 阶段复核 | 在冲突、持续返工、风险集中、重要变更或里程碑时检查覆盖、质量、结构和预算 | 必须修复的问题已处理，剩余问题及计划调整已登记 |
| K3 全局整合 | 在约定范围处理完成后整合内容、接口、命名、索引、重复和历史修正 | 整体一致、范围清楚，未决事项已显式保留 |
| K4 验收 | 按事先约定的标准核对结构、内容或功能、来源、覆盖、状态与恢复 | 明确通过／有条件通过／未通过，列出检查范围、证据、限制与阻断 |
| K5 正式交付 | 从验收版本形成最终成果、使用说明、版本清单、已知限制和恢复资料 | 成果可取得、可打开、符合约定范围；发布阻断已消除 |

## Use the Skill

The portable entrypoint is [`SKILL.md`](SKILL.md). Keep the supporting `agents/`, `scripts/`, and `assets/` files with it. Whether a particular app can install it directly depends on that app's Skill support and import mechanism.

Use these existing example prompts from the Skill:

- 新项目：“使用 K-Loop 规划这个项目。第一轮只给计划，确认后再执行 K0。”
- 确认启动：“确认计划 v1，执行 K0。”
- 普通继续：“执行 K1：处理下一批。”
- 换窗口：“按 K-Loop 从这些交接文件和实际成果恢复，核对最新状态后继续。”
- 插入变更：“保留既有成果，按本次范围插入修订任务；验收后回到原队列。”
- 最终交付：“按 K4 的实际验收结论检查交付条件，满足后执行 K5。”

## Project Files

```text
k-loop/
  README.md
  SKILL.md
  agents/openai.yaml
  assets/icon.svg
  scripts/check_state.py
```

## Validate a K-Loop Project

The state checker requires only Python 3 standard library:

```bash
python3 scripts/check_state.py /path/to/project
```

The check verifies declared state, file existence and selected hashes; it is not a semantic review of the project or proof of end-to-end button operation.

## Download / Distribution

For an installable Skill archive, use the separately packaged `skill.zip` containing the `k-loop/` directory and its files. A GitHub source-code ZIP is not necessarily identical to that archive. Attach the installable `skill.zip` under a GitHub Release for easy download.

## Privacy and Licensing

The reusable Skill files do not include the personal chat archive or project output data. Before publishing further examples or project checkpoints, review them for private or confidential details. This repository template intentionally does not include a `LICENSE` file: choose and add a license before advertising the project as open source. A public GitHub repository alone is not an open-source grant.
