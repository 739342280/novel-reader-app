# ==============================================================================
# 文件：core/reader_action.py
# 职责：阅读器核心行为控制器 (Reader Action Controller)
# 
# 详细功能介绍：
# 1. 新书解析与装载：响应用户点击，调度底层 Engine 执行耗时的正则切章任务（并伴随 UI 进度条），
#    如果是新书则呼叫 library_state 颁发 UUID，解析完成后转存目录缓存。
# 2. 章节渲染与翻页：根据索引 (idx) 提取纯文本，应用用户的排版设置（字号、行高、间距、字体），
#    生成 Flet 的 Text 控件流并挂载到阅读页，处理“上一章/下一章”越界逻辑。
# 3. 丝滑滚动定位：监听用户的滑动事件 (on_scroll) 并计算百分比；在跨章加载时，
#    精确还原上一次退出的滚动像素偏移量 (offset)，实现无缝衔接。
# 4. 目录检索与联动：实现左侧目录面板的搜索过滤功能，并控制目录项随当前章节高亮及自动滚动。
#
# 架构定位：连接底层文本引擎 (Engine) 与前端阅读界面 (UI) 的强力胶水，混入到主 App 中运行。
# ==============================================================================
import flet as ft
import os
import sys
import threading
import asyncio
from data.storage import StorageManager

class ReaderActionMixin:
    """负责阅读核心引擎、翻页控制、目录检索与滚动定位逻辑"""

    def check_and_load_book(self, path):
        # 💥 极点防御 1（优雅升级版）：拦截建库期间的书籍切换
        if getattr(self, "is_building_index", False):
            # 如果用户点击的正是当前正在建库的书
            if path == getattr(self, "current_book_path", ""):
                # 连重新加载都免了，直接秒切回阅读页，体验极度丝滑！
                self.page.run_task(self.page.push_route, "/reader")
                return
            else:
                # 如果点的是别的书，依然死死焊住大门
                self.show_snack_bar("⚠️ 引擎正在后台建库，为防止数据错乱，暂不支持打开其他书籍！")
                return
            
        if not os.path.exists(path):
            self.show_snack_bar("文件丢失，可能已被移动或删除，将自动移出书架。")
            self.remove_from_bookshelf(path)
            return
        self.start_parsing(path)

    def start_parsing(self, path):
        self.current_book_path = path
        
        custom_name = os.path.splitext(os.path.basename(path))[0]
        book_exists = False
        for b in self.bookshelf:
            if b['path'] == path:
                custom_name = b.get('name', custom_name)
                book_exists = True
                break
        self.current_book_name = custom_name
        
        # 💥 核心防御：如果是新书，立刻发放 UUID 钢印，确保存储管家有 ID 可用！
        if not book_exists:
            import uuid
            self.bookshelf.insert(0, {
                "name": self.current_book_name,
                "path": self.current_book_path,
                "book_id": str(uuid.uuid4()), 
                "last_chapter_idx": 0,
                "last_chapter_title": "未读",
                "last_scroll_offset": 0.0
            })
            self._save_bookshelf()
        
        # 💥 呼叫管家时，传入真正的 book_id 而不再是 path！
        toc_cache = StorageManager.load_book_toc(self.current_book_id)
        if toc_cache:
            self.engine.load_with_cache(path, toc_cache)
            self.on_parse_success()
            return

        if hasattr(self, "status_text"): self.status_text.visible = True
        if hasattr(self, "progress_bar"): 
            self.progress_bar.visible = True
            self.progress_bar.value = 0
        self.page.update()
        
        def task():
            try:
                chaps = self.engine.load_and_analyze(path, self._sync_progress)
                # 💥 呼叫管家存文件时，传入真正的 book_id
                StorageManager.save_book_toc(self.current_book_id, chaps)
                self.on_parse_success()
            except Exception as e:
                self.show_snack_bar(f"解析失败: {str(e)}")
                if hasattr(self, "status_text"): self.status_text.visible = False
                if hasattr(self, "progress_bar"): self.progress_bar.visible = False
                self.page.update()
                
        threading.Thread(target=task, daemon=True).start()

    def on_parse_success(self):
        if hasattr(self, "status_text"): self.status_text.visible = False
        if hasattr(self, "progress_bar"): self.progress_bar.visible = False
        
        target_idx = -1
        target_offset = 0.0
        book_exists = False
        for book in self.bookshelf:
            if book['path'] == self.current_book_path:
                book_exists = True
                target_idx = book.get('last_chapter_idx', -1)
                target_offset = book.get('last_scroll_offset', 0.0)
                break
                   
        self._load_book_summaries()

        if target_idx != -1 and target_idx < len(self.engine.chapters_info):
            self.current_chapter_idx = target_idx
        else:
            valid_idx = self._find_valid_chapter(0, 1)
            self.current_chapter_idx = valid_idx if valid_idx != -1 else 0
            
        self.current_scroll_offset = target_offset

        self.page.run_task(self.page.push_route, "/reader")

    def load_chapter(self, idx, target_offset=0.0):
        if not self.engine.chapters_info: return
        self.current_chapter_idx = idx
        
        ch_info = self.engine.chapters_info[idx]
        title = ch_info['title']
        volume = ch_info.get('volume', '')
        text = self.engine.get_chapter_text(idx)

        self.current_scroll_offset = target_offset
        self.current_max_scroll_extent = 0.0 

        if hasattr(self, "top_bar_book_name"):
            display_vol = volume if volume and volume != title else ""
            self.top_bar_book_name.value = f"{self.current_book_name} | {display_vol}" if display_vol else self.current_book_name
        if hasattr(self, "top_bar_chapter_name"):
            self.top_bar_chapter_name.value = title
        if hasattr(self, "info_chapter_name"):
            self.info_chapter_name.value = title
            
        if hasattr(self, "info_progress"):
            total_length = len(self.engine.full_text_content)
            if total_length > 0:
                base_pct = (ch_info['start'] / total_length) * 100
            else:
                base_pct = 0.0
            self.last_reported_pct = base_pct
            self.info_progress.value = f"{base_pct:.1f}%"
        
        current_text_color = "#B0B0B0" if self._get_is_dark_mode() else self.reader_text_color
        
        paragraphs = [p.rstrip() for p in text.replace('\r', '').split('\n') if p.strip()]
        
        self.reader_text_controls = []
        self.chapter_title_control = None

        # ==========================================
        # 💥 强力修复 1：生成唯一的章节渲染 ID，彻底杜绝 Flet 翻页时的幽灵 Key 冲突！
        # ==========================================
        self.current_render_id = getattr(self, "current_render_id", 0) + 1
        render_id = self.current_render_id
        
        # 💥 1. 标题部分：将 render_id 缝合进 key 中
        if paragraphs:
            title_text = paragraphs.pop(0)
            self.chapter_title_control = ft.Container(
                key=ft.ScrollKey(f"chunk_{render_id}_0"),  # 👈 【核心修复】必须用 ft.ScrollKey 包裹！
                content=ft.Text(
                    title_text,
                    size=self.font_size + 2,  
                    weight=ft.FontWeight.BOLD, 
                    style=ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing),
                    font_family=self.font_family,
                    color=current_text_color,
                    text_align=ft.TextAlign.LEFT 
                ),
                padding=ft.Padding(left=0, top=0, right=16, bottom=15) 
            )

            # 💥 2. 正文部分：同样缝合 render_id
            for i, p in enumerate(paragraphs):
                self.reader_text_controls.append(
                    ft.Container(
                        key=ft.ScrollKey(f"chunk_{render_id}_{i + 1}"), # 👈 【核心修复】必须用 ft.ScrollKey 包裹！
                        content=ft.Text(
                            p, 
                            size=self.font_size, 
                            style=ft.TextStyle(height=self.line_height, letter_spacing=self.letter_spacing),
                            font_family=self.font_family, 
                            color=current_text_color   
                        ),
                        padding=ft.Padding(left=0, top=0, right=16, bottom=0) 
                    )
                )

        prev_valid = self._find_valid_chapter(idx - 1, -1) if idx > 0 else -1
        next_valid = self._find_valid_chapter(idx + 1, 1) if idx < len(self.engine.chapters_info)-1 else -1

        # 💥 3. 底部按钮：也补齐 right=16
        if next_valid != -1:
            self.inline_next_btn = ft.Container(
                content=ft.TextButton(
                    content=ft.Text("下一章"),
                    icon=ft.Icons.ARROW_FORWARD,
                    on_click=self.load_next,
                    style=ft.ButtonStyle(color=current_text_color)
                ),
                alignment=ft.Alignment(0, 0),
                padding=ft.Padding(top=30, bottom=50, left=0, right=16) # 👈 修改右边距
            )
        else:
            self.inline_next_btn = ft.Container(
                content=ft.Text("— 已经是最后一章了 —", color=current_text_color, size=13),
                alignment=ft.Alignment(0, 0),
                padding=ft.Padding(top=30, bottom=50, left=0, right=16) # 👈 修改右边距
            )

        # 💥 4. 拍扁层级：废弃 inner_text_col，将控件直接组装
        controls_to_add = []
        if self.chapter_title_control:
            controls_to_add.append(self.chapter_title_control)
        controls_to_add.extend(self.reader_text_controls)
        controls_to_add.append(self.inline_next_btn)
        
        # 让 scroll_col 没有任何外层限制，霸占全部宽度，让滚动条死死贴边！
        self.text_scroll_col = ft.Column(
            controls=controls_to_add,
            spacing=self.paragraph_spacing,
            expand=True, 
            scroll=ft.ScrollMode.AUTO,
            on_scroll=self._on_text_scroll, 
            key="text_scroll_col",
            opacity=0,                                                            
            animate_opacity=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT)    
        )
        
        if hasattr(self, "text_panel"):
            self.text_panel.content = self.text_scroll_col # 直接赋值，绝不套 Container！

        if hasattr(self, "btn_prev"): self.btn_prev.disabled = prev_valid == -1
        if hasattr(self, "btn_next"): self.btn_next.disabled = next_valid == -1

        self.save_current_progress() 

        if not hasattr(self, "toc_listview") or not self.toc_listview.controls:
            self.filter_toc(None) 
        else:
            self._update_toc_highlight()
            
        self.page.update()
        
        self.page.run_task(self._delayed_scroll_to_chapter, idx)
        self.page.run_task(self._finalize_chapter_load, self.text_scroll_col, target_offset)

    def load_prev(self, e=None):
        if self.current_chapter_idx > 0:
            valid_idx = self._find_valid_chapter(self.current_chapter_idx - 1, -1)
            if valid_idx != -1: self.load_chapter(valid_idx) 

    def load_next(self, e=None):
        if self.current_chapter_idx < len(self.engine.chapters_info) - 1:
            valid_idx = self._find_valid_chapter(self.current_chapter_idx + 1, 1)
            if valid_idx != -1: self.load_chapter(valid_idx) 

    def _on_text_scroll(self, e: ft.OnScrollEvent):
        self.current_scroll_offset = e.pixels
        self.current_max_scroll_extent = getattr(e, "max_scroll_extent", 0.0) 
        
        if not self.engine.chapters_info: return
        
        max_ext = self.current_max_scroll_extent
        chap_pct = 0.0
        if max_ext and max_ext > 0:
            p = max(0.0, min(float(e.pixels), float(max_ext)))
            chap_pct = p / max_ext
            
        total_length = len(self.engine.full_text_content)
        if total_length > 0:
            ch_info = self.engine.chapters_info[self.current_chapter_idx]
            chap_len = ch_info['end'] - ch_info['start']
            current_total_pct = ((ch_info['start'] + chap_len * chap_pct) / total_length) * 100
            
            if abs(current_total_pct - getattr(self, "last_reported_pct", -1.0)) >= 0.1:
                self.last_reported_pct = current_total_pct
                if hasattr(self, "info_progress"):
                    self.info_progress.value = f"{current_total_pct:.1f}%"
                    try: self.info_progress.update()
                    except Exception: pass

    def filter_toc(self, e=None):
        if e is not None and getattr(e, "name", "") != "change":
            return

        query = getattr(self, "search_tf", None).value.lower() if getattr(self, "search_tf", None) and self.search_tf.value else ""
        
        if getattr(self, "last_search_query", None) == query:
            return 
        self.last_search_query = query
        
        new_controls = []
        new_mapping = []
        for i, ch in enumerate(self.engine.chapters_info):
            if query in ch['title'].lower():
                def make_click(idx):
                    def click_handler(e):
                        self.page.run_task(self.close_reader_overlays)
                        self.load_chapter(idx)
                    return click_handler
                
                color = ft.Colors.BLUE if i == self.current_chapter_idx else None
                item = ft.Container(
                    key=f"toc_{i}", 
                    content=ft.Text(ch['title'], color=color),
                    padding=10, border_radius=5,
                    height=42, 
                    ink=True, on_click=make_click(i)
                )
                new_controls.append(item)
                new_mapping.append(i)
        
        if hasattr(self, "toc_listview"):
            self.toc_listview.controls.clear()
            self.toc_listview.controls.extend(new_controls)
            self.filtered_toc_mapping = new_mapping
            self.page.update()

    def _update_toc_highlight(self):
        if not hasattr(self, "toc_listview"): return
        for i, idx in enumerate(self.filtered_toc_mapping):
            if i < len(self.toc_listview.controls):
                try:
                    text_ctrl = self.toc_listview.controls[i].content
                    expected_color = ft.Colors.BLUE if idx == self.current_chapter_idx else None
                    if text_ctrl.color != expected_color:
                        text_ctrl.color = expected_color
                        try: text_ctrl.update()
                        except Exception: pass
                except Exception:
                    pass

    async def _delayed_scroll_to_chapter(self, idx, delay=0.1):
        if not hasattr(self, "toc_listview"): return
        
        # 💥 关键防御：如果目录面板当前根本不可见，绝对不要去触发 scroll_to，否则必卡 4 秒超时！
        if not getattr(self, "toc_panel", None) or not self.toc_panel.visible: 
            return
            
        display_idx = -1
        try:
            display_idx = self.filtered_toc_mapping.index(idx)
        except ValueError:
            pass
            
        if display_idx != -1:
            await asyncio.sleep(delay) 
            try:
                calculated_offset = display_idx * 44
                await self.toc_listview.scroll_to(offset=calculated_offset, duration=300)
            except Exception:
                pass

    async def _finalize_chapter_load(self, col, offset):
        await asyncio.sleep(0.1) 
        try:
            # 只有当路由真的是阅读页时，才执行滚动
            if offset > 0 and getattr(self.page, "route", "/") == "/reader":
                try:
                    await col.scroll_to(offset=offset, duration=0)
                    await asyncio.sleep(0.05) 
                except Exception:
                    pass # 忽略所有滚动引起的超时错误
        finally:
            # 💥 终极保障：无论滚动是否成功、是否被中断，这里使用 finally 绝对保证透明度被设为 1，让文字显现！
            col.opacity = 1
            try:
                col.update()
            except Exception:
                pass

    def go_back_home(self, e):
        if self.page.route == "/reader":
            self.save_current_progress()
            if getattr(self, "is_immersive", False):
                self.toggle_immersive(None)
                
        self.page.run_task(self.page.push_route, "/")
    
    async def copy_current(self, e):
        if not self.engine.chapters_info: return
        text = self.engine.get_chapter_text(self.current_chapter_idx)
        self._execute_copy(text)
        self.show_snack_bar("✅ 本章内容已复制到剪贴板")
        await self.close_reader_overlays()

    def _find_valid_chapter(self, start_idx, step=1):
        idx = start_idx
        while 0 <= idx < len(self.engine.chapters_info):
            ch_info = self.engine.chapters_info[idx]
            text = self.engine.get_chapter_text(idx).strip()
            title = ch_info['title'].strip()
            content_only = text.replace(title, "", 1).strip()
            if len(content_only) > 15:
                return idx
            idx += step
        return -1
    
    