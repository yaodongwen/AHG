import sys
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR) 

DB_PATH = os.path.join(PROJECT_ROOT, "database", "finance_news.db")
CONCEPT_DIR = os.path.join(PROJECT_ROOT, "concept")
CONTENT_ROOT = os.path.join(PROJECT_ROOT, "data", "content")

print("base dir {}",BASE_DIR)
print("PROJECT_ROOT dir {}",PROJECT_ROOT)
print("DB_PATH dir {}",DB_PATH)
print("CONCEPT_DIR dir {}",CONCEPT_DIR)
print("CONTENT_ROOT dir {}",CONTENT_ROOT)