import flet as ft
import hashlib
import os
import threading
import asyncio
from data.storage import StorageManager
from core.ai_service import AIService

def get_ai_settings_view(app):
    UI_WIDTH = 500  

    def go_back(e):
        app.page.run_task(app.page.push_route, "/reader")

    # ==========================================
    # Tab 1: 对话模型配置
    # ==========================================
    url_tf = ft.TextField(label="API URL", value=app.ai_config.get("url", ""), text_size=13, dense=True, width=UI_WIDTH)
    key_tf = ft.TextField(label="API Key", value=app.ai_config.get("key", ""), password=True, can_reveal_password=True, text_size=13, dense=True, width=UI_WIDTH)
    model_tf = ft.TextField(label="模型名称", value=app.ai_config.get("model", ""), text_size=13, dense=True, width=UI_WIDTH)
    prompt_tf = ft.TextField(label="系统提示词", value=app.ai_config.get("prompt", ""), multiline=True, min_lines=3, max_lines=5, text_size=13, dense=True, width=UI_WIDTH)
    
    tab1_col = ft.Column([url_tf, key_tf, model_tf, prompt_tf], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    tab1_container = ft.Container(content=tab1_col, padding=ft.padding.only(left=20, top=20, right=20, bottom=10))

    # ==========================================
    # Tab 2: 向量引擎配置
    # ==========================================
    embed_url_tf = ft.TextField(label="Embedding API URL", value=app.ai_config.get("embed_url", ""), text_size=13, dense=True, width=UI_WIDTH)
    embed_key_tf = ft.TextField(label="API Key", value=app.ai_config.get("embed_key", ""), password=True, can_reveal_password=True, text_size=13, dense=True, width=UI_WIDTH)
    embed_model_tf = ft.TextField(label="模型名称 (如 text-embedding-3-small)", value=app.ai_config.get("embed_model", ""), text_size=13, dense=True, width=UI_WIDTH)
    cloud_view = ft.Column([embed_url_tf, embed_key_tf, embed_model_tf], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    local_models = app.get_local_models()
    saved_local_model = app.ai_config.get("local_model_path", "")
    local_model_dd = ft.Dropdown(
        label="已导入的本地模型",
        options=[ft.dropdown.Option(m) for m in local_models],
        value=saved_local_model if saved_local_model in local_models else None,
        text_size=13, dense=True, expand=True
    )
    import_btn = ft.IconButton(
        icon=ft.Icons.FOLDER_OPEN, icon_color="blue", tooltip="导入本地模型文件",
        on_click=lambda _: app.page.run_task(app.trigger_model_picker, local_model_dd)
    )
    local_path_row = ft.Row([local_model_dd, import_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=UI_WIDTH)
    local_view = ft.Column([local_path_row], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    content_slot = ft.Container()

    def on_embed_mode_change(e):
        mode = e.data if e and getattr(e, "data", None) else embed_mode_dd.value
        if e and getattr(e, "data", None):
            embed_mode_dd.value = mode

        content_slot.content = local_view if mode == "本地模型" else cloud_view
        try:
            content_slot.update()
            app.page.update()
        except Exception: pass
        
    embed_mode_dd = ft.Dropdown(
        label="工作模式", 
        options=[ft.dropdown.Option("云端 API"), ft.dropdown.Option("本地模型")], 
        value=app.ai_config.get("embed_mode", "云端 API"),
        text_size=13, dense=True, width=UI_WIDTH
    )
    # 稳健挂载法
    embed_mode_dd.on_change = on_embed_mode_change

    content_slot.content = local_view if embed_mode_dd.value == "本地模型" else cloud_view

    tab2_col = ft.Column([embed_mode_dd, ft.Container(height=5), content_slot], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    tab2_container = ft.Container(content=tab2_col, padding=ft.padding.only(left=20, top=20, right=20, bottom=10))

    # ==========================================
    # Tab 3: 本书知识库 
    # ==========================================
    book_name = app.current_book_name if getattr(app, 'current_book_name', "") else "未打开任何书籍"
    status_text = ft.Text(f"当前阅读：《{book_name}》\n索引状态：未建立", size=14, color="onSurface", text_align=ft.TextAlign.CENTER)
    
    init_prog_val = getattr(app, "build_progress_value", 0)
    init_prog_text = getattr(app, "build_progress_text", "准备切块中...")
    is_building = getattr(app, "is_building_index", False)
    
    prog_bar = ft.ProgressBar(value=init_prog_val, visible=is_building, color="blue", height=8, width=UI_WIDTH)
    prog_text = ft.Text(init_prog_text, size=12, color="grey", visible=is_building)
    
    btn_build = ft.ElevatedButton(content=ft.Text("🚀 向量建库"), style=app.get_action_button_style(ft.padding.symmetric(horizontal=16, vertical=12)))
    btn_clear = ft.ElevatedButton(content=ft.Text("🧹 清除索引", color="black"), style=ft.ButtonStyle(bgcolor="red", color="black"))
    
    action_row = ft.Row([btn_build, btn_clear], alignment=ft.MainAxisAlignment.CENTER, spacing=20)
    
    top_k_val = app.ai_config.get("top_k", 5)
    top_k_text = ft.Text(f"检索数量 (top_k): {top_k_val} 段", size=13, color="onSurface")
    
    def on_top_k_change(e):
        val = int(e.control.value)
        top_k_text.value = f"检索数量 (top_k): {val} 段"
        try: top_k_text.update()
        except Exception: pass

    top_k_slider = ft.Slider(min=1, max=10, divisions=9, value=top_k_val, label="{value} 段", on_change=on_top_k_change, width=UI_WIDTH)
    
    top_k_container = ft.Column([
        ft.Row([ft.Icon(ft.Icons.TUNE, size=16, color="grey"), top_k_text], alignment=ft.MainAxisAlignment.START),
        top_k_slider,
        ft.Text("提示: 数值越大提供的背景知识越多，但也越容易分散大模型注意力或导致 API 超时。", size=11, color="grey", text_align=ft.TextAlign.LEFT)
    ], spacing=5)

    app._active_ui = {
        'prog_bar': prog_bar, 'prog_text': prog_text,
        'btn_build': btn_build, 'btn_clear': btn_clear, 'status_text': status_text
    }

    def refresh_db_status():
        if not app.current_book_path: return
        try:
            from core.vector_db import VectorDB
        except ImportError:
            status_text.value = f"当前阅读：《{book_name}》\n⚠️ 未安装 sqlite-vec 扩展库，知识库暂不可用"
            btn_build.disabled = btn_clear.disabled = True
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

    if is_building:
        btn_build.content.value = "⏳ 后台建库中..."
        btn_build.disabled = btn_clear.disabled = True
    else:
        refresh_db_status()
    
    def on_build_click(e):
        if not app.current_book_path:
            app.show_snack_bar("⚠️ 请先在首页打开一本小说")
            return

        def do_build():
            target_book_path = app.current_book_path
            target_book_name = app.current_book_name
            target_chapters = app.engine.chapters_info.copy()
            
            app.is_building_index = True
            app.build_progress_value = 0
            app.build_progress_text = "正在进行滑动窗口分块..."
            
            btn_build.content.value = "⏳ 后台建库中..."
            btn_build.disabled = btn_clear.disabled = True
            prog_bar.visible = prog_text.visible = True
            prog_bar.value = app.build_progress_value
            prog_text.value = app.build_progress_text
            try: tab3_col.update()
            except Exception: pass

            def build_task():
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
                    from core.chunker import NovelChunker
                    from core.ai_service import AIService
                    try:
                        from core.vector_db import VectorDB
                    except ImportError:
                        safe_update_ui(0, "❌ 启动失败：缺少 sqlite-vec 依赖")
                        app.page.update()
                        return
                    
                    book_hash = hashlib.md5(target_book_path.encode('utf-8')).hexdigest()
                    db_dir = os.path.join(StorageManager.get_base_dir(), "vector_dbs")
                    os.makedirs(db_dir, exist_ok=True)
                    db_path = os.path.join(db_dir, f"{book_hash}.db")
                    
                    chunker = NovelChunker(chunk_size=500, overlap=50)
                    all_chunks = []
                    
                    for idx, ch in enumerate(target_chapters):
                        chunks = chunker.chunk_text(app.engine.get_chapter_text(idx))
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
                        
                        batch_texts = [c[1] for c in batch]
                        batch_embs = AIService.get_embeddings(app.ai_config, batch_texts)

                        db_data = []
                        for idx_in_batch, (chapter_idx, chunk_text) in enumerate(batch):
                            emb = batch_embs[idx_in_batch]
                            db_data.append((chapter_idx, chunk_text, emb))
                            
                        vdb.insert_chunks(db_data)
                        
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
                    ft.TextButton(content=ft.Text("确认重建"), style=ft.ButtonStyle(color="red"), on_click=confirm_action)
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
                ft.TextButton(content=ft.Text("确认清除"), style=ft.ButtonStyle(color="red"), on_click=confirm_clear)
            ]
        )
        app.page.overlay.append(confirm_dlg)
        confirm_dlg.open = True
        app.page.update()
            
    btn_build.on_click = on_build_click
    btn_clear.on_click = on_clear_click

    tab3_col = ft.Column([
        ft.Container(height=10), status_text, ft.Container(height=20),
        prog_bar, prog_text, ft.Container(height=20),
        action_row, ft.Container(height=20),
        ft.Divider(height=1, thickness=0.5), ft.Container(height=10),
        top_k_container
    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)

    tab3_container = ft.Container(content=tab3_col, padding=ft.padding.all(20))

    # ==========================================
    # 保存与组装层
    # ==========================================
    def save(e):
        app.ai_config["url"] = url_tf.value.strip()
        app.ai_config["key"] = key_tf.value.strip()
        app.ai_config["model"] = model_tf.value.strip()
        app.ai_config["prompt"] = prompt_tf.value.strip()
        
        app.ai_config["embed_mode"] = embed_mode_dd.value
        app.ai_config["embed_url"] = embed_url_tf.value.strip()
        app.ai_config["embed_key"] = embed_key_tf.value.strip()
        app.ai_config["embed_model"] = embed_model_tf.value.strip()
        app.ai_config["local_model_path"] = local_model_dd.value if local_model_dd.value else ""
        app.ai_config["top_k"] = int(top_k_slider.value) 
        
        app._save_config_to_appdata()
        app.show_snack_bar("✅ AI 配置已保存")
        go_back(None)

    # 💥 完全使用你原版 dialogs.py 中的稳健结构
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
            tab3_container
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
    
    bottom_bar = ft.Container(
        content=ft.Row([
            ft.TextButton(content=ft.Text("取消"), on_click=go_back),
            ft.ElevatedButton(content=ft.Text("保存设置并返回"), bgcolor="blue", color="white", on_click=save)
        ], alignment=ft.MainAxisAlignment.END),
        padding=10,
        bgcolor="surfaceVariant"
    )

    return ft.View(
        route="/reader/ai_settings",
        appbar=ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=go_back),
            title=ft.Text("AI 设置与知识库中心", size=18, weight="bold"),
            center_title=True,
            bgcolor="surfaceVariant"
        ),
        controls=[
            ft.Container(content=tabs, expand=True),
            bottom_bar
        ],
        padding=0,
        bgcolor="surface"
    )