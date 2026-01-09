import pandas as pd
import akshare as ak
import os
import time
import sqlite3
import datetime
import requests
import re
import ollama
import threading
import queue
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

import sys
# 确保能导入同级目录的模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 尝试导入 AI 模块，如果没配置好就用替身，防止报错
try:
    from ai import AIKeywordGenerator
except ImportError:
    class AIKeywordGenerator:
        def __init__(self, model): pass
        def generate_keywords(self, name): return [name]

# ================= 配置区 =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))

DB_PATH = os.path.join(PROJECT_ROOT, "database", "finance_news.db")
CONCEPT_DIR = os.path.join(PROJECT_ROOT, "concept")
CONTENT_ROOT = os.path.join(PROJECT_ROOT, "data", "content")

AI_MODEL_NAME = "qwen2.5:3b"
MAX_WORKERS = 16  # 🔥 提速关键：开到 16-32 线程
# ==========================================

# 数据库写入队列
db_write_queue = queue.Queue()

class ProxyPool:
    """
    简易免费代理池：自动获取、维护和分发代理
    """
    def __init__(self):
        self.proxies = []
        self.last_update = 0
        self.lock = threading.Lock()
        
    def fetch_proxies(self):
        """从公开源获取免费代理 (Github 镜像源)"""
        print("   🌐 正在下载免费代理池...")
        # 这些是比较稳定的公开代理列表源
        urls = [
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt"
        ]
        
        temp_proxies = set()
        for url in urls:
            try:
                # 5秒超时，防止下载卡住
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    lines = resp.text.splitlines()
                    for line in lines:
                        if ':' in line:
                            temp_proxies.add(f"http://{line.strip()}")
            except:
                pass
        
        with self.lock:
            self.proxies = list(temp_proxies)
            self.last_update = time.time()
        print(f"   ✅ 代理池更新完毕，当前可用 IP 数: {len(self.proxies)}")

    def get_proxy(self):
        """随机获取一个代理，如果池子空了就触发更新"""
        if not self.proxies or (time.time() - self.last_update > 3600): # 1小时过期
            self.fetch_proxies()
        
        with self.lock:
            if self.proxies:
                return random.choice(self.proxies)
        return None

# 全局代理池实例
global_proxy_pool = ProxyPool()

class TranslationUtils:
    @staticmethod
    def to_english_tablename(text):
        try:
            translator = GoogleTranslator(source='zh-CN', target='en')
            translated = translator.translate(text)
            clean_name = re.sub(r'[^a-zA-Z0-9 ]', '', translated)
            clean_name = clean_name.lower().replace(' ', '_')
            if not clean_name: raise ValueError("Empty")
            return f"news_{clean_name}"
        except:
            from pypinyin import lazy_pinyin
            safe_name = "_".join(lazy_pinyin(text)).replace(" ", "")
            return f"news_{safe_name}"

class FileManager:
    @staticmethod
    def clean_filename(title):
        cleaned = re.sub(r'[\\/*?:"<>|]', '_', str(title))
        cleaned = cleaned.replace('\n', '')
        return cleaned[:50] 

    @staticmethod
    def save_content_to_file(folder_name, title, content):
        if not content: return None
        save_dir = os.path.join(CONTENT_ROOT, folder_name)
        if not os.path.exists(save_dir): 
            os.makedirs(save_dir, exist_ok=True)
            
        filename = f"{FileManager.clean_filename(title)}.txt"
        file_path = os.path.join(save_dir, filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return os.path.relpath(file_path, start=PROJECT_ROOT)
        except: return None

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        if threading.current_thread() is threading.main_thread():
            self._init_master_table()

    def _get_conn(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_master_table(self):
        with self._get_conn() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS concepts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_name TEXT UNIQUE,
                table_name TEXT UNIQUE,
                ai_keywords TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )""")
            conn.commit()

    def get_or_create_concept_table(self, concept_chinese_name, keywords_list):
        table_name = TranslationUtils.to_english_tablename(concept_chinese_name)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        keywords_str = ",".join(keywords_list)

        with self._get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO concepts (concept_name, table_name, ai_keywords, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (concept_chinese_name, table_name, keywords_str, now, now))
            except sqlite3.IntegrityError:
                cursor.execute("""
                    UPDATE concepts SET updated_at = ?, ai_keywords = ? 
                    WHERE concept_name = ?
                """, (now, keywords_str, concept_chinese_name))
            
            cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code TEXT, stock_name TEXT, title TEXT,
                file_path TEXT, public_time TEXT, url TEXT UNIQUE,
                matched_keywords TEXT, crawl_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            conn.commit()
        return table_name

    def save_news_index(self, table_name, df_data):
        if df_data.empty: return 0
        count = 0
        with self._get_conn() as conn:
            cursor = conn.cursor()
            for _, row in df_data.iterrows():
                try:
                    cursor.execute(f"""
                        INSERT OR IGNORE INTO {table_name} 
                        (stock_code, stock_name, title, file_path, public_time, url, matched_keywords)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(row.get('stock_code', '')), str(row.get('stock_name', '')),
                        str(row.get('title', '')), str(row.get('file_path', '')),
                        str(row.get('public_time', '')), str(row.get('url', '')),
                        str(row.get('matched_keywords', ''))
                    ))
                    if cursor.rowcount > 0: count += 1
                except: pass
            conn.commit()
        return count

def db_writer_worker():
    db_manager = DatabaseManager(DB_PATH)
    while True:
        item = db_write_queue.get()
        if item is None: break
        table_name, news_data, concept_name = item
        try:
            count = db_manager.save_news_index(table_name, news_data)
            if count > 0:
                print(f"   [DB] {concept_name} 新入库 {count} 条")
        except: pass
        finally:
            db_write_queue.task_done()

class CrawlEngine:
    def __init__(self, concept_dir):
        self.concept_dir = concept_dir
        self.headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

    def get_excel_files(self):
        if os.path.exists(self.concept_dir):
            return [f for f in os.listdir(self.concept_dir) if f.endswith('.xlsx')]
        return []

    def read_stock_list(self, file_path):
        try:
            df = pd.read_excel(file_path)
            if not any(u'\u4e00' <= char <= u'\u9fff' for char in str(df.columns)):
                df = pd.read_excel(file_path, header=1)
            code_col = next((c for c in df.columns if any(x in str(c) for x in ['代码','Symbol','Code'])), None)
            name_col = next((c for c in df.columns if any(x in str(c) for x in ['简称','名称','Name','name'])), None)
            if code_col and name_col: return df, code_col, name_col
            return None, None, None
        except: return None, None, None

    def clean_code(self, code):
        code = str(code)
        if code.endswith('.0'): code = code[:-2]
        if "." in code: return code.split(".")[0]
        return code.zfill(6)

    def _request_with_retry(self, url, use_proxy=False, retries=3):
        """
        带重试和代理切换的网络请求核心函数
        """
        for i in range(retries):
            proxies = None
            if use_proxy:
                proxy_url = global_proxy_pool.get_proxy()
                if proxy_url:
                    proxies = {"http": proxy_url, "https": proxy_url}
            
            try:
                # 免费代理很慢，超时设置短一点，不行就换
                timeout = 5 if use_proxy else 10
                response = requests.get(url, headers=self.headers, proxies=proxies, timeout=timeout)
                if response.status_code == 200:
                    return response
            except Exception:
                pass # 失败直接重试
        return None

    def _fetch_full_text(self, url):
        if not url or not url.startswith('http'): return ""
        
        # 策略：先尝试直连 (速度快)，如果直连失败，再尝试用代理
        response = self._request_with_retry(url, use_proxy=False, retries=1)
        if not response:
            # 直连失败，启用代理模式重试
            response = self._request_with_retry(url, use_proxy=True, retries=2)
            
        if not response: return ""

        try:
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            div = soup.find('div', class_='Body') or soup.find('div', id='ContentBody')
            if div: return div.get_text(strip=True)
            return "\n".join([p.get_text() for p in soup.find_all('p') if len(p.get_text())>10])
        except: return ""

    def _find_exact_keywords(self, text, keywords_list):
        hits = [k for k in keywords_list if k.lower() in str(text).lower()]
        return ",".join(hits)

    def fetch_news_and_content(self, stock_code, keywords, folder_name):
        try:
            # AkShare 接口很难加代理，通常用本机IP跑列表不会挂，瓶颈在详情页
            news_df = ak.stock_news_em(symbol=stock_code)
            if news_df is None or news_df.empty: return None
            news_df.rename(columns={'新闻标题':'title', '内容':'desc', '发布时间':'public_time', '新闻链接':'url'}, inplace=True)
            
            pattern = '|'.join([re.escape(k) for k in keywords])
            mask = news_df['title'].astype(str).str.contains(pattern, case=False, na=False)
            matched = news_df[mask].copy()
            if matched.empty: return None
            
            file_paths = []
            exact_hits = []
            for _, row in matched.iterrows():
                exact_hits.append(self._find_exact_keywords(row['title'], keywords))
                full_text = self._fetch_full_text(row['url'])
                path = FileManager.save_content_to_file(folder_name, row['title'], full_text) if full_text else ""
                file_paths.append(path)
                # 只有直连成功才sleep，用代理因为慢所以不用sleep
                time.sleep(0.1)
            
            matched['file_path'] = file_paths
            matched['matched_keywords'] = exact_hits
            return matched
        except: return None

def process_single_stock(crawler, row, code_col, name_col, keywords, table_name):
    code = crawler.clean_code(row[code_col])
    name = str(row[name_col]).strip() if name_col else "Unknown"
    if name in ['nan', '']: name = "Unknown"
    
    news_data = crawler.fetch_news_and_content(code, keywords, table_name)
    if news_data is not None:
        news_data['stock_code'] = code
        news_data['stock_name'] = name
        return news_data
    return None

def main():
    print(f"🚀 启动极速代理版 (Threads={MAX_WORKERS})...")
    
    # 初始化代理池 (非阻塞，后台慢慢下)
    threading.Thread(target=global_proxy_pool.fetch_proxies, daemon=True).start()
    
    db_thread = threading.Thread(target=db_writer_worker, daemon=True)
    db_thread.start()

    db_manager = DatabaseManager(DB_PATH)
    crawler = CrawlEngine(CONCEPT_DIR) 
    
    files = crawler.get_excel_files()
    if not files: print(f"⚠️ 没找到xlsx文件"); return

    for file_name in files:
        concept_cn = file_name.replace(".xlsx", "").replace("概念", "").replace("板块", "")
        
        try:
            aiKeywordGenerator = AIKeywordGenerator(AI_MODEL_NAME)
            keywords = aiKeywordGenerator.generate_keywords(concept_cn)
        except: keywords = [concept_cn]
        
        table_name = db_manager.get_or_create_concept_table(concept_cn, keywords)
        print(f"\n======== {concept_cn} -> {table_name} ========")
        
        full_path = os.path.join(CONCEPT_DIR, file_name)
        df_stock, code_col, name_col = crawler.read_stock_list(full_path)
        if df_stock is None: continue

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_stock = {
                executor.submit(
                    process_single_stock, 
                    crawler, row, code_col, name_col, keywords, table_name
                ): idx for idx, row in df_stock.iterrows()
            }
            
            for future in as_completed(future_to_stock):
                idx = future_to_stock[future]
                try:
                    result = future.result()
                    if result is not None:
                        db_write_queue.put((table_name, result, concept_cn))
                        print(f"\r   [{idx+1}/{len(df_stock)}] 命中!", end="")
                    else:
                        print(f"\r   [{idx+1}/{len(df_stock)}] ...", end="")
                except: pass

        print(f"\n✅ {concept_cn} 扫描结束")

    db_write_queue.put(None) 
    db_write_queue.join()
    print("🎉 所有任务全部完成！")

if __name__ == "__main__":
    main()