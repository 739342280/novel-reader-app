import flet as ft
import asyncio
import threading
from core.ai_service import AIService

def get_ai_chat_view(app):
    # 如果没加载书籍数据，做一个优雅的防御拦截
    if not hasattr(app.engine, "chapters_info") or not app.engine.chapters_info:
        return ft.View(route="/reader/ai_chat", controls=[ft.Text("暂无书籍数据", color="red")])
    
    def get_smart_chapter_text(text):
        # 统计中文字符数（简单去除空白符后计算长度）
        text_len = len("".join(text.split()))
        
        # 设定极端红线：30000 字
        max_safe_length = 30000
        
        # 如果是正常章节，直接全量返回，一个字都不删！
        if text_len <= max_safe_length:
            return text
            
        # 如果是极端未分章文本，进行“掐中间留头尾”压缩
        separator = "\n\n...[系统提示：本章中间部分因字数超过 3 万字极限被智能折叠，已为您保留开头与结尾核心剧情]...\n\n"
        keep_len = max_safe_length - len(separator)
        
        front_len = int(keep_len * 0.3) # 保留前 30%
        back_len = keep_len - front_len # 保留后 70% (网文结尾更重要)
        
        return text[:front_len] + separator + text[-back_len:]

    target_idx = app.current_chapter_idx
    ch_info = app.engine.chapters_info[target_idx]
    
    target_idx_str = str(target_idx)
    saved_data = app.current_book_summaries.setdefault(target_idx_str, {})
    if isinstance(saved_data, str):
        saved_data = {"main": saved_data}
        app.current_book_summaries[target_idx_str] = saved_data
    
    state = {
        "mode": "main",         
        "chats": {
            "main": [],
            "characters": [],
            "characters_pro": [],
            "clues": []
        },             
        "is_streaming": False,
        "cancel_flag": False # 💥 新增：用于拦截大模型输出的开关
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
        return app.page.route == "/reader/ai_chat" and not state.get("cancel_flag", False)
    
    def stop_generation(e):
        if state["is_streaming"]:
            state["cancel_flag"] = True
            btn_regen.content.value = "停止中..."
            btn_regen.disabled = True
            try: btn_regen.update()
            except Exception: pass

    def set_btn_streaming():
        state["cancel_flag"] = False
        btn_regen.content.value = "⏹ 停止输出"
        # 💥 安全替换：直接赋全新的 ButtonStyle 对象，杜绝 Flet 样式静默崩溃
        btn_regen.style = ft.ButtonStyle(bgcolor=ft.Colors.RED_400, color=ft.Colors.WHITE) 
        btn_regen.on_click = stop_generation
        btn_regen.disabled = False
        try: btn_regen.update()
        except Exception: pass

    def set_btn_normal():
        btn_regen.style = ft.ButtonStyle(bgcolor=ft.Colors.DEEP_PURPLE_400, color=ft.Colors.WHITE) 
        btn_regen.on_click = lambda e: generate_base(e) 
        btn_regen.disabled = False
        # 💥 精准判定真实内容
        has_content = bool(saved_data.get(state["mode"]))
        btn_regen.content.value = "重新总结" if has_content else "总结"
        try: btn_regen.update()
        except Exception: pass

    def get_sys_prompt():
        if state["mode"] == "main": 
            return app.ai_config.get("prompt", "")
        if state["mode"] == "characters": 
            return app.ai_config.get("prompt_char", "")
        if state["mode"] == "characters_pro": 
            # 👇 让 characters_pro 使用我们刚才新建的专属提示词
            return app.ai_config.get("prompt_char_pro", "")
        if state["mode"] == "clues": 
            return app.ai_config.get("prompt_clue", "")
        
    def render_chat():
        chat_list_col.controls.clear()
        
        # 💥 逻辑大修：先判断有没有真正的历史记录，再去塞占位符
        raw_content = saved_data.get(state["mode"], "")
        has_content = bool(raw_content)
        
        if has_content:
            display_content = raw_content.replace("\n> ", "\n   ").replace("\n>", "\n   ").replace("---", "")
        else:
            display_content = "请选择上方选项卡，然后点击下方按钮开始分析本章。\n\n*(注意：请确保已在首页设置中配置了 API Key)*"
            
        if not state["is_streaming"]:
            btn_regen.content.value = "重新总结" if has_content else "总结"
            try: btn_regen.update()
            except Exception: pass
        
        chat_list_col.controls.append(
            ft.Container(
                content=ft.Markdown(display_content, selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB),
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
        set_btn_streaming() # 💥 切入流式按键状态

        if state["mode"] == "characters_pro":
            def pro_task():
                                
                saved_data[state["mode"]] = "✨ [1/3] 盲眼读心：正在飞速阅读本章，提取出场人物名单...\n\n"
                render_chat()

                raw_text = app.engine.get_chapter_text(target_idx)
                chapter_text = get_smart_chapter_text(raw_text)
                
                extract_msg = [{"role": "system", "content": f"请阅读以下文本，提取对本章情节推动最关键的 3-5 个人物名字。过滤掉只被提及、没有实际戏份的龙套配角。仅返回名字本身，用逗号分隔，不要返回任何说明或多余符号。如果没有人物，返回'无'。\n\n文本：\n{chapter_text}"}]
                names_result = [""]
                evt = threading.Event()
                def on_c(d): names_result[0] += d
                def on_comp(f): evt.set()
                def on_err(err): names_result[0] = f"Error: {err}"; evt.set()
                
                AIService.stream_chat(app.ai_config, extract_msg, on_c, on_comp, on_err, is_active)
                evt.set() 
                evt.wait()

                # 💥 拦截点 1：提取名单后
                if state.get("cancel_flag"):
                    saved_data[state["mode"]] += "\n\n*[已手动终止]*"
                    state["is_streaming"] = False
                    set_btn_normal()
                    render_chat()
                    return

                names_str = names_result[0].strip()
                if "Error" in names_str or not names_str or names_str == "无":
                    saved_data[state["mode"]] = f"⚠️ 未能有效提取到人物名单 ({names_str})。梳理终止。"
                    state["is_streaming"] = False    
                    set_btn_normal()                
                    render_chat()
                    return

                saved_data[state["mode"]] = f"✨ [2/3] 时光回溯：已成功锁定本章人物 ({names_str})。正在从全书知识库打捞他们的历史档案 (已开启防剧透隔离)...\n\n"
                render_chat()
                
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
                                    # 💥 拦截点 2：强行阻断耗时的数据库循环查询
                                    if state.get("cancel_flag"): break 
                                    query_emb = AIService.get_embedding(app.ai_config, f"{name}的背景设定与经历")
                                    results = vdb.search(query_emb, top_k=5, max_chapter_idx=target_idx)
                                    if results:
                                        rag_context += f"\n【人物 '{name}' 的档案线索】:\n"
                                        for r in results:
                                            ch_title = app.engine.chapters_info[r['chapter_idx']]['title']
                                            rag_context += f"- [出自: {ch_title}]: {r['chunk_text']}\n"
                        except ImportError:
                            pass 
                    except Exception as ex:
                        print(f"人物档案检索失败: {ex}")

                # 💥 拦截点 3：打捞档案后
                if state.get("cancel_flag"):
                    saved_data[state["mode"]] += "\n\n*[已手动终止]*"
                    state["is_streaming"] = False
                    set_btn_normal()
                    render_chat()
                    return

                saved_data[state["mode"]] = f"✨ [3/3] 档案重组：历史档案打捞完毕！正在融合本章剧情，为您撰写极具纵深感的人物梳理报告...\n\n"
                render_chat()
                
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
                    set_btn_normal()
                    
                def on_error_final(err):
                    state["is_streaming"] = False
                    # 💥 拦截点 4：强制将中止信息写入 stream_buffer，让 ui_updater_pro 能够捕获并在屏幕上渲染
                    if state.get("cancel_flag"):
                        if stream_buffer[0]:
                            stream_buffer[0] += "\n\n*[已手动终止]*"
                        else:
                            stream_buffer[0] = saved_data[state["mode"]] + "\n\n*[已手动终止]*"
                    else:
                        if stream_buffer[0]:
                            stream_buffer[0] += f"\n\nError: {err}"
                        else:
                            stream_buffer[0] = saved_data[state["mode"]] + f"\n\nError: {err}"
                    
                    saved_data[state["mode"]] = stream_buffer[0]
                    set_btn_normal()

                AIService.stream_chat(app.ai_config, final_messages, on_chunk_final, on_complete_final, on_error_final, is_active)
                
                if state["is_streaming"] and state.get("cancel_flag"):
                    on_error_final("Abort")              
            threading.Thread(target=pro_task, daemon=True).start()

            return 

        
        saved_data[state["mode"]] = "✨ 大模型正在阅读本章并进行梳理，请稍候...\n\n"
        render_chat()
        
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
            set_btn_normal() # 💥 恢复按钮

        def on_error(err):
            state["is_streaming"] = False
            # 💥 强制写入流缓冲区
            if state.get("cancel_flag"):
                if stream_buffer[0]:
                    stream_buffer[0] += "\n\n*[已手动终止]*"
                else:
                    stream_buffer[0] = saved_data[state["mode"]] + "\n\n*[已手动终止]*"
            else:
                if stream_buffer[0]:
                    stream_buffer[0] += f"\n\nError: {err}"
                else:
                    stream_buffer[0] = saved_data[state["mode"]] + f"\n\nError: {err}"
            
            saved_data[state["mode"]] = stream_buffer[0]
            set_btn_normal()

        def run_stream_normal():
            AIService.stream_chat(app.ai_config, messages, on_chunk, on_complete, on_error, is_active)
            # 💥 兜底：防止常规总结的静默退出
            if state["is_streaming"] and state.get("cancel_flag"):
                on_error("Abort")
        
        # 💥 核心修复：清理掉多余的参数，明确把 target 指向我们的兜底函数
        threading.Thread(target=run_stream_normal, daemon=True).start()

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
        set_btn_streaming()
        
        # 追加对话记录至当前模式专属存储区
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

                raw_text = app.engine.get_chapter_text(target_idx)
                chapter_text = get_smart_chapter_text(raw_text)
                
                # 💥 架构优化：将之前的总结降级为参考资料，打破模型的“身份幻觉”
                prev_summary = saved_data.get(state["mode"], "")
                summary_context = f"\n\n【参考资料 C：初步分析】\n{prev_summary}\n(注：以上是你之前生成的初步总结，仅供参考，若与原文冲突，请坚决以原文为准。)" if prev_summary else ""

                # 为追问环节增加一个适配层，告诉 AI 现在是对话模式，可以参考历史
                base_prompt = get_sys_prompt()
                rag_instruction = ""
                if rag_context:
                    rag_instruction = (
                        "\n\n【重要指令：全书关联】\n"
                        "当前用户正在进行追问。虽然你的基本职责由上方系统提示词定义，但现在请你打破'仅限本章'的限制，"
                        "充分利用下方提供的【全书知识库检索片段】来回答。如果用户问及之前的剧情或人物背景，请以检索到的档案为准。"
                    )
                    
                # 👇 这里是核心修复：把 {get_sys_prompt()} 替换成了 {base_prompt}{rag_instruction}
                system_content = f"{base_prompt}{rag_instruction}\n{rag_context}\n\n【参考资料 B：当前阅读章节原文】\n{chapter_text}{summary_context}"
                messages = [{"role": "system", "content": system_content}]
                
                
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
                    set_btn_normal() # 💥 恢复按钮
                
                def on_error(err):
                    state["is_streaming"] = False
                    base_txt = state["chats"][state["mode"]][-1]["content"]
                    # 💥 强制写入流缓冲区
                    if state.get("cancel_flag"):
                        if stream_buffer[0]:
                            stream_buffer[0] += "\n\n*[已手动终止]*"
                        else:
                            stream_buffer[0] = base_txt + "\n\n*[已手动终止]*"
                    else:
                        if stream_buffer[0]:
                            stream_buffer[0] += f"\n\n请求失败: {err}"
                        else:
                            stream_buffer[0] = base_txt + f"\n\n请求失败: {err}"
                    
                    state["chats"][state["mode"]][-1]["content"] = stream_buffer[0]
                    set_btn_normal()

                AIService.stream_chat(app.ai_config, messages, on_chunk, on_complete, on_error, is_active)
                
                # 💥 兜底：防止追问聊天时的静默退出
                if state["is_streaming"] and state.get("cancel_flag"):
                    on_error("Abort")
                
            except Exception as ex:
                state["is_streaming"] = False
                state["chats"][state["mode"]][-1]["content"] = f"系统错误: {ex}"
                set_btn_normal() # 💥 恢复按钮
                try: app.page.update()
                except Exception: pass

        threading.Thread(target=rag_chat_task, daemon=True).start()

    async def copy_result(e):
        import subprocess
        import sys

        # 1. 拼装内容（防 None 处理）
        base_content = str(saved_data.get(state["mode"], "") or "")
        content_to_copy = base_content
        
        chat_history = state["chats"].get(state["mode"], [])
        if chat_history:
            content_to_copy += "\n\n--- 追问记录 ---\n"
            for msg in chat_history:
                if "⏳ 正在检索" in msg.get("content", ""): continue
                role = "【我】" if msg.get("role") == "user" else "【AI】"
                content_to_copy += f"\n{role}：\n{msg.get('content', '')}\n"

        content_to_copy = content_to_copy.strip()
        if not content_to_copy:
            app.show_snack_bar("⚠️ 暂无内容可复制")
            return

        success = False
        
        # --- 核心修复：根据不同平台精准分发复制任务 ---
        if sys.platform == "win32":
            # Windows 端：必须优先使用 PowerShell 强制 UTF-8 管道流（彻底杜绝中文乱码与长度限制）
            try:
                process = subprocess.Popen(
                    ['powershell', '-NoProfile', '-Command', 
                     '[Console]::InputEncoding = [System.Text.Encoding]::UTF8; $input | Set-Clipboard'],
                    stdin=subprocess.PIPE,
                    text=False # 使用字节流发送
                )
                process.communicate(input=content_to_copy.encode('utf-8'))
                if process.returncode == 0:
                    success = True
            except Exception as ex:
                print(f"Windows PS Copy Error: {ex}")
        else:
            # 移动端（Android/iOS/Linux）：Flet 的原生 API 在手机上容易静默失败
            # 💥 必须优先调用你底座原本封装好的 _execute_copy 方法！
            if hasattr(app, '_execute_copy'):
                try:
                    app._execute_copy(content_to_copy)
                    success = True
                except Exception as ex:
                    print(f"Mobile execute_copy Error: {ex}")

        # --- 终极兜底：如果上面的首选方案都失败了，再尝试 Flet 原生 API ---
        if not success:
            for method_name in ["set_clipboard", "set_clipboard_data", "set_clipboard_text"]:
                if hasattr(app.page, method_name):
                    try:
                        getattr(app.page, method_name)(content_to_copy)
                        success = True
                        break
                    except: 
                        continue

        # 3. UI 反馈
        if success:
            app.show_snack_bar("✅ 内容已存入剪贴板")
            btn_copy.content.value = "复制成功"
            btn_copy.style = ft.ButtonStyle(bgcolor="green", color="white")
            try: btn_copy.update()
            except Exception: pass
            
            await asyncio.sleep(2)
            btn_copy.content.value = "复制"
            btn_copy.style = app.get_action_button_style()
            try: btn_copy.update()
            except Exception: pass
        else:
            app.show_snack_bar("❌ 复制失败：请手动选择文字复制")

    # ================= 以下是被你不小心删掉的视图拼装代码 =================

    btn_regen.on_click = generate_base
    btn_copy.on_click = copy_result

    # 首次进入页面，渲染默认的主线频道
    render_chat()

    # 底栏大瘦身，彻底抛弃原有按钮轨道
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

    # 💥 这里就是丢失的 return，没有它页面根本加载不出来！
    return ft.View(
        route="/reader/ai_chat",
        appbar=ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=go_back),
            title=ft.Text(f"✨ AI 助手 - {ch_info['title']}", size=16, weight="bold"),
            center_title=True,
            bgcolor="surfaceVariant"
        ),
        controls=[
            # 在 AppBar 下方紧贴注入选项卡组件
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