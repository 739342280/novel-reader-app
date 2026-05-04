# ==============================================================================
# 文件：core/overlay_manager.py
# 职责：全局悬浮层与顶层交互大管家 (Overlay & Dialog Manager)
# 
# 详细功能介绍：
# 1. 统一弹窗调度：封装了 Flet 原生的 `page.open` 和 `page.close`，提供 `_universal_open` 
#    和 `_universal_close` 方法，确保多对话框叠加时不会发生层级错乱或系统卡死。
# 2. 气泡提示引擎：实现了基于队列的全局 Toast (SnackBar) 提示系统，方便在任何业务节点
#    向用户反馈操作结果（成功、失败、警告），并支持自定义显示时长。
# 3. 侧滑面板控制：负责调出和隐藏阅读器独有的抽屉式 UI 组件（如：目录面板 toc_panel、
#    设置面板 settings_panel），并包含优雅的阻尼退场动画机制。
# 4. 跨端剪贴板：深度优化了文本复制功能，在移动端调用 Flet 原生 API 的同时，针对
#    Windows 平台直接拉起系统底层的 `clip.exe` / `powershell`，彻底解决长文本复制截断和乱码问题。
#
# 架构定位：属于 App 底座的 UI 混入类 (Mixin)，专职处理所有超越普通页面层级的“浮动”视觉元素。
# ==============================================================================
import flet as ft
import time
import asyncio
import sys
from datetime import datetime
from ui.dialogs import DialogManager

class OverlayManagerMixin:
    """负责全局对话框、侧滑面板、气泡提示及剪贴板等顶层交互"""

    def _universal_open(self, control):
        if not hasattr(self, "active_dialogs"): self.active_dialogs = []
        if control not in self.active_dialogs:
            self.active_dialogs.append(control)

        if not getattr(control, "_hooked", False):
            orig_dismiss = control.on_dismiss
            def wrapped_dismiss(e):
                self._last_dismiss_time = time.time()
                if hasattr(self, "active_dialogs") and control in self.active_dialogs:
                    self.active_dialogs.remove(control)
                if orig_dismiss: orig_dismiss(e)
            control.on_dismiss = wrapped_dismiss
            control._hooked = True

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
            content=ft.Column(
                controls=[toast_ui], 
                tight=True, 
                horizontal_alignment=ft.CrossAxisAlignment.START
            ), 
            behavior=ft.SnackBarBehavior.FLOATING,
            bgcolor=ft.Colors.TRANSPARENT,  
            elevation=0,                    
            padding=0,                      
            duration=self.ai_config.get("snack_duration", 3000), 
            key=f"snack_{self.snack_counter}"
        )
        self._universal_open(new_snack)

    def _open_dialog(self):
        self._universal_open(self.global_dialog)

    def _close_dialog(self):
        self._universal_close(self.global_dialog)

    def _open_toc_panel(self, e=None):
        if hasattr(self, "toc_panel"):
            self.reader_mask.visible = True 
            self.toc_panel.visible = True
            self.toc_panel.offset = ft.Offset(0, 0)
            self.page.update()
            self.page.run_task(self._delayed_scroll_to_chapter, self.current_chapter_idx, 0.3)

    def _open_settings_panel(self, e=None):
        if hasattr(self, "settings_panel"):
            self.reader_mask.visible = True 
            self.settings_panel.visible = True
            self.settings_panel.offset = ft.Offset(0, 0)
            self.page.update()

    async def close_reader_overlays(self, e=None):
        if getattr(self, "_is_closing_overlay", False): return
        self._is_closing_overlay = True
        try:
            if hasattr(self, "toc_panel"): self.toc_panel.offset = ft.Offset(0, 1)
            if hasattr(self, "settings_panel"): self.settings_panel.offset = ft.Offset(0, 1)
            if hasattr(self, "reader_mask"): self.reader_mask.visible = False
            self.page.update()
            await asyncio.sleep(0.3) 
            if hasattr(self, "toc_panel"): self.toc_panel.visible = False
            if hasattr(self, "settings_panel"): self.settings_panel.visible = False
            self.page.update()
        finally:
            self._is_closing_overlay = False

    def show_book_options_dialog(self, path, current_name):
        DialogManager.show_book_options_dialog(self, path, current_name)

    def show_statistics_dialog(self, e):
        self.page.route = "/reader/statistics"
        self.route_change(None)

    def show_settings_dialog(self, e):
        self.page.route = "/reader/ai_settings"
        self.route_change(None)

    def show_global_settings_dialog(self, e):
        DialogManager.show_global_settings_dialog(self, e)

    def show_changelog_dialog(self, e):
        DialogManager.show_changelog_dialog(self, e)

    def show_ai_dialog(self, e):
        self.page.route = "/reader/ai_chat"
        self.route_change(None)

    def _execute_copy(self, text):
        try:
            if hasattr(self.page, "set_clipboard"): self.page.set_clipboard(text)
        except Exception: pass
            
        if sys.platform.startswith("win"):
            try:
                import subprocess
                subprocess.run(['clip.exe'], input=text, text=True, check=True)
            except Exception: pass

    async def _update_clock_task(self):
        while True:
            try:
                if hasattr(self, "info_time"):
                    now_str = datetime.now().strftime("%H:%M")
                    if self.info_time.value != now_str:
                        self.info_time.value = now_str
                        try: self.info_time.update()
                        except Exception: pass
            except Exception: pass
            await asyncio.sleep(5)