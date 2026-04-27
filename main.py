import flet as ft
import os
import sys
import threading
import asyncio
import shutil
import time  
import zipfile
from datetime import datetime
import traceback
import ctypes  # 【新增】必须导入 ctypes 以调用 Windows 底层 API

from core.engine import NovelEngine
from data.storage import StorageManager
from ui.dialogs import DialogManager
from ui.home_view import get_home_view
from ui.reader_view import get_reader_view

# ==========================================
# 0. 跨平台路径寻址与 DLL 强制注册 (针对 Win11 环境修复)
# ==========================================
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

ASSETS_DIR = os.path.join(application_path, "assets")

if sys.platform == "win32":
    # 1. 解决 Python 引擎寻找主 DLL 的路径限制
    if hasattr(os, "add_dll_directory") and os.path.exists(ASSETS_DIR):
        try:
            os.add_dll_directory(ASSETS_DIR)
        except Exception:
            pass
            
    # 2. 【终极绝杀】利用 llama.cpp 官方预留的环境变量，强行重定向 C++ 底层的搜索路径
    os.environ["GGML_BACKEND_PATH"] = ASSETS_DIR
    
    # 3. 环境变量兜底 (调用 Windows 底层穿透)
    try:
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(ASSETS_DIR)
    except Exception:
        pass
    os.environ["PATH"] = ASSETS_DIR + os.pathsep + os.environ.get("PATH", "")

# --- 【闪退捕兽夹】代码开始 ---
def global_crash_catcher(exctype, value, tb):
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "小说智读_绝密报错日志.txt")
    with open(desktop_path, "w", encoding="utf-8") as f:
        f.write("=== 软件启动崩溃现场 ===\n")
        f.write(error_msg)

sys.excepthook = global_crash_catcher
# --- 【闪退捕兽夹】代码结束 ---

# ==========================================
# 控制器层 (App Controller & Router) 
# ==========================================
class NovelReaderApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.version = "0.4.6"  
        self.author = "手背儿"
        self.page.title = f"小说智读 - v{self.version}"
        
        try:
            self.page.window.icon = "icon.png"
        except Exception: pass

        # --- 1. 全局引擎与 UI 底盘配置 ---
        self.engine = NovelEngine()
        self.page.fonts = {
            "汉仪旗黑": "fonts/汉仪旗黑.ttf",
            "汉仪中宋": "fonts/汉仪中宋.ttf",
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

        # --- 2. 核心业务状态 ---
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

        # --- 3. UI 样式默认配置 ---
        self.font_size = 18
        self.line_height = 1.5           
        self.paragraph_spacing = 10      
        self.letter_spacing = 0.0  
        self.bg_color = "#FFFFFF"
        self.bg_image = None  
        self.reader_text_color = "#212121"
        self.font_family = None
        self.follow_system_theme = True
        self.manual_theme_mode = "light" 

        # --- 4. 弹窗管控 ---
        self.global_dialog = ft.AlertDialog(title=ft.Text(""))
        self.snack_counter = 0
        self._last_dismiss_time = 0
        self.active_dialogs = []  # 💥 新增：自己维护一个弹窗生死簿，不依赖 Flet 延迟的状态  
        
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
            ),
            "embed_mode": "云端 API",
            "embed_url": "https://api.deepseek.com/v1/embeddings",
            "embed_key": "",
            "embed_model": "text-embedding-3-small",
            "local_embed_path": "",
            "top_k": 5
        }

        # --- 5. 生命周期拉起与路由挂载 ---
        self._load_config_from_appdata()
        self._load_bookshelf()
        
        self.page.on_keyboard_event = self._on_keyboard_control
        self.page.on_platform_brightness_change = self._on_os_theme_change
        self.page.on_app_lifecycle_state_change = self._on_app_lifecycle
        self.page.on_route_change = self.route_change
        self.page.on_view_pop = self.view_pop

        self.page.run_task(self._update_clock_task)
        self.page.run_task(self._pc_auto_save_task)
        self.page.run_task(self.page.push_route, self.page.route or "/")
        self.route_change(None)

    # region 1. 生命周期与原生路由管理
    def route_change(self, e):
        # 💥 终极回归：采用 Flet 官方标准的“全量重建视图”法
        # 每次路由变化，彻底清空并重新生成干净的视图，100% 根绝空气墙和点击失效！
        self.page.views.clear()
        self.page.views.append(get_home_view(self))
        
        if self.page.route == "/reader":
            self.page.views.append(get_reader_view(self))
            
        self._apply_theme_colors()
        self.page.update()

    def view_pop(self, e):
        # 1. 物理侧滑余震拦截（0.5秒内刚因为侧滑关过弹窗，则绝不回退页面，留在这看书）
        if hasattr(self, "_last_dismiss_time") and (time.time() - self._last_dismiss_time < 0.5):
            return

        # 2. 检查是否有业务弹窗开着，有的话优先关弹窗
        if hasattr(self, "active_dialogs") and self.active_dialogs:
            dlg = self.active_dialogs.pop()
            self._universal_close(dlg)
            return

        # 3. 没有任何弹窗阻挡，执行正常的退回书架逻辑
        self.go_back_home(None)

    def _on_os_theme_change(self, e):
        if getattr(self, "follow_system_theme", True):
            self.page.theme_mode = ft.ThemeMode.SYSTEM
            self.sync_theme_btn_ui()
            self._sync_font_highlight() 
            self._sync_bg_highlight()
            self._apply_theme_colors() 
        else:
            if "dark" in getattr(self, "manual_theme_mode", "light"):
                self.page.theme_mode = ft.ThemeMode.DARK
            else:
                self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.update()
        
    def _on_app_lifecycle(self, e):
        if "RESUME" not in str(e.state).upper():
            self.save_current_progress()

    def _on_keyboard_control(self, e: ft.KeyboardEvent):
        if e.key == "Escape":
            dialogs_to_check = [
                getattr(self, "global_dialog", None),
                getattr(self, "toc_sheet", None),
                getattr(self, "settings_sheet", None)
            ]
            for dlg in dialogs_to_check:
                if dlg and getattr(dlg, "open", False):
                    self._universal_close(dlg)
                    return

            if self.page.route == "/reader":
                self.go_back_home(None)
            return

        if self.page.route != "/reader": return
        
        if e.key == "Arrow Right":
            self.load_next()
        elif e.key == "Arrow Left":
            self.load_prev()
            
        elif e.key in ["Arrow Down", " "]:
            if hasattr(self, "text_scroll_col"):
                self.page.run_task(self.text_scroll_col.scroll_to, delta=200, duration=100)
        elif e.key == "Arrow Up":
            if hasattr(self, "text_scroll_col"):
                self.page.run_task(self.text_scroll_col.scroll_to, delta=-200, duration=100)
    # endregion

    # region 2. 数据持久化与存储总线
    def _load_config_from_appdata(self):
        data = StorageManager.load_json("ai_config.json")
        if data:
            for k in ["url", "key", "model", "prompt", "embed_mode", "embed_url", "embed_key", "embed_model", "local_embed_path", "local_model_path", "top_k"]:
                if k in data: self.ai_config[k] = data[k]
            bg_c = data.get("bg_color")
            self.bg_color = bg_c if bg_c else "#FFFFFF"
            self.bg_image = data.get("bg_image")  
            self.reader_text_color = data.get("reader_text_color", "#212121")
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
        else:
            self.page.theme_mode = ft.ThemeMode.SYSTEM

    def _save_config_to_appdata(self):
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
        
        StorageManager.save_json("ai_config.json", data_to_save)

    def _load_bookshelf(self):
        self.bookshelf = StorageManager.load_json("bookshelf.json", default=[])

    def _save_bookshelf(self):
        StorageManager.save_json("bookshelf.json", self.bookshelf)

    def _load_book_summaries(self):
        self.current_book_summaries = StorageManager.load_book_summaries(self.current_book_path)

    def _save_book_summaries(self):
        StorageManager.save_book_summaries(self.current_book_path, self.current_book_summaries)

    async def export_app_data(self, e):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            suggested_name = f"小说智读备份_{timestamp}.zip"
            base_dir = StorageManager.get_base_dir()

            all_files = []
            for root, dirs, files in os.walk(base_dir):
                # 💥 核心修复 1：剥离大模型！将 models 文件夹从遍历名单中踢出！
                if 'models' in dirs:
                    dirs.remove('models')
                    
                for file in files:
                    all_files.append(os.path.join(root, file))
            
            total_files = len(all_files)
            if total_files == 0:
                self.show_snack_bar("⚠️ 没有可导出的数据")
                return
            
            # ... 下面的 轨道A 和 轨道B 代码保持完全不变 ...

            # ========================================================
            # 🚀 轨道 A：电脑端 (Windows/Mac/Linux) —— 沿用原逻辑，拒绝内存爆炸
            # ========================================================
            if sys.platform in ["win32", "darwin", "linux"]:
                # 1. 电脑端先选路径（不带 src_bytes，秒弹系统窗口）
                save_path = await ft.FilePicker().save_file(
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["zip"],
                    file_name=suggested_name
                )
                
                if not save_path:
                    self.show_snack_bar("⚠️ 已取消导出")
                    return

                # 2. 选好路径后再弹进度条，直接边读边往硬盘里写
                prog_bar = ft.ProgressBar(value=0, color=ft.Colors.BLUE, height=8, width=300)
                prog_text = ft.Text("正在打包写入硬盘...", size=13, color="onSurface")
                
                self.global_dialog.title = ft.Text("正在导出备份", size=18, weight=ft.FontWeight.BOLD)
                self.global_dialog.content = ft.Column([
                    ft.Container(height=10), prog_bar, prog_text, ft.Container(height=10)
                ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                self.global_dialog.actions = []
                self.page.update()

                import zipfile
                with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for i, abs_path in enumerate(all_files):
                        rel_path = os.path.relpath(abs_path, base_dir)
                        zipf.write(abs_path, rel_path)
                        
                        # 动态刷新 UI 进度
                        if i % max(1, total_files // 20) == 0 or i == total_files - 1:
                            prog_bar.value = (i + 1) / total_files
                            prog_text.value = f"正在写入硬盘... {i+1} / {total_files}"
                            self.page.update()
                            await asyncio.sleep(0.01)

                self.show_snack_bar("✅ 应用数据已完整导出到本地")
                self._close_dialog()

            # ========================================================
            # 📱 轨道 B：移动端 (Android/iOS) —— 内存打包 + 沙盒穿透
            # ========================================================
            else:
                # 1. 移动端先弹进度条
                prog_bar = ft.ProgressBar(value=0, color=ft.Colors.BLUE, height=8, width=300)
                prog_text = ft.Text("正在内存中构建数据包...", size=13, color="onSurface")
                
                self.global_dialog.title = ft.Text("正在导出备份", size=18, weight=ft.FontWeight.BOLD)
                self.global_dialog.content = ft.Column([
                    ft.Container(height=10), prog_bar, prog_text, ft.Container(height=10)
                ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                self.global_dialog.actions = []
                self.page.update()

                import io
                import zipfile
                zip_buffer = io.BytesIO()

                # 2. 强制在内存中打包，规避安卓沙盒磁盘写入拦截
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for i, abs_path in enumerate(all_files):
                        rel_path = os.path.relpath(abs_path, base_dir)
                        zipf.write(abs_path, rel_path)
                        
                        if i % max(1, total_files // 20) == 0 or i == total_files - 1:
                            prog_bar.value = (i + 1) / total_files
                            prog_text.value = f"正在构建数据包... {i+1} / {total_files}"
                            self.page.update()
                            await asyncio.sleep(0.01)

                zip_bytes = zip_buffer.getvalue()
                prog_bar.value = 1.0
                prog_text.value = "构建完成！请在系统弹窗中选择保存..."
                self.page.update()

                # 3. 把构建好的内存包直接喂给安卓底层分享接口
                await ft.FilePicker().save_file(
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["zip"],
                    file_name=suggested_name,
                    src_bytes=zip_bytes
                )
                
                self.show_snack_bar("✅ 操作结束 (若未取消，备份已保存)")
                self._close_dialog()

        except Exception as ex:
            self.show_snack_bar(f"❌ 导出失败: {str(ex)}")
            self._close_dialog()


    async def import_app_data(self, e):
        try:
            # 1. UI 状态切换
            prog_bar = ft.ProgressBar(value=0, color=ft.Colors.BLUE, height=8, width=300)
            prog_text = ft.Text("正在准备恢复环境...", size=13, color="onSurface")
            
            self.global_dialog.title = ft.Text("正在恢复备份", size=18, weight=ft.FontWeight.BOLD)
            self.global_dialog.content = ft.Column([
                ft.Container(height=10), prog_bar, prog_text, ft.Container(height=10)
            ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            self.global_dialog.actions = []
            self.page.update()

            # 2. 唤起文件选择器
            files = await ft.FilePicker().pick_files(
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["zip"]
            )

            if files and len(files) > 0:
                zip_path = files[0].path
                if zip_path:
                    # 💥 关键点 1：清理引擎状态，确保不再占用任何书籍文件
                    # 如果你的 NovelEngine 有 close() 方法请在此调用
                    self.current_book_path = "" 
                    self.engine.chapters_info = []
                    
                    prog_text.value = "正在验证备份文件..."
                    self.page.update()

                    base_dir = StorageManager.get_base_dir()
                    import zipfile
                    
                    with zipfile.ZipFile(zip_path, 'r') as zipf:
                        zip_infos = zipf.infolist()
                        total_files = len(zip_infos)
                        
                        # 2. 开始解压并动态刷新进度
                        for i, zip_info in enumerate(zip_infos):
                            try:
                                # 💥 治标之法：在解压覆盖前，先探测旧文件是否存在。若存在，强行解除只读封印！
                                target_path = os.path.join(base_dir, zip_info.filename)
                                if os.path.exists(target_path):
                                    import stat
                                    try:
                                        os.chmod(target_path, stat.S_IWRITE) 
                                    except Exception:
                                        pass # 如果连改权限的权限都没有，就交给下面的 except 去捕获

                                # 安全执行解压覆盖
                                zipf.extract(zip_info, base_dir)
                                
                            except PermissionError:
                                filename = zip_info.filename
                                raise Exception(f"文件正在被占用：{filename}\n请确保已关闭所有正在阅读的界面，并重试。")
                            
                            if i % max(1, total_files // 20) == 0 or i == total_files - 1:
                                prog_bar.value = (i + 1) / total_files
                                prog_text.value = f"正在还原文件... {i+1} / {total_files}"
                                self.page.update()
                                await asyncio.sleep(0.01)

                    self.show_snack_bar("✅ 数据已完美恢复，请重启应用生效")
                    self._load_config_from_appdata()
                    self._load_bookshelf()
                    self.refresh_bookshelf_ui()
                    # 💥 修复 500 报错 Bug 的终极补丁：一枪崩掉旧引擎，强迫它下次热启动
                    if sys.platform == "win32":
                        os.system("taskkill /F /IM llama-server.exe >nul 2>&1")

                else:
                    self.show_snack_bar("❌ 无法获取文件路径")
            else:
                self.show_snack_bar("⚠️ 已取消恢复")
            
            self._close_dialog()
            
        except Exception as ex:
            # 将错误信息反馈给 UI
            self.show_snack_bar(f"❌ 恢复失败: {str(ex)}")
            self._close_dialog()
        

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

    # ==========================================
    # --- 新增 Flet 0.84.0 适配代码：本地模型文件管理与导入 ---
    # ==========================================
    def get_models_dir(self):
        """获取/创建模型专属的私有存放目录"""
        import os
        from data.storage import StorageManager
        models_dir = os.path.join(StorageManager.get_base_dir(), "models")
        os.makedirs(models_dir, exist_ok=True)
        return models_dir

    def get_local_models(self):
        """扫描目录，返回所有可用模型文件的绝对路径"""
        import os
        models_dir = self.get_models_dir()
        if not os.path.exists(models_dir):
            return []
        try:
            return [os.path.join(models_dir, f) for f in os.listdir(models_dir) if f.endswith(('.gguf', '.onnx', '.bin'))]
        except Exception:
            return []

    async def trigger_model_picker(self, dropdown_control):
        """拉起系统文件管理器并导入模型（纯异步调用）"""
        try:
            # 最新版的 FilePicker 作为全局独立方法直接 await
            files = await ft.FilePicker().pick_files(
                dialog_title="请选择本地大模型",
                file_type=ft.FilePickerFileType.CUSTOM, 
                allowed_extensions=["onnx", "gguf", "bin", "pt", "safetensors"]
            )
            
            if files and len(files) > 0:
                import shutil
                import asyncio
                
                src_path = files[0].path
                original_name = files[0].name
                
                if not src_path:
                    self.show_snack_bar("获取文件路径失败，请尝试更换目录。")
                    return

                dest_path = os.path.join(self.get_models_dir(), original_name)

                try:
                    # 关键权衡：将大文件拷贝抛入子线程，避免阻塞主 UI 导致掉帧卡死
                    await asyncio.to_thread(shutil.copy2, src_path, dest_path)
                    self.show_snack_bar(f"✅ 模型 {original_name} 导入成功")
                    
                    # 动态刷新 UI 选项卡
                    if dropdown_control:
                        opts = [ft.dropdown.Option(f) for f in self.get_local_models()]
                        dropdown_control.options = opts
                        dropdown_control.value = dest_path
                        try: dropdown_control.update()
                        except Exception: pass
                        
                except Exception as copy_ex:
                    self.show_snack_bar(f"模型文件转存失败: {str(copy_ex)}")
                    
        except Exception as ex:
            self.show_snack_bar(f"唤起文件管理器失败: {str(ex)}")
    # ==========================================

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
                    books_dir = os.path.join(StorageManager.get_base_dir(), "books")
                    
                    if not os.path.exists(books_dir):
                        try: 
                            os.makedirs(books_dir, exist_ok=True)
                        except Exception as create_ex:
                            self.show_snack_bar(f"建立书籍存放目录失败，请检查应用存储权限: {str(create_ex)}")
                            return

                    persistent_path = os.path.join(books_dir, original_name)

                    try:
                        shutil.copy2(picked_path, persistent_path)
                        # 💥 治本之法：无论是不是微信来的文件，落地瞬间强行洗掉“只读”属性！
                        import stat
                        os.chmod(persistent_path, stat.S_IWRITE | stat.S_IREAD)
                        
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
        if hasattr(self, "progress_bar"):
            self.progress_bar.value = progress
        if hasattr(self, "status_text"):
            self.status_text.value = msg
        self.page.update()

    def refresh_bookshelf_ui(self):
        if not hasattr(self, "bookshelf_grid"): return
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
            
            vol_title = book.get('last_volume_title', '')
            chap_title = book.get('last_chapter_title', '未读')
            
            info_col = ft.Column(spacing=2)
            info_col.controls.append(ft.Text(book['name'], weight=ft.FontWeight.BOLD, size=15, color=ft.Colors.BLUE, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS))
            if vol_title:
                info_col.controls.append(ft.Text(vol_title, size=11, color=ft.Colors.GREY_700, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))
            info_col.controls.append(ft.Text(chap_title, size=11, color=ft.Colors.GREY_500, max_lines=2 if not vol_title else 1, overflow=ft.TextOverflow.ELLIPSIS))

            # 💥 彻底弃用 GestureDetector，改用原生 Container，配合全新的纯净路由，手感拉满！
            card = ft.Container(
                alignment=ft.Alignment(0, 0),
                content=ft.Container(
                    ink=True,
                    on_click=lambda e, p=book['path']: self.check_and_load_book(p),
                    on_long_press=lambda e, p=book['path'], n=book['name']: self.show_book_options_dialog(p, n),
                    content=ft.Stack([
                        ft.Container(width=160, height=220, border_radius=0, bgcolor="surface", border=card_border), 
                        ft.Container(width=14, height=218, left=1, top=1, bgcolor=ft.Colors.BLUE_700),
                        ft.Container(width=2, height=218, left=15, top=1, bgcolor=ft.Colors.BLUE_900),
                        ft.Container(content=info_col, left=30, top=20, width=120)
                    ])
                )
            )
            self.bookshelf_grid.controls.append(card)
        self.page.update()

    # region 3. 阅读核心引擎与交互
    # =========================================================================
    def check_and_load_book(self, path):
        if not os.path.exists(path):
            self.show_snack_bar("文件丢失，可能已被移动或删除，将自动移出书架。")
            self.remove_from_bookshelf(path)
            return
        self.start_parsing(path)

    def start_parsing(self, path):
        self.current_book_path = path
        
        custom_name = os.path.splitext(os.path.basename(path))[0]
        for b in self.bookshelf:
            if b['path'] == path:
                custom_name = b.get('name', custom_name)
                break
        self.current_book_name = custom_name
        
        toc_cache = StorageManager.load_book_toc(path)
        if toc_cache:
            self.engine.load_with_cache(path, toc_cache)
            self.on_parse_success()
            return

        if hasattr(self, "status_text"): self.status_text.visible = True
        if hasattr(self, "progress_bar"): 
            self.progress_bar.visible = True
            self.progress_bar.value = 0
        self.page.update()
        
        def task():
            try:
                chaps = self.engine.load_and_analyze(path, self._sync_progress)
                StorageManager.save_book_toc(path, chaps)
                self.on_parse_success()
            except Exception as e:
                self.show_snack_bar(f"解析失败: {str(e)}")
                if hasattr(self, "status_text"): self.status_text.visible = False
                if hasattr(self, "progress_bar"): self.progress_bar.visible = False
                self.page.update()
                
        threading.Thread(target=task, daemon=True).start()

    def on_parse_success(self):
        if hasattr(self, "status_text"): self.status_text.visible = False
        if hasattr(self, "progress_bar"): self.progress_bar.visible = False
        
        target_idx = -1
        target_offset = 0.0
        book_exists = False
        for book in self.bookshelf:
            if book['path'] == self.current_book_path:
                book_exists = True
                target_idx = book.get('last_chapter_idx', -1)
                target_offset = book.get('last_scroll_offset', 0.0)
                break

        if not book_exists:
            self.bookshelf.insert(0, {
                "name": self.current_book_name,
                "path": self.current_book_path,
                "last_chapter_idx": 0,
                "last_chapter_title": "未读",
                "last_scroll_offset": 0.0
            })
            self._save_bookshelf()
            
        self._load_book_summaries()

        if target_idx != -1 and target_idx < len(self.engine.chapters_info):
            self.current_chapter_idx = target_idx
        else:
            valid_idx = self._find_valid_chapter(0, 1)
            self.current_chapter_idx = valid_idx if valid_idx != -1 else 0
            
        self.current_scroll_offset = target_offset

        self.page.run_task(self.page.push_route, "/reader")

    def load_chapter(self, idx, target_offset=0.0):
        if not self.engine.chapters_info: return
        self.current_chapter_idx = idx
        
        ch_info = self.engine.chapters_info[idx]
        title = ch_info['title']
        volume = ch_info.get('volume', '')
        text = self.engine.get_chapter_text(idx)

        self.current_scroll_offset = target_offset
        self.current_max_scroll_extent = 0.0 

        # --- 1. 更新顶部菜单与状态进度 ---
        if hasattr(self, "top_bar_book_name"):
            display_vol = volume if volume and volume != title else ""
            self.top_bar_book_name.value = f"{self.current_book_name} | {display_vol}" if display_vol else self.current_book_name
        if hasattr(self, "top_bar_chapter_name"):
            self.top_bar_chapter_name.value = title
        if hasattr(self, "info_chapter_name"):
            self.info_chapter_name.value = title
            
        if hasattr(self, "info_progress"):
            total_length = len(self.engine.full_text_content)
            if total_length > 0:
                base_pct = (ch_info['start'] / total_length) * 100
            else:
                base_pct = 0.0
            self.last_reported_pct = base_pct
            self.info_progress.value = f"{base_pct:.1f}%"
        
        current_text_color = "#B0B0B0" if self._get_is_dark_mode() else self.reader_text_color
        
        # --- 2. 切分文本并生成 UI 正文节点 ---
        paragraphs = [p.rstrip() for p in text.replace('\r', '').split('\n') if p.strip()]
        
        self.reader_text_controls = []
        self.chapter_title_control = None
        
        if paragraphs:
            title_text = paragraphs.pop(0)
            self.chapter_title_control = ft.Container(
                content=ft.Text(
                    title_text,
                    size=self.font_size + 2,  
                    weight=ft.FontWeight.BOLD, 
                    style=ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing),
                    font_family=self.font_family,
                    color=current_text_color,
                    text_align=ft.TextAlign.LEFT 
                ),
                padding=ft.Padding(left=0, top=0, right=0, bottom=15) 
            )

            for p in paragraphs:
                self.reader_text_controls.append(
                    ft.Text(
                        p, 
                        size=self.font_size, 
                        style=ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing),
                        font_family=self.font_family, 
                        color=current_text_color   
                    )
                )

        prev_valid = self._find_valid_chapter(idx - 1, -1) if idx > 0 else -1
        next_valid = self._find_valid_chapter(idx + 1, 1) if idx < len(self.engine.chapters_info)-1 else -1

        if next_valid != -1:
            self.inline_next_btn = ft.Container(
                content=ft.TextButton(
                    content=ft.Text("下一章"),
                    icon=ft.Icons.ARROW_FORWARD,
                    on_click=self.load_next,
                    style=ft.ButtonStyle(color=current_text_color)
                ),
                alignment=ft.Alignment(0, 0),
                padding=ft.Padding(top=30, bottom=50, left=0, right=0)
            )
        else:
            self.inline_next_btn = ft.Container(
                content=ft.Text("— 已经是最后一章了 —", color=current_text_color, size=13),
                alignment=ft.Alignment(0, 0),
                padding=ft.Padding(top=30, bottom=50, left=0, right=0)
            )

        controls_to_add = []
        if self.chapter_title_control:
            controls_to_add.append(self.chapter_title_control)
        controls_to_add.extend(self.reader_text_controls)
        controls_to_add.append(self.inline_next_btn)

        self.inner_text_col = ft.Column(
            controls=controls_to_add,
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
            on_scroll=self._on_text_scroll, 
            key="text_scroll_col",
            opacity=0,                                                            
            animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT)      
        )
        
        if hasattr(self, "text_panel"):
            self.text_panel.content = self.text_scroll_col

        if hasattr(self, "btn_prev"): self.btn_prev.disabled = prev_valid == -1
        if hasattr(self, "btn_next"): self.btn_next.disabled = next_valid == -1

        self.save_current_progress() 

        if not hasattr(self, "toc_listview") or not self.toc_listview.controls:
            self.filter_toc(None) 
        else:
            self._update_toc_highlight()
            
        self.page.update()
        
        # --- 3. 触发滚动与透明度淡入动画 ---
        self.page.run_task(self._delayed_scroll_to_chapter, idx)
        self.page.run_task(self._finalize_chapter_load, self.text_scroll_col, target_offset)

    def load_prev(self, e=None):
        if self.current_chapter_idx > 0:
            valid_idx = self._find_valid_chapter(self.current_chapter_idx - 1, -1)
            if valid_idx != -1: self.load_chapter(valid_idx) 

    def load_next(self, e=None):
        if self.current_chapter_idx < len(self.engine.chapters_info) - 1:
            valid_idx = self._find_valid_chapter(self.current_chapter_idx + 1, 1)
            if valid_idx != -1: self.load_chapter(valid_idx) 

    def _on_text_scroll(self, e: ft.OnScrollEvent):
        self.current_scroll_offset = e.pixels
        self.current_max_scroll_extent = getattr(e, "max_scroll_extent", 0.0) 
        
        if not self.engine.chapters_info: return
        
        max_ext = self.current_max_scroll_extent
        chap_pct = 0.0
        if max_ext and max_ext > 0:
            p = max(0.0, min(float(e.pixels), float(max_ext)))
            chap_pct = p / max_ext
            
        total_length = len(self.engine.full_text_content)
        if total_length > 0:
            ch_info = self.engine.chapters_info[self.current_chapter_idx]
            chap_len = ch_info['end'] - ch_info['start']
            current_total_pct = ((ch_info['start'] + chap_len * chap_pct) / total_length) * 100
            
            if abs(current_total_pct - getattr(self, "last_reported_pct", -1.0)) >= 0.1:
                self.last_reported_pct = current_total_pct
                if hasattr(self, "info_progress"):
                    self.info_progress.value = f"{current_total_pct:.1f}%"
                    try: self.info_progress.update()
                    except Exception: pass

    def filter_toc(self, e=None):
        if e is not None and getattr(e, "name", "") != "change":
            return

        query = getattr(self, "search_tf", None).value.lower() if getattr(self, "search_tf", None) and self.search_tf.value else ""
        
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
        
        if hasattr(self, "toc_listview"):
            self.toc_listview.controls.clear()
            self.toc_listview.controls.extend(new_controls)
            self.filtered_toc_mapping = new_mapping
            self.page.update()

    def _update_toc_highlight(self):
        if not hasattr(self, "toc_listview"): return
        for i, idx in enumerate(self.filtered_toc_mapping):
            if i < len(self.toc_listview.controls):
                try:
                    text_ctrl = self.toc_listview.controls[i].content
                    expected_color = ft.Colors.BLUE if idx == self.current_chapter_idx else None
                    if text_ctrl.color != expected_color:
                        text_ctrl.color = expected_color
                        try: text_ctrl.update()
                        except Exception: pass
                except Exception:
                    pass

    async def _delayed_scroll_to_chapter(self, idx, delay=0.1):
        if not hasattr(self, "toc_listview"): return
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

    async def _finalize_chapter_load(self, col, offset):
        await asyncio.sleep(0.1) 
        try:
            if offset > 0:
                await col.scroll_to(offset=offset, duration=0)
                await asyncio.sleep(0.05) 
            col.opacity = 1
            col.update()
        except Exception:
            pass

    def go_back_home(self, e):
        if self.page.route == "/reader":
            self.save_current_progress()
            if getattr(self, "is_immersive", False):
                self.toggle_immersive(None)
                
        # 通过 push_route 触发上面的 route_change，实现全局干净回退
        self.page.run_task(self.page.push_route, "/")
    
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
    # endregion

    # region 4. 主题排版与 UI 渲染刷子
    # =========================================================================
    
    def get_action_button_style(self, padding=ft.Padding.symmetric(horizontal=16, vertical=8), text_color="onSurface"):
        is_dark = self._get_is_dark_mode()
        
        in_reader = getattr(self.page, "route", "/") == "/reader"
        
        if is_dark:
            btn_bg_c = "#2C2C2C" 
        else:
            if not in_reader:
                btn_bg_c = "#F0F0F0"
            else:
                bg_c = self.bg_color
                if bg_c == "#FFFFFF": btn_bg_c = "#F8F8F8"       
                elif bg_c == "#D4A373": btn_bg_c = "#E8B787"       
                elif bg_c == "#CBB28C": btn_bg_c = "#DFC6A0"       
                elif bg_c == "#E8DCC8": btn_bg_c = "#F7EBD7"       
                elif bg_c == "#F5F5DC": btn_bg_c = "#FFFFE6"       
                elif bg_c == "#CCE8CF": btn_bg_c = "#E0FCE3"       
                else: btn_bg_c = "#F0F0F0"
                
        return ft.ButtonStyle(bgcolor=btn_bg_c, color=text_color, elevation=0, shape=ft.RoundedRectangleBorder(radius=30), padding=padding)

    def update_reader_appearance(self, **kwargs):
        if "bg" in kwargs: self.bg_color = kwargs["bg"]
        if "bg_image" in kwargs: self.bg_image = kwargs["bg_image"]  
        if "text" in kwargs: self.reader_text_color = kwargs["text"]
        if "font" in kwargs: self.font_family = kwargs["font"]
        
        if hasattr(self, "reader_text_controls"):
            for ctrl in self.reader_text_controls:
                ctrl.font_family = self.font_family
                try: ctrl.update()
                except Exception: pass

        if hasattr(self, "chapter_title_control") and self.chapter_title_control:
            if isinstance(self.chapter_title_control.content, ft.Text):
                self.chapter_title_control.content.font_family = self.font_family
                try: self.chapter_title_control.content.update()
                except Exception: pass
                
        self._apply_theme_colors() 
        self._save_config_to_appdata()

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
        except Exception: pass

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
            try: self.reader_top_bar.update()
            except Exception: pass

        if hasattr(self, "reader_bottom_bar"):
            self.reader_bottom_bar.offset = ft.Offset(0, 1) if self.is_immersive else ft.Offset(0, 0)
            try: self.reader_bottom_bar.update()
            except Exception: pass
            
        self.page.update()

    def change_font(self, delta):
        new_size = self.font_size + delta
        if 12 <= new_size <= 48:
            self.font_size = new_size
            
            if hasattr(self, "chapter_title_control") and self.chapter_title_control:
                if isinstance(self.chapter_title_control.content, ft.Text):
                    self.chapter_title_control.content.size = self.font_size + 2
                    try: self.chapter_title_control.content.update()
                    except Exception: pass
                    
            if hasattr(self, "reader_text_controls"):
                for ctrl in self.reader_text_controls:
                    ctrl.size = self.font_size
                    try: ctrl.update()
                    except Exception: pass
            if hasattr(self, "font_size_text"):
                self.font_size_text.value = str(self.font_size)
                try: self.font_size_text.update()
                except Exception: pass

    def change_line_height(self, delta):
        new_height = round(self.line_height + delta, 1)
        if 1.0 <= new_height <= 3.0:
            self.line_height = new_height
            
            if hasattr(self, "chapter_title_control") and self.chapter_title_control:
                if isinstance(self.chapter_title_control.content, ft.Text):
                    self.chapter_title_control.content.style = ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing)
                    try: self.chapter_title_control.content.update()
                    except Exception: pass
                    
            if hasattr(self, "reader_text_controls"):
                for ctrl in self.reader_text_controls:
                    ctrl.style = ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing)
                    try: ctrl.update()
                    except Exception: pass
            if hasattr(self, "line_height_text"):
                self.line_height_text.value = f"{self.line_height:.1f}"
                try: self.line_height_text.update()
                except Exception: pass

    def change_paragraph_spacing(self, delta):
        new_spacing = int(self.paragraph_spacing + delta)
        if 0 <= new_spacing <= 50:
            self.paragraph_spacing = new_spacing
            if hasattr(self, "inner_text_col"):
                self.inner_text_col.spacing = self.paragraph_spacing
                try: self.inner_text_col.update()
                except Exception: pass
            if hasattr(self, "para_spacing_text"):
                self.para_spacing_text.value = str(self.paragraph_spacing)
                try: self.para_spacing_text.update()
                except Exception: pass

    def change_letter_spacing(self, delta):
        new_spacing = round(self.letter_spacing + delta, 1)
        if 0.0 <= new_spacing <= 10.0:
            self.letter_spacing = new_spacing
            
            if hasattr(self, "chapter_title_control") and self.chapter_title_control:
                if isinstance(self.chapter_title_control.content, ft.Text):
                    self.chapter_title_control.content.style = ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing)
                    try: self.chapter_title_control.content.update()
                    except Exception: pass
                    
            if hasattr(self, "reader_text_controls"):
                for ctrl in self.reader_text_controls:
                    ctrl.style = ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing)
                    try: ctrl.update()
                    except Exception: pass
            if hasattr(self, "letter_spacing_text"):
                self.letter_spacing_text.value = f"{self.letter_spacing:.1f}"
                try: self.letter_spacing_text.update()
                except Exception: pass

    def _sync_bg_highlight(self):
        is_dark = self._get_is_dark_mode()
        shadow_color = "#66FFFFFF" if is_dark else "#66000000" 
        
        bg_configs = [
            (getattr(self, "bg_btn_white", None), "#FFFFFF", None),
            (getattr(self, "bg_btn_kraft1", None), "#D4A373", "backgrounds/牛皮纸.jpg"),
            (getattr(self, "bg_btn_kraft2", None), "#CBB28C", "backgrounds/牛皮纸2.jpg"),
            (getattr(self, "bg_btn_kraft3", None), "#E8DCC8", "backgrounds/牛皮纸3.jpg"),
            (getattr(self, "bg_btn_yellow", None), "#F5F5DC", None),
            (getattr(self, "bg_btn_green", None), "#CCE8CF", None),
        ]
        
        for btn, bg_c, bg_img in bg_configs:
            if not btn: continue
            is_active = (self.bg_color == bg_c and self.bg_image == bg_img)
            
            btn.border = ft.Border.all(1, ft.Colors.GREY_400)
                
            if is_active:
                btn.shadow = ft.BoxShadow(
                    spread_radius=2, 
                    blur_radius=8, 
                    color=shadow_color, 
                    offset=ft.Offset(0, 0)
                )
            else:
                btn.shadow = None
                
            try: btn.update()
            except Exception: pass

    def _sync_font_highlight(self):
        active_bg = "#1AFFFFFF" if self._get_is_dark_mode() else "#1A000000"
        inactive_bg = ft.Colors.TRANSPARENT
        
        font_configs = [
            (getattr(self, "font_btn_default", None), None),
            (getattr(self, "font_btn_qihei", None), "汉仪旗黑"),
            (getattr(self, "font_btn_zhongsong", None), "汉仪中宋"),
            (getattr(self, "font_btn_zhengyuan", None), "汉仪正圆"),
        ]
        
        for btn, f_family in font_configs:
            if not btn: continue
            is_active = (self.font_family == f_family)
            btn.style = ft.ButtonStyle(
                bgcolor=active_bg if is_active else inactive_bg,
                color=ft.Colors.ON_SURFACE,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8)
            )
            try: btn.update()
            except Exception: pass

    def _get_is_dark_mode(self):
        if not getattr(self, "follow_system_theme", True):
            return "dark" in getattr(self, "manual_theme_mode", "light")
            
        pb = self.page.platform_brightness
        if pb is None:
            return False 
        return str(pb).lower().endswith("dark")

    def _apply_theme_colors(self):
        is_dark = self._get_is_dark_mode()
        
        if is_dark:
            bg_c = "#000000"
            bg_i = None
            menu_c = "surface"
            text_c = "#B0B0B0"             
            top_book_c = ft.Colors.GREY_500
            top_chap_c = ft.Colors.WHITE   
        else:
            bg_c = self.bg_color
            bg_i = self.bg_image
            menu_c = self.bg_color if self.bg_color else "surface"
            text_c = self.reader_text_color 
            top_book_c = ft.Colors.GREY_600
            top_chap_c = ft.Colors.BLACK if self.bg_color else ft.Colors.ON_SURFACE
            
        if hasattr(self, "reading_base_layer"):
            self.reading_base_layer.bgcolor = bg_c
            self.reading_base_layer.image = ft.DecorationImage(src=bg_i, repeat="repeat") if bg_i else None
            try: self.reading_base_layer.update()
            except Exception: pass

        in_reader = getattr(self.page, "route", "/") == "/reader"
        dialog_bg_c = menu_c if in_reader else "surface"

        for sheet in [getattr(self, "global_dialog", None), getattr(self, "settings_sheet", None), getattr(self, "toc_sheet", None)]:
            if sheet:
                target_c = dialog_bg_c if sheet == getattr(self, "global_dialog", None) else menu_c
                sheet.bgcolor = target_c
                if getattr(sheet, "content", None) and isinstance(sheet.content, ft.Container):
                    sheet.content.bgcolor = target_c
                    if isinstance(sheet, ft.BottomSheet):
                        sheet.content.border_radius = ft.BorderRadius.only(top_left=28, top_right=28)
                    else:
                        sheet.content.border_radius = 28
                    try: sheet.content.update()
                    except Exception: pass
                try: sheet.update()
                except Exception: pass
                
        if hasattr(self, "page") and self.page.theme:
            self.page.theme.popup_menu_theme = ft.PopupMenuTheme(
                color=menu_c
            )
            try: self.page.update()
            except Exception: pass

        if hasattr(self, "chapter_title_control") and self.chapter_title_control:
            if isinstance(self.chapter_title_control.content, ft.Text):
                self.chapter_title_control.content.color = text_c
                try: self.chapter_title_control.content.update()
                except Exception: pass
            
        if hasattr(self, "reader_text_controls"):
            for ctrl in self.reader_text_controls:
                if ctrl.color != text_c:
                    ctrl.color = text_c
                    try: ctrl.update()
                    except Exception: pass

        if hasattr(self, "inline_next_btn") and self.inline_next_btn:
            if isinstance(self.inline_next_btn.content, ft.TextButton):
                self.inline_next_btn.content.style = ft.ButtonStyle(
                    color=text_c,
                    bgcolor=ft.Colors.TRANSPARENT,
                    elevation=0
                )
                self.inline_next_btn.content.icon_color = text_c
                if getattr(self.inline_next_btn.content, "content", None) and isinstance(self.inline_next_btn.content.content, ft.Text):
                    self.inline_next_btn.content.content.color = text_c
                    try: self.inline_next_btn.content.content.update()
                    except Exception: pass
            elif isinstance(self.inline_next_btn.content, ft.Text):
                self.inline_next_btn.content.color = text_c
            try: self.inline_next_btn.update()
            except Exception: pass
            
        if hasattr(self, "reader_top_bar"):
            self.reader_top_bar.bgcolor = menu_c
            try: self.reader_top_bar.update()
            except Exception: pass
            
        if hasattr(self, "top_bar_book_name"):
            self.top_bar_book_name.color = top_book_c
            try: self.top_bar_book_name.update()
            except Exception: pass
            
        if hasattr(self, "top_bar_chapter_name"):
            self.top_bar_chapter_name.color = top_chap_c
            try: self.top_bar_chapter_name.update()
            except Exception: pass
            
        if hasattr(self, "reader_bottom_bar"):
            self.reader_bottom_bar.bgcolor = menu_c
            try: self.reader_bottom_bar.update()
            except Exception: pass

        if hasattr(self, "btn_more") and self.btn_more:
            self.btn_more.icon_color = top_chap_c
            try: self.btn_more.update()
            except Exception: pass

        pad_12 = ft.Padding.symmetric(horizontal=12)
        pad_8 = ft.Padding.symmetric(horizontal=8)
        
        for btn, pad in [
            (getattr(self, "btn_prev", None), pad_12),
            (getattr(self, "btn_next", None), pad_12),
            (getattr(self, "btn_toc", None), pad_8),
            (getattr(self, "theme_btn", None), pad_8),
            (getattr(self, "btn_settings", None), pad_8),
            (getattr(self, "btn_copy_current", None), pad_8) 
        ]:
            if btn:
                if getattr(btn, "content", None) and isinstance(btn.content, ft.Text):
                    btn.content.color = top_chap_c
                    try: btn.content.update()
                    except Exception: pass
                
                btn.icon_color = top_chap_c
                btn.style = self.get_action_button_style(pad, text_color=top_chap_c)
                try: btn.update()
                except Exception: pass

    def _universal_open(self, control):
        if not hasattr(self, "active_dialogs"): self.active_dialogs = []
        if control not in self.active_dialogs:
            self.active_dialogs.append(control)

        # 挂载关闭钩子：只要弹窗关闭（哪怕是安卓物理侧滑关闭），立刻从生死簿除名并记录时间
        if not getattr(control, "_hooked", False):
            orig_dismiss = control.on_dismiss
            def wrapped_dismiss(e):
                self._last_dismiss_time = time.time()
                if hasattr(self, "active_dialogs") and control in self.active_dialogs:
                    self.active_dialogs.remove(control)
                if orig_dismiss: orig_dismiss(e)
            control.on_dismiss = wrapped_dismiss
            control._hooked = True

        # 标准 Flet API 唤起
        if hasattr(self.page, "open") and callable(getattr(self.page, "open")):
            self.page.open(control)
        else:
            if control not in self.page.overlay:
                self.page.overlay.append(control)
            control.open = True
            self.page.update()

    def _universal_close(self, control):
        self._last_dismiss_time = time.time()
        if hasattr(self, "active_dialogs") and control in self.active_dialogs:
            self.active_dialogs.remove(control)
            
        if hasattr(self.page, "close") and callable(getattr(self.page, "close")):
            self.page.close(control)
        else:
            control.open = False
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

    def show_book_options_dialog(self, path, current_name):
        DialogManager.show_book_options_dialog(self, path, current_name)

    def show_statistics_dialog(self, e):
        DialogManager.show_statistics_dialog(self, e)

    def show_settings_dialog(self, e):
        DialogManager.show_settings_dialog(self, e)

    def show_global_settings_dialog(self, e):
        DialogManager.show_global_settings_dialog(self, e)

    def show_changelog_dialog(self, e):
        DialogManager.show_changelog_dialog(self, e)

    def show_ai_dialog(self, e):
        DialogManager.show_ai_dialog(self, e)

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

    async def _update_clock_task(self):
        while True:
            try:
                if hasattr(self, "info_time"):
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

def main(page: ft.Page):
    app = NovelReaderApp(page)

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

ASSETS_DIR = os.path.join(application_path, "assets")

if __name__ == "__main__":
    ft.run(main, assets_dir=ASSETS_DIR)