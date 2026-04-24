import os
import sys
import json
import hashlib

class StorageManager:
    @staticmethod
    def get_base_dir():
        if sys.platform.startswith("win"):
            appdata = os.getenv('APPDATA')
            if not appdata:
                appdata = os.path.expanduser("~")
            base_dir = os.path.join(appdata, "NovelReaderApp")
        else:
            home_dir = os.path.expanduser("~")
            current_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
            current_dir_normalized = current_dir.replace("\\", "/")
            
            if "flet/app" in current_dir_normalized:
                home_dir = current_dir_normalized.split("flet/app")[0]
            elif home_dir == "/data" or home_dir == "/" or not os.access(home_dir, os.W_OK):
                home_dir = current_dir
                
            base_dir = os.path.join(home_dir, ".novelreaderapp")
            
        if not os.path.exists(base_dir):
            try: 
                os.makedirs(base_dir, exist_ok=True)
            except Exception: 
                import tempfile
                base_dir = os.path.join(tempfile.gettempdir(), "NovelReaderApp")
                try: os.makedirs(base_dir, exist_ok=True)
                except Exception: pass
        return base_dir

    @classmethod
    def load_json(cls, filename, default=None):
        path = os.path.join(cls.get_base_dir(), filename)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception: pass
        return default if default is not None else {}

    @classmethod
    def save_json(cls, filename, data):
        path = os.path.join(cls.get_base_dir(), filename)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e: 
            print(f"保存文件 {filename} 失败: {e}")

    @classmethod
    def load_book_summaries(cls, book_path):
        if not book_path: return {}
        path_hash = hashlib.md5(book_path.encode('utf-8')).hexdigest()
        summaries_dir = os.path.join(cls.get_base_dir(), "ai_summaries")
        path = os.path.join(summaries_dir, f"{path_hash}.json")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception: pass
        return {}

    @classmethod
    def save_book_summaries(cls, book_path, data):
        if not book_path: return
        summaries_dir = os.path.join(cls.get_base_dir(), "ai_summaries")
        if not os.path.exists(summaries_dir):
            try: os.makedirs(summaries_dir, exist_ok=True)
            except Exception: pass
            
        path_hash = hashlib.md5(book_path.encode('utf-8')).hexdigest()
        path = os.path.join(summaries_dir, f"{path_hash}.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存书籍总结失败: {e}")

    # ==========================
    # 【新增】目录缓存 (TOC Cache)
    # ==========================
    @classmethod
    def get_toc_dir(cls):
        path = os.path.join(cls.get_base_dir(), "tocs")
        if not os.path.exists(path):
            try: os.makedirs(path, exist_ok=True)
            except Exception: pass
        return path

    @classmethod
    def load_book_toc(cls, book_path):
        if not book_path: return None
        path_hash = hashlib.md5(book_path.encode('utf-8')).hexdigest()
        path = os.path.join(cls.get_toc_dir(), f"{path_hash}.json")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception: pass
        return None

    @classmethod
    def save_book_toc(cls, book_path, toc_data):
        if not book_path or not toc_data: return
        path_hash = hashlib.md5(book_path.encode('utf-8')).hexdigest()
        path = os.path.join(cls.get_toc_dir(), f"{path_hash}.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(toc_data, f, ensure_ascii=False, indent=4)
        except Exception: pass