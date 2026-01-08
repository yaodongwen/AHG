import re
import pypinyin
from deep_translator import GoogleTranslator

class TranslationUtils:
    @staticmethod
    def to_english_name(text):
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