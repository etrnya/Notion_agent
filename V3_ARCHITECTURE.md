# Notion Agent V3 知識研究智能體：架構演進與設計藍圖

針對當前 RAG 知識彙整系統從「知識管理 (KM)」邁向「知識研究 (KR)」階段所面臨的關鍵盲點，本文件定義了 V3 智能助理系統的架構設計方案。

---

## 🗺️ V3 架構演進對比 (KM vs. KR)

```mermaid
graph TD
    subgraph V2: 知識管理階段 (文字 -> 文字)
        V2_Source[Notion 筆記] --> V2_Clust[語意聚類]
        V2_Clust --> V2_DA[同模型假反駁]
        V2_DA --> V2_Synth[LLM 混合 RAG 合成]
        V2_Synth --> V2_Doc[專題文章]
    end

    subgraph V3: 知識研究階段 (資料 -> 事實 -> 洞察)
        V3_Source[Notion 筆記 & 來源權重] --> V3_Clust[語意聚類 & 相關度重排]
        V3_Clust --> V3_Fact[事實提取層 Fact Layer]
        V3_Fact --> V3_Disproof[非對稱模型反證 Devil's Evidence]
        V3_Fact --> V3_Synth[事實組裝 RAG 合成]
        V3_Synth --> V3_Eval[新洞察評估器 Insight Evaluator]
        V3_Eval -- 評估合格 --> V3_Doc[高含金量專題文章]
        V3_Eval -- 未產生新洞察 (警報) --> V3_ReRetrieval[擴大文獻檢索]
    end
```

---

## 1. 拆分「主題相關度」與「主觀品質分數」 (Relevance vs. Quality)

* **痛點**：高分但無關的文章（如 Docker 實踐 10 分）會排擠低分但高度相關的文章（如 Notion 知識管理 5 分）。
* **V3 設計**：將文章的篩選分數拆分為兩個獨立維度：
  1. **品質分數 (Quality Score, QS)**：由原先公式計算，代表文獻本身的含金量。
     $$QS = 0.4 \times \text{Credibility} + 0.3 \times \text{Actionability} + 0.3 \times \text{Inspiration}$$
  2. **主題相關度分數 (Topic Relevance Score, TRS)**：計算文獻與語意聚類主題的特徵重疊度（如 Cosine Similarity 或詞組重合度）。
* **最終加權排序分數 (Final Score)**：
  $$\text{Final Score} = 0.6 \times TRS + 0.4 \times QS$$
  *相關度佔 60% 決定檢索召回，品質佔 40% 決定排序優先級，確保文獻「不跑題且質量高」。*

---

## 2. 建立「事實提取層」 (Fact Extraction Layer)

* **痛點**：文字直推文字（Text-to-Text）會導致 AI 在重組過程中產生細微的語意漂移，且極易漏掉正文標記。
* **V3 設計**：在文獻輸入與專題合成之間，物理切分出一個「Fact Layer」。
  * **做法**：對每篇核心文獻，先調用 LLM 提煉為結構化的事實聲明 JSON。
  ```json
  [
    {
      "claim": "TW Legal RAG 開源模型基於法律條文進行了語意特徵微調",
      "evidence": "在測試集上比通用 Llama 模型準確度提升 25%",
      "source_id": "Notion_Page_UUID_1",
      "source_title": "臺灣法律RAG模型開源"
    }
  ]
  ```
  * **合成約束**：正文生成器 (Article Generator) 的輸入**僅能使用這份事實 JSON**，禁止直接吃原文。所有觀點必須嚴格對應到 `source_id` 的 Claim。

---

## 3. 非對稱模型反證 (Devil's Evidence)

* **痛點**：同一模型「自己反駁自己」容易流於客套的「假反駁」（優點寫滿篇，缺點兩三句）。
* **V3 設計**：
  * **角色對立**：正文由 Gemini-2.5-Pro / GPT-4o 撰寫；而「惡魔代言人」改由專注於代碼靜態分析、邏輯檢驗、或安全審查的專門 Agent（甚至調用不同的開源模型如 Llama-3-Guard）擔任。
  * **任務改變**：惡魔 Agent 的 prompt 從「提出反對意見」改為「**尋找不支持本文觀點的證據 (Evidence Disproof)**」。例如：尋找與該 Claim 衝突的技術限制、官方 Deprecation 聲明、或本地資料庫中的失敗案例。

---

## 4. 來源權重系統 (Source Weight)

* **痛點**：FB 貼文、技術白皮書、官方 API 文件在系統中被一視同仁，容易導致基於社群流言的推論影響力大於官方規範。
* **V3 設計**：
  * 在 Notion 來源資料庫中新增屬性 `來源類型` (Select)，對應以下權重對照表：
  
  | 來源類型 (Source Type) | 權重 (Weight) | 適用對象 |
  | :--- | :--- | :--- |
  | **Official Doc** | `1.0` | 官方 API 文件、官方 GitHub Release、標準規範 |
  | **Paper** | `0.9` | 學術會議論文、ArXiv 預印本 |
  | **Tech Blog** | `0.7` | 業界公認技術部落格 (如 Vercel, Netflix Tech) |
  | **Personal Note** | `0.5` | 個人開發筆記、日常碎碎念、工作週報 |
  | **Social Post** | `0.3` | FB 貼文、Twitter 短文、論壇討論 |

  * 計算文獻品質分數 (QS) 時，將 `Credibility`（可信度）乘上該來源的 `Weight`，讓官方規格與權威論文天然具備更高的說服力。

---

## 5. 新洞察檢查器 (Insight Evaluator)

* **痛點**：AI 僅僅是把「A 說了什麼、B 說了什麼」重組在一起，缺乏跨文獻融合推導出的「新知識/新洞察」。
* **V3 設計**：
  * 在文章合成後，加入一個獨立的 Gatekeeper：**Insight Evaluator**。
  * **評估原則**：
    1. 「這篇文章中，有哪些觀點是*單一文獻中不存在*，而是透過多篇文獻交叉推導出來的？」
    2. 「文章結論是否需要至少兩篇以上文獻的證據支撐才能成立？」
  * **處理分支**：
    * **合格**：標記並高亮這些 `【跨文獻推論】`。
    * **不合格**：若回答「無新洞察」，系統應判定此文僅為「重組摘要」，拒絕寫入「AI 整理知識庫」，而是將其降級寫入「基礎摘要庫」，或觸發擴大召回（Re-Retrieval）流程重新寫作。

---

## 6. AI 推理比例限制與顯式標記 (Explicit Reasoning)

* **痛點**：AI 自己推理的「延伸分析」在正文中佔比過高，導致整篇文章 80% 都是 AI 的幻覺常識，脫離了用戶本地資料庫的約束。
* **V3 設計**：
  * **硬性比例**：AI 自己的推理在正文總字數中**不得超過 15%**。
  * **顯式分類**：廢除模糊的 `[外部補充/AI延伸]`，強制將非資料庫來源的段落標註為以下三類：
    1. `【跨文獻推論】`：從資料庫文獻 A 的 X 點與文獻 B 的 Y 點共同歸納出的邏輯。
    2. `【AI延伸推測】`：基於 AI 背景知識庫補充的常識（如工具的 npm 安裝指令）。
    3. `[外部文獻 Y]`：AI 主動引入的真實外部網路連結。
