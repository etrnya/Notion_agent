import os
import sys
import re
import random
import json
import time
import math
import argparse
import io
from datetime import datetime, timedelta
from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIResponseError

# 強制將 stdout 與 stderr 設為 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# ==============================================================
# V3.8 Domain-Aware Temporal Decay (領域自適應時間衰減係數表)
# lambda 值越大 = 衰減越快；0.00 = 永不衰減
# ==============================================================
DOMAIN_DECAY_MAP = {
    "ai":          0.80,  # AI/LLM：技術日新月異
    "llm":         0.80,
    "軟體工程":    0.50,
    "software":    0.50,
    "程式開發":    0.50,
    "框架":        0.50,
    "商業模式":    0.30,
    "business":    0.30,
    "創業":        0.30,
    "行銷":        0.30,
    "管理":        0.05,
    "management":  0.05,
    "組織":        0.05,
    "領導力":      0.05,
    "哲學":        0.00,
    "心理學":      0.00,
    "psychology":  0.00,
    "philosophy":  0.00,
    "歷史":        0.00,
}
DEFAULT_DECAY_LAMBDA = 0.30  # 未匹配領域的預設衰減係數

def compute_freshness_score(created_time_str, domain_tags):
    """V3.8：根據文章建立時間與所屬領域，計算領域自適應的新鮮度分數 (0~1)"""
    if not created_time_str:
        return 0.85  # 無時間資訊時給予中等新鮮度

    try:
        created_dt = datetime.fromisoformat(created_time_str.replace("Z", "+00:00"))
        age_years = (datetime.now(created_dt.tzinfo) - created_dt).days / 365.0
    except Exception:
        return 0.85

    # 尋找最快的衰減係數（若文章同時屬於 AI 和管理，AI 的衰減優先）
    lam = DEFAULT_DECAY_LAMBDA
    best_lam = -1
    for tag in domain_tags:
        tag_lower = tag.lower()
        for keyword, kl in DOMAIN_DECAY_MAP.items():
            if keyword in tag_lower:
                if kl > best_lam:
                    best_lam = kl
    if best_lam >= 0:
        lam = best_lam

    freshness = math.exp(-lam * age_years)
    return round(freshness, 4)

# ==============================================================
# 品質過濾 + 分層抽樣：從 3000+ 筆資料庫智慧選出精華素材池
# ==============================================================
def smart_sample_articles(pages, sample_size=400, min_qs=5.0, inspired_quota=60):
    """
    三步驟智慧抽樣：
    1. 深受啟發文章優先全納入（最多 inspired_quota 篇）
    2. 其餘文章以 QS >= min_qs 過濾後，按 AI 標籤分層比例抽樣
    3. 打亂順序確保模型不受排列影響
    目的：保留跨領域多樣性（不同於先分類再挑一類），同時控制 token 量。
    """
    import random

    inspired_pool = []
    qualified_pool = []

    for page in pages:
        props = page.get("properties", {})
        # 快速計算 QS
        cred = props.get("可信度", {}).get("number") or 5.0
        act  = props.get("可執行性", {}).get("number") or 5.0
        inspired_select = props.get("深受啟發", {}).get("select")
        is_inspired = bool(inspired_select and inspired_select.get("name") == "深受啟發")
        inspiration = 10.0 if is_inspired else 5.0
        qs = 0.4 * cred + 0.3 * act + 0.3 * inspiration

        # 必須有摘要才有合成價值
        has_summary = bool(
            props.get("AI 摘要", {}).get("rich_text") or
            props.get("摘要", {}).get("rich_text")
        )
        if not has_summary:
            continue

        if is_inspired:
            inspired_pool.append(page)
        elif qs >= min_qs:
            qualified_pool.append(page)

    # --- Step 1: 深受啟發優先 ---
    # 按 QS 降序，若超過配額就取前 inspired_quota 篇
    inspired_pool.sort(
        key=lambda p: 0.4*(p["properties"].get("可信度",{}).get("number") or 5)
                    + 0.3*(p["properties"].get("可執行性",{}).get("number") or 5)
                    + 0.3*10.0,
        reverse=True
    )
    selected_inspired = inspired_pool[:inspired_quota]

    # --- Step 2: 分層抽樣填滿剩餘名額 ---
    remaining_quota = max(0, sample_size - len(selected_inspired))
    sampled_general = []

    if remaining_quota > 0 and qualified_pool:
        # 按主要標籤分組
        tag_groups = {}
        untagged = []
        for page in qualified_pool:
            props = page.get("properties", {})
            tags = []
            for field in ["AI 標籤", "Tag", ""]:
                if field in props:
                    raw = props[field].get("multi_select", [])
                    if raw:
                        tags = [t.get("name", "") for t in raw if t.get("name")]
                        break
            if tags:
                tag_groups.setdefault(tags[0], []).append(page)
            else:
                untagged.append(page)

        total_qualified = len(qualified_pool)
        # 各標籤組按比例抽樣（保留 8% 名額給無標籤文章）
        tagged_quota = round(remaining_quota * 0.92)
        for tag, group in tag_groups.items():
            proportion = len(group) / total_qualified
            n = max(1, round(proportion * tagged_quota))
            sampled_general.extend(random.sample(group, min(len(group), n)))

        # 補充無標籤文章
        untagged_quota = remaining_quota - len(sampled_general)
        if untagged_quota > 0 and untagged:
            sampled_general.extend(random.sample(untagged, min(len(untagged), untagged_quota)))

        # 若分層後仍不足，從整體 qualified 補足（避免某些標籤組比例計算誤差）
        if len(sampled_general) < remaining_quota:
            already = {p["id"] for p in sampled_general}
            pool_extra = [p for p in qualified_pool if p["id"] not in already]
            needed = remaining_quota - len(sampled_general)
            sampled_general.extend(random.sample(pool_extra, min(len(pool_extra), needed)))

    # --- Step 3: 合併並打亂 ---
    result = selected_inspired + sampled_general
    random.shuffle(result)
    return result, len(inspired_pool), len(qualified_pool)

load_dotenv()

# 初始化 LLM 用戶端
openai_client = None
gemini_client = None
engine_name = ""

def init_llm():
    global openai_client, gemini_client, engine_name
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")

    # 優先檢測本地是否存在 gcp-key.json，如果存在且未禁用則啟動 Vertex AI 引擎
    key_path = "gcp-key.json"
    use_vertex = os.getenv("USE_VERTEX_AI", "true").lower() in ("true", "1", "yes")
    if use_vertex and os.path.exists(key_path):
        try:
            from google import genai
            from google.oauth2 import service_account
            
            with open(key_path, "r", encoding="utf-8") as f:
                key_data = json.load(f)
                project_id = key_data.get("project_id")
                
            if not project_id:
                raise ValueError("無法在 JSON 中找到 project_id 欄位")
                
            credentials = service_account.Credentials.from_service_account_file(
                key_path,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            gemini_client = genai.Client(
                vertexai=True,
                project=project_id,
                credentials=credentials
            )
            engine_name = "gemini"
            print(f"[INFO] 已成功初始化 GCP Vertex AI 引擎 (專案 ID: {project_id}，模型: gemini-2.5-flash)")
            return
        except Exception as e:
            print(f"[WARN] 嘗試初始化 Vertex AI 失敗: {e}，將回退至其他 API Key 驗證...")

    if deepseek_key:
        from openai import OpenAI
        openai_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
        engine_name = "deepseek"
        print("[INFO] 已成功初始化 DeepSeek 引擎 (deepseek-chat)")
        return
    
    if gemini_key:
        try:
            from google import genai
            gemini_client = genai.Client(api_key=gemini_key)
            engine_name = "gemini"
            print("[INFO] 已成功初始化 Gemini 引擎 (gemini-2.5-flash)")
            return
        except ImportError:
            pass
            
    if openai_key:
        from openai import OpenAI
        openai_client = OpenAI(api_key=openai_key)
        engine_name = "openai"
        print("[INFO] 已成功初始化 OpenAI 引擎 (gpt-4o-mini)")
        return
        
    print("[ERROR] 未找到 gcp-key.json，且未在 .env 中設定 DEEPSEEK_API_KEY, GEMINI_API_KEY 或 OPENAI_API_KEY")
    sys.exit(1)

def fallback_retrieve_articles(theme_name, all_articles, count=3):
    """當 LLM 回傳的文獻 ID/Index 無法匹配時，使用物理規則從所有文章中召回最相關的真實文章"""
    scored_articles = []
    
    # 簡單提取關鍵字 (去除常見字)
    words = re.findall(r'[\u4e00-\u9fa5]{2,4}|[a-zA-Z0-9]+', theme_name)
    # 過濾掉一些無意義的詞
    stop_words = {"挑戰", "框架", "合作", "實踐", "省思", "深度", "批判", "探討", "研究", "分析", "實作", "治理", "國際"}
    keywords = [w for w in words if w not in stop_words]
    if not keywords:
        keywords = words
        
    for art in all_articles:
        title = art.get("title", "")
        summary = art.get("summary", "")
        
        # 計算匹配度分數
        match_score = 0.0
        for kw in keywords:
            if kw.lower() in title.lower():
                match_score += 10.0  # 標題包含關鍵字加 10 分
            if kw.lower() in summary.lower():
                match_score += 3.0   # 摘要包含關鍵字加 3 分
                
        # 加上原本的 RAG 分數以保證質量
        final_score = match_score + art.get("rag_score", 5.0)
        scored_articles.append((final_score, art))
        
    # 依分數降序排序
    scored_articles.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored_articles[:count]]

def semantic_clustering(articles_brief, existing_tags, count):
    """呼叫 LLM 進行跨文章的語意聚類，找出適合撰寫深度專題文章的【多文獻合成主題】"""
    # 1. 建立 index 對照表，避免 LLM 複製錯 UUID
    brief_with_indices = []
    index_to_id = {}
    for idx, art in enumerate(articles_brief):
        art_idx = str(idx)
        brief_with_indices.append({
            "index": art_idx,
            "title": art["title"],
            "tags": art["tags"],
            "summary": art["summary"]
        })
        index_to_id[art_idx] = art["id"]

    prompt = f"""
    以下是從知識庫中撈出的已處理文章列表（共 {{len(brief_with_indices)}} 篇）：
    {{json.dumps(brief_with_indices, ensure_ascii=False)}}

    已存在的專題主題包括：{{json.dumps(list(existing_tags), ensure_ascii=False)}}。
    請避開這些方向，對剩下的文章進行「跨文獻語意聚類」，找出全新且適合撰寫深度專題文章的【多文獻合成主題】。

    每個主題必須滿足以下條件：
    1. 每個主題必須至少包含 2 篇或 3 篇以上的相關文章，以實現跨文獻的交叉論證與知識融合。絕不能只放 1 篇文章。
    2. 每個主題應有一個明確且具吸引力的專案研究主題名稱。
    3. 每個主題中，請明確指定哪些是「核心文獻」（最多 3 篇）與哪些是「輔助參考文獻」（提供摘要）。

    請回傳一個 JSON 格式的列表，格式如下：
    [
      {{
        "theme": "主題名稱（例如：AI 輔助軟體開發的雙面刃與風險治理）",
        "rationale": "為什麼要彙整這個主題的簡短說明",
        "core_article_indices": ["0", "1"],
        "helper_article_indices": ["2"]
      }}
    ]

    注意：請務必回傳對應文章列表中的真實 "index" 值（如 "0", "1" 等字串），絕對不要使用範例中的 "0", "1", "2" 或是自創其他 ID，也絕對不能使用文章的標題。
    請只回傳 strict JSON，不要用 ```json 包覆。
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if engine_name == "deepseek":
                response = openai_client.chat.completions.create(
                    model="deepseek-chat",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You are a professional knowledge curator. You perform semantic clustering and output strict JSON in Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                res_text = response.choices[0].message.content
            elif engine_name == "gemini":
                try:
                    response = gemini_client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                        config={"response_mime_type": "application/json"}
                    )
                    res_text = response.text
                except Exception as e:
                    print(f"    [WARN] 使用 Gemini JSON 模式失敗，嘗試一般模式: {{e}}")
                    response = gemini_client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt
                    )
                    res_text = response.text
            else:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You are a professional knowledge curator. You perform semantic clustering and output strict JSON in Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                res_text = response.choices[0].message.content
                
            res_text = res_text.strip()
            if res_text.startswith("```"):
                res_text = re.sub(r'^```(?:json)?\n', '', res_text)
                res_text = re.sub(r'\n```$', '', res_text)
                res_text = res_text.strip()
                
            data = json.loads(res_text)
            raw_themes = []
            if isinstance(data, dict) and "themes" in data:
                raw_themes = data["themes"]
            elif isinstance(data, list):
                raw_themes = data
            else:
                raw_themes = [data]
                
            # 將 indices 轉換回 UUID (core_article_ids / helper_article_ids)
            processed_themes = []
            for t in raw_themes:
                core_ids = []
                # 支援 core_article_indices
                if "core_article_indices" in t:
                    for idx_str in t["core_article_indices"]:
                        idx_str = str(idx_str).strip()
                        if idx_str in index_to_id:
                            core_ids.append(index_to_id[idx_str])
                # 支援 core_article_ids
                elif "core_article_ids" in t:
                    for cid in t["core_article_ids"]:
                        cid_str = str(cid).strip()
                        if cid_str in index_to_id:
                            core_ids.append(index_to_id[cid_str])
                        elif cid_str.replace("-", "").lower() in [aid.replace("-", "").lower() for aid in index_to_id.values()]:
                            matched_id = next(aid for aid in index_to_id.values() if aid.replace("-", "").lower() == cid_str.replace("-", "").lower())
                            core_ids.append(matched_id)
                            
                helper_ids = []
                if "helper_article_indices" in t:
                    for idx_str in t["helper_article_indices"]:
                        idx_str = str(idx_str).strip()
                        if idx_str in index_to_id:
                            helper_ids.append(index_to_id[idx_str])
                elif "helper_article_ids" in t:
                    for hid in t["helper_article_ids"]:
                        hid_str = str(hid).strip()
                        if hid_str in index_to_id:
                            helper_ids.append(index_to_id[hid_str])
                        elif hid_str.replace("-", "").lower() in [aid.replace("-", "").lower() for aid in index_to_id.values()]:
                            matched_id = next(aid for aid in index_to_id.values() if aid.replace("-", "").lower() == hid_str.replace("-", "").lower())
                            helper_ids.append(matched_id)
                            
                processed_themes.append({
                    "theme": t.get("theme", "未定義主題"),
                    "rationale": t.get("rationale", ""),
                    "core_article_ids": core_ids,
                    "helper_article_ids": helper_ids
                })
                
            return processed_themes
        except Exception as e:
            print(f"  [WARN] 語意聚類 LLM 呼叫失敗 (嘗試 {attempt+1}/{max_retries}): {e}，將在 5 秒後重試...")
            time.sleep(5)
            
    print("  [ERROR] 語意聚類呼叫失敗，已達最大重試次數。")
    return []

def get_page_content(notion, page_id):
    """讀取 Notion 頁面內部的完整文字區塊（第一層）"""
    try:
        blocks = notion.blocks.children.list(block_id=page_id)
        text_parts = []
        for block in blocks.get("results", []):
            block_type = block.get("type")
            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", 
                            "bulleted_list_item", "numbered_list_item", "to_do", "toggle"]:
                rich_texts = block.get(block_type, {}).get("rich_text", [])
                for rt in rich_texts:
                    text_parts.append(rt.get("plain_text", ""))
        return "\n".join(text_parts)
    except Exception as e:
        print(f"    [WARN] 讀取頁面內容失敗 (ID: {page_id}): {e}")
        return ""

def normalize_tags(all_tags):
    """呼叫 LLM 對所有標籤進行「語意對齊與清洗」，消除相近或重疊的字詞"""
    prompt = f"""
    以下是從知識庫中收集到的所有原始標籤：
    {json.dumps(all_tags, ensure_ascii=False)}
    
    由於這些標籤在多次對話中產生，存在許多語意相近或重疊的字詞（例如：『自動化』、『自動化工作』、『自動化案例』；或是『AI 代理』、『AI Agent』、『Agent應用』）。
    請將這些標籤進行「語意對齊與清洗」，把相近的原始標籤合併為一個精煉的「標準標籤」。
    
    請回傳一個 JSON 物件，格式如下：
    {{
      "標準標籤 1": ["原始標籤 A", "原始標籤 B"],
      "標準標籤 2": ["原始標籤 C"]
    }}
    
    規則：
    1. 標準標籤應使用最常見、最明確的繁體中文術語（例如：『自動化工作流』、『AI程式開發』、『自我成長』）。
    2. 每個原始標籤只能歸入一個標準標籤。
    3. 只回傳 strict JSON，不要有任何 ```json 標籤包覆，也不要有其他問候語。
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if engine_name == "deepseek":
                response = openai_client.chat.completions.create(
                    model="deepseek-chat",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You are a helpful database tag normalizer. You output strict JSON in Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return json.loads(response.choices[0].message.content)
            elif engine_name == "gemini":
                response = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                return json.loads(response.text)
            else:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You are a helpful database tag normalizer. You output strict JSON in Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"  [WARN] 標籤清洗 LLM 呼叫失敗: {e}，將在 5 秒後重試...")
            time.sleep(5)
            
    print("  [WARN] 標籤清洗失敗，使用原始標籤作為備份。")
    return {tag: [tag] for tag in all_tags}

# ==============================================================
# V3.5 Fact Layer：Claim Pool 事實提取
# ==============================================================
def extract_claim_pool(notion_page_id, page_title, full_text, source_url):
    """V3.5 Fact Layer：對單篇核心文獻呼叫 LLM，提取含 evidence_quote 與 provenance 的 Claim Pool JSON"""
    prompt = f"""
你是一位嚴謹的知識分析師，負責從文章中提取「事實層級」的結構化主張。

文章標題：{page_title}
來源 ID：{notion_page_id}
文章內容（前 3000 字）：
{full_text[:3000]}

請提取 2~4 個最重要的主張（Claim），每個主張必須包含：
- claim: 用一句繁體中文精確表述主張（不可泛化為常識）
- evidence_quote: 原文中支撐此主張的精確引文（逐字引用，不要意譯）
- evidence_type: 必須是 "fact" (客觀事實)、"opinion" (作者觀點) 或 "speculation" (作者推測) 三者之一
- confidence: 你對此 Claim 可靠性的評估分數 (0.0~1.0)

【硬性要求】只回傳一個 JSON 陣列，格式如下（不要加 ```json 包覆）：
[
  {{
    "claim": "精確主張",
    "evidence_quote": "原文逐字引用",
    "evidence_type": "fact",
    "confidence": 0.90,
    "source_id": "{notion_page_id}",
    "source_title": "{page_title}",
    "source_url": "{source_url or '無'}"
  }}
]
"""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            if engine_name == "deepseek":
                response = openai_client.chat.completions.create(
                    model="deepseek-chat",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You extract structured factual claims from articles. Output strict JSON array in Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                res_text = response.choices[0].message.content
            elif engine_name == "gemini":
                try:
                    response = gemini_client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                        config={"response_mime_type": "application/json"}
                    )
                    res_text = response.text
                except Exception:
                    response = gemini_client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt
                    )
                    res_text = response.text
            else:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You extract structured factual claims from articles. Output strict JSON array in Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                res_text = response.choices[0].message.content

            res_text = res_text.strip()
            if res_text.startswith("```"):
                res_text = re.sub(r'^```(?:json)?\n?', '', res_text)
                res_text = re.sub(r'\n?```$', '', res_text).strip()

            parsed = json.loads(res_text)
            # 支援 {"claims": [...]} 包裝格式
            if isinstance(parsed, dict):
                parsed = parsed.get("claims", parsed.get("data", []))
            if isinstance(parsed, list):
                return parsed
        except Exception as e:
            print(f"    [WARN] Fact Layer 提取失敗 (嘗試 {attempt+1}): {e}")
            time.sleep(3)
    return []


# ==============================================================
# V3.5 Explainability Layer：可解釋性報告生成
# ==============================================================
def generate_explainability_report(selected_articles, rejected_articles):
    """V3.5：根據選中與淘汰的文章清單，生成 Markdown 可解釋性報告區塊"""
    report_data = {
        "explainability_report": {
            "selected_articles": [
                {
                    "title": a.get("title", ""),
                    "source_id": a.get("id", ""),
                    "trs": round(a.get("trs", 0), 2),
                    "qs": round(a.get("rag_score", 5.0) / 10.0, 2),
                    "freshness": round(a.get("freshness_score", 0.85), 2),
                    "final_score": round(a.get("final_score", a.get("rag_score", 5.0)), 2)
                }
                for a in selected_articles
            ],
            "rejected_articles": [
                {
                    "title": a.get("title", ""),
                    "source_id": a.get("id", ""),
                    "trs": round(a.get("trs", 0), 2),
                    "freshness": round(a.get("freshness_score", 0.85), 2),
                    "reason_code": a.get("reject_reason", "LOW_SCORE")
                }
                for a in rejected_articles
            ]
        }
    }
    report_json = json.dumps(report_data, ensure_ascii=False, indent=2)
    return f"""## 🗺️ 系統可解釋性報告 (Explainability Report)

> **可解釋性層 (Explainability Layer)**：以下為本專題生成時的檢索排序與過濾決策，確保推論透明度。

```json
{report_json}
```

---

"""


# ==============================================================
# V3.5 Decision Memory：決策記憶生成
# ==============================================================
def generate_decision_memory(tag, claim_pool):
    """V3.5：根據主題與 Claim Pool，呼叫 LLM 生成 Decision Memory JSON 區塊"""
    claims_summary = "\n".join(
        f"- [{c.get('evidence_type','?')}] {c.get('claim','')} (可信度: {c.get('confidence',0):.2f})"
        for c in claim_pool[:6]
    ) if claim_pool else "（無 Claim Pool 資料）"

    prompt = f"""
你是一位決策記憶設計師。基於以下主題與核心主張，設計一個「決策記憶」JSON 結構。

主題：{tag}
核心主張摘要：
{claims_summary}

請生成一個 JSON 物件，包含以下欄位：
- decision: 一句話說明基於以上主張，對此主題最核心的決策或行動結論（繁體中文）
- because: 3 條支撐此決策的主要理由（各對應一個 Claim），每條約 20-30 字
- revisit_triggers: 一個物件，定義什麼時候應重新審視此決策，包含 3~4 個可量化的觸發條件（例如時間週期、KPI 閾值）

只回傳 strict JSON，不要有 ```json 包覆，不要有其他說明。格式範例：
{{
  "decision": "...",
  "because": ["理由1", "理由2", "理由3"],
  "revisit_triggers": {{
    "time_interval_days": 90,
    "key_metric_threshold": "..."
  }}
}}
"""
    for attempt in range(2):
        try:
            if engine_name == "deepseek":
                response = openai_client.chat.completions.create(
                    model="deepseek-chat",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "Design decision memory structures. Output strict JSON."},
                        {"role": "user", "content": prompt}
                    ]
                )
                res_text = response.choices[0].message.content
            elif engine_name == "gemini":
                try:
                    response = gemini_client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                        config={"response_mime_type": "application/json"}
                    )
                    res_text = response.text
                except Exception:
                    response = gemini_client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt
                    )
                    res_text = response.text
            else:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "Design decision memory structures. Output strict JSON."},
                        {"role": "user", "content": prompt}
                    ]
                )
                res_text = response.choices[0].message.content

            res_text = res_text.strip()
            if res_text.startswith("```"):
                res_text = re.sub(r'^```(?:json)?\n?', '', res_text)
                res_text = re.sub(r'\n?```$', '', res_text).strip()

            dm = json.loads(res_text)
            # 包裝為 decision_memory 結構
            return {"decision_memory": dm}
        except Exception as e:
            print(f"    [WARN] Decision Memory 生成失敗 (嘗試 {attempt+1}): {e}")
            time.sleep(3)

    # 回退方案
    return {
        "decision_memory": {
            "decision": f"針對「{tag}」主題的核心決策（自動生成失敗，請手動補充）",
            "because": ["文獻提供核心事實依據"],
            "revisit_triggers": {"time_interval_days": 90}
        }
    }


def ask_llm(tag, articles, core_articles_content, devils_advocate_critique="", claim_pool=None):
    """混合式 RAG + V3.5 升級：利用核心文章全文與其他文章摘要，融會貫通合成一篇專題知識文章
    支援嚴格引用標註、惡魔代言人思辨、Context Graph 情境差異對比、Synthesis/Hypothesis 雙軌輸出"""
    
    # 建立一個文獻編號映射，方便 LLM 引用
    all_citations = []
    for idx, art in enumerate(core_articles_content, 1):
        all_citations.append({
            "num": idx,
            "title": art["title"],
            "url": art["url"],
            "type": "core",
            "year": art["year"],
            "content_preview": art["content"][:2500]
        })
        
    start_num = len(core_articles_content) + 1
    for idx, art in enumerate(articles, start_num):
        year = art['created_time'][:4] if art['created_time'] else "未知"
        all_citations.append({
            "num": idx,
            "title": art["title"],
            "url": art["url"],
            "type": "summary",
            "year": year,
            "summary": art["summary"]
        })

    prompt = f"你是一個極度嚴謹的知識整理與內容策劃專家。請將以下關於『{tag}』主題的參考文獻進行深度融會貫通，撰寫一篇有系統、結構完整且具備技術細節的『專題知識文章』。\n\n"
    
    prompt += "=== 參考文獻清單（請根據以下文獻的編號進行正文段落內標註引用） ===\n"
    for cit in all_citations:
        prompt += f"【資料庫文獻 {cit['num']}】標題：{cit['title']}\n"
        prompt += f"發表年份：{cit['year']} | 連結：{cit['url'] if cit['url'] else '無'}\n"
        if cit["type"] == "core":
            prompt += f"核心內文細節：\n{cit['content_preview']}\n"
        else:
            prompt += f"摘要內容：{cit['summary']}\n"
        prompt += "-" * 40 + "\n"
        
    if devils_advocate_critique:
        prompt += "=== 惡魔代言人批判與反向觀點 ===\n"
        prompt += devils_advocate_critique + "\n\n"
        
    # 加入 V3.5 Claim Pool 摘要供 LLM 參考（限前 6 條）
    if claim_pool:
        prompt += "=== V3.5 Claim Pool（預提取的結構化事實，供正文引用時交叉驗證） ===\n"
        for i, c in enumerate(claim_pool[:6], 1):
            prompt += f"[Claim {i}][{c.get('evidence_type','?')}][可信度:{c.get('confidence',0):.2f}] {c.get('claim','')}\n"
            prompt += f"  原文引用：{c.get('evidence_quote','')[:200]}\n"
        prompt += "\n"

    prompt += """
請以繁體中文撰寫，並格式化為乾淨的 Markdown 格式，且必須嚴格遵守以下學術與思辨規範：

1. 主標題格式：請根據您彙整後的文章實際核心內容，擬定一個專業、具備吸引力且與內容高度契合的中文標題，格式為：`## [自訂標題]`。例如 `## 打造高效團隊：n8n 流程自動化與專案治理實踐`。
2. 前言：說明這個主題在現代數位/工作場景中的價值與演進脈絡。
3. 核心觀點與概念彙整：
   - 整合文獻的精髓，整理出 2-3 個深入的觀點，並以標題與段落詳細展開。
   - 【硬性要求 - 來源區分與標註】：
     - 凡是來自於上方『參考文獻清單』中的內容（包含觀點、數據、案例），在正文中引用時，必須在句子或段落結尾嚴格標註出處（格式為：`[資料庫文獻 X]`，例如：`...以此來降低 Token 浪費 [資料庫文獻 1]。` 或 `...適用於快速開發 [資料庫文獻 2, 3]。`）。
     - 凡是您（AI）為了補充主題完整性、進行深入研究而從外部引入的知識、背景或延伸分析，必須標註 `[外部補充/AI延伸]`（例如：`...業界通常會結合自動化測試 [外部補充/AI延伸]。`）。
     - 【文獻佔比】：整篇文章的內容中，來自『參考文獻清單』的內容佔比必須至少有 70% 以上，嚴禁完全脫離文獻清單憑空捏造無關的科普大話。
   - 請根據文獻的發表年份，在撰寫核心觀點時展現出「時間演進」的技術發展脈絡，避免時空錯置。
   - 【V3.5 跨文獻綜合發現 (Synthesis) 與研究假說 (Hypothesis) 雙軌輸出】：
     - 若多篇文獻的客觀事實交叉印證出一個新觀點，請以標題 `### 💡 【跨文獻綜合發現 (Synthesis)】` 呈現。
     - 若你基於文獻事實進行了合理的邏輯外推，請以標題 `### 🔮 【研究假說 (Hypothesis)】` 呈現，並清楚說明這是 AI 推測而非已被文獻完全證實的結論。
     - 【硬性要求】：若文章中既無 Synthesis 也無 Hypothesis，則整篇文章視為「基礎摘要」，不得稱為「深度專題文章」。
   - 【V3.8 情境脈絡對比 (Context Graph)】：若發現兩篇以上文獻在某議題上結論不同，請不要一味判斷對錯，改以 `### ⚖️ 【情境差異對比 (Context Graph)】` 標題呈現，分析各結論各自適用的情境條件（例如：團隊規模、技術棧、使用情境等）。
4. 【硬性要求】反向觀點與不適用情境：
   - 必須包含一個大標題 `#### 反向觀點與不適用情境`。
   - 整合上述提供之惡魔代言人批判，深入探討此主題/技術的侷限性、業界失敗案例，以及在什麼特定情境下絕對不該採用，讓專題文章具備客觀辯證與風險防範價值。論述時凡是基於參考文獻的批判請標註 `[資料庫文獻 X]`，AI延伸分析請標註 `[外部補充/AI延伸]`。
5. 實踐與下一步行動計畫：
   - 必須包含一個大標題 `#### 下一步行動計畫 (Action Items)`。
   - 提供 2-3 個具體、個人可落地執行、高度具體實踐性的任務，格式化為 Markdown 任務列表。
   - 【警告】：絕對禁止生成與個人開發者/知識庫使用者無關的空洞大企業或政府套話（例如「設立倫理委員會」、「投資數據治理」、「建立合規團隊」、「推動立法」等）。
   - 即使文獻討論的是宏觀的「AI 治理與政策」，也必須在行動計畫中將其轉化為個人在日常開發/使用 AI 時可落地之操作，例如：「使用本地 ollama 跑敏感資料以防洩露 [資料庫文獻 1]」或「在 IDE 提示詞中加入安全護欄 [外部補充/AI延伸]」。
   - 每個行動指引後必須標註其出處（如：`[資料庫文獻 1]` 或 `[外部補充/AI延伸]`）。
6. 關於參考文獻列表：
   - 【硬性要求】不要在文章末尾自己生成「參考文獻」區塊。請寫到下一步行動計畫結束即可，不要輸出任何參考文獻清單！

注意：請直接回傳 Markdown 文本，不要用 ```markdown 標籤包覆，也不要有任何無關的開頭或結尾問候。
"""

    system_prompt = "你是一個極度嚴謹的知識庫彙整專家（V3.5 DKMS）。你必須嚴格遵守引用標註指令，在正文的每一句陳述結尾，強制標註 `[資料庫文獻 X]`（源自提供文獻）或 `[外部補充/AI延伸]`（源自你的外部知識）。必須輸出 Synthesis/Hypothesis 雙軌發現。若文獻結論有情境差異，必須輸出情境差異對比而非是非判斷。絕對禁止漏掉引用標記。不要自己生成文末的『參考文獻』區塊。"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            if engine_name == "deepseek":
                response = openai_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content
            elif engine_name == "gemini":
                response = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config={"system_instruction": system_prompt}
                )
                return response.text
            else:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content
        except Exception as e:
            print(f"  [WARN] LLM 呼叫失敗: {e}，將在 5 秒後重試...")
            time.sleep(5)
            
    print("  [ERROR] LLM 呼叫失敗，已達最大重試次數。")
    return None

def ask_devils_advocate(tag, core_articles_content, other_articles):
    """扮演惡魔代言人，對該主題的主流觀點提出質疑、反向思考、失敗案例及不適用情境"""
    prompt = f"""
    你是一位極度挑剔、擅長批判思考與規避風險的「惡魔代言人（Devil's Advocate）」。
    針對主題『{tag}』，主流的參考文獻內容如下：
    
    """
    
    # 加入文獻內容摘要
    for idx, art in enumerate(core_articles_content, 1):
        prompt += f"【文獻 {idx}】標題：{art['title']}\n"
        prompt += f"內文片段：{art['content'][:1500]}\n\n"
        
    for idx, art in enumerate(other_articles, len(core_articles_content)+1):
        prompt += f"【文獻 {idx}】標題：{art['title']}\n"
        prompt += f"摘要：{art['summary']}\n\n"
        
    prompt += """
    請針對上述文獻提倡的方法、技術 or 觀點，進行深度反思與批判，並回傳以下三個部分的繁體中文分析：
    
    1. 反對該思維/技術的主流質疑或反向觀點 (至少 2 點)。
    2. 業界可能發生的經典失敗案例或落地痛點 (例如過度工程化、學習曲線陡峭、維護成本高等)。
    3. 什麼特定條件或情境下「絕對不該使用」此方法或技術 (不適用情境)。
    
    請以 Markdown 格式輸出，直接回傳正文，不要用 ```markdown 標籤包覆，也不要有任何無關的開頭或結尾問候。
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if engine_name == "deepseek":
                response = openai_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "You are a critical thinker and risk assessment expert. Output Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content
            elif engine_name == "gemini":
                response = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
                return response.text
            else:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a critical thinker and risk assessment expert. Output Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content
        except Exception as e:
            print(f"  [WARN] 惡魔代言人 LLM 呼叫失敗: {e}，將在 3 秒後重試...")
            time.sleep(3)
            
    return "無法生成反向觀點。"

def extract_action_items(markdown_text):
    """從 Markdown 中提取下一步行動計畫清單"""
    action_items = []
    lines = markdown_text.split('\n')
    in_action_section = False
    for line in lines:
        line_strip = line.strip()
        # 尋找行動計畫區塊
        if "下一步行動" in line_strip or "Action Items" in line_strip or "行動計畫" in line_strip:
            in_action_section = True
            continue
        if in_action_section:
            # 碰到了其他標題，且已經有收集到東西，則退出
            if line_strip.startswith('#'):
                if action_items:
                    break
                continue
            # 匹配 - [ ] 任務名稱 或 - [x] 任務名稱 或 - 任務名稱
            match = re.match(r'^[-*]\s*(?:\[\s*[xX\s]?\s*\])?\s*(.+)$', line_strip)
            if match:
                item_content = match.group(1).strip()
                # 剔除參考文獻的引用標註，如 [1] 或 [2, 3]
                item_content = re.sub(r'\[\d+(?:\s*,\s*\d+)*\]', '', item_content).strip()
                if item_content:
                    action_items.append(item_content)
    
    # 備份：如果在 "下一步行動" 區間找不到，就在全文找 - [ ] 或 - [x]
    if not action_items:
        for line in lines:
            line_strip = line.strip()
            match = re.match(r'^[-*]\s*\[\s*[xX\s]?\s*\]\s*(.+)$', line_strip)
            if match:
                item_content = match.group(1).strip()
                item_content = re.sub(r'\[\d+(?:\s*,\s*\d+)*\]', '', item_content).strip()
                if item_content:
                    action_items.append(item_content)
                
    return action_items

def create_task_in_db(notion, task_db_id, task_name, source_page_id):
    """在 Notion 任務資料庫中建立一筆 Task 紀錄（相容新版 data_source DB，不依賴 retrieve properties）"""
    # 新版 Notion Private Integration 的 data_source 型 DB，databases.retrieve 回傳的 properties 可能為空 {}
    # 因此改用「候選欄位清單直接嘗試寫入」策略，按優先序逐一嘗試常見 title 欄位名稱
    title_field_candidates = ["名稱", "Name", "任務名稱", "Title", "標題", "任務"]
    
    for title_field in title_field_candidates:
        try:
            page_properties = {
                title_field: {
                    "title": [{"text": {"content": task_name[:2000]}}]
                }
            }
            result = notion.pages.create(
                parent={"database_id": task_db_id},
                properties=page_properties
            )
            return True
        except Exception as e:
            err_msg = str(e)
            # 如果是欄位不存在的錯誤，繼續嘗試下一個候選
            if "property" in err_msg.lower() or "validation" in err_msg.lower() or "does not exist" in err_msg.lower():
                continue
            # 其他錯誤（權限、網路等）直接報錯並返回
            print(f"      [WARN] 寫入任務資料庫失敗 (欄位={title_field}): {err_msg[:120]}")
            return False
    
    print(f"      [WARN] 寫入任務資料庫失敗：無法找到可用的 title 欄位（嘗試了 {title_field_candidates}）")
    return False



def parse_rich_text(text):
    """解析 Markdown 的粗體、斜體、行內程式碼、連結與純網址，並轉換為 Notion 的 rich_text 格式"""
    pattern = re.compile(
        r'\[([^\]]+)\]\((https?://[^\s\)]+)\)|'  # group 1, 2: Markdown 連結
        r'(https?://[^\s\)]+)|'                  # group 3: 純網址
        r'\*\*([^*]+)\*\*|__([^_]+)__|'           # group 4, 5: 粗體
        r'\*([^*]+)\*|_([^_]+)_|'                 # group 6, 7: 斜體
        r'`([^`]+)`'                              # group 8: 行內程式碼
    )
    
    last_idx = 0
    rich_text = []
    
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last_idx:
            rich_text.append({"type": "text", "text": {"content": text[last_idx:start]}})
            
        g1, g2, g3, g4, g5, g6, g7, g8 = match.groups()
        
        if g1 and g2:
            # Markdown 連結
            rich_text.append({
                "type": "text",
                "text": {"content": g1, "link": {"url": g2}}
            })
        elif g3:
            # 純網址
            rich_text.append({
                "type": "text",
                "text": {"content": g3, "link": {"url": g3}}
            })
        elif g4 or g5:
            # 粗體
            content = g4 if g4 else g5
            rich_text.append({
                "type": "text",
                "text": {"content": content},
                "annotations": {"bold": True}
            })
        elif g6 or g7:
            # 斜體
            content = g6 if g6 else g7
            rich_text.append({
                "type": "text",
                "text": {"content": content},
                "annotations": {"italic": True}
            })
        elif g8:
            # 行內程式碼
            rich_text.append({
                "type": "text",
                "text": {"content": g8},
                "annotations": {"code": True}
            })
            
        last_idx = end
        
    if last_idx < len(text):
        rich_text.append({"type": "text", "text": {"content": text[last_idx:]}})
        
    if not rich_text:
        rich_text.append({"type": "text", "text": {"content": text if text else " "}})
        
    return rich_text

def markdown_to_notion_blocks(markdown_text):
    """將 Markdown 文字解析並轉換為 Notion 的區塊 (Blocks) 格式，支援待辦清單與原生代碼區塊"""
    blocks = []
    lines = markdown_text.split('\n')
    
    in_code_block = False
    code_content = []
    code_language = "plain text"
    
    for line in lines:
        stripped_line = line.strip()
        
        # 處理代碼區塊的開頭與結束
        if stripped_line.startswith('```'):
            if in_code_block:
                # 結束代碼區塊，封裝為 Notion code block
                full_code = '\n'.join(code_content)
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": full_code}
                            }
                        ],
                        "language": code_language
                    }
                })
                in_code_block = False
                code_content = []
            else:
                # 開始代碼區塊，判定語言
                in_code_block = True
                lang = stripped_line[3:].strip().lower()
                if lang in ("js", "javascript"):
                    code_language = "javascript"
                elif lang in ("ts", "typescript"):
                    code_language = "typescript"
                elif lang in ("py", "python"):
                    code_language = "python"
                elif lang in ("json",):
                    code_language = "json"
                elif lang in ("html", "css", "yaml", "markdown", "sql"):
                    code_language = lang
                else:
                    code_language = "plain text"
            continue
            
        if in_code_block:
            # 代碼區塊內部保留原汁原味的縮排與底線
            code_content.append(line)
            continue
            
        if not stripped_line:
            continue
            
        # 解析標題 (支援 # 到 ######，自動降級大於 3 級的標題，並剔除字首的 # 號)
        header_match = re.match(r'^(#{1,6})\s+(.*)$', stripped_line)
        if header_match:
            level = len(header_match.group(1))
            content = header_match.group(2)
            heading_type = f"heading_{min(level, 3)}"
            blocks.append({
                "object": "block",
                "type": heading_type,
                heading_type: {
                    "rich_text": parse_rich_text(content)
                }
            })
        # 解析待辦清單 (To-Do List Checkbox)
        elif re.match(r'^[-*]\s*\[\s*([xX\s]?)\s*\]\s*(.*)$', stripped_line):
            todo_match = re.match(r'^[-*]\s*\[\s*([xX\s]?)\s*\]\s*(.*)$', stripped_line)
            checked = todo_match.group(1).lower() == 'x'
            content = todo_match.group(2).strip()
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": parse_rich_text(content),
                    "checked": checked
                }
            })
        # 解析一般無序清單
        elif stripped_line.startswith('- ') or stripped_line.startswith('* '):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": parse_rich_text(stripped_line[2:])
                }
            })
        elif re.match(r'^\d+\.\s', stripped_line):
            content = re.sub(r'^\d+\.\s', '', stripped_line)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": parse_rich_text(content)
                }
            })
        # 預設為一般段落
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": parse_rich_text(line)
                }
            })
            
    return blocks


def filter_and_validate_markdown_citations(markdown_text, all_citations):
    """使用 Python 對 LLM 回傳的 Markdown 進行引用的二次校驗，並提取正文中的外部文獻"""
    max_valid_num = len(all_citations)
    
    # 1. 修正正文中的超標引用編號（例如只給了 3 篇，LLM 卻寫了 [資料庫文獻 5]）
    def replace_citation(match):
        cit_str = match.group(1)
        nums = [int(n) for n in re.findall(r'\d+', cit_str)]
        valid_nums = [n for n in nums if 1 <= n <= max_valid_num]
        if not valid_nums:
            return ""
        return "[資料庫文獻 " + ", ".join(map(str, valid_nums)) + "]"
        
    fixed_text = re.sub(r'\[資料庫文獻\s*(\d+(?:\s*,\s*\d+)*)\]', replace_citation, markdown_text)
    
    # 同時相容舊的 [X] 格式，以防 LLM 仍然寫成 [1] 的格式
    def replace_old_citation(match):
        cit_str = match.group(1)
        nums = [int(n) for n in re.findall(r'\d+', cit_str)]
        valid_nums = [n for n in nums if 1 <= n <= max_valid_num]
        if not valid_nums:
            return ""
        return "[資料庫文獻 " + ", ".join(map(str, valid_nums)) + "]"
        
    fixed_text = re.sub(r'\[(\d+(?:\s*,\s*\d+)*)\]', replace_old_citation, fixed_text)
    
    # 2. 提取正文中的 [外部文獻: 標題](網址)
    external_pattern = re.compile(r'\[外部文獻:\s*([^\]]+)\]\(((?:https?://)[^\s\)]+)\)')
    external_citations = []
    seen_urls = set()
    
    temp_num = max_valid_num + 1
    
    def match_external(match):
        nonlocal temp_num
        title = match.group(1).strip()
        url = match.group(2).strip()
        
        if url not in seen_urls:
            seen_urls.add(url)
            external_citations.append({
                "num": temp_num,
                "title": title,
                "url": url
            })
            curr_num = temp_num
            temp_num += 1
        else:
            curr_num = next(ec["num"] for ec in external_citations if ec["url"] == url)
            
        return f"[外部文獻 {curr_num}]"
        
    fixed_text = external_pattern.sub(match_external, fixed_text)
    
    # 3. 物理截斷：如果 LLM 自己生成了參考文獻區塊，直接將其完全切除，交由 Python 自動生成
    lines = fixed_text.split('\n')
    cleaned_lines = []
    for line in lines:
        if any(h in line for h in ["#### 參考文獻", "### 參考文獻", "## 參考文獻", "Reference"]):
            break
        cleaned_lines.append(line)
        
    return '\n'.join(cleaned_lines).strip(), external_citations

def extract_summary_points_tags(summary_text, default_tag):
    """解析 LLM 輸出的摘要、核心知識點與標籤"""
    summary_part = ""
    points_part = ""
    tags = []
    
    # 預設標籤以防完全解析不到，截斷至 20 個字
    tags.append({"name": default_tag[:20]})
    
    try:
        # 1. 提取一句話摘要
        if "【一句話摘要】" in summary_text:
            s_idx = summary_text.find("【一句話摘要】") + len("【一句話摘要】")
            p_idx = summary_text.find("【3個核心知識點】") if "【3個核心知識點】" in summary_text else len(summary_text)
            summary_part = summary_text[s_idx:p_idx].strip()
        
        # 2. 提取核心知識點
        if "【3個核心知識點】" in summary_text:
            p_idx = summary_text.find("【3個核心知識點】") + len("【3個核心知識點】")
            t_idx = summary_text.find("【AI標籤】") if "【AI標籤】" in summary_text else len(summary_text)
            points_part = summary_text[p_idx:t_idx].strip()
            
        # 3. 提取 AI 標籤
        if "【AI標籤】" in summary_text:
            t_idx = summary_text.find("【AI標籤】") + len("【AI標籤】")
            tags_str = summary_text[t_idx:].strip()
            # 以逗號、頓號或空白拆分
            raw_tags = re.split(r'[,，、\s\n]+', tags_str)
            parsed_tags = []
            for rt in raw_tags:
                rt = rt.strip()
                # 限制標籤長度不超過 8 個字，且防呆空值
                if rt and len(rt) <= 8 and rt not in ["AI標籤", "AI標籤】"]:
                    parsed_tags.append({"name": rt})
            if parsed_tags:
                tags = parsed_tags
    except Exception as e:
        print(f"    [WARN] 解析摘要、知識點與標籤失敗: {e}")
        
    # 長度限制
    if len(summary_part) > 200:
        summary_part = summary_part[:197] + "..."
    if not summary_part:
        summary_part = f"關於『{default_tag}』主題的知識彙整專題文章。"
        
    return summary_part, points_part, tags

def generate_core_knowledge_points(markdown_article):
    """根據專題文章內容，呼叫 LLM 生成符合特定格式的 AI 核心知識點與簡短標籤"""
    prompt = f"""
    請閱讀以下知識專題文章，為其提煉出「一句話摘要」、「3個核心知識點」與「2-4個簡短的AI標籤（如：RAG, AI治理, 自動化, 軟體工程，每個標籤不超過6個字）」。
    
    文章內容：
    {markdown_article}
    
    【硬性要求】你必須嚴格遵守以下格式回傳（包含【】括號字元，且不要有任何 markdown 代碼塊包覆或多餘問候語，字詞需為繁體中文）：
    【一句話摘要】
    [請在此處用一兩句話精煉概括文章的核心主題與價值]
    【3個核心知識點】
    - 知識點 1: [具體且具含金量的知識點 1]
    - 知識點 2: [具體且具含金量的知識點 2]
    - 知識點 3: [具體且具含金量的知識點 3]
    【AI標籤】
    標籤1, 標籤2, 標籤3
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if engine_name == "deepseek":
                response = openai_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "You are a precise summarizer. Output strictly according to the format in Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content.strip()
            elif engine_name == "gemini":
                response = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
                return response.text.strip()
            else:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a precise summarizer. Output strictly according to the format in Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"  [WARN] 核心知識點提煉 LLM 呼叫失敗: {e}，將在 5 秒後重試...")
            time.sleep(5)
            
    # 備份回退方案
    return "【一句話摘要】\n關於此專題的知識彙整文章。\n【3個核心知識點】\n- 知識點 1: 整合了多篇核心文獻的關鍵見解。\n- 知識點 2: 提供具體可操作的實踐建議與行動方案。\n- 知識點 3: 展現出技術或觀點的時間演進脈絡。\n【AI標籤】\nAI知識, 專題彙整"

def write_notion_page_with_blocks(notion, database_id, page_title, summary_part, points_part, tag_options, blocks):
    """分頁追加寫入：建立頁面並分批寫入 blocks，完全突破 Notion 的 100 筆區塊負載限制"""
    first_chunk_size = 80
    first_chunk = blocks[:first_chunk_size]
    remaining_chunks = [blocks[i:i+80] for i in range(first_chunk_size, len(blocks), 80)]
        
    # 建立頁面並寫入第一批 blocks
    new_page = notion.pages.create(
        parent={"database_id": database_id},
        properties={
            "Name": {
                "title": [
                    {
                        "text": {
                            "content": page_title
                        }
                    }
                ]
            },
            "AI摘要": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": summary_part
                        }
                    }
                ]
            },
            "AI知識點": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": points_part
                        }
                    }
                ]
            },
            "AI 標籤": {
                "multi_select": tag_options
            }
        },
        children=first_chunk
    )
    
    page_id = new_page["id"]
    
    # 分批追加寫入其餘 blocks
    for idx, chunk in enumerate(remaining_chunks, 1):
        if chunk:
            print(f"    [+] 正在追加寫入後續區塊 (分頁 {idx}/{len(remaining_chunks)})...")
            notion.blocks.children.append(block_id=page_id, children=chunk)
            time.sleep(0.5) # 遵守 Notion API 頻率限制
            
    return page_id

def get_page_title(page):
    properties = page.get("properties", {})
    for name, prop in properties.items():
        if prop.get("type") == "title":
            title_objs = prop.get("title", [])
            return "".join([t.get("plain_text", "") for t in title_objs])
    return "無標題"

def get_page_url_property(page):
    properties = page.get("properties", {})
    for name, prop in properties.items():
        if prop.get("type") == "url":
            return prop.get("url") or ""
    return ""

def get_page_summary(page):
    properties = page.get("properties", {})
    for name, prop in properties.items():
        if name == "AI 摘要" and prop.get("type") == "rich_text":
            rich_texts = prop.get("rich_text", [])
            return "".join([t.get("plain_text", "") for t in rich_texts])
    return ""

def main():
    parser = argparse.ArgumentParser(description="生產級 Notion 知識庫多主題 AI 彙整提煉與寫回器")
    parser.add_argument("--source-ds", default="06d38af4-6d06-4ad6-a4c6-831809c908fa", help="來源資料來源 ID")
    parser.add_argument("--dest-db", default="3717152bd49e80159327dfa47874a1b3", help="目標彙整資料庫 ID")
    parser.add_argument("--count", type=int, default=3, help="要抽選並產生的專題文章主題個數")
    parser.add_argument("--max-source", type=int, default=2000, dest="max_source",
                        help="從來源 DB 最多撈取多少筆已處理文章（預設 2000，涵蓋大型知識庫）")
    parser.add_argument("--sample-size", type=int, default=400, dest="sample_size",
                        help="品質過濾+分層抽樣後的目標素材量（預設 400，控制聚類 prompt 大小）")
    parser.add_argument("--min-qs", type=float, default=5.0, dest="min_qs",
                        help="納入素材池的最低 QS 門檻（預設 5.0；提高可過濾低品質文章）")
    args = parser.parse_args()

    notion_token = os.getenv("NOTION_API_KEY")
    if not notion_token:
        print("[ERROR] 未在 .env 中設定 NOTION_API_KEY")
        sys.exit(1)
        
    print("=" * 60)
    print("[INFO] 生產級 Notion 知識彙整器啟動...")
    print(f"來源資料來源 ID: {args.source_ds}")
    print(f"目標資料庫 ID: {args.dest_db}")
    print("=" * 60)
    
    notion = Client(auth=notion_token)
    init_llm()
    
    # 1. 撈取已處理文章
    print("\n[INFO] 正在從來源資料庫撈取已處理的文章與標籤...")
    pages = []
    next_cursor = None
    max_source = getattr(args, 'max_source', 500)  # 預設最多撈 500 筆，避免語意聚類 prompt 過大
    try:
        while len(pages) < max_source:
            kwargs = {
                "data_source_id": args.source_ds,
                "filter": {
                    "property": "AI 已處理",
                    "checkbox": {"equals": True}
                },
                "page_size": 100
            }
            if next_cursor:
                kwargs["start_cursor"] = next_cursor
            query_results = notion.data_sources.query(**kwargs)
            batch = query_results.get("results", [])
            pages.extend(batch)
            has_more = query_results.get("has_more", False)
            next_cursor = query_results.get("next_cursor")
            if not has_more or not next_cursor:
                break
        print(f"[INFO] 成功讀取到 {len(pages)} 筆已處理的文章（上限 {max_source} 筆）。")
    except Exception as e:
        print(f"[ERROR] 撈取來源資料庫失敗: {e}")
        sys.exit(1)

    if not pages:
        print("[WARN] 沒有找到任何 AI 已處理的文章，請先執行 batch_processor.py 進行提煉。")
        sys.exit(0)

    # 1.5 品質過濾 + 分層抽樣：從大型資料庫中智慧選出精華素材池
    raw_count = len(pages)
    pages, n_inspired, n_qualified = smart_sample_articles(
        pages,
        sample_size=args.sample_size,
        min_qs=args.min_qs,
        inspired_quota=min(60, args.sample_size // 5)
    )
    print(f"[INFO] 智慧抽樣完成：")
    print(f"       原始撈取 {raw_count} 筆 → 深受啟發 {n_inspired} 篇 + 合格(QS≥{args.min_qs}) {n_qualified} 篇")
    print(f"       → 最終素材池 {len(pages)} 篇（分層抽樣，維持跨領域多樣性）")

    # 2. 建立標籤對應表 (tag -> list of pages)
    tag_map = {}
    all_raw_tags = set()
    articles_by_id = {}
    articles_brief = []
    for page in pages:
        title = get_page_title(page)
        url = get_page_url_property(page)
        summary = get_page_summary(page)
        created_time = page.get("created_time")
        
        if not summary:
            continue
            
        # 智慧尋找有值的標籤欄位：'AI 標籤' -> 'Tag' -> 空字串 ''
        props = page.get("properties", {})
        tags = []
        for field in ["AI 標籤", "Tag", ""]:
            if field in props:
                val = props[field].get("multi_select", [])
                if val:
                    tags = val
                    break
                    
        # 如果皆為空，則以優先序獲取對應欄位
        if not tags:
            for field in ["AI 標籤", "Tag", ""]:
                if field in props:
                    tags = props[field].get("multi_select", [])
                    break
                    
        # 偵測是否為「深受啟發」的精華文章
        inspired_prop = page.get("properties", {}).get("深受啟發", {}).get("select")
        is_inspired = inspired_prop is not None and inspired_prop.get("name") == "深受啟發"
        
        # 讀取可信度 (Number, 預設為 5)
        cred_prop = page.get("properties", {}).get("可信度", {}).get("number")
        credibility = cred_prop if cred_prop is not None else 5.0
        
        # 讀取可執行性 (Number, 預設為 5)
        act_prop = page.get("properties", {}).get("可執行性", {}).get("number")
        actionability = act_prop if act_prop is not None else 5.0
        
        # 主觀啟發分數：深受啟發為 10，否則為 5
        inspiration = 10.0 if is_inspired else 5.0
        
        # 多維度加權排序 RAG Score 公式（即 QS，Quality Score）
        rag_score = 0.4 * credibility + 0.3 * actionability + 0.3 * inspiration

        # V3 TRS (Topic Relevance Score) 預設為 0.5（在主題匹配時再動態計算）
        # V3.8 領域自適應時間衰減：讀取標籤名稱作為領域線索
        simple_tag_names = [t.get("name", "") for t in tags if t.get("name")]
        freshness_score = compute_freshness_score(created_time, simple_tag_names)
        # V3.8 Final Score 公式：(0.7 * TRS + 0.3 * QS_norm) * freshness
        # TRS 暫時以 0.5 佔位，在主題匹配後再修正；QS 正規化到 0~1 範圍
        qs_norm = rag_score / 10.0
        final_score = (0.7 * 0.5 + 0.3 * qs_norm) * freshness_score
        
        for t in tags:
            tag_name = t.get("name")
            if tag_name:
                all_raw_tags.add(tag_name)
                tag_map.setdefault(tag_name, []).append({
                    "id": page["id"],
                    "title": title,
                    "url": url,
                    "summary": summary,
                    "created_time": created_time,
                    "is_inspired": is_inspired,
                    "credibility": credibility,
                    "actionability": actionability,
                    "inspiration": inspiration,
                    "rag_score": rag_score,
                    "freshness_score": freshness_score,
                    "final_score": final_score,
                    "trs": 0.5  # 佔位，主題匹配後更新
                })
        
        # 儲存到 articles_by_id 與 articles_brief 供語意聚類 fallback 使用
        art_info = {
            "id": page["id"],
            "title": title,
            "url": url,
            "summary": summary,
            "created_time": created_time,
            "is_inspired": is_inspired,
            "credibility": credibility,
            "actionability": actionability,
            "inspiration": inspiration,
            "rag_score": rag_score,
            "freshness_score": freshness_score,
            "final_score": final_score,
            "trs": 0.5
        }
        clean_id = page["id"].replace("-", "").lower()
        articles_by_id[clean_id] = art_info
        
        simple_tags = [t.get("name") for t in tags if t.get("name")]
        articles_brief.append({
            "id": page["id"],
            "title": title,
            "tags": simple_tags,
            "summary": summary
        })
                
    # 3. 標籤清洗與去重 (Tag De-duplication)
    print("\n[INFO] 正在進行標籤清理與去重...")
    cleaned_tag_map = {}
    for raw_tag in all_raw_tags:
        cleaned = raw_tag.strip()
        if not cleaned:
            continue
        # 大小寫對齊
        key = cleaned.lower()
        cleaned_tag_map.setdefault(key, []).append(raw_tag)
        
    standard_tag_map = {}
    for key, raws in cleaned_tag_map.items():
        std_name = raws[0] # 以第一個出現的原始標籤名作為標準名
        seen_ids = set()
        merged_articles = []
        for r in raws:
            for art in tag_map.get(r, []):
                if art["id"] not in seen_ids:
                    seen_ids.add(art["id"])
                    merged_articles.append(art)
        if merged_articles:
            standard_tag_map[std_name] = merged_articles
            
    # 撈取目標資料庫中已存在的專題文章的標籤以進行精準去重（分頁迴圈確保完整）
    print("\n[INFO] 正在撈取目標資料庫中已存在的專題文章以進行去重...")
    existing_tags = set()
    existing_titles = set()
    try:
        target_db_clean = args.dest_db.replace("-", "").lower()
        search_cursor = None
        while True:
            search_kwargs = {
                "filter": {"property": "object", "value": "page"},
                "page_size": 100
            }
            if search_cursor:
                search_kwargs["start_cursor"] = search_cursor
            search_results = notion.search(**search_kwargs)
            for page in search_results.get("results", []):
                p_id = page.get("parent", {}).get("database_id", "").replace("-", "").lower()
                if p_id == target_db_clean:
                    props = page.get("properties", {})
                    tags_prop = props.get("AI 標籤", {}).get("multi_select", [])
                    for t in tags_prop:
                        tag_name = t.get("name")
                        if tag_name:
                            existing_tags.add(tag_name.strip().lower())
                    # 同時記錄已存在的標題（以名稱去重）
                    for k, v in props.items():
                        if v.get("type") == "title":
                            title_val = "".join([t.get("plain_text", "") for t in v.get("title", [])])
                            if title_val:
                                existing_titles.add(title_val.strip())
                            break
            if not search_results.get("has_more") or not search_results.get("next_cursor"):
                break
            search_cursor = search_results.get("next_cursor")
        print(f"[INFO] 目標資料庫中已存在 {len(existing_tags)} 個主題標籤、{len(existing_titles)} 篇專題文章，將排除以防重複。")
    except Exception as e:
        print(f"[WARN] 撈取目標資料庫已存在頁面失敗: {e}，將跳過增量去重防護。")

    # 篩選出至少有 2 篇文章以上的標準標籤，排除太過寬泛的大型標籤
    BROAD_TAGS_BLACKLIST = {
        "ai工具", "ai應用", "ai", "工具", "科技", "資訊", "未分類", "tag", "無標籤",
        "ai 應用", "ai 工具", "科技趨勢", "軟體", "應用", "技術", "分享", "影片", "文章",
        "自動化", "ai自動化", "ai 自動化", "生產力", "生產力工具", "高效工作", "效率提升"
    }
    
    # 優先篩選出至少有 3 篇文章以上的標準標籤（提供豐富的跨文獻彙整）
    eligible_tags = {}
    for tag, arts in standard_tag_map.items():
        if tag.lower() in BROAD_TAGS_BLACKLIST:
            continue
        if tag.strip().lower() in existing_tags:
            continue
        if len(arts) >= 3:
            eligible_tags[tag] = arts
            
    # 如果符合 3 篇以上的主題太少，則降級為大於等於 2 篇的主題
    if len(eligible_tags) < args.count:
        eligible_tags = {}
        for tag, arts in standard_tag_map.items():
            if tag.lower() in BROAD_TAGS_BLACKLIST:
                continue
            if tag.strip().lower() in existing_tags:
                continue
            if len(arts) >= 2:
                eligible_tags[tag] = arts
                
    themes_to_process = []
    
    if len(eligible_tags) >= args.count:
        print(f"[INFO] 成功在 Notion 標籤中找到 {len(eligible_tags)} 個可用主題，將使用標籤分組模式。")
        # 4. 優先抽取包含了「深受啟發」文章的主題，其餘主題隨機補充
        inspired_tags = []
        other_tags = []
        for tag, arts in eligible_tags.items():
            if any(art.get("is_inspired", False) for art in arts):
                inspired_tags.append(tag)
            else:
                other_tags.append(tag)
                
        random.shuffle(inspired_tags)
        random.shuffle(other_tags)
        
        selected_tags = []
        selected_tags.extend(inspired_tags[:args.count])
        remaining_need = args.count - len(selected_tags)
        if remaining_need > 0:
            selected_tags.extend(other_tags[:remaining_need])
            
        print(f"[INFO] 優先挑選有「深受啟發」文章的主題後，選定的 {len(selected_tags)} 個標準主題為: {', '.join(selected_tags)}")
        
        for tag in selected_tags:
            articles = eligible_tags[tag]
            # V3.8 排序：依 final_score（TRS*0.7 + QS*0.3）* freshness_score 降序排序
            # 同時計算該主題下各文章的 TRS（關鍵字命中率作為啟發式 TRS 代理）
            tag_keywords = re.findall(r'[\u4e00-\u9fa5]{2,4}|[a-zA-Z]{3,}', tag)
            for art in articles:
                # 關鍵字命中率作為 TRS 啟發式代理
                title_hits = sum(1 for kw in tag_keywords if kw.lower() in art.get("title", "").lower())
                summary_hits = sum(1 for kw in tag_keywords if kw.lower() in art.get("summary", "").lower())
                trs = min(1.0, (title_hits * 0.4 + summary_hits * 0.15) / max(len(tag_keywords), 1))
                art["trs"] = round(trs, 3)
                qs_norm = art.get("rag_score", 5.0) / 10.0
                art["final_score"] = round((0.7 * trs + 0.3 * qs_norm) * art.get("freshness_score", 0.85), 4)

            articles.sort(key=lambda x: (x.get("final_score", 0), x.get("created_time", "") or ""), reverse=True)
            core_candidates_raw = articles[:3]
            # V3.5 Explainability：記錄被淘汰的文章（第 4 篇以後）用於可解釋性報告
            rejected_raw = []
            for a in articles[3:6]:  # 只記錄前 3 個被淘汰的
                a_copy = dict(a)
                if a_copy.get("trs", 0.5) < 0.3:
                    a_copy["reject_reason"] = f"LOW_RELEVANCE (TRS < 0.30)"
                elif a_copy.get("freshness_score", 0.85) < 0.3:
                    a_copy["reject_reason"] = "EXPIRED (freshness < 0.30)"
                else:
                    a_copy["reject_reason"] = "LOW_SCORE"
                rejected_raw.append(a_copy)

            core_ids = {c["id"] for c in core_candidates_raw}
            other_articles_raw = [a for a in articles if a["id"] not in core_ids]
            themes_to_process.append({
                "tag": tag,
                "core_candidates": core_candidates_raw,
                "other_articles": other_articles_raw,
                "rejected_articles": rejected_raw
            })
    else:
        print(f"\n[INFO] 基於 Notion 標籤的主題篩選僅獲得 {len(eligible_tags)} 個主題，不足要求的 {args.count} 個。")
        print("[INFO] 自動啟動「跨文章語意聚類 fallback 機制」進行精準融合...")
        
        clustered_themes = semantic_clustering(articles_brief, existing_tags, args.count)
        if not clustered_themes:
            print("[ERROR] 語意聚類未回傳任何主題，且標籤分組主題不足，無法進行彙整。")
            sys.exit(1)
            
        selected_themes = clustered_themes[:args.count]
        print(f"[INFO] 語意聚類已選定 {len(selected_themes)} 個專題主題：")
        for idx, t in enumerate(selected_themes, 1):
            print(f"  {idx}. {t.get('theme')} (包含核心文獻 {len(t.get('core_article_ids', []))} 篇，輔助 {len(t.get('helper_article_ids', []))} 篇)")
        # 建立一個 list 把所有文章收集起來，方便在匹配不到時進行物理檢索
        all_articles_list = list(articles_by_id.values())
        
        for t in selected_themes:
            core_candidates_raw = [articles_by_id[cid.replace("-", "").lower()] for cid in t["core_article_ids"] if cid.replace("-", "").lower() in articles_by_id]
            other_articles_raw = [articles_by_id[hid.replace("-", "").lower()] for hid in t.get("helper_article_ids", []) if hid.replace("-", "").lower() in articles_by_id]
            
            # --- 物理防禦容錯 (保證 100% 有真實文獻注入) ---
            if not core_candidates_raw:
                print(f"    [WARN] 語意聚類主題 '{t.get('theme')}' 的核心文獻匹配為空，將啟用物理防禦召回...")
                core_candidates_raw = fallback_retrieve_articles(t.get("theme", ""), all_articles_list, count=2)
                print(f"    [OK] 物理防禦成功召回 {len(core_candidates_raw)} 篇真實核心文獻。")
                
            # 如果輔助文獻也為空，召回其他跟主題最相關的文章
            if not other_articles_raw and len(all_articles_list) > len(core_candidates_raw):
                core_ids = {c["id"] for c in core_candidates_raw}
                eligible_for_helper = [a for a in all_articles_list if a["id"] not in core_ids]
                other_articles_raw = fallback_retrieve_articles(t.get("theme", ""), eligible_for_helper, count=1)
                
            themes_to_process.append({
                "tag": t["theme"],
                "core_candidates": core_candidates_raw,
                "other_articles": other_articles_raw,
                "rejected_articles": []  # 語意聚類模式下無明確淘汰記錄
            })
            
    # 5. 針對每個主題進行彙整並寫入新資料庫
    task_db_id = os.getenv("NOTION_TASK_DATABASE_ID")
    for item in themes_to_process:
        tag = item["tag"]
        core_candidates = item["core_candidates"]
        other_articles = item["other_articles"]
        
        rejected_articles = item.get("rejected_articles", [])

        # B. 混合式 RAG：讀取核心文獻的 Notion 頁面完整文字內容
        core_articles_content = []
        for idx, core in enumerate(core_candidates, 1):
            freshness_display = f"{core.get('freshness_score', 0.85):.2f}"
            final_display = f"{core.get('final_score', core.get('rag_score', 5.0)):.3f}"
            print(f"    [+] 正在讀取核心文獻 [{idx}/{len(core_candidates)}] 全文: {core['title']}")
            print(f"        (QS: {core.get('rag_score', 5.0):.1f} | TRS: {core.get('trs', 0.5):.2f} | freshness: {freshness_display} | final: {final_display})")
            full_text = get_page_content(notion, core["id"])
            year = core["created_time"][:4] if core["created_time"] else "未知"
            core_articles_content.append({
                "title": core["title"],
                "url": core["url"],
                "year": year,
                "content": full_text
            })
            time.sleep(0.5) # 遵守 Notion API 頻率限制

        # V3.5 Fact Layer：對每篇核心文獻提取 Claim Pool
        all_claim_pool = []
        print(f"    [+] V3.5 Fact Layer：正在提取核心文獻的 Claim Pool...")
        for idx, (core, content_info) in enumerate(zip(core_candidates, core_articles_content), 1):
            claims = extract_claim_pool(
                notion_page_id=core["id"],
                page_title=core["title"],
                full_text=content_info["content"],
                source_url=core.get("url", "")
            )
            print(f"        文獻 [{idx}] 提取到 {len(claims)} 個 Claim")
            all_claim_pool.extend(claims)
            time.sleep(0.5)

        # V3.5 Explainability Layer：生成可解釋性報告
        print(f"    [+] V3.5 Explainability Layer：正在生成可解釋性報告...")
        explainability_report_md = generate_explainability_report(
            selected_articles=core_candidates,
            rejected_articles=rejected_articles
        )

        # C. 將其他文章重排為時間升序（最早在前，最新在後）以利 LLM 呈現技術/觀點演進
        other_articles.sort(key=lambda x: x.get("created_time", ""))
        
        # 呼叫惡魔代言人進行反向論點與風險分析
        print(f"    [+] 正在呼叫 {engine_name.upper()} 扮演「惡魔代言人」進行批判思考與反向觀點分析...")
        devils_advocate_critique = ask_devils_advocate(tag, core_articles_content, other_articles)
        
        # D. 呼叫 LLM 進行混合 RAG 知識合成（注入 Claim Pool + Context Graph 要求）
        print(f"    [+] 正在呼叫 {engine_name.upper()} 進行 V3.5 深度知識融會貫通 (融合正反思辨 + Synthesis/Hypothesis + Context Graph)...")
        markdown_article = ask_llm(tag, other_articles, core_articles_content, devils_advocate_critique, claim_pool=all_claim_pool)
        
        if not markdown_article:
            print("    [ERROR] 知識彙整失敗，跳過此主題。")
            continue
            
        # 建立與 ask_llm 相同結構的 citations 清單，用於 Python 二次校驗過濾
        all_citations = []
        for idx, art in enumerate(core_articles_content, 1):
            all_citations.append({
                "num": idx,
                "title": art["title"],
                "url": art["url"]
            })
        start_num = len(core_articles_content) + 1
        for idx, art in enumerate(other_articles, start_num):
            all_citations.append({
                "num": idx,
                "title": art["title"],
                "url": art["url"]
            })
            
        # 使用 Python 二次過濾與防護（Guardrail），剔除 LLM 憑空捏造的幻覺參考文獻，並提取外部文獻
        print("    [+] 正在進行引用關係與幻覺文獻校驗 (Guardrail)...")
        markdown_article, external_citations = filter_and_validate_markdown_citations(markdown_article, all_citations)
        
        # 用 Python 強制附加 100% 正確的「網路文章影片筆記資料庫」真實參考文獻與外部文獻列表
        ref_section = "\n\n#### 參考文獻\n"
        for cit in all_citations:
            url_text = f"({cit['url']})" if cit.get('url') else "(來源資料庫無連結)"
            ref_section += f"- `[資料庫文獻 {cit['num']}]` [{cit['title']}]{url_text}\n"
        for ec in external_citations:
            url_text = f"({ec['url']})" if ec.get('url') else "(外部連結無效)"
            ref_section += f"- `[外部文獻 {ec['num']}]` [{ec['title']}]{url_text}\n"
        markdown_article += ref_section

        # V3.5 Decision Memory：生成決策記憶區塊
        print(f"    [+] V3.5 Decision Memory：正在生成決策記憶...")
        decision_memory_data = generate_decision_memory(tag, all_claim_pool)
        dm_json = json.dumps(decision_memory_data, ensure_ascii=False, indent=2)
        decision_memory_md = f"\n\n## 🧠 決策記憶與失效提醒 (Decision Memory)\n\n> **決策記憶 (Decision Memory)**：以下結構化記錄了本專題的核心決策與其背景假設。當觸發器條件滿足時，請重新評估本決策。\n\n```json\n{dm_json}\n```\n"
        markdown_article += decision_memory_md

        # 將 Explainability Report 插入文章開頭（在主標題之後）
        lines = markdown_article.split('\n')
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('##') or line.strip().startswith('# '):
                insert_pos = i + 1
                break
        lines.insert(insert_pos, '\n' + explainability_report_md)
        markdown_article = '\n'.join(lines)

        # E. 將 Markdown 轉成 Notion 區塊
        blocks = markdown_to_notion_blocks(markdown_article)
        
        # 呼叫 LLM 專門為該文章提煉符合【一句話摘要】與【3個核心知識點】格式的摘要文字與 AI 標籤
        print("    [+] 正在為專題文章提煉【一句話摘要】、【3個核心知識點】與【AI標籤】...")
        summary_text = generate_core_knowledge_points(markdown_article)
        summary_part, points_part, tag_options = extract_summary_points_tags(summary_text, tag)
        
        # 解析 LLM 回傳的文章主標題，作為 Notion 的頁面 Title
        page_title = ""
        for line in markdown_article.split('\n'):
            line = line.strip()
            if line.startswith('# '):
                page_title = line[2:].strip()
                break
            elif line.startswith('## '):
                page_title = line[3:].strip()
                break
                
        # 清理標題的 markdown 標籤（如星號、超連結等）
        if page_title:
            page_title = re.sub(r'\*\*|__', '', page_title)
            page_title = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', page_title)
        else:
            page_title = f"【知識專題】{tag} 的核心精髓與實踐指南"
 
        # F. 分頁寫入 Notion 資料庫
        print(f"    [+] 正在將專題文章『{page_title}』寫入目標資料庫...")
        try:
            page_id = write_notion_page_with_blocks(
                notion=notion,
                database_id=args.dest_db,
                page_title=page_title,
                summary_part=summary_part,
                points_part=points_part,
                tag_options=tag_options,
                blocks=blocks
            )
            print(f"    [OK] 成功建立並完整寫入專題頁面！頁面 ID: {page_id}")
            
            # 行動閉環：解析並建立 Task 寫入 Task DB
            action_items = extract_action_items(markdown_article)
            if action_items:
                print(f"    [+] 解析出 {len(action_items)} 個行動項目，開始進行任務寫入閉環...")
                if task_db_id:
                    success_count = 0
                    for item in action_items:
                        if create_task_in_db(notion, task_db_id, item, page_id):
                            success_count += 1
                    print(f"    [OK] 成功將 {success_count}/{len(action_items)} 個行動任務寫入 Notion 任務資料庫！")
                else:
                    print("    [WARN] 未設定 NOTION_TASK_DATABASE_ID 環境變數，跳過任務寫入。解析到的行動項目為：")
                    for item in action_items:
                        print(f"      - {item}")
            else:
                print("    [INFO] 未在專題文章中解析出具體的下一步行動項目。")
                
        except Exception as e:
            print(f"    [ERROR] 寫入目標資料庫失敗: {e}")
            
    print("\n[INFO] 所有主題彙整與生產級寫入工作圓滿完成！")

if __name__ == "__main__":
    main()
