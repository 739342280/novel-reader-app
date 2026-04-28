import flet as ft
import asyncio
import threading
from core.ai_service import AIService

def get_ai_chat_view(app):
    # 如果没加载书籍数据，做一个优雅的防御拦截
    if not hasattr(app.engine, "chapters_info") or not app.engine.chapters_info:
        return ft.View(route="/reader/ai_chat", controls=[ft.Text("暂无书籍数据", color="red")])

    target_idx = app.current_chapter_idx
    ch_info = app.engine.chapters_info[target_idx]
    
    target_idx_str = str(target_idx)
    saved_data = app.current_book_summaries.setdefault(target_idx_str, {})
    if isinstance(saved_data, str):
        saved_data = {"main": saved_data}
        app.current_book_summaries[target_idx_str] = saved_data

    # 💥 修改点 1：将 chat 升级为独立的多频道字典，保留各模式追问记录
    state = {
        "mode": "main",         
        "chats": {
            "main": [],
            "characters": [],
            "characters_pro": [],
            "clues": []
        },             
        "is_streaming": False
    }

    # 聊天列表区（拉伸铺满）
    chat_list_col = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=15, expand=True)
    
    chat_input = ft.TextField(
        hint_text="追问AI全书细节 (已启用全书防剧透知识库)...", 
        text_size=13,
        expand=True, dense=True, 
        content_padding=10, border_radius=20,
        on_submit=lambda _: send_message(None)
    )
    
    send_btn = ft.IconButton(icon=ft.Icons.SEND, icon_color="onSurface", on_click=lambda _: send_message(None))

    btn_regen = ft.ElevatedButton(content=ft.Text("总结"), style=ft.ButtonStyle(bgcolor=ft.Colors.DEEP_PURPLE_400, color=ft.Colors.WHITE))
    btn_copy = ft.ElevatedButton(content=ft.Text("复制", color="onSurface"), style=app.get_action_button_style())

    def go_back(e):
        # 🚨 【路由纪律：禁止修改】：统一调用主控制器的 view_pop 进行退栈。
        app.view_pop(None)

    # 核心判定锁：通过路由判断当前视图是否存活
    def is_active():
        return app.page.route == "/reader/ai_chat"

    def get_sys_prompt():
        if state["mode"] == "main": 
            return app.ai_config.get("prompt", "")
        if state["mode"] in ["characters", "characters_pro"]: 
            return app.ai_config.get("prompt_char", "")
        if state["mode"] == "clues": 
            return app.ai_config.get("prompt_clue", "")
        
    def render_chat():
        chat_list_col.controls.clear()
        
        base_content = saved_data.get(state["mode"], "")
        if not base_content:
            base_content = "请选择上方选项卡，然后点击下方按钮开始分析本章。\n\n*(注意：请确保已在首页设置中配置了 API Key)*"
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

        # 💥 修改点 2：读取独立频道的聊天记录
        for msg in state["chats"][state["mode"]]:
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

    # 💥 修改点 3：增加顶端 Tabs 的原生切换处理逻辑
    def handle_tab_change(e):
        modes = ["main", "characters", "characters_pro", "clues"]
        target_idx = e.control.selected_index
        
        # 稳健性拦截：流式输出中严禁切换频道
        if state["is_streaming"]:
            app.show_snack_bar("⚠️ AI 正在输出中，请等待完成后切换")
            # 强制回弹指示器位置
            e.control.selected_index = modes.index(state["mode"])
            try: e.control.update()
            except Exception: pass
            return
            
        state["mode"] = modes[target_idx]
        # 注意：这里不再清空 state["chats"]，以此实现记忆历史
        render_chat()

   # 💥 彻底适配 Flet 最新版本的选项卡分离架构
    ai_tabs = ft.Tabs(
        selected_index=0,
        length=4,  # 💥 新版要求必须在控制器上声明选项卡总数量
        on_change=handle_tab_change,
        content=ft.TabBar(
            tab_alignment=ft.TabAlignment.CENTER, # 💥 居中对齐，替代以前的 scrollable 属性
            tabs=[
                # 💥 核心修复：属性名彻底变更为 label，原生 icon 完美回归
                ft.Tab(label="主线", icon=ft.Icons.MENU_BOOK),
                ft.Tab(label="人物", icon=ft.Icons.PERSON),
                ft.Tab(label="人物+", icon=ft.Icons.PERSON_ADD_ALT_1),
                ft.Tab(label="伏笔", icon=ft.Icons.SEARCH),
            ]
        )
    )

    def generate_base(e):
        if not app.ai_config.get("key"):
            app.show_snack_bar("⚠️ 请先配置 API Key")
            return
        if state["is_streaming"]: return

        state["is_streaming"] = True
        # 重新生成大纲时，清空当前频道的追问历史
        state["chats"][state["mode"]].clear() 
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
                
                AIService.stream_chat(app.ai_config, extract_msg, on_c, on_comp, on_err, is_active)
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

                AIService.stream_chat(app.ai_config, final_messages, on_chunk_final, on_complete_final, on_error_final, is_active)

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

        threading.Thread(target=AIService.stream_chat, args=(app.ai_config, messages, on_chunk, on_complete, on_error, is_active), daemon=True).start()

    def send_message(e):
        if not app.ai_config.get("key"):
            app.show_snack_bar("⚠️ 请先配置 API Key")
            return
        text = chat_input.value.strip()
        if not text or state["is_streaming"]: return
        
        chat_input.value = ""
        try: chat_input.update()
        except Exception: pass

        state["is_streaming"] = True
        
        # 💥 修改点 5：追加对话记录至当前模式专属存储区
        state["chats"][state["mode"]].append({"role": "user", "content": text})
        state["chats"][state["mode"]].append({"role": "assistant", "content": "⏳ 正在检索防剧透知识库并思考中..."})
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
                
                base_prompt = app.ai_config.get("prompt", "你是一个小说阅读助手，请根据已有信息回答用户的问题。")
                system_content = f"{get_sys_prompt()}\n{rag_context}\n\n当前阅读章节文本：\n{chapter_text}"
                messages = [{"role": "system", "content": system_content}]
                
                if saved_data.get(state["mode"]):
                    messages.append({"role": "assistant", "content": saved_data[state["mode"]]})
                
                for msg in state["chats"][state["mode"]][:-1]: 
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
                    state["chats"][state["mode"]][-1]["content"] = full
                
                def on_error(err):
                    state["is_streaming"] = False
                    stream_buffer[0] = f"请求失败: {err}"
                    state["chats"][state["mode"]][-1]["content"] = stream_buffer[0]

                AIService.stream_chat(app.ai_config, messages, on_chunk, on_complete, on_error, is_active)
                
            except Exception as ex:
                state["is_streaming"] = False
                state["chats"][state["mode"]][-1]["content"] = f"系统错误: {ex}"
                try: app.page.update()
                except Exception: pass

        threading.Thread(target=rag_chat_task, daemon=True).start()

    async def copy_result(e):
        content_to_copy = saved_data.get(state["mode"], "")
        
        # 💥 修改点 6：复制时连带导出本频道的专属追问记录
        if state["chats"][state["mode"]]:
            content_to_copy += "\n\n--- 追问记录 ---\n"
            for msg in state["chats"][state["mode"]]:
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

    # 首次进入页面，渲染默认的主线频道
    render_chat()

    # 💥 修改点 7：底栏大瘦身，彻底抛弃原有按钮轨道
    bottom_area = ft.Container(
        content=ft.Column([
            ft.Row(
                [btn_regen, btn_copy], 
                alignment=ft.MainAxisAlignment.SPACE_AROUND
            ),
            ft.Row(
                [chat_input, send_btn], 
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            )
        ], tight=True, spacing=10),
        padding=ft.padding.all(10),
        bgcolor="surface", 
        border=ft.border.only(top=ft.BorderSide(1, "outlineVariant"))
    )

    # 💥 修改点 8：按标准的 View 架构注入 Tabs
    return ft.View(
        route="/reader/ai_chat",
        appbar=ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=go_back),
            title=ft.Text(f"✨ AI 助手 - {ch_info['title']}", size=16, weight="bold"),
            center_title=True,
            bgcolor="surfaceVariant"
        ),
        controls=[
            # 在 AppBar 下方紧贴注入我们新做好的选项卡组件
            ai_tabs,
            ft.Container(
                content=chat_list_col,
                expand=True,
                padding=15
            ),
            bottom_area
        ],
        padding=0,
        bgcolor="surface"
    )