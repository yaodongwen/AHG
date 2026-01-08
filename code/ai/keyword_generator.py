import json  # 记得在文件最开头加上 import json
import ollama

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import TranslationUtils

class AIKeywordGenerator:
    """
    智能大脑：利用本地 LLM 自动扩展关键词 (JSON 强制版)
    """
    
    def __init__(self, model="qwen3:4b"):
        """
        初始化 AIKeywordGenerator。
        
        :param model: 要使用的 Ollama 模型名称，默认为 "qwen3:4b"
        """
        self.model = model

    def generate_keywords(self, concept_name):
        print(f"   🧠 AI正在思考: '{concept_name}' 的关联词...", end="", flush=True)
        
        # 1. 定义强制 JSON 的 Prompt
        # 我们给它几个范例 (Few-Shot)，教它怎么做
        prompt = f"""
        你是一个专业的金融关键词提取API。
        任务：根据输入的【A股概念】，输出该行业在全球市场（美股、港股）最核心的【英文关键词】。
        
        要求：
        1. 关键词必须是英文。
        2. 包含行业缩写 (如 VR, EV)。
        3. 包含全球领头羊公司 (如 Tesla, Apple)。
        4. 包含核心产品名 (如 GPU, Vision Pro)。
        5. 只需要最重要的 5 个词。
        6. 严禁输出任何思考过程，严禁中文解释。
        
        范例 1:
        输入: "虚拟现实"
        输出: {{ "keywords": ["VR", "Meta", "Apple", "Quest", "Vision Pro"] }}
        
        范例 2:
        输入: "光伏概念"
        输出: {{ "keywords": ["Solar", "Photovoltaic", "PV", "First Solar", "Inverter"] }}
        
        现在请处理:
        输入: "{concept_name}"
        输出:
        """
        
        try:
            # 2. 调用 Ollama，开启 format='json'
            response = ollama.chat(
                model=self.model, 
                messages=[{'role': 'user', 'content': prompt}],
                format='json',  # <--- 关键！强制输出 JSON
                options={'temperature': 0.2}  # <--- 关键！降低创造性，让它老实点
            )
            
            content = response['message']['content']
            
            # 3. 解析 JSON
            data = json.loads(content)
            
            # 提取 keywords 列表
            keywords = data.get("keywords", [])
            
            # 兜底清洗：确保都是字符串
            keywords = [str(k).strip() for k in keywords if k]
            
            # 把原本的中文名也加进去，防止 AI 跑偏
            english_concept_name = TranslationUtils.to_english_name(concept_name)
            keywords.insert(0, english_concept_name)
            
            # 去重（保留顺序的去重）
            seen = set()
            unique_keywords = []
            for kw in keywords:
                if kw not in seen:
                    seen.add(kw)
                    unique_keywords.append(kw)
            
            print(f" 完成! \n      -> 生成: {unique_keywords}")
            return unique_keywords
            
        except Exception as e:
            print(f" 失败 ({e})。降级使用默认关键词。")
            # 出错时的兜底
            return [concept_name]