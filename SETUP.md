# 要去申请的东西

一张清单。**没有任何一项是跑通 demo 的必需品** —— `make platform` 在零 key 的情况下完整跑完三个 bug、出 findings、出报告、审计链可验。下面每一项解锁的是"真实那一份",以及对应的 side award 资格。

按性价比排序。

---

## 1. Nebius Token Factory ⬅ 先办这个

所有模型推理走它。拿到它,语义评审层和测试生成才是真的。

| | |
|---|---|
| 注册 | https://tokenfactory.nebius.com |
| 兑换 | 黑客松平台上领 promo code,进去兑换 |
| 建 key | 控制台 → API keys |
| 环境变量 | `NEBIUS_API_KEY` |
| 接口地址 | `https://api.tokenfactory.nebius.com/v1/` |
| 协议 | OpenAI 兼容,直接用 `openai` SDK |

⚠️ **注册要绑卡做验证,部分非 16 位的德国卡会失败。** 真卡住了去一楼 Nebius 台子或 Discord,他们现场解决。

**还要记一个东西**:在 playground 的 model catalog 里找 Nemotron,把**确切的 model id 复制下来**,填进 `MODEL_INSPECTOR`。

目录里现有的 Nemotron(2026-10-18 实测):

| model id | 备注 |
|---|---|
| `nvidia/Nemotron-3_5-Lightning` | 本项目当前使用。快,`json_schema` 严格模式实测可用 |
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 更小更便宜 |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | 最强,延迟更高;演示时谨慎 |

```
NEBIUS_API_KEY=
MODEL_INSPECTOR=      # Nemotron,从 catalog 复制
MODEL_TESTGEN=        # 可留空,默认跟 MODEL_INSPECTOR 一致
```

**不配的后果**:语义评审层返回 "MODEL_INSPECTOR is not set",按设计 escalate。确定性层照常工作,所以 demo 不受影响。

**自检**(不打印任何密钥):

```bash
python3 -c "
import json,os,urllib.request
from darkfactory.platform import Store
for g in Store().overrides.values():
    for k,v in g.items():
        if v: os.environ[k]=v
base=os.environ.get('NEBIUS_BASE_URL','https://api.tokenfactory.nebius.com/v1/').rstrip('/')
req=urllib.request.Request(base+'/models', headers={'Authorization':'Bearer '+os.environ['NEBIUS_API_KEY']})
ids=[m['id'] for m in json.load(urllib.request.urlopen(req,timeout=20))['data']]
print(len(ids),'models | MODEL_INSPECTOR 在目录里:', os.environ.get('MODEL_INSPECTOR') in ids)
"
```

---

## 2. NVIDIA Nemotron(side award:DGX 卡)

不需要单独的 key —— 通过 Token Factory 调用。你要做的只是把 `MODEL_INSPECTOR` 指向一个 Nemotron 模型。

备用入口(如果 Token Factory 上的 Nemotron 不可用):https://build.nvidia.com

---

## 3. Tavily(给 escalation 做取证)

| | |
|---|---|
| 注册 | https://app.tavily.com |
| 免费额度 | 1,000 credits/月,**不要信用卡** |
| 环境变量 | `TAVILY_API_KEY`(`tvly-` 开头) |
| 接口地址 | `https://api.tavily.com/search` |
| 认证 | `Authorization: Bearer $TAVILY_API_KEY` |

**不配的后果**:Findings 页的 "look up advisories" 按钮会返回 `TAVILY_API_KEY is not set`,其余一切正常。

---

## 4. Devin(side award:3 个月 Devin Max / 人)

| | |
|---|---|
| 注册 | https://devin.ai |
| 建 key | Settings → Devin API → **service user key** |
| 环境变量 | `DEVIN_API_KEY` |
| MCP 地址 | `https://mcp.devin.ai/mcp` |

⚠️ **key 必须是 `cog_` 开头的 service user key。旧的 `apk_` / `apk_user_` 前缀不被支持。**

企业账号还要 `X-Org-Id`(在 Settings → Devin API 页顶部),填 `DEVIN_ORG_ID`;org-scoped key 不需要。

**不配的后果**:黑盒 fixer 用不了 Devin 实现,拿不到这个 side award。流水线用 fixture fixer 照常跑。

⚠️ **2026-10-18 实测:`cog_` 前缀的 key 在 `api.devin.ai/v1/*` 全部返回 403 Unauthorized**,换端点、加 `X-Org-Id` 都一样。前缀本身是对的,所以问题在账号侧 —— 去 Devin 后台确认 key 是否已激活、是否选对了 organization、trial 是否已开通。

---

## 5. n8n(side award:1 年 Cloud Pro + Cardputer)

**n8n 跟这张清单上其它东西不一样 —— 它不是一个你去注册拿 key 的托管服务。**

它是你自己跑的工作流引擎。所以:

- `N8N_API_URL` = **你那个实例的地址**
- `N8N_API_KEY` = **在那个实例的设置页里生成的**

没有实例就没有这两样东西。这就是为什么在 n8n 官网上找不到"API keys"页面。

### 路线 A:本地起(不需要 Docker)

```bash
N8N_USER_FOLDER=/tmp/n8n-home npx -y n8n start
```

首次会下载比较久。起来后:

1. 打开 http://localhost:5678
2. **建一个 owner 账号**(邮箱 + 密码,本地自用随便填)
3. 左下角头像 → **Settings → n8n API** → **Create an API key**

```
N8N_API_URL=http://localhost:5678
N8N_API_KEY=<上一步生成的>
```

### 路线 B:n8n Cloud 试用

https://n8n.io 注册。拿到的工作区地址形如 `https://<你的工作区>.app.n8n.cloud`,那就是 `N8N_API_URL`。

API key 在**同一个位置**:Settings → n8n API → Create an API key。

两条路唯一的区别是 URL,key 的生成位置完全一样。

### 两个容易踩的点

- `N8N_API_URL` 填**实例根地址**(`http://localhost:5678`),**不要带 `/api/v1`** —— 客户端自己会拼。
- n8n 的 REST API 认证走 `X-N8N-API-KEY` 请求头,不是 `Authorization: Bearer`。自己用 curl 试的时候别弄错。

验证:

```bash
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" "$N8N_API_URL/api/v1/workflows" | head -c 200
```

### MCP(side award 的加分项)

题目明确把"通过 n8n MCP server 接入自己的 coding agent"列为加分项:

```bash
claude mcp add n8n-mcp \
  -e MCP_MODE=stdio -e LOG_LEVEL=error -e DISABLE_CONSOLE_OUTPUT=true \
  -e N8N_API_URL=http://localhost:5678 \
  -e N8N_API_KEY=<你的 key> \
  -- npx n8n-mcp
```

不带后两个变量就只有文档查询能力,不能真的建 workflow —— **要带上**。

**不配的后果**:拿不到 n8n 这个 side award,主赛道和其它页面都不受影响。

## 6. Nebius Sandboxes(Beta,要审批 —— 越早办越好)

黑盒 fixer 的 VM 级隔离,补上 SAP 的 PDF 里点名"一天做不完"的那块。

| | |
|---|---|
| 申请 | https://tokenfactory.nebius.com/sandboxes/about |
| 登录 | `uv tool install contree-cli && contree auth` |
| 配置文件 | `~/.config/contree/auth.ini`(权限 0600) |
| 接口地址 | `https://api.tokenfactory.nebius.com/sandboxes` |
| 环境变量 | `NEBIUS_PROJECT_ID` |
| MCP | `claude mcp add --transport stdio contree -- $(which uvx) contree-mcp` |

**要审批,所以第一件事就去提交**,别等到想用的时候。走不通就去一楼 Nebius 台子现场要。

---

## 7. Hugging Face Community Award($5,000 credits)

跟代码无关,单独填表:https://huggingface.co/nebius-build-week

---

## 8. Nebius AI Cloud(部署 VM 用)

和 Token Factory 是**两个独立账号**,都要注册:https://nebius.com

部署照着 `deploy/bootstrap.sh` 走,见 [README](README.md#deploying-on-a-nebius-vm)。

---

## 汇总:`.env`

在项目根目录建 `.env`(已在 `.gitignore` 里),或者直接在平台的 **Integrations 页**填 —— 填完下一次扫描立即生效,不用重启。

```bash
# 1. Token Factory —— 必填项里最重要的
NEBIUS_API_KEY=
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
MODEL_INSPECTOR=            # Nemotron,从 playground catalog 复制确切 id
MODEL_TESTGEN=
MODEL_FIXER=

# 3. Tavily
TAVILY_API_KEY=             # tvly- 开头

# 4. Devin
DEVIN_API_KEY=              # cog_ 开头,service user key
DEVIN_ORG_ID=               # 仅企业账号

# 5. n8n
N8N_API_URL=http://localhost:5678
N8N_API_KEY=

# 6. Sandboxes
NEBIUS_PROJECT_ID=

# 本地:审计链签名。演示前随便设一个非空值。
AUDIT_SIGNING_KEY=

# 本地:装好 PHP 工具链后设为 1,启用 pre-check 的 php -l 闸
DF_REAL_PHP=1
```

---

## 自检

```bash
python3 -c "
from darkfactory.platform import Store
for i in Store().integrations():
    marks = ' '.join(('OK' if v['set'] else '--') + ' ' + v['name'] for v in i['vars'])
    print(f\"{'✓' if i['connected'] else '·'} {i['label']:26} {marks}\")
"
```

平台 **Integrations 页**是同一份信息的界面版,还能直接填。

---

## 一句话优先级

剩的时间不多的话,只办 **1(Token Factory)** 和 **6(Sandboxes,要排队所以先提交)**。3、4、5 都是加分项,各自只影响一个 side award,不影响主赛道。
