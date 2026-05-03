# core/library_state.py
import sys
import asyncio
from data.storage import StorageManager

class LibraryStateMixin:
    """负责管理书架、阅读进度、章节缓存等状态"""
    
    def init_library_state(self):
        # --- 核心业务状态 ---
        self.bookshelf = []
        self.current_book_summaries = {}
        self.current_book_path = ""
        self.current_book_name = ""
        self.current_chapter_idx = 0
        self.current_scroll_offset = 0.0  
        self.current_max_scroll_extent = 0.0 
        self.last_reported_pct = -1.0 
        self.filtered_toc_mapping = []
        self.last_search_query = None  
        self.is_immersive = False 

    def _load_bookshelf(self):
        self.bookshelf = StorageManager.load_json("bookshelf.json", default=[])

    def _save_bookshelf(self):
        StorageManager.save_json("bookshelf.json", self.bookshelf)

    def _load_book_summaries(self):
        self.current_book_summaries = StorageManager.load_book_summaries(self.current_book_path)

    def _save_book_summaries(self):
        StorageManager.save_book_summaries(self.current_book_path, self.current_book_summaries)    

    def save_current_progress(self):
        if getattr(self, "current_book_path", "") == "":
            return
        if not hasattr(self, "engine") or not self.engine.chapters_info:
            return
            
        current_idx = getattr(self, "current_chapter_idx", 0)
        if current_idx < 0 or current_idx >= len(self.engine.chapters_info):
            return
            
        title = self.engine.chapters_info[current_idx]['title']
        volume = self.engine.chapters_info[current_idx].get('volume', '')
        offset = getattr(self, "current_scroll_offset", 0.0)
        
        for book in self.bookshelf:
            if book['path'] == self.current_book_path:
                if book.get('last_chapter_idx') == current_idx and book.get('last_scroll_offset') == offset:
                    break
                    
                book['last_chapter_idx'] = current_idx
                book['last_chapter_title'] = title
                book['last_volume_title'] = volume 
                book['last_scroll_offset'] = offset  
                self._save_bookshelf()
                break

    async def _pc_auto_save_task(self):
        if sys.platform == "win32":
            while True:
                await asyncio.sleep(5)
                try:
                    self.save_current_progress()
                except Exception:
                    pass

    def rename_book(self, path, new_name):
        for book in self.bookshelf:
            if book['path'] == path:
                book['name'] = new_name
                break
        self._save_bookshelf()
        self.route_change(None)

    def remove_from_bookshelf(self, path):
        self.bookshelf = [b for b in self.bookshelf if b['path'] != path]
        self._save_bookshelf()
        self.route_change(None)