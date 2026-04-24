import flet as ft

def get_home_view(app):
    header = ft.Container(
        content=ft.Row([
            ft.Text("📚 我的书架", size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
            ft.Container(expand=True),
            ft.IconButton(icon=ft.Icons.SETTINGS, tooltip="AI设置", on_click=app.show_settings_dialog),
            ft.IconButton(icon=ft.Icons.HISTORY, tooltip="更新日志", on_click=app.show_changelog_dialog),
        ]),
        padding=ft.Padding(left=30, top=50, right=30, bottom=10)
    )

    app.bookshelf_grid = ft.GridView(
        expand=True,
        max_extent=170,           
        child_aspect_ratio=0.72,  
        spacing=20,
        run_spacing=20,
        padding=30
    )
    
    app.status_text = ft.Text("等待导入...", size=12, color=ft.Colors.GREY_500, visible=False)
    app.progress_bar = ft.ProgressBar(width=400, value=0, visible=False)
    status_area = ft.Column([app.status_text, app.progress_bar], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    app.home_view = ft.Column([
        header,
        app.bookshelf_grid,
        ft.Container(status_area, alignment=ft.Alignment(0, 0), padding=10)
    ], expand=True)

    # 构建视图时自动拉取最新书架数据渲染
    app.refresh_bookshelf_ui()
    
    return ft.View(
        route="/",
        controls=[
            ft.Container(content=app.home_view, expand=True)
        ],
        padding=0,
        bgcolor="surface" 
    )