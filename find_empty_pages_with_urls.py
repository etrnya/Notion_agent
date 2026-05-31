import os
import sys
import io
import json
from dotenv import load_dotenv
from notion_client import Client

# 強制 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "981c349065cd4f92bb0ba358b9e0a56d")

if not NOTION_API_KEY:
    print("[ERROR] 找不到 NOTION_API_KEY")
    sys.exit(1)

notion = Client(auth=NOTION_API_KEY)

def get_page_title(page):
    properties = page.get("properties", {})
    for name, prop in properties.items():
        if prop.get("type") == "title":
            title_objs = prop.get("title", [])
            return "".join([t.get("plain_text", "") for t in title_objs])
    return "無標題"

def get_page_url(page):
    properties = page.get("properties", {})
    for name, prop in properties.items():
        if prop.get("type") == "url":
            return prop.get("url") or ""
    return ""

print(f"正在搜尋資料庫 {DATABASE_ID} 中 AI 標記為空白且有網址的頁面 (高速過濾)...")

empty_pages = []

try:
    # 獲取資料來源 ID
    db_info = notion.databases.retrieve(DATABASE_ID)
    data_sources = db_info.get("data_sources", [])
    if not data_sources:
        print("[ERROR] 無法在該資料庫中找到資料來源 (Data Source)。")
        sys.exit(1)
    data_source_id = data_sources[0]["id"]
    print(f"[INFO] 取得 Data Source ID: {data_source_id}")

    # 使用 Notion API 的過濾器進行高速篩選
    filter_query = {
        "and": [
            {
                "property": "URL",
                "url": {
                    "is_not_empty": True
                }
            },
            {
                "or": [
                    {
                        "property": "AI 摘要",
                        "rich_text": {
                            "contains": "無內文"
                        }
                    },
                    {
                        "property": "AI 摘要",
                        "rich_text": {
                            "contains": "無內容"
                        }
                    },
                    {
                        "property": "AI 摘要",
                        "rich_text": {
                            "contains": "不足"
                        }
                    },
                    {
                        "property": "AI 摘要",
                        "rich_text": {
                            "contains": "無法提煉"
                        }
                    }
                ]
            }
        ]
    }

    response = notion.data_sources.query(
        data_source_id=data_source_id,
        filter=filter_query,
        page_size=100
    )
    
    results = response.get("results", [])
    print(f"篩選成功，共撈取到 {len(results)} 筆潛在的空白內文頁面。")
    
    for page in results:
        page_id = page["id"]
        url = get_page_url(page)
        # 排除 youtube 網址
        if "youtube.com" in url or "youtu.be" in url or "youtube" in url:
            continue
            
        title = get_page_title(page)
        empty_pages.append({
            "id": page_id,
            "title": title,
            "url": url
        })
        print(f"  [FND] {title} (URL: {url})")
        
        # 我們限制每次最多只處理 10 筆，避免寫入過於頻繁
        if len(empty_pages) >= 10:
            break
            
    print(f"\n篩選完成。共選定 {len(empty_pages)} 筆空白內文且有網址的非影片文章。")
    with open("empty_pages_to_process.json", "w", encoding="utf-8") as f:
        json.dump(empty_pages, f, ensure_ascii=False, indent=2)
    print("名單已儲存至 empty_pages_to_process.json")
    
except Exception as e:
    print(f"[ERROR] 查詢 Notion 失敗: {e}")
