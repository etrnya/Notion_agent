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

## 🚀 Notion Agent V3.5/V3.8 決策知識管理體系 (DKMS) 全面落地

本專案已全面實作 **決策知識管理體系 (DKMS, Decision Knowledge Management System)**，系統已從簡單的「收藏 -> 摘要」轉變為協助決策的研究智能體。核心架構與特點包括：

### 1. 智慧品質過濾與分層抽樣 (Smart Sampling)
針對擁有 3000+ 筆資料的大型知識庫，如果將所有文章傳給 LLM 會超過 Token 上限且破壞聚焦度。本系統設計了**智慧分層抽樣**機制：
* **深受啟發優先**：主觀標記為「深受啟發」的文章擁有最高優先級，會優先保證全數納入（預設上限 60 篇）。
* **分層比例抽樣**：其餘文章以 `QS` (Quality Score) 過濾後，按 AI 自動提取的標籤領域進行分層比例抽樣，維持跨領域的多元性。
* **隨機打亂**：隨機化打亂素材排序送至 LLM，避免排列偏差影響主題聚類與合成。
* **指令參數**：
  ```bash
  python synthesize_knowledge.py --max-source 2000 --sample-size 400 --min-qs 5.0
  ```

### 2. 領域自適應時間衰減 (Domain-Aware Temporal Layer)
* 避免一刀切的時間衰減（這會歧視常青文獻）。
* 根據文章標籤自動對應不同的衰減係數 $\lambda$：
  * **AI/LLM**: $\lambda = 0.80$ (衰減極快，時效性高)
  * **軟體工程/架構**: $\lambda = 0.50$ (中等偏快)
  * **管理/領導力**: $\lambda = 0.05$ (衰減極慢)
  * **哲學/心理學**: $\lambda = 0.00$ (不衰減，常青經典)

### 3. 事實提取層與資料血統追溯 (Fact Layer with Data Lineage)
* 在主合成前，對每篇核心文獻提煉出含 `evidence_quote`、`evidence_type` (`fact`/`opinion`/`speculation`)、`confidence` 的結構化 Claims Pool (JSON)。
* 確保每一句合成結論皆能上溯至資料庫的物理血統。

### 4. 惡魔代言人批判思辨 (Devil's Advocate)
* 引入批判性 LLM 機制，在彙整前針對主流觀點生成反對意見、落地痛點與失敗案例，並融入最終專題的 **`#### 反向觀點與不適用情境`** 區塊，防止回音室效應與盲目跟風。

### 5. 可解釋性報告 (Explainability Layer)
* 每篇專題文章開頭自動附帶「可解釋性報告」，列出本次核心文獻的篩選指標（TRS、QS、freshness、final_score），以及淘汰其他文獻的原因，讓系統完全透明可 Debug。

### 6. 決策記憶與失效提醒 (Decision Memory)
* 每篇專題文章底端附帶結構化的 **Decision Memory (決策記憶)** JSON 區塊，記錄決策的背景假設前提（`revisit_triggers`）。當外部假設失效時，系統可快速重審該決策。

### 7. 任務與行動閉環 (Task DB Integration)
* 自動解析專題文章末尾的 Action Items，自動於任務資料庫建立代辦任務（截止日期設為 7 天後），並建立 Relation 雙向關聯回專題彙整頁面。

---

## 🛠️ 環境配置與運行 (.env)

確認 `.env` 檔案中已設定以下欄位：
```ini
NOTION_API_KEY=ntn_your_notion_token_here
GEMINI_API_KEY=your_gemini_api_key_here
NOTION_DATABASE_ID=your_database_id_here
NOTION_TASK_DATABASE_ID=your_task_database_id_here
USE_VERTEX_AI=true # 設定為 true 時使用 GCP Vertex AI 引擎，需要搭配 gcp-key.json；否則自動降級為一般 API Key
```

## 📖 系統化架構與設計文件
詳細系統架構及撰寫策略，請參閱：
* 📘 [DKMS V3.5 架構設計藍圖 (V3_ARCHITECTURE.md)](file:///c:/Users/etrny/.gemini/antigravity/scratch/Notion_agent/V3_ARCHITECTURE.md)
* 📙 [知識彙整與專題撰寫策略 (WRITING_STRATEGY.md)](file:///c:/Users/etrny/.gemini/antigravity/scratch/Notion_agent/WRITING_STRATEGY.md)
* 📗 [專案統一詞彙表 (GLOSSARY.md)](file:///c:/Users/etrny/.gemini/antigravity/scratch/Notion_agent/GLOSSARY.md)
* 📓 [專案待辦與開發狀態記錄 (PENDING.md)](file:///c:/Users/etrny/.gemini/antigravity/scratch/Notion_agent/PENDING.md)

