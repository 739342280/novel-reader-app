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
        # 🚨 【路由纪律：禁止修改】：统一调用主控制器的 view_pop 进行退栈。
        # 严禁在此处直接使用 app.page.go("/reader") 或 push_route，以避免与安卓原生弹栈动画发生时序撕裂。
        app.view_pop(None)

    # ==========================================
    # Tab 1: 对话模型配置 (UI升级：卡片化与折叠)
    # ==========================================
    # 💥 修改点：为所有输入框增加固定宽度，防止无限拉伸
    INPUT_WIDTH = 450 

    url_tf = ft.TextField(label="API URL", value=app.ai_config.get("url", ""), text_size=13, dense=True, width=INPUT_WIDTH)
    key_tf = ft.TextField(label="API Key", value=app.ai_config.get("key", ""), password=True, can_reveal_password=True, text_size=13, dense=True, width=INPUT_WIDTH)
    model_tf = ft.TextField(label="模型名称", value=app.ai_config.get("model", ""), text_size=13, dense=True, width=INPUT_WIDTH)
    
    prompt_tf = ft.TextField(label="系统提示词", value=app.ai_config.get("prompt", ""), multiline=True, min_lines=3, max_lines=5, text_size=13, dense=True, width=INPUT_WIDTH)
    
    prompt_char_tf = ft.TextField(label="系统提示词 (人物模式)", value=app.ai_config.get("prompt_char", ""), multiline=True, min_lines=3, max_lines=5, text_size=13, dense=True, width=INPUT_WIDTH)
    prompt_clue_tf = ft.TextField(label="系统提示词 (伏笔模式)", value=app.ai_config.get("prompt_clue", ""), multiline=True, min_lines=3, max_lines=5, text_size=13, dense=True, width=INPUT_WIDTH)
    
    expansion_prompts = ft.ExpansionTile(
        title=ft.Text("高级提示词设置 (人物/伏笔)", size=13, weight="bold"),
        subtitle=ft.Text("通常无需修改，除非您想自定义分析深度", size=11, color="grey"),
        width=INPUT_WIDTH, # 💥 折叠面板也限宽
        controls=[
            ft.Container(
                content=ft.Column([prompt_char_tf, prompt_clue_tf], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.only(top=10, bottom=10)
            )
        ],
        maintain_state=True
    )

    tab1_container = ft.Container(
        content=ft.Column([
            ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.LOCK, size=16), ft.Text("API 身份认证", weight="bold")], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                        url_tf, key_tf, model_tf
                    ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER), # 💥 改为居中
                    padding=15
                ),
                elevation=1
            ),
            ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.EDIT, size=16), ft.Text("模型指令配置", weight="bold")], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                        prompt_tf,
                        expansion_prompts
                    ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER), # 💥 改为居中
                    padding=15
                ),
                elevation=1
            )
        ], spacing=15, scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.CENTER), # 💥 父级 Column 也居中
        padding=20
    )
    
    # ==========================================
    # Tab 2: 向量引擎配置 (重构：静态三卡片布局)
    # ==========================================
    
    # 1. 基础控件定义 (保持限宽 INPUT_WIDTH)
    embed_url_tf = ft.TextField(label="Embedding API URL", value=app.ai_config.get("embed_url", ""), text_size=13, dense=True, width=INPUT_WIDTH)
    embed_key_tf = ft.TextField(label="API Key", value=app.ai_config.get("embed_key", ""), password=True, can_reveal_password=True, text_size=13, dense=True, width=INPUT_WIDTH)
    embed_model_tf = ft.TextField(label="模型名称", value=app.ai_config.get("embed_model", ""), text_size=13, dense=True, width=INPUT_WIDTH)
    
    local_models = app.get_local_models()
    local_model_dd = ft.Dropdown(
        label="已导入的本地模型",
        options=[ft.dropdown.Option(m) for m in local_models],
        value=app.ai_config.get("local_model_path", "") if app.ai_config.get("local_model_path", "") in local_models else None,
        text_size=13, dense=True, width=INPUT_WIDTH - 60 
    )
    import_btn = ft.IconButton(
        icon=ft.Icons.FOLDER_OPEN, icon_color="blue", tooltip="导入本地模型文件",
        on_click=lambda _: app.page.run_task(app.trigger_model_picker, local_model_dd)
    )

    embed_mode_dd = ft.Dropdown(
        label="当前生效工作模式", 
        options=[ft.dropdown.Option("云端 API"), ft.dropdown.Option("本地模型")], 
        value=app.ai_config.get("embed_mode", "云端 API"),
        text_size=13, dense=True, width=INPUT_WIDTH
    )

    # 2. 组装成三个独立的卡片，彻底抛弃动态切换逻辑
    tab2_container = ft.Container(
        content=ft.Column([
            # 卡片一：全局工作模式设定
            ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.HUB, size=16), ft.Text("全局模式设定", weight="bold")], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                        embed_mode_dd,
                        ft.Text("提示: 此选项决定系统最终使用下方哪一套配置进行建库和检索", size=11, color="grey", text_align=ft.TextAlign.CENTER)
                    ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=15
                ),
                elevation=1
            ),
            
            # 卡片二：本地模型设定
            ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.COMPUTER, size=16), ft.Text("本地模型设定", weight="bold")], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                        ft.Row([local_model_dd, import_btn], alignment=ft.MainAxisAlignment.CENTER, spacing=10)
                    ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=15
                ),
                elevation=1
            ),
            
            # 卡片三：云端 API 设定
            ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.CLOUD, size=16), ft.Text("云端 API 设定", weight="bold")], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                        embed_url_tf, embed_key_tf, embed_model_tf
                    ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=15
                ),
                elevation=1
            )
        ], spacing=15, scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=20
    )

    # ==========================================
    # Tab 3: 本书知识库 (100% 还原业务逻辑，UI升级为仪表盘)
    # ==========================================
    book_name = app.current_book_name if getattr(app, 'current_book_name', "") else "未打开任何书籍"
    status_text = ft.Text(f"当前阅读：《{book_name}》\n索引状态：未建立", size=14, color="onSurface", text_align=ft.TextAlign.CENTER)
    
    # 动态状态仪表盘
    status_card = ft.Container(
        content=ft.Column([
            ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, size=20), ft.Text("知识库运行状态", weight="bold")], alignment=ft.MainAxisAlignment.CENTER),
            status_text,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=20,
        border_radius=12,
        bgcolor="surfaceVariant", 
        # 💥 修复：直接使用大写的 ft.Animation
        animate=ft.Animation(300, ft.AnimationCurve.DECELERATE)
    )

    init_prog_val = getattr(app, "build_progress_value", 0)
    init_prog_text = getattr(app, "build_progress_text", "准备切块中...")
    is_building = getattr(app, "is_building_index", False)
    
    prog_bar = ft.ProgressBar(value=init_prog_val, visible=is_building, color="blue", height=8, width=INPUT_WIDTH) # 💥 加上宽度
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

    top_k_slider = ft.Slider(min=1, max=10, divisions=9, value=top_k_val, label="{value} 段", on_change=on_top_k_change)
    
    top_k_card = ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.TUNE, size=16), ft.Text("检索性能参数", weight="bold")]),
                top_k_text,
                top_k_slider,
                ft.Text("提示: 数值越大提供的背景知识越多，但也越容易分散大模型注意力或导致 API 超时。", size=11, color="grey")
            ], spacing=10),
            padding=15
        ),
        elevation=1
    )

    app._active_ui = {
        'prog_bar': prog_bar, 'prog_text': prog_text,
        'btn_build': btn_build, 'btn_clear': btn_clear, 'status_text': status_text, 'status_card': status_card
    }

    def refresh_db_status():
        if not app.current_book_path: return
        try:
            from core.vector_db import VectorDB
        except ImportError:
            status_text.value = f"当前阅读：《{book_name}》\n⚠️ 未安装 sqlite-vec 扩展库，知识库暂不可用"
            btn_build.disabled = btn_clear.disabled = True
            return

        book_hash = hashlib.md5(app.current_book_path.encode('utf-8')).hexdigest()
        db_path = os.path.join(StorageManager.get_base_dir(), "vector_dbs", f"{book_hash}.db")
        if os.path.exists(db_path):
            try:
                vdb = VectorDB(db_path)
                status = vdb.get_index_status()
                if status["is_indexed"]:
                    status_text.value = f"当前阅读：《{book_name}》\n索引状态：已建库 ({status['chunk_count']} 个切块)"
                    status_card.bgcolor = ft.Colors.with_opacity(0.15, ft.Colors.GREEN) # 建库后变色
                    btn_build.content.value = "🔁 重新建库"
                else:
                    status_card.bgcolor = "surfaceVariant"
                    btn_build.content.value = "🚀 向量建库"
            except Exception: 
                btn_build.content.value = "🚀 向量建库"
        else:
            status_card.bgcolor = "surfaceVariant"
            btn_build.content.value = "🚀 向量建库"
            
        try: status_card.update()
        except Exception: pass

    if is_building:
        btn_build.content.value = "⏳ 后台建库中..."
        btn_build.disabled = btn_clear.disabled = True
    else:
        refresh_db_status()
    
    def on_build_click(e):
        if not app.current_book_path:
            app.show_snack_bar("⚠️ 请先在首页打开一本小说")
            return

        # 快照当前书籍信息（防止在建库过程中用户切换书籍）
        target_book_path = app.current_book_path
        target_book_name = app.current_book_name
        target_chapters = app.engine.chapters_info.copy()

        def do_build():
            nonlocal target_book_path, target_book_name, target_chapters

            app.is_building_index = True
            app.build_progress_value = 0
            app.build_progress_text = "正在初始化引擎..."

            # 更新 UI 按钮初始状态
            btn_build.content.value = "⏳ 后台建库中..."
            btn_build.disabled = btn_clear.disabled = True
            prog_bar.visible = prog_text.visible = True
            prog_bar.value = 0
            prog_text.value = app.build_progress_text
            
            try:
                tab3_col.update()
                app.page.update()
            except Exception: pass

            # 💥 核心修复：听你的建议，引入“定时刷新”的 UI 监控协程
            async def progress_updater():
                last_val = -1
                last_text = ""
                # 只要还在建库，这个监控器就会一直运行
                while getattr(app, "is_building_index", False):
                    curr_val = getattr(app, "build_progress_value", 0)
                    curr_text = getattr(app, "build_progress_text", "")
                    
                    # 只有当进度真的发生变化时，才通知 UI 刷新
                    if curr_val != last_val or curr_text != last_text:
                        try:
                            prog_bar.value = curr_val
                            prog_text.value = curr_text
                            prog_bar.update()
                            prog_text.update()
                        except Exception: pass
                        last_val = curr_val
                        last_text = curr_text
                    
                    # 每 0.5 秒醒来刷新一次，既能保证视觉连贯，又绝对不卡顿
                    await asyncio.sleep(0.5)

            # 让 Flet 主循环启动这个定时监控器
            app.page.run_task(progress_updater)

            def build_task(path, name, chapters):
                import traceback
                import time

                def safe_update_ui(val, text):
                    # 💥 后台线程现在只负责静默修改变量，绝对不去碰 .update()
                    app.build_progress_value = val
                    app.build_progress_text = text

                try:
                    from core.chunker import NovelChunker
                    from core.ai_service import AIService
                    from core.vector_db import VectorDB
                    
                    book_hash = hashlib.md5(path.encode('utf-8')).hexdigest()
                    db_dir = os.path.join(StorageManager.get_base_dir(), "vector_dbs")
                    os.makedirs(db_dir, exist_ok=True)
                    db_path = os.path.join(db_dir, f"{book_hash}.db")

                    # 1. 文本分块
                    safe_update_ui(0, "✂️ 正在进行滑动窗口分块...")
                    chunker = NovelChunker(chunk_size=500, overlap=50)
                    all_chunks = []
                    for idx, ch in enumerate(chapters):
                        chunks = chunker.chunk_text(app.engine.get_chapter_text(idx))
                        for c in chunks:
                            all_chunks.append((idx, c))

                    total = len(all_chunks)
                    if total == 0: raise Exception("提取不到书籍文本内容")

                    # 2. 获取向量维度
                    safe_update_ui(0.05, f"🔍 正在获取 Embedding 维度 (总块数: {total})...")
                    first_emb = AIService.get_embedding(app.ai_config, all_chunks[0][1])
                    dim = len(first_emb)

                    # 3. 初始化数据库 (显式清除防止叠加)
                    vdb = VectorDB(db_path)
                    vdb.clear_index() 
                    vdb.init_tables(dim)

                    # 4. 批量向量化
                    batch_size = 15
                    total_batches = (total + batch_size - 1) // batch_size
                    
                    for batch_idx in range(0, total, batch_size):
                        batch = all_chunks[batch_idx:batch_idx+batch_size]
                        current_batch_num = batch_idx // batch_size + 1
                        percent = batch_idx / total
                        current_end = min(batch_idx + batch_size, total)
                        
                        safe_update_ui(percent, f"🧠 推理中 (批次 {current_batch_num}/{total_batches} | 第 {batch_idx+1}-{current_end}/{total} 块)")

                        batch_texts = [c[1] for c in batch]
                        start_time = time.time()
                        batch_embs = AIService.get_embeddings(app.ai_config, batch_texts)
                        cost = time.time() - start_time

                        db_data = []
                        for i_b, (ch_idx, text) in enumerate(batch):
                            db_data.append((ch_idx, text, batch_embs[i_b]))

                        safe_update_ui(percent + (0.1 / total_batches), f"💾 写入索引 (本批次耗时 {cost:.1f}s)...")
                        vdb.insert_chunks(db_data)

                    # 5. 完成：通知监控器停止，并进行最后的大清洗式刷新
                    app.is_building_index = False
                    safe_update_ui(1.0, "🎉 建库大功告成！")
                    
                    # 此时后台重算结束，主线程完全空闲，可以直接安全地 update
                    if hasattr(app, '_active_ui'):
                        try:
                            ui = app._active_ui
                            ui['status_text'].value = f"当前阅读：《{name}》\n索引状态：已建库 ({total} 个切块)"
                            ui['status_card'].bgcolor = ft.Colors.with_opacity(0.15, ft.Colors.GREEN)
                            ui['btn_build'].content.value = "🔁 重新建库"
                            ui['btn_build'].disabled = False
                            ui['btn_clear'].disabled = False
                            
                            # 💥 核心修复：强行隐藏进度条和文字
                            ui['prog_bar'].visible = False
                            ui['prog_text'].visible = False

                            ui['status_text'].update()
                            ui['status_card'].update()
                            ui['btn_build'].update()
                            ui['btn_clear'].update()
                            ui['prog_bar'].update() # 💥 推送隐藏状态
                            ui['prog_text'].update() # 💥 推送隐藏状态
                            
                            # 给监控器一点时间渲染最后一条文字，然后收尾
                            time.sleep(0.5)
                            app.page.update()
                        except Exception: pass
                        
                    app.show_snack_bar(f"✅ 《{name}》全书向量建库已完成！")
                    
                except Exception as ex:
                    app.is_building_index = False
                    safe_update_ui(app.build_progress_value, f"❌ 建库失败: {str(ex)}")
                    if hasattr(app, '_active_ui'):
                        try:
                            ui = app._active_ui
                            ui['btn_build'].disabled = False
                            ui['btn_clear'].disabled = False
                            # 💥 如果建库失败，同样应该隐藏进度条，防止卡在界面上
                            ui['prog_bar'].visible = False
                            ui['prog_text'].visible = False

                            ui['btn_build'].update()
                            ui['btn_clear'].update()
                            ui['prog_bar'].update()
                            ui['prog_text'].update()
                            app.page.update()
                        except Exception: pass
                    app.show_snack_bar(f"❌ 《{name}》后台建库中断: {str(ex)}")

            threading.Thread(target=build_task, args=(target_book_path, target_book_name, target_chapters), daemon=True).start()
        
        # 弹窗确认逻辑
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

    # 🚨 完整保留的业务核心代码：清除逻辑
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
                status_card.bgcolor = "surfaceVariant"
                btn_build.content.value = "🚀 向量建库"
                app.show_snack_bar("🧹 索引已清除")
                try: 
                    status_text.update()
                    status_card.update()
                    btn_build.update()
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
    
    # 💥 把这行直接删掉！不要了！
    # prog_bar = ft.ProgressBar(value=init_prog_val, visible=is_building, color="blue", height=8, width=INPUT_WIDTH)
    top_k_slider = ft.Slider(min=1, max=10, divisions=9, value=top_k_val, label="{value} 段", on_change=on_top_k_change, width=INPUT_WIDTH)
    
    # 将 status_card 也加上宽度限制
    status_card.width = INPUT_WIDTH

    tab3_col = ft.Column([
        status_card, 
        prog_bar, 
        prog_text, 
        action_row, 
        ft.Divider(height=20, thickness=0.5),
        # 💥 给 top_k_card 增加居中对齐
        ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([ft.Icon(ft.Icons.TUNE, size=16), ft.Text("检索性能参数", weight="bold")], alignment=ft.MainAxisAlignment.CENTER),
                    top_k_text,
                    top_k_slider,
                    ft.Text("提示: 数值越大提供的背景知识越多，但也越容易分散大模型注意力。", size=11, color="grey", text_align=ft.TextAlign.CENTER)
                ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=15
            ),
            elevation=1
        )
    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True, scroll=ft.ScrollMode.AUTO, spacing=15)

    tab3_container = ft.Container(content=tab3_col, padding=20)

    # ==========================================
    # 保存逻辑与控制器装配
    # ==========================================
    def save(e):
        app.ai_config["url"] = url_tf.value.strip()
        app.ai_config["key"] = key_tf.value.strip()
        app.ai_config["model"] = model_tf.value.strip()
        app.ai_config["prompt"] = prompt_tf.value.strip()
        app.ai_config["prompt_char"] = prompt_char_tf.value.strip() 
        app.ai_config["prompt_clue"] = prompt_clue_tf.value.strip() 

        app.ai_config["embed_mode"] = embed_mode_dd.value
        app.ai_config["embed_url"] = embed_url_tf.value.strip()
        app.ai_config["embed_key"] = embed_key_tf.value.strip()
        app.ai_config["embed_model"] = embed_model_tf.value.strip()
        app.ai_config["local_model_path"] = local_model_dd.value if local_model_dd.value else ""
        app.ai_config["top_k"] = int(top_k_slider.value) 
        
        app._save_config_to_appdata()
        app.show_snack_bar("✅ AI 配置已保存")

    # 💥 核心修复：创建一个专门用来动态装载内容的容器
    content_area = ft.Container(content=tab1_container, expand=True)

    # 监听原生 TabBar 的滑动/点击切换，手动更新下方的内容容器
    def handle_tab_change(e):
        idx = e.control.selected_index
        if idx == 0:
            content_area.content = tab1_container
        elif idx == 1:
            content_area.content = tab2_container
        elif idx == 2:
            content_area.content = tab3_container
            refresh_db_status() # 切换到知识库时自动刷新状态
        
        try: content_area.update()
        except Exception: pass

    # 💥 核心修复：添加 Flet 0.84.0 强制要求的 length 参数
    settings_tabs = ft.Tabs(
        length=3, # 💥 必须明确告诉控制器这里有 3 个选项卡
        selected_index=0,
        on_change=handle_tab_change,
        content=ft.TabBar(
            tab_alignment=ft.TabAlignment.CENTER, 
            tabs=[
                ft.Tab(label="对话模型", icon=ft.Icons.CHAT),
                ft.Tab(label="向量引擎", icon=ft.Icons.HUB),
                ft.Tab(label="全书知识库", icon=ft.Icons.STORAGE),
            ]
        )
    )

    # 像拼积木一样拼接：顶部的状态与导航 + 底部的动态内容区
    tabs_layout = ft.Column(
        controls=[
            settings_tabs,
            content_area
        ],
        expand=True,
        spacing=0
    )

    return ft.View(
        route="/reader/ai_settings",
        appbar=ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=go_back),
            title=ft.Text("AI 设置中心", size=18, weight="bold"),
            center_title=True,
            bgcolor="surfaceVariant",
            actions=[
                # 💥 软盘图标保存按钮
                ft.IconButton(icon=ft.Icons.SAVE, on_click=save, icon_color="primary", tooltip="保存设置"),
                # 💥 修改点：增加一个透明容器作为右边距 padding，数值你可以根据手感调整
                ft.Container(width=15) 
            ]
        ),
        controls=[tabs_layout], 
        padding=0,
        bgcolor="surface"
    )