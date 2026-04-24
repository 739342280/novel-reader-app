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

        log_text = """【v0.4.4】上帝类代码结构重塑
- (优化) 对高达 1200 行的主控制器进行视觉层架构大扫除。划定六大专属业务防区 (Region)，彻底根治“找函数如大海捞针”的开发痛点，提升代码长效可维护性。
- (优化) 重塑生命周期承重墙 `load_chapter` 物理结构，划分布局生成、数据抽取与滚动触发三层物理隔离，防御潜在的时序竞态问题。

【v0.4.3】解析提速与架构打通
- (新增) TXT 目录结构缓存：首次解析书籍后将自动在本地生成目录索引。下次阅读同一本书时，将彻底跳过耗时的正则扫描流程，实现秒开阅读。
- (优化) 核心引擎解耦：支持从外部注入预解析数据，大幅降低 CPU 开销。

【v0.4.2】阅读统计与界面完善
- (新增) 章节名独立排版：正文内第一行章节名自动识别并独立进行加大加粗处理，左对齐排列，底部增加微小留白，拉开阅读层次感。
- (新增) 右上角“设置”菜单，加入基于文本去水（剔除空白符）的精确“阅读统计”功能，包含卷/章/全局与卷内维度的详尽已读未读数据。

【v0.4.0】沉浸式阅读交互大升级
- (新增) 正文尾部追加“下一章”无缝跳转按钮：当阅读到章节最末尾时，无需再唤出底侧菜单即可直接点击进入下一章，彻底打破跨章割裂感，保持心流沉浸。
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
        
        # --- 数据格式向后兼容升级 ---
        target_idx_str = str(target_idx)
        saved_data = app.current_book_summaries.get(target_idx_str, {})
        if isinstance(saved_data, str):
            saved_data = {"main": saved_data}
            app.current_book_summaries[target_idx_str] = saved_data

        # --- 对话与模式状态机 ---
        state = {
            "mode": "main",         
            "chat": [],             
            "is_streaming": False
        }

        # --- UI 控件声明 ---
        chat_list_col = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=15, expand=True)
        
        chat_input = ft.TextField(
            hint_text="追问AI本章细节...", 
            text_size=13,
            expand=True, dense=True, 
            content_padding=10, border_radius=20,
            on_submit=lambda _: send_message(None)
        )
        
        send_btn = ft.IconButton(icon=ft.Icons.SEND, icon_color="onSurface", on_click=lambda _: send_message(None))

        mode_btn_main = ft.TextButton(content=ft.Text("主线总结", color="onSurface"))
        mode_btn_char = ft.TextButton(content=ft.Text("人物梳理", color="onSurface"))
        mode_btn_clue = ft.TextButton(content=ft.Text("伏笔剖析", color="onSurface"))

        btn_regen = ft.Button(content=ft.Text(""), style=ft.ButtonStyle(bgcolor=ft.Colors.DEEP_PURPLE_400, color=ft.Colors.WHITE))
        
        btn_copy = ft.Button(content=ft.Text("复制", color="onSurface"))
        btn_close = ft.Button(content=ft.Text("关闭", color="onSurface"), on_click=lambda _: app._close_dialog())

        def update_mode_btns_ui():
            is_dark = app._get_is_dark_mode()
            
            active_bg = "#1AFFFFFF" if is_dark else "#1A000000"
            inactive_bg = ft.Colors.TRANSPARENT
            
            for btn, m in [(mode_btn_main, "main"), (mode_btn_char, "characters"), (mode_btn_clue, "clues")]:
                is_active = (state["mode"] == m)
                btn.style = ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    bgcolor=active_bg if is_active else inactive_bg,
                    elevation=0,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8)
                )
                try: btn.update()
                except Exception: pass

            # 【核心修改点】：增加 radius=30 的圆角边框，让复制和关闭按钮变得圆圆的
            action_bg = "#2C2C2C" if is_dark else "#F8F8F8"
            action_style = ft.ButtonStyle(
                bgcolor=action_bg,
                color="onSurface",
                elevation=0,
                shape=ft.RoundedRectangleBorder(radius=30),
                padding=ft.Padding.symmetric(horizontal=16, vertical=8)
            )
            btn_copy.style = action_style
            btn_close.style = action_style
            try: btn_copy.update()
            except Exception: pass
            try: btn_close.update()
            except Exception: pass

        def get_sys_prompt():
            if state["mode"] == "main": 
                return app.ai_config["prompt"]
            if state["mode"] == "characters": 
                return "提取本章出现的所有人物，用一句话标明他们的阵营、当前状态、以及与主角的关系。严禁脑补未发生的情节。"
            if state["mode"] == "clues": 
                return "找出本章看似不起眼的环境描写、对话停顿或异常行为，推测作者可能埋下的伏笔与线索。尽量精简干练。"

        def render_chat():
            chat_list_col.controls.clear()
            
            base_content = saved_data.get(state["mode"], "")
            if not base_content:
                base_content = "暂无内容，请点击下方按钮开始分析本章。\n\n*(注意：请确保已在首页设置中配置了 API Key)*"
                btn_regen.content.value = "总结本章"
            else:
                btn_regen.content.value = "重新总结"
                
            try: btn_regen.update()
            except Exception: pass
            
            chat_list_col.controls.append(
                ft.Container(
                    content=ft.Markdown(base_content, selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB),
                    bgcolor="surfaceVariant",
                    padding=12,
                    border_radius=8
                )
            )

            for msg in state["chat"]:
                if msg["role"] == "user":
                    chat_list_col.controls.append(
                        ft.Container(
                            content=ft.Text(msg["content"], color=ft.Colors.WHITE),
                            bgcolor=ft.Colors.BLUE_600,
                            padding=10, border_radius=8,
                            alignment=ft.Alignment.CENTER_RIGHT, 
                            margin=ft.margin.only(left=40)
                        )
                    )
                else:
                    chat_list_col.controls.append(
                        ft.Container(
                            content=ft.Markdown(msg["content"], selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB),
                            bgcolor=ft.Colors.TRANSPARENT,
                            padding=10, border_radius=8,
                            margin=ft.margin.only(right=40)
                        )
                    )
            
            try:
                chat_list_col.update()
            except Exception: pass

            async def safe_scroll():
                try: await chat_list_col.scroll_to(offset=-1, duration=100)
                except Exception: pass
            app.page.run_task(safe_scroll)

        def switch_mode(new_mode):
            if state["is_streaming"]: return
            state["mode"] = new_mode
            state["chat"].clear() 
            update_mode_btns_ui()
            render_chat()

        mode_btn_main.on_click = lambda _: switch_mode("main")
        mode_btn_char.on_click = lambda _: switch_mode("characters")
        mode_btn_clue.on_click = lambda _: switch_mode("clues")

        def generate_base(e):
            if not app.ai_config["key"]:
                app.show_snack_bar("⚠️ 请先配置 API Key")
                return
            if state["is_streaming"]: return

            state["is_streaming"] = True
            state["chat"].clear() 
            btn_regen.disabled = True
            
            btn_regen.content.value = "总结中..."
            saved_data[state["mode"]] = "✨ 大模型正在阅读本章并进行梳理，请稍候...\n\n"
            render_chat()
            try: btn_regen.update()
            except Exception: pass

            chapter_text = app.engine.get_chapter_text(target_idx)[:15000]
            messages = [{"role": "system", "content": f"{get_sys_prompt()}\n\n【参考文本开始】\n{chapter_text}\n【参考文本结束】"}]

            stream_buffer = [""]
            
            async def ui_updater():
                last_text = ""
                while state["is_streaming"]:
                    curr = stream_buffer[0]
                    if curr != last_text and curr:
                        try:
                            chat_list_col.controls[0].content.value = curr
                            chat_list_col.controls[0].content.update()
                            await chat_list_col.scroll_to(offset=-1, duration=0)
                        except Exception: pass
                        last_text = curr
                    await asyncio.sleep(0.05)
                if stream_buffer[0] != last_text and stream_buffer[0]:
                    try:
                        chat_list_col.controls[0].content.value = stream_buffer[0]
                        chat_list_col.controls[0].content.update()
                        await chat_list_col.scroll_to(offset=-1, duration=0)
                    except Exception: pass

            app.page.run_task(ui_updater)

            def on_chunk(delta):
                stream_buffer[0] += delta

            def on_complete(full):
                state["is_streaming"] = False
                saved_data[state["mode"]] = full
                app._save_book_summaries()
                try:
                    btn_regen.disabled = False
                    btn_regen.content.value = "重新总结"
                    btn_regen.update()
                except Exception: pass

            def on_error(err):
                state["is_streaming"] = False
                stream_buffer[0] = err
                saved_data[state["mode"]] = err
                try:
                    btn_regen.disabled = False
                    btn_regen.content.value = "重新总结"
                    btn_regen.update()
                except Exception: pass

            def is_active():
                return getattr(app.global_dialog, "open", False)

            threading.Thread(target=AIService.stream_chat, args=(app.ai_config, messages, on_chunk, on_complete, on_error, is_active), daemon=True).start()

        def send_message(e):
            if not app.ai_config["key"]:
                app.show_snack_bar("⚠️ 请先配置 API Key")
                return
            text = chat_input.value.strip()
            if not text or state["is_streaming"]: return
            
            chat_input.value = ""
            try: chat_input.update()
            except Exception: pass

            state["is_streaming"] = True
            state["chat"].append({"role": "user", "content": text})
            state["chat"].append({"role": "assistant", "content": "⏳ 思考中..."})
            render_chat()

            chapter_text = app.engine.get_chapter_text(target_idx)[:15000]
            
            messages = [{"role": "system", "content": f"{get_sys_prompt()}\n\n【参考文本开始】\n{chapter_text}\n【参考文本结束】"}]
            if saved_data.get(state["mode"]):
                messages.append({"role": "assistant", "content": saved_data[state["mode"]]})
            
            for msg in state["chat"][:-1]: 
                messages.append(msg)

            stream_buffer = [""]

            async def ui_updater():
                last_text = ""
                while state["is_streaming"]:
                    curr = stream_buffer[0]
                    if curr != last_text and curr:
                        try:
                            chat_list_col.controls[-1].content.value = curr
                            chat_list_col.controls[-1].content.update()
                            await chat_list_col.scroll_to(offset=-1, duration=0)
                        except Exception: pass
                        last_text = curr
                    await asyncio.sleep(0.05)
                
                if stream_buffer[0] != last_text and stream_buffer[0]:
                    try:
                        chat_list_col.controls[-1].content.value = stream_buffer[0]
                        chat_list_col.controls[-1].content.update()
                        await chat_list_col.scroll_to(offset=-1, duration=0)
                    except Exception: pass

            app.page.run_task(ui_updater)

            def on_chunk(delta):
                stream_buffer[0] += delta

            def on_complete(full):
                state["is_streaming"] = False
                state["chat"][-1]["content"] = full
            
            def on_error(err):
                state["is_streaming"] = False
                stream_buffer[0] = f"请求失败: {err}"
                state["chat"][-1]["content"] = stream_buffer[0]
            
            def is_active():
                return getattr(app.global_dialog, "open", False)

            threading.Thread(target=AIService.stream_chat, args=(app.ai_config, messages, on_chunk, on_complete, on_error, is_active), daemon=True).start()

        async def copy_result(e):
            content_to_copy = saved_data.get(state["mode"], "")
            
            if state["chat"]:
                content_to_copy += "\n\n--- 追问记录 ---\n"
                for msg in state["chat"]:
                    role_name = "【我】" if msg["role"] == "user" else "【AI】"
                    content_to_copy += f"\n{role_name}：\n{msg['content']}\n"

            if not content_to_copy.strip(): return
            app._execute_copy(content_to_copy.strip())
            app.show_snack_bar("✅ 已完整复制分析结果与对话")

            btn_copy.content.value = "复制成功"
            try: btn_copy.update()
            except Exception: pass
            
            await asyncio.sleep(2)
            btn_copy.content.value = "复制"
            try: btn_copy.update()
            except Exception: pass

        btn_regen.on_click = generate_base
        btn_copy.on_click = copy_result

        update_mode_btns_ui()
        render_chat()

        app.global_dialog.inset_padding = ft.Padding.symmetric(horizontal=12, vertical=24)
        app.global_dialog.content_padding = ft.Padding(left=20, top=15, right=4, bottom=15)
        
        app.global_dialog.title = ft.Text(f"✨ AI 助手 - {ch_info['title']}", size=16, weight=ft.FontWeight.BOLD)
        app.global_dialog.content = ft.Container(
            content=chat_list_col,
            width=600, height=400, bgcolor=ft.Colors.TRANSPARENT  
        )
        
        app.global_dialog.actions = [
            ft.Container(
                content=ft.Column([
                    ft.Row([mode_btn_main, mode_btn_char, mode_btn_clue], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Row([btn_regen, btn_copy, btn_close], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Row([chat_input, send_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                ], tight=True, spacing=10),
                width=600
            )
        ]
        
        app._open_dialog()