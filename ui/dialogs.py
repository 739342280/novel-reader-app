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

        export_btn = ft.Button(
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
        app.global_dialog.inset_padding = ft.padding.symmetric(horizontal=20, vertical=24)
        app.global_dialog.content_padding = ft.padding.only(left=20, top=20, right=20, bottom=10)

        app.global_dialog.title = ft.Text("阅读统计", size=18, weight=ft.FontWeight.BOLD, color="onSurface")

        stat_content = ft.Column([
            ft.Text(f"卷数：{total_vols}", size=14, color="onSurface"),
            ft.Text(f"章节数：{total_chaps}", size=14, color="onSurface"),
            ft.Text(f"总字数：{total_words:,}", size=14, color="onSurface"),
            ft.Text(f"本卷字数：{vol_total_words:,}", size=14, color="onSurface"),
            ft.Text(f"本章字数：{curr_chap_words:,}", size=14, color="onSurface"),
            ft.Divider(height=10, thickness=0.5),
            ft.Text(f"已读：{total_read_words:,}", size=14, color="onSurface"),
            ft.Text(f"未读：{total_unread_words:,}", size=14, color="onSurface"),
            ft.Text(f"本卷已读：{vol_read_words:,}", size=14, color="onSurface"),
            ft.Text(f"本卷未读：{vol_unread_words:,}", size=14, color="onSurface"),
        ], tight=True, spacing=8)

        app.global_dialog.content = stat_content
        btn_close = ft.Button(content=ft.Text("关闭", color="onSurface"), on_click=lambda _: app._close_dialog(), style=app.get_action_button_style())
        app.global_dialog.actions = [btn_close]

        app._open_dialog()

    @staticmethod
    def show_settings_dialog(app, e):
        app.global_dialog.modal = False
        app.global_dialog.inset_padding = ft.padding.symmetric(horizontal=20, vertical=24)
        app.global_dialog.content_padding = ft.padding.only(left=0, top=10, right=0, bottom=0)

        UI_WIDTH = 400

        # === Tab 1: 对话模型配置 ===
        url_tf = ft.TextField(label="API URL", value=app.ai_config.get("url", ""), text_size=13, dense=True, width=UI_WIDTH)
        key_tf = ft.TextField(label="API Key", value=app.ai_config.get("key", ""), password=True, can_reveal_password=True, text_size=13, dense=True, width=UI_WIDTH)
        model_tf = ft.TextField(label="模型名称", value=app.ai_config.get("model", ""), text_size=13, dense=True, width=UI_WIDTH)
        prompt_tf = ft.TextField(label="系统提示词", value=app.ai_config.get("prompt", ""), multiline=True, min_lines=3, max_lines=5, text_size=13, dense=True, width=UI_WIDTH)
        
        tab1_col = ft.Column([url_tf, key_tf, model_tf, prompt_tf], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        tab1_container = ft.Container(content=tab1_col, padding=ft.padding.only(left=40, top=20, right=40, bottom=10))

        # === Tab 2: 向量引擎配置 ===
        embed_url_tf = ft.TextField(label="Embedding API URL", value=app.ai_config.get("embed_url", ""), text_size=13, dense=True, width=UI_WIDTH)
        embed_key_tf = ft.TextField(label="API Key", value=app.ai_config.get("embed_key", ""), password=True, can_reveal_password=True, text_size=13, dense=True, width=UI_WIDTH)
        embed_model_tf = ft.TextField(label="模型名称 (如 text-embedding-3-small)", value=app.ai_config.get("embed_model", ""), text_size=13, dense=True, width=UI_WIDTH)
        cloud_view = ft.Column([embed_url_tf, embed_key_tf, embed_model_tf], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        local_models = app.get_local_models()
        # 💥 修正点：将回显绑定的键严格对齐为 ai_service.py 所识别的 local_model_path
        saved_local_model = app.ai_config.get("local_model_path", "")
        local_model_dd = ft.Dropdown(
            label="已导入的本地模型",
            options=[ft.dropdown.Option(m) for m in local_models],
            value=saved_local_model if saved_local_model in local_models else None,
            text_size=13, dense=True, expand=True
        )
        import_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            icon_color=ft.Colors.BLUE,
            tooltip="导入本地模型文件",
            on_click=lambda _: app.page.run_task(app.trigger_model_picker, local_model_dd)
        )
        local_path_row = ft.Row([local_model_dd, import_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=UI_WIDTH)
        local_view = ft.Column([local_path_row], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        content_slot = ft.Container()

        def on_embed_mode_change(e):
            mode = e.data if e and getattr(e, "data", None) else embed_mode_dd.value
            if e and getattr(e, "data", None):
                embed_mode_dd.value = mode

            if mode == "本地模型":
                content_slot.content = local_view
            else:
                content_slot.content = cloud_view
            try:
                content_slot.update()
                app.page.update()
            except Exception: pass
            
        embed_mode_dd = ft.Dropdown(
            label="工作模式", 
            options=[ft.dropdown.Option("云端 API"), ft.dropdown.Option("本地模型")], 
            value=app.ai_config.get("embed_mode", "云端 API"),
            text_size=13, dense=True, width=UI_WIDTH,
            on_select=on_embed_mode_change
        )

        if embed_mode_dd.value == "本地模型":
            content_slot.content = local_view
        else:
            content_slot.content = cloud_view

        tab2_col = ft.Column([embed_mode_dd, ft.Container(height=5), content_slot], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        tab2_container = ft.Container(content=tab2_col, padding=ft.padding.only(left=40, top=20, right=40, bottom=10))

        # === Tab 3: 本书知识库 (方案 A 状态解耦重构) ===
        book_name = app.current_book_name if getattr(app, 'current_book_name', "") else "未打开任何书籍"
        status_text = ft.Text(f"当前阅读：《{book_name}》\n索引状态：未建立", size=14, color="onSurface", text_align=ft.TextAlign.CENTER)
        
        # 读取全局进度变量初始化 UI（首次打开为默认值）
        init_prog_val = getattr(app, "build_progress_value", 0)
        init_prog_text = getattr(app, "build_progress_text", "准备切块中...")
        is_building = getattr(app, "is_building_index", False)
        
        prog_bar = ft.ProgressBar(value=init_prog_val, visible=is_building, color=ft.Colors.BLUE, height=8, width=UI_WIDTH)
        prog_text = ft.Text(init_prog_text, size=12, color=ft.Colors.GREY_500, visible=is_building)
        
        btn_build = ft.Button(content=ft.Text("🚀 向量建库"), style=app.get_action_button_style(ft.padding.symmetric(horizontal=16, vertical=12)))
        btn_clear = ft.Button(content=ft.Text("🧹 清除索引", color=ft.Colors.BLACK), style=ft.ButtonStyle(bgcolor=ft.Colors.RED, color=ft.Colors.BLACK))
        
        action_row = ft.Row([btn_build, btn_clear], alignment=ft.MainAxisAlignment.CENTER, spacing=20)
        
        top_k_val = app.ai_config.get("top_k", 5)
        top_k_text = ft.Text(f"检索数量 (top_k): {top_k_val} 段", size=13, color="onSurface")
        
        def on_top_k_change(e):
            val = int(e.control.value)
            top_k_text.value = f"检索数量 (top_k): {val} 段"
            try: top_k_text.update()
            except Exception: pass

        top_k_slider = ft.Slider(
            min=1, max=10, divisions=9, value=top_k_val, label="{value} 段",
            on_change=on_top_k_change, width=UI_WIDTH
        )
        
        top_k_container = ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.TUNE, size=16, color=ft.Colors.GREY_500),
                top_k_text
            ], alignment=ft.MainAxisAlignment.START),
            top_k_slider,
            ft.Text("提示: 数值越大提供的背景知识越多，但也越容易分散大模型注意力或导致 API 超时。", size=11, color=ft.Colors.GREY_500, text_align=ft.TextAlign.LEFT)
        ], spacing=5)

        # 💥 方案 A 核心：将当前新创建的 UI 注册给 App 全局引用，供后台动态寻找
        app._active_ui = {
            'prog_bar': prog_bar,
            'prog_text': prog_text,
            'btn_build': btn_build,
            'btn_clear': btn_clear,
            'status_text': status_text
        }

        def refresh_db_status():
            import hashlib
            import os
            from data.storage import StorageManager
            if not app.current_book_path: return
            
            try:
                from core.vector_db import VectorDB
            except ImportError:
                status_text.value = f"当前阅读：《{book_name}》\n⚠️ 未安装 sqlite-vec 扩展库，知识库暂不可用"
                btn_build.disabled = True
                btn_clear.disabled = True
                try: tab3_col.update()
                except Exception: pass
                return

            book_hash = hashlib.md5(app.current_book_path.encode('utf-8')).hexdigest()
            db_path = os.path.join(StorageManager.get_base_dir(), "vector_dbs", f"{book_hash}.db")
            if os.path.exists(db_path):
                try:
                    vdb = VectorDB(db_path)
                    status = vdb.get_index_status()
                    if status["is_indexed"]:
                        status_text.value = f"当前阅读：《{book_name}》\n索引状态：已建库 ({status['chunk_count']} 个切块)"
                        btn_build.content.value = "🔁 重新建库"
                    else:
                        btn_build.content.value = "🚀 向量建库"
                except Exception: 
                    btn_build.content.value = "🚀 向量建库"
            else:
                btn_build.content.value = "🚀 向量建库"

        # 如果当前不在建库，正常刷新；如果正在建库，则恢复锁定的 UI 状态
        if is_building:
            btn_build.content.value = "⏳ 后台建库中..."
            btn_build.disabled = True
            btn_clear.disabled = True
        else:
            refresh_db_status()
        
        def on_build_click(e):
            if not app.current_book_path:
                app.show_snack_bar("⚠️ 请先在首页打开一本小说")
                return

            def do_build():
                # 💥 并发安全快照：锁死当前正在建库的书籍数据，防止用户切书导致数据错乱污染
                target_book_path = app.current_book_path
                target_book_name = app.current_book_name
                target_chapters = app.engine.chapters_info.copy()
                
                app.is_building_index = True
                app.build_progress_value = 0
                app.build_progress_text = "正在进行滑动窗口分块..."
                
                btn_build.content.value = "⏳ 后台建库中..."
                btn_build.disabled = True
                btn_clear.disabled = True
                prog_bar.visible = True
                prog_text.visible = True
                prog_bar.value = app.build_progress_value
                prog_text.value = app.build_progress_text
                try: tab3_col.update()
                except Exception: pass

                def build_task():
                    # 💥 方案 A 专用帮助函数：安全更新动态 UI
                    def safe_update_ui(val, text):
                        app.build_progress_value = val
                        app.build_progress_text = text
                        if hasattr(app, '_active_ui'):
                            try:
                                ui = app._active_ui
                                ui['prog_bar'].value = val
                                ui['prog_text'].value = text
                                ui['prog_bar'].update()
                                ui['prog_text'].update()
                            except Exception: pass

                    try:
                        import hashlib
                        import os
                        from data.storage import StorageManager
                        from core.chunker import NovelChunker
                        from core.ai_service import AIService
                        try:
                            from core.vector_db import VectorDB
                        except ImportError:
                            safe_update_ui(0, "❌ 启动失败：缺少 sqlite-vec 依赖")
                            app.page.update()
                            return
                        
                        # 💥 使用快照数据进行物理处理
                        book_hash = hashlib.md5(target_book_path.encode('utf-8')).hexdigest()
                        db_dir = os.path.join(StorageManager.get_base_dir(), "vector_dbs")
                        os.makedirs(db_dir, exist_ok=True)
                        db_path = os.path.join(db_dir, f"{book_hash}.db")
                        
                        chunker = NovelChunker(chunk_size=500, overlap=50)
                        all_chunks = []
                        
                        for idx, ch in enumerate(target_chapters):
                            text = app.engine.get_chapter_text(idx)
                            chunks = chunker.chunk_text(text)
                            for c in chunks:
                                all_chunks.append((idx, c))
                                
                        total = len(all_chunks)
                        if total == 0: raise Exception("提取不到书籍文本内容")
                            
                        safe_update_ui(0, f"分块完毕 (共 {total} 块)，请求 API 获取维度...")
                        app.page.update()
                        
                        first_emb = AIService.get_embedding(app.ai_config, all_chunks[0][1])
                        dim = len(first_emb)
                        
                        vdb = VectorDB(db_path)
                        vdb.init_tables(dim)
                        
                        batch_size = 50
                        for i in range(0, total, batch_size):
                            batch = all_chunks[i:i+batch_size]
                            
                            safe_update_ui(i / total, f"🚀 正在调用 Embedding 接口... ( {i} / {total} )")
                            
                            # 提取这一批次的所有文本
                            batch_texts = [c[1] for c in batch]
                            
                            # 💥 核心修改：调用批量接口（需配合更新 AIService 和 local_inference）
                            # 注意：此处我们需要在 AIService 中新增 get_embeddings 方法（带 s）
                            batch_embs = AIService.get_embeddings(app.ai_config, batch_texts)

                            db_data = []
                            for idx_in_batch, (chapter_idx, chunk_text) in enumerate(batch):
                                emb = batch_embs[idx_in_batch]
                                db_data.append((chapter_idx, chunk_text, emb))
                                
                            vdb.insert_chunks(db_data)
                            
                        # 成功大满贯
                        app.is_building_index = False
                        safe_update_ui(1.0, "✅ 建库大功告成！")
                        
                        if hasattr(app, '_active_ui'):
                            try:
                                ui = app._active_ui
                                ui['status_text'].value = f"当前阅读：《{target_book_name}》\n索引状态：已建库 ({total} 个切块)"
                                ui['btn_build'].content.value = "🔁 重新建库"
                                ui['btn_build'].disabled = False
                                ui['btn_clear'].disabled = False
                                ui['status_text'].update()
                                ui['btn_build'].update()
                                ui['btn_clear'].update()
                            except Exception: pass
                            
                        app.show_snack_bar(f"✅ 《{target_book_name}》全书向量建库已在后台完成！")
                        
                    except Exception as ex:
                        app.is_building_index = False
                        safe_update_ui(app.build_progress_value, f"❌ 建库失败: {str(ex)}")
                        
                        if hasattr(app, '_active_ui'):
                            try:
                                ui = app._active_ui
                                ui['btn_build'].disabled = False
                                ui['btn_clear'].disabled = False
                                ui['btn_build'].update()
                                ui['btn_clear'].update()
                            except Exception: pass
                            
                        app.show_snack_bar(f"❌ 《{target_book_name}》后台建库中断: {str(ex)}")
                        
                threading.Thread(target=build_task, daemon=True).start()

            def close_confirm(e):
                confirm_dlg.open = False
                app.page.update()

            def confirm_action(e):
                confirm_dlg.open = False
                app.page.update()
                do_build()

            if "已建库" in status_text.value:
                confirm_dlg = ft.AlertDialog(
                    title=ft.Text("重新建库确认", weight=ft.FontWeight.BOLD),
                    content=ft.Text("本书已存在向量索引，重新建库将覆盖原有数据。是否继续？"),
                    actions=[
                        ft.TextButton(content=ft.Text("取消"), on_click=close_confirm),
                        ft.TextButton(content=ft.Text("确认重建"), style=ft.ButtonStyle(color=ft.Colors.RED), on_click=confirm_action)
                    ]
                )
            else:
                confirm_dlg = ft.AlertDialog(
                    title=ft.Text("建库确认", weight=ft.FontWeight.BOLD),
                    content=ft.Text("即将调用大模型 API 对全书进行向量化切块，可能需要消耗一定的时间和 Token 额度。是否开始？\n\n(提示：开始后您可以关闭此弹窗继续阅读，系统会在后台静默完成并通知您)"),
                    actions=[
                        ft.TextButton(content=ft.Text("取消"), on_click=close_confirm),
                        ft.TextButton(content=ft.Text("开始建库"), on_click=confirm_action)
                    ]
                )
            app.page.overlay.append(confirm_dlg)
            confirm_dlg.open = True
            app.page.update()

        def on_clear_click(e):
            if not app.current_book_path: return
            if "未建立" in status_text.value:
                app.show_snack_bar("⚠️ 尚无索引可清除")
                return
            
            def do_clear():
                import hashlib
                import os
                from data.storage import StorageManager
                try:
                    from core.vector_db import VectorDB
                except ImportError:
                    app.show_snack_bar("⚠️ 未安装 sqlite-vec 扩展")
                    return
                    
                book_hash = hashlib.md5(app.current_book_path.encode('utf-8')).hexdigest()
                db_path = os.path.join(StorageManager.get_base_dir(), "vector_dbs", f"{book_hash}.db")
                if os.path.exists(db_path):
                    vdb = VectorDB(db_path)
                    vdb.clear_index()
                    status_text.value = f"当前阅读：《{book_name}》\n索引状态：未建立"
                    btn_build.content.value = "🚀 向量建库"
                    app.show_snack_bar("🧹 索引已清除")
                    try: tab3_col.update()
                    except Exception: pass

            def close_clear(e):
                confirm_dlg.open = False
                app.page.update()

            def confirm_clear(e):
                confirm_dlg.open = False
                app.page.update()
                do_clear()

            confirm_dlg = ft.AlertDialog(
                title=ft.Text("清除索引确认", weight=ft.FontWeight.BOLD),
                content=ft.Text("确定要清除本书的向量索引吗？清除后 RAG 全书检索将失效，此操作不可逆。"),
                actions=[
                    ft.TextButton(content=ft.Text("取消"), on_click=close_clear),
                    ft.TextButton(content=ft.Text("确认清除"), style=ft.ButtonStyle(color=ft.Colors.RED), on_click=confirm_clear)
                ]
            )
            app.page.overlay.append(confirm_dlg)
            confirm_dlg.open = True
            app.page.update()
                
        btn_build.on_click = on_build_click
        btn_clear.on_click = on_clear_click

        tab3_col = ft.Column([
            ft.Container(height=10),
            status_text, 
            ft.Container(height=20),
            prog_bar, 
            prog_text, 
            ft.Container(height=20),
            action_row,
            ft.Container(height=20),
            ft.Divider(height=1, thickness=0.5),
            ft.Container(height=10),
            top_k_container
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)

        # =========================================================
        # 💥 Flet 0.84.0 破坏性更新真正跟进 (Tabs 组件重构)
        # 彻底采用 Flutter 分离架构：TabBar 负责顶栏按钮，TabBarView 负责页面装载
        tab_bar = ft.TabBar(
            tabs=[
                ft.Tab(label="对话模型"),
                ft.Tab(label="向量引擎"),
                ft.Tab(label="本书知识库")
            ]
        )
        
        tab_view = ft.TabBarView(
            controls=[
                tab1_container,
                tab2_container,
                ft.Container(
                    content=tab3_col, 
                    padding=ft.padding.all(15)
                )
            ],
            expand=True
        )

        tabs = ft.Tabs(
            selected_index=0,
            length=3,
            expand=True,
            content=ft.Column(
                controls=[tab_bar, tab_view], 
                expand=True
            )
        )
        # =========================================================

        def save(e):
            app.ai_config["url"] = url_tf.value.strip()
            app.ai_config["key"] = key_tf.value.strip()
            app.ai_config["model"] = model_tf.value.strip()
            app.ai_config["prompt"] = prompt_tf.value.strip()
            
            app.ai_config["embed_mode"] = embed_mode_dd.value
            app.ai_config["embed_url"] = embed_url_tf.value.strip()
            app.ai_config["embed_key"] = embed_key_tf.value.strip()
            app.ai_config["embed_model"] = embed_model_tf.value.strip()
            # 💥 修正点：保存时严格对齐为 local_model_path，以驱动本地计算
            app.ai_config["local_model_path"] = local_model_dd.value if local_model_dd.value else ""
            app.ai_config["top_k"] = int(top_k_slider.value) 
            
            app._save_config_to_appdata()
            app._close_dialog()
            app.show_snack_bar("✅ AI 配置已保存")

        app.global_dialog.title = ft.Text("设置与知识库中心", size=18, weight=ft.FontWeight.BOLD, color="onSurface")
        app.global_dialog.content = ft.Container(content=tabs, width=500, height=450)
        
        app.global_dialog.actions = [
            ft.Button(content=ft.Text("保存并关闭"), on_click=save, style=app.get_action_button_style()),
            ft.Button(content=ft.Text("取消"), on_click=lambda _: app._close_dialog(), style=app.get_action_button_style())
        ]
        app._open_dialog()

    @staticmethod
    def show_global_settings_dialog(app, e):
        app.global_dialog.modal = False
        app.global_dialog.inset_padding = None
        app.global_dialog.content_padding = ft.padding.only(left=20, top=15, right=20, bottom=15)

        backup_row = ft.Row([
            ft.Button(content=ft.Row([ft.Icon(ft.Icons.UPLOAD), ft.Text("导出备份", color="onSurface")]), on_click=app.export_app_data, style=app.get_action_button_style()),
            ft.Button(content=ft.Row([ft.Icon(ft.Icons.DOWNLOAD), ft.Text("恢复备份", color="onSurface")]), on_click=app.import_app_data, style=app.get_action_button_style())
        ], alignment=ft.MainAxisAlignment.SPACE_AROUND)

        app.global_dialog.title = ft.Text("⚙️ 全局设置", size=18, weight=ft.FontWeight.BOLD, color="onSurface")
        app.global_dialog.content = ft.Column([
            ft.Text("数据安全", weight=ft.FontWeight.BOLD, size=14, color="onSurface"),
            ft.Text("本地备份包含所有书籍、阅读进度及 AI 总结数据", size=12, color=ft.Colors.GREY_500),
            ft.Container(height=5),
            backup_row
        ], tight=True)
        
        app.global_dialog.actions = [
            ft.Button(content=ft.Text("关闭", color="onSurface"), on_click=lambda _: app._close_dialog(), style=app.get_action_button_style())
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
        
        app.global_dialog.actions = [
            ft.Button(
                content=ft.Text("关闭", color="onSurface"), 
                on_click=lambda _: app._close_dialog(), 
                style=app.get_action_button_style()
            )
        ]
        app._open_dialog()

    # =========================================================================
    # 核心 AI 助手界面 (含 人物梳理 Pro 及防剧透检索)
    # =========================================================================
    @staticmethod
    def show_ai_dialog(app, e):
        if not app.engine.chapters_info: return
        app.global_dialog.modal = True
        target_idx = app.current_chapter_idx
        ch_info = app.engine.chapters_info[target_idx]
        
        target_idx_str = str(target_idx)
        saved_data = app.current_book_summaries.get(target_idx_str, {})
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

        btn_regen = ft.Button(content=ft.Text("总结"), style=ft.ButtonStyle(bgcolor=ft.Colors.DEEP_PURPLE_400, color=ft.Colors.WHITE))
        
        btn_copy = ft.Button(content=ft.Text("复制", color="onSurface"), style=app.get_action_button_style())
        btn_close = ft.Button(content=ft.Text("关闭", color="onSurface"), on_click=lambda _: app._close_dialog(), style=app.get_action_button_style())

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
        
        # char_row = ft.Row([mode_btn_char, mode_btn_char_pro], spacing=5, alignment=ft.MainAxisAlignment.CENTER)
        app.global_dialog.actions = [
            ft.Container(
                content=ft.Column([
                    # 💥 彻底拆掉 char_row，让 4 个按钮平起平坐，全部享受自由间距！
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