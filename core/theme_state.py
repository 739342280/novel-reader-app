# ==============================================================================
# 文件：core/theme_state.py
# 职责：阅读器排版与全局主题渲染引擎 (Theme & Layout Renderer)
# 
# 详细功能介绍：
# 1. 阅读排版核心：精确控制和动态计算阅读页面的每一项文本属性（字号 font_size、
#    行高 line_height、段间距 paragraph_spacing、字间距 letter_spacing）。
# 2. 深浅色模式中枢：监听系统级或用户强制设定的 Dark/Light Mode 切换，并负责
#    向各个子控件（如顶栏、阅读背景、对话框、按钮）下发对应的调色板。
# 3. 沉浸式阅读：一键触发全屏逻辑（toggle_immersive），动态推走 AppBar 和 BottomBar，
#    在移动端同时接管状态栏的沉浸式映射。
# 4. 样式复用库：提供如 `get_action_button_style` 等工厂方法，确保全局数百个
#    按钮和卡片在切换主题时能够保持视觉风格的绝对统一。
#
# 架构定位：属于 App 底座的视觉混入类 (Mixin)，是决定软件“颜值”和“护眼程度”的最高指挥官。
# ==============================================================================
import flet as ft

class ThemeRendererMixin:
    """负责管理 UI 主题渲染、深浅色模式切换、以及阅读器排版参数"""

    def get_action_button_style(self, padding=ft.Padding.symmetric(horizontal=16, vertical=8), text_color="onSurface", is_reader_btn=False):
        is_dark = self._get_is_dark_mode()
        
        # 恢复轻量级：只需极小的 1 值即可激活原生的精致阴影，不传的按钮保持 0
        curr_elevation = 1 if is_reader_btn else 0
        
        if is_dark:
            btn_bg_c = "#2C2C2C" 
        else:
            if not is_reader_btn:
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
                
        return ft.ButtonStyle(
            bgcolor=btn_bg_c, 
            color=text_color, 
            elevation=curr_elevation, 
            shape=ft.RoundedRectangleBorder(radius=30), 
            padding=padding
        )
    
    def update_reader_appearance(self, **kwargs):
        if "bg" in kwargs: self.bg_color = kwargs["bg"]
        if "bg_image" in kwargs: self.bg_image = kwargs["bg_image"]  
        if "text" in kwargs: self.reader_text_color = kwargs["text"]
        if "font" in kwargs: self.font_family = kwargs["font"]
        
        if hasattr(self, "reader_text_controls"):
            for ctrl in self.reader_text_controls:
                # 穿透盒子找文字
                target = ctrl.content if isinstance(ctrl, ft.Container) else ctrl
                target.font_family = self.font_family
                try: target.update()
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
                    target = ctrl.content if isinstance(ctrl, ft.Container) else ctrl
                    target.size = self.font_size
                    try: target.update()
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
                    target = ctrl.content if isinstance(ctrl, ft.Container) else ctrl
                    target.style = ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing)
                    try: target.update()
                    except Exception: pass
            if hasattr(self, "line_height_text"):
                self.line_height_text.value = f"{self.line_height:.1f}"
                try: self.line_height_text.update()
                except Exception: pass

    def change_paragraph_spacing(self, delta):
        new_spacing = int(self.paragraph_spacing + delta)
        if 0 <= new_spacing <= 50:
            self.paragraph_spacing = new_spacing
            if hasattr(self, "text_scroll_col"):
                self.text_scroll_col.spacing = self.paragraph_spacing
                try: self.text_scroll_col.update()
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
                    target = ctrl.content if isinstance(ctrl, ft.Container) else ctrl
                    target.style = ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing)
                    try: target.update()
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
        current_real_route = self.page.views[-1].route if self.page.views else "/"

        if current_real_route == "/":
            if hasattr(self, "global_dialog") and self.global_dialog:
                self.global_dialog.bgcolor = "surface"
                if getattr(self.global_dialog, "content", None) and isinstance(self.global_dialog.content, ft.Container):
                    self.global_dialog.content.bgcolor = "surface"
            return
        
        if current_real_route != "/reader":
            return
        
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

        current_real_route = self.page.views[-1].route if getattr(self.page, "views", None) else "/"
        in_reader = current_real_route == "/reader"
        dialog_bg_c = menu_c if in_reader else "surface"

        for sheet in [getattr(self, "global_dialog", None), getattr(self, "settings_panel", None), getattr(self, "toc_panel", None)]:
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
                target = ctrl.content if isinstance(ctrl, ft.Container) else ctrl
                if getattr(target, "color", None) != text_c:
                    target.color = text_c
                    try: target.update()
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
                if getattr(btn, "content", None):
                    if isinstance(btn.content, ft.Text):
                        btn.content.color = top_chap_c
                        try: btn.content.update()
                        except Exception: pass
                    elif isinstance(btn.content, ft.Row):
                        for item in btn.content.controls:
                            if isinstance(item, ft.Text) or isinstance(item, ft.Icon):
                                item.color = top_chap_c
                                try: item.update()
                                except Exception: pass
                
                btn.icon_color = top_chap_c
                btn.style = self.get_action_button_style(pad, text_color=top_chap_c, is_reader_btn=True)
                try: btn.update()
                except Exception: pass