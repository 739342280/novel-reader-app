# ==============================================================================
# 文件：core/tts_manager.py
# 职责：纯内存流媒体 TTS 引擎 (In-Memory Text-to-Speech Manager)
# 
# 详细功能介绍：
# 1. 生产者-消费者双核架构：引入 asyncio.Queue 实现音频流的无缝预加载，彻底消除段落间的网络延迟停顿。
# 2. 彻底抛弃前端 UI 框架限制，使用 Python 原生 Pygame 引擎进行底层混音播放。
# 3. 完美兼容滚动偏移量，实现听觉与视觉进度的平滑追踪。
# ==============================================================================
import flet as ft
import asyncio
import io
import os

# 隐藏 Pygame 启动时的欢迎信息
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

class TTSManagerMixin:
    """负责小说阅读器的听书流媒体控制"""

    async def toggle_tts(self, e=None):
        if getattr(self, "is_tts_playing", False):
            self.stop_tts()
        else:
            self.start_tts()

    def start_tts(self):
        if not self.engine.chapters_info:
            return
            
        self.is_tts_playing = True
        
        # 变身红色停止按钮
        if hasattr(self, "btn_tts"):
            self.btn_tts.content.value = "停止"
            self.btn_tts.icon = ft.Icons.STOP
            self.btn_tts.style.bgcolor = ft.Colors.RED_400
            try: self.btn_tts.update()
            except Exception: pass

        text = self.engine.get_chapter_text(self.current_chapter_idx)
        self.tts_chunks = [p.strip() for p in text.split('\n') if p.strip()]
        
        # 视觉进度与段落进度同步算法
        start_idx = 0
        max_extent = getattr(self, "current_max_scroll_extent", 0.0)
        current_offset = getattr(self, "current_scroll_offset", 0.0)
        
        if max_extent > 0 and current_offset > 0:
            progress_pct = max(0.0, min(1.0, current_offset / max_extent))
            start_idx = int(progress_pct * len(self.tts_chunks))
            if start_idx >= len(self.tts_chunks):
                start_idx = len(self.tts_chunks) - 1
                
        self.tts_current_chunk_idx = start_idx

        self.show_snack_bar("🎧 正在连接微软语音引擎...")

        # 💥 核心重构：创建异步预加载队列 (提前缓存 3 个段落的音频，足以抵消任何网络延迟)
        self.tts_queue = asyncio.Queue(maxsize=3)
        
        # 💥 架构升级：生成独一无二的“世代令牌”，防止旧线程死灰复燃
        self.tts_run_token = getattr(self, "tts_run_token", 0) + 1
        current_token = self.tts_run_token
        
        # 启动兵分两路的双引擎，并将当前令牌授予它们
        self.tts_producer_task = self.page.run_task(self._tts_producer, start_idx, current_token)
        self.tts_consumer_task = self.page.run_task(self._tts_consumer, current_token)
        
        # 💥 新增：引擎刚启动时，立刻高亮第一句！
        self.page.run_task(self._update_tts_highlight)

    def stop_tts(self):
        self.is_tts_playing = False
        
        # 💥 清空预加载队列，释放内存，防止幽灵缓存
        if hasattr(self, "tts_queue"):
            while not self.tts_queue.empty():
                try: self.tts_queue.get_nowait()
                except asyncio.QueueEmpty: break
            
            # 💥 核心修复：丢入一颗“毒药”信号，唤醒正在死等的消费者，让它体面地结束
            try: self.tts_queue.put_nowait((None, None))
            except Exception: pass

        # 瞬间物理掐断声音
        try:
            import pygame
            if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except Exception: pass
            
        # 变回青色听书按钮
        if hasattr(self, "btn_tts"):
            self.btn_tts.content.value = "听书"
            self.btn_tts.icon = ft.Icons.HEADSET
            self.btn_tts.style.bgcolor = ft.Colors.TEAL_500
            try: self.btn_tts.update()
            except Exception: pass
            
        # 💥 新增：停止听书时，全场擦除高亮
        self.page.run_task(self._update_tts_highlight)

    # ==============================================================
    # 💥 引擎1：生产者 (只管疯狂向微软索要下一段音频，放入托盘)
    # ==============================================================
    async def _tts_producer(self, start_idx, token): # 💥 接收令牌
        try:
            import edge_tts
            voice = self.ai_config.get("tts_voice", "zh-CN-XiaoxiaoNeural")
            rate = self.ai_config.get("tts_rate", "+0%")

            for idx in range(start_idx, len(self.tts_chunks)):
                # 💥 核心防线 1：如果令牌不符，说明自己是前朝遗老，立刻自尽！
                if not getattr(self, "is_tts_playing", False) or getattr(self, "tts_run_token", 0) != token: 
                    break
                
                text_to_read = self.tts_chunks[idx]
                audio_data = b""
                
                communicate = edge_tts.Communicate(text_to_read, voice, rate=rate)
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                
                # 💥 核心防线 2：网络请求归来后（可能过了好几秒），再次核对令牌！绝对不许把旧声音塞进新队列！
                if getattr(self, "is_tts_playing", False) and getattr(self, "tts_run_token", 0) == token and audio_data:
                    await self.tts_queue.put((idx, audio_data))

            if getattr(self, "is_tts_playing", False) and getattr(self, "tts_run_token", 0) == token:
                await self.tts_queue.put((None, None))
                
        except Exception as e:
            print(f"TTS 预加载网络异常: {e}")

    # ==============================================================
    # 💥 引擎2：消费者 (只管从托盘取现成的音频播放，负责翻页与UI联动)
    # ==============================================================
    async def _tts_consumer(self, token): # 💥 接收令牌
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()

            while getattr(self, "is_tts_playing", False):
                # 💥 消费者防线：每次取货前看一眼令牌
                if getattr(self, "tts_run_token", 0) != token:
                    break

                item = await self.tts_queue.get()
                chunk_idx, audio_data = item
                
                if chunk_idx is None:
                    # 💥 毒药判定：如果不是自己的令牌，或者是被强制掐断的，安静退出
                    if not getattr(self, "is_tts_playing", False) or getattr(self, "tts_run_token", 0) != token:
                        break
                        
                    if self.current_chapter_idx < len(self.engine.chapters_info) - 1:
                        self.show_snack_bar("自动为您播放下一章...")
                        self.page.run_task(self.close_reader_overlays)
                        self.load_next() # 翻页
                        await asyncio.sleep(1) # 给渲染器一点时间
                        self.start_tts() # 重新接力播放
                    else:
                        self.stop_tts()
                        self.show_snack_bar("🎧 全书已播放完毕")
                    break

                self.tts_current_chunk_idx = chunk_idx
                
                # 💥 新增：拿到新的一段音频，立刻把高亮焦点移过来！
                self.page.run_task(self._update_tts_highlight)

                # ==========================================
                # 💥 架构升级：抛弃脆弱的像素百分比计算，启用精准锚点追踪！
                # ==========================================
                if hasattr(self, "text_scroll_col"):
                    try:
                        render_id = getattr(self, "current_render_id", 0)
                        target_key = f"chunk_{render_id}_{self.tts_current_chunk_idx}"
                        
                        # 💥 终极修复：把 key= 改为 Flet 官方正确的 API 参数名 scroll_key=
                        scroll_result = self.text_scroll_col.scroll_to(scroll_key=target_key, duration=500)
                        
                        if asyncio.iscoroutine(scroll_result):
                            await scroll_result
                            
                    except Exception as e:
                        print(f"TTS 滚动定位失败: {e}")

                # 播放内存中的 MP3 字节流
                audio_io = io.BytesIO(audio_data)
                pygame.mixer.music.load(audio_io)
                pygame.mixer.music.play()

                # 死死盯住播放器，等到当前这段【真正发声结束】才进入下一个循环
                while pygame.mixer.music.get_busy() and getattr(self, "is_tts_playing", False):
                    await asyncio.sleep(0.05)
                    
        except Exception as e:
            print(f"TTS 播放异常: {e}")
            self.show_snack_bar("❌ 语音播放异常，已停止。")
            self.stop_tts()

    # ==============================================================
    # 💥 引擎3：UI 伴读渲染器 (动态高亮当前段落)
    # ==============================================================
    async def _update_tts_highlight(self): # 💥 核心修复：添加 async，使其成为标准的协程函数
        # 如果文本控件还没渲染出来，直接跳过防报错
        if not hasattr(self, "reader_text_controls"): return
        
        # 绝妙的自适应高亮色：取当前主题字体颜色的 15% 透明度
        highlight_color = ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE)
        
        # 1. 无情擦除全场现有的高亮（包括标题和所有正文段落）
        if hasattr(self, "chapter_title_control") and self.chapter_title_control:
            if getattr(self.chapter_title_control.content, "bgcolor", None) is not None:
                self.chapter_title_control.content.bgcolor = None
                try: self.chapter_title_control.content.update()
                except Exception: pass
                
        for txt_ctrl in self.reader_text_controls:
            if getattr(txt_ctrl, "bgcolor", None) is not None:
                txt_ctrl.bgcolor = None
                try: txt_ctrl.update()
                except Exception: pass

        # 2. 如果是因为点【停止】进来的，擦除完就可以收工了
        if not getattr(self, "is_tts_playing", False):
            return

        # 3. 锁定目标，为当前正在读的段落打上专属高亮！
        idx = self.tts_current_chunk_idx
        # 巧妙应对：切片数组的第 0 项是标题，后面的才是正文
        if idx == 0 and hasattr(self, "chapter_title_control") and self.chapter_title_control:
            self.chapter_title_control.content.bgcolor = highlight_color
            try: self.chapter_title_control.content.update()
            except Exception: pass
        elif idx > 0 and (idx - 1) < len(self.reader_text_controls):
            target_ctrl = self.reader_text_controls[idx - 1]
            target_ctrl.bgcolor = highlight_color
            try: target_ctrl.update()
            except Exception: pass 