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
        
        if os.path.exists(path) and os.path.getsize(path) == 0:
            raise ValueError("文件为空 (0字节)，请检查文件是否完整。")

        encodings = ['utf-8', 'gb18030', 'gbk', 'utf-16', 'utf-16-le', 'utf-16-be']
        for enc in encodings:
            try:
                with open(path, 'r', encoding=enc) as f: 
                    content = f.read()
                    if content:
                        break
            except: 
                continue
                
        if not content:
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except: 
                pass
            
        if not content:
            raise ValueError("编码解析失败，请检查文件格式是否为标准 TXT。")
            
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
        self.version = "0.3.14"  
        self.author = "手背儿"
        
        self.page.title = f"小说智读 - v{self.version}"
        
        self.page.fonts = {
            "思源黑体": "fonts/思源黑体.ttf",
            "思源宋体": "fonts/思源宋体.ttf",
            "汉仪正圆": "fonts/汉仪正圆.ttf",
        }

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
        self.letter_spacing = 0.0  
        self.filtered_toc_mapping = []
        self.last_search_query = None  
        self.is_immersive = False  

        self.bg_color = None
        self.bg_image = None  
        self.reader_text_color = None
        self.font_family = None
        
        self.follow_system_theme = True
        self.manual_theme_mode = "light" 

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
        
        self.page.on_platform_brightness_change = self._on_os_theme_change

        self.main_container = ft.Container(expand=True)
        self.page.add(self.main_container)
        
        self.page.run_task(self._update_clock_task)

        self.build_home_view()

    def _on_os_theme_change(self, e):
        if getattr(self, "follow_system_theme", True):
            self.page.theme_mode = ft.ThemeMode.SYSTEM
            self.sync_theme_btn_ui()
        else:
            if "dark" in getattr(self, "manual_theme_mode", "light"):
                self.page.theme_mode = ft.ThemeMode.DARK
            else:
                self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.update()

    async def _update_clock_task(self):
        while True:
            try:
                if hasattr(self, "info_time"):
                    try:
                        is_mounted = self.info_time.page is not None
                    except RuntimeError:
                        is_mounted = False
                        
                    if is_mounted:
                        now_str = datetime.now().strftime("%H:%M")
                        if self.info_time.value != now_str:
                            self.info_time.value = now_str
                            try:
                                self.info_time.update()
                            except Exception:
                                pass
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
        
        # 【核心尝试】：去除平台检测，全局强行请求沉浸式/全屏模式
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
                    self.bg_color = data.get("bg_color")
                    self.bg_image = data.get("bg_image")  
                    self.reader_text_color = data.get("reader_text_color")
                    self.font_family = data.get("font_family")
                    self.letter_spacing = data.get("letter_spacing", 0.0)
                    
                    self.follow_system_theme = data.get("follow_system_theme", True)
                    self.manual_theme_mode = str(data.get("theme_mode", "light")).lower()
                    
                    if self.follow_system_theme:
                        self.page.theme_mode = ft.ThemeMode.SYSTEM
                    else:
                        if "dark" in self.manual_theme_mode:
                            self.page.theme_mode = ft.ThemeMode.DARK
                        else:
                            self.page.theme_mode = ft.ThemeMode.LIGHT
            except Exception: 
                self.page.theme_mode = ft.ThemeMode.SYSTEM
        else:
            self.page.theme_mode = ft.ThemeMode.SYSTEM

    def _save_config_to_appdata(self):
        path = self._get_config_path()
        data_to_save = self.ai_config.copy()
        data_to_save["bg_color"] = self.bg_color
        data_to_save["bg_image"] = self.bg_image  
        data_to_save["reader_text_color"] = self.reader_text_color
        data_to_save["font_family"] = self.font_family
        data_to_save["letter_spacing"] = self.letter_spacing
        
        data_to_save["follow_system_theme"] = self.follow_system_theme
        
        theme_str = str(self.page.theme_mode).lower()
        if "dark" in theme_str:
            data_to_save["theme_mode"] = "dark"
        elif "light" in theme_str:
            data_to_save["theme_mode"] = "light"
        else:
            data_to_save["theme_mode"] = "system"
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
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

    # ==========================
    # 界面更新函数
    # ==========================
    def update_reader_appearance(self, **kwargs):
        if "bg" in kwargs: self.bg_color = kwargs["bg"]
        if "bg_image" in kwargs: self.bg_image = kwargs["bg_image"]  
        if "text" in kwargs: self.reader_text_color = kwargs["text"]
        if "font" in kwargs: self.font_family = kwargs["font"]
        
        if hasattr(self, "reader_text_controls"):
            for ctrl in self.reader_text_controls:
                ctrl.font_family = self.font_family
                ctrl.color = self.reader_text_color
                ctrl.update()
        
        if hasattr(self, "reading_base_layer"):
            self.reading_base_layer.bgcolor = self.bg_color
            self.reading_base_layer.image = ft.DecorationImage(
                src=self.bg_image,
                repeat="repeat"
            ) if self.bg_image else None
            self.reading_base_layer.update()
        
        self._save_config_to_appdata()

    def _get_is_dark_mode(self):
        if not getattr(self, "follow_system_theme", True):
            return "dark" in getattr(self, "manual_theme_mode", "light")
            
        pb = self.page.platform_brightness
        if pb is None:
            return False 
        return str(pb).lower().endswith("dark")

    def sync_theme_btn_ui(self):
        if not hasattr(self, "theme_btn"): return
        is_dark = self._get_is_dark_mode()
        
        if is_dark:
            self.theme_btn.content.value = "日间"
            self.theme_btn.icon = ft.Icons.LIGHT_MODE
        else:
            self.theme_btn.content.value = "夜间"
            self.theme_btn.icon = ft.Icons.DARK_MODE
            
        try: self.theme_btn.update()
        except: pass

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
        self.letter_spacing_text = ft.Text(f"{self.letter_spacing:.1f}", weight=ft.FontWeight.BOLD)

        def set_bg_preset(bg, text, bg_image=None):
            self.update_reader_appearance(bg=bg, text=text, bg_image=bg_image)

        def set_font_preset(font_name):
            self.update_reader_appearance(font=font_name)

        bg_options = ft.Row([
            ft.IconButton(icon=ft.Icons.BRIGHTNESS_AUTO, tooltip="默认", on_click=lambda _: set_bg_preset(None, None, None)),
            ft.Container(width=30, height=30, bgcolor="#FFFFFF", border_radius=15, tooltip="纯白", on_click=lambda _: set_bg_preset("#FFFFFF", "#212121"), border=ft.Border.all(1, ft.Colors.GREY_400)),
            
            ft.Container(
                width=30, height=30, bgcolor="#B9A080", border_radius=15, tooltip="牛皮纸一", 
                image=ft.DecorationImage(src="backgrounds/牛皮纸_thumb.jpg", fit="cover"),
                on_click=lambda _: set_bg_preset("#B9A080", "#3E2723", "backgrounds/牛皮纸.jpg"), border=ft.Border.all(1, ft.Colors.GREY_400)),
            
            ft.Container(
                width=30, height=30, bgcolor="#D4C4A8", border_radius=15, tooltip="牛皮纸二", 
                image=ft.DecorationImage(src="backgrounds/牛皮纸_thumb2.jpg", fit="cover"),
                on_click=lambda _: set_bg_preset("#D4C4A8", "#3E2723", "backgrounds/牛皮纸2.jpg"), border=ft.Border.all(1, ft.Colors.GREY_400)),
            
            ft.Container(
                width=30, height=30, bgcolor="#E8DCC8", border_radius=15, tooltip="牛皮纸三", 
                image=ft.DecorationImage(src="backgrounds/牛皮纸_thumb3.jpg", fit="cover"),
                on_click=lambda _: set_bg_preset("#E8DCC8", "#3E2723", "backgrounds/牛皮纸3.jpg"), border=ft.Border.all(1, ft.Colors.GREY_400)),
            
            ft.Container(width=30, height=30, bgcolor="#F5F5DC", border_radius=15, tooltip="米黄", on_click=lambda _: set_bg_preset("#F5F5DC", "#3E2723"), border=ft.Border.all(1, ft.Colors.GREY_400)),
            ft.Container(width=30, height=30, bgcolor="#CCE8CF", border_radius=15, tooltip="护眼", on_click=lambda _: set_bg_preset("#CCE8CF", "#1B5E20"), border=ft.Border.all(1, ft.Colors.GREY_400)),
            ft.Container(width=30, height=30, bgcolor="#1A1A1B", border_radius=15, tooltip="夜间", on_click=lambda _: set_bg_preset("#1A1A1B", "#B0B0B0"), border=ft.Border.all(1, ft.Colors.WHITE24)),
        ], alignment=ft.MainAxisAlignment.SPACE_AROUND, scroll=ft.ScrollMode.AUTO)

        font_options = ft.Row([
            ft.TextButton(content=ft.Text("默认", size=15), on_click=lambda _: set_font_preset(None), style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE)),
            ft.TextButton(content=ft.Text("黑体", font_family="思源黑体", size=15), on_click=lambda _: set_font_preset("思源黑体"), style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE)),
            ft.TextButton(content=ft.Text("宋体", font_family="思源宋体", size=15), on_click=lambda _: set_font_preset("思源宋体"), style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE)),
            ft.TextButton(content=ft.Text("正圆", font_family="汉仪正圆", size=15), on_click=lambda _: set_font_preset("汉仪正圆"), style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE)),
        ], alignment=ft.MainAxisAlignment.START, scroll=ft.ScrollMode.AUTO)

        typography_row = ft.Row([
            ft.Column([
                ft.Row([
                    ft.IconButton(icon=ft.Icons.REMOVE, on_click=lambda _: self.change_font(-1), icon_size=20),
                    self.font_size_text,
                    ft.IconButton(icon=ft.Icons.ADD, on_click=lambda _: self.change_font(1), icon_size=20),
                ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
                ft.Text("字号", size=12, color=ft.Colors.GREY_500)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),

            ft.Column([
                ft.Row([
                    ft.IconButton(icon=ft.Icons.LINEAR_SCALE, on_click=lambda _: self.change_letter_spacing(-0.5), icon_size=20, tooltip="字距-"),
                    self.letter_spacing_text,
                    ft.IconButton(icon=ft.Icons.LINEAR_SCALE, on_click=lambda _: self.change_letter_spacing(0.5), icon_size=20, tooltip="字距+"),
                ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
                ft.Text("字距", size=12, color=ft.Colors.GREY_500)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
            
            ft.Column([
                ft.Row([
                    ft.IconButton(icon=ft.Icons.FORMAT_LINE_SPACING, on_click=lambda _: self.change_line_height(-0.1), icon_size=20, tooltip="行距-"),
                    self.line_height_text,
                    ft.IconButton(icon=ft.Icons.FORMAT_LINE_SPACING, on_click=lambda _: self.change_line_height(0.1), icon_size=20, tooltip="行距+"),
                ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
                ft.Text("行距", size=12, color=ft.Colors.GREY_500)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),

            ft.Column([
                ft.Row([
                    ft.IconButton(icon=ft.Icons.VERTICAL_ALIGN_CENTER, on_click=lambda _: self.change_paragraph_spacing(-5), icon_size=20, tooltip="段距-"),
                    self.para_spacing_text,
                    ft.IconButton(icon=ft.Icons.VERTICAL_ALIGN_CENTER, on_click=lambda _: self.change_paragraph_spacing(5), icon_size=20, tooltip="段距+"),
                ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
                ft.Text("段距", size=12, color=ft.Colors.GREY_500)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        def on_system_theme_switch_change(e):
            self.follow_system_theme = e.control.value
            if self.follow_system_theme:
                self.page.theme_mode = ft.ThemeMode.SYSTEM
            else:
                is_dark = str(self.page.platform_brightness).lower().endswith("dark")
                if is_dark:
                    self.page.theme_mode = ft.ThemeMode.DARK
                    self.manual_theme_mode = "dark"
                else:
                    self.page.theme_mode = ft.ThemeMode.LIGHT
                    self.manual_theme_mode = "light"
            self.page.update()
            self.sync_theme_btn_ui()
            self._save_config_to_appdata()

        self.system_theme_switch = ft.Switch(
            value=self.follow_system_theme, 
            on_change=on_system_theme_switch_change,
            active_color=ft.Colors.BLUE,
            scale=0.85 
        )

        theme_switch_row = ft.Row([
            ft.Text("跟随系统主题", size=14, weight=ft.FontWeight.BOLD),
            self.system_theme_switch
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        self.settings_sheet = ft.BottomSheet(
            content=ft.Container(
                padding=12, 
                content=ft.Column([
                    ft.Text("排版调整", size=14, weight=ft.FontWeight.BOLD), 
                    typography_row,
                    
                    ft.Divider(height=6, thickness=0.5), 
                    theme_switch_row,
                    
                    ft.Divider(height=6, thickness=0.5), 
                    ft.Text("阅读背景", size=14, weight=ft.FontWeight.BOLD),
                    bg_options,
                    
                    ft.Divider(height=6, thickness=0.5),
                    ft.Text("字体选择", size=14, weight=ft.FontWeight.BOLD),
                    font_options,

                    ft.Divider(height=6, thickness=0.5),
                    ft.Button(
                        content=ft.Row([ft.Icon(ft.Icons.COPY, size=18), ft.Text("复制本章", size=13)], alignment=ft.MainAxisAlignment.CENTER),
                        on_click=self.copy_current,
                        style=ft.ButtonStyle(bgcolor="surface", color=ft.Colors.ON_SURFACE, padding=10)
                    )
                ], tight=True, scroll=ft.ScrollMode.AUTO, spacing=4) 
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
            bgcolor=self.bg_color, 
            image=ft.DecorationImage(
                src=self.bg_image,
                repeat="repeat"
            ) if self.bg_image else None,
            content=ft.Column([
                self.info_bar,
                self.text_panel
            ], spacing=0)
        )

        def toggle_app_theme(e):
            self.follow_system_theme = False
            if hasattr(self, "system_theme_switch"):
                self.system_theme_switch.value = False
                try: self.system_theme_switch.update()
                except: pass

            is_dark = self._get_is_dark_mode()
            if is_dark:
                self.page.theme_mode = ft.ThemeMode.LIGHT
                self.manual_theme_mode = "light"
            else:
                self.page.theme_mode = ft.ThemeMode.DARK
                self.manual_theme_mode = "dark"
            self.page.update()
            
            self.sync_theme_btn_ui()
            self._save_config_to_appdata()

        self.theme_btn = ft.Button(
            content=ft.Text("日间"), 
            icon=ft.Icons.LIGHT_MODE,
            on_click=toggle_app_theme,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8)) 
        )
        self.sync_theme_btn_ui()

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
                        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8))
                    ),
                    self.theme_btn,
                    ft.Button(
                        content=ft.Text("AI总结"), 
                        icon=ft.Icons.AUTO_AWESOME, 
                        on_click=self.show_ai_dialog, 
                        style=ft.ButtonStyle(
                            color=ft.Colors.WHITE, 
                            bgcolor=ft.Colors.DEEP_PURPLE_400,
                            padding=ft.Padding.symmetric(horizontal=8) 
                        )
                    ),
                    ft.Button(
                        content=ft.Text("界面"), 
                        icon=ft.Icons.FORMAT_SIZE, 
                        on_click=self._open_settings_sheet,
                        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8))
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
                style=ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing),
                font_family=self.font_family, 
                color=self.reader_text_color   
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
                    ctrl.style = ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing)
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

    def change_letter_spacing(self, delta):
        new_spacing = round(self.letter_spacing + delta, 1)
        if 0.0 <= new_spacing <= 10.0:
            self.letter_spacing = new_spacing
            if hasattr(self, "reader_text_controls"):
                for ctrl in self.reader_text_controls:
                    ctrl.style = ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing)
                    ctrl.update()
            if hasattr(self, "letter_spacing_text"):
                self.letter_spacing_text.value = f"{self.letter_spacing:.1f}"
                self.letter_spacing_text.update()

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

        log_text = """【v0.3.14】个性化阅读体验升级
- (修复) 核心逻辑：重构了底层的系统主题状态管理架构。彻底解决了在“跟随系统”关闭状态下，因冷启动时底层 Flet 客户端强制同步导致的“深浅色手动配置被系统强行覆盖”的隐蔽 Bug。目前无论冷/热启动，用户的手动偏好都将如盘石般稳固。
- (新增) 智能系统主题联动：在“界面”设置中重磅推出“跟随系统主题”开关。开启后，阅读器将无缝监听操作系统的深浅色模式切换。
- (优化) 冷热启动状态同步：全面接管 App 的生命周期。增强底层环境嗅探的容错率，彻底防范老旧机型冷启动由于 API 延迟导致的黑屏隐患，保证启动 100% 顺滑。
- 背景预设：新增经典四色背景切换（默认、纸张、护眼、夜间），完美平衡视觉舒适度与审美。
- 字体随心换：重磅引入精选中文字体，支持在设置面板一键无缝切换，提升阅读质感。
- 细致排版：新增文章“字距”微调功能。

【v0.3.13】AI交互体验进阶
- AI流式输出视觉优化：针对 Flet 最新渲染架构进行了深度调优。通过多重异步补偿滚动机制，彻底解决了 Markdown 控件因高度重算延迟导致的自动滚动失效问题。

【v0.3.12】核心存储机制与滚动体验终极优化
- API 请求极度鲁棒化：深度重构了 AI 请求的底层异常捕获机制。
- AI总结持久化存储：实现了 AI 总结内容的永久保存，关闭弹窗或重启应用不再丢失。
- 致命数据丢失修复：重构底层存储寻址逻辑，彻底解决跨版本升级导致的数据清空问题。
- 滚动排版架构重构：全面引入“轨道分离”技术，彻底根除安卓端滚动条遮挡文字的痛点。

【v0.3.11】UI细节与提示框优化
- 提示框重构：将底部提示栏升级为 Material 3 悬浮气泡模式。
- 轻提示 (Toast) 视觉升级：实现了完全靠左对齐且宽度完美自适应文字长度的精致 Toast。
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

            async def safe_scroll_task():
                while is_streaming[0]:
                    try:
                        if ai_scroll_col.page is not None:
                            await ai_scroll_col.scroll_to(offset=-1, duration=0)
                    except Exception:
                        pass
                    await asyncio.sleep(0.1)

            async def ui_updater():
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
                    stream_buffer[0] += f"\n\n❌ **接口请求失败**: {error_msg}\n\n请检查 API Key 是否填写正确、余额是否充足。"
                except Exception as ex:
                    is_success = False
                    if not has_real_data: stream_buffer[0] = ""
                    stream_buffer[0] += f"\n\n❌ **网络异常**: {str(ex)}"
                finally:
                    is_streaming[0] = False
                    if is_success and not has_real_data:
                        is_success = False
                        stream_buffer[0] = "⚠️ 大模型未返回任何有效内容，请稍后重试。"

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
    ft.run(main, assets_dir="assets")