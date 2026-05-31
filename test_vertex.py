import os
import sys
import json
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

key_path = "gcp-key.json"

print(f"確認金鑰檔案 {key_path} 是否存在...")
if not os.path.exists(key_path):
    print(f"[ERROR] 找不到 {key_path}！請確認檔案已放置於 Notion_agent/ 目錄下。")
    sys.exit(1)

print("[INFO] 找到金鑰檔案，正在讀取並解析 project_id...")
try:
    with open(key_path, "r", encoding="utf-8") as f:
        key_data = json.load(f)
        project_id = key_data.get("project_id")
        client_email = key_data.get("client_email")
        
    print(f"  - Project ID: {project_id}")
    print(f"  - Client Email: {client_email}")
    
    if not project_id:
        raise ValueError("無法在 JSON 金鑰中找到 project_id 欄位")
except Exception as e:
    print(f"[ERROR] 解析 JSON 金鑰失敗: {e}")
    sys.exit(1)

print("\n嘗試載入 google-genai SDK 與驗證庫...")
try:
    from google import genai
    from google.oauth2 import service_account
    print("[SUCCESS] SDK 載入成功！")
except ImportError as e:
    print(f"[ERROR] 載入 SDK 失敗: {e}")
    print("請確認是否已安裝 google-genai 軟體包，可執行: pip install google-genai google-auth")
    sys.exit(1)

print("\n正在使用服務帳戶憑證初始化 genai.Client...")
try:
    credentials = service_account.Credentials.from_service_account_file(
        key_path,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    client = genai.Client(
        vertexai=True,
        project=project_id,
        credentials=credentials
    )
    print("[SUCCESS] Client 初始化成功！")
except Exception as e:
    print(f"[ERROR] Client 初始化失敗: {e}")
    sys.exit(1)

print("\n正在嘗試向 Vertex AI 發送簡單請求 (使用 gemini-2.5-flash)...")
try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Hello! Please respond with a short sentence to verify the connection is working."
    )
    print("\n--- API 回應結果 ---")
    print(response.text)
    print("-------------------")
    print("[SUCCESS] Vertex AI 連線測試成功！")
except Exception as e:
    print(f"[ERROR] API 呼叫失敗: {e}")
    print("\n請檢查：")
    print("1. 該服務帳戶是否在 GCP 控制台中啟用了 Vertex AI API")
    print("2. 該服務帳戶是否具非凡或正確的 Vertex AI 使用者權限 (例如 Vertex AI User 角色)")
    sys.exit(1)
