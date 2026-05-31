import asyncio
import os
import sys
from textwrap import dedent
from dotenv import load_dotenv
from agno.agent import Agent
from agno.tools.mcp import MCPTools
from mcp import StdioServerParameters

# 載入環境變數
load_dotenv()

async def run_notion_agent():
    print("=" * 60)
    print("[Notion Agent] Notion MCP Interactive Agent 啟動中...")
    print("=" * 60)

    # 1. 檢查並獲取必要金鑰
    notion_token = os.getenv("NOTION_API_KEY")
    openai_token = os.getenv("OPENAI_API_KEY")
    gemini_token = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    default_page_id = os.getenv("NOTION_PAGE_ID")

    if not notion_token:
        print("[ERROR] 未在 .env 中檢測到 NOTION_API_KEY")
        print("請填寫您的 Notion Integration Token。")
        sys.exit(1)

    # 動態選擇 LLM 引擎
    if gemini_token:
        # 將 GEMINI_API_KEY 對齊為 google-genai 期待的 GOOGLE_API_KEY
        os.environ["GOOGLE_API_KEY"] = gemini_token
        from agno.models.google import Gemini
        model = Gemini(id="gemini-2.5-flash")
        print("[INFO] 偵測到 Gemini 金鑰，將使用 Gemini 引擎 (gemini-2.5-flash)")
    elif openai_token:
        from agno.models.openai import OpenAIChat
        model = OpenAIChat(id="gpt-4o-mini")
        print("[INFO] 偵測到 OpenAI 金鑰，將使用 OpenAI 引擎 (gpt-4o-mini)")
    else:
        print("[ERROR] 未在 .env 中檢測到 OPENAI_API_KEY 或 GEMINI_API_KEY")
        print("請填寫其中一個 API 金鑰以啟動對話。")
        sys.exit(1)

    # 2. 定義 Notion MCP 服務器啟動參數
    # 使用官方 @notionhq/notion-mcp-server，並透過 npx 自動下載運行
    print("[INFO] 正在連接 Notion MCP 服務器...")
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@notionhq/notion-mcp-server"],
        env={
            "NOTION_API_KEY": notion_token,
            "NOTION_VERSION": "2022-06-28"
        }
    )

    # 3. 初始化 Agent 與其 MCP 工具
    try:
        async with MCPTools(server_params=server_params) as mcp_tools:
            # 建立 Agent，邏輯分離
            agent = Agent(
                name="NotionAssistant",
                model=model,
                tools=[mcp_tools],
                description="您是一位專業的 Notion 助手，能夠以自然語言讀寫、搜尋與編輯 Notion 工作區中的頁面、資料庫與區塊。",
                instructions=dedent(f"""
                    您擁有通過 MCP 工具訪問用戶 Notion 工作區的權限。
                    
                    運作規範：
                    1. 用戶的預設綁定頁面/資料庫 ID 是：{default_page_id or '未指定'}。如果用戶要求操作且未指定 ID，優先使用此 ID。
                    2. 在執行任何刪除、清空或覆蓋等破壞性操作前，必須先向用戶確認。
                    3. 當查詢內容時，若內容過長，請自動為用戶進行結構化摘要。
                    4. 回答請使用繁體中文。
                """),
                markdown=True,
                show_tool_calls=True  # 顯示 LLM 呼叫 MCP 工具的軌跡，方便 Debug
            )

            print("[OK] Notion MCP 連線成功！")
            print("[INFO] 輸入 'exit', 'quit' 或 'bye' 可結束對話。")
            print("-" * 60)
            
            # 首次打招呼，檢索頁面資訊
            if default_page_id:
                print(f"[INFO] 正在為您自動讀取預設頁面 (ID: {default_page_id})...")
                await agent.aprint_response(
                    f"請幫我讀取頁面 ID {default_page_id} 的標題與前幾行內容，向用戶打個招呼並簡單介紹該頁面。",
                    stream=True
                )
            else:
                print("[INFO] 您好！目前未設定預設 Page ID，您可以直接告訴我您想操作哪一個 Database ID 或 Page ID。")

            # 4. 啟動終端對話循環 (CLI Loop)
            while True:
                try:
                    user_input = input("\n👤 您: ")
                    if not user_input.strip():
                        continue
                    
                    if user_input.strip().lower() in ["exit", "quit", "bye", "goodbye", "再見", "結束"]:
                        print("\n[INFO] 再見！感謝使用 Notion MCP Agent。")
                        break
                    
                    print("[Agent] 思考中...")
                    await agent.aprint_response(user_input, stream=True)
                    
                except KeyboardInterrupt:
                    print("\n[INFO] 偵測到中斷，正在退出對話...")
                    break
                except Exception as e:
                    print(f"\n[WARN] 執行過程中發生錯誤: {e}")
                    
    except Exception as e:
        print(f"[ERROR] 無法連接 MCP 服務器。請確認您已安裝 Node.js (npx) 且網路連線正常。")
        print(f"詳細錯誤資訊: {e}")

if __name__ == "__main__":
    # 解決 Windows 下 asyncio 事件循環的相容性問題
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_notion_agent())
