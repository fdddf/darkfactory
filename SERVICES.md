# 服务与 MCP 配置

> 配套 [PLAN.md](PLAN.md)。本文件里所有 URL / 命令都是 2026-10-18 当天从官方文档核对过的,**标 ⚠️ 的需要现场确认**。

---

## 0. 开赛前 30 分钟 checklist

按这个顺序办,因为后面的依赖前面的:

- [ ] **Nebius AI Cloud** 和 **Nebius Token Factory** 是**两个独立账号**,都要注册
- [ ] 在黑客松平台上领 promo code,到 Token Factory 里兑换
- [ ] Token Factory 建 API key → `NEBIUS_API_KEY`
- [ ] 申请 **Sandboxes** 访问(Beta,要审批 —— 越早越好,见 §2)
- [ ] Devin API key(side award 用)
- [ ] n8n 起本地实例 + 建 API key(side award 用)
- [ ] 跑通一次 §1 的 smoke test,确认 key 能用

> ⚠️ Token Factory 注册要绑卡做验证,**部分非 16 位的德国卡会失败**。真失败了去一楼 Nebius 台子或 Discord 现场解决。

---

## 1. Nebius Token Factory(主力推理)

**用途**:pre-check 的测试生成、diff inspection 的 LLM 语义评审、黑盒 fixer 的模型后端。

OpenAI 兼容。本项目用标准库 urllib 直接调,不装 SDK。

| 项 | 值 |
|---|---|
| Base URL | `https://api.tokenfactory.nebius.com/v1/` |
| 认证 | `Authorization: Bearer $NEBIUS_API_KEY` |
| 控制台 | https://tokenfactory.nebius.com |
| 文档 | https://docs.tokenfactory.nebius.com |
| 给 agent 读的索引 | https://docs.tokenfactory.nebius.com/llms.txt |
| Cookbook | https://github.com/nebius/token-factory-cookbook |

```python
import json, os, urllib.request

def complete(payload):
    req = urllib.request.Request(
        "https://api.tokenfactory.nebius.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {os.environ['NEBIUS_API_KEY']}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)
```

SDK 也能用(`pip install openai`,`base_url` 填上面那个),但本项目刻意不装 —— 整个项目零依赖,VM 上少一个会在最糟时刻装失败的轮子。

### 结构化输出(diff inspection 必须用)

支持 `response_format`:
- `{"type": "json_schema"}` —— 严格按 schema
- `{"type": "json_object"}` —— 任意 JSON

> 官方提示:**schema 同时写进 prompt 文本和 `json_schema` 参数**,输出质量明显更好。

模型卡上有 `JSON mode` 标签的才支持,选之前在 playground 确认。

```python
resp = client.chat.completions.create(
    model="<见下>",
    temperature=0,
    response_format={"type": "json_schema", "json_schema": {...}},
    messages=[...],
)
```

### Function calling

文档:https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling.md

### 模型选择

⚠️ **确切的 model id 去 playground 的 catalog 里复制,别手写。** 格式形如 `deepseek-ai/DeepSeek-R1-0528`(vendor/Model-Name)。

赛前文档里点名"已上线且擅长 tool calling"的:

| 用途 | 建议 | 备注 |
|---|---|---|
| **Diff inspection 语义评审** | **Nemotron 3.5 Super VL** 或 **Nemotron 3 Super** | 用 Nemotron 才有资格拿 side award(DGX 卡) |
| 测试生成 | Nemotron 3 Super / DeepSeek / Qwen | 挑 JSON mode + 长上下文的 |
| 便宜的分类/路由 | Nemotron 3 Nano | |
| 黑盒 fixer 后端 | 任意 | 不是交付物,别调 |

目录里还有 DeepSeek、Qwen、Llama、Kimi、MiniMax-M3,以及 Reflection 的 Beam 1.0(搜 "Beam")。

---

## 2. Nebius Sandboxes / Contree(隔离执行 + MCP)⭐

**这是本项目最大的加分项。**

SAP 的 PDF 在 "Future improvements" 里明说缺的就是这个:

> "A runtime sandbox for the agent... scoped file access, no secret access, and a network allowlist, closes that gap. It is out of scope for a one-day build."

Nebius 把它做成了托管服务,所以**我们能在一天内补上出题人自己承认做不完的那块**。

### 它给了什么

- **VM 级隔离**,每次运行独立 compute,可控制给哪些文件、凭据、网络访问
- **Git 式分支**:从同一个 checkpoint 并行试多个补丁,只保留赢的那个 —— 正好对应我们"黑盒产出多个候选 diff,逐个过闸"的场景
- **per-run metrics**,天然可审计 —— 直接灌进我们的 audit trail
- 预装 7000+ SWE 环境(SWE-bench Verified、SWE-rebench)
- 官方 cookbook 里有一篇就叫 **"Compare two fixes"**

### 访问

> ⚠️ **Beta,需要申请**:https://tokenfactory.nebius.com/sandboxes/about
> 现场走不通就去一楼 Nebius 台子,或 Discord。**第一件事就去办,审批要时间。**

### CLI 登录

```bash
uv tool install contree-cli   # 或 pip install contree-cli
contree auth                  # 交互式登录
```

会写入 `~/.config/contree/auth.ini`(权限 0600),MCP server 自动读取。

手写的话:

```ini
[DEFAULT]
profile = default

[profile:default]
type = iam
url = https://api.tokenfactory.nebius.com/sandboxes
token = <TOKEN>
project = <NEBIUS PROJECT ID>
```

### MCP 配置(Claude Code)

```bash
claude mcp add --transport stdio contree -- $(which uvx) contree-mcp
```

验证:`/mcp`

### 可用的 MCP 工具

`run`、`rsync`、`upload`、`download`、`list_files`、`read_file`、`grep`、`import_image`、`list_images`、`get_image`、`set_tag`、`get_operation` / `list_operations` / `wait_operations` / `cancel_operation`、`get_guide`

内置 prompt:`prepare-environment`、`run-python`、`run-shell`

### 在我们架构里的位置

- **黑盒 fixer 跑在 sandbox 里** → 隔离,出网白名单
- **测试也可以跑在 sandbox 里** → 本地 Docker 起不来时的备选方案
- 用分支功能并行试多个候选补丁
- 每次 run 的 metrics 写进 audit

文档:https://docs.tokenfactory.nebius.com/sandboxes/overview.md ·
SWE agents:https://docs.tokenfactory.nebius.com/sandboxes/swe-agents.md ·
MCP:https://docs.tokenfactory.nebius.com/sandboxes/mcp/quickstart.md

---

## 3. NVIDIA Nemotron(side award:DGX 卡)

**参赛条件**:项目里用到 Nemotron 即可。

**我们怎么用**:diff inspection 的 LLM 语义评审层跑在 Nemotron 上,通过 Token Factory 调用。

**为什么这个用法站得住**:安全判定是本项目最吃模型判断力的环节,不是硬塞进去的。README 里要把这点写清楚 —— side award 的评审只看你怎么用。

可选的第二个端点:https://build.nvidia.com

---

## 4. n8n(side award:1 年 Cloud Pro + Cardputer)

**题目要求**(来自 side.md):

> 挑一个具体的真实问题,端到端自动化。AI 用量要省。要扛得住 —— 有 error workflow,边界情况处理好,**不能静默失败**。
> 加分项:用 n8n AI Assistant 构建、通过 **n8n MCP server** 接入自己的 coding agent、用新的 n8n Agent 功能。

**契合点**:"不能静默失败" 跟我们的 escalation gate 是同一件事。整条产线本来就是 workflow。

**怎么用**:把 pre-check → fixer → post-check → deploy 这条编排放进 n8n,每个闸门失败都有显式的 error branch 指向"转人工"。

### 起实例

```bash
docker run -d --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n
```

进 http://localhost:5678 → Settings → n8n API → 建 key。

### n8n MCP 配置(Claude Code)

让 Claude Code 直接帮你建 workflow —— 这就是题目说的"通过 n8n MCP server 接入自己的 coding agent",**是明确的加分项**。

```bash
claude mcp add n8n-mcp \
  -e MCP_MODE=stdio \
  -e LOG_LEVEL=error \
  -e DISABLE_CONSOLE_OUTPUT=true \
  -e N8N_API_URL=http://localhost:5678 \
  -e N8N_API_KEY=<你的 n8n API key> \
  -- npx n8n-mcp
```

不带 `N8N_API_URL` / `N8N_API_KEY` 就只有文档查询工具,不能真的操作 workflow —— **要带上**。

包:`n8n-mcp`(npm,最新 2.94.2)· 源码:https://github.com/czlonkowski/n8n-mcp

---

## 5. Devin(side award:3 个月 Devin Max / 人)

**题目要求**:

> 展示 Devin cloud agents 和 Devin API 能怎么扩展团队能力。**最好的作品会并行跑多个 Devin session,把活交给 Devin 跑。**

**契合点**:我们的黑盒接口本来就是可插拔的 —— 插 Devin,并行开多个 session 同时修多个 bug。天生契合,不需要为了拿奖硬加东西。

### Devin MCP

| 项 | 值 |
|---|---|
| Server URL | `https://mcp.devin.ai/mcp` |
| 认证 | `Authorization: Bearer <API_KEY>` |
| API key 前缀 | **`cog_`**(service user key)。旧的 `apk_` / `apk_user_` **不支持** |
| 企业账号额外需要 | `X-Org-Id` header(org-scoped key 不需要) |

`.mcp.json`:

```json
{
  "mcpServers": {
    "devin": {
      "serverUrl": "https://mcp.devin.ai/mcp",
      "headers": {
        "Authorization": "Bearer <API_KEY>"
      }
    }
  }
}
```

> ⚠️ Claude Code 的 remote MCP 配置字段写法可能是 `type: "http"` + `url`,而不是上面文档里的 `serverUrl`。加完跑 `/mcp` 确认连上了,不对就两种都试。

工具含仓库文档查询(`read_wiki_structure`、`read_wiki_contents`、`ask_question`、`list_available_repos`)和 session / playbook / knowledge / 调度管理。

### 并行 session —— 直接对上评审标准

**Devin Dynamic Workflows**:用确定性的 Python 脚本编排多个 Devin session,fan out、在阶段之间传结构化结果、断点续跑。
https://docs.devin.ai/work-with-devin/dynamic-workflows.md

用法:3 个 trivial bug → 3 个并行 Devin session → 各自产出 diff → 全部进我们的闸门。**demo 里这一幕同时服务主赛道和 side award。**

相关:
- 从 Claude Code 交接给 Devin:https://docs.devin.ai/work-with-devin/devin-handoff.md
- MCP 文档:https://docs.devin.ai/work-with-devin/devin-mcp.md

---

## 6. Nebius AI Cloud(可选)

和 Token Factory 是**不同账号**。本项目不是必须,可选用途:

- **Object Storage** 存 demo 录像、audit 归档、覆盖率映射产物
- **GPU VM** 自托管模型 —— 本项目不需要,别浪费时间

---

## 6.5 Tavily(给 escalation 做取证)

**注意:side award 里没有 Tavily 奖**(只有 Nemotron / n8n / Devin / HF)。加它的理由不是拿奖,是补上一个真实缺口 —— 流水线每一条非放行路径的终点都是人,而那个人拿到的只有一个规则名和行号。

**用法**:只在 inspection 判 reject/escalate 时触发,去查这个漏洞类是什么、WordPress 历史上怎么被打过、公开通告怎么说,带 source 写进 audit。干净跑完全不联网。

```bash
export TAVILY_API_KEY=tvly-...
python3 -m darkfactory.cli run --all --enrich tavily
```

| 项 | 值 |
|---|---|
| 端点 | `POST https://api.tavily.com/search` |
| 认证 | `Authorization: Bearer $TAVILY_API_KEY` |
| 注册 | https://app.tavily.com(免费 1,000 credits/月,不要信用卡) |
| 文档 | https://docs.tavily.com/llms.txt |

检索被 `include_domains` 偏向 wordpress.org / core.trac / wpscan / patchstack / NVD / OWASP(用 `prefer` 模式,不是硬过滤),避免 SEO 垃圾。每次最多研究 3 条 finding,按严重度排序。

没有 key 时返回 `TAVILY_API_KEY is not set`,流水线照常跑完。

---

## 7. 用不上的
- **Reflection Beam / Mirror** —— 绑定 Deep Research 赛道的奖,跟我们无关。
- **Hugging Face Community Award** —— 单独申请:https://huggingface.co/nebius-build-week($5,000 credits,顺手填一下)

---

## 8. 环境变量汇总

`.env.example`:

```bash
# Nebius Token Factory(主力推理)
NEBIUS_API_KEY=
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
MODEL_INSPECTOR=            # Nemotron,从 playground catalog 复制确切 id
MODEL_TESTGEN=              # 测试生成用
MODEL_FIXER=                # 黑盒后端,非交付物

# Nebius Sandboxes(Contree)—— 由 contree auth 写入 ~/.config/contree/auth.ini
NEBIUS_PROJECT_ID=

# Devin(side award)
DEVIN_API_KEY=              # cog_ 开头
DEVIN_ORG_ID=               # 仅企业账号需要

# n8n(side award)
N8N_API_URL=http://localhost:5678
N8N_API_KEY=

# Tavily(escalation 取证)
TAVILY_API_KEY=

# Audit 签名
AUDIT_SIGNING_KEY=
```

**`.env` 进 `.gitignore`。** repo 是公开的,而且我们自己的 diff inspection 里就有一条 secret 扫描 —— 别自己踩自己的规则。

---

## 9. `.mcp.json` 完整样例

放在项目根目录,队友 clone 下来就能用:

```json
{
  "mcpServers": {
    "contree": {
      "command": "uvx",
      "args": ["contree-mcp"]
    },
    "n8n-mcp": {
      "command": "npx",
      "args": ["n8n-mcp"],
      "env": {
        "MCP_MODE": "stdio",
        "LOG_LEVEL": "error",
        "DISABLE_CONSOLE_OUTPUT": "true",
        "N8N_API_URL": "http://localhost:5678",
        "N8N_API_KEY": "${N8N_API_KEY}"
      }
    },
    "devin": {
      "serverUrl": "https://mcp.devin.ai/mcp",
      "headers": {
        "Authorization": "Bearer ${DEVIN_API_KEY}"
      }
    }
  }
}
```

加完跑 `/mcp` 逐个确认。⚠️ 环境变量插值 `${...}` 和 remote server 的字段名在不同客户端版本里有差异,连不上就先硬编码跑通,提交前再换回变量。

---

## 10. README 里必须写清楚的

side award 的评审只看 README,**专门列一节**:

| 服务 | 用在哪 | 为什么 |
|---|---|---|
| Nebius Token Factory | 全部 LLM 推理 | OpenAI 兼容,json_schema 结构化输出 |
| **NVIDIA Nemotron** | diff inspection 的语义评审 | 最吃判断力的环节 |
| **Nebius Sandboxes** | 黑盒 fixer 的隔离运行 + 并行候选补丁 | 补上 PDF 点名的 runtime containment 缺口 |
| **Devin** | 黑盒 fixer 实现,多 session 并行 | 可插拔接口的实证 |
| **n8n** | 产线编排 + error branch | 每个闸门失败都显式转人工,不静默失败 |

---

## 11. PHPUnit 环境(已验证可用)

这台机器上实际跑通的步骤,照抄即可。**不需要 Docker。**

```bash
brew install mariadb && brew services start mariadb

# MariaDB 的 root 走 unix_socket,用 OS 用户连进去建库和专用账号
export PATH="/opt/homebrew/opt/mariadb/bin:$PATH"
mariadb -e "
CREATE DATABASE IF NOT EXISTS wordpress_tests DEFAULT CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'wptests'@'localhost' IDENTIFIED BY 'wptests';
GRANT ALL PRIVILEGES ON wordpress_tests.* TO 'wptests'@'localhost';"

git clone --depth 50 https://github.com/WordPress/wordpress-develop.git wp
cd wp && composer install
sed -e "s/youremptytestdbnamehere/wordpress_tests/" \
    -e "s/yourusernamehere/wptests/" \
    -e "s/yourpasswordhere/wptests/" \
    wp-tests-config-sample.php > wp-tests-config.php
```

验证:

```bash
python3 -c "from darkfactory.runners import PhpUnitRunner; r=PhpUnitRunner('wp'); print(r.backend, r.availability())"
make real
```

已验证的实际耗时(PHPUnit 9.6.38、MariaDB 13.0.2、PHP 8.4.1):

| 选择 | 测试数 | 耗时 |
|---|---|---|
| `formatting/` + `basic.php` | 1753 | 14s |
| `admin/` + `basic.php` | 1179 | 68s |
| 三个 bug 跑完整条线 | — | 86s |

### 两个会静默骗过你的 PHPUnit 坑

都已经在执行器里修掉,但手工跑的时候要知道:

1. **目录选择器必须带 `--test-suffix .php`。** WP 的测试文件叫 `humanTimeDiff.php`,不是 `humanTimeDiffTest.php`。不带这个参数,`phpunit tests/phpunit/tests/formatting` 跑 **0 个测试并退出 0** —— 看起来是绿的。
2. **PHPUnit 9 只认第一个位置参数**,后面的选择器被静默丢弃。所以执行器是逐个选择器调用再合并结果。

### 兜底:扔到 Nebius Sandbox 上跑

```bash
export DF_PHPUNIT_CMD='contree run --image <image-id> -- ./vendor/bin/phpunit {args}'
```

`{args}` 会被替换成 `--log-junit <path> --test-suffix .php <selector>`。流水线其余部分一行都不用改。
