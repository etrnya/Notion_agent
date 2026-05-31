import os
import sys
import io
from dotenv import load_dotenv
from notion_client import Client

# 強制 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
notion = Client(auth=NOTION_API_KEY)
db_id = "981c349065cd4f92bb0ba358b9e0a56d"

try:
    # 獲取資料來源 ID
    db = notion.databases.retrieve(database_id=db_id)
    data_source_id = db["data_sources"][0]["id"]
    
    # 撈取深受啟發不為空的頁面
    response = notion.data_sources.query(
        data_source_id=data_source_id,
        filter={
            "property": "深受啟發",
            "select": {
                "is_not_empty": True
            }
        },
        page_size=10
    )
    results = response.get("results", [])
    print(f"Found {len(results)} pages with '深受啟發' not empty.")
    for idx, page in enumerate(results, 1):
        props = page.get("properties", {})
        title = ""
        for k, v in props.items():
            if v.get("type") == "title":
                title = "".join([t.get("plain_text", "") for t in v.get("title", [])])
                break
        inspired_val = props.get("深受啟發", {}).get("select", {})
        print(f"Page {idx}: '{title}' -> '深受啟發' select value: {inspired_val}")
except Exception as e:
    print("Error:", e)
