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
DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "981c349065cd4f92bb0ba358b9e0a56d")

if not NOTION_API_KEY:
    print("[ERROR] 找不到 NOTION_API_KEY")
    sys.exit(1)

notion = Client(auth=NOTION_API_KEY)

# 為了防止 400，對 Facebook 域名不帶自訂 Header，對其他使用預設 requests 即可。
def fetch_url_content(url):
    try:
        # 使用 python-requests 預設的 UA 訪問 facebook.com
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as e:
        print(f"    [ERROR] 擷取網頁失敗 ({url}): {e}")
        return None

def extract_meta_info(html):
    """從 HTML 的 Meta 標籤中抽取貼文標題與內容"""
    if not html:
        return None, None
        
    soup = BeautifulSoup(html, "html.parser")
    
    # 提取 OpenGraph description
    og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
    og_title = soup.find("meta", property="og:title")
    
    desc_text = og_desc.get("content", "").strip() if og_desc else ""
    title_text = og_title.get("content", "").strip() if og_title else ""
    
    # 如果內容中包含登入跳轉的廢話，說明沒抓到真實內容
    if "Facebook" in desc_text[:20] or "登入" in desc_text[:10]:
        desc_text = ""
        
    # 如果沒有 og:title，或 og:title 是通用詞
    if not title_text or "Facebook" in title_text:
        title_text = ""
        
    return title_text, desc_text

def get_page_title(page):
    properties = page.get("properties", {})
    for name, prop in properties.items():
        if prop.get("type") == "title":
            title_objs = prop.get("title", [])
            return "".join([t.get("plain_text", "") for t in title_objs]).strip()
    return ""

def get_page_url(page):
    properties = page.get("properties", {})
    for name, prop in properties.items():
        if prop.get("type") == "url":
            return prop.get("url") or ""
    return ""

def is_page_content_empty(page_id):
    try:
        blocks = notion.blocks.children.list(block_id=page_id, page_size=10)
        results = blocks.get("results", [])
        if not results:
            return True
            
        total_text_len = 0
        for block in results:
            b_type = block.get("type")
            if b_type in ["paragraph", "heading_1", "heading_2", "heading_3", 
                          "bulleted_list_item", "numbered_list_item", "to_do", "toggle"]:
                rich_texts = block.get(b_type, {}).get("rich_text", [])
                for rt in rich_texts:
                    total_text_len += len(rt.get("plain_text", ""))
        return total_text_len < 20
    except Exception:
        return False

def clean_desc_to_paragraphs(desc_text):
    """將貼文內容切分為多個段落，長度限制在 1500 字以防 Notion 崩潰"""
    lines = [line.strip() for line in desc_text.split("\n") if line.strip()]
    paragraphs = []
    for line in lines:
        if len(line) > 1500:
            parts = [line[i:i+1500] for i in range(0, len(line), 1500)]
            for p in parts:
                paragraphs.append(p)
        else:
            paragraphs.append(line)
    return paragraphs

def main():
    print(f"正在搜尋資料庫 {DATABASE_ID} 中「無標題」且「無內文」的有網址 Facebook 頁面...")
    
    try:
        db_info = notion.databases.retrieve(DATABASE_ID)
        data_sources = db_info.get("data_sources", [])
        if not data_sources:
            print("[ERROR] 無法在該資料庫中找到資料來源")
            sys.exit(1)
        data_source_id = data_sources[0]["id"]
        
        # 撈取所有有網址的頁面 (由於無標題不易做 text filter，我們直接查詢所有有 URL 的)
        # 再用 Python 篩選標題為空/無標題，且內文為空的項目
        has_more = True
        next_cursor = None
        target_pages = []
        scanned_count = 0
        
        while has_more:
            query_params = {
                "data_source_id": data_source_id,
                "page_size": 100,
                "filter": {
                    "property": "URL",
                    "url": {
                        "is_not_empty": True
                    }
                }
            }
            if next_cursor:
                query_params["start_cursor"] = next_cursor
                
            response = notion.data_sources.query(**query_params)
            results = response.get("results", [])
            scanned_count += len(results)
            print(f"  已掃描有網址的文章: {scanned_count} 筆...")
            
            for page in results:
                url = get_page_url(page)
                # 只處理 Facebook/Instagram 等社群分享
                if not any(k in url for k in ["facebook.com", "fb.watch", "youtu"]):
                    continue
                    
                title = get_page_title(page)
                
                # 判定標題是否缺失 (空字串、或是 "無標題" 或是 "test")
                is_title_missing = not title or title.strip() in ["無標題", "test", "Untitled"]
                
                if is_title_missing:
                    page_id = page["id"]
                    # 進一步檢查內文是否為空
                    if is_page_content_empty(page_id):
                        target_pages.append({
                            "id": page_id,
                            "title": title,
                            "url": url
                        })
                        print(f"    [MATCH] 匹配到需修復頁面 (ID: {page_id}, URL: {url})")
                        
                        # 每次最多修復 15 筆，避免耗時過長
                        if len(target_pages) >= 15:
                            has_more = False
                            break
                            
            if not response.get("has_more"):
                has_more = False
            else:
                next_cursor = response.get("next_cursor")
                
        print(f"\n掃描結束。共發現 {len(target_pages)} 筆無標題且無內文的 Facebook 頁面。")
        
        if not target_pages:
            print("[INFO] 沒有找到符合修復條件的頁面。")
            sys.exit(0)
            
        print("\n開始執行自動內容修補與標題重構...")
        success_count = 0
        
        for idx, item in enumerate(target_pages, 1):
            page_id = item["id"]
            url = item["url"]
            print(f"\n[{idx}/{len(target_pages)}] 正在處理網址: {url}")
            
            # 1. 爬取
            html = fetch_url_content(url)
            if not html:
                print("  [SKIP] 無法取得網頁 HTML，跳過。")
                continue
                
            # 2. 解析
            meta_title, meta_desc = extract_meta_info(html)
            if not meta_desc:
                print("  [SKIP] 解析失敗或貼文內容為空，跳過。")
                continue
                
            # 3. 擬定新標題 (優先使用 og:title，若無，則使用貼文前 25 個字)
            new_title = meta_title
            if not new_title:
                clean_desc_preview = meta_desc.replace("\n", " ").strip()
                if len(clean_desc_preview) > 25:
                    new_title = clean_desc_preview[:25] + "..."
                else:
                    new_title = clean_desc_preview
                    
            if not new_title:
                new_title = "未命名 Facebook 貼文"
                
            print(f"  - 擬定新標題: {new_title}")
            print(f"  - 提取內容長度: {len(meta_desc)} 字")
            
            # 4. 追加寫入內文 blocks
            paragraphs = clean_desc_to_paragraphs(meta_desc)
            blocks = []
            for p in paragraphs:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": p
                                }
                            }
                        ]
                    }
                })
                
            print("  - 正在將段落追加寫入 Notion 頁面...")
            # 分批追加
            batch_size = 40
            for i in range(0, len(blocks), batch_size):
                batch = blocks[i:i+batch_size]
                notion.blocks.children.append(block_id=page_id, children=batch)
                time.sleep(0.5)
                
            # 5. 更新 Notion 頁面屬性（寫入新標題，並重設 AI 已處理=False）
            # 注意：在 Notion 中，頁面的 title 屬性是在 properties 底下名為 "Name" 或 "Title" 的屬性。
            # 我們需要偵測該 title 屬性的名稱是什麼。通常是 "Name" 或是 "名稱" 或是 "標題"
            # 我們先獲取該 page 的屬性以確認 title 屬性名稱
            page_detail = notion.pages.retrieve(page_id=page_id)
            title_prop_name = None
            for prop_name, prop_val in page_detail.get("properties", {}).items():
                if prop_val.get("type") == "title":
                    title_prop_name = prop_name
                    break
                    
            if not title_prop_name:
                title_prop_name = "Name" # 預設回退
                
            print(f"  - 正在更新 Notion 標題屬性 [{title_prop_name}] 並標記為 AI 未處理...")
            notion.pages.update(
                page_id=page_id,
                properties={
                    title_prop_name: {
                        "title": [
                            {
                                "text": {
                                    "content": new_title
                                }
                            }
                        ]
                    },
                    "AI 已處理": {
                        "checkbox": False
                    }
                }
            )
            print("  [OK] 處理成功！")
            success_count += 1
            time.sleep(1.0)
            
        print(f"\n[INFO] 全部修復完成！共成功修補了 {success_count} 筆頁面的標題與內文。")
        if success_count > 0:
            print("\n[INFO] 正在自動為這些新修復的文章啟動 AI 批次提煉...")
            # 直接在 python 中執行 batch_processor.py 來為這幾筆重新做 AI 提煉
            os.system(f"python batch_processor.py --limit {success_count} --yes")
            
    except Exception as e:
        print(f"[ERROR] 執行過程中出錯: {e}")

if __name__ == "__main__":
    main()
