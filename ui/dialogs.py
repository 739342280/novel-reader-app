import flet as ft
import asyncio
import threading
import time
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

        # 💥 修正：ft.Button 替换为 ft.ElevatedButton
        export_btn = ft.ElevatedButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.DOWNLOAD), ft.Text("导出书籍到本地")], 
                alignment=ft.MainAxisAlignment.CENTER
            ),
            on_click=on_export,
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_50, color=ft.Colors.BLUE_900)
        )

        app.global_dialog.title = ft.Text("书籍管理", size=18, weight=ft.FontWeight.BOLD, color="onSurface")
        app.global_dialog.content = ft.Column([
            rename_tf,
            ft.Container(height=5),
            export_btn,
            ft.Container(height=5),
            ft.Text("注：移出书架不会删除原文件，导出则会另存一份副本", size=12, color=ft.Colors.GREY)
        ], tight=True) 
        
        # 💥 修正：ft.Button 替换为 ft.TextButton
        app.global_dialog.actions = [
            ft.TextButton(content=ft.Text("保存名称"), on_click=on_save),
            ft.TextButton(content=ft.Text("移出书架"), style=ft.ButtonStyle(color=ft.Colors.RED), on_click=confirm_delete),
            ft.TextButton(content=ft.Text("取消"), on_click=lambda _: app._close_dialog())
        ]
        app._open_dialog()

   
    @staticmethod
    def show_global_settings_dialog(app, e):
        app.global_dialog.modal = False
        app.global_dialog.inset_padding = None
        app.global_dialog.content_padding = ft.padding.only(left=20, top=15, right=20, bottom=15)

        # 💥 修正：ft.Button 替换为 ft.ElevatedButton
        backup_row = ft.Row([
            ft.ElevatedButton(content=ft.Row([ft.Icon(ft.Icons.UPLOAD), ft.Text("导出备份", color="onSurface")]), on_click=app.export_app_data, style=app.get_action_button_style()),
            ft.ElevatedButton(content=ft.Row([ft.Icon(ft.Icons.DOWNLOAD), ft.Text("恢复备份", color="onSurface")]), on_click=app.import_app_data, style=app.get_action_button_style())
        ], alignment=ft.MainAxisAlignment.SPACE_AROUND)

        app.global_dialog.title = ft.Text("⚙️ 全局设置", size=18, weight=ft.FontWeight.BOLD, color="onSurface")
        app.global_dialog.content = ft.Column([
            ft.Text("数据安全", weight=ft.FontWeight.BOLD, size=14, color="onSurface"),
            ft.Text("本地备份包含所有书籍、阅读进度及 AI 总结数据", size=12, color=ft.Colors.GREY_500),
            ft.Container(height=5),
            backup_row
        ], tight=True)
        
        # 💥 修正：ft.Button 替换为 ft.TextButton
        app.global_dialog.actions = [
            ft.TextButton(content=ft.Text("关闭", color="onSurface"), on_click=lambda _: app._close_dialog(), style=app.get_action_button_style())
        ]
        app._open_dialog()

    @staticmethod
    def show_changelog_dialog(app, e):
        app.global_dialog.modal = False
        app.global_dialog.inset_padding = None
        app.global_dialog.content_padding = ft.padding.only(left=20, top=24, right=4, bottom=24)

        log_text = """【v0.4.6】端云混合 RAG 架构启航
- (重构) 知识库控制中心：重塑原有的 AI 接口面板，全新引入三段式 Tab 视图。
- (新增) 向量引擎接入底盘：支持自由切换云端 Embedding 接口或本地大模型，为全书 RAG（检索增强生成）铺平道路。
- (新增) 本书知识库管理面板：支持动态查看与管控当前阅读书籍的向量索引状态。

【v0.4.5】功能扩展与交互优化
- (新增) 键盘快捷键控制：PC端支持左右键切换章节，上下键与空格键控制正文平滑滚动，大幅提升桌面端手感。
- (新增) 应用数据全局备份与恢复：支持一键导出所有 JSON 配置、书籍文件及 AI 总结记录，换机无忧。

【v0.4.4】上帝类代码结构重塑
- (优化) 对高达 1200 行的主控制器进行视觉层架构大扫除。划定六大专属业务防区 (Region)，彻底根治“找函数如大海捞针”的开发痛点，提升代码长效可维护性。
- (优化) 重塑生命周期承重墙 `load_chapter` 物理结构，防御潜在的时序竞态问题。

【v0.4.3】解析提速与架构打通
- (新增) TXT 目录结构缓存：首次解析书籍后将自动在本地生成目录索引。下次阅读同一本书时，将彻底跳过耗时的正则扫描流程，实现秒开阅读。
- (优化) 核心引擎解耦：支持从外部注入预解析数据，大幅降低 CPU 开销。
"""
        app.global_dialog.title = ft.Text("历史更新记录", size=18, weight=ft.FontWeight.BOLD, color="onSurface")
        
        app.global_dialog.content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Text(log_text, selectable=True),
                        padding=ft.padding.only(left=0, top=0, right=16, bottom=0)
                    )
                ], 
                scroll=ft.ScrollMode.AUTO
            ), 
            padding=0,
            height=400, width=500
        )
        
        # 💥 修正：ft.Button 替换为 ft.TextButton
        app.global_dialog.actions = [
            ft.TextButton(
                content=ft.Text("关闭", color="onSurface"), 
                on_click=lambda _: app._close_dialog(), 
                style=app.get_action_button_style()
            )
        ]
        app._open_dialog()

    @staticmethod
    def show_ai_dialog(app, e):
        if not app.engine.chapters_info: return
        app.global_dialog.modal = True
        target_idx = app.current_chapter_idx
        ch_info = app.engine.chapters_info[target_idx]
        
        target_idx_str = str(target_idx)
        # 💥 优化：使用 setdefault，确保空字典被安全地注入到内存中，避免丢失指针
        saved_data = app.current_book_summaries.setdefault(target_idx_str, {})
        if isinstance(saved_data, str):
            saved_data = {"main": saved_data}
            app.current_book_summaries[target_idx_str] = saved_data

        state = {
            "mode": "main",         
            "chat": [],             
            "is_streaming": False
        }

        chat_list_col = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=15, expand=True)
        
        chat_input = ft.TextField(
            hint_text="追问AI全书细节 (已启用全书防剧透知识库)...", 
            text_size=13,
            expand=True, dense=True, 
            content_padding=10, border_radius=20,
            on_submit=lambda _: send_message(None)
        )
        
        send_btn = ft.IconButton(icon=ft.Icons.SEND, icon_color="onSurface", on_click=lambda _: send_message(None))

        mode_btn_main = ft.TextButton(content=ft.Text("主线"), style=ft.ButtonStyle(color="onSurface"))
        mode_btn_char = ft.TextButton(content=ft.Text("人物"), style=ft.ButtonStyle(color="onSurface"))
        mode_btn_char_pro = ft.TextButton(content=ft.Text("人物+"), style=ft.ButtonStyle(color="onSurface"))
        mode_btn_clue = ft.TextButton(content=ft.Text("伏笔"), style=ft.ButtonStyle(color="onSurface"))

        # 💥 修正：ft.Button 替换为 ft.ElevatedButton / TextButton
        btn_regen = ft.ElevatedButton(content=ft.Text("总结"), style=ft.ButtonStyle(bgcolor=ft.Colors.DEEP_PURPLE_400, color=ft.Colors.WHITE))
        btn_copy = ft.ElevatedButton(content=ft.Text("复制", color="onSurface"), style=app.get_action_button_style())
        btn_close = ft.TextButton(content=ft.Text("关闭", color="onSurface"), on_click=lambda _: app._close_dialog(), style=app.get_action_button_style())

        def update_mode_btns_ui():
            is_dark = app._get_is_dark_mode()
            active_bg = "#1AFFFFFF" if is_dark else "#1A000000"
            inactive_bg = ft.Colors.TRANSPARENT
            
            for btn, m in [(mode_btn_main, "main"), (mode_btn_char, "characters"), (mode_btn_char_pro, "characters_pro"), (mode_btn_clue, "clues")]:
                is_active = (state["mode"] == m)
                btn.style = ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    bgcolor=active_bg if is_active else inactive_bg,
                    elevation=0,
                    padding=ft.padding.symmetric(horizontal=12, vertical=8)
                )
                try: btn.update()
                except Exception: pass
            
            btn_copy.style = app.get_action_button_style()
            btn_close.style = app.get_action_button_style()
            try: btn_copy.update(); btn_close.update()
            except Exception: pass

        def get_sys_prompt():
            if state["mode"] == "main": 
                return app.ai_config["prompt"]
            if state["mode"] in ["characters", "characters_pro"]: 
                return "提取本章出现的所有人物，写出一段深度的人物梳理。用一句话标明他们的阵营、当前状态、以及与主角的关系。严禁脑补未发生的情节。"
            if state["mode"] == "clues": 
                return "找出本章看似不起眼的环境描写、对话停顿或异常行为，推测作者可能埋下的伏笔与线索。尽量精简干练。"

        def render_chat():
            chat_list_col.controls.clear()
            
            base_content = saved_data.get(state["mode"], "")
            if not base_content:
                base_content = "请点击下方按钮开始分析本章。\n\n*(注意：请确保已在首页设置中配置了 API Key)*"
                btn_regen.content.value = "总结"
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
                        ft.Row(
                            controls=[
                                ft.Container(
                                    content=ft.Text(msg["content"], color="onSurface"),
                                    bgcolor="surface",
                                    padding=10, 
                                    border_radius=8,
                                    shadow=ft.BoxShadow(blur_radius=4, color="#1A000000", offset=ft.Offset(0, 1)),
                                    margin=ft.margin.only(left=40, right=10) 
                                )
                            ],
                            alignment=ft.MainAxisAlignment.END
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
        mode_btn_char_pro.on_click = lambda _: switch_mode("characters_pro")
        mode_btn_clue.on_click = lambda _: switch_mode("clues")

        def generate_base(e):
            if not app.ai_config["key"]:
                app.show_snack_bar("⚠️ 请先配置 API Key")
                return
            if state["is_streaming"]: return

            state["is_streaming"] = True
            state["chat"].clear() 
            btn_regen.disabled = True

            if state["mode"] == "characters_pro":
                def pro_task():
                    btn_regen.content.value = "提取名单中..."
                    try: btn_regen.update()
                    except Exception: pass
                    
                    saved_data[state["mode"]] = "✨ [1/3] 盲眼读心：正在飞速阅读本章，提取出场人物名单...\n\n"
                    render_chat()

                    chapter_text = app.engine.get_chapter_text(target_idx)[:8000]
                    
                    extract_msg = [{"role": "system", "content": f"请提取以下章节文本中出现的关键人物名字。仅返回名字本身，用逗号分隔，不要返回其他任何说明、问候或多余符号。如果没有人物，返回'无'。\n\n文本：\n{chapter_text}"}]
                    names_result = [""]
                    evt = threading.Event()
                    def on_c(d): names_result[0] += d
                    def on_comp(f): evt.set()
                    def on_err(err): names_result[0] = f"Error: {err}"; evt.set()
                    
                    AIService.stream_chat(app.ai_config, extract_msg, on_c, on_comp, on_err, lambda: getattr(app.global_dialog, "open", False))
                    evt.wait()

                    names_str = names_result[0].strip()
                    if "Error" in names_str or not names_str or names_str == "无":
                        saved_data[state["mode"]] = f"⚠️ 未能有效提取到人物名单 ({names_str})。梳理终止。"
                        state["is_streaming"] = False
                        try:
                            btn_regen.disabled = False
                            btn_regen.content.value = "重新总结"
                            btn_regen.update()
                        except Exception: pass
                        render_chat()
                        return

                    saved_data[state["mode"]] = f"✨ [2/3] 时光回溯：已成功锁定本章人物 ({names_str})。正在从全书知识库打捞他们的历史档案 (已开启防剧透隔离)...\n\n"
                    render_chat()
                    btn_regen.content.value = "打捞档案中..."
                    try: btn_regen.update()
                    except Exception: pass

                    names = [n.strip() for n in names_str.replace("，", ",").split(",") if n.strip()]
                    rag_context = ""
                    if names:
                        try:
                            import hashlib
                            import os
                            from data.storage import StorageManager
                            try:
                                from core.vector_db import VectorDB
                                book_hash = hashlib.md5(app.current_book_path.encode('utf-8')).hexdigest()
                                db_path = os.path.join(StorageManager.get_base_dir(), "vector_dbs", f"{book_hash}.db")
                                
                                if os.path.exists(db_path):
                                    vdb = VectorDB(db_path)
                                    for name in names:
                                        query_emb = AIService.get_embedding(app.ai_config, f"{name}的背景设定与经历")
                                        results = vdb.search(query_emb, top_k=2, max_chapter_idx=target_idx)
                                        if results:
                                            rag_context += f"\n【人物 '{name}' 的档案线索】:\n"
                                            for r in results:
                                                ch_title = app.engine.chapters_info[r['chapter_idx']]['title']
                                                rag_context += f"- [出自: {ch_title}]: {r['chunk_text']}\n"
                            except ImportError:
                                pass 
                        except Exception as ex:
                            print(f"人物档案检索失败: {ex}")

                    saved_data[state["mode"]] = f"✨ [3/3] 档案重组：历史档案打捞完毕！正在融合本章剧情，为您撰写极具纵深感的人物梳理报告...\n\n"
                    render_chat()
                    btn_regen.content.value = "撰写报告中..."
                    try: btn_regen.update()
                    except Exception: pass

                    system_content = f"{get_sys_prompt()}\n\n请结合以下检索到的【历史档案】和【本章文本】进行综合分析：\n{rag_context}\n\n【本章文本开始】\n{chapter_text}\n【本章文本结束】"
                    final_messages = [{"role": "system", "content": system_content}]

                    stream_buffer = [""]
                    async def ui_updater_pro():
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

                    app.page.run_task(ui_updater_pro)

                    def on_chunk_final(delta): stream_buffer[0] += delta
                    def on_complete_final(full):
                        state["is_streaming"] = False
                        saved_data[state["mode"]] = full
                        app._save_book_summaries()
                        try:
                            btn_regen.disabled = False
                            btn_regen.content.value = "重新总结"
                            btn_regen.update()
                        except Exception: pass
                    def on_error_final(err):
                        state["is_streaming"] = False
                        saved_data[state["mode"]] = err
                        try:
                            btn_regen.disabled = False
                            btn_regen.content.value = "重新总结"
                            btn_regen.update()
                        except Exception: pass

                    AIService.stream_chat(app.ai_config, final_messages, on_chunk_final, on_complete_final, on_error_final, lambda: getattr(app.global_dialog, "open", False))

                threading.Thread(target=pro_task, daemon=True).start()
                return 

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
            state["chat"].append({"role": "assistant", "content": "⏳ 正在检索防剧透知识库并思考中..."})
            render_chat()

            def rag_chat_task():
                try:
                    import hashlib
                    import os
                    from data.storage import StorageManager
                    from core.ai_service import AIService
                    
                    rag_context = ""
                    try:
                        from core.vector_db import VectorDB
                        book_hash = hashlib.md5(app.current_book_path.encode('utf-8')).hexdigest()
                        db_path = os.path.join(StorageManager.get_base_dir(), "vector_dbs", f"{book_hash}.db")
                        
                        if os.path.exists(db_path):
                            vdb = VectorDB(db_path)
                            query_emb = AIService.get_embedding(app.ai_config, text)
                            
                            user_top_k = app.ai_config.get("top_k", 5)
                            results = vdb.search(query_emb, top_k=user_top_k, max_chapter_idx=target_idx)
                            
                            if results:
                                rag_context = "\n【以下是从全书知识库检索到的相关片段，供参考】：\n"
                                for r in results:
                                    ch_title = app.engine.chapters_info[r['chapter_idx']]['title']
                                    rag_context += f"- [出自: {ch_title}]: {r['chunk_text']}\n"
                    except Exception as ex:
                        print(f"RAG 检索失败 (将回退到仅看当前章节): {ex}")

                    chapter_text = app.engine.get_chapter_text(target_idx)[:8000]
                    
                    system_content = f"{get_sys_prompt()}\n{rag_context}\n\n当前阅读章节文本：\n{chapter_text}"
                    messages = [{"role": "system", "content": system_content}]
                    
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

                    AIService.stream_chat(app.ai_config, messages, on_chunk, on_complete, on_error, is_active)
                    
                except Exception as ex:
                    state["is_streaming"] = False
                    state["chat"][-1]["content"] = f"系统错误: {ex}"
                    try: app.page.update()
                    except Exception: pass

            threading.Thread(target=rag_chat_task, daemon=True).start()

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

        app.global_dialog.inset_padding = ft.padding.symmetric(horizontal=12, vertical=24)
        app.global_dialog.content_padding = ft.padding.only(left=20, top=15, right=4, bottom=15)
        
        app.global_dialog.title = ft.Text(f"✨ AI 助手 - {ch_info['title']}", size=16, weight=ft.FontWeight.BOLD, color="onSurface")
        app.global_dialog.content = ft.Container(
            content=chat_list_col,
            width=600, height=400, bgcolor=ft.Colors.TRANSPARENT  
        )
        
        app.global_dialog.actions = [
            ft.Container(
                content=ft.Column([
                    ft.Row(
                        [mode_btn_main, mode_btn_char, mode_btn_char_pro, mode_btn_clue], 
                        alignment=ft.MainAxisAlignment.SPACE_AROUND
                    ),
                    ft.Row(
                        [btn_regen, btn_copy, btn_close], 
                        alignment=ft.MainAxisAlignment.SPACE_AROUND
                    ),
                    ft.Row(
                        [chat_input, send_btn], 
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                ], tight=True, spacing=10),
                padding=ft.padding.symmetric(horizontal=10)
            )
        ]
        
        app._open_dialog()