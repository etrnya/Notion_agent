# Notion AI 智能笔记与批次知识提炼工具 🤖📝

🌐 **语言切换 (Languages)**: [繁體中文](README.md) | **简体中文** | [English](README_EN.md) | [日本語](README_JA.md) | [한국어](README_KO.md)

本项目提供了一套结合 **自然语言对话 (Interactive Agent)** 與 **大规模批次增量处理 (Batch Processor)** 的 Notion 知识管理方案。

> 💡 **项目出处注明**：
> 本项目的对话式 Agent 模块启动与部分设计启发自 Shubhamsaboo 的开源项目 [awesome-llm-apps/notion_mcp_agent](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/notion_mcp_agent)。本项目在此基础上进行了深度定制，并扩充了大规模批次处理与混合 RAG 专题汇总引擎。

---

## 🌟 核心功能说明

### 1. 海量笔记自动提炼与多维度评估打标签 (Batch Processor)
针对存储数千笔网络文章、电子书、视频笔记的 Notion 原始数据库进行增量批次提炼：
* **增量防重**：自动捞取未处理的文章（`AI已处理` 未勾选），处理完后自动打勾，避免重复消耗 Token。
* **分栏结构化写回**：
  * **【一口话摘要】**：自动写入 Notion 的 **`AI摘要`** 栏位。
  * **【3個核心知識點】**：自动写入 Notion 的 **`AI知識點`** 栏位。
* **多维度评估评分**：
  * 自动推估并写入 **`可信度`** (客观真实性 1-10 分) 与 **`可执行性`** (实践指导性 1-10 分)，若数据库未设定此属性则自动安全降级，不影响流程。
* **空白网址内容自动抓取**：对含有 Facebook 贴文等仅有 URL 但内容为空的卡片，提供自动截取与标题修复功能，随后完成 AI 打标与摘要。

### 2. 双核心多主题 RAG 知识合成与思辨长文 (Knowledge Synthesizer)
针对已经完成摘要与标签化的 Notion 数据库，自动进行跨多篇文章的主题归纳与融合：
* **多维度加权 RAG 排序**：
  * 计算公式：$\text{RAG Score} = 0.4 \times \text{可信度} + 0.3 \times \text{可执行性} + 0.3 \times \text{深受启发(10分/5分)}$。
  * 自动依分数降序排序，精准挑选最合适的 3 篇文献读取 Notion 页面全文作为 RAG 核心 context。
* **恶魔代言人 (Devil's Advocate) 机制**：
  * 引入批判性 LLM，在汇总前针对主流观点生成反对意见、落地痛点与失败案例，并融入最终专题的 **`#### 反向观点與不適用情境`** 区域，防止回音室效应。
* **行动与任务闭环**：
  * 自动解析专题文章末尾的 **`#### 下一步行動計畫 (Action Items)`** Markdown 任务清单。
  * 若设定了 **`NOTION_TASK_DATABASE_ID`**，系统会自动在任务数据库中建立待办任务（截止日期设为 7 天后），并利用 **Relation 属性关联** 回刚刚写入的专题汇总页面。
* **标签清洗与去重**：自动对原始大小写、空格与重叠标签进行清洗与语义对齐，剔除过于宽泛的大型标签（如 `"AI工具"`、`"AI应用"`、`"自动化"` 等），保留高聚焦度的主题。
* **完美 Markdown 格式排版优化**：
  * **多级标题解析**：动态匹配 Markdown 的 `H1` 至 `H6` 标题，自动将 4~6 级标题安全映射为 Notion 支持的 `heading_3`。
  * **文字样式与链接转换**：正确解析 **粗体 (`**`)**、*斜体 (`*`)*、``行内代码`` 为 Notion 内建 Annotations，并将 markdown 链接与行内纯网址 (HTTP/HTTPS) 转换为一键可点击的 Notion 内建链接。
  * **引用关系 Guardrail**：二次校验 LLM 生成的参考文献列表，剔除凭空捏造的幻觉文献，且仅保留正文中有实际被标注引用的来源。

### 3. 知识生命周期自动化代谢与巡检 (Freshness Checker)
* **新鲜度评估**：
  * 读取 **`知識新鮮度`** (A级:长青/B級:一年/C級:半年/D級:三個月) 与 **`最後驗證時間`**。
* **代谢运作**：
  * 对于判定已过期的文章，探测网页 URL 存活率，呼叫 LLM 评估该知识在目前 (2026年) 是否已过时淘汰。
  * **代谢治理决策**：
    * `KEEP`：内容依然有效，自动更新 **`最後驗證時間`** 为今天。
    * `UPDATE` / `ARCHIVE`：需要更新或归档，自动在任务数据库中建立一笔「知识库代谢维护任务」，完成知识库的新陈代谢。

---

## 📖 项目准备与设置指南 (Step-by-Step)

为确保工具能顺利读取与更新您的 Notion 数据库，请依序完成以下步骤：

### 一、 取得 Notion Integration Token (API 密钥)
1. 开启 [Notion Developers 整合管理页面](https://www.notion.so/profile/integrations)。
2. 点击右上角的 **"+ New integration"** (新增整合)。
3. 在设定页面中填写工作区资讯并命名为 `Notion AI Curation Assistant`，点击 **Submit**。
4. 建立后复制 **Secrets** 栏位下的 **Internal Integration Token**（即 `NOTION_API_KEY`）。
5. 切换至 **"Capabilities"**，确保勾选以下核心权限：
   * `Read content` (读取内容)
   * `Update content` (更新内容)
   * `Insert content` (写入内容)

### 二、 取得 Notion 数据库 ID (Database ID)
1. 开启您的 Notion 并前往该原始数据库。
2. 点击页面右上角的 **"Copy link"** (复制连结) 取得网址。
3. 在斜线 `/` 之后、问号 `?` 之前的这串 32 位元字母数字就是您的 Database ID。例如：`981c349065cd4f92bb0ba358b9e0a56d`。

### 三、 在 Notion 中将整合加入连线 (Add Connection)
1. 在浏览器开启该 Notion 数据库或包含该数据库的页面。
2. 点击页面右上角的 **`...`** (三个点) 图示。
3. 滚动至选单最底部，找到 **"Add connections"** (新增连线)。
4. 搜寻并选取您建立的整合（例如：`Notion AI Curation Assistant`），点击 **Confirm**。

### 四、 申请 Google Gemini API 密钥 (GEMINI_API_KEY)
* **推荐做法**：前往 [Google AI Studio](https://aistudio.google.com/)，登入并点击 **"Get API key"**，选择 **"Create API key in a new project"** 即可。

---

### 五、 申请 Agent Platform (前称 Vertex AI) 的服务帐户 JSON 凭证（生产级高速呼叫）
若需要以服务帐户（Service Account）的形式透过企业级 **Agent Platform** 呼叫 Gemini 模型：
1. 登入 [Google Cloud Console](https://console.cloud.google.com/)。
2. 进入 **IAM & Admin** -> **Service Accounts**，建立新服务帐户。
3. 指派 IAM 角色时，搜寻并指派 **`Vertex AI User`** 角色。
4. 在服务帐户的操作选单中，点选 **Manage keys** -> **Add Key** -> **Create new key** 选择 **JSON** 格式下载。
5. 将下载的文件命名为 **`gcp-key.json`**，放置在 `Notion_agent/` 项目根目录下（已被写入 `.gitignore`）。
6. 切换开关：可在 `.env` 中设定 `USE_VERTEX_AI=false` 以停用并降级回退到一般 API Key。

---

## 📥 安装与环境配置

### 1. 安装套件依赖
```powershell
pip install -r requirements.txt
```

### 2. 设定环境变数
将 `.env.example` 复制为 `.env` 文件并填写：
```ini
NOTION_API_KEY=ntn_your_notion_token_here
GEMINI_API_KEY=your_gemini_api_key_here
NOTION_DATABASE_ID=your_database_id_here
# 选填：连动的 Notion 任务管理数据库 ID
NOTION_TASK_DATABASE_ID=your_task_database_id_here
```

---

## 🎯 项目使用方法快速对照表

| 工作情境 (关键字) | 常用 CLI 指令 | 运作说明与最佳实践 |
| :--- | :--- | :--- |
| **在网络文章影片笔记数据库标上AI摘要和AI标签** | `python batch_processor.py --limit <数量> --yes` | **增量 AI 提炼**：自动捞取未处理的文章，以 **Agent Platform** 提炼并分栏回写摘要、标签、可信度与可执行性。 |
| **在AI整理知识库产生汇总性文章** | `python synthesize_knowledge.py --count <篇数>` | **生产级知识汇总**：排除宽泛标签，优先以三维度加权 RAG 评分挑选核心文献，融合恶魔代言人批判，并自动将下一步行动写入 Task DB。 |
| **知识新鲜度过期生命周期自动巡检** | `python freshness_checker.py --yes` | **知识新鲜度巡检**：自动探测过期笔记之 URL 存活率，使用 LLM 评估时效决策，更新验证时间 (KEEP) 或在 Task DB 建立维护任务 (UPDATE/ARCHIVE)。 |
| **空白/无标题 Facebook 页面内容自动抓取补齐** | `python fix_empty_title_and_body_pages.py` | **空白页面修复**：自动从数据库中找出有 URL 但内容为空的卡片，抓取贴文并重构写入。 |
| **停用/启用 GCP JSON 金钥凭证** | 打开 `.env` 修改 `USE_VERTEX_AI` | `USE_VERTEX_AI=true` (优先启动 GCP)；`USE_VERTEX_AI=false` (回退至一般 Key) |
| **乾跑预览 (不写入 Notion)** | `python batch_processor.py --limit 5 --dry-run` | **乾跑模式 (Dry Run)**：仅进行资料捞取与提炼预览。 |
| **自然语言对话式查询与管理** | `python notion_mcp_agent.py` | **对话式 Agent**：直接用自然语言查找、操作数据库。 |
