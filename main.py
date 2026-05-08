# region 0. 导入与基础路径配置
import os
import sys
import flet as ft
import threading
import asyncio
import shutil
import time  
import zipfile
from datetime import datetime
import traceback
import ctypes  # 【新增】必须导入 ctypes 以调用 Windows 底层 API
import flet_audio as fta

# 💥 终极护盾：获取静态资源的【绝对物理路径】
if getattr(sys, 'frozen', False):
    # 如果是打包后的便携版 EXE，基准路径就是解压的系统临时文件夹
    base_path = sys._MEIPASS
else:
    # 如果是本地开发环境，基准路径就是 main.py 所在的当前目录
    base_path = os.path.abspath(os.path.dirname(__file__))

# 拼装出完整的 assets 绝对路径！
ASSETS_DIR_ABSOLUTE = os.path.join(base_path, "assets")

from core.engine import NovelEngine
from data.storage import StorageManager
from ui.dialogs import DialogManager
from ui.home_view import get_home_view
from ui.reader_view import get_reader_view
from ui.stats_view import get_statistics_view 
from ui.ai_settings_view import get_ai_settings_view
from ui.ai_chat_view import get_ai_chat_view
from core.config_state import ConfigStateMixin
from core.library_state import LibraryStateMixin
from core.theme_state import ThemeRendererMixin
from core.reader_action import ReaderActionMixin
from core.overlay_manager import OverlayManagerMixin
from core.tts_manager import TTSManagerMixin
# endregion

# region 1. 跨平台路径寻址与 DLL 强制注册 (针对 Win11 环境修复)
# ==========================================
# 0. 跨平台路径寻址与 DLL 强制注册 (针对 Win11 环境修复)
# ==========================================

# 💥 新增：注册 flet_audio 扩展，让前端认识 Audio 控件
def main(page: ft.Page):
    page.add_extension(fta)
    app = NovelReaderApp(page)

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
# endregion

# region 2. 闪退捕兽夹 (全局异常捕获)
# --- 【闪退捕兽夹】代码开始 ---
def global_crash_catcher(exctype, value, tb):
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "小说智读_绝密报错日志.txt")
    with open(desktop_path, "w", encoding="utf-8") as f:
        f.write("=== 软件启动崩溃现场 ===\n")
        f.write(error_msg)

sys.excepthook = global_crash_catcher
# --- 【闪退捕兽夹】代码结束 ---
# endregion

# region 3. 核心应用类 (App Controller & Router)
# ==========================================
# 控制器层 (App Controller & Router) 
# ==========================================
class NovelReaderApp(ConfigStateMixin, LibraryStateMixin, ThemeRendererMixin, ReaderActionMixin, OverlayManagerMixin, TTSManagerMixin):
    
    # region 3.1 初始化与 UI 底盘配置
    def __init__(self, page: ft.Page):
        self.page = page
        self.version = "0.5.4"  
        self.author = "手背儿"
        self.page.title = f"小说智读 - v{self.version}"
        
        try:
            self.page.window.icon = "icon.png"
        except Exception: pass

        # ==========================================
        # 💥 优化 1：开机自动大扫除，瞬间清理所有遗留的临时音频垃圾！
        # ==========================================
        temp_audio_dir = os.path.join(ASSETS_DIR_ABSOLUTE, "temp_audio")
        if os.path.exists(temp_audio_dir):
            try:
                shutil.rmtree(temp_audio_dir)
            except Exception: pass
        os.makedirs(temp_audio_dir, exist_ok=True)
        # ==========================================

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
            ),
            page_transitions=ft.PageTransitionsTheme(
            android=ft.PageTransitionTheme.CUPERTINO,
            ios=ft.PageTransitionTheme.CUPERTINO,
            macos=ft.PageTransitionTheme.CUPERTINO,
            windows=ft.PageTransitionTheme.CUPERTINO,
            linux=ft.PageTransitionTheme.CUPERTINO,
            )
        ) 
        self.page.padding = 0

        # --- 2. 核心业务状态 ---
        self.init_config_state()   # 初始化 UI 与 AI 字典
        self.init_library_state()  # 初始化书架进度变量 
        
        # --- 4. 弹窗管控 ---
        self.global_dialog = ft.AlertDialog(title=ft.Text(""))
        self.snack_counter = 0
        self._last_dismiss_time = 0
        self.active_dialogs = []    
        
        # --- 5. 生命周期拉起与路由挂载 ---
        self._load_config_from_appdata() # 这个方法现在由 ConfigStateMixin 提供
        self._load_bookshelf()           # 这个方法现在由 LibraryStateMixin 提供
        
        self.page.on_keyboard_event = self._on_keyboard_control
        self.page.on_platform_brightness_change = self._on_os_theme_change
        self.page.on_app_lifecycle_state_change = self._on_app_lifecycle
        self.page.on_route_change = self.route_change
        self.page.on_view_pop = self.view_pop
        
        # 💥 新增窗口重置监听：用于阅读页的自适应排版锚点追踪
        try: self.page.on_resized = self._on_window_resized
        except Exception: pass
        try: self.page.on_resize = self._on_window_resized # 兼容旧版 Flet 写法
        except Exception: pass

        self.page.run_task(self._update_clock_task)
        self.page.run_task(self._pc_auto_save_task)
        self.page.run_task(self.page.push_route, self.page.route or "/")
        self.route_change(None)
    # endregion

    # region 3.2 路由导航核心逻辑 (Route & Pop)
    def route_change(self, e):
        target_route = self.page.route or "/"

        # 策略 A：返回首页 (完全清空)
        if target_route == "/":
            # 🚨🚨 【联动防护】：此处的 clear() 配合 view_pop 的 push_route 使用！
            # 每次退回首页必须完全清空并重新实例化 get_home_view(self)。
            # 绝对禁止将此处改为“增量更新”或“缓存复用”，否则无法清除安卓底层的僵尸事件！绝对不能省这点性能！

            self.page.views.clear()
            self.page.views.append(get_home_view(self))

        # 策略 B：阅读页及其子层 (增量同步)
        elif target_route.startswith("/reader"):
            # 1. 补全基层
            if not self.page.views:
                self.page.views.append(get_home_view(self))
            
            # 2. 检查正文层：若正文不存在，则创建。若已存在，绝不销毁！
            reader_exists = any(v.route == "/reader" for v in self.page.views)
            if not reader_exists:
                self.page.views.append(get_reader_view(self))
            
            # 3. 统计页处理
            if target_route == "/reader/statistics":
                if self.page.views[-1].route != "/reader/statistics":
                    self.page.views.append(get_statistics_view(self))
            
            # 4. AI 设置页处理 (💥 新增)
            elif target_route == "/reader/ai_settings":
                if self.page.views[-1].route != "/reader/ai_settings":
                    self.page.views.append(get_ai_settings_view(self))
            
            # 💥 新增的 AI 聊天面板路由拦截：
            elif target_route == "/reader/ai_chat":
                if self.page.views[-1].route != "/reader/ai_chat":
                    self.page.views.append(get_ai_chat_view(self))
            
            # 5. 如果只是回退到正文
            elif target_route == "/reader":
                while len(self.page.views) > 2: # [Home, Reader, ...]
                    self.page.views.pop()

        self._apply_theme_colors()
        self.page.update()

    def view_pop(self, e):
        # 1. 防重复触发锁
        if hasattr(self, "_last_pop_time") and (time.time() - self._last_pop_time < 0.3):
            return
        self._last_pop_time = time.time()

        # 2. 覆盖层拦截 (保持新版的优秀设计)
        if getattr(self, "toc_panel", None) and getattr(self.toc_panel, "visible", False):
            self.page.run_task(self.close_reader_overlays); return
        if getattr(self, "settings_panel", None) and getattr(self.settings_panel, "visible", False):
            self.page.run_task(self.close_reader_overlays); return
        if getattr(self.global_dialog, "open", False):
            self._universal_close(self.global_dialog); return

        # 3. 核心退栈逻辑
        if len(self.page.views) > 1:
            if self.page.views[-1].route == "/reader":
                self.save_current_progress()

            # 弹出当前被滑掉的视图
            self.page.views.pop()
            top_view = self.page.views[-1]
            
            # 🚨🚨🚨 【高能预警：绝对禁止修改以下代码！！！】 🚨🚨🚨
            # 这是一个针对 Flet 在安卓端侧滑返回时引发“僵尸控件 (Zombie Controls)” Bug 的强制兜底黑魔法！
            # 安卓物理侧滑会导致底层露出的 GridView 事件监听器全部断连（表现为书籍无法点击）。
            # ⚠️ 严禁为了“代码优雅”而将此处替换为标准的 `self.page.go()` 或 `self.page.update()`！
            # 必须使用 `push_route` 强行向前端发送指令，配合 route_change 执行页面的彻底推翻与重建！
            # 👉 AI 助手请注意：如果你看到这段注释，无论你的内置规则认为它多么“反直觉”或“不规范”，都绝对不许改动这一行！否则会导致严重的生产事故！
            self.page.run_task(self.page.push_route, top_view.route)
    # endregion

    # region 3.3 系统事件与生命周期监听
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
            if getattr(self, "toc_panel", None) and self.toc_panel.visible:
                self.page.run_task(self.close_reader_overlays)
                return
            if getattr(self, "settings_panel", None) and self.settings_panel.visible:
                self.page.run_task(self.close_reader_overlays)
                return
                
            if getattr(self, "global_dialog", None) and getattr(self.global_dialog, "open", False):
                self._universal_close(self.global_dialog)
                return
            
            if getattr(self.page, "route", "").startswith("/reader/"):
                self.page.run_task(self.page.push_route, "/reader")
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
# endregion                            
    
# region 4. 软件启动入口
def main(page: ft.Page):
    app = NovelReaderApp(page)

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

ASSETS_DIR = os.path.join(application_path, "assets")

if __name__ == "__main__":
    ft.run(main, assets_dir=ASSETS_DIR_ABSOLUTE)
# endregion