# Dark Factory for Bug Resolution — 构建计划

> **赛道**:SAP — Autonomous Bug Resolution(Nebius Build Week × NVIDIA,2026-10-18)
> **提交截止**:18:30(平台自动关闭,不接受迟交)
> **Seed repo**:WordPress core(`wordpress-develop`)

---

## 1. 一句话定位

> 我们不做修 bug 的 agent。我们做的是**让 AI 写的补丁敢于无人审批直接上生产的那层信任机制** —— pre-check、oracle、diff 安全检查、灰度发布、可审计链路。修复器是一个黑盒,随时可替换。

这是题目的原话要求:

> "The bug-fixing agent is the robot arm, and nobody cares how smart the arm is. They care about the interlocks."
> "Teams do not build the whole factory. They build the pre-checks and post-checks around an off-the-shelf coding agent."

**红线:任何时间都不要花在优化黑盒 fixer 上。** 那是明确的 out of scope,会扣分。

---

## 2. 架构

```
┌─────────────┐
│ Bug Report  │  (来自 revert 的真实 WP 历史提交 + Trac 票)
└──────┬──────┘
       ▼
┌─────────────────────────────────────────┐
│ ① PRE-CHECK  准入闸门                     │
│   LLM 生成复现测试 → 必须是"红"的          │
│   四道硬闸全过才放行,否则 → 转人工         │
└──────┬──────────────────────────────────┘
       ▼
┌─────────────────────────────────────────┐
│ ② BLACK BOX  修复器(不属于我们的交付物)   │
│   fix(bug, failing_test, repo) -> diff  │
│   运行在 Nebius Sandboxes 里(隔离)       │
└──────┬──────────────────────────────────┘
       ▼
┌─────────────────────────────────────────┐
│ ③ POST-CHECK  双重验收                   │
│   ③a Oracle      行为正确性               │
│   ③b Diff Inspect 安全性(我们的主场)     │
│   任一不过 → reject + 转人工              │
└──────┬──────────────────────────────────┘
       ▼
┌─────────────────────────────────────────┐
│ ④ GATED DEPLOY  灰度发布                 │
│   feature flag + 10% canary + SLO 自动回滚│
└──────┬──────────────────────────────────┘
       ▼
┌─────────────────────────────────────────┐
│ ⑤ AUDIT TRAIL  哈希链 + 签名,可重放       │
└─────────────────────────────────────────┘

贯穿原则:任何一关"不是明确通过",一律转人工,绝不猜。
```

---

## 3. 组件规格

### ① Pre-check:准入闸门

**作用**:判定这个 bug 是否属于 "trivial"。题目给的定义只有两条 —— 能自动生成复现测试,且修复是小而局部的 diff。

**机制**:让 LLM 生成一个 `WP_UnitTestCase`,跑它,**必须是红的**。

不要让模型凭空写。喂给它:
- 同目录下一个现成的测试文件当 few-shot 模板(按路径启发式捞)
- 被改函数的源码
- WP factory API 速查片段
- 如果 bug 是 revert 来的,当年的测试文件就是最好的模板

**四道硬闸,全过才算复现成功:**

| # | 闸 | 判据 |
|---|---|---|
| 1 | 语法 | `php -l` 通过 |
| 2 | 可执行 | PHPUnit 能加载并运行 |
| 3 | 是红的 | 测试失败 |
| 4 | **红的原因对** | 是 assertion failure,**不是** fatal error / class not found |

第 4 条是关键:跑挂了不等于复现了。

**重试预算 3 次,超了 → escalate。** 那个 nasty bug 就应该死在这里,这是 demo 里最重要的拒绝动作。

**输出**:`{reproduced: bool, test_file, test_name, attempts, reason}`

---

### ② Black box fixer

**接口定死,不要改:**

```python
def fix(bug_report: str, failing_test: Path, repo: Path) -> Diff
```

**实现**(按优先级,插哪个都行,这正是要演示的点):
1. Devin API(并行 session,同时吃 side award)
2. Token Factory 上任意开源模型 + 一个极简 agent loop
3. 兜底:一个写死的脚本

**跑在 Nebius Sandboxes 里**,VM 级隔离。README 里必须显式展示"换一个实现"——这是在向评委证明我们理解了题目。

---

### ③a Oracle:行为正确性

| 检查 | 判据 |
|---|---|
| 复现测试 | red → **green** |
| 回归测试 | 保持 green |
| **测试文件未被修改** | diff 不许触碰 `tests/**` ← 防作弊,必须有 |

**回归测试不跑全量。** WP core 两万多个测试,全量跑会拖死循环。改成**按 diff 选测试**,并且把这个选择本身写进 audit:

> 我们不跑两万个测试。我们跑覆盖了被改动代码的那些测试,并且 audit 记录了这个集合是怎么选出来的。

这不是偷工减料,这正是题目要的 interlock。

**两条路同时上:**
- **立刻可用(路径启发式)**:WP 测试目录镜像源码结构。`wp-includes/formatting.php` → `tests/phpunit/tests/formatting/`。20 行映射表 + 一个永远跑的 smoke 子集。先让链路通。
- **后台并行(覆盖率映射)**:现在就用 pcov 跑一次带 coverage 的基线,导出**源文件 → 测试**的真实映射。约 15:00 出结果,到时替换掉启发式版本。

**Flaky 处理**:显式 quarantine list,写进 policy 文件,体现在 audit 里。
> 不稳定的测试不能充当 oracle。我们隔离它,audit 显示隔离了哪些、为什么。

做法:选中的测试子集连跑 3 遍,不一致的进 quarantine。WP 的典型坑:时区/日期、外部 HTTP、GD 图像、multisite。

---

### ③b Diff Inspection:安全性(本项目的核心)

**双签名制 —— 两层都 pass 才放行,意见不一致 → escalate。**

**第一层:确定性静态检查**

大部分由 WPCS(WordPress-Coding-Standards)现成的安全 sniff 完成:

| Sniff | 漏洞类 |
|---|---|
| `WordPress.Security.NonceVerification` | CSRF |
| `WordPress.Security.EscapeOutput` | XSS |
| `WordPress.Security.ValidatedSanitizedInput` | 输入校验 |
| `WordPress.DB.PreparedSQL` | SQL 注入 |
| `WordPress.PHP.NoSilencedErrors` / `DiscouragedFunctions` | 其他 |

`phpcs --report=json`,按 diff 行号过滤。

额外的确定性规则:

- **Blast radius**:改动文件数 ≤ N,改动行数 ≤ M
- **Protected paths**(见下表),命中直接 reject
- **依赖未变**:`composer.json` / `package-lock.json` 未动
- **无 secret**:熵值 + 模式扫描
- **测试文件未动**

**Protected paths(WP core):**

```
wp-includes/pluggable.php          # 认证,碰了直接 reject
wp-includes/capabilities.php       # 权限
wp-includes/class-wp-user.php
wp-includes/user.php
wp-includes/kses.php               # XSS 过滤
wp-includes/class-wpdb.php         # DB 层
wp-includes/version.php
wp-admin/includes/upgrade.php      # schema
composer.json, package-lock.json   # 依赖
.github/**, *.yml                  # CI
tests/**                           # 测试
```

**第二层:AST + LLM 语义评审**

- `nikic/php-parser` 做 AST:新增危险 sink(`eval`、`extract`、`$$var`、`unserialize`、字符串拼 SQL、新增出网调用)、**权限检查被删除**(`current_user_can` / `check_admin_referer` / nonce 校验在 AST 中消失)
- LLM(Nemotron,temperature=0,`response_format: json_schema`)把 policy 当 context,输出结构化 verdict

**输出 schema:**

```json
{
  "verdict": "allow | reject | escalate",
  "confidence": 0.0,
  "findings": [
    {"rule": "...", "severity": "...", "file": "...", "line": 0, "evidence": "...", "rationale": "..."}
  ]
}
```

确定性检查是主干,LLM 只做增量判断,不做唯一判断。

---

### ④ Gated Deploy

- 两个 WP 实例(Docker),一个 toy 反向代理做 **10% canary** 分流
- 合成流量打几个端点
- SLO:5xx 率 + PHP fatal 出现在 error log
- 越线 → **自动回滚**,结果写入 audit

> "The worst case stays small and undoes itself." —— 这是本层的验收标准。

---

### ⑤ Audit Trail

- append-only JSONL,**每条记录带上一条的 sha256(哈希链)**
- 用一个 key 签名
- `replay <bug_id>` CLI + 一个时间线 Web UI

**现场杀手锏**:让评委手改 audit 里的一个字节,哈希链立刻断。十行代码,效果极强。

每条记录必须包含:bug、qualification 决策、diff、验收证据、部署结果。

---

## 4. 三个种子 bug(demo 的全部内容)

**bug 来源:revert 真实的 WP 历史修复提交。**

```bash
git log --oneline --grep="Fixes #" -- wp-includes/ | head -50
```

revert 一个,你同时拿到:真实 bug、真实 bug report(commit message 里有 Trac 票号)、官方正确修法、当年随补丁提交的测试。

> 台词:"我们的 bug 集不是造的,是 WordPress 真实的历史回归。"

| # | 类型 | 预期结果 | 证明了什么 |
|---|---|---|---|
| **A** | 普通 trivial bug(×3) | 端到端自动修复、验收、灰度上线、入 audit,**全程无人触碰** | 产线能跑 |
| **B** | Nasty bug —— 测试生成不出来 / 生成了但不红 | **卡在 pre-check,转人工** | 系统知道自己的边界 |
| **C** | **修得对但不安全** | **Oracle 判绿 ✅,Diff Inspection 判红 🛑** | 光有测试不够,安全层不是冗余 |

**C 是整个 demo 的高潮,优先级仅次于打通链路。**

构造方式:revert 一个当年**加了 `current_user_can()` 检查**的安全补丁 → bug report 变成"某些用户操作失败" → 黑盒最省事的修法是放宽或删掉这个检查 → 回归全绿 → diff inspection 判定提权,拒绝。

---

## 5. 范围切割

### 必做(砍了就不成立)
- ① Pre-check 四道闸
- ③a Oracle(含测试文件保护)
- ③b Diff Inspection 双签名
- ⑤ Audit 哈希链
- bug A / B / C 三条链路

### 加分(有余力才做)
- ④ Gated deploy 真的 canary + 回滚
- Sandbox 出网白名单(题目 PDF 点名的 "obvious next step")
- 覆盖率精确映射(替换启发式)
- 时间线 Web UI

### 不做
- ❌ 优化黑盒 fixer(明确 out of scope)
- ❌ 跑 WP 全量测试套件
- ❌ multisite
- ❌ 花哨的仪表盘

---

## 6. 时间表

| 时间 | 内容 |
|---|---|
| **立刻** | 后台拉 WP 环境(见下)+ 申请 Sandboxes 访问 + 领 Token Factory promo code |
| –14:30 | 定死接口 schema(`fix()`、`Verdict`、audit 记录格式),从 git log 挑 bug 候选 |
| 14:30–16:00 | **四路并行**(见分工) |
| 16:00–16:45 | **打通第一条端到端链路**(bug A) |
| 16:45–17:15 | bug B + bug C(gated deploy 有时间才做) |
| 17:15–17:50 | 彩排 + 录 2 分钟视频 |
| 17:50–18:15 | README(评委要能跑起来)+ 提交 |
| 18:15–18:30 | 纯缓冲 |

> 本表按 **14:13** 起算,剩余 4h17m。比原计划压缩,④ gated deploy 已降级为"有余力才做"。

**硬规矩:16:00 还没打通第一条链路,立刻砍掉 ④ gated deploy**,只保留 flag + 回滚的模拟。audit 和 diff inspection 不能砍,那是题目的核心。

**立刻执行:**

```bash
git clone --depth 50 https://github.com/WordPress/wordpress-develop.git wp && cd wp && npm install && npm run env:start
```

用 `wordpress-develop`,不要用 `wordpress/wordpress` —— 测试套件和 Docker 环境都在这个 repo 里,省掉 svn 那套老 scaffolding。之后 `npm run test:php` 直接能跑。

---

## 7. 分工(2–4 人)

| 角色 | 负责 | 关键路径 |
|---|---|---|
| **A** | seed repo:revert 种 bug、quarantine 跑 3 遍、后台 coverage 映射 | |
| **B** | ① pre-check 四道闸 + ③a oracle 选测试 | ⚠️ 关键路径 |
| **C** | ③b diff inspection:phpcs + AST + LLM 双签名 | ⚠️ 关键路径 |
| **D** | ⑤ audit 哈希链 + 时间线 UI + ④ gated deploy;全程负责 demo 和 README | |

只有 2 人:B + C 各一人,A 和 D 的内容压缩后分摊。
只有 3 人:A 合并进 D。

---

## 8. Demo 脚本(2 分钟,PDF 原样给的)

> Seed a repo with a handful of trivial bugs and one genuinely nasty one. The system resolves the trivial bugs end to end, from bug report to verified fix to deployed change to audit entry, while people watch and touch nothing. Then it hits the nasty bug, refuses it, and escalates to a human.

| 秒 | 画面 |
|---|---|
| 0:00–0:15 | 问题陈述:能修 bug 的 agent 已经不稀奇,没人敢让它直接上线。这是信任问题不是能力问题 |
| 0:15–0:25 | 架构一张图,强调 fixer 是黑盒 |
| 0:25–1:00 | **bug A 全自动跑通**:bug report → 生成复现测试(红)→ 黑盒 → oracle 绿 → diff 检查过 → canary → audit 入链。全程没人碰键盘 |
| 1:00–1:20 | **bug B 被拒**:测试生成不出来,pre-check 拦截,escalate 给人 |
| 1:20–1:45 | **bug C —— 高潮**:测试全绿,但 diff inspection 发现权限检查被删,判定提权,拒绝并升级 |
| 1:45–2:00 | audit 时间线:现场手改一个字节,哈希链断裂。结尾一句:信任在系统里,不在那个黑盒里 |

**拍摄规矩:**
- 视频里录真跑的,**现场答辩用 replay 模式**(从 audit 回放),不依赖实时模型调用
- bug C 的拒绝瞬间**不许剪掉**,那是整个 demo 的价值所在

---

## 9. 风险与降级预案

| 风险 | 预案 |
|---|---|
| Docker 环境起不来 | 最大的单点。立刻开始拉,别等。备选:直接用 Nebius Sandboxes 跑测试 |
| 回归测试太慢 | 已设计:按 diff 选测试。再不行就只跑 smoke 子集,并在 audit 里声明范围 |
| Flaky 假阴性 | quarantine list。demo 前把三个 bug 的链路各跑 3 遍确认稳定 |
| LLM 生成不出红测试 | 重试 3 次后 escalate —— **这本身就是功能**,不是失败 |
| LLM 判定不稳定 | temperature=0 + json_schema + 确定性检查当主干 |
| Sandboxes 还在 Beta,拿不到权限 | 去一楼 Nebius 台子现场要;拿不到就退回本地 Docker,只是少一个加分项 |
| 时间不够 | 按第 5 节的"加分"清单从下往上砍 |

---

## 10. 交付物清单

- [ ] 公开 GitHub repo,README 评委能照着跑起来
- [ ] 2 分钟 demo 视频
- [ ] 平台提交(**18:30 自动关闭**)
- [ ] README 里显式写出黑盒接口,并演示换实现
- [ ] README 里说明用到的 Nebius / NVIDIA / n8n / Devin(side award 评审看这个)
- [ ] 队伍 2–4 人

服务配置、API key、MCP 设置见 [SERVICES.md](SERVICES.md)。
