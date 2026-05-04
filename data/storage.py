# ==============================================================================
# 文件：core/engine.py[cite: 28]
# 职责：文本解析与小说结构化引擎 (Text Parsing & Structural Engine)[cite: 28]
# 
# 详细功能介绍：
# 1. 智能编码读取：内置多编码探测（UTF-8, GBK, UTF-16 等），确保导入各种老旧 TXT 文本时不会乱码报错[cite: 28]。
# 2. 章节正则扫描：使用高性能正则表达式匹配“第X章”、“卷X”等常见网文目录特征，瞬间将百万字长文切分为结构化的章节数组[cite: 28]。
# 3. 缓存秒开支持：提供 `load_with_cache` 方法，允许直接读取已固化的目录缓存，避开重复正则计算，实现万章小说的秒速打开[cite: 28]。
# 4. 按需内存提取：通过 `get_chapter_text` 方法，利用起止索引坐标精准从内存池中截取单章文本，极大地节省了运行内存[cite: 28]。
#
# 架构定位：底层数据清洗工厂。负责把无序的 TXT 纯文本，转化为 UI 和 AI 都能理解的“章节块”结构[cite: 28]。
# ==============================================================================
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
    def load_book_summaries(cls, book_id): # 💥 参数改为 book_id
        if not book_id: return {}
        summaries_dir = os.path.join(cls.get_base_dir(), "ai_summaries")
        path = os.path.join(summaries_dir, f"{book_id}.json") # 💥 直接用 ID 做文件名
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception: pass
        return {}

    @classmethod
    def save_book_summaries(cls, book_id, data):
        if not book_id: return
        summaries_dir = os.path.join(cls.get_base_dir(), "ai_summaries")
        if not os.path.exists(summaries_dir):
            try: os.makedirs(summaries_dir, exist_ok=True)
            except Exception: pass
            
        path = os.path.join(summaries_dir, f"{book_id}.json")
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
    def load_book_toc(cls, book_id):
        if not book_id: return None
        path = os.path.join(cls.get_toc_dir(), f"{book_id}.json")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception: pass
        return None

    @classmethod
    def save_book_toc(cls, book_id, toc_data):
        if not book_id or not toc_data: return
        path = os.path.join(cls.get_toc_dir(), f"{book_id}.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(toc_data, f, ensure_ascii=False, indent=4)
        except Exception: pass