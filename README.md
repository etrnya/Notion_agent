# Notion AI 智慧筆記與批次知識提煉工具 🤖📝

🌐 **語言切換 (Languages)**: **繁體中文** | [简体中文](README_ZH.md) | [English](README_EN.md) | [日本語](README_JA.md) | [한국어](README_KO.md)

本專案提供了一套結合 **自然語言對話 (Interactive Agent)** 與 **大規模批次增量處理 (Batch Processor)** 的 Notion 知識管理方案。

> 💡 **專案出處註明**：
> 本專案的對話式 Agent 模組啟動與部分設計啟發自 Shubhamsaboo 的開源專案 [awesome-llm-apps/notion_mcp_agent](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/notion_mcp_agent)。本專案在此基礎上進行了深度客製化，並擴充了大規模批次處理與混合 RAG 專題彙整引擎。

---

## 🌟 核心功能說明

### 1. 海量筆記自動提煉與多維度評估打標籤 (Batch Processor)
針對儲存數千筆網路文章、電子書、影片筆記的 Notion 原始資料庫進行增量批次提煉：
* **增量防重**：自動撈取未處理的文章（`AI已處理` 未勾選），處理完後自動打勾，避免重複消耗 Token。
* **分欄結構化寫回**：
  * **【一句話摘要】**：自動寫入 Notion 的 **`AI摘要`** 欄位。
  * **【3個核心知識點】**：自動寫入 Notion 的 **`AI知識點`** 欄位。
* **多維度評估評分**：
  * 自動推估並寫入 **`可信度`** (客觀真實性 1-10 分) 與 **`可執行性`** (實踐指導性 1-10 分)，若資料庫未設定此屬性則自動安全降級，不影響流程。
* **空白網址內容自動抓取**：對含有 Facebook 貼文等僅有 URL 但內容為空的卡片，提供自動擷取與標題修復功能，隨後完成 AI 打標與摘要。

### 2. 雙核心多主題 RAG 知識合成與思辨長文 (Knowledge Synthesizer)
針對已經完成摘要與標籤化的 Notion 資料庫，自動進行跨多篇文章的主題歸納與融合：
* **多維度加權 RAG 排序**：
  * 計算公式：$\text{RAG Score} = 0.4 \times \text{可信度} + 0.3 \times \text{可執行性} + 0.3 \times \text{深受啟發(10分/5分)}$。
  * 自動依分數降序排序，精準挑選最合適的 3 篇文獻讀取 Notion 頁面全文作為 RAG 核心 context。
* **惡魔代言人 (Devil's Advocate) 機制**：
  * 引入批判性 LLM，在彙整前針對主流觀點生成反對意見、落地痛點與失敗案例，並融入最終專題的 **`#### 反向觀點與不適用情境`** 區塊，防止回音室效應。
* **行動與任務閉環**：
  * 自動解析專題文章末尾的 **`#### 下一步行動計畫 (Action Items)`** Markdown 任務清單。
  * 若設定了 **`NOTION_TASK_DATABASE_ID`**，系統會自動在任務資料庫中建立待辦任務（截止日期設為 7 天後），並利用 **Relation 屬性關聯** 回剛剛寫入的專題彙整頁面。
* **標籤清洗與去重**：自動對原始大小寫、空白與重疊標籤進行清洗與語意對齊，剔除過於寬泛的大型標籤（如 `"AI工具"`、`"AI應用"`、`"自動化"` 等），保留高聚焦度的主題。
* **完美 Markdown 格式排版優化**：
  * **多級標題解析**：動態匹配 Markdown 的 `H1` 至 `H6` 標題，自動將 4~6 級標題安全映射為 Notion 支援的 `heading_3`。
  * **文字樣式與連結轉換**：正確解析 **粗體 (`**`)**、*斜體 (`*`)*、``行內程式碼`` 為 Notion 內建 Annotations，並將 markdown 連結與行內純網址 (HTTP/HTTPS) 轉換為一鍵可點擊的 Notion 內建連結。
  * **引用關係 Guardrail**：二次校驗 LLM 生成的參考文獻列表，剔除憑空捏造的幻覺文獻，且僅保留正文中有實際被標註引用的來源。

### 3. 知識生命週期自動化代謝與巡檢 (Freshness Checker)
* **新鮮度評估**：
  * 讀取 **`知識新鮮度`** (A級:長青/B級:一年/C級:半年/D級:三個月) 與 **`最後驗證時間`**。
* **代謝運作**：
  * 對於判定已過期的文章，探測網頁 URL 存活率，呼叫 LLM 評估該知識在目前 (2026年) 是否已過時淘汰。
  * **代謝治理決策**：
    * `KEEP`：內容依然有效，自動更新 **`最後驗證時間`** 為今天。
    * `UPDATE` / `ARCHIVE`：需要更新或歸檔，自動在任務資料庫中建立一筆「知識庫代謝維護任務」，完成知識庫的新陳代謝。

---

## 📖 專案準備與設定指南 (Step-by-Step)

為確保工具能順利讀取與更新您的 Notion 資料庫，請依序完成以下步驟：

### 一、 取得 Notion Integration Token (API 金鑰)
1. 開啟 [Notion Developers 整合管理頁面](https://www.notion.so/profile/integrations)。
2. 點擊右上角的 **"+ New integration"** (新增整合)。
3. 在設定頁面中填寫工作區資訊並命名為 `Notion AI Curation Assistant`，點擊 **Submit**。
4. 建立後複製 **Secrets** 區塊下的 **Internal Integration Token**（即 `NOTION_API_KEY`）。
5. 切換至 **"Capabilities"**，確保勾選以下核心權限：
   * `Read content` (讀取內容)
   * `Update content` (更新內容)
   * `Insert content` (寫入內容)

### 二、 取得 Notion 資料庫 ID (Database ID)
1. 開啟您的 Notion 並前往該原始資料庫。
2. 點擊頁面右上角的 **"Copy link"** (複製連結) 取得網址。
3. 在斜線 `/` 之後、問號 `?` 之前的這串 32 位元字母數字就是您的 Database ID。例如：`981c349065cd4f92bb0ba358b9e0a56d`。

### 三、 在 Notion 中將整合加入連線 (Add Connection)
1. 在瀏覽器開啟該 Notion 資料庫或包含該資料庫的頁面。
2. 點擊頁面右上角的 **`...`** (三個點) 圖示。
3. 滾動至選單最底部，找到 **"Add connections"** (新增連線)。
4. 搜尋並選取您建立的整合（例如：`Notion AI Curation Assistant`），點擊 **Confirm**。

### 四、 申請 Google Gemini API 金鑰 (GEMINI_API_KEY)
* **推薦做法**：前往 [Google AI Studio](https://aistudio.google.com/)，登入並點擊 **"Get API key"**，選擇 **"Create API key in a new project"** 即可。

---

### 五、 申請 Agent Platform (前稱 Vertex AI) 的服務帳戶 JSON 憑證（生產級高速呼叫）
若需要以服務帳戶（Service Account）的形式透過企業級 **Agent Platform** 呼叫 Gemini 模型：
1. 登入 [Google Cloud Console](https://console.cloud.google.com/)。
2. 進入 **IAM & Admin** -> **Service Accounts**，建立新服務帳戶。
3. 指派 IAM 角色時，搜尋並指派 **`Vertex AI User`** 角色。
4. 在服務帳戶的操作選單中，點選 **Manage keys** -> **Add Key** -> **Create new key** 選擇 **JSON** 格式下載。
5. 將下載的檔案命名為 **`gcp-key.json`**，放置在 `Notion_agent/` 專案根目錄下（已被寫入 `.gitignore`）。
6. 切換開關：可在 `.env` 中設定 `USE_VERTEX_AI=false` 以停用並降級回退到一般 API Key。

---

## 📥 安裝與環境配置

### 1. 安裝套件依賴
```powershell
pip install -r requirements.txt
```

### 2. 設定環境變數
將 `.env.example` 複製為 `.env` 檔案並填寫：
```ini
NOTION_API_KEY=ntn_your_notion_token_here
GEMINI_API_KEY=your_gemini_api_key_here
NOTION_DATABASE_ID=your_database_id_here
# 選填：連動的 Notion 任務管理資料庫 ID
NOTION_TASK_DATABASE_ID=your_task_database_id_here
```

---

## 🎯 專案使用方法快速對照表

| 工作情境 (關鍵字) | 常用 CLI 指令 | 運作說明與最佳實踐 |
| :--- | :--- | :--- |
| **在網路文章影片筆記資料庫標上AI摘要和AI標籤** | `python batch_processor.py --limit <數量> --yes` | **增量 AI 提煉**：自動撈取未處理的文章，以 **Agent Platform** 提煉並分欄回寫摘要、標籤、可信度與可執行性。 |
| **在AI整理知識庫產生彙整性文章** | `python synthesize_knowledge.py --count <篇數>` | **生產級知識彙整**：排除寬泛標籤，優先以三維度加權 RAG 評分挑選核心文獻，融合惡魔代言人批判，並自動將下一步行動寫入 Task DB。 |
| **知識新鮮度過期生命週期自動巡檢** | `python freshness_checker.py --yes` | **知識新鮮度巡檢**：自動探測過期筆記之 URL 存活率，使用 LLM 評估時效決策，更新驗證時間 (KEEP) 或在 Task DB 建立維護任務 (UPDATE/ARCHIVE)。 |
| **空白/無標題 Facebook 頁面內容自動抓取補齊** | `python fix_empty_title_and_body_pages.py` | **空白頁面修復**：自動從資料庫中找出有 URL 但內容為空的卡片，抓取貼文並重構寫入。 |
| **停用/啟用 GCP JSON 金鑰憑證** | 打開 `.env` 修改 `USE_VERTEX_AI` | `USE_VERTEX_AI=true` (優先啟動 GCP)；`USE_VERTEX_AI=false` (回退至一般 Key) |
| **乾跑預覽 (不寫入 Notion)** | `python batch_processor.py --limit 5 --dry-run` | **乾跑模式 (Dry Run)**：僅進行資料撈取與提煉預覽。 |
| **自然語言對話式查詢與管理** | `python notion_mcp_agent.py` | **對話式 Agent**：直接用自然語言查找、操作資料庫。 |

---

## 🚀 未來藍圖：Notion Agent V3 & V3.5 決策知識管理體系 (DKMS)

針對當前 RAG 知識彙整系統面臨的關鍵盲點，本專案已設計了 **V3 & V3.5 決策知識管理體系 (Decision Knowledge Management System)** 架構藍圖。系統將從簡單的「收藏 -> 摘要」演進為協助決策的研究智能體，核心設計包括：

1. **決策記憶與失效提醒 (Decision Memory)**：結構化記錄決策與其背景前提假設，在外部假設失效（如團隊擴大）時自動建立重審任務，引導未來決策。
2. **可解釋性報告層 (Explainability Layer)**：每篇專題自動附帶選擇與淘汰文獻原因的報告，防止多層系統淪為無法 Debug 的黑箱。
3. **資料血統追溯 (Data Lineage)**：在 Claim Pool 的 JSON 中記錄精確引文 (`evidence_quote`) 與物理位置 (`provenance`)，實現「觀點 -> 原始段落」的三級血統追溯。
4. **領域自適應時間衰減 (Domain-Aware Freshness)**：根據學門特徵（如 AI 快速更迭 vs. 心理學經典常青）動態配置時間衰減係數，避免歧視經典文獻。
5. **情境脈絡對比 (Context Graph)**：提取 Claims 所在的情境變數（如團隊規模、專案大小），輸出「情境對比」而非一味判斷是非對錯。

> 📖 **詳細架構與研發 Roadmap 請參閱**：
> [Notion Agent V3 & V3.5 決策知識管理體系 (DKMS) 架構演進與設計藍圖](file:///c:/Users/etrny/.gemini/antigravity/scratch/Notion_agent/V3_ARCHITECTURE.md)

