import os
import sys
import re
import json
import time
import argparse
import urllib.request
import io
from datetime import datetime, timezone
from dotenv import load_dotenv
from notion_client import Client
from notion_client.errors import APIResponseError

# 強制將 stdout 與 stderr 設為 UTF-8，防止 Windows 環境下 Unicode 錯誤
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# 載入環境變數
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
            return "gemini"
        except Exception as e:
            print(f"[WARN] 嘗試初始化 Vertex AI 失敗: {e}，將回退至其他 API Key 驗證...")

    if deepseek_key:
        from openai import OpenAI
        openai_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
        engine_name = "deepseek"
        print("[INFO] 已成功初始化 DeepSeek 引擎 (deepseek-chat)")
        return "deepseek"

    if gemini_key:
        try:
            from google import genai
            gemini_client = genai.Client(api_key=gemini_key)
            engine_name = "gemini"
            print("[INFO] 已成功初始化 Gemini 引擎 (gemini-2.5-flash)")
            return "gemini"
        except ImportError:
            pass
            
    if openai_key:
        from openai import OpenAI
        openai_client = OpenAI(api_key=openai_key)
        engine_name = "openai"
        print("[INFO] 已成功初始化 OpenAI 引擎 (gpt-4o-mini)")
        return "openai"
        
    print("[ERROR] 未找到 gcp-key.json，且未在 .env 中設定 DEEPSEEK_API_KEY, GEMINI_API_KEY 或 OPENAI_API_KEY")
    sys.exit(1)

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
        if name in ["AI摘要", "AI 摘要"] and prop.get("type") == "rich_text":
            rich_texts = prop.get("rich_text", [])
            return "".join([t.get("plain_text", "") for t in rich_texts])
    return ""

def get_expiration_days(freshness_str):
    if not freshness_str:
        return 180 # 預設 C 級 (快速迭代)
    
    clean_str = freshness_str.strip().upper()
    if not clean_str:
        return 180
        
    first_char = clean_str[0]
    if first_char == 'A':
        return 99999 # 長青知識，永不過期
    elif first_char == 'B':
        return 365   # 技術長青，1 年
    elif first_char == 'C':
        return 180   # 快速迭代，半年
    elif first_char == 'D':
        return 90    # 高度時效，3 個月
    return 180

def parse_date(date_str):
    try:
        if 'T' in date_str:
            date_str = date_str.split('T')[0]
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return datetime.now()

def check_url_status(url):
    if not url:
        return "NO_URL"
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        # 設置超時為 5 秒，防止卡死
        with urllib.request.urlopen(req, timeout=5) as response:
            status = response.status
            if status == 200:
                return "OK"
            return f"HTTP_{status}"
    except Exception as e:
        return f"ERROR_{type(e).__name__}"

def evaluate_freshness_with_llm(title, url, summary, url_status, freshness_str):
    """呼叫 LLM 評估該知識在目前 (2026年) 是否已過時淘汰"""
    prompt = f"""
    你是一個專門負責個人知識管理 (PKM) 系統的「知識治理智能體 (Knowledge Governance Agent)」。
    目前正在進行過期知識巡檢，請評估以下這筆知識內容在目前 (當前時間為 2026 年) 是否仍具備參考價值。
    
    - 標題：{title}
    - 網址：{url if url else '無'}
    - AI摘要：{summary}
    - 網址存活探測結果：{url_status}
    - 當前設定新鮮度：{freshness_str}
    
    請幫我做兩件事：
    1. 評估該技術、工具或知識是否已經「過時淘汰」（例如 API 已過期、工具已關閉、或已被更主流技術取代）。
    2. 給出「知識治理決策」，僅從以下三個選項中選擇一個：
       - `KEEP`：知識依然有效，只需更新驗證時間。
       - `UPDATE`：知識核心觀點仍有價值，但因為 API 變更、連結失效、或有新版本發布，需要手動或自動更新。
       - `ARCHIVE`：知識已徹底過時淘汰，或網址失效且無參考價值，需要進行歸檔或刪除。
       
    請以繁體中文回傳一個 JSON 物件，格式如下：
    {{
      "reason": "[請簡短說明評估原因，例如：原文章工具目前已被更好的開源工具取代，且網址已失效]",
      "decision": "KEEP" // 必須為 KEEP, UPDATE 或 ARCHIVE 之一
    }}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if engine_name == "deepseek":
                response = openai_client.chat.completions.create(
                    model="deepseek-chat",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You are a precise knowledge governance agent. You output strict JSON in Traditional Chinese."},
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
                        {"role": "system", "content": "You are a precise knowledge governance agent. You output strict JSON in Traditional Chinese."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"  [WARN] LLM 時效評估呼叫失敗: {e}，將在 3 秒後重試...")
            time.sleep(3)
            
    return {"decision": "KEEP", "reason": "LLM 評估超時，預設保持不變"}

def create_maintenance_task(notion, task_db_id, task_title, source_page_id):
    """在 Task DB 中建立一個知識維護任務，並關聯回原始文章頁面"""
    try:
        db_info = notion.databases.retrieve(task_db_id)
        props = db_info.get("properties", {})
        
        # 識別標題屬性
        title_field = None
        for name, prop in props.items():
            if prop.get("type") == "title":
                title_field = name
                break
                
        # 識別 Relation 屬性 (關聯至原始資料來源)
        relation_field = None
        for name, prop in props.items():
            if prop.get("type") == "relation":
                relation_field = name
                break
                
        # 識別 Status 或 Select
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
                            "content": task_title
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
                
        # 預設 3 天內處理
        date_field = None
        for name, prop in props.items():
            if prop.get("type") == "date" and name in ["截止日期", "Due Date", "Deadline"]:
                date_field = name
                break
        if date_field:
            due_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
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
        print(f"  [WARN] 寫入知識維護任務到 Task DB 失敗: {e}")
        return False

def update_page_freshness_meta(notion, page_id, verification_field=None):
    """更新最後驗證時間為今天"""
    if not verification_field:
        return False
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        notion.pages.update(
            page_id=page_id,
            properties={
                verification_field: {
                    "date": {
                        "start": today_str
                    }
                }
            }
        )
        return True
    except Exception as e:
        print(f"  [WARN] 更新頁面最後驗證時間失敗: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Notion AI 知識新鮮度自動化巡檢與生命週期代謝器")
    parser.add_argument("--yes", action="store_true", help="跳過二次確認直接運行")
    args = parser.parse_args()

    notion_token = os.getenv("NOTION_API_KEY")
    database_id = os.getenv("NOTION_DATABASE_ID")
    task_db_id = os.getenv("NOTION_TASK_DATABASE_ID")

    if not notion_token:
        print("[ERROR] 未在 .env 中設定 NOTION_API_KEY")
        sys.exit(1)
    if not database_id:
        print("[ERROR] 未在 .env 中設定 NOTION_DATABASE_ID")
        sys.exit(1)

    print("=" * 60)
    print("[INFO] Notion 知識新鮮度過期巡檢器啟動...")
    print(f"工作來源資料庫 ID: {database_id}")
    if task_db_id:
        print(f"連動任務管理資料庫 ID: {task_db_id}")
    else:
        print("模式: 獨立評估模式 (未設定任務資料庫，僅列印報告)")
    print("=" * 60)

    notion = Client(auth=notion_token)
    init_llm()

    # 1. 撈取資料庫與 data source id
    try:
        db_info = notion.databases.retrieve(database_id)
        data_sources = db_info.get("data_sources", [])
        if not data_sources:
            print("[ERROR] 無法在該資料庫中找到資料來源 (Data Source)。")
            sys.exit(1)
        data_source_id = data_sources[0]["id"]
    except Exception as e:
        print(f"[ERROR] 無法讀取 Notion 資料庫屬性: {e}")
        sys.exit(1)

    # 2. 撈取已處理的文章進行新鮮度評估
    print("\n[INFO] 正在撈取來源資料庫中已由 AI 處理過的文章...")
    try:
        query_results = notion.data_sources.query(
            data_source_id=data_source_id,
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
        print("[INFO] 沒有找到任何已處理的文章，巡檢結束。")
        sys.exit(0)

    print(f"[INFO] 成功取得 {len(pages)} 筆已處理的文章，開始新鮮度掃描...")

    # 二次確認
    if not args.yes:
        confirm = input(f"\n[?] 是否開始對這 {len(pages)} 筆文章進行過期巡檢？ (y/n): ")
        if confirm.lower() != 'y':
            print("[INFO] 操作取消。")
            sys.exit(0)

    expired_count = 0
    updated_meta_count = 0
    created_tasks_count = 0

    for idx, page in enumerate(pages, 1):
        title = get_page_title(page)
        url = get_page_url_property(page)
        summary = get_page_summary(page)
        created_time_str = page.get("created_time")
        
        props = page.get("properties", {})
        
        # 尋找新鮮度與驗證時間欄位
        freshness_field = "知識新鮮度" if "知識新鮮度" in props else None
        verification_field = "最後驗證時間" if "最後驗證時間" in props else None
        
        freshness_val = ""
        if freshness_field:
            select_obj = props[freshness_field].get("select")
            if select_obj:
                freshness_val = select_obj.get("name") or ""
                
        verification_val = ""
        if verification_field:
            date_obj = props[verification_field].get("date")
            if date_obj:
                verification_val = date_obj.get("start") or ""

        # 判定基準：如果有驗證時間就用驗證時間，否則用建立時間
        base_date_str = verification_val if verification_val else created_time_str
        base_date = parse_date(base_date_str)
        
        # 計算相隔天數
        days_passed = (datetime.now() - base_date).days
        allowed_days = get_expiration_days(freshness_val)
        
        is_expired = days_passed > allowed_days
        
        # 格式化顯示新鮮度字串
        fresh_display = freshness_val if freshness_val else "未設定 (預設 C 級: 半年)"
        print(f"\n[{idx}/{len(pages)}] 正在評估: {title}")
        print(f"    - 新鮮度設定: {fresh_display} (容許天數: {allowed_days} 天)")
        print(f"    - 基準日期: {base_date.strftime('%Y-%m-%d')} (已過去: {days_passed} 天)")

        if not is_expired:
            print("    [OK] 知識仍在有效生命週期內，跳過。")
            continue
            
        expired_count += 1
        print("    [!] 該項目已過期！啟動 URL 存活與 LLM 時效評估機制...")
        
        # 1. URL 狀態探測
        url_status = check_url_status(url)
        print(f"    [+] 連結探測結果: {url_status}")
        
        # 2. LLM 時效評估
        print(f"    [+] 正在呼叫 {engine_name.upper()} 評估該知識在 2026 年是否過時淘汰...")
        evaluation = evaluate_freshness_with_llm(title, url, summary, url_status, fresh_display)
        decision = evaluation.get("decision", "KEEP").upper()
        reason = evaluation.get("reason", "無詳細說明")
        
        print(f"    [+] 知識治理決策: {decision}")
        print(f"    [+] 評估原因: {reason}")
        
        if decision == "KEEP":
            print("    [+] 決策為保持。正在更新頁面的「最後驗證時間」為今天...")
            if verification_field:
                if update_page_freshness_meta(notion, page["id"], verification_field):
                    print("    [OK] 成功更新最後驗證時間！")
                    updated_meta_count += 1
                else:
                    print("    [WARN] 更新驗證時間失敗。")
            else:
                print("    [WARN] 找不到『最後驗證時間』欄位，無法更新屬性。請在原始資料庫新增 Date 類型的屬性。")
                
        elif decision in ["UPDATE", "ARCHIVE"]:
            action_type = "更新" if decision == "UPDATE" else "歸檔"
            task_title = f"[知識庫代謝] {action_type}過期知識：{title}"
            
            print(f"    [!] 決策為 {decision} ({action_type})。正在建立維護任務...")
            if task_db_id:
                if create_maintenance_task(notion, task_db_id, task_title, page["id"]):
                    print(f"    [OK] 成功將維護任務寫入 Task DB！")
                    created_tasks_count += 1
                else:
                    print("    [WARN] 寫入任務失敗。")
            else:
                print(f"    [WARN] 未配置任務資料庫，僅列印治理任務說明：")
                print(f"      >> 任務名稱: {task_title}")
                print(f"      >> 關聯來源: {title} (ID: {page['id']})")
                
        # 頻率防護，每次評估休息 0.5 秒
        time.sleep(0.5)

    print("\n" + "=" * 60)
    print("[INFO] 知識生命週期代謝巡檢圓滿結束！")
    print(f"  - 評估總筆數: {len(pages)} 筆")
    print(f"  - 判定已過期: {expired_count} 筆")
    print(f"  - 自動更新驗證時間 (KEEP): {updated_meta_count} 筆")
    if task_db_id:
        print(f"  - 寫入 Task DB 之維護任務: {created_tasks_count} 筆")
    print("=" * 60)

if __name__ == "__main__":
    main()
