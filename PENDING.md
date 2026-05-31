# PENDING.md (待辦清單與狀態)

本清單用於追蹤 Notion Agent 專案的開發與測試進度。

---

## 📅 開發進度

- [x] **基礎環境準備**
  - [x] 建立 `GLOSSARY.md` 詞彙對齊表
  - [x] 建立 `requirements.txt` 依賴定義
  - [x] 建立 `.env.example` 環境配置範本

- [x] **互動式 Notion MCP Agent (方案 A)**
  - [x] 實作 `notion_mcp_agent.py`，支援多輪對話與 Notion MCP 整合
  - [x] 測試與 Notion 頁面的基本讀寫操作，調整為 gemini-2.5-flash

- [x] **批次增量處理器 (方案 B)**
  - [x] 實作 `batch_processor.py`，串接 Notion Client API (相容 2025-09-03 新版 API)
  - [x] 實作分批讀取與 API Rate Limiting 指數退避重試防禦限制 (適合 Gemini Free Tier)
  - [x] 實作 AI 摘要提取與標籤生成邏輯
  - [x] 實作 AI 屬性更新（`AI 摘要`、`AI 標籤`、`AI 已處理`）與寫回 Notion

- [x] **部署與測試**
  - [x] 編寫詳細的 `README.md` 設定與操作指南 (包含 Step-by-Step 金鑰取得教學)
  - [x] 進行 3 筆的增量提取實測並確認成功寫回 Notion
  - [x] 準備 GitHub 開源分享文件 (`.gitignore`, `LICENSE`)
- [x] **大型全庫提煉**
  - [x] 進行全庫 3304 筆的正式提煉（切換至 DeepSeek 引擎以避開 429 限制，改寫支援分頁自動迴圈處理，已於背景順利運行中）

