# Notion AI Smart Notes & Batch Knowledge Synthesis Tool 🤖📝

🌐 **Languages**: [繁體中文](README.md) | [简体中文](README_ZH.md) | **English** | [日本語](README_JA.md) | [한국어](README_KO.md)

This project provides a comprehensive Notion knowledge management solution combining an **Interactive Agent (Natural Language Dialogue)** and a **Large-scale Batch Incremental Processor**.

> 💡 **Project Citations**:
> The interactive Agent module and parts of the workflow design in this repository are inspired by and adapted from Shubhamsaboo's open-source project [awesome-llm-apps/notion_mcp_agent](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/notion_mcp_agent). This project extends it by adding large-scale batch database updates and hybrid RAG knowledge synthesis engines.

---

## 🌟 Core Features

### 1. Large-scale Note Summarization & Auto-tagging (Batch Processor)
Perform incremental batch processing on your source database containing thousands of web articles, e-books, and video notes:
* **Incremental Processing**: Automatically query unprocessed notes (`AI已處理` unchecked) and mark them as processed afterwards to prevent token waste and duplicated writes.
* **Structured Property Writes**:
  * **"One-sentence Summary"**: Written to Notion's **`AI摘要`** property.
  * **"3 Core Knowledge Points"**: Written to Notion's **`AI知識點`** property.
* **Auto-scraping for Empty URLs**: Detect and automatically scrape contents from empty card entries (e.g. Facebook shares) using their URLs, reconstruct titles, and generate summaries and tags.

### 2. Production-Grade Knowledge Synthesis & Synthesis Articles (Knowledge Synthesizer)
Automatically cluster, normalize, and synthesize already summarized and tagged pages into comprehensive knowledge topics:
* **Tag Cleaning & De-duplication**: Clean casing, spaces, and duplicate tags while filtering out overly broad categories (e.g., `"AI工具"`, `"AI應用"`, `"自動化"`) to keep topics highly focused.
* **"Inspired" Article Priority**: Automatically detect pages flagged with the "Inspired" (`深受啟發`) property. The system **prioritizes choosing topics containing inspired articles** and **retrieves the full text of inspired articles** as RAG core context.
* **Stunning Markdown Layout Optimization**:
  * **Header Levels Parsing**: Support H1-H6 headers. Automatically strip hashes and safely map levels H4-H6 down to Notion's H3 (`heading_3`) for proper font sizing.
  * **Rich Text Formatting conversion**: Parse **bold (`**`)**, *italic (`*`)*, and ``inline code`` syntax into Notion Text Annotations. This ensures bold text displays cleanly without markdown syntax clutter.
  * **Automatic Hyperlink Conversion**: Capture both Markdown-style links `[Text](URL)` and raw inline **URLs (HTTP/HTTPS)** and convert them into clickable blue hyperlinks in Notion.
  * **Citations Guardrail**: Cross-verify LLM generated bibliographies to eliminate hallucinations and retain only sources actually cited in the text, ensuring accurate URLs.

---

## 📖 Step-by-Step Configuration Guide

Follow these steps to connect your Notion database and API keys:

### 1. Get Notion Integration Token (API Key)
1. Visit the [Notion Developers Integrations Dashboard](https://www.notion.so/profile/integrations).
2. Click **"+ New integration"** in the top right.
3. Choose your workspace, name it `Notion AI Curation Assistant`, and click **Submit**.
4. Copy the **Internal Integration Token** (e.g., `ntn_...`) under the **Secrets** section. This is your `NOTION_API_KEY`.
5. Under **"Capabilities"**, ensure the following permissions are checked:
   * `Read content`
   * `Update content`
   * `Insert content`

### 2. Get Notion Database ID
1. Open your Notion database in the browser.
2. Click the **"Copy link"** button in the top right.
3. The 32-character alphanumeric sequence following the workspace name slash `/` and preceding the question mark `?` is your Database ID. Example: `981c349065cd4f92bb0ba358b9e0a56d`.

### 3. Add Connection in Notion
1. Open the target Notion database page.
2. Click the **`...`** (three dots) icon in the top right.
3. Scroll down and click **"Add connections"**.
4. Search and select your integration name (e.g., `Notion AI Curation Assistant`), then click **Confirm**.

### 4. Get Google Gemini API Key
* **Recommended**: Go to [Google AI Studio](https://aistudio.google.com/), log in, and click **"Get API key"** -> **"Create API key in a new project"**.

### 5. Configure Agent Platform (formerly Vertex AI) Service Account JSON Credentials
If you prefer enterprise-grade call speeds using GCP Service Accounts:
1. Log in to [Google Cloud Console](https://console.cloud.google.com/).
2. Navigate to **IAM & Admin** -> **Service Accounts** and create a new account.
3. For IAM roles, search and assign the **`Vertex AI User`** role.
4. In the service account options, click **Manage keys** -> **Add Key** -> **Create new key** and select **JSON**.
5. Save the downloaded file as **`gcp-key.json`** in the `Notion_agent/` root directory (it is already ignored in `.gitignore`).
6. Toggle switch: Adjust `USE_VERTEX_AI=false` in `.env` if you want to fall back to the standard API Key.

---

## 📥 Installation & Environment Setup

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in the values:
```ini
NOTION_API_KEY=ntn_your_notion_token_here
GEMINI_API_KEY=your_gemini_api_key_here
NOTION_DATABASE_ID=your_database_id_here
```

---

## 🎯 Quick Command Cheat Sheet

| Work Scenario (Keywords) | CLI Command | Description & Best Practices |
| :--- | :--- | :--- |
| **Apply AI Summary and Tagging to Notes DB** | `python batch_processor.py --limit <amount> --yes` | **Incremental AI extraction**: Auto-fetch unprocessed pages and update the `AI摘要` and `AI知識點` properties. |
| **Generate Synthesis Articles in Curation DB** | `python synthesize_knowledge.py --count <amount>` | **Production-grade RAG Synthesis**: Filter broad tags, prioritize "Inspired" articles as full-text RAG context, and write custom synthesized posts. |
| **Scrape & Fix Empty Facebook/Webpages** | `python fix_empty_title_and_body_pages.py` | **Empty Page Auto-repair**: Detect empty cards with valid URLs, scrape contents, restore titles, and trigger AI processing. |
| **Enable/Disable GCP JSON Key** | Edit `USE_VERTEX_AI` in `.env` | `USE_VERTEX_AI=true` (GCP prioritized); `USE_VERTEX_AI=false` (Gemini API Key fallback). |
| **Dry Run Mode (No Notion writes)** | `python batch_processor.py --limit 5 --dry-run` | **Preview Mode**: Fetch and show AI responses without writing updates to Notion. |
| **Interactive Query via Natural Language** | `python notion_mcp_agent.py` | **Interactive CLI Agent**: Manage, query, and edit your Notion database using natural language. |
