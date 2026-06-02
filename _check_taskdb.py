import sys, io, os, json
from dotenv import load_dotenv
from notion_client import Client

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
load_dotenv()

notion_key = os.getenv('NOTION_API_KEY')
if not notion_key:
    print("ERROR: Please set NOTION_API_KEY in your .env file")
    sys.exit(1)

notion = Client(auth=notion_key)

task_db_id = os.getenv('NOTION_TASK_DATABASE_ID')
if not task_db_id:
    print("ERROR: Please set NOTION_TASK_DATABASE_ID in your .env file")
    sys.exit(1)

# 嘗試直接寫一筆測試任務
try:
    result = notion.pages.create(
        parent={"database_id": task_db_id},
        properties={
            "名稱": {
                "title": [{"text": {"content": "[TEST] 這是一筆測試任務，請手動刪除"}}]
            }
        }
    )
    print("SUCCESS! Page ID:", result['id'])
    print("Properties written:", list(result.get('properties', {}).keys()))
except Exception as e:
    print("ERROR with '名稱':", str(e)[:200])
    # 試 'Name'
    try:
        result = notion.pages.create(
            parent={"database_id": task_db_id},
            properties={
                "Name": {
                    "title": [{"text": {"content": "[TEST] 這是一筆測試任務，請手動刪除"}}]
                }
            }
        )
        print("SUCCESS with 'Name'! Page ID:", result['id'])
        print("Properties:", list(result.get('properties', {}).keys()))
    except Exception as e2:
        print("ERROR with 'Name':", str(e2)[:200])
