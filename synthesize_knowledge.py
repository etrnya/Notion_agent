import os
import sys
import re
import random
import json
import time
import argparse
import io
from datetime import datetime, timedelta
from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIResponseError

# 強制將 stdout 與 stderr 設為 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

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

def ask_llm(tag, articles, core_articles_content, devils_advocate_critique=""):
    """混合式 RAG：利用核心文章全文與其他文章摘要，融會貫通合成一篇專題知識文章，支援嚴格引用標註與惡魔代言人思辨"""
    
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
    
    prompt += "=== 參考文獻清單（請嚴格根據以下文獻的編號進行正文段落內標註引用） ===\n"
    for cit in all_citations:
        prompt += f"【文獻 {cit['num']}】標題：{cit['title']}\n"
        prompt += f"發表年份：{cit['year']} | 連結：{cit['url'] if cit['url'] else '無'}\n"
        if cit["type"] == "core":
            prompt += f"核心內文細節：\n{cit['content_preview']}\n"
        else:
            prompt += f"摘要內容：{cit['summary']}\n"
        prompt += "-" * 40 + "\n"
        
    if devils_advocate_critique:
        prompt += "=== 惡魔代言人批判與反向觀點 ===\n"
        prompt += devils_advocate_critique + "\n\n"
        
    prompt += """
請以繁體中文撰寫，並格式化為乾淨的 Markdown 格式，且必須嚴格遵守以下學術與思辨規範：

1. 主標題格式：請根據您彙整後的文章實際核心內容，擬定一個專業、具備吸引力且與內容高度契合的中文標題，格式為：`## [自訂標題]`。例如 `## 打造高效團隊：n8n 流程自動化與專案治理實踐`。
2. 前言：說明這個主題在現代數位/工作場景中的價值與演進脈絡。
3. 核心觀點與概念彙整：
   - 整合文獻的精髓，整理出 2-3 個深入的觀點，並以標題與段落詳細展開。
   - 【硬性要求】：在撰寫的每一個觀點、技術描述或陳述句後面，必須在其段落或句子結尾標註其出處的文獻編號（例如：`...此技術能顯著提升工作效率 [1]。` 或是 `...在 2026 年的應用中更趨於成熟 [3, 5]。`）。
   - 請根據文獻的發表年份（例如：[2025]、[2026]），在撰寫核心觀點時展現出「時間演進」的技術發展脈絡，避免時空錯置。
4. 【硬性要求】反向觀點與不適用情境：
   - 必須包含一個大標題 `#### 反向觀點與不適用情境`。
   - 整合上述提供之惡魔代言人批判，深入探討此主題/技術的侷限性、業界失敗案例，以及在什麼特定情境下絕對不該採用，讓專題文章具備客觀辯證與風險防範價值。
5. 實踐與下一步行動計畫：
   - 必須包含一個大標題 `#### 下一步行動計畫 (Action Items)`。
   - 提供 2-3 個具體、可落地、可執行的下一步行動，並格式化為 Markdown 任務列表。例如：
     - [ ] 行動指引 1 [1]
     - [ ] 行動指引 2 [3]
6. 參考文獻列表：
   - 在文章末尾列出「參考文獻」標題。
   - 【硬性要求】：只列出您在文章中「實際標註引用」過的文獻。如果某篇文獻在正文中沒有被 `[編號]` 引用，則絕對不能出現在參考文獻列表中。
   - 格式必須為：- `[文獻編號] [文章標題](原始連結)`。例如：`- [1] [AI開發新趨勢](https://example.com)`。如果原始連結為「無」，請寫成 `- [1] [AI開發新趨勢](無連結)`。
   - 【警告】：嚴禁憑空捏造任何不在上述清單中的文獻或網址連結！

注意：請直接回傳 Markdown 文本，不要用 ```markdown 標籤包覆，也不要有任何無關的開頭或結尾問候。
"""
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if engine_name == "deepseek":
                response = openai_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "You are a helpful knowledge curator. You output strict Markdown in Traditional Chinese."},
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
                        {"role": "system", "content": "You are a helpful knowledge curator. You output strict Markdown in Traditional Chinese."},
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
    """在 Notion 任務資料庫中建立一筆 Task 紀錄，並關聯至來源專題頁面"""
    try:
        # 1. 撈取資料庫屬性以對齊欄位
        db_info = notion.databases.retrieve(task_db_id)
        props = db_info.get("properties", {})
        
        # 識別標題屬性名稱 (通常是 'Name' 或 '任務名稱' 或 'Title')
        title_field = None
        for name, prop in props.items():
            if prop.get("type") == "title":
                title_field = name
                break
                
        # 識別 Relation 屬性名稱 (通常是 '來源專題' 或 'Source' 等)
        relation_field = None
        for name, prop in props.items():
            if prop.get("type") == "relation":
                relation_field = name
                break
                
        # 識別 Status 或 Select 屬性 (用於設定待辦狀態)
        status_field = None
        status_value = None
        for name, prop in props.items():
            if prop.get("type") == "status":
                status_field = name
                status_value = {"name": "Not started"}
                break
            elif prop.get("type") == "select" and name in ["狀態", "Status", "執行狀態"]:
                status_field = name
                status_value = {"name": "待辦"}
                break
                
        properties = {}
        if title_field:
            properties[title_field] = {
                "title": [
                    {
                        "text": {
                            "content": task_name
                        }
                    }
                ]
            }
            
        if relation_field and source_page_id:
            properties[relation_field] = {
                "relation": [
                    {
                        "id": source_page_id
                    }
                ]
            }
            
        if status_field and status_value:
            if props[status_field].get("type") == "status":
                properties[status_field] = {"status": status_value}
            else:
                properties[status_field] = {"select": status_value}
                
        # 自動計算截止日期：1 週後
        # 尋找截止日期欄位
        date_field = None
        for name, prop in props.items():
            if prop.get("type") == "date" and name in ["截止日期", "Due Date", "Deadline"]:
                date_field = name
                break
        if date_field:
            due_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            properties[date_field] = {
                "date": {
                    "start": due_date
                }
            }
            
        notion.pages.create(
            parent={"database_id": task_db_id},
            properties=properties
        )
        return True
    except Exception as e:
        print(f"      [WARN] 寫入任務資料庫失敗: {e}")
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
    """將 Markdown 文字解析並轉換為 Notion 的區塊 (Blocks) 格式"""
    blocks = []
    lines = markdown_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 解析標題 (支援 # 到 ######，自動降級大於 3 級的標題，並剔除字首的 # 號)
        header_match = re.match(r'^(#{1,6})\s+(.*)$', line)
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
        # 解析清單
        elif line.startswith('- ') or line.startswith('* '):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": parse_rich_text(line[2:])
                }
            })
        elif re.match(r'^\d+\.\s', line):
            content = re.sub(r'^\d+\.\s', '', line)
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
    """使用 Python 對 LLM 回傳的 Markdown 進行引用的二次校驗，防止幻覺"""
    # 建立一個真實的 url -> title 對照表，以及編號對照表
    valid_urls = {cit["url"] for cit in all_citations if cit["url"]}
    valid_titles = {cit["title"] for cit in all_citations}
    max_valid_num = len(all_citations)
    
    # 1. 修正正文中的超標引用編號（例如只給了5篇，LLM 卻寫了 [7]）
    def replace_citation(match):
        cit_str = match.group(0)
        nums = [int(n) for n in re.findall(r'\d+', cit_str)]
        valid_nums = [n for n in nums if 1 <= n <= max_valid_num]
        if not valid_nums:
            return ""
        return "[" + ", ".join(map(str, valid_nums)) + "]"
        
    fixed_text = re.sub(r'\[\d+(?:\s*,\s*\d+)*\]', replace_citation, markdown_text)
    
    # 2. 修正文章最後的「參考文獻」列表，剔除幻覺文獻
    lines = fixed_text.split('\n')
    cleaned_lines = []
    in_references_section = False
    
    for line in lines:
        if "參考文獻" in line or "Reference" in line:
            in_references_section = True
            cleaned_lines.append(line)
            continue
            
        if in_references_section:
            link_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', line)
            if link_match:
                title = link_match.group(1).strip()
                url = link_match.group(2).strip()
                
                # 判斷這篇文獻是否在我們的真實文獻列表中，或者是標題符合
                is_valid = (url in valid_urls) or any(t in title for t in valid_titles)
                if not is_valid:
                    print(f"      [GUARDRAIL] 剔除幻覺參考文獻: {title} (URL: {url})")
                    continue
            
        cleaned_lines.append(line)
        
    return '\n'.join(cleaned_lines)

def extract_summary_and_tags(markdown_text, tag):
    """從 Markdown 內容中提取第一段作為 AI摘要，並以主題作為 AI 標籤"""
    lines = markdown_text.split('\n')
    summary = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('#') or line.startswith('-') or line.startswith('*') or re.match(r'^\d+\.', line):
            continue
        # 排除字數過短的行
        if len(line) < 15 or line.replace("：", "").replace(":", "").strip() in ["前言", "引言", "摘要", "一、前言", "1. 前言"]:
            continue
        summary = line
        break
        
    if len(summary) > 200:
        summary = summary[:197] + "..."
    if not summary:
        summary = f"關於『{tag}』主題的知識彙整專題文章。"
        
    tags = [{"name": tag}]
    return summary, tags

def generate_core_knowledge_points(markdown_article):
    """根據專題文章內容，呼叫 LLM 生成符合特定格式的 AI 核心知識點"""
    prompt = f"""
    請閱讀以下知識專題文章，並為其提煉出「一句話摘要」與「3個核心知識點」。
    
    文章內容：
    {markdown_article}
    
    【硬性要求】你必須嚴格遵守以下格式回傳（包含【】括號字元，且不要有任何 markdown 代碼塊包覆或多餘問候語，字詞需為繁體中文）：
    【一句話摘要】
    [請在此處用一兩句話精煉概括文章的核心主題與價值]
    【3個核心知識點】
    - 知識點 1: [具體且具含金量的知識點 1]
    - 知識點 2: [具體且具含金量的知識點 2]
    - 知識點 3: [具體且具含金量的知識點 3]
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
    return "【一句話摘要】\n關於此專題的知識彙整文章。\n【3個核心知識點】\n- 知識點 1: 整合了多篇核心文獻的關鍵見解。\n- 知識點 2: 提供具體可操作的實踐建議與行動方案。\n- 知識點 3: 展現出技術或觀點的時間演進脈絡。"

def write_notion_page_with_blocks(notion, database_id, page_title, summary_text, tag_options, blocks):
    """分頁追加寫入：建立頁面並分批寫入 blocks，完全突破 Notion 的 100 筆區塊負載限制"""
    first_chunk_size = 80
    first_chunk = blocks[:first_chunk_size]
    remaining_chunks = [blocks[i:i+80] for i in range(first_chunk_size, len(blocks), 80)]
    
    # 拆分【一句話摘要】與【3個核心知識點】
    summary_part = ""
    points_part = ""
    if "【一句話摘要】" in summary_text and "【3個核心知識點】" in summary_text:
        parts = summary_text.split("【3個核心知識點】")
        summary_part = parts[0].replace("【一句話摘要】", "").strip()
        points_part = parts[1].strip()
    else:
        summary_part = summary_text
        points_part = ""
        
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
    try:
        query_results = notion.data_sources.query(
            data_source_id=args.source_ds,
            filter={
                "property": "AI 已處理",
                "checkbox": {
                    "equals": True
                }
            },
            page_size=100
        )
    except Exception as e:
        print(f"[ERROR] 撈取來源資料庫失敗: {e}")
        sys.exit(1)
        
    pages = query_results.get("results", [])
    if not pages:
        print("[WARN] 沒有找到任何 AI 已處理的文章，請先執行 batch_processor.py 進行提煉。")
        sys.exit(0)
        
    print(f"[INFO] 成功讀取到 {len(pages)} 筆已處理的文章。")
    
    # 2. 建立標籤對應表 (tag -> list of pages)
    tag_map = {}
    all_raw_tags = set()
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
        
        # 多維度加權排序 RAG Score 公式
        rag_score = 0.4 * credibility + 0.3 * actionability + 0.3 * inspiration
        
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
                    "rag_score": rag_score
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
            
    # 撈取目標資料庫中已存在的專題文章的標籤以進行精準去重
    print("\n[INFO] 正在撈取目標資料庫中已存在的專題文章以進行去重...")
    existing_tags = set()
    try:
        search_results = notion.search(
            filter={"property": "object", "value": "page"},
            page_size=100
        )
        target_db_clean = args.dest_db.replace("-", "").lower()
        for page in search_results.get("results", []):
            p_id = page.get("parent", {}).get("database_id", "").replace("-", "").lower()
            if p_id == target_db_clean:
                props = page.get("properties", {})
                
                # 智慧撈取專題文章已有的「AI 標籤」屬性
                tags_prop = props.get("AI 標籤", {}).get("multi_select", [])
                for t in tags_prop:
                    tag_name = t.get("name")
                    if tag_name:
                        existing_tags.add(tag_name.strip().lower())
        print(f"[INFO] 目標資料庫中已存在 {len(existing_tags)} 個主題的專題文章，將排除以防重複。")
    except Exception as e:
        print(f"[WARN] 撈取目標資料庫已存在頁面失敗: {e}，將跳過增量去重防護。")

    # 篩選出至少有 2 篇文章以上的標準標籤，排除太過寬泛的大型標籤
    BROAD_TAGS_BLACKLIST = {
        "ai工具", "ai應用", "ai", "工具", "科技", "資訊", "未分類", "tag", "無標籤",
        "ai 應用", "ai 工具", "科技趨勢", "軟體", "應用", "技術", "分享", "影片", "文章",
        "自動化", "ai自動化", "ai 自動化", "生產力", "生產力工具", "高效工作", "效率提升"
    }
    
    eligible_tags = {}
    for tag, arts in standard_tag_map.items():
        if tag.lower() in BROAD_TAGS_BLACKLIST:
            continue
        # 精準增量去重：如果已有該主題的彙整文章則跳過
        if tag.strip().lower() in existing_tags:
            continue
        if len(arts) >= 2:
            eligible_tags[tag] = arts
            
    # 如果 eligible_tags 太少，則降級為大於等於 1 篇的標籤，且同樣過濾黑名單與重複
    if len(eligible_tags) < 3:
        eligible_tags = {}
        for tag, arts in standard_tag_map.items():
            if tag.lower() in BROAD_TAGS_BLACKLIST:
                continue
            if tag.strip().lower() in existing_tags:
                continue
            if len(arts) >= 1:
                eligible_tags[tag] = arts
        
    if not eligible_tags:
        print("[ERROR] 沒有找到足夠的文章與標籤來進行彙整。")
        sys.exit(1)
        
    print(f"[INFO] 可用於彙整的主題標籤數量: {len(eligible_tags)} 個。")
    
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
    
    # 5. 針對每個主題進行彙整並寫入新資料庫
    task_db_id = os.getenv("NOTION_TASK_DATABASE_ID")
    for tag in selected_tags:
        articles = eligible_tags[tag]
        print(f"\n[+] 正在處理主題『{tag}』(包含 {len(articles)} 篇參考文獻)...")
        
        # A. 排序：依據加權 RAG 分數 (rag_score) 降序排序，同分時依建立時間降序排序，選出前 3 篇作為核心文獻
        articles.sort(key=lambda x: (x.get("rag_score", 5.0), x.get("created_time", "") or ""), reverse=True)
        core_candidates = articles[:3]
        core_ids = {c["id"] for c in core_candidates}
        
        # 排除已選為核心的文獻，剩下的是其他非核心文獻，避免重複傳遞與重複引用
        other_articles = [a for a in articles if a["id"] not in core_ids]
        
        # B. 混合式 RAG：讀取核心文獻的 Notion 頁面完整文字內容
        core_articles_content = []
        for idx, core in enumerate(core_candidates, 1):
            print(f"    [+] 正在讀取核心文獻 [{idx}/{len(core_candidates)}] 全文: {core['title']} (RAG分數: {core['rag_score']:.1f})...")
            full_text = get_page_content(notion, core["id"])
            year = core["created_time"][:4] if core["created_time"] else "未知"
            core_articles_content.append({
                "title": core["title"],
                "url": core["url"],
                "year": year,
                "content": full_text
            })
            time.sleep(0.5) # 遵守 Notion API 頻率限制
            
        # C. 將其他文章重排為時間升序（最早在前，最新在後）以利 LLM 呈現技術/觀點演進
        other_articles.sort(key=lambda x: x.get("created_time", ""))
        
        # 呼叫惡魔代言人進行反向論點與風險分析
        print(f"    [+] 正在呼叫 {engine_name.upper()} 扮演「惡魔代言人」進行批判思考與反向觀點分析...")
        devils_advocate_critique = ask_devils_advocate(tag, core_articles_content, other_articles)
        
        # D. 呼叫 LLM 進行混合 RAG 知識合成
        print(f"    [+] 正在呼叫 {engine_name.upper()} 進行深度知識融會貫通 (融合正反思辨)...")
        markdown_article = ask_llm(tag, other_articles, core_articles_content, devils_advocate_critique)
        
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
            
        # 使用 Python 二次過濾與防護（Guardrail），剔除 LLM 憑空捏造的幻覺參考文獻
        print("    [+] 正在進行引用關係與幻覺文獻校驗 (Guardrail)...")
        markdown_article = filter_and_validate_markdown_citations(markdown_article, all_citations)
            
        # E. 將 Markdown 轉成 Notion 區塊，並提取標籤
        blocks = markdown_to_notion_blocks(markdown_article)
        _, tag_options = extract_summary_and_tags(markdown_article, tag)
        
        # 呼叫 LLM 專門為該文章提煉符合【一句話摘要】與【3個核心知識點】格式的摘要文字
        print("    [+] 正在為專題文章提煉【一句話摘要】與【3個核心知識點】...")
        summary_text = generate_core_knowledge_points(markdown_article)
        
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
                summary_text=summary_text,
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
