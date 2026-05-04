# ==============================================================================
# 文件：data/storage.py
# 职责：底层硬盘 I/O 大管家 (File System / Storage Manager)
# 
# 详细功能介绍：
# 1. 跨平台路径归一化：动态识别当前运行环境（Windows 桌面端 / Android 移动端 / Flet 独立沙盒），
#    极其精准地计算出安全、可写的全局根目录 (get_base_dir)。
# 2. JSON 持久化基座：封装了所有 .json 文件的读写操作（如全局配置、书架数据），并做好防奔溃处理。
# 3. RAG 知识库配件管理：完全基于书籍的唯一标识 (book_id) 来存取配套的静态文件，包含：
#    - ai_summaries/：存放每本书各章节的 AI 总结与追问历史对话。
#    - tocs/：存放已解析书籍的章节目录缓存，实现二次打开“秒进”阅读页。
# 
# 架构定位：这是一个纯静态工具类 (Static Utility Class)，无状态，只负责和操作系统的底层硬盘打交道。
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

    # ==========================
    # 专属目录获取助手 (Path Helpers)
    # ==========================
    @classmethod
    def get_db_dir(cls):
        """获取向量数据库的专属目录"""
        path = os.path.join(cls.get_base_dir(), "vector_dbs")
        if not os.path.exists(path):
            try: os.makedirs(path, exist_ok=True)
            except Exception: pass
        return path

    @classmethod
    def get_summaries_dir(cls):
        """获取 AI 总结的专属目录"""
        path = os.path.join(cls.get_base_dir(), "ai_summaries")
        if not os.path.exists(path):
            try: os.makedirs(path, exist_ok=True)
            except Exception: pass
        return path

    # ==========================
    # AI 总结读写
    # ==========================
    @classmethod
    def load_book_summaries(cls, book_id): 
        if not book_id: return {}
        # 💥 架构优化：直接呼叫专属助手获取路径
        path = os.path.join(cls.get_summaries_dir(), f"{book_id}.json") 
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception: pass
        return {}

    @classmethod
    def save_book_summaries(cls, book_id, data):
        if not book_id: return
        # 💥 架构优化：直接呼叫专属助手获取路径
        path = os.path.join(cls.get_summaries_dir(), f"{book_id}.json")
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