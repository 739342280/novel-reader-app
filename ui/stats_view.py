import flet as ft

def get_statistics_view(app):
    if not app.engine.chapters_info:
        return ft.View(route="/reader/statistics", controls=[ft.Text("暂无数据")])

    total_words = len("".join(app.engine.full_text_content.split()))
    total_chaps = len(app.engine.chapters_info)
    
    vols = set(ch.get('volume', '') for ch in app.engine.chapters_info)
    total_vols = len(vols)

    current_idx = app.current_chapter_idx
    curr_ch_info = app.engine.chapters_info[current_idx]
    curr_vol = curr_ch_info.get('volume', '')

    curr_chap_words = len("".join(app.engine.get_chapter_text(current_idx).split()))

    total_read_words = 0
    vol_total_words = 0
    vol_read_words = 0

    max_ext = getattr(app, "current_max_scroll_extent", 0.0)
    pct = 0.0
    if max_ext > 0:
        pct = min(1.0, max(0.0, app.current_scroll_offset / max_ext))

    for i, ch in enumerate(app.engine.chapters_info):
        words = len("".join(app.engine.get_chapter_text(i).split()))
        
        is_curr_vol = (ch.get('volume', '') == curr_vol)
        if is_curr_vol:
            vol_total_words += words

        if i < current_idx:
            total_read_words += words
            if is_curr_vol:
                vol_read_words += words
        elif i == current_idx:
            read_part = int(words * pct)
            total_read_words += read_part
            if is_curr_vol:
                vol_read_words += read_part

    total_unread_words = total_words - total_read_words
    vol_unread_words = vol_total_words - vol_read_words
    
    def go_back(e):
        # 🚨 【路由纪律：禁止修改】：统一调用主控制器的 view_pop 进行退栈。
        # 严禁在此处直接使用 app.page.go("/reader") 或 push_route，以避免与安卓原生弹栈动画发生时序撕裂。
        app.view_pop(None)

    appbar = ft.AppBar(
        leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=go_back),
        title=ft.Text("阅读统计", weight=ft.FontWeight.BOLD, size=18),
        center_title=True,
        bgcolor="surfaceVariant", # 使用 MD3 字符串变量
    )

    stat_content = ft.Column([
        ft.ListTile(leading=ft.Icon(ft.Icons.BOOKMARK_OUTLINE), title=ft.Text(f"卷数：{total_vols}"), dense=True),
        ft.ListTile(leading=ft.Icon(ft.Icons.FORMAT_LIST_NUMBERED), title=ft.Text(f"章节数：{total_chaps}"), dense=True),
        ft.ListTile(leading=ft.Icon(ft.Icons.TEXT_SNIPPET_OUTLINED), title=ft.Text(f"总字数：{total_words:,}"), dense=True),
        ft.ListTile(leading=ft.Icon(ft.Icons.FOLDER_OPEN), title=ft.Text(f"本卷字数：{vol_total_words:,}"), dense=True),
        ft.ListTile(leading=ft.Icon(ft.Icons.ARTICLE_OUTLINED), title=ft.Text(f"本章字数：{curr_chap_words:,}"), dense=True),
        
        ft.Divider(height=20, thickness=1, color="outlineVariant"), 
        
        # 💥 终极修复：彻底抛弃 ft.colors 和 ft.Colors 枚举，直接使用通用标准颜色字符串
        ft.ListTile(leading=ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color="green"), title=ft.Text(f"已读：{total_read_words:,}"), dense=True),
        ft.ListTile(leading=ft.Icon(ft.Icons.PENDING_OUTLINED, color="orange"), title=ft.Text(f"未读：{total_unread_words:,}"), dense=True),
        ft.ListTile(leading=ft.Icon(ft.Icons.LIBRARY_BOOKS), title=ft.Text(f"本卷已读：{vol_read_words:,}"), dense=True),
        ft.ListTile(leading=ft.Icon(ft.Icons.LIBRARY_BOOKS_OUTLINED), title=ft.Text(f"本卷未读：{vol_unread_words:,}"), dense=True),
    ], spacing=0)

    main_card = ft.Card(
        content=ft.Container(
            content=stat_content,
            padding=ft.padding.symmetric(vertical=10, horizontal=5)
        ),
        elevation=2,
        margin=ft.margin.all(15)
    )

    return ft.View(
        route="/reader/statistics",
        appbar=appbar,
        controls=[
            ft.Container(
                content=main_card,
                expand=True,
                alignment=ft.Alignment(0, -1) 
            )
        ],
        bgcolor="surface", # 使用 MD3 字符串变量
        padding=0
    )