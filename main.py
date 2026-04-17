import flet as ft
import re
import os
import sys
import urllib.request
import json
import threading
import asyncio
import shutil

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
        self.version = "0.3.6"
        self.author = "手背儿"
        
        self.page.title = f"小说智读 - v{self.version}"
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        
        target_font = "Microsoft YaHei" if sys.platform.startswith("win") else None
        self.page.theme = ft.Theme(
            color_scheme_seed=ft.Colors.BLUE,
            font_family=target_font
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
            "prompt": "# 指令\n请对以下小说章节内容进行深度总结。\n\n# 输出限制\n- 字数控制在300字以内。\n- 严禁评价剧情“好不好看”，只做客观梳理。"
        }
        self.bookshelf = []
        
        self.file_picker = ft.FilePicker(on_result=self.on_file_picked)
        self.export_picker = ft.FilePicker(on_result=self.on_export_picked)
        if hasattr(self.page, "overlay"):
            self.page.overlay.extend([self.file_picker, self.export_picker])
        self.pending_export_path = None

        self._load_config_from_appdata()
        self._load_bookshelf()

        self.main_container = ft.Container(expand=True)
        self.page.add(self.main_container)
        
        self.build_home_view()
            
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
        new_snack = ft.SnackBar(content=ft.Text(msg), key=f"snack_{self.snack_counter}")
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
        
        # 仅在移动端调用全屏隐藏状态栏
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
            base_dir = os.path.join(os.path.expanduser("~"), ".novelreaderapp")
        
        if not os.path.exists(base_dir):
            try: os.makedirs(base_dir)
            except Exception: pass
        return base_dir

    def _get_config_path(self):
        return os.path.join(self._get_base_dir(), "ai_config.json")

    def _get_bookshelf_path(self):
        return os.path.join(self._get_base_dir(), "bookshelf.json")

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

        def on_export(e):
            self._close_dialog()
            self.trigger_export_picker(path, current_name)

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

        plus_side = ft.border.BorderSide(2, ft.Colors.BLUE)
        plus_border = ft.border.Border(top=plus_side, bottom=plus_side, left=plus_side, right=plus_side)
        
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
            card_side = ft.border.BorderSide(1, "outlineVariant")
            card_border = ft.border.Border(top=card_side, bottom=card_side, left=card_side, right=card_side)

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
    # 纯净 0.84 FilePicker 原生挂载调用 (含移动端持久化转存)
    # ==========================
    def trigger_file_picker(self, e):
        try:
            self.file_picker.pick_files(allowed_extensions=["txt"])
        except Exception as ex:
            self.show_snack_bar(f"唤起文件管理器失败: {str(ex)}")

    # <--- 核心修正 1：移除事件参数的类型提示 --->
    def on_file_picked(self, e):
        try:
            if e.files and len(e.files) > 0:
                picked_path = e.files[0].path
                original_name = e.files[0].name
                
                # 有些安卓机型严格沙盒下可能会丢掉路径，增加一次拦截保护
                if not picked_path:
                    self.show_snack_bar("获取文件路径失败，请尝试换一个目录或系统文件管理器导入。")
                    return

                if picked_path.lower().endswith('.txt'):
                    # 1. 在 App 的私有数据目录下创建一个专用的 books 文件夹
                    books_dir = os.path.join(self._get_base_dir(), "books")
                    if not os.path.exists(books_dir):
                        try: os.makedirs(books_dir)
                        except Exception: pass

                    # 2. 拼接出安全的、绝对不会被系统自动删除的持久化路径
                    persistent_path = os.path.join(books_dir, original_name)

                    # 3. 将系统的临时缓存文件，强行拷贝到我们的持久化目录中
                    try:
                        shutil.copy2(picked_path, persistent_path)
                    except Exception as copy_ex:
                        self.show_snack_bar(f"文件转存失败: {str(copy_ex)}")
                        return

                    # 4. 让引擎去解析我们持久化目录下的文件
                    self.start_parsing(persistent_path)
                else:
                    self.show_snack_bar("仅支持 TXT 文本文件")
        except Exception as ex:
            self.show_snack_bar(f"文件处理发生异常: {str(ex)}")

    def trigger_export_picker(self, src_path, default_name):
        try:
            if not os.path.exists(src_path):
                self.show_snack_bar("⚠️ 源文件已丢失，无法导出")
                return
            self.pending_export_path = src_path
            self.export_picker.save_file(allowed_extensions=["txt"], file_name=f"{default_name}.txt")
        except Exception as ex:
            self.show_snack_bar(f"唤起导出面板失败: {str(ex)}")

    # <--- 核心修正 2：移除事件参数的类型提示 --->
    def on_export_picked(self, e):
        if e.path and getattr(self, "pending_export_path", None):
            try:
                shutil.copy2(self.pending_export_path, e.path)
                self.show_snack_bar("✅ 书籍导出成功")
            except Exception as ex:
                self.show_snack_bar(f"导出失败: {str(ex)}")
            self.pending_export_path = None

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

        self.build_reader_view()

        i