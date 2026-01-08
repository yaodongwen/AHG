import pandas as pd
import akshare as ak
import os
import time
import sqlite3
import datetime
import requests
import re
import ollama  # 导入 ollama 库
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai import AIKeywordGenerator
from tools import TranslationUtils

# ================= 配置区 =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))

DB_PATH = os.path.join(PROJECT_ROOT, "database", "finance_news.db")
CONCEPT_DIR = os.path.join(PROJECT_ROOT, "concept")
CONTENT_ROOT = os.path.join(PROJECT_ROOT, "data", "content")

# 在这里指定你刚才 pull 下来的模型名字
# 8GB 内存建议 'qwen2.5:3b'，16GB 建议 'qwen2.5:7b'
AI_MODEL_NAME = "qwen3:4b" 
# ==========================================


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
        if not os.path.exists(save_dir): os.makedirs(save_dir)
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
        self._init_master_table()

    def _get_conn(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _init_master_table(self):
        with self._get_conn() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS concepts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_name TEXT UNIQUE,
                table_name TEXT UNIQUE,
                ai_keywords TEXT, -- 新增：记录AI生成的关键词
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )""")
            conn.commit()

    def get_or_create_concept_table(self, concept_chinese_name, keywords_list):
        table_name = TranslationUtils.to_english_name(concept_chinese_name)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        keywords_str = ",".join(keywords_list) # 存入数据库备查

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

    def _fetch_full_text(self, url):
        if not url or not url.startswith('http'): return ""
        try:
            response = requests.get(url, headers=self.headers, timeout=5)
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
            news_df = ak.stock_news_em(symbol=stock_code)
            if news_df is None or news_df.empty: return None
            news_df.rename(columns={'新闻标题':'title', '内容':'desc', '发布时间':'public_time', '新闻链接':'url'}, inplace=True)
            
            pattern = '|'.join([re.escape(k) for k in keywords]) # 正则转义防止报错
            mask = news_df['title'].astype(str).str.contains(pattern, case=False, na=False)
            matched = news_df[mask].copy()
            if matched.empty: return None
            
            file_paths = []
            exact_hits = []
            for _, row in matched.iterrows():
                exact_hits.append(self._find_exact_keywords(row['title'], keywords))
                full_text = self._fetch_full_text(row['url'])
                file_paths.append(FileManager.save_content_to_file(folder_name, row['title'], full_text) if full_text else "")
                time.sleep(0.3)
            
            matched['file_path'] = file_paths
            matched['matched_keywords'] = exact_hits
            return matched
        except: return None

def main():
    print(f"🚀 启动 AI 增强版 (Ollama inside)...")
    
    # 0. 检查 Ollama 是否运行 (简单的健康检查)
    try:
        ollama.list()
    except:
        print("❌ 错误: 无法连接 Ollama。请确保你已经安装并运行了 Ollama (在终端输入 'ollama serve')")
        return

    db_manager = DatabaseManager(DB_PATH)
    crawler = CrawlEngine(CONCEPT_DIR) 
    
    files = crawler.get_excel_files()
    if not files: print(f"⚠️ 没找到xlsx文件"); return

    for file_name in files:
        concept_cn = file_name.replace(".xlsx", "").replace("概念", "").replace("板块", "")
        
        # ==========================================
        # 🧠 第一步：调用 AI 生成关键词
        # ==========================================
        aiKeywordGenerator = AIKeywordGenerator(AI_MODEL_NAME)
        keywords = aiKeywordGenerator.generate_keywords(concept_cn)
        
        # 数据库记录概念和生成的关键词
        table_name = db_manager.get_or_create_concept_table(concept_cn, keywords)
        print(f"======== {concept_cn} -> {table_name} ========")
        
        full_path = os.path.join(CONCEPT_DIR, file_name)
        df_stock, code_col, name_col = crawler.read_stock_list(full_path)
        if df_stock is None: continue

        total_new = 0
        for idx, row in df_stock.iterrows():
            code = crawler.clean_code(row[code_col])
            raw_name = row[name_col] if name_col else "Unknown"
            name = str(raw_name).strip()
            if name in ['nan', '']: name = "Unknown"
            
            print(f"\r[{idx+1}/{len(df_stock)}] {name}({code}) check...", end="")
            
            # 使用 AI 生成的 keywords 进行爬取
            news_data = crawler.fetch_news_and_content(code, keywords, table_name)
            
            if news_data is not None:
                news_data['stock_code'] = code
                news_data['stock_name'] = name
                count = db_manager.save_news_index(table_name, news_data)
                if count > 0: total_new += count
            
            time.sleep(0.1)
        print(f"\n✅ 完成，新增 {total_new} 条。")

if __name__ == "__main__":
    main()