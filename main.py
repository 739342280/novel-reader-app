import flet as ft
import re
import os
import sys
import urllib.request
import urllib.error
import json
import threading
import asyncio
import shutil
import time  
import hashlib
from datetime import datetime

# ==========================================
# 核心引擎 (NovelEngine) - 100% 完美复用
# ==========================================
class NovelEngine:
    def __init__(self):
        self.full_text_content = ""
        self.chapters_info = []
    
    def load_and_analyze(self, path, progress_callback=None):
        content = None
        for enc in ['utf-8', 'gbk', 'gb18030']:
            try:
                with open(path, 'r', encoding=enc) as f: 
                    content = f.read()
                    break
            except: continue
            
        if not content:
            raise ValueError("编码解析失败，请检查文件格式。")
            
        self.full_text_content = content
        if progress_callback: progress_callback(0.1, "读取完成，开始正则匹配...")

        chap_pattern = re.compile(r'^\s*(?:第\s*[0-9零一二三四五六七八九十百千万]+\s*[章卷部]|卷\s*[0-9零一二三四五六七八九十百千万]+).*$', re.MULTILINE)
        chaps = list(chap_pattern.finditer(content))
        
        self.chapters_info = []
        total_chaps = len(chaps)
        
        if total_chaps == 0:
            self.chapters_info.append({'start': 0, 'end': len(content), 'title': "正文 (全文无章节)"})
        else:
            for i, m in enumerate(chaps):
                title, start = m.group().strip(), m.start()
                end = chaps[i+1].start() if i+1 < len(chaps) else len(content)
                self.chapters_info.append({'start': start, 'end': end, 'title': title})
                
                if progress_callback and i % 1000 == 0:
                    progress_callback(0.1 + (i/total_chaps)*0.8, f"分析中: {title}")

        if progress_callback: progress_callback(1.0, "分析完毕。")
        return self.chapters_info

    def get_chapter_text(self, idx):
        if not self.chapters_info or idx < 0 or idx >= len(self.chapters_info):
            return ""
        ch = self.chapters_info[idx]
        return self.full_text_content[ch['start']:ch['end']]


# ==========================================
# 表现层 (Flet UI) - 适配 0.84.0 原生规范
# ==========================================
class NovelReaderApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.version = "0.3.13"  
        self.author = "手背儿"
        
        self.page.title = f"小说智读 - v{self.version}"
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        
        target_font = "Microsoft YaHei" if sys.platform.startswith("win") else None
        self.page.theme = ft.Theme(
            color_scheme_seed=ft.Colors.BLUE,
            font_family=target_font,
            scrollbar_theme=ft.ScrollbarTheme(
                thumb_visibility=False,         
                thumb_color=ft.Colors.OUTLINE_VARIANT
            )
        ) 
        self.page.padding = 0
        
        self.engine = NovelEngine()
        
        self.current_book_path = ""
        self.current_book_name = ""
        self.current_chapter_idx = 0
        self.font_size = 18
        self.line_height = 1.5           
        self.paragraph_spacing = 10      
        self.filtered_toc_mapping = []
        self.last_search_query = None  
        self.is_immersive = False  

        self.global_dialog = ft.AlertDialog(title=ft.Text(""))
        self.snack_counter = 0  

        self.ai_config = {
            "url": "https://api.deepseek.com/v1/chat/completions",
            "key": "",
            "model": "deepseek-chat",
            "prompt": (
                "请对以下小说章节内容进行深度总结。\n\n"
                "# 角色设定\n"
                "你是一个细心的“追文助手”，擅长捕捉作者的文字留白和情绪张力。\n\n"
                "# 总结维度\n"
                "1. **一句话概括**：用一句话说清这章讲了什么。\n"
                "2. **情节脉络**：\n"
                "   - 起因：\n"
                "   - 经过（转折点）：\n"
                "   - 结果：\n"
                "3. **人物弧光**：主角在这一章的心态变化曲线（例如：从愤怒 -> 冷静 -> 下定决心）。\n"
                "4. **文笔赏析**：指出本章最精彩的一句描写或对话。\n"
                "5. **悬疑/钩子**：本章结尾留下的悬念是什么？\n\n"
                "# 输出限制\n"
                "- 字数控制在300字以内。\n"
                "- 严禁评价剧情“好不好看”，只做客观梳理。"
            )
        }
        self.bookshelf = []
        self.current_book_summaries = {}

        self._load_config_from_appdata()
        self._load_bookshelf()

        self.main_container = ft.Container(expand=True)
        self.page.add(self.main_container)
        
        self.page.run_task(self._update_clock_task)

        self.build_home_view()

    async def _update_clock_task(self):
        while True:
            if hasattr(self, "info_time") and getattr(self.info_time, "page", None):
                now_str = datetime.now().strftime("%H:%M")
                if self.info_time.value != now_str:
                    self.info_time.value = now_str
                    try:
                        self.info_time.update()
                    except Exception:
                        pass
            await asyncio.sleep(5)
            
    # ==========================
    # 终极弹窗与抽屉调度器
    # ==========================
    def _universal_open(self, control):
        if hasattr(self.page, "overlay") and control not in self.page.overlay:
            self.page.overlay.append(control)

        try: control.open = True
        except Exception: pass

        if hasattr(self.page, "open") and callable(getattr(self.page, "open")):
            try: self.page.open(control)
            except Exception: pass

        try:
            if control.page: control.update()
        except Exception: pass
        self.page.update()

    def _universal_close(self, control):
        try: control.open = False
        except Exception: pass

        if hasattr(self.page, "close") and callable(getattr(self.page, "close")):
            try: self.page.close(control)
            except Exception: pass

        try:
            if control.page: control.update()
        except Exception: pass
        self.page.update()

    def show_snack_bar(self, msg):
        self.snack_counter += 1
        
        toast_ui = ft.Container(
            content=ft.Text(msg, color=ft.Colors.ON_INVERSE_SURFACE),
            bgcolor=ft.Colors.INVERSE_SURFACE,
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            border_radius=8,
        )
        
        new_snack = ft.SnackBar(
            content=ft.Row([toast_ui], alignment=ft.MainAxisAlignment.START), 
            behavior=ft.SnackBarBehavior.FLOATING,
            bgcolor=ft.Colors.TRANSPARENT,  
            elevation=0,                    
            padding=0,                      
            duration=1200,                  
            key=f"snack_{self.snack_counter}"
        )
        self._universal_open(new_snack)

    def _open_dialog(self):
        self._universal_open(self.global_dialog)

    def _close_dialog(self):
        self._universal_close(self.global_dialog)

    def _open_toc_sheet(self, e=None):
        self._universal_open(self.toc_sheet)
        self.page.run_task(self._delayed_scroll_to_chapter, self.current_chapter_idx, 0.3)

    def _close_toc_sheet(self, e=None):
        self._universal_close(self.toc_sheet)

    def _open_settings_sheet(self, e=None):
        self._universal_open(self.settings_sheet)

    def _close_settings_sheet(self, e=None):
        self._universal_close(self.settings_sheet)

    def toggle_immersive(self, e=None):
        self.is_immersive = not getattr(self, "is_immersive", False)
        
        platform_str = str(self.page.platform).lower()
        if "android" in platform_str or "ios" in platform_str:
            try:
                self.page.window.full_screen = self.is_immersive
            except Exception:
                pass
                
        if hasattr(self, "reader_top_bar"):
            self.reader_top_bar.offset = ft.Offset(0, -1) if self.is_immersive else ft.Offset(0, 0)
            self.reader_top_bar.update()

        if hasattr(self, "reader_bottom_bar"):
            self.reader_bottom_bar.offset = ft.Offset(0, 1) if self.is_immersive else ft.Offset(0, 0)
            self.reader_bottom_bar.update()
            
        self.page.update()

    # ==========================
    # 数据存取逻辑
    # ==========================
    def _get_base_dir(self):
        if sys.platform.startswith("win"):
            appdata = os.getenv('APPDATA')
            if not appdata:
                appdata = os.path.expanduser("~")
            base_dir = os.path.join(appdata, "NovelReaderApp")
        else:
            home_dir = os.path.expanduser("~")
            current_dir = os.path.abspath(os.path.dirname(__file__))
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
                try: 
                    os.makedirs(base_dir, exist_ok=True)
                except Exception: 
                    pass
        return base_dir

    def _get_config_path(self):
        return os.path.join(self._get_base_dir(), "ai_config.json")

    def _get_bookshelf_path(self):
        return os.path.join(self._get_base_dir(), "bookshelf.json")

    def _get_summaries_dir(self):
        path = os.path.join(self._get_base_dir(), "ai_summaries")
        if not os.path.exists(path):
            try: os.makedirs(path, exist_ok=True)
            except Exception: pass
        return path

    def _get_current_book_summary_path(self):
        if not self.current_book_path:
            return ""
        path_hash = hashlib.md5(self.current_book_path.encode('utf-8')).hexdigest()
        return os.path.join(self._get_summaries_dir(), f"{path_hash}.json")

    def _load_config_from_appdata(self):
        path = self._get_config_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k in ["url", "key", "model", "prompt"]:
                        if k in data: self.ai_config[k] = data[k]
            except Exception: pass

    def _save_config_to_appdata(self):
        path = self._get_config_path()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.ai_config, f, ensure_ascii=False, indent=4)
        except Exception as e: print(f"保存配置失败: {e}")

    def _load_bookshelf(self):
        path = self._get_bookshelf_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.bookshelf = json.load(f)
            except Exception:
                self.bookshelf = []

    def _save_bookshelf(self):
        path = self._get_bookshelf_path()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.bookshelf, f, ensure_ascii=False, indent=4)
        except Exception as e: print(f"保存书架失败: {e}")

    def _load_book_summaries(self):
        self.current_book_summaries = {}
        path = self._get_current_book_summary_path()
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.current_book_summaries = json.load(f)
            except Exception: pass

    def _save_book_summaries(self):
        path = self._get_current_book_summary_path()
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(self.current_book_summaries, f, ensure_ascii=False, indent=4)
            except Exception as e: 
                pass

    def _execute_copy(self, text):
        try:
            if hasattr(self.page, "set_clipboard"):
                self.page.set_clipboard(text)
        except Exception:
            pass
            
        if sys.platform.startswith("win"):
            try:
                import subprocess
                subprocess.run(['clip.exe'], input=text, text=True, check=True)
            except Exception:
                pass

    def _find_valid_chapter(self, start_idx, step=1):
        idx = start_idx
        while 0 <= idx < len(self.engine.chapters_info):
            ch_info = self.engine.chapters_info[idx]
            text = self.engine.get_chapter_text(idx).strip()
            title = ch_info['title'].strip()
            content_only = text.replace(title, "", 1).strip()
            if len(content_only) > 15:
                return idx
            idx += step
        return -1

    # ==========================
    # 视图：书架首页
    # ==========================
    def build_home_view(self):
        header = ft.Container(
            content=ft.Row([
                ft.Text("📚 我的书架", size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
                ft.Container(expand=True),
                ft.IconButton(icon=ft.Icons.SETTINGS, tooltip="AI设置", on_click=self.show_settings_dialog),
                ft.IconButton(icon=ft.Icons.HISTORY, tooltip="更新日志", on_click=self.show_changelog_dialog),
            ]),
            padding=ft.Padding(left=30, top=20, right=30, bottom=10)
        )

        self.bookshelf_grid = ft.GridView(
            expand=True,
            max_extent=170,           
            child_aspect_ratio=0.72,  
            spacing=20,
            run_spacing=20,
            padding=30
        )
        
        self.status_text = ft.Text("等待导入...", size=12, color=ft.Colors.GREY_500, visible=False)
        self.progress_bar = ft.ProgressBar(width=400, value=0, visible=False)
        status_area = ft.Column([self.status_text, self.progress_bar], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        self.home_view = ft.Column([
            header,
            self.bookshelf_grid,
            ft.Container(status_area, alignment=ft.Alignment(0, 0), padding=10)
        ], expand=True)

        self.refresh_bookshelf_ui()
        self.main_container.content = self.home_view
        self.page.update()

    def show_book_options_dialog(self, path, current_name):
        self.global_dialog.modal = False
        self.global_dialog.inset_padding = None
        self.global_dialog.content_padding = None
        
        rename_tf = ft.TextField(label="重命名书籍", value=current_name)

        def on_save(e):
            new_name = rename_tf.value.strip()
            if new_name and new_name != current_name:
                self.rename_book(path, new_name)
                self.show_snack_bar("✅ 书名已更新")
            self._close_dialog()

        def confirm_delete(e):
            self.remove_from_bookshelf(path)
            self._close_dialog()
            self.show_snack_bar(f"✅ 《{current_name}》已移出书架")

        async def on_export(e):
            self._close_dialog()
            await self.trigger_export_picker(path, current_name)

        export_btn = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.DOWNLOAD), ft.Text("导出书籍到本地")], alignment=ft.MainAxisAlignment.CENTER),
            on_click=on_export,
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_50, color=ft.Colors.BLUE_900)
        )

        self.global_dialog.title = ft.Text("书籍管理")
        self.global_dialog.content = ft.Column([
            rename_tf,
            ft.Container(height=5),
            export_btn,
            ft.Container(height=5),
            ft.Text("注：移出书架不会删除原文件，导出则会另存一份副本", size=12, color=ft.Colors.GREY)
        ], tight=True) 
        
        self.global_dialog.actions = [
            ft.Button(content=ft.Text("保存名称"), on_click=on_save),
            ft.Button(content=ft.Text("移出书架"), style=ft.ButtonStyle(color=ft.Colors.RED), on_click=confirm_delete),
            ft.Button(content=ft.Text("取消"), on_click=lambda _: self._close_dialog())
        ]
        self._open_dialog()

    def rename_book(self, path, new_name):
        for book in self.bookshelf:
            if book['path'] == path:
                book['name'] = new_name
                break
        self._save_bookshelf()
        self.refresh_bookshelf_ui()

    def refresh_bookshelf_ui(self):
        self.bookshelf_grid.controls.clear()

        plus_side = ft.BorderSide(2, ft.Colors.BLUE)
        plus_border = ft.Border(top=plus_side, bottom=plus_side, left=plus_side, right=plus_side)
        
        plus_card = ft.Container(
            alignment=ft.Alignment(0, 0),
            content=ft.Container(
                width=160, height=220, 
                border=plus_border,
                bgcolor="surface",
                ink=True,
                on_click=self.trigger_file_picker, 
                content=ft.Column([
                    ft.Icon(ft.Icons.ADD, size=48, color=ft.Colors.BLUE),
                    ft.Text("导入本地TXT", size=13, color=ft.Colors.GREY)
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            )
        )
        self.bookshelf_grid.controls.append(plus_card)

        for book in self.bookshelf:
            card_side = ft.BorderSide(1, "outlineVariant")
            card_border = ft.Border(top=card_side, bottom=card_side, left=card_side, right=card_side)

            card = ft.Container(
                alignment=ft.Alignment(0, 0),
                content=ft.GestureDetector(
                    on_tap=lambda e, p=book['path']: self.check_and_load_book(p),
                    on_long_press=lambda e, p=book['path'], n=book['name']: self.show_book_options_dialog(p, n),
                    content=ft.Stack([
                        ft.Container(width=160, height=220, border_radius=0, bgcolor="surface", border=card_border), 
                        ft.Container(width=14, height=218, left=1, top=1, bgcolor=ft.Colors.BLUE_700),
                        ft.Container(width=2, height=218, left=15, top=1, bgcolor=ft.Colors.BLUE_900),
                        ft.Column([
                            ft.Text(book['name'], weight=ft.FontWeight.BOLD, size=15, color=ft.Colors.BLUE),
                            ft.Text(book.get('last_chapter_title', '未读'), size=12, color=ft.Colors.GREY, max_lines=2)
                        ], left=30, top=20, width=120)
                    ])
                )
            )
            self.bookshelf_grid.controls.append(card)
        self.page.update()

    def remove_from_bookshelf(self, path):
        self.bookshelf = [b for b in self.bookshelf if b['path'] != path]
        self._save_bookshelf()
        self.refresh_bookshelf_ui()

    def check_and_load_book(self, path):
        if not os.path.exists(path):
            self.show_snack_bar("文件丢失，可能已被移动或删除，将自动移出书架。")
            self.remove_from_bookshelf(path)
            return
        self.start_parsing(path)

    # ==========================
    # 文件选择与导出逻辑 
    # ==========================
    async def trigger_file_picker(self, e):
        try:
            files = await ft.FilePicker().pick_files(
                file_type=ft.FilePickerFileType.CUSTOM, 
                allowed_extensions=["txt"]
            )
            
            if files and len(files) > 0:
                picked_path = files[0].path
                original_name = files[0].name
                
                if not picked_path:
                    self.show_snack_bar("获取文件路径失败，请尝试换一个目录或系统文件管理器导入。")
                    return

                if picked_path.lower().endswith('.txt'):
                    books_dir = os.path.join(self._get_base_dir(), "books")
                    
                    if not os.path.exists(books_dir):
                        try: 
                            os.makedirs(books_dir, exist_ok=True)
                        except Exception as create_ex:
                            self.show_snack_bar(f"建立书籍存放目录失败，请检查应用存储权限: {str(create_ex)}")
                            return

                    persistent_path = os.path.join(books_dir, original_name)

                    try:
                        shutil.copy2(picked_path, persistent_path)
                    except Exception as copy_ex:
                        self.show_snack_bar(f"文件转存失败: {str(copy_ex)}")
                        return

                    self.start_parsing(persistent_path)
                else:
                    self.show_snack_bar("仅支持 TXT 文本文件")
        except Exception as ex:
            self.show_snack_bar(f"唤起文件管理器失败: {str(ex)}")

    async def trigger_export_picker(self, src_path, default_name):
        try:
            if not os.path.exists(src_path):
                self.show_snack_bar("⚠️ 源文件已丢失，无法导出")
                return
            
            saved_path = await ft.FilePicker().save_file(
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["txt"], 
                file_name=f"{default_name}.txt"
            )
            
            if saved_path:
                try:
                    shutil.copy2(src_path, saved_path)
                    self.show_snack_bar("✅ 书籍导出成功")
                except Exception as ex:
                    self.show_snack_bar(f"导出失败: {str(ex)}")
        except Exception as ex:
            self.show_snack_bar(f"唤起导出面板失败: {str(ex)}")

    def _sync_progress(self, progress, msg):
        self.progress_bar.value = progress
        self.status_text.value = msg
        self.page.update()

    def start_parsing(self, path):
        self.current_book_path = path
        
        custom_name = os.path.splitext(os.path.basename(path))[0]
        for b in self.bookshelf:
            if b['path'] == path:
                custom_name = b.get('name', custom_name)
                break
        self.current_book_name = custom_name
        
        self.status_text.visible = True
        self.progress_bar.visible = True
        self.progress_bar.value = 0
        self.page.update()
        
        def task():
            try:
                self.engine.load_and_analyze(path, self._sync_progress)
                self.on_parse_success()
            except Exception as e:
                self.show_snack_bar(f"解析失败: {str(e)}")
                self.status_text.visible = False
                self.progress_bar.visible = False
                self.page.update()
                
        threading.Thread(target=task, daemon=True).start()

    def on_parse_success(self):
        self.status_text.visible = False
        self.progress_bar.visible = False
        
        target_idx = -1
        book_exists = False
        for book in self.bookshelf:
            if book['path'] == self.current_book_path:
                book_exists = True
                target_idx = book.get('last_chapter_idx', -1)
                break

        if not book_exists:
            self.bookshelf.insert(0, {
                "name": self.current_book_name,
                "path": self.current_book_path,
                "last_chapter_idx": 0,
                "last_chapter_title": "未读"
            })
            self._save_bookshelf()
            
        self._load_book_summaries()

        self.build_reader_view()

        if target_idx != -1 and target_idx < len(self.engine.chapters_info):
            self.load_chapter(target_idx)
        else:
            valid_idx = self._find_valid_chapter(0, 1)
            self.load_chapter(valid_idx if valid_idx != -1 else 0)

    # ==========================================
    # 视图：阅读沉浸页面
    # ==========================================
    def build_reader_view(self):
        self.last_search_query = None

        self.search_tf = ft.TextField(label="搜索章节", height=40, on_change=self.filter_toc)
        self.toc_listview = ft.ListView(expand=True, spacing=2, key="toc_listview")
        
        self.toc_sheet = ft.BottomSheet(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("📚 章节目录", size=20, weight=ft.FontWeight.BOLD),
                    self.search_tf, 
                    self.toc_listview
                ], expand=True),
                padding=20,
                height=self.page.height * 0.7 if self.page.height else 600
            )
        )

        self.font_size_text = ft.Text(str(self.font_size), weight=ft.FontWeight.BOLD)
        self.line_height_text = ft.Text(f"{self.line_height:.1f}", weight=ft.FontWeight.BOLD)
        self.para_spacing_text = ft.Text(str(self.paragraph_spacing), weight=ft.FontWeight.BOLD)

        copy_btn = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.COPY), ft.Text("复制本章内容")], alignment=ft.MainAxisAlignment.CENTER),
            on_click=self.copy_current,
            style=ft.ButtonStyle(bgcolor="surface")
        )

        self.settings_sheet = ft.BottomSheet(
            content=ft.Container(
                padding=25,
                content=ft.Column([
                    ft.Text("排版与操作", size=20, weight=ft.FontWeight.BOLD),
                    ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                    ft.Row([
                        ft.Text("字号:", width=50), 
                        ft.IconButton(icon=ft.Icons.REMOVE, on_click=lambda _: self.change_font(-1)),
                        self.font_size_text,
                        ft.IconButton(icon=ft.Icons.ADD, on_click=lambda _: self.change_font(1)),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([
                        ft.Text("行距:", width=50), 
                        ft.IconButton(icon=ft.Icons.REMOVE, on_click=lambda _: self.change_line_height(-0.1)),
                        self.line_height_text,
                        ft.IconButton(icon=ft.Icons.ADD, on_click=lambda _: self.change_line_height(0.1)),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([
                        ft.Text("段距:", width=50), 
                        ft.IconButton(icon=ft.Icons.REMOVE, on_click=lambda _: self.change_paragraph_spacing(-5)),
                        self.para_spacing_text,
                        ft.IconButton(icon=ft.Icons.ADD, on_click=lambda _: self.change_paragraph_spacing(5)),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                    copy_btn 
                ], tight=True)
            )
        )

        self.top_bar_book_name = ft.Text(self.current_book_name, size=13, color=ft.Colors.GREY_500, overflow=ft.TextOverflow.ELLIPSIS)
        self.top_bar_chapter_name = ft.Text("", size=17, weight=ft.FontWeight.BOLD, overflow=ft.TextOverflow.ELLIPSIS)

        self.reader_top_bar = ft.Container(
            top=0, left=0, right=0,
            content=ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=self.go_back_home),
                ft.Column([
                    self.top_bar_book_name,
                    self.top_bar_chapter_name
                ], expand=True, spacing=2, horizontal_alignment=ft.CrossAxisAlignment.START, alignment=ft.MainAxisAlignment.CENTER),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding(top=40, left=10, right=10, bottom=10),
            bgcolor="surface",
            shadow=ft.BoxShadow(blur_radius=8, color="#40000000", offset=ft.Offset(0, 2)), 
            offset=ft.Offset(0, 0),
            animate_offset=ft.Animation(300, ft.AnimationCurve.DECELERATE)
        )

        self.info_chapter_name = ft.Text("", size=12, color=ft.Colors.GREY_500, expand=True, overflow=ft.TextOverflow.ELLIPSIS)
        self.info_time = ft.Text(datetime.now().strftime("%H:%M"), size=12, color=ft.Colors.GREY_500)
        
        self.info_bar = ft.Container(
            content=ft.Row([self.info_chapter_name, self.info_time], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=ft.Padding(left=20, right=20, top=10, bottom=0),
            on_click=self.toggle_immersive,
            bgcolor=ft.Colors.TRANSPARENT
        )

        self.text_panel = ft.Container(
            padding=ft.Padding(left=20, right=4, top=5, bottom=20),
            on_click=self.toggle_immersive, 
            bgcolor=ft.Colors.TRANSPARENT,
            expand=True
        )

        self.reading_base_layer = ft.Container(
            top=0, bottom=0, left=0, right=0,
            bgcolor=ft.Colors.TRANSPARENT,
            content=ft.Column([
                self.info_bar,
                self.text_panel
            ], spacing=0)
        )

        self.reader_bottom_bar = ft.Container(
            bottom=0, left=0, right=0,
            padding=10, 
            bgcolor="surface",
            shadow=ft.BoxShadow(blur_radius=8, color="#40000000", offset=ft.Offset(0, -2)), 
            content=ft.Column([
                ft.Row([
                    self._btn_prev(),
                    self._btn_next()
                ], alignment=ft.MainAxisAlignment.SPACE_AROUND),
                
                ft.Row([
                    ft.Button(
                        content=ft.Text("目录"), 
                        icon=ft.Icons.MENU_BOOK, 
                        on_click=self._open_toc_sheet,
                        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=12))
                    ),
                    ft.Button(
                        content=ft.Text("AI总结"), 
                        icon=ft.Icons.AUTO_AWESOME, 
                        on_click=self.show_ai_dialog, 
                        style=ft.ButtonStyle(
                            color=ft.Colors.WHITE, 
                            bgcolor=ft.Colors.DEEP_PURPLE_400,
                            padding=ft.Padding.symmetric(horizontal=12) 
                        )
                    ),
                    ft.Button(
                        content=ft.Text("界面"), 
                        icon=ft.Icons.FORMAT_SIZE, 
                        on_click=self._open_settings_sheet,
                        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=12))
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_AROUND)
            ], tight=True, spacing=10),
            offset=ft.Offset(0, 0),
            animate_offset=ft.Animation(300, ft.AnimationCurve.DECELERATE)
        )

        self.reader_view = ft.Stack([
            self.reading_base_layer,  
            self.reader_top_bar,
            self.reader_bottom_bar
        ], expand=True, key="reader_view_main_stack")
        
        self.main_container.content = self.reader_view
        self.page.update()

    def _btn_prev(self):
        self.btn_prev = ft.Button(
            content=ft.Text("上一章"), 
            icon=ft.Icons.NAVIGATE_BEFORE, 
            on_click=self.load_prev,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=12))
        )
        return self.btn_prev

    def _btn_next(self):
        self.btn_next = ft.Button(
            content=ft.Text("下一章"), 
            icon=ft.Icons.NAVIGATE_NEXT, 
            on_click=self.load_next,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=12))
        )
        return self.btn_next

    def go_back_home(self, e):
        if getattr(self, "is_immersive", False):
            self.toggle_immersive(None)
            
        self.main_container.content = self.home_view
        self.page.update()
        
        self.refresh_bookshelf_ui()

    def filter_toc(self, e=None):
        if e is not None and getattr(e, "name", "") != "change":
            return

        query = self.search_tf.value.lower() if self.search_tf.value else ""
        
        if getattr(self, "last_search_query", None) == query:
            return 
        self.last_search_query = query
        
        new_controls = []
        new_mapping = []
        for i, ch in enumerate(self.engine.chapters_info):
            if query in ch['title'].lower():
                def make_click(idx):
                    def click_handler(e):
                        self._close_toc_sheet()
                        self.load_chapter(idx)
                    return click_handler
                
                color = ft.Colors.BLUE if i == self.current_chapter_idx else None
                item = ft.Container(
                    key=f"toc_{i}", 
                    content=ft.Text(ch['title'], color=color),
                    padding=10, border_radius=5,
                    height=42, 
                    ink=True, on_click=make_click(i)
                )
                new_controls.append(item)
                new_mapping.append(i)
        
        self.toc_listview.controls.clear()
        self.toc_listview.controls.extend(new_controls)
        self.filtered_toc_mapping = new_mapping
        self.page.update()

    def _update_toc_highlight(self):
        for i, idx in enumerate(self.filtered_toc_mapping):
            if i < len(self.toc_listview.controls):
                try:
                    text_ctrl = self.toc_listview.controls[i].content
                    expected_color = ft.Colors.BLUE if idx == self.current_chapter_idx else None
                    if text_ctrl.color != expected_color:
                        text_ctrl.color = expected_color
                        text_ctrl.update()
                except Exception:
                    pass

    async def _delayed_scroll_to_chapter(self, idx, delay=0.1):
        display_idx = -1
        try:
            display_idx = self.filtered_toc_mapping.index(idx)
        except ValueError:
            pass
            
        if display_idx != -1:
            await asyncio.sleep(delay) 
            try:
                calculated_offset = display_idx * 44
                await self.toc_listview.scroll_to(offset=calculated_offset, duration=300)
            except Exception:
                pass

    def load_chapter(self, idx):
        if not self.engine.chapters_info: return
        self.current_chapter_idx = idx
        
        ch_info = self.engine.chapters_info[idx]
        title = ch_info['title']
        text = self.engine.get_chapter_text(idx)

        if hasattr(self, "top_bar_chapter_name"):
            self.top_bar_chapter_name.value = title
        if hasattr(self, "info_chapter_name"):
            self.info_chapter_name.value = title
        
        paragraphs = [p.rstrip() for p in text.replace('\r', '').split('\n') if p.strip()]
        self.reader_text_controls = [
            ft.Text(
                p, 
                size=self.font_size, 
                style=ft.TextStyle(height=self.line_height) 
            ) 
            for p in paragraphs
        ]

        self.inner_text_col = ft.Column(
            controls=self.reader_text_controls, 
            spacing=self.paragraph_spacing
        )

        self.text_scroll_col = ft.Column(
            controls=[
                ft.Container(
                    content=self.inner_text_col,
                    padding=ft.Padding(left=0, top=0, right=16, bottom=0)
                )
            ],
            expand=True, 
            scroll=ft.ScrollMode.AUTO,
            key="text_scroll_col"
        )
        
        self.text_panel.content = self.text_scroll_col

        prev_valid = self._find_valid_chapter(idx - 1, -1) if idx > 0 else -1
        next_valid = self._find_valid_chapter(idx + 1, 1) if idx < len(self.engine.chapters_info)-1 else -1
        self.btn_prev.disabled = prev_valid == -1
        self.btn_next.disabled = next_valid == -1

        for book in self.bookshelf:
            if book['path'] == self.current_book_path:
                book['last_chapter_idx'] = idx
                book['last_chapter_title'] = title
                self._save_bookshelf()
                break

        if not self.toc_listview.controls:
            self.filter_toc(None) 
        else:
            self._update_toc_highlight()
            
        self.page.update()
        
        self.page.run_task(self._delayed_scroll_to_chapter, idx)

    def load_prev(self, e):
        if self.current_chapter_idx > 0:
            valid_idx = self._find_valid_chapter(self.current_chapter_idx - 1, -1)
            if valid_idx != -1: self.load_chapter(valid_idx)

    def load_next(self, e):
        if self.current_chapter_idx < len(self.engine.chapters_info) - 1:
            valid_idx = self._find_valid_chapter(self.current_chapter_idx + 1, 1)
            if valid_idx != -1: self.load_chapter(valid_idx)

    def change_font(self, delta):
        new_size = self.font_size + delta
        if 12 <= new_size <= 48:
            self.font_size = new_size
            if hasattr(self, "reader_text_controls"):
                for ctrl in self.reader_text_controls:
                    ctrl.size = self.font_size
                    ctrl.update()
            if hasattr(self, "font_size_text"):
                self.font_size_text.value = str(self.font_size)
                self.font_size_text.update()

    def change_line_height(self, delta):
        new_height = round(self.line_height + delta, 1)
        if 1.0 <= new_height <= 3.0:
            self.line_height = new_height
            if hasattr(self, "reader_text_controls"):
                for ctrl in self.reader_text_controls:
                    ctrl.style = ft.TextStyle(height=self.line_height)
                    ctrl.update()
            if hasattr(self, "line_height_text"):
                self.line_height_text.value = f"{self.line_height:.1f}"
                self.line_height_text.update()

    def change_paragraph_spacing(self, delta):
        new_spacing = int(self.paragraph_spacing + delta)
        if 0 <= new_spacing <= 50:
            self.paragraph_spacing = new_spacing
            if hasattr(self, "inner_text_col"):
                self.inner_text_col.spacing = self.paragraph_spacing
                self.inner_text_col.update()
            if hasattr(self, "para_spacing_text"):
                self.para_spacing_text.value = str(self.paragraph_spacing)
                self.para_spacing_text.update()

    async def copy_current(self, e):
        if not self.engine.chapters_info: return
        text = self.engine.get_chapter_text(self.current_chapter_idx)
        self._execute_copy(text)
        self.show_snack_bar("✅ 本章内容已复制到剪贴板")
        try:
            self._close_toc_sheet() 
            self.page.close(self.settings_sheet)
        except Exception:
            pass

    # ==========================
    # 弹窗逻辑
    # ==========================
    def show_settings_dialog(self, e):
        self.global_dialog.modal = False
        self.global_dialog.inset_padding = None
        self.global_dialog.content_padding = None

        url_tf = ft.TextField(label="API URL", value=self.ai_config["url"])
        key_tf = ft.TextField(label="API Key", value=self.ai_config["key"], password=True, can_reveal_password=True)
        model_tf = ft.TextField(label="模型名称", value=self.ai_config["model"])
        prompt_tf = ft.TextField(label="系统提示词", value=self.ai_config["prompt"], multiline=True, min_lines=4, max_lines=6)

        def save(e):
            self.ai_config["url"] = url_tf.value.strip()
            self.ai_config["key"] = key_tf.value.strip()
            self.ai_config["model"] = model_tf.value.strip()
            self.ai_config["prompt"] = prompt_tf.value.strip()
            self._save_config_to_appdata()
            self._close_dialog()
            self.show_snack_bar("✅ AI 配置已持久化保存")

        self.global_dialog.title = ft.Text("⚙️ AI 接口配置")
        self.global_dialog.content = ft.Column([url_tf, key_tf, model_tf, prompt_tf], tight=True)
        self.global_dialog.actions = [
            ft.Button(content=ft.Text("保存并关闭"), on_click=save),
            ft.Button(content=ft.Text("取消"), on_click=lambda _: self._close_dialog())
        ]
        self._open_dialog()

    def show_changelog_dialog(self, e):
        self.global_dialog.modal = False
        self.global_dialog.inset_padding = None
        self.global_dialog.content_padding = ft.Padding(left=20, top=24, right=4, bottom=24)

        log_text = """【v0.3.13】AI交互体验进阶
- AI流式输出视觉优化：针对 Flet 最新渲染架构进行了深度调优。通过多重异步补偿滚动机制，彻底解决了 Markdown 控件因高度重算延迟导致的自动滚动失效问题。无论在 Windows 还是安卓端，新生成的总结文字都能被平滑、实时地追踪呈现。

【v0.3.12】核心存储机制与滚动体验终极优化
- API 请求极度鲁棒化：深度重构了 AI 请求的底层异常捕获机制。现在能够精准剥离并解析大模型返回的深层 JSON 报错（如余额不足、Token失效等），拒绝“哑巴报错”。同时新增了“空数据假死拦截”机制，在极端网络抽风导致 API 返回空流时，能立即终止等待并提示用户，彻底告别无限 Loading 假死现象。
- AI总结持久化存储：引入独立文件存储架构（按书目独立分配 JSON）。实现了 AI 总结内容的永久保存，关闭弹窗或重启应用不再丢失。并通过底层路径 MD5 哈希算法，彻底杜绝了同名书籍导入导致的数据覆盖 Bug。
- 致命数据丢失修复：重构底层存储寻址逻辑，强行跳出 Flet 安卓引擎的“更新自毁”沙盒区。彻底解决应用在跨大版本升级后，导致的本地书架记录、阅读进度以及 AI API Key 配置被系统暴力清空的问题。
- 滚动排版架构重构：全面引入“轨道分离（Track Separation）”技术。通过精密的内外双层边距（Padding）配合，将滚动条与文字在物理图层上彻底隔离。既保持了完美的左右视觉对称，又彻底根除安卓端滚动条遮挡文字的痛点，实现100%无遮挡的沉浸式阅读体验。

【v0.3.11】UI细节与提示框优化
- 提示框重构：将底部提示栏升级为 Material 3 悬浮气泡模式，彻底解决安卓端全面屏手势条导致的异常高度问题。
- 轻提示 (Toast) 视觉升级：采用“透明包裹层+内部独立容器”的设计模式，打破底层框架强制居中的限制，实现了完全靠左对齐且宽度完美自适应文字长度的精致 Toast 轻提示效果。
- 滚动条双端智能适配：移除全局强制粗细限制，PC 端还原宽体以方便鼠标精准拖拽，安卓端恢复原生极细线条以保障沉浸式阅读。

【v0.3.10】UI细节与滚动体验优化
- 滚动条适配：引入智能自适应灰色（ON_SURFACE_VARIANT/OUTLINE_VARIANT）全局滚动条主题，完美契合深浅模式，既保证滑动可见又不抢夺视觉焦点。
- 日志排版优化：更新日志弹窗改用高性能 ListView，解决滚动条遮挡文字问题，并统一下拉交互逻辑。

【v0.3.9】沉浸式阅读与视觉调优
- 视觉沉浸：优化了 AI 总结弹窗的配色方案，去除内部容器生硬的色块，使文本区域与对话框背景完全融合，实现沉浸式视觉效果。
- 空间利用：大幅压缩了 AI 总结弹窗距离手机屏幕左右边缘的默认安全留白，显著加大了水平阅读宽度，提升长文本阅读体验。

【v0.3.8】细节体验与AI指令优化
- 交互重构：全面优化底部菜单为双行布局，将高频操作（目录、界面、AI总结）下放，极大提升手机端单手握持体验。
- 智能排版：重构 AI 总结弹窗的按钮自适应逻辑，完美适配各种窄屏手机，杜绝 UI 溢出和重叠。
- AI 提示词升级：引入结构化的高级提示词，新增“情节脉络”、“人物弧光”、“文笔赏析”等专业追文解析维度。
- 底层稳健：全面适配 Flet 0.84.0 原生大驼峰语法规范，消除了所有废弃 API 警告，安卓端运行更加稳健。

【v0.3.7】修复离线渲染断层 Bug
- 状态同步：修复了在阅读页点击返回主页时，由于 Flet 离线 DOM 更新延迟导致的“两本书”残影 Bug。

【v0.3.6】沉浸式阅读UI革新
- 界面重构：阅读界面摒弃了传统的线性排版，升级为悬浮式交互。点击正文唤出菜单，内容不再上下跳动。

【v0.3.5】阅读排版升级
- 排版优化：新增自定义行距、段距调节功能，彻底释放阅读空间的自由度。
"""
        self.global_dialog.title = ft.Text("历史更新记录")
        
        self.global_dialog.content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Text(log_text, selectable=True),
                        padding=ft.Padding(left=0, top=0, right=16, bottom=0)
                    )
                ], 
                scroll=ft.ScrollMode.AUTO
            ), 
            padding=0,
            height=400, width=500
        )
        self.global_dialog.actions = [ft.Button(content=ft.Text("关闭"), on_click=lambda _: self._close_dialog())]
        self._open_dialog()

    def show_ai_dialog(self, e):
        if not self.engine.chapters_info: return
        
        self.global_dialog.modal = True
        
        target_idx = self.current_chapter_idx
        ch_info = self.engine.chapters_info[target_idx]
        
        existing_summary = self.current_book_summaries.get(str(target_idx), "")
        
        init_text = existing_summary if existing_summary else "点击下方按钮，开始使用 AI 梳理本章节剧情...\n\n*(注意：请确保已在首页设置中配置了 API Key)*"
        btn_text = "🔄 重新总结" if existing_summary else "🚀 总结本章"
        
        result_text = ft.Markdown(init_text, selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB)
        
        ai_scroll_col = ft.Column(
            controls=[
                ft.Container(
                    content=result_text,
                    padding=ft.Padding(left=0, top=0, right=16, bottom=0)
                )
            ], 
            scroll=ft.ScrollMode.AUTO, 
            auto_scroll=False,
            tight=True
        )
        
        btn_start = ft.Button(content=ft.Text(btn_text), style=ft.ButtonStyle(bgcolor=ft.Colors.DEEP_PURPLE_400, color=ft.Colors.WHITE))
        btn_copy = ft.Button(content=ft.Text("📋 复制"), style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_500, color=ft.Colors.WHITE))

        def start_ai(e):
            if not self.ai_config["key"]:
                self.show_snack_bar("⚠️ 请先配置 API Key")
                return
            
            btn_start.disabled = True
            btn_start.content.value = "思考中..."
            result_text.value = "✨ 大模型正在阅读本章并进行多维度梳理，请稍候...\n\n"
            
            try:
                btn_start.update()
                result_text.update()
            except Exception:
                pass

            chapter_text = self.engine.get_chapter_text(target_idx)[:15000]
            
            stream_buffer = [""] 
            is_streaming = [True]

            # 【核心修改点 1】：独立的、不阻塞主线程的异步滚动追踪器
            async def safe_scroll_task():
                # 这个小任务专门负责追踪滚动，独立于 UI 更新主循环
                while is_streaming[0]:
                    if ai_scroll_col.page:
                        try:
                            # 强制跳转末尾指令
                            await ai_scroll_col.scroll_to(offset=-1, duration=0)
                        except: pass
                    await asyncio.sleep(0.1)

            async def ui_updater():
                # 开启独立的滚动追踪任务（Fire-and-forget 模式，不在此等待它）
                self.page.run_task(safe_scroll_task)
                
                last_text = stream_buffer[0]
                try:
                    while is_streaming[0]:
                        current_text = stream_buffer[0]
                        if current_text != last_text:
                            result_text.value = current_text
                            try:
                                result_text.update()
                            except: pass
                            last_text = current_text
                        await asyncio.sleep(0.05) 
                finally:
                    # 【核心修改点 2】：确保状态彻底复位，杜绝点击无反应 Bug
                    if stream_buffer[0] != last_text:
                        result_text.value = stream_buffer[0]
                        try: result_text.update()
                        except: pass
                    
                    try:
                        btn_start.disabled = False
                        btn_start.content.value = "🔄 重新总结"
                        btn_start.update()
                    except: pass

            def fetch():
                is_success = True
                has_real_data = False
                try:
                    req_data = {
                        "model": self.ai_config["model"],
                        "messages": [
                            {"role": "system", "content": self.ai_config["prompt"]},
                            {"role": "user", "content": f"请总结以下内容：\n\n{chapter_text}"}
                        ],
                        "stream": True
                    }
                    req = urllib.request.Request(
                        self.ai_config["url"], 
                        data=json.dumps(req_data).encode("utf-8"), 
                        headers={
                            "Content-Type": "application/json", 
                            "Authorization": f"Bearer {self.ai_config['key']}",
                            "Accept": "text/event-stream" 
                        }, 
                        method="POST"
                    )
                    
                    with urllib.request.urlopen(req, timeout=60) as response:
                        while True:
                            if not getattr(self.global_dialog, "open", False):
                                is_success = False
                                break

                            line = response.readline()
                            if not line:
                                break
                            
                            decoded_line = line.decode("utf-8").strip()
                            if not decoded_line:
                                continue
                                
                            if decoded_line.startswith("data: "):
                                data_str = decoded_line[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data_json = json.loads(data_str)
                                    delta = data_json["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        if not has_real_data:
                                            stream_buffer[0] = ""
                                            has_real_data = True
                                        stream_buffer[0] += delta["content"]
                                except Exception:
                                    pass
                except urllib.error.HTTPError as ex:
                    is_success = False
                    if not has_real_data: stream_buffer[0] = ""
                    error_msg = str(ex)
                    try:
                        error_body = ex.read().decode('utf-8')
                        error_json = json.loads(error_body)
                        if "error" in error_json and "message" in error_json["error"]:
                            error_msg += f"\n详细原因: {error_json['error']['message']}"
                        elif "message" in error_json:
                            error_msg += f"\n详细原因: {error_json['message']}"
                    except: pass
                    stream_buffer[0] += f"\n\n❌ **接口请求失败**: {error_msg}\n\n请检查 API Key 是否填写正确、余额是否充足，或模型名称是否有误。"
                except Exception as ex:
                    is_success = False
                    if not has_real_data: stream_buffer[0] = ""
                    stream_buffer[0] += f"\n\n❌ **网络异常**: {str(ex)}\n\n请检查网络连通性。"
                finally:
                    is_streaming[0] = False
                    if is_success and not has_real_data:
                        is_success = False
                        stream_buffer[0] = "⚠️ 大模型未返回任何有效内容，请稍后重试或检查接口状态。"

                    if is_success and stream_buffer[0]:
                        self.current_book_summaries[str(target_idx)] = stream_buffer[0]
                        self._save_book_summaries()

            self.page.run_task(ui_updater)
            threading.Thread(target=fetch, daemon=True).start()

        async def copy_result(e):
            self._execute_copy(result_text.value)
            self.show_snack_bar("✅ 总结已复制")

            btn_copy.content.value = "✅ 复制成功"
            btn_copy.style = ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE)
            try: btn_copy.update()
            except: pass
            
            await asyncio.sleep(2)
            btn_copy.content.value = "📋 复制"
            btn_copy.style = ft.ButtonStyle(bgcolor=ft.Colors.GREEN_500, color=ft.Colors.WHITE)
            try: btn_copy.update()
            except: pass

        btn_start.on_click = start_ai
        btn_copy.on_click = copy_result

        self.global_dialog.inset_padding = ft.Padding.symmetric(horizontal=12, vertical=24)
        self.global_dialog.content_padding = ft.Padding(left=20, top=15, right=4, bottom=15)
        
        self.global_dialog.title = ft.Text(f"✨ AI 智能总结 - {ch_info['title']}")
        self.global_dialog.content = ft.Container(
            content=ai_scroll_col,
            width=600, height=400, bgcolor=ft.Colors.TRANSPARENT  
        )
        
        self.global_dialog.actions = [
            ft.Container(
                content=ft.Row(
                    controls=[btn_start, btn_copy, ft.Button(content=ft.Text("关闭"), on_click=lambda _: self._close_dialog())],
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                    wrap=True
                ),
                width=600
            )
        ]
        
        self._open_dialog()

def main(page: ft.Page):
    app = NovelReaderApp(page)

if __name__ == "__main__":
    ft.run(main)