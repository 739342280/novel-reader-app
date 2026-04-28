import flet as ft
from datetime import datetime
import asyncio  

def get_reader_view(app):
    app.last_search_query = None

    app.search_tf = ft.TextField(label="搜索章节", height=40, on_change=app.filter_toc)
    app.toc_listview = ft.ListView(expand=True, spacing=2, key="toc_listview")
    
    app.reader_mask = ft.Container(
    expand=True,
    on_click=app.close_reader_overlays, # 点击即关闭
    bgcolor=ft.Colors.TRANSPARENT,      # 保持透明，或者可以设为 "#20000000" 来实现调暗效果
    visible=False                       # 初始隐藏
    )

    app.toc_panel = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text("📚 章节目录", size=20, weight=ft.FontWeight.BOLD),
                ft.IconButton(ft.Icons.CLOSE, on_click=app.close_reader_overlays)
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            app.search_tf, 
            app.toc_listview
        ], expand=True),
        padding=20,
        bgcolor="surface", # 必须有底色，否则透明
        border_radius=ft.BorderRadius.only(top_left=28, top_right=28),
        shadow=ft.BoxShadow(blur_radius=20, color="#80000000"),
        left=0, right=0, bottom=0,
        height=app.page.height * 0.7 if app.page.height else 600,
        offset=ft.Offset(0, 1), # 默认藏在屏幕下方 100% 处
        animate_offset=ft.Animation(300, ft.AnimationCurve.DECELERATE),
        visible=False
    )

    app.font_size_text = ft.Text(str(app.font_size), weight=ft.FontWeight.BOLD)
    app.line_height_text = ft.Text(f"{app.line_height:.1f}", weight=ft.FontWeight.BOLD)
    app.para_spacing_text = ft.Text(str(app.paragraph_spacing), weight=ft.FontWeight.BOLD)
    app.letter_spacing_text = ft.Text(f"{app.letter_spacing:.1f}", weight=ft.FontWeight.BOLD)

    def set_bg_preset(bg, text, bg_image=None):
        app.update_reader_appearance(bg=bg, text=text, bg_image=bg_image)
        app._sync_bg_highlight()

    def set_font_preset(font_name):
        app.update_reader_appearance(font=font_name)
        app._sync_font_highlight()

    app.bg_btn_white = ft.Container(width=30, height=30, bgcolor="#FFFFFF", border_radius=15, tooltip="纯白", on_click=lambda _: set_bg_preset("#FFFFFF", "#212121"), border=ft.Border.all(1, ft.Colors.GREY_400))
    app.bg_btn_kraft1 = ft.Container(
        width=30, height=30, bgcolor="#D4A373", border_radius=15, tooltip="牛皮纸一", 
        image=ft.DecorationImage(src="backgrounds/牛皮纸_thumb.jpg", fit="cover"),
        on_click=lambda _: set_bg_preset("#D4A373", "#3E2723", "backgrounds/牛皮纸.jpg"), border=ft.Border.all(1, ft.Colors.GREY_400))
    app.bg_btn_kraft2 = ft.Container(
        width=30, height=30, bgcolor="#CBB28C", border_radius=15, tooltip="牛皮纸二", 
        image=ft.DecorationImage(src="backgrounds/牛皮纸_thumb2.jpg", fit="cover"),
        on_click=lambda _: set_bg_preset("#CBB28C", "#3E2723", "backgrounds/牛皮纸2.jpg"), border=ft.Border.all(1, ft.Colors.GREY_400))
    app.bg_btn_kraft3 = ft.Container(
        width=30, height=30, bgcolor="#E8DCC8", border_radius=15, tooltip="牛皮纸三", 
        image=ft.DecorationImage(src="backgrounds/牛皮纸_thumb3.jpg", fit="cover"),
        on_click=lambda _: set_bg_preset("#E8DCC8", "#3E2723", "backgrounds/牛皮纸3.jpg"), border=ft.Border.all(1, ft.Colors.GREY_400))
    app.bg_btn_yellow = ft.Container(width=30, height=30, bgcolor="#F5F5DC", border_radius=15, tooltip="米黄", on_click=lambda _: set_bg_preset("#F5F5DC", "#3E2723"), border=ft.Border.all(1, ft.Colors.GREY_400))
    app.bg_btn_green = ft.Container(width=30, height=30, bgcolor="#CCE8CF", border_radius=15, tooltip="护眼", on_click=lambda _: set_bg_preset("#CCE8CF", "#1B5E20"), border=ft.Border.all(1, ft.Colors.GREY_400))
    
    bg_options = ft.Row([
        app.bg_btn_white, app.bg_btn_kraft1, app.bg_btn_kraft2, 
        app.bg_btn_kraft3, app.bg_btn_yellow, app.bg_btn_green
    ], alignment=ft.MainAxisAlignment.SPACE_AROUND, scroll=ft.ScrollMode.AUTO)

    app.font_btn_default = ft.TextButton(content=ft.Text("默认", size=15), on_click=lambda _: set_font_preset(None))
    app.font_btn_qihei = ft.TextButton(content=ft.Text("旗黑", font_family="汉仪旗黑", size=15), on_click=lambda _: set_font_preset("汉仪旗黑"))
    app.font_btn_zhongsong = ft.TextButton(content=ft.Text("中宋", font_family="汉仪中宋", size=15), on_click=lambda _: set_font_preset("汉仪中宋"))
    app.font_btn_zhengyuan = ft.TextButton(content=ft.Text("正圆", font_family="汉仪正圆", size=15), on_click=lambda _: set_font_preset("汉仪正圆"))

    font_options = ft.Row([
        app.font_btn_default, app.font_btn_qihei, app.font_btn_zhongsong, app.font_btn_zhengyuan
    ], alignment=ft.MainAxisAlignment.START, scroll=ft.ScrollMode.AUTO)

    # 【修改点 1】：强行压缩所有调整排版按钮的宽高(width=32, height=32)，并将顶层 Row 改为 SPACE_AROUND 均分布局
    typography_row = ft.Row([
        ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.REMOVE, on_click=lambda _: app.change_font(-1), icon_size=18, width=32, height=32),
                app.font_size_text,
                ft.IconButton(icon=ft.Icons.ADD, on_click=lambda _: app.change_font(1), icon_size=18, width=32, height=32),
            ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
            ft.Text("字号", size=12, color=ft.Colors.GREY_500)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),

        ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.LINEAR_SCALE, on_click=lambda _: app.change_letter_spacing(-0.5), icon_size=18, width=32, height=32, tooltip="字距-"),
                app.letter_spacing_text,
                ft.IconButton(icon=ft.Icons.LINEAR_SCALE, on_click=lambda _: app.change_letter_spacing(0.5), icon_size=18, width=32, height=32, tooltip="字距+"),
            ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
            ft.Text("字距", size=12, color=ft.Colors.GREY_500)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
        
        ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.FORMAT_LINE_SPACING, on_click=lambda _: app.change_line_height(-0.1), icon_size=18, width=32, height=32, tooltip="行距-"),
                app.line_height_text,
                ft.IconButton(icon=ft.Icons.FORMAT_LINE_SPACING, on_click=lambda _: app.change_line_height(0.1), icon_size=18, width=32, height=32, tooltip="行距+"),
            ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
            ft.Text("行距", size=12, color=ft.Colors.GREY_500)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),

        ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.VERTICAL_ALIGN_CENTER, on_click=lambda _: app.change_paragraph_spacing(-5), icon_size=18, width=32, height=32, tooltip="段距-"),
                app.para_spacing_text,
                ft.IconButton(icon=ft.Icons.VERTICAL_ALIGN_CENTER, on_click=lambda _: app.change_paragraph_spacing(5), icon_size=18, width=32, height=32, tooltip="段距+"),
            ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
            ft.Text("段距", size=12, color=ft.Colors.GREY_500)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
    ], alignment=ft.MainAxisAlignment.SPACE_AROUND)

    def on_system_theme_switch_change(e):
        app.follow_system_theme = e.control.value
        if app.follow_system_theme:
            app.page.theme_mode = ft.ThemeMode.SYSTEM
        else:
            is_dark = str(app.page.platform_brightness).lower().endswith("dark")
            if is_dark:
                app.page.theme_mode = ft.ThemeMode.DARK
                app.manual_theme_mode = "dark"
            else:
                app.page.theme_mode = ft.ThemeMode.LIGHT
                app.manual_theme_mode = "light"
        app.page.update()
        app.sync_theme_btn_ui()
        app._sync_font_highlight() 
        app._sync_bg_highlight()
        app._apply_theme_colors() 
        app._save_config_to_appdata()

    app.system_theme_switch = ft.Switch(
        value=app.follow_system_theme, 
        on_change=on_system_theme_switch_change,
        active_color=ft.Colors.BLUE,
        scale=0.85 
    )

    theme_switch_row = ft.Row([
        ft.Text("跟随系统主题", size=14, weight=ft.FontWeight.BOLD),
        app.system_theme_switch
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

    app.btn_copy_current = ft.ElevatedButton(
        content=ft.Row([ft.Icon(ft.Icons.COPY, size=18), ft.Text("复制本章", size=13)], alignment=ft.MainAxisAlignment.CENTER),
        on_click=app.copy_current,
    )

    app.settings_panel = ft.Container(
        padding=12,
        bgcolor="surface",
        border_radius=ft.BorderRadius.only(top_left=28, top_right=28),
        shadow=ft.BoxShadow(blur_radius=20, color="#80000000"),
        left=0, right=0, bottom=0,
        offset=ft.Offset(0, 1), # 默认藏在屏幕下方
        animate_offset=ft.Animation(300, ft.AnimationCurve.DECELERATE),
        visible=False,
        content=ft.Column([
            ft.Row([
                ft.Text("排版调整", size=14, weight=ft.FontWeight.BOLD),
                ft.IconButton(ft.Icons.CLOSE, on_click=app.close_reader_overlays)
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
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
            app.btn_copy_current
        ], tight=True, scroll=ft.ScrollMode.AUTO, spacing=4) 
    )

    app.top_bar_book_name = ft.Text(app.current_book_name, size=13, color=ft.Colors.GREY_500, overflow=ft.TextOverflow.ELLIPSIS)
    app.top_bar_chapter_name = ft.Text("", size=17, weight=ft.FontWeight.BOLD, overflow=ft.TextOverflow.ELLIPSIS)

    app.btn_more = ft.PopupMenuButton(
        icon=ft.Icons.MORE_VERT,
        tooltip="菜单",
        items=[
            ft.PopupMenuItem(
                content=ft.Row([ft.Icon(ft.Icons.BAR_CHART), ft.Text("阅读统计")], spacing=10),
                on_click=app.show_statistics_dialog
            ),
            ft.PopupMenuItem(
                content=ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME), ft.Text("AI 设置")], spacing=10),
                on_click=app.show_settings_dialog
            ),
        ]
    )

    app.reader_top_bar = ft.Container(
        top=0, left=0, right=0,
        content=ft.Row([
            ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=app.go_back_home),
            ft.Column([
                app.top_bar_book_name,
                app.top_bar_chapter_name
            ], expand=True, spacing=2, horizontal_alignment=ft.CrossAxisAlignment.START, alignment=ft.MainAxisAlignment.CENTER),
            app.btn_more  
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding(top=40, left=10, right=10, bottom=10),
        bgcolor="surface",
        shadow=ft.BoxShadow(blur_radius=8, color="#40000000", offset=ft.Offset(0, 2)), 
        offset=ft.Offset(0, 0),
        animate_offset=ft.Animation(300, ft.AnimationCurve.DECELERATE)
    )

    app.info_chapter_name = ft.Text("", size=12, color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER, overflow=ft.TextOverflow.ELLIPSIS)
    app.info_time = ft.Text(datetime.now().strftime("%H:%M"), size=12, color=ft.Colors.GREY_500, text_align=ft.TextAlign.RIGHT)
    app.info_progress = ft.Text("", size=12, color=ft.Colors.GREY_500, text_align=ft.TextAlign.LEFT)
    
    app.info_bar = ft.Container(
        content=ft.Row([
            ft.Container(content=app.info_progress, expand=1, alignment=ft.Alignment(-1, 0)),
            ft.Container(content=app.info_chapter_name, expand=2, alignment=ft.Alignment(0, 0)),
            ft.Container(content=app.info_time, expand=1, alignment=ft.Alignment(1, 0))
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        padding=ft.Padding(left=20, right=20, top=2, bottom=12),
        on_click=app.toggle_immersive,
        bgcolor=ft.Colors.TRANSPARENT
    )

    app.text_panel = ft.Container(
        padding=ft.Padding(left=20, right=4, top=35, bottom=0),
        on_click=app.toggle_immersive, 
        bgcolor=ft.Colors.TRANSPARENT,
        expand=True
    )

    app.reading_base_layer = ft.Container(
        top=0, bottom=0, left=0, right=0,
        bgcolor=app.bg_color, 
        image=ft.DecorationImage(
            src=app.bg_image,
            repeat="repeat"
        ) if app.bg_image else None,
        content=ft.Column([
            app.text_panel,
            app.info_bar
        ], spacing=0)
    )

    def toggle_app_theme(e):
        app.follow_system_theme = False
        if hasattr(app, "system_theme_switch"):
            app.system_theme_switch.value = False
            try: app.system_theme_switch.update()
            except Exception: pass

        is_dark = app._get_is_dark_mode()
        if is_dark:
            app.page.theme_mode = ft.ThemeMode.LIGHT
            app.manual_theme_mode = "light"
        else:
            app.page.theme_mode = ft.ThemeMode.DARK
            app.manual_theme_mode = "dark"
        app.page.update()
        
        app.sync_theme_btn_ui()
        app._sync_font_highlight() 
        app._sync_bg_highlight()
        app._apply_theme_colors() 
        app._save_config_to_appdata()

    # 💥 强制修正：全部替换为真实存在的 TextButton / ElevatedButton，并将点击事件指向新方法
    app.theme_btn = ft.TextButton(
        content=ft.Text("日间"), icon=ft.Icons.LIGHT_MODE, on_click=toggle_app_theme,
        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8)) 
    )
    app.sync_theme_btn_ui()

    app.btn_toc = ft.TextButton(
        content=ft.Text("目录"), icon=ft.Icons.MENU_BOOK, on_click=app._open_toc_panel,
        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8))
    )
    
    app.btn_settings = ft.TextButton(
        content=ft.Text("界面"), icon=ft.Icons.FORMAT_SIZE, on_click=app._open_settings_panel,
        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=8))
    )

    app.btn_prev = ft.TextButton(
        content=ft.Text("上一章"), icon=ft.Icons.NAVIGATE_BEFORE, on_click=app.load_prev,
        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=12))
    )
    
    app.btn_next = ft.TextButton(
        content=ft.Text("下一章"), icon=ft.Icons.NAVIGATE_NEXT, on_click=app.load_next,
        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=12))
    )

    app.reader_bottom_bar = ft.Container(
        bottom=0, left=0, right=0, padding=10, bgcolor="surface",
        shadow=ft.BoxShadow(blur_radius=8, color="#40000000", offset=ft.Offset(0, -2)), 
        content=ft.Column([
            ft.Row([app.btn_prev, app.btn_next], alignment=ft.MainAxisAlignment.SPACE_AROUND),
            ft.Row([
                app.btn_toc,
                app.theme_btn,
                ft.ElevatedButton(
                    content=ft.Text("AI总结"), icon=ft.Icons.AUTO_AWESOME, on_click=app.show_ai_dialog, 
                    style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.DEEP_PURPLE_400, padding=ft.Padding.symmetric(horizontal=8))
                ),
                app.btn_settings
            ], alignment=ft.MainAxisAlignment.SPACE_AROUND)
        ], tight=True, spacing=10),
        offset=ft.Offset(0, 0), animate_offset=ft.Animation(300, ft.AnimationCurve.DECELERATE)
    )

    app.reader_view = ft.Stack([
        app.reading_base_layer,
        app.reader_mask,  
        app.reader_top_bar,
        app.reader_bottom_bar,
        app.toc_panel,      # 新增
        app.settings_panel  # 新增
    ], expand=True, key="reader_view_main_stack")
    
    app._apply_theme_colors() 
    app._sync_bg_highlight()
    app._sync_font_highlight()

    async def lazy_load_chapter():
        await asyncio.sleep(0.05)
        if app.engine.chapters_info:
            app.load_chapter(app.current_chapter_idx, target_offset=app.current_scroll_offset)

    app.page.run_task(lazy_load_chapter)

    return ft.View(
        route="/reader",
        controls=[
            ft.Container(content=app.reader_view, expand=True)
        ],
        padding=0,
        bgcolor="surface" 
    )