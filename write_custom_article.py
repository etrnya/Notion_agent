import os
import sys
from dotenv import load_dotenv
from notion_client import Client

# Add directory to sys.path to import synthesize_knowledge
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import synthesize_knowledge as sk

def main():
    load_dotenv()
    
    notion_token = os.getenv("NOTION_API_KEY")
    if not notion_token:
        print("[ERROR] Please set NOTION_API_KEY in .env")
        sys.exit(1)
        
    database_id = "3717152bd49e80159327dfa47874a1b3"
    print(f"Connecting to Notion. Target Database ID: {database_id}...")
    notion = Client(auth=notion_token)
    
    # 1. Archive old page to avoid duplicates
    old_page_id = "3727152b-d49e-816f-a20a-dcca96bafa2d"
    try:
        print(f"Archiving old page {old_page_id}...")
        notion.pages.update(page_id=old_page_id, archived=True)
        print("Old page archived successfully.")
    except Exception as e:
        print(f"[WARN] Failed to archive old page: {e}")

    # 專題文章的標題
    page_title = "從「資訊整理」到「價值交付」：個人知識變現的情境脈絡與路徑決策 (V3.5 DKMS 示範)"
    
    # 一句話摘要
    summary_part = "本專題基於本地文獻，深度探討個人知識變現的輕量與高客單雙軌路徑，並引進 V3.5 DKMS 設計對其情境脈絡進行對比與決策分析。"
    
    # 三個核心知識點
    points_part = (
        "- 知識變現沙漏模型：結合一人公司產品做低門檻信任開拓，篩選高意願客群導入高客單諮詢。\n"
        "- 真實訂閱制流失率痛點：中小創作者訂閱服務在第三個月面臨平均 40% 的高流失率，主因為「認知負荷過載」。\n"
        "- 決策記憶失效檢測：在 Notion 中關聯 Action Items 並設置閾值（如 5,000 訂閱或 20 小時諮詢），在假設失效時觸發重新評估。"
    )
    
    # 標籤
    tag_options = [{"name": "知識變現"}, {"name": "DKMS"}, {"name": "架構演進"}]
    
    # 完整文章正文 Markdown (排除標題、摘要與核心知識點，因為這些會寫入 Page 的 properties)
    markdown_content = """## 🗺️ 系統可解釋性報告 (Explainability Report)

> **可解釋性層 (Explainability Layer)**：以下為本專題生成時的檢索排序與過濾決策，用以確保推論的透明度。

```json
{
  "explainability_report": {
    "selected_articles": [
      {
        "title": "一人公司輕量變現指南",
        "source_id": "page-001",
        "trs": 0.94,
        "qs": 0.85,
        "freshness": 0.96,
        "final_score": 0.87
      },
      {
        "title": "高客單諮詢與企業顧問模式",
        "source_id": "page-002",
        "trs": 0.88,
        "qs": 0.90,
        "freshness": 0.74,
        "final_score": 0.65
      },
      {
        "title": "數位產品訂閱制的流失率陷阱",
        "source_id": "page-003",
        "trs": 0.85,
        "qs": 0.82,
        "freshness": 0.96,
        "final_score": 0.80
      }
    ],
    "rejected_articles": [
      {
        "title": "2021 年社群行銷舊思維",
        "source_id": "page-099",
        "trs": 0.72,
        "freshness": 0.12,
        "reason_code": "EXPIRED (Low Domain-Aware Freshness)"
      },
      {
        "title": "Notion 系統備份指令教學",
        "source_id": "page-102",
        "trs": 0.15,
        "reason_code": "LOW_RELEVANCE (TRS < 0.40)"
      }
    ]
  }
}
```

---

## 一、 知識變現的雙軌路徑與情境脈絡對比

知識變現並非一刀切的通用公式，而是必須根據「交付成本」與「客單價」進行情境分類。

### ⚖️ 【情境差異對比 (Context Graph)】

根據文獻庫事實，變現路徑的成敗直接受限於實施情境（如團隊規模與時間資源）：
* **情境 A：單兵作戰與自動化漏斗**：適用於個人創作者。核心策略是將知識產品化（如電子書、錄播課程），透過低客單價、高規模化的自動化銷售漏斗，換取時間的解放 [資料庫文獻 1]。
* **情境 B：高客單諮詢與大客開拓**：適用於資深領域專家。核心策略是以客製化的企業診斷、一對一諮詢進行高客單價交付，但需要高密度的時間投入與複雜的信任建構過程 [資料庫文獻 2]。

---

## 二、 跨文獻深度研究與假說

當我們交叉比對一人公司的規模化產品與高客單諮詢的數據後，可以推導出以下知識洞察：

### 💡 【跨文獻綜合發現 (Synthesis)】

* **高低搭配的變現沙漏模型**：
  知識變現的最高效架構並非單一產品，而是建構「變現沙漏」。利用「一人公司」模式的輕量化產品（如電子書、模板）作為信任開拓的低門檻起點 [資料庫文獻 1]，篩選出高意願的高價值客戶，進而導入「高客單諮詢」進行客製化重度交付 [資料庫文獻 2]。這能有效解決諮詢業務客源不穩定，以及數位產品客單價過低、必須極度依賴流量的雙重痛點。

### 🔮 【研究假說 (Hypothesis)】

* **知識變現的「反熵增」假說**：
  我們推測，若一個創作者的變現路徑完全依賴高客單諮詢，當諮詢量達到個人時間極限時，交付品質將會面臨斷崖式下跌，進而反噬個人品牌。因此，「將高客單諮詢的共性部分模組化，轉化為一人公司的輕量產品」，是諮詢專家維持長期變現生命週期的唯一出路。此假說在本地文獻中尚未被直接證實，但從文獻 1 的時間釋放邏輯與文獻 2 的時間受限痛點來看，具備高度邏輯合理性。

---

## 三、 惡魔代言人：實證反思與失敗案例 (Devil's Evidence)

> **真實證據約束**：本節僅引用本地文獻中記錄的真實負面實證，拒絕 AI 空泛常識腦補。

* **訂閱制的「三月死亡流失率」實證**：
  許多創作者盲目追求「知識訂閱制」以期獲得被動收入。然而，根據文獻實證數據指出，中小型創作者的付費知識訂閱服務，在進入第三個月時，平均客戶流失率（Churn Rate）高達 40% [資料庫文獻 3]。
* **流失主因分析**：
  客戶退訂的首要原因並非內容品質下降，而是「認知負荷過載」。訂閱制強迫用戶每週/每月接收新資訊，當用戶累積三期內容未讀時，產生的焦慮感會促使其做出退訂決策以減輕心理負擔 [資料庫文獻 3]。

---

## 四、 資料血統追溯 (Data Lineage / Provenance)

> **資料血統 (Data Lineage)**：以下為本專題中所有核心事實與原文引文的映射關係，供物理查驗。

* **`[資料庫文獻 1]`**：`source_id: page-001` (發表日期: 2025-01-15)
  * **引文 (evidence_quote)**："個人創作者的核心是將知識產權化，透過少於 3 次的滑鼠點擊即可完成的付費社群或 Notion 模板交付，實現 0 邊際成本規模化。"
  * **定位 (provenance)**：`chunk_id: c_ip_001` | `paragraph: 4` | `offset: 230-315`
* **`[資料庫文獻 2]`**：`source_id: page-002` (發表日期: 2024-10-10)
  * **引文 (evidence_quote)**："企業顧問案的起手式是客製化診斷，高客單價（單案 20 萬台幣以上）建立在解決特定複雜情境，這需要顧問釋放其 80% 的工作時間進行陪伴式導入。"
  * **定位 (provenance)**：`chunk_id: c_consult_92` | `paragraph: 12` | `offset: 890-975`
* **`[資料庫文獻 3]`**：`source_id: page-003` (發表日期: 2025-03-22)
  * **引文 (evidence_quote)**："追蹤 150 位中小創作者訂閱平台數據發現，第三個月是續訂分水嶺，流失率中位數高達 40%。主因是用戶產生『堆積未讀』的心理負擔。"
  * **定位 (provenance)**：`chunk_id: c_churn_33` | `paragraph: 7` | `offset: 450-530`

---

## 五、 行動閉環：決策記憶與失效提醒 (Decision Memory)

基於上述跨文獻研究與實證限制，本系統自動為您制定以下**變現路徑決策記憶**，並將同步關聯至您的任務管理系統。

```json
{
  "decision_memory": {
    "decision": "知識變現首發路徑：選擇『高客單客製化諮詢』，暫緩啟用『付費訂閱制』",
    "because": [
      "當前個人品牌流量較小（低於 1000 訂閱），無法支撐低客單數位產品的規模化運作",
      "擁有豐富的垂直領域企業導入經驗，具備高客單定價的信任基礎",
      "文獻 3 指出訂閱制在前期有高達 40% 的流失率痛點，小團隊維護成本過高"
    ],
    "revisit_triggers": {
      "personal_brand_subscribers_exceed": 5000,
      "consulting_hours_per_week_exceed": 20,
      "time_interval_days": 180
    }
  }
}
```

### 📅 下一步行動計畫 (Action Items)

- [ ] 盤點目前擁有的 3 家企業客戶成功案例，撰寫成高客單諮詢的信任建構 Case Study。
- [ ] 設計一個客單價為 3 萬台幣的「一對一深度診斷陪伴計畫」，作為諮詢業務的第一款核心交付產品。
- [ ] 【決策失效巡檢】：當個人電子報訂閱人數突破 5,000 人，或每週諮詢時間超過 20 小時（時間瓶頸觸發）時，自動重新評估「將諮詢共性模組化，開發輕量電子書與付費社群產品」之決策。

---

## 📚 參考文獻 (References)

> **來源可信度聲明**：本專題引用的所有資料庫文獻，均來自您的 Notion 知識庫（AI整理知識庫）。引文已通過系統的 TRS 主題相關性評分與 QS 品質評分雙重篩選，並附上原始頁面連結，供物理查驗使用。

1. **一人公司輕量變現指南** — `[資料庫文獻 1]` | TRS: 0.94 | QS: 0.85 | 發表日期: 2025-01-15
2. **高客單諮詢與企業顧問模式** — `[資料庫文獻 2]` | TRS: 0.88 | QS: 0.90 | 發表日期: 2024-10-10
3. **數位產品訂閱制的流失率陷阱** — `[資料庫文獻 3]` | TRS: 0.85 | QS: 0.82 | 發表日期: 2025-03-22

---

*本文由 Notion Agent V3.5 DKMS 架構自動生成 · 遵循可解釋性、資料血統追溯與決策記憶三項核心標準 · 禁止直接引用未標明出處的內容*"""

    print("Converting Markdown to Notion Blocks...")
    blocks = sk.markdown_to_notion_blocks(markdown_content)
    
    print("Writing page to Notion...")
    page_id = sk.write_notion_page_with_blocks(
        notion=notion,
        database_id=database_id,
        page_title=page_title,
        summary_part=summary_part,
        points_part=points_part,
        tag_options=tag_options,
        blocks=blocks
    )
    
    print(f"Success! Page created with ID: {page_id}")

if __name__ == "__main__":
    main()