import flet as ft
import asyncio
import threading
from core.ai_service import AIService

class DialogManager:
    
    @staticmethod
    def show_book_options_dialog(app, path, current_name):
        app.global_dialog.modal = False
        app.global_dialog.inset_padding = None
        app.global_dialog.content_padding = None
        
        rename_tf = ft.TextField(label="重命名书籍", value=current_name)

        def on_save(e):
            new_name = rename_tf.value.strip()
            if new_name and new_name != current_name:
                app.rename_book(path, new_name)
                app.show_snack_bar("✅ 书名已更新")
            app._close_dialog()

        def confirm_delete(e):
            app.remove_from_bookshelf(path)
            app._close_dialog()
            app.show_snack_bar(f"✅ 《{current_name}》已移出书架")

        async def on_export(e):
            app._close_dialog()
            await app.trigger_export_picker(path, current_name)

        export_btn = ft.Button(
            content=ft.Row(
                [ft.Icon(ft.Icons.DOWNLOAD), ft.Text("导出书籍到本地")], 
                alignment=ft.MainAxisAlignment.CENTER
            ),
            on_click=on_export,
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_50, color=ft.Colors.BLUE_900)
        )

        app.global_dialog.title = ft.Text("书籍管理")
        app.global_dialog.content = ft.Column([
            rename_tf,
            ft.Container(height=5),
            export_btn,
            ft.Container(height=5),
            ft.Text("注：移出书架不会删除原文件，导出则会另存一份副本", size=12, color=ft.Colors.GREY)
        ], tight=True) 
        
        app.global_dialog.actions = [
            ft.Button(content=ft.Text("保存名称"), on_click=on_save),
            ft.Button(content=ft.Text("移出书架"), style=ft.ButtonStyle(color=ft.Colors.RED), on_click=confirm_delete),
            ft.Button(content=ft.Text("取消"), on_click=lambda _: app._close_dialog())
        ]
        app._open_dialog()

    @staticmethod
    def show_statistics_dialog(app, e):
        if not app.engine.chapters_info: return

        total_words = len("".join(app.engine.full_text_content.split()))
        total_chaps = len(app.engine.chapters_info)
        
        vols = set(ch['volume'] for ch in app.engine.chapters_info)
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

        app.global_dialog.modal = False
        app.global_dialog.inset_padding = ft.Padding.symmetric(horizontal=20, vertical=24)
        app.global_dialog.content_padding = ft.Padding(20, 20, 20, 10)

        app.global_dialog.title = ft.Text("阅读统计", size=18, weight=ft.FontWeight.BOLD)

        stat_content = ft.Column([
            ft.Text(f"卷数：{total_vols}", size=14),
            ft.Text(f"章节数：{total_chaps}", size=14),
            ft.Text(f"总字数：{total_words:,}", size=14),
            ft.Text(f"本卷字数：{vol_total_words:,}", size=14),
            ft.Text(f"本章字数：{curr_chap_words:,}", size=14),
            ft.Divider(height=10, thickness=0.5),
            ft.Text(f"已读：{total_read_words:,}", size=14),
            ft.Text(f"未读：{total_unread_words:,}", size=14),
            ft.Text(f"本卷已读：{vol_read_words:,}", size=14),
            ft.Text(f"本卷未读：{vol_unread_words:,}", size=14),
        ], tight=True, spacing=8)

        app.global_dialog.content = stat_content
        app.global_dialog.actions = [
            ft.Button(content=ft.Text("关闭"), on_click=lambda _: app._close_dialog())
        ]

        app._open_dialog()

    @staticmethod
    def show_settings_dialog(app, e):
        app.global_dialog.modal = False
        app.global_dialog.inset_padding = None
        app.global_dialog.content_padding = None

        url_tf = ft.TextField(label="API URL", value=app.ai_config["url"])
        key_tf = ft.TextField(label="API Key", value=app.ai_config["key"], password=True, can_reveal_password=True)
        model_tf = ft.TextField(label="模型名称", value=app.ai_config["model"])
        prompt_tf = ft.TextField(label="系统提示词", value=app.ai_config["prompt"], multiline=True, min_lines=4, max_lines=6)

        def save(e):
            app.ai_config["url"] = url_tf.value.strip()
            app.ai_config["key"] = key_tf.value.strip()
            app.ai_config["model"] = model_tf.value.strip()
            app.ai_config["prompt"] = prompt_tf.value.strip()
            app._save_config_to_appdata()
            app._close_dialog()
            app.show_snack_bar("✅ AI 配置已持久化保存")

        app.global_dialog.title = ft.Text("⚙️ AI 接口配置")
        app.global_dialog.content = ft.Column([url_tf, key_tf, model_tf, prompt_tf], tight=True)
        app.global_dialog.actions = [
            ft.Button(content=ft.Text("保存并关闭"), on_click=save),
            ft.Button(content=ft.Text("取消"), on_click=lambda _: app._close_dialog())
        ]
        app._open_dialog()

    @staticmethod
    def show_changelog_dialog(app, e):
        app.global_dialog.modal = False
        app.global_dialog.inset_padding = None
        app.global_dialog.content_padding = ft.Padding(left=20, top=24, right=4, bottom=24)

        log_text = """【v0.4.3】解析提速与架构打通
- (新增) TXT 目录结构缓存：首次解析书籍后将自动在本地生成目录索引。下次阅读同一本书时，将彻底跳过耗时的正则扫描流程，实现秒开阅读。
- (优化) 核心引擎解耦：支持从外部注入预解析数据，大幅降低 CPU 开销。

【v0.4.2】阅读统计与界面完善
- (新增) 章节名独立排版：正文内第一行章节名自动识别并独立进行加大加粗处理，左对齐排列，底部增加微小留白，拉开阅读层次感。
- (新增) 右上角“设置”菜单，加入基于文本去水（剔除空白符）的精确“阅读统计”功能，包含卷/章/全局与卷内维度的详尽已读未读数据。

【v0.4.0】沉浸式阅读交互大升级
- (新增) 正文尾部追加“下一章”无缝跳转按钮：当阅读到章节最末尾时，无需再唤出底侧菜单即可直接点击进入下一章，彻底打破跨章割裂感，保持心流沉浸。

【v0.3.19】核心阅读体验与界面精调
- (修复) 夜间模式沉浸感打磨：修复了夜间强制黑屏时，文字颜色依然保持日间色彩的 Bug；修复了顶部菜单文字在夜间模式下不可见的 Bug。
- (优化) 重新提取并校准了“牛皮纸一”和“牛皮纸二”的 Base 底色，使其与真实图片材质更加贴合。
- (修复) 彻底移除了导致阅读总进度“提前增加”的分子加一算法，精准还原真实阅读比例。
- (新增) 精细化总进度百分比：总进度不再只按章节跳动，现在会实时包含“本章内的像素级滚动百分比”，精确到 0.1% 防抖刷新，掌控感拉满。
- (新增) 卷名强化识别：底层分析引擎新增卷名状态机，并在书架界面的卡片及阅读页顶部菜单双重显性展示“卷+章”。
- (优化) 智能日夜间 UI 联动：日间模式下，顶底菜单会自动变色并融入当前选定的背景纯色中；夜间模式则强行压制所有彩色背景为纯黑，真正做到深夜护眼。
"""
        app.global_dialog.title = ft.Text("历史更新记录")
        
        app.global_dialog.content = ft.Container(
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
        app.global_dialog.actions = [
            ft.Button(content=ft.Text("关闭"), on_click=lambda _: app._close_dialog())
        ]
        app._open_dialog()

    @staticmethod
    def show_ai_dialog(app, e):
        if not app.engine.chapters_info: return
        
        app.global_dialog.modal = True
        
        target_idx = app.current_chapter_idx
        ch_info = app.engine.chapters_info[target_idx]
        
        existing_summary = app.current_book_summaries.get(str(target_idx), "")
        
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
        
        btn_start = ft.Button(
            content=ft.Text(btn_text), 
            style=ft.ButtonStyle(bgcolor=ft.Colors.DEEP_PURPLE_400, color=ft.Colors.WHITE)
        )
        btn_copy = ft.Button(
            content=ft.Text("📋 复制"), 
            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_500, color=ft.Colors.WHITE)
        )

        def start_ai(e):
            if not app.ai_config["key"]:
                app.show_snack_bar("⚠️ 请先配置 API Key")
                return
            
            btn_start.disabled = True
            btn_start.content.value = "思考中..."
            result_text.value = "✨ 大模型正在阅读本章并进行多维度梳理，请稍候...\n\n"
            
            try:
                btn_start.update()
                result_text.update()
            except Exception:
                pass

            chapter_text = app.engine.get_chapter_text(target_idx)[:15000]
            
            stream_buffer = [""] 
            is_streaming = [True]

            async def safe_scroll_task():
                while is_streaming[0]:
                    try:
                        await ai_scroll_col.scroll_to(offset=-1, duration=0)
                    except Exception:
                        pass
                    await asyncio.sleep(0.1)

            async def ui_updater():
                app.page.run_task(safe_scroll_task)
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

            def on_chunk(text_delta):
                stream_buffer[0] += text_delta
                
            def on_complete(full_text):
                is_streaming[0] = False
                app.current_book_summaries[str(target_idx)] = full_text
                app._save_book_summaries()
                
            def on_error(error_msg):
                is_streaming[0] = False
                stream_buffer[0] = error_msg
                
            def is_active():
                return getattr(app.global_dialog, "open", False)

            app.page.run_task(ui_updater)
            threading.Thread(
                target=AIService.stream_summary, 
                args=(app.ai_config, chapter_text, on_chunk, on_complete, on_error, is_active), 
                daemon=True
            ).start()

        async def copy_result(e):
            app._execute_copy(result_text.value)
            app.show_snack_bar("✅ 总结已复制")

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

        app.global_dialog.inset_padding = ft.Padding.symmetric(horizontal=12, vertical=24)
        app.global_dialog.content_padding = ft.Padding(left=20, top=15, right=4, bottom=15)
        
        app.global_dialog.title = ft.Text(f"✨ AI 总结 - {ch_info['title']}", size=16, weight=ft.FontWeight.BOLD)
        app.global_dialog.content = ft.Container(
            content=ai_scroll_col,
            width=600, height=400, bgcolor=ft.Colors.TRANSPARENT  
        )
        
        app.global_dialog.actions = [
            ft.Container(
                content=ft.Row(
                    controls=[
                        btn_start, 
                        btn_copy, 
                        ft.Button(content=ft.Text("关闭"), on_click=lambda _: app._close_dialog())
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                    wrap=True
                ),
                width=600
            )
        ]
        
        app._open_dialog()