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
    
    # 💥 新增：一键恢复默认提示词逻辑
    def restore_default_prompts(e):
        # 巧妙借用底座配置类，获取最纯净的“出厂设置”
        from core.config_state import ConfigStateMixin
        class TempConfig(ConfigStateMixin):
            def __init__(self):
                self.init_config_state()
        defaults = TempConfig().ai_config
        
        # 1. 更新屏幕上可见的三个输入框
        prompt_tf.value = defaults.get("prompt", "")
        prompt_char_tf.value = defaults.get("prompt_char", "")
        prompt_clue_tf.value = defaults.get("prompt_clue", "")
        
        # 2. 静默更新隐藏的提示词（它们目前没有独立 UI）
        app.ai_config["prompt_char_pro"] = defaults.get("prompt_char_pro", "")
        app.ai_config["prompt_chat"] = defaults.get("prompt_chat", "")
        
        try:
            prompt_tf.update()
            prompt_char_tf.update()
            prompt_clue_tf.update()
        except Exception: pass
        
        app.show_snack_bar("✅ 已载入最新系统内置提示词，请点击右上角【保存】生效！")

    # 💥 新增：重置按钮 UI（靠右排列，弱化视觉防止误触）
    btn_restore_prompts = ft.TextButton(
        icon=ft.Icons.RESTORE,
        content=ft.Text("恢复系统内置提示词"), # 💥 核心修复：用 content=ft.Text() 替代 text=
        icon_color="grey700",
        style=ft.ButtonStyle(color="grey700"),
        on_click=restore_default_prompts
    )
    restore_row = ft.Row([btn_restore_prompts], alignment=ft.MainAxisAlignment.CENTER, width=INPUT_WIDTH)

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
                        restore_row,
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
    
    # 💥 删掉这两行：不再去扫描 AppData 里的本地模型了
    # local_models = app.get_local_models() 
    # local_model_dd = ft.Dropdown(...)

    # 💥 替换为全新的绝对路径显示框
    local_model_tf = ft.TextField(
        label="本地模型绝对路径",
        value=app.ai_config.get("local_model_path", ""),
        text_size=13, dense=True, expand=True,
        read_only=True, # 设置为只读，强制用户只能通过右侧按钮选择，防止手残改错路径
        hint_text="请点击右侧按钮选择纯英文路径下的 .gguf 模型"
    )

    import_btn = ft.IconButton(
        icon=ft.Icons.FOLDER_OPEN, icon_color="blue", tooltip="选择本地模型文件",
        # 💥 注意：这里传给选择器的参数，从 local_model_dd 变成了 local_model_tf
        on_click=lambda _: app.page.run_task(app.trigger_model_picker, local_model_tf)
    )

    # 一键下载按钮
    download_btn = ft.IconButton(
        icon=ft.Icons.CLOUD_DOWNLOAD, icon_color="green", tooltip="一键获取官方推荐模型",
        on_click=lambda _: app.page.run_task(app.trigger_official_model_download, local_model_tf)
    )

    # 硬件加速模式下拉框
    hardware_mode_dd = ft.Dropdown(
        label="硬件加速模式", 
        options=[ft.dropdown.Option("强制GPU模式"), ft.dropdown.Option("强制 CPU 模式")], 
        value=app.ai_config.get("hardware_mode", "强制GPU模式"),
        text_size=13, dense=True, width=INPUT_WIDTH
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
                        ft.Row(
                            controls=[local_model_tf, import_btn, download_btn], 
                            alignment=ft.MainAxisAlignment.CENTER, 
                            spacing=10, 
                            width=INPUT_WIDTH  
                        ),
                        hardware_mode_dd,

                        # 💥 新增的 UI 提示，放在下拉框正下方
                        ft.Divider(height=5, thickness=0.5, color="transparent"),
                        ft.Text(
                            "💡 硬件加速提示: 若您的电脑装有 NVIDIA 显卡且驱动版本 >= 551.14，系统将自动开启 GPU 极速建库。\n否则将智能回退至纯 CPU 模式运行（速度稍慢，但不影响正常使用）。", 
                            size=11, 
                            color="grey", 
                            text_align=ft.TextAlign.CENTER
                        )
                    ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
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
        val = int(round(e.control.value)) # 💥 加了 round()
        top_k_text.value = f"检索数量 (top_k): {val} 段"
        try: top_k_text.update()
        except Exception: pass

    top_k_slider = ft.Slider(min=1, max=10, divisions=9, value=top_k_val, label="{value} 段", on_change=on_top_k_change)
    
    # 💥 新增 GPU 层数滑块
    gpu_layers_val = app.ai_config.get("n_gpu_layers", 10)
    gpu_layers_text = ft.Text(f"GPU 物理卸载层数: {gpu_layers_val} 层", size=13, color="onSurface")

    def on_gpu_layers_change(e):
        val = int(round(e.control.value)) # 💥 加了 round()
        gpu_layers_text.value = f"GPU 物理卸载层数: {val} 层"
        try: gpu_layers_text.update()
        except Exception: pass

    gpu_layers_slider = ft.Slider(min=0, max=32, divisions=32, value=gpu_layers_val, label="{value} 层", on_change=on_gpu_layers_change, width=INPUT_WIDTH)
    
    # 新增的 Batch Size 控件
    batch_size_val = app.ai_config.get("build_batch_size", 15) # 默认值给 15
    batch_size_text = ft.Text(f"建库批处理量 (Batch Size): {batch_size_val} 块", size=13, color="onSurface")

    def on_batch_size_change(e):
        val = int(round(e.control.value)) # 💥 加了 round()
        batch_size_text.value = f"建库批处理量 (Batch Size): {val} 块"
        try: batch_size_text.update()
        except Exception: pass

    # min=2, max=100, divisions=49 意味着每档步进为 (100 - 2) / 49 = 2
    batch_size_slider = ft.Slider(
        min=1,           # 最小允许到 1
        max=100,         # 最大到 100
        divisions=99,    # 严格划分为 99 份，保证每一档刚好是 1
        value=batch_size_val, 
        label="{value} 块", 
        on_change=on_batch_size_change, 
        width=INPUT_WIDTH
    )

    # 💥新增：物理运算切片 (n_ubatch) 档位滑块
    ubatch_map = {1: 256, 2: 512, 3: 1024}
    reverse_ubatch_map = {256: 1, 512: 2, 1024: 3}
    
    current_ubatch = app.ai_config.get("n_ubatch", 512)
    ubatch_slider_val = reverse_ubatch_map.get(current_ubatch, 2) # 默认第 2 档
    
    # 直接使用一个普通的 Text 控件，不再使用花哨的 TextSpan
    ubatch_text = ft.Text("", size=13, color="onSurface")

    def update_ubatch_label(val):
        real_val = ubatch_map[int(val)]
        if real_val == 256:
            mode_name = "（稳定模式）"
        elif real_val == 512:
            mode_name = "（均衡模式）"
        else:
            mode_name = "（极速模式）"
            
        # 💥 取消加粗，取消颜色，取消方括号，增加三个空格的间距
        ubatch_text.value = f"物理运算切片 (n_ubatch): {real_val}{mode_name}"
        
        try: ubatch_text.update()
        except Exception: pass

    def on_ubatch_change(e):
        update_ubatch_label(round(e.control.value)) # 💥 加了 round()

    # 设置 min=1, max=3, divisions=2，强制滑块只能停在 1, 2, 3 这三个整档位上
    ubatch_slider = ft.Slider(min=1, max=3, divisions=2, value=ubatch_slider_val, on_change=on_ubatch_change, width=INPUT_WIDTH)
    update_ubatch_label(ubatch_slider_val) # 初始化文字
    
    # 硬件并发通道数 (Parallelism) 控件
    parallel_val = app.ai_config.get("n_parallel", 8) # 默认甜点并发给 8
    parallel_text = ft.Text(f"硬件并发通道数 (Parallelism): {parallel_val}", size=13, color="onSurface")

    def on_parallel_change(e):
        val = int(round(e.control.value)) # 💥 加了 round()
        parallel_text.value = f"硬件并发通道数 (Parallelism): {val}"
        try: parallel_text.update()
        except Exception: pass

    # 范围 1 到 32，步进 1
    parallel_slider = ft.Slider(min=1, max=32, divisions=31, value=parallel_val, label="{value}", on_change=on_parallel_change, width=INPUT_WIDTH)

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

    # 💥 新增：将刷新器提取到页面根作用域
    async def progress_updater():
        last_val = -1
        last_text = ""
        # 只要还在建库，这个监控器就会一直运行
        while getattr(app, "is_building_index", False):
            curr_val = getattr(app, "build_progress_value", 0)
            curr_text = getattr(app, "build_progress_text", "")
            
            if curr_val != last_val or curr_text != last_text:
                try:
                    prog_bar.value = curr_val
                    prog_text.value = curr_text
                    prog_bar.update()
                    prog_text.update()
                except Exception: pass
                last_val = curr_val
                last_text = curr_text
            
            await asyncio.sleep(0.5)
    
    def refresh_db_status():
        # 💥 极点防御：如果后台正在建库，绝对不许去读半成品的数据库！
        if getattr(app, "is_building_index", False): 
            return
            
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
                    # 💥 精准识别半成品
                    if status.get("status") == "building":
                        status_text.value = f"当前阅读：《{book_name}》\n⚠️ 索引中断：仅完成 {status['chunk_count']} / {status.get('total_chunks', '?')} 块"
                        status_card.bgcolor = ft.Colors.with_opacity(0.15, ft.Colors.ORANGE) 
                        # 💥 变成继续建库！
                        btn_build.content.value = "▶️ 继续建库"
                    else:
                        status_text.value = f"当前阅读：《{book_name}》\n索引状态：已建库 ({status['chunk_count']} 个切块)"
                        status_card.bgcolor = ft.Colors.with_opacity(0.15, ft.Colors.GREEN) 
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

    # 💥 修改：重新进入页面时，如果正在建库，立刻唤醒新版监控器！
    if is_building:
        btn_build.content.value = "⏳ 后台建库中..."
        btn_build.disabled = btn_clear.disabled = True
        app.page.run_task(progress_updater) # 👈 加了这行
    else:
        refresh_db_status()
    
    def on_build_click(e):
        if not app.current_book_path:
            app.show_snack_bar("⚠️ 请先在首页打开一本小说")
            return

        # 💥 新增：暂停建库的触发器
        def pause_build(e):
            app.cancel_build_flag = True # 升起中止旗帜
            btn_build.content.value = "⏳ 正在安全暂停..."
            btn_build.disabled = True # 防止狂点
            try: btn_build.update()
            except Exception: pass

        # 快照当前书籍信息
        target_book_path = app.current_book_path
        target_book_name = app.current_book_name
        target_chapters = app.engine.chapters_info.copy()

        def do_build():
            nonlocal target_book_path, target_book_name, target_chapters

            app.is_building_index = True
            app.cancel_build_flag = False # 每次建库前清空旗帜
            app.build_progress_value = 0
            app.build_progress_text = "正在初始化引擎..."

            # 💥 核心修改：建库开始后，把建库按钮临时变成【暂停】按钮！
            btn_build.content.value = "⏸ 暂停建库"
            btn_build.on_click = pause_build # 临时替换点击事件
            btn_build.disabled = False # 必须保持可用，用户才能点暂停
            btn_clear.disabled = True
            prog_bar.visible = prog_text.visible = True
            prog_bar.value = 0
            prog_text.value = app.build_progress_text
            
            try:
                tab3_col.update()
                app.page.update()
            except Exception: pass

            
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
                    # 💥 在建库最开头，记录总起点时间
                    total_start_time = time.time()
                    from core.chunker import NovelChunker
                    from core.ai_service import AIService
                    from core.vector_db import VectorDB
                    
                    book_hash = hashlib.md5(path.encode('utf-8')).hexdigest()
                    db_dir = os.path.join(StorageManager.get_base_dir(), "vector_dbs")
                    os.makedirs(db_dir, exist_ok=True)
                    db_path = os.path.join(db_dir, f"{book_hash}.db")

                    # 1. 文本分块
                    safe_update_ui(0, "✂️ 正在进行滑动窗口分块...")
                    chunker = NovelChunker(chunk_size=350, overlap=50)
                    all_chunks = []
                    for idx, ch in enumerate(chapters):
                        chunks = chunker.chunk_text(app.engine.get_chapter_text(idx))
                        for c in chunks:
                            all_chunks.append((idx, c))

                    total = len(all_chunks)
                    if total == 0: raise Exception("提取不到书籍文本内容")

                    # 2. 唤醒底层引擎并进行探针探测
                    # 💥 终极革命：引入 JSONL 本地坚固快照缓存
                    import json
                    cache_path = os.path.join(db_dir, f"{book_hash}_cache.jsonl")
                    emb_cache = {}
                    if os.path.exists(cache_path):
                        safe_update_ui(0.01, "🔄 读取本地断点快照中...")
                        try:
                            with open(cache_path, 'r', encoding='utf-8') as f:
                                for line in f:
                                    if not line.strip(): continue
                                    data = json.loads(line)
                                    emb_cache[data["id"]] = data["emb"]
                        except Exception as e: 
                            print(f"读取快照失败: {e}")

                    # 2. 唤醒底层引擎并进行探针探测
                    if emb_cache:
                        # 如果有快照，直接从快照里获取模型维度，跳过探测动画秒进
                        dim = len(next(iter(emb_cache.values())))
                    else:
                        safe_update_ui(0.05, f"🔍 正在初始化推理引擎与探针探测 (总块数: {total})...")
                        first_emb = AIService.get_embedding(app.ai_config, all_chunks[0][1])
                        dim = len(first_emb)

                        # 探针结果分析与 UI 互动
                        if app.ai_config.get("embed_mode") == "本地模型" and app.ai_config.get("hardware_mode") == "强制GPU模式":
                            engine = getattr(AIService, '_local_engine', None)
                            if engine:
                                import sys
                                if sys.platform == "win32":
                                    safe_update_ui(0.05, "⚡ 桌面端 GPU 引擎就绪，全速建库中...")
                                else:
                                    reason = getattr(engine, 'vulkan_disable_reason', '')
                                    if reason:  
                                        app.show_snack_bar(f"⚠️ 探针报错: {reason}\n(已开启极限测试，将强行调用 GPU)")
                                        safe_update_ui(0.05, "⚡ 强行 GPU 点火，2秒后开始突围...")
                                        time.sleep(2)
                                    else:
                                        app.show_snack_bar("⚡ 探针探测通过！Vulkan GPU 加速已就绪。")
                                        safe_update_ui(0.05, "⚡ GPU 引擎点火成功，2秒后开始全速建库...")
                                        time.sleep(2)

                    # 💥 3. 放弃修补，直接物理毁灭旧库，保证 SQLite 100% 纯净无损
                    safe_update_ui(0.08, "🧹 净化底层数据库环境...")
                    import gc
                    vdb = VectorDB(db_path)
                    if hasattr(vdb, 'conn'): 
                        vdb.conn.close()
                    vdb = None
                    gc.collect()
                    try: 
                        os.remove(db_path)
                    except Exception: pass
                    
                    # 重生：创建全新纯洁的数据库
                    vdb = VectorDB(db_path)
                    vdb.init_tables(dim)
                    vdb.set_meta("status", "building")
                    vdb.set_meta("total_chunks", str(total))

                    # 4. 批量向量化 (带缓存穿透)
                    batch_size = app.ai_config.get("build_batch_size", 15)
                    total_batches = (total + batch_size - 1) // batch_size
                    
                    # 打开快照文件，准备追加写入新进度
                    cache_file = open(cache_path, 'a', encoding='utf-8')
                    
                    for batch_idx in range(0, total, batch_size):
                        # 💥 核心拦截：每开始一个新批次前，先看看用户有没有点暂停
                        if getattr(app, 'cancel_build_flag', False):
                            safe_update_ui(batch_idx / total, "⚠️ 正在安全切断建库进程...")
                            break # 安全跳出循环
                            
                        batch = all_chunks[batch_idx:batch_idx+batch_size]
                        
                        db_data = []
                        need_api_texts = []
                        need_api_indices = []
                        batch_result_map = {} # 保持原汁原味的顺序
                        
                        # 扫描本批次，谁在快照里，谁需要大模型算？
                        for i_b, (ch_idx, text) in enumerate(batch):
                            abs_idx = batch_idx + i_b
                            if abs_idx in emb_cache:
                                batch_result_map[abs_idx] = (ch_idx, text, emb_cache[abs_idx])
                            else:
                                need_api_texts.append(text)
                                need_api_indices.append((ch_idx, abs_idx))
                                
                        if need_api_texts:
                            current_batch_num = batch_idx // batch_size + 1
                            percent = batch_idx / total
                            current_end = min(batch_idx + batch_size, total)
                            safe_update_ui(percent, f"🧠 推理中 (批次 {current_batch_num}/{total_batches} | 第 {batch_idx+1}-{current_end}/{total} 块)")

                            start_time = time.time()
                            new_embs = AIService.get_embeddings(app.ai_config, need_api_texts)
                            cost = time.time() - start_time

                            if not new_embs or len(new_embs) != len(need_api_texts):
                                cache_file.close()
                                raise Exception("大模型返回的向量数量缺失，已阻断写入以保护快照免受污染。")

                            for i, emb in enumerate(new_embs):
                                if not emb or not isinstance(emb, list) or len(emb) < 10:
                                    cache_file.close()
                                    raise Exception(f"检测到损坏的空向量 (本批次第{i+1}条)，已强行拦截写入！")
                                
                                ch_idx, abs_idx = need_api_indices[i]
                                text = need_api_texts[i]
                                batch_result_map[abs_idx] = (ch_idx, text, emb)
                                
                                # 💥 写入绝对安全的文本快照！防断电防强退！
                                cache_file.write(json.dumps({"id": abs_idx, "emb": emb}, ensure_ascii=False) + "\n")
                                cache_file.flush()
                                os.fsync(cache_file.fileno())

                            safe_update_ui(percent + (0.1 / total_batches), f"💾 写入纯净索引 (本批次耗时 {cost:.1f}s)...")
                        else:
                            # 全是快照命中，进度条飞速闪过
                            percent = batch_idx / total
                            safe_update_ui(percent, f"⚡ 快照闪速恢复中 (第 {batch_idx+1}-{batch_idx+len(batch)} 块)...")

                        # 按正确顺序组装 db_data 并秒插纯净数据库
                        for i_b in range(len(batch)):
                            abs_idx = batch_idx + i_b
                            db_data.append(batch_result_map[abs_idx])
                            
                        vdb.insert_chunks(db_data)

                    cache_file.close()

                    # 💥 新增：被暂停时的优雅退场逻辑
                    if getattr(app, 'cancel_build_flag', False):
                        app.is_building_index = False
                        time.sleep(0.5)
                        if hasattr(app, '_active_ui'):
                            try:
                                ui = app._active_ui
                                ui['status_text'].value = f"当前阅读：《{name}》\n⚠️ 索引暂停：已快照 {batch_idx} / {total} 块"
                                ui['status_card'].bgcolor = ft.Colors.with_opacity(0.15, ft.Colors.ORANGE)
                                ui['btn_build'].content.value = "▶️ 继续建库"
                                ui['btn_build'].on_click = on_build_click # 恢复原本的建库事件
                                ui['btn_build'].disabled = False
                                ui['btn_clear'].disabled = False
                                app.page.update()
                            except Exception: pass
                        app.show_snack_bar("⏸ 建库已暂停！进度已绝对安全地存入快照。")
                        return # 直接退出线程，不再执行下方的“完成”印章

                    # === 以下为未被暂停，正常建库完成的逻辑 ===
                    total_cost_sec = time.time() - total_start_time
                    mins, secs = divmod(total_cost_sec, 60)
                    cost_str = f"{int(mins)}分{secs:.1f}秒" if mins > 0 else f"{secs:.1f}秒"

                    # 💥 完工后修改钢印：状态改为"已完成"
                    vdb.set_meta("status", "completed")

                    # 5. 完成前夕：让监控器显示最后的信息
                    safe_update_ui(1.0, f"🎉 建库大功告成！总耗时: {cost_str}")
                    
                    # 给监控器 1 秒钟的时间，去把那句 100% 的话印在屏幕上！
                    import time
                    time.sleep(1)
                    
                    # 拔掉监控器的电源
                    app.is_building_index = False
                    
                    # 再给 0.5 秒，确保那个 async 循环死透了
                    time.sleep(0.5)

                    # 现在，工作线程独占了 UI 刷新权，可以尽情修改了！
                    if hasattr(app, '_active_ui'):
                        try:
                            ui = app._active_ui
                            ui['status_text'].value = f"当前阅读：《{name}》\n索引状态：已建库 ({total} 个切块)"
                            ui['status_card'].bgcolor = ft.Colors.with_opacity(0.15, ft.Colors.GREEN)
                            ui['btn_build'].content.value = "🔁 重新建库"
                            ui['btn_build'].disabled = False
                            ui['btn_clear'].disabled = False
                            
                            ui['prog_bar'].visible = False
                            ui['prog_text'].visible = False
                            ui['btn_build'].on_click = on_build_click # 💥 异常兜底：务必把点击事件切回来

                            # 不要再去单独 update 它们了！太容易出错！
                            # 直接召唤最高神，一键刷新整个页面！
                            app.page.update()
                            
                        except Exception: pass
                        
                    app.show_snack_bar(f"✅ 《{name}》全书建库已完成！总耗时: {cost_str}")
                    
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
            # 💥 判断如果是继续建库，修改一下文案
            is_resume = "继续建库" in btn_build.content.value
            title_text = "继续建库确认" if is_resume else "建库确认"
            body_text = "即将接着之前的进度继续建库。" if is_resume else "即将调用大模型 API 对全书进行向量化切块，可能需要消耗一定的时间和 Token 额度。是否开始？"
            
            confirm_dlg = ft.AlertDialog(
                title=ft.Text(title_text, weight=ft.FontWeight.BOLD),
                content=ft.Text(
                    f"{body_text}\n\n"
                    "(提示：开始后您可以关闭此弹窗继续阅读，系统会在后台静默完成并通知您。)\n\n"
                    "⚠️ 强烈建议：安卓系统内存管理极其严格，建库期间请尽量保持本软件在屏幕前台运行，切勿息屏或切换至其他应用（如微信），以防被系统强制杀后台导致建库中断！",
                
                ),
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
            cache_path = os.path.join(StorageManager.get_base_dir(), "vector_dbs", f"{book_hash}_cache.jsonl")
            
            # 💥 暴力粉碎数据库和快照文件
            import gc
            try:
                vdb = VectorDB(db_path)
                if hasattr(vdb, 'conn'): vdb.conn.close()
                vdb = None
                gc.collect()
            except Exception: pass
            
            try: os.remove(db_path)
            except Exception: pass
            try: os.remove(cache_path)
            except Exception: pass

            status_text.value = f"当前阅读：《{book_name}》\n索引状态：未建立"
            status_card.bgcolor = "surfaceVariant"
            btn_build.content.value = "🚀 向量建库"
            app.show_snack_bar("🧹 索引及快照缓存已彻底清除")
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
    
    top_k_slider = ft.Slider(min=1, max=10, divisions=9, value=top_k_val, label="{value} 段", on_change=on_top_k_change, width=INPUT_WIDTH)
    
    # 将 status_card 也加上宽度限制
    status_card.width = INPUT_WIDTH

    tab3_col = ft.Column([
        status_card, 
        prog_bar, 
        prog_text, 
        action_row, 
        ft.Divider(height=20, thickness=0.5),
        # 💥 合并升级后的“引擎与检索调优”卡片
        ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([ft.Icon(ft.Icons.SPEED, size=16), ft.Text("引擎与检索性能调优", weight="bold")], alignment=ft.MainAxisAlignment.CENTER),
                    
                    # 💥 插入并发控制滑块
                    ft.Divider(height=5, thickness=0.5, color="transparent"),
                    parallel_text,
                    parallel_slider,
                    ft.Text(
                        "💡 物理算力限制：受显存大小制约。核显/老显卡建议设为 1~4，中高端独显建议 8~16。\n若建库时频繁瞬间崩溃或报 500 错误，请务必调低此值！\n(注：此参数仅在电脑端生效。移动端底层引擎会自动接管最佳并发数。)", 
                        size=11, color="grey", text_align=ft.TextAlign.CENTER
                    ),

                    # 💥 插入 GPU 层数滑块
                    ft.Divider(height=5, thickness=0.5, color="transparent"),
                    gpu_layers_text,
                    gpu_layers_slider,
                    ft.Text(
                        "💡 GPU 卸载层数：决定将多少层神经网络交由显卡计算。若建库时发生闪退，请尝试降低此数值（如 10 或 14）。", 
                        size=11, color="grey", text_align=ft.TextAlign.CENTER
                    ),

                    ft.Divider(height=5, thickness=0.5, color="transparent"),
                    batch_size_text,
                    batch_size_slider,
                    ft.Text(
                        "💡 软件投喂频率：建议设为上方【并发通道数】的 2 到 4 倍。\n过小会导致显卡算力闲置浪费，过大可能导致进度条长时间卡顿或网络超时。", 
                        size=11, color="grey", text_align=ft.TextAlign.CENTER
                    ),

                    # 💥 插入物理切片滑块
                    ft.Divider(height=5, thickness=0.5, color="transparent"),
                    ubatch_text,
                    ubatch_slider,
                    ft.Text(
                        "💡 物理运算切片：决定底层硬件单次矩阵运算的真实吞吐量。数值越大算力利用率越高，但会引发激增的瞬时内存（运存/显存）消耗。\n若建库时遭遇应用直接闪退（手机端）或显存溢出报错（电脑端），请务必调低此档位！",  
                        size=11, color="grey", text_align=ft.TextAlign.CENTER
                    ),

                    ft.Divider(height=10, thickness=0.5),
                    top_k_text,
                    top_k_slider,
                    ft.Text("提示: 问答时提供的背景知识量。数值越大知识越丰富，但也越容易分散大模型注意力。", size=11, color="grey", text_align=ft.TextAlign.CENTER)
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
        # app.ai_config["local_model_path"] = local_model_dd.value if local_model_dd.value else ""
        # 💥 替换为从文本框取值
        app.ai_config["local_model_path"] = local_model_tf.value.strip()
        # 💥 保存硬件模式
        app.ai_config["hardware_mode"] = hardware_mode_dd.value
        
        # 💥 修复一：安全提取滑块值，防止空指针或类型异常
        app.ai_config["build_batch_size"] = int(round(float(batch_size_slider.value)))
        app.ai_config["n_parallel"] = int(round(float(parallel_slider.value)))
        app.ai_config["n_gpu_layers"] = int(round(float(gpu_layers_slider.value)))
        app.ai_config["top_k"] = int(round(float(top_k_slider.value)))
        
        # 💥 修复二：给脆弱的字典映射加上兜底逻辑，防止它中断整个保存进程
        app.ai_config["n_ubatch"] = ubatch_map[int(round(ubatch_slider.value))]
        
        # 写入硬盘
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