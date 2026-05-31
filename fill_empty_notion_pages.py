import os
import sys
import io
import json
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from notion_client import Client

# 強制 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
if not NOTION_API_KEY:
    print("[ERROR] 找不到 NOTION_API_KEY")
    sys.exit(1)

notion = Client(auth=NOTION_API_KEY)

# 定義爬蟲的 Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
}

def clean_html_to_paragraphs(html_content):
    """將 HTML 解析並提取出乾淨的段落文字，特別優化社群媒體(Facebook)等 meta 標籤提取"""
    soup = BeautifulSoup(html_content, "html.parser")
    
    paragraphs = []
    
    # 優先嘗試從 OpenGraph 或 HTML Meta 中提取 description/title
    # 這對於防爬的社群媒體(例如 Facebook)非常重要，因為其 JS 不會執行，但 meta 卻有貼文資訊
    og_desc_meta = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
    if og_desc_meta:
        desc_text = og_desc_meta.get("content", "").strip()
        # 清除一些標準的 Facebook 跳轉提示字眼
        if desc_text and "Facebook" not in desc_text[:20] and "登入" not in desc_text[:10]:
            # 將 description 切割成較短的段落，方便寫入
            lines = [line.strip() for line in desc_text.split("\n") if line.strip()]
            for line in lines:
                if len(line) > 1500:
                    parts = [line[i:i+1500] for i in range(0, len(line), 1500)]
                    for p in parts:
                        paragraphs.append(("p", p))
                else:
                    paragraphs.append(("p", line))
                    
    # 如果 meta description 沒有抓到，或是長度太短（小於 50 字），我們再採用一般的 HTML 標籤提取
    if len("".join([p[1] for p in paragraphs])) < 50:
        # 移除無用的標籤
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "noscript"]):
            tag.decompose()
            
        html_paragraphs = []
        # 尋找主要文字區塊
        for element in soup.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
            text = element.get_text().strip()
            if not text:
                continue
                
            tag_name = element.name
            if len(text) > 1500:
                parts = [text[i:i+1500] for i in range(0, len(text), 1500)]
                for p in parts:
                    html_paragraphs.append((tag_name, p))
            else:
                html_paragraphs.append((tag_name, text))
                
        # 如果結構化標籤依然沒有內容，退回到抓取 body text
        if len(html_paragraphs) < 3:
            body_text = soup.get_text()
            raw_lines = [line.strip() for line in body_text.split("\n") if line.strip()]
            for line in raw_lines:
                # 排除一些常見的登入、Cookie等廢話
                if any(k in line for k in ["Cookie", "JavaScript", "登入", "註冊", "Login", "Sign Up"]):
                    continue
                if len(line) > 1500:
                    parts = [line[i:i+1500] for i in range(0, len(line), 1500)]
                    for p in parts:
                        html_paragraphs.append(("p", p))
                else:
                    html_paragraphs.append(("p", line))
        
        # 將 html 提取的段落加進來
        paragraphs.extend(html_paragraphs)
                
    # 限制總段落數量，避免寫入過多
    return paragraphs[:150]

def convert_to_notion_blocks(paragraphs):
    """將段落轉換為 Notion Block 格式"""
    blocks = []
    for tag, text in paragraphs:
        if tag == "h1":
            b_type = "heading_1"
        elif tag in ["h2", "h3"]:
            b_type = "heading_2"
        elif tag == "h4":
            b_type = "heading_3"
        elif tag == "li":
            b_type = "bulleted_list_item"
        else:
            b_type = "paragraph"
            
        blocks.append({
            "object": "block",
            "type": b_type,
            b_type: {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": text
                        }
                    }
                ]
            }
        })
    return blocks

def fetch_url_content(url):
    """取得網頁 HTML 內容"""
    try:
        # 對於 Facebook 或其他的 share 網址，使用自訂的 Mozilla UA 反而會被拒絕 (400 Bad Request)
        # 我們對於 facebook 域名使用預設的 python-requests UA，其餘才使用自訂 HEADERS
        if "facebook.com" in url or "fb.watch" in url:
            r = requests.get(url, timeout=15)
        else:
            r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        # 自動偵測編碼
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as e:
        print(f"    [ERROR] 擷取網頁失敗 ({url}): {e}")
        return None

def main():
    list_file = "empty_pages_to_process.json"
    if not os.path.exists(list_file):
        print(f"[ERROR] 找不到待處理名單 {list_file}。請先運行 find_empty_pages_with_urls.py 進行掃描。")
        sys.exit(1)
        
    with open(list_file, "r", encoding="utf-8") as f:
        pages_to_process = json.load(f)
        
    if not pages_to_process:
        print("[INFO] 待處理名單為空，無須處理。")
        sys.exit(0)
        
    print(f"[INFO] 開始處理空白頁面內容補齊，共計 {len(pages_to_process)} 筆...")
    
    success_count = 0
    
    for idx, item in enumerate(pages_to_process, 1):
        page_id = item["id"]
        title = item["title"]
        url = item["url"]
        
        print(f"\n[{idx}/{len(pages_to_process)}] 正在處理: {title}")
        print(f"  網址: {url}")
        
        # 1. 抓取網頁內容
        html = fetch_url_content(url)
        if not html:
            print("  [SKIP] 無法取得網頁內容，跳過此筆。")
            continue
            
        # 2. 解析並清洗出段落
        paragraphs = clean_html_to_paragraphs(html)
        if not paragraphs:
            print("  [SKIP] 網頁中未解析出有效文字內容，跳過。")
            continue
            
        print(f"  已成功提取 {len(paragraphs)} 個段落，正在轉為 Notion Blocks...")
        blocks = convert_to_notion_blocks(paragraphs)
        
        # 3. 追加寫入 Notion 頁面內文
        # Notion 追加 block API 每次最多限制 100 個，我們分批寫入（每次 40 個）
        batch_size = 40
        print("  正在寫入內容至 Notion 頁面...")
        try:
            for i in range(0, len(blocks), batch_size):
                batch = blocks[i:i+batch_size]
                notion.blocks.children.append(block_id=page_id, children=batch)
                time.sleep(0.5) # 頻率限制防護
                
            # 4. 更新該頁面的屬性，將 "AI 已處理" 設為 False 
            # 這樣下一次運行批次處理器時，就能以全新的內文重新提煉摘要和標籤！
            notion.pages.update(
                page_id=page_id,
                properties={
                    "AI 已處理": {
                        "checkbox": False
                    }
                }
            )
            print("  [OK] 內容已寫入成功，且已將該頁面標記為「AI 未處理」，以便下次重新提煉！")
            success_count += 1
            
        except Exception as e:
            print(f"  [ERROR] 寫入 Notion 失敗: {e}")
            
        time.sleep(1.0) # 頁面間間隔
        
    print(f"\n[INFO] 處理完成！共成功補齊了 {success_count} 筆頁面內容。")

if __name__ == "__main__":
    main()
