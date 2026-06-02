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

- [x] **V3 ~ V3.8 DKMS 架構整合 (2026-06-02)**
  - [x] **Domain-Aware Temporal Layer (V3.8)**：新增 `DOMAIN_DECAY_MAP` 與 `compute_freshness_score()`，根據文章領域（AI/軟體工程/管理/哲學等）動態計算時間衰減係數
  - [x] **TRS/QS 分離評分 (V3)**：QS（Quality Score = 原 RAG Score）與 TRS（Topic Relevance Score，以關鍵字命中率為啟發式代理）分離計算，Final Score = (0.7×TRS + 0.3×QS) × freshness
  - [x] **Fact Layer / Claim Pool (V3.5)**：新增 `extract_claim_pool()`，對每篇核心文獻提取含 `evidence_quote`、`evidence_type`、`confidence` 的結構化 JSON 主張池
  - [x] **Explainability Layer (V3.5)**：新增 `generate_explainability_report()`，每篇專題自動在文章開頭附帶選中與淘汰文獻的可解釋性報告（含 TRS、freshness、final_score、reject_reason）
  - [x] **Decision Memory (V3.5)**：新增 `generate_decision_memory()`，在文章末尾生成含 `decision`、`because`、`revisit_triggers` 的決策記憶 JSON 區塊
  - [x] **Context Graph / 情境脈絡對比 (V3.8)**：在 `ask_llm()` prompt 中強制要求 LLM 在發現文獻結論情境差異時輸出 `⚖️ 【情境差異對比 (Context Graph)】` 而非是非判斷
  - [x] **Synthesis/Hypothesis 雙軌輸出 (V3.5)**：在 `ask_llm()` prompt 中強制要求 LLM 區分並輸出 `💡 【跨文獻綜合發現 (Synthesis)】` 與 `🔮 【研究假說 (Hypothesis)】`

## 🧪 測試結果
- [x] 執行 `python synthesize_knowledge.py --count 1` 進行端對端整合測試，確認 Fact Layer、Explainability Report、Decision Memory、Task DB 寫入與智慧分層抽樣皆已正常運作且寫回 Notion 成功。
