import os
import sys
import time
import json
import argparse
import io
from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIResponseError

# 強制將 stdout 與 stderr 的編碼設為 UTF-8，並對無法解碼的字元使用 replace 替換，防止 Windows CP950 環境下崩潰
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# 載入環境變數
load_dotenv()

# 初始化 LLM 用戶端
openai_client = None
gemini_client = None

def init_llm():
    global openai_client, gemini_client
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
            print(f"[INFO] 已成功初始化 GCP Vertex AI 引擎 (專案 ID: {project_id}，模型: gemini-2.5-flash)")
            return "gemini"
        except Exception as e:
            print(f"[WARN] 嘗試初始化 Vertex AI 失敗: {e}，將回退至其他 API Key 驗證...")

    if deepseek_key:
        from openai import OpenAI
        openai_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
        print("[INFO] 已成功初始化 DeepSeek 引擎 (deepseek-chat)")
        return "deepseek"

    if gemini_key:
        try:
            from google import genai
            # 使用官方全新的 google-genai 軟體包，原生支援 AQ. 開頭的新金鑰，避免 401 路由錯誤
            gemini_client = genai.Client(api_key=gemini_key)
            print("[INFO] 已成功初始化 Gemini 引擎 (google-genai / gemini-2.5-flash)")
            return "gemini"
        except ImportError:
            print("[WARN] 未安裝 google-genai 套件，將嘗試使用 OpenAI 引擎")
    
    if openai_key:
        from openai import OpenAI
        openai_client = OpenAI(api_key=openai_key)
        print("[INFO] 已成功初始化 OpenAI 引擎 (gpt-4o-mini)")
        return "openai"
    
    print("[ERROR] 未找到 gcp-key.json，且未在 .env 中設定 DEEPSEEK_API_KEY, OPENAI_API_KEY 或 GEMINI_API_KEY")
    print("批次處理器需要至少一個 LLM API 金鑰來進行知識提煉。")
    sys.exit(1)

def get_page_title(page):
    """提取 Notion 頁面的標題"""
    properties = page.get("properties", {})
    for name, prop in properties.items():
        if prop.get("type") == "title":
            title_objs = prop.get("title", [])
            return "".join([t.get("plain_text", "") for t in title_objs])
    return "無標題"

def get_page_url_property(page):
    """提取 Notion 頁面的 URL 屬性（若有）"""
    properties = page.get("properties", {})
    # 尋找類型為 url 的屬性
    for name, prop in properties.items():
        if prop.get("type") == "url":
            return prop.get("url") or ""
    return ""

def get_page_content(notion, page_id):
    """讀取 Notion 頁面內部的區塊文字內容"""
    try:
        blocks = notion.blocks.children.list(block_id=page_id)
        text_parts = []
        for block in blocks.get("results", []):
            block_type = block.get("type")
            # 僅收集文本類型的區塊
            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", 
                            "bulleted_list_item", "numbered_list_item", "to_do", "toggle"]:
                rich_texts = block.get(block_type, {}).get("rich_text", [])
                for rt in rich_texts:
                    text_parts.append(rt.get("plain_text", ""))
        return "\n".join(text_parts)
    except Exception as e:
        print(f"  [WARN] 讀取頁面內容失敗 (ID: {page_id}): {e}")
        return ""

def ask_llm(engine, title, content, url=""):
    """調用 LLM 進行摘要與標籤生成，強制回傳結構化 JSON，支援 429 自動重試"""
    prompt = f"""
    請閱讀以下網路文章的標題與內容，為其進行知識提煉：
    - 標題：{title}
    - 網址：{url if url else '無'}
    - 內容：
    {content[:6000]} # 限制長度避免 Context 溢出
    
    請以繁體中文回傳一個 JSON 物件，格式如下：
    {{
      "summary": "【一句話摘要】\\n【3個核心知識點】\\n- 知識點 1...\\n- 知識點 2...\\n- 知識點 3...",
      "tags": ["標籤1", "標籤2", "標籤3"],
      "credibility": 8,
      "actionability": 7
    }}
    
    規則：
    1. tags 陣列最多 3 個標籤，每個標籤長度不超過 15 個字，不可包含逗號。
    2. summary 必須精簡且具實用價值，直接點出文章核心。
    3. credibility (可信度) 代表該文章的客觀真實與學術可靠程度 (整數 1 至 10 分)。例如：官方文檔、知名研究或代碼實測為 8-10 分；論壇貼文或主觀雞湯文為 1-4 分。
    4. actionability (可執行性) 代表該文章是否提供清晰、可落地的具體步驟、代碼或流程指引 (整數 1 至 10 分)。有具體實踐指引者為 7-10 分；純概念探討或觀點性文章為 1-4 分。
    """
    
    max_retries = 5
    
    for attempt in range(max_retries):
        if engine == "gemini":
            try:
                response = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                return json.loads(response.text)
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "Quota exceeded" in err_msg or "limit" in err_msg.lower():
                    # 依據錯誤指示，通常需要等待 30 秒以上
                    sleep_sec = 35 if attempt == 0 else 60
                    print(f"  [WARN] 達到 Gemini 頻率限制 (429)。正在等待 {sleep_sec} 秒後重試 (第 {attempt+1}/{max_retries} 次)...")
                    time.sleep(sleep_sec)
                    continue
                else:
                    print(f"  [WARN] Gemini API 呼叫失敗: {e}")
                    return None
        elif engine == "deepseek":
            try:
                response = openai_client.chat.completions.create(
                    model="deepseek-chat",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You are a helpful knowledge curation assistant. You output strict JSON in Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "Rate limit" in err_msg or "limit" in err_msg.lower():
                    sleep_sec = 10 * (attempt + 1)
                    print(f"  [WARN] 達到 DeepSeek 頻率限制 (429)。正在等待 {sleep_sec} 秒後重試 (第 {attempt+1}/{max_retries} 次)...")
                    time.sleep(sleep_sec)
                    continue
                else:
                    print(f"  [WARN] DeepSeek API 呼叫失敗: {e}")
                    return None
        else:
            try:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You are a helpful knowledge curation assistant. You output strict JSON in Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "Rate limit" in err_msg:
                    sleep_sec = 10 * (attempt + 1)
                    print(f"  [WARN] 達到 OpenAI 頻率限制 (429)。正在等待 {sleep_sec} 秒後重試 (第 {attempt+1}/{max_retries} 次)...")
                    time.sleep(sleep_sec)
                    continue
                else:
                    print(f"  [WARN] OpenAI API 呼叫失敗: {e}")
                    return None
    print("  [ERROR] 已達最大重試次數，LLM 呼叫宣告失敗。")
    return None

def update_notion_properties(notion, page_id, summary, tags, credibility=None, actionability=None):
    """更新 Notion 頁面的 AI 摘要、AI 標籤與 AI 已處理狀態，支援屬性名稱自動對齊與優雅降級"""
    # 限制並清理標籤，確保符合 Notion 限制
    sanitized_tags = []
    for tag in tags:
        clean = tag.replace(",", "").strip()
        if clean and len(clean) < 100:
            sanitized_tags.append({"name": clean})
            
    try:
        # 1. 獲取頁面詳細屬性，以自動對齊屬性欄位名稱
        page_detail = notion.pages.retrieve(page_id=page_id)
        props = page_detail.get("properties", {})
        
        # 2. 確定可用的屬性名稱
        processed_field = "AI 已處理" if "AI 已處理" in props else None
        summary_field = "AI 摘要" if "AI 摘要" in props else None
        credibility_field = "可信度" if "可信度" in props else None
        actionability_field = "可執行性" if "可執行性" in props else None
        
        # 標籤欄位對齊優先序：'AI 標籤' -> 'Tag' -> 空字串 ''
        tag_field = None
        if "AI 標籤" in props:
            tag_field = "AI 標籤"
        elif "Tag" in props:
            tag_field = "Tag"
        elif "" in props:
            tag_field = ""
            
        update_payload = {}
        if processed_field:
            update_payload[processed_field] = {"checkbox": True}
            
        if summary_field:
            update_payload[summary_field] = {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": summary
                        }
                    }
                ]
            }
            
        if tag_field and sanitized_tags:
            update_payload[tag_field] = {
                "multi_select": sanitized_tags
            }
            
        if credibility_field and credibility is not None:
            update_payload[credibility_field] = {"number": credibility}
            
        if actionability_field and actionability is not None:
            update_payload[actionability_field] = {"number": actionability}
            
        if not update_payload:
            print("  [WARN] 找不到任何可供寫入的屬性欄位 ('AI 已處理', 'AI 摘要', 'AI 標籤', '可信度', '可執行性')。")
            return False
            
        notion.pages.update(
            page_id=page_id,
            properties=update_payload
        )
        return True
    except APIResponseError as e:
        err_msg = str(e)
        print(f"  [ERROR] Notion 更新失敗: {err_msg}")
        if "Could not find property" in err_msg:
            print("\n[INFO] 提示：找不到預期的屬性欄位。請先確認您已在 Notion 資料庫中新增了以下三個欄位：")
            print("  1. 'AI 已處理' (屬性型態: Checkbox)")
            print("  2. 'AI 摘要' (屬性型態: Text)")
            print("  3. 'AI 標籤' (屬性型態: Multi-select)")
        return False

def main():
    parser = argparse.ArgumentParser(description="Notion 網路文章筆記資料庫批次 AI 提煉處理器")
    parser.add_argument("--limit", type=int, default=5, help="本次要處理的文章筆數上限 (預設為 5)")
    parser.add_argument("--dry-run", action="store_true", help="只撈取資料預覽，不呼叫 LLM 亦不寫回 Notion")
    parser.add_argument("--yes", action="store_true", help="跳過二次確認直接運行")
    args = parser.parse_args()

    # 1. 驗證基礎環境
    notion_token = os.getenv("NOTION_API_KEY")
    database_id = os.getenv("NOTION_DATABASE_ID")

    if not notion_token:
        print("[ERROR] 未在 .env 中設定 NOTION_API_KEY")
        sys.exit(1)
    if not database_id:
        print("[ERROR] 未在 .env 中設定 NOTION_DATABASE_ID")
        sys.exit(1)

    print("=" * 60)
    print("[INFO] Notion 網路文章批次處理器啟動...")
    print(f"工作資料庫 ID: {database_id}")
    print(f"本次處理上限: {args.limit} 筆")
    if args.dry_run:
        print("模式: 乾跑預覽模式 (Dry Run) - 不會改動任何資料")
    print("=" * 60)

    # 2. 初始化 API 用戶端
    notion = Client(auth=notion_token)
    engine = None if args.dry_run else init_llm()

    # 3. 查詢與處理未處理的資料 (支援自動分頁/分批，直到達到 limit 上限)
    try:
        # 獲取資料庫元數據並解析 Data Source ID (相容 Notion API 2025-09-03 版本)
        db_info = notion.databases.retrieve(database_id)
        data_sources = db_info.get("data_sources", [])
        if not data_sources:
            print("[ERROR] 無法在該資料庫中找到資料來源 (Data Source)。")
            sys.exit(1)
        data_source_id = data_sources[0]["id"]
    except APIResponseError as e:
        print(f"[ERROR] 無法讀取 Notion 資料庫: {e}")
        print("請確認：")
        print("  1. 資料庫 ID 是否正確。")
        print("  2. 您的 Notion Integration 已經對該資料庫點選了 'Add Connection' 授權。")
        print("  3. 資料庫中是否已建立了名為 'AI 已處理' 的 Checkbox 欄位。")
        sys.exit(1)

    max_to_process = args.limit
    total_processed = 0

    # A. 乾跑預覽模式：只撈取第一頁 (最多 100 筆) 並列印預覽，然後退出
    if args.dry_run:
        print("[INFO] 正在乾跑撈取未處理的文章列表...")
        try:
            query_results = notion.data_sources.query(
                data_source_id=data_source_id,
                filter={
                    "property": "AI 已處理",
                    "checkbox": {
                        "equals": False
                    }
                },
                page_size=min(max_to_process, 100)
            )
            pages = query_results.get("results", [])
            if not pages:
                print("[INFO] 所有網路文章都已經處理完成，沒有未處理的項目。")
                sys.exit(0)
            print(f"[INFO] 找到 {len(pages)} 筆未處理的文章：")
            for idx, page in enumerate(pages, 1):
                title = get_page_title(page)
                print(f"  {idx}. {title} (ID: {page['id']})")
            print("\n[INFO] 預覽完成，乾跑模式結束。")
            sys.exit(0)
        except Exception as e:
            print(f"[ERROR] 查詢失敗: {e}")
            sys.exit(1)

    # B. 二次確認
    if not args.yes:
        confirm = input(f"\n[?] 是否要開始對未處理的文章進行 AI 提煉與寫回？(預計處理上限: {max_to_process} 筆) (y/n): ")
        if confirm.lower() != 'y':
            print("[INFO] 操作取消。")
            sys.exit(0)

    # C. 開始批次處理迴圈
    print("\n[INFO] 開始執行提煉處理...")
    
    while total_processed < max_to_process:
        current_page_size = min(100, max_to_process - total_processed)
        if current_page_size <= 0:
            break

        print(f"\n[INFO] 正在撈取下一批未處理文章 (目標: {current_page_size} 筆，目前已處理 {total_processed} 筆)...")
        try:
            query_results = notion.data_sources.query(
                data_source_id=data_source_id,
                filter={
                    "property": "AI 已處理",
                    "checkbox": {
                        "equals": False
                    }
                },
                page_size=current_page_size
            )
        except Exception as e:
            print(f"[ERROR] 讀取 Notion 資料庫失敗: {e}")
            break

        pages = query_results.get("results", [])
        if not pages:
            print("[INFO] 所有未處理文章已全部處理完畢！")
            break

        print(f"[INFO] 成功取得 {len(pages)} 筆文章，開始處理這一批...")

        for idx, page in enumerate(pages, 1):
            page_id = page["id"]
            title = get_page_title(page)
            url = get_page_url_property(page)
            
            display_idx = total_processed + 1
            print(f"\n[+] [{display_idx}/{max_to_process}] 正在處理: {title}")
            
            # 1. 提取頁面內文
            print("  [+] 正在讀取 Notion 內文...")
            content = get_page_content(notion, page_id)
            if not content.strip():
                print("  [WARN] 警告: 頁面內文為空。將僅基於標題與網址進行提煉。")
                content = f"此頁面無內文，請根據標題『{title}』與網址『{url}』提煉相關學科領域的預期知識。"

            # 2. 呼叫 LLM 提煉
            print(f"  [+] 正在呼叫 {engine.upper()} 提煉知識、評分與標籤...")
            result = ask_llm(engine, title, content, url)
            
            if not result or "summary" not in result or "tags" not in result:
                print("  [ERROR] LLM 提煉失敗，跳過此筆。")
                continue
                
            summary = result["summary"]
            tags = result["tags"]
            credibility = result.get("credibility")
            actionability = result.get("actionability")
            
            print("  [+] 提煉結果預覽：")
            print(f"    [標籤] {', '.join(tags)}")
            print(f"    [可信度] {credibility if credibility is not None else '無'} | [可執行性] {actionability if actionability is not None else '無'}")
            print(f"    [摘要] {summary.replace(chr(10), ' ')}")

            # 3. 寫回 Notion
            print("  [+] 正在更新 Notion 屬性並標記為已處理...")
            success = update_notion_properties(notion, page_id, summary, tags, credibility, actionability)
            
            if success:
                print("  [OK] 處理成功！")
                total_processed += 1
            else:
                print("  [ERROR] 更新失敗，跳過。")
                
            # 遵守 Notion 頻率限制 (每秒 3 次)，每次請求間間隔 0.5 秒
            time.sleep(0.5)

    print(f"\n[INFO] 任務結束！本次成功處理 {total_processed} 筆文章。")

if __name__ == "__main__":
    main()
