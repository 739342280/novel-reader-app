# ==============================================================================
# 文件：core/library_state.py
# 职责：图书资产大管家 (Library State Manager)
# 
# 详细功能介绍：
# 1. 书架生命周期：负责加载、保存、添加、重命名、移除用户的本地书籍。
# 2. 跨平台数据标识：为每本新导入的书籍颁发全球唯一标识符 (UUID) [book_id]，
#    彻底解耦文件绝对路径，保证知识库在多设备间流转不迷路。
# 3. 阅读进度记忆：实时记录并持久化用户在每本书中的阅读位置（章节索引、滚动偏移量）。
# 4. 老数据热升级：包含惰性迁移逻辑，能在老用户启动时无感将哈希命名的文件转换为 UUID 命名。
# 5. 本地模型获取：提供 UI 层唤起文件管理器选择本地 GGUF 模型，或一键从云端下载双端官方模型的逻辑。
#
# 架构定位：属于 App 底座的混入类 (Mixin)，其状态和方法最终会被注入到主 App 实例中。
# ==============================================================================
import flet as ft
import sys
import os
import shutil
import asyncio
import urllib.request
import threading
from data.storage import StorageManager

class LibraryStateMixin:
    """负责管理书架、阅读进度、章节缓存及本地文件交互状态"""
    
    def init_library_state(self):
        # --- 核心业务状态 ---
        self.bookshelf = []
        self.current_book_summaries = {}
        self.current_book_path = ""
        self.current_book_name = ""
        self.current_chapter_idx = 0
        self.current_scroll_offset = 0.0  
        self.current_max_scroll_extent = 0.0 
        self.last_reported_pct = -1.0 
        self.filtered_toc_mapping = []
        self.last_search_query = None  
        self.is_immersive = False 

    def _load_bookshelf(self):
        self.bookshelf = StorageManager.load_json("bookshelf.json", default=[])
        
        # 💥 终极无感热升级：哈希转 UUID，且不抛弃任何一个配套文件！
        need_save = False
        import uuid
        import hashlib
        
        db_dir = StorageManager.get_db_dir()
        toc_dir = StorageManager.get_toc_dir()
        sum_dir = StorageManager.get_summaries_dir()
        
        for book in self.bookshelf:
            if 'book_id' not in book:
                new_id = str(uuid.uuid4())
                book['book_id'] = new_id
                need_save = True
                
                book_path = book.get('path', '')
                if book_path:
                    old_hash = hashlib.md5(book_path.encode('utf-8')).hexdigest()
                    
                    # 组装老文件的名字
                    old_db = os.path.join(db_dir, f"{old_hash}.db")
                    old_cache = os.path.join(db_dir, f"{old_hash}_cache.jsonl")
                    old_toc = os.path.join(toc_dir, f"{old_hash}.json")
                    old_sum = os.path.join(sum_dir, f"{old_hash}.json")
                    
                    # 组装新文件的名字
                    new_db = os.path.join(db_dir, f"{new_id}.db")
                    new_cache = os.path.join(db_dir, f"{new_id}_cache.jsonl")
                    new_toc = os.path.join(toc_dir, f"{new_id}.json")
                    new_sum = os.path.join(sum_dir, f"{new_id}.json")
                    
                    # 三路大军，统一改名！
                    for old_p, new_p in [(old_db, new_db), (old_cache, new_cache), (old_toc, new_toc), (old_sum, new_sum)]:
                        if os.path.exists(old_p):
                            try:
                                os.rename(old_p, new_p)
                                print(f"[热升级] 成功迁移: {os.path.basename(new_p)}")
                            except Exception: pass

        if need_save:
            self._save_bookshelf()

    def _save_bookshelf(self):
        StorageManager.save_json("bookshelf.json", self.bookshelf)

    def _load_book_summaries(self):
        # 💥 呼叫管家时，传入 ID 而不是 path
        self.current_book_summaries = StorageManager.load_book_summaries(self.current_book_id)

    def _save_book_summaries(self):
        StorageManager.save_book_summaries(self.current_book_id, self.current_book_summaries)   

    def save_current_progress(self):
        if getattr(self, "current_book_path", "") == "":
            return
        if not hasattr(self, "engine") or not self.engine.chapters_info:
            return
            
        current_idx = getattr(self, "current_chapter_idx", 0)
        if current_idx < 0 or current_idx >= len(self.engine.chapters_info):
            return
            
        title = self.engine.chapters_info[current_idx]['title']
        volume = self.engine.chapters_info[current_idx].get('volume', '')
        offset = getattr(self, "current_scroll_offset", 0.0)
        
        for book in self.bookshelf:
            if book['path'] == self.current_book_path:
                if book.get('last_chapter_idx') == current_idx and book.get('last_scroll_offset') == offset:
                    break
                    
                book['last_chapter_idx'] = current_idx
                book['last_chapter_title'] = title
                book['last_volume_title'] = volume 
                book['last_scroll_offset'] = offset  
                self._save_bookshelf()
                break

    async def _pc_auto_save_task(self):
        if sys.platform == "win32":
            while True:
                await asyncio.sleep(5)
                try:
                    self.save_current_progress()
                except Exception:
                    pass

    def rename_book(self, path, new_name):
        for book in self.bookshelf:
            if book['path'] == path:
                book['name'] = new_name
                break
        self._save_bookshelf()
        self.route_change(None)

    def remove_from_bookshelf(self, path):
        self.bookshelf = [b for b in self.bookshelf if b['path'] != path]
        self._save_bookshelf()
        self.route_change(None)

    # ==========================================
    # 以下为本地文件交互与模型下载逻辑
    # ==========================================

    async def trigger_model_picker(self, ui_control):
        try:
            files = await ft.FilePicker().pick_files(
                dialog_title="请选择本地大模型",
                file_type=ft.FilePickerFileType.CUSTOM, 
                allowed_extensions=["onnx", "gguf", "bin", "pt", "safetensors"]
            )
            
            if files and len(files) > 0:
                absolute_path = files[0].path
                
                if not absolute_path:
                    self.show_snack_bar("获取文件路径失败，请尝试更换目录。")
                    return

                if ui_control:
                    ui_control.value = absolute_path
                    try: ui_control.update()
                    except Exception: pass
                    
                self.ai_config["local_model_path"] = absolute_path
                self._save_config_to_appdata()
                
                self.show_snack_bar(f"✅ 模型路径已设定: {absolute_path}")
                    
        except Exception as ex:
            self.show_snack_bar(f"唤起文件管理器失败: {str(ex)}")

    async def trigger_official_model_download(self, ui_control):
        """一键从云端拉取双端适配模型并静默装配 (带打断与清理机制)"""
        platform_str = str(self.page.platform).lower()
        is_mobile = "android" in platform_str or "ios" in platform_str

        # 💥 修复点 1：修正了 HuggingFace 的仓库作者名 (CompendiumLabs)
        if is_mobile:
            model_name = "bge-small-zh-v1.5-q8_0.gguf"
            model_size = "26 MB"
            model_desc = "极速省电版 (专为手机 ARM 处理器优化，防闪退)"
            model_url = "https://hf-mirror.com/CompendiumLabs/bge-small-zh-v1.5-gguf/resolve/main/bge-small-zh-v1.5-q8_0.gguf"
        else:
            model_name = "Qwen3-Embedding-0.6B-q4_k_m.gguf"
            model_size = "385 MB"
            model_desc = "高精度满血版 (专为电脑端优化，语义理解极强)"
            model_url = "https://hf-mirror.com/doggge/Qwen3-Embedding-0.6B-q4_k_m/resolve/main/Qwen3-Embedding-0.6B-q4_k_m.gguf"

        prog_bar = ft.ProgressBar(value=0, color="green", height=8, expand=True, visible=False)
        prog_text = ft.Text(f"准备下载... (大小: {model_size})", size=13, color="grey")
        
        # 💥 修复点 2：明确指定 text 参数，方便后续修改
        btn_start = ft.ElevatedButton(
            content=ft.Text("开始下载"), 
            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
        )
        btn_cancel = ft.TextButton(content=ft.Text("取消"))

        download_aborted = [False]

        def download_task():
            models_dir = os.path.join(StorageManager.get_base_dir(), "models")
            os.makedirs(models_dir, exist_ok=True)
            save_path = os.path.join(models_dir, model_name)

            try:
                prog_text.value = "正在连接高速下载节点..."
                try: prog_text.update()
                except Exception: pass

                req = urllib.request.Request(model_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=15) as response, open(save_path, 'wb') as out_file:
                    total_size = int(response.getheader('Content-Length', 0))
                    downloaded = 0
                    chunk_size = 1024 * 512 
                    
                    while True:
                        if download_aborted[0]:
                            break

                        chunk = response.read(chunk_size)
                        if not chunk: break
                        
                        out_file.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            pct = downloaded / total_size
                            prog_bar.value = pct
                            prog_text.value = f"正在下载: {downloaded/1024/1024:.1f} MB / {total_size/1024/1024:.1f} MB ({int(pct*100)}%)"
                            try:
                                prog_bar.update()
                                prog_text.update()
                            except Exception: pass

                if download_aborted[0]:
                    if os.path.exists(save_path):
                        try: 
                            os.remove(save_path) 
                        except Exception: 
                            pass # 忽略极端的系统占用错误
                    # ⚠️ 这里的弹窗被我们删掉了，因为前端按钮已经秒弹过了，防止重复打扰用户
                    return # 直接干掉线程

                # 正常完成的装配逻辑
                self.ai_config["local_model_path"] = save_path
                self._save_config_to_appdata()
                
                if ui_control:
                    ui_control.value = save_path
                    try: ui_control.update()
                    except Exception: pass

                self._universal_close(dl_dialog)
                self.show_snack_bar("🎉 官方推荐模型下载并装载成功！现在可以去建库了。")

            except Exception as e:
                if download_aborted[0]: return 
                
                prog_text.value = f"❌ 下载异常: {str(e)}"
                prog_text.color = "red"
                prog_bar.color = "red"
                try:
                    prog_text.update()
                    prog_bar.update()
                except Exception: pass
                
                btn_start.visible = True
                # 💥 终极修复：现在 btn_start.content 是一个真正的 ft.Text 对象了，有 value 属性了！
                btn_start.content.value = "重试"
                try: btn_start.update()
                except Exception: pass

        def on_start_click(e):
            btn_start.visible = False
            prog_bar.visible = True
            
            # 💥 修复点：每次重试前，用“卸妆水”洗掉红色，恢复默认状态！
            prog_bar.color = "green"
            prog_text.color = "grey"
            prog_bar.value = 0  # 顺手将进度条归零，视觉更顺滑

            try:
                btn_start.update()
                prog_bar.update()
                prog_text.update() # 别忘了把文字控件也更新一下
            except Exception: pass
            
            download_aborted[0] = False 
            threading.Thread(target=download_task, daemon=True).start()

        def on_cancel_click(e):
            download_aborted[0] = True # 触发后台线程阻断
            self._universal_close(dl_dialog)
            # 💥 立即给予用户视觉反馈，彻底消除等待焦虑！
            self.show_snack_bar("⚠️ 下载已取消，后台残留文件已自动清除。")

        btn_start.on_click = on_start_click
        btn_cancel.on_click = on_cancel_click

        dl_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row([ft.Icon(ft.Icons.CLOUD_DOWNLOAD, color="green"), ft.Text("一键获取官方模型", weight="bold")]),
            content=ft.Column([
                ft.Text(f"系统检测到您使用的是 {'移动端' if is_mobile else '电脑端'}，为您智能匹配："),
                ft.Container(
                    content=ft.Column([
                        ft.Text(f"📦 模型名称: {model_name}", weight="bold", size=13),
                        ft.Text(f"💡 特性: {model_desc}", size=12, color="grey"),
                    ]),
                    padding=10, bgcolor="surfaceVariant", border_radius=8
                ),
                ft.Container(height=10),
                ft.Row([prog_bar], width=300), 
                prog_text
            ], tight=True),
            actions=[btn_cancel, btn_start],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self._universal_open(dl_dialog)

    async def trigger_file_picker(self, e):
        # 拦截建库期间的新书导入
        if getattr(self, "is_building_index", False):
            self.show_snack_bar("⚠️ 引擎正在后台高强度建库，为防止数据错乱，请等待完成后再导入新书！")
            return
        
        try:
            files = await ft.FilePicker().pick_files(
                file_type=ft.FilePickerFileType.CUSTOM, 
                allowed_extensions=["txt", "nra"] # 💥 开放 .nra 权限
            )
            
            if files and len(files) > 0:
                picked_path = files[0].path
                original_name = files[0].name
                
                if not picked_path:
                    self.show_snack_bar("获取文件路径失败，请尝试换一个目录或系统文件管理器导入。")
                    return

                # 💥 新增：分流处理 .nra 智能知识库包
                if picked_path.lower().endswith('.nra'):
                    self.page.run_task(self._process_nra_import, picked_path)
                    return

                if picked_path.lower().endswith('.txt'):
                    books_dir = os.path.join(StorageManager.get_base_dir(), "books")
                    
                    if not os.path.exists(books_dir):
                        try: 
                            os.makedirs(books_dir, exist_ok=True)
                        except Exception as create_ex:
                            self.show_snack_bar(f"建立书籍存放目录失败，请检查应用存储权限: {str(create_ex)}")
                            return

                    persistent_path = os.path.join(books_dir, original_name)

                    try:
                        shutil.copy2(picked_path, persistent_path)
                        import stat
                        os.chmod(persistent_path, stat.S_IWRITE | stat.S_IREAD)
                        
                    except Exception as copy_ex:
                        self.show_snack_bar(f"文件转存失败: {str(copy_ex)}")
                        return

                    self.start_parsing(persistent_path)
                else:
                    self.show_snack_bar("仅支持 TXT 文本文件")
        except Exception as ex:
            self.show_snack_bar(f"唤起文件管理器失败: {str(ex)}")

    async def trigger_export_picker(self, src_path, default_name):
        try:
            if not os.path.exists(src_path):
                self.show_snack_bar("⚠️ 源文件已丢失，无法导出")
                return
            
            saved_path = await ft.FilePicker().save_file(
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["txt"], 
                file_name=f"{default_name}.txt"
            )
            
            if saved_path:
                try:
                    shutil.copy2(src_path, saved_path)
                    self.show_snack_bar("✅ 书籍导出成功")
                except Exception as ex:
                    self.show_snack_bar(f"导出失败: {str(ex)}")
        except Exception as ex:
            self.show_snack_bar(f"唤起导出面板失败: {str(ex)}")

    def _sync_progress(self, progress, msg):
        if hasattr(self, "progress_bar"):
            self.progress_bar.value = progress
        if hasattr(self, "status_text"):
            self.status_text.value = msg
        self.page.update()

    def refresh_bookshelf_ui(self):
        if not hasattr(self, "bookshelf_grid"): return
        self.bookshelf_grid.controls.clear()

        plus_side = ft.BorderSide(2, ft.Colors.BLUE)
        plus_border = ft.Border(top=plus_side, bottom=plus_side, left=plus_side, right=plus_side)
        
        plus_card = ft.Container(
            alignment=ft.Alignment(0, 0),
            content=ft.Container(
                width=160, height=220, 
                border=plus_border,
                bgcolor="surface",
                ink=True,
                on_click=self.trigger_file_picker, 
                content=ft.Column([
                    ft.Icon(ft.Icons.ADD, size=48, color=ft.Colors.BLUE),
                    ft.Text("导入本地TXT", size=13, color=ft.Colors.GREY)
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            )
        )
        self.bookshelf_grid.controls.append(plus_card)

        for book in self.bookshelf:
            card_side = ft.BorderSide(1, "outlineVariant")
            card_border = ft.Border(top=card_side, bottom=card_side, left=card_side, right=card_side)
            
            vol_title = book.get('last_volume_title', '')
            chap_title = book.get('last_chapter_title', '未读')
            
            info_col = ft.Column(spacing=2)
            info_col.controls.append(ft.Text(book['name'], weight=ft.FontWeight.BOLD, size=15, color=ft.Colors.BLUE, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS))
            if vol_title:
                info_col.controls.append(ft.Text(vol_title, size=11, color=ft.Colors.GREY_700, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))
            info_col.controls.append(ft.Text(chap_title, size=11, color=ft.Colors.GREY_500, max_lines=2 if not vol_title else 1, overflow=ft.TextOverflow.ELLIPSIS))

            card = ft.Container(
                alignment=ft.Alignment(0, 0),
                content=ft.Container(
                    ink=True,
                    on_click=lambda e, p=book['path']: self.check_and_load_book(p),
                    on_long_press=lambda e, p=book['path'], n=book['name']: self.show_book_options_dialog(p, n),
                    content=ft.Stack([
                        ft.Container(width=160, height=220, border_radius=0, bgcolor="surface", border=card_border), 
                        ft.Container(width=14, height=218, left=1, top=1, bgcolor=ft.Colors.BLUE_700),
                        ft.Container(width=2, height=218, left=15, top=1, bgcolor=ft.Colors.BLUE_900),
                        ft.Container(content=info_col, left=30, top=20, width=120)
                    ])
                )
            )
            self.bookshelf_grid.controls.append(card)
        self.page.update()
    
    @property
    def current_book_id(self):
        for book in self.bookshelf:
            if book.get('path') == getattr(self, 'current_book_path', ''):
                return book.get('book_id')
        return None
    
    # ==========================================
    # 📦 .nra 知识库 打包与导出引擎
    # ==========================================
    async def export_nra_package(self, book_path, current_name):
        book_id = None
        for b in self.bookshelf:
            if b['path'] == book_path:
                book_id = b.get('book_id')
                break
        
        if not book_id:
            self.show_snack_bar("⚠️ 无法获取书籍 ID，请先打开该书一次。")
            return
            
        db_path = os.path.join(StorageManager.get_db_dir(), f"{book_id}.db")
        if not os.path.exists(db_path):
            self.show_snack_bar("⚠️ 本书尚未建立向量库，无法打包 .nra，请使用普通 TXT 导出。")
            return
            
        saved_path = await ft.FilePicker().save_file(
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["nra"], 
            file_name=f"{current_name}_智能知识库.nra"
        )
        
        if not saved_path: return
        
        self.show_snack_bar("📦 正在打包知识库，请稍候...")
        
        def pack_task():
            import zipfile
            import json
            from datetime import datetime
            try:
                # 使用 ZIP_DEFLATED 进行无损高压，巨幅缩减体积
                with zipfile.ZipFile(saved_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # 1. 塞入纯文本
                    zipf.write(book_path, "book.txt")
                    # 2. 塞入底层数据库
                    zipf.write(db_path, "index.db")
                    
                    # 3. 塞入目录缓存（如果有）
                    toc_path = os.path.join(StorageManager.get_toc_dir(), f"{book_id}.json")
                    if os.path.exists(toc_path): zipf.write(toc_path, "toc.json")
                    
                    # 4. 塞入 AI 总结和聊天记录（如果有）
                    sum_path = os.path.join(StorageManager.get_summaries_dir(), f"{book_id}.json")
                    if os.path.exists(sum_path): zipf.write(sum_path, "summary.json")
                    
                    # 5. 生成基因图谱 (Manifest)
                    current_mode = self.ai_config.get("embed_mode", "")
                    current_model = self.ai_config.get("embed_model", "") if current_mode == "云端 API" else os.path.basename(self.ai_config.get("local_model_path", ""))
                    
                    manifest = {
                        "book_name": current_name,
                        "original_filename": os.path.basename(book_path),
                        "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "vector_info": {
                            "mode": current_mode,
                            "model_name": current_model
                        }
                    }
                    zipf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=4))
                    
                self.show_snack_bar(f"✅ 《{current_name}》知识库已成功打包为 .nra！")
            except Exception as e:
                self.show_snack_bar(f"❌ 打包失败: {e}")
                
        threading.Thread(target=pack_task, daemon=True).start()

    # ==========================================
    # 📥 .nra 知识库 解包与挂载引擎
    # ==========================================
    async def _process_nra_import(self, nra_path):
        self.show_snack_bar("📥 正在解压并挂载知识库，请稍候...")
        
        def import_task():
            import tempfile
            import zipfile
            import json
            import uuid
            
            temp_dir = tempfile.mkdtemp()
            try:
                # 1. 暴力拆包
                with zipfile.ZipFile(nra_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                    
                # 2. 验尸（读取基因图谱）
                manifest_path = os.path.join(temp_dir, "manifest.json")
                if not os.path.exists(manifest_path):
                    self.show_snack_bar("❌ 无效的 .nra 包：缺少 manifest.json 基因图谱")
                    return
                    
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                    
                book_name = manifest.get("book_name", "未知书籍")
                original_txt_name = manifest.get("original_filename", f"{book_name}.txt")
                v_model = manifest.get("vector_info", {}).get("model_name", "未知")
                
                # 🛡️ 3. 维度安全校验 (目前仅作强提醒，不强行阻断，给用户切回模型的机会)
                current_mode = self.ai_config.get("embed_mode", "")
                current_model = self.ai_config.get("embed_model", "") if current_mode == "云端 API" else os.path.basename(self.ai_config.get("local_model_path", ""))
                
                if current_model != v_model:
                    self.show_snack_bar(f"⚠️ 警告：当前模型 ({current_model}) 与知识库原模型 ({v_model}) 不符！请前往设置切换，否则追问将崩溃或乱码。")
                
                # 4. 办理新身份证落户！
                new_id = str(uuid.uuid4())
                books_dir = os.path.join(StorageManager.get_base_dir(), "books")
                os.makedirs(books_dir, exist_ok=True)
                
                # 本体防重名处理（如果电脑里已经有一本同名 txt）
                target_txt_path = os.path.join(books_dir, original_txt_name)
                counter = 1
                while os.path.exists(target_txt_path):
                    name, ext = os.path.splitext(original_txt_name)
                    target_txt_path = os.path.join(books_dir, f"{name}({counter}){ext}")
                    counter += 1
                    
                # 搬运本体
                shutil.copy2(os.path.join(temp_dir, "book.txt"), target_txt_path)
                
                # 5. 配套资产全面挂载新 UUID 护照！
                db_src = os.path.join(temp_dir, "index.db")
                if os.path.exists(db_src):
                    db_dir = StorageManager.get_db_dir()
                    shutil.copy2(db_src, os.path.join(db_dir, f"{new_id}.db"))
                    
                toc_src = os.path.join(temp_dir, "toc.json")
                if os.path.exists(toc_src):
                    shutil.copy2(toc_src, os.path.join(StorageManager.get_toc_dir(), f"{new_id}.json"))
                    
                sum_src = os.path.join(temp_dir, "summary.json")
                if os.path.exists(sum_src):
                    sum_dir = StorageManager.get_summaries_dir()
                    shutil.copy2(sum_src, os.path.join(sum_dir, f"{new_id}.json"))
                    
                # 6. 正式登记到书架
                self.bookshelf.insert(0, {
                    "name": book_name,
                    "path": target_txt_path,
                    "book_id": new_id,
                    "last_chapter_idx": 0,
                    "last_chapter_title": "未读",
                    "last_scroll_offset": 0.0
                })
                self._save_bookshelf()
                self.refresh_bookshelf_ui()
                self.show_snack_bar(f"🎉 知识库《{book_name}》导入并装配成功！")
                
            except Exception as e:
                self.show_snack_bar(f"❌ 导入 .nra 失败: {e}")
            finally:
                # 环保卫士：无论成功与否，无情抹除临时解压文件
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        threading.Thread(target=import_task, daemon=True).start()