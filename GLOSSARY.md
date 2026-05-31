# GLOSSARY.md (專案詞彙表)

本詞彙表定義了 Notion Agent 專案中的專業術語、環境變數與 Notion 資料庫屬性對照，所有程式碼變數命名必須與本表完全對齊。

---

## 🔑 系統設定與環境變數 (Configuration Variables)

| 中文名稱 | 英文名稱 | 代碼變數名 | 說明 |
| :--- | :--- | :--- | :--- |
| Notion 整合令牌 | Notion Integration Token | `NOTION_API_KEY` | 用於訪問 Notion API 的 Internal Integration Token (例如 `ntn_...`) |
| OpenAI API 金鑰 | OpenAI API Key | `OPENAI_API_KEY` | 用於大語言模型推理的 API Key (例如 `sk-proj-...`) |
| 網路文章資料庫 ID | Notion Database ID | `NOTION_DATABASE_ID` | 網路文章影片筆記資料庫的 UUID 標識符 |
| 預設操作頁面 ID | Notion Page ID | `NOTION_PAGE_ID` | 互動式 Agent 預設綁定的 Notion 頁面識別碼 |

---

## 🗃️ Notion 資料庫屬性對照 (Database Properties)

| 欄位中文名稱 | 欄位英文名稱 | Notion 屬性型態 | 變數/屬性 Key | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| AI 已處理 | AI Processed | Checkbox | `AI_PROCESSED` | 標記該筆文章是否已經過 AI 處理，防止重複處理 |
| AI 摘要 | AI Summary | Rich Text | `AI_SUMMARY` | 存放 AI 提煉的簡短摘要與核心知識點 |
| AI 標籤 | AI Tags | Multi-select | `AI_TAGS` | 存放 AI 自動分類提取的文章主題標籤 |

---

## 🤖 智能體模組定義 (Agent Modules)

| 中文名稱 | 英文名稱 | 程式模組/檔名 | 說明 |
| :--- | :--- | :--- | :--- |
| 互動式 Notion 智能體 | Interactive Notion MCP Agent | `notion_mcp_agent.py` | 透過 MCP 服務器與 Notion 進行自然語言對話的 CLI 程式 |
| 批次增量處理器 | Batch Incremental Processor | `batch_processor.py` | 專門處理大批量（3304筆）文章整理與打標籤的後端腳本 |
| 環境配置檔 | Environment Config | `.env` | 儲存 API 金鑰等敏感資訊的本地配置文件 |
| 依賴套件清單 | Python Dependencies | `requirements.txt` | 專案所需的 Python 套件清單 |
