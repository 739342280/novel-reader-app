# ==============================================================================
# 文件：core/tts_manager.py
# 职责：纯内存流媒体 TTS 引擎 (In-Memory Text-to-Speech Manager)
# 
# 详细功能介绍：
# 1. 负责调度 edge-tts 将文本转换为语音字节流。
# 2. 彻底抛弃前端 UI 框架限制，使用 Python 原生 Pygame 引擎进行底层混音播放。
# 3. 基于内存流 (BytesIO) 实现零延迟、零硬盘损耗的丝滑播放。
# ==============================================================================
import flet as ft
import asyncio
import io
import os

# 隐藏 Pygame 启动时的欢迎信息，保持控制台洁癖
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
        
        # 巧妙切片：按段落切分，过滤空行，防止微软接口超时
        self.tts_chunks = [p.strip() for p in text.split('\n') if p.strip()]
        
        # 💥 核心修复：根据当前屏幕滚动百分比，计算应该从第几段开始读
        start_idx = 0
        max_extent = getattr(self, "current_max_scroll_extent", 0.0)
        current_offset = getattr(self, "current_scroll_offset", 0.0)
        
        if max_extent > 0 and current_offset > 0:
            # 计算当前滑动占全文的百分比
            progress_pct = current_offset / max_extent
            # 限制在 0.0 到 1.0 之间防越界
            progress_pct = max(0.0, min(1.0, progress_pct)) 
            # 百分比 * 总段落数 = 当前应该播的段落索引
            start_idx = int(progress_pct * len(self.tts_chunks))
            
            # 防御极端情况
            if start_idx >= len(self.tts_chunks):
                start_idx = len(self.tts_chunks) - 1
                
        self.tts_current_chunk_idx = start_idx

        self.show_snack_bar("🎧 正在连接微软语音引擎...")
        self.page.run_task(self._play_current_tts_chunk)

    def stop_tts(self):
        self.is_tts_playing = False
        
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

    async def _play_current_tts_chunk(self):
        # 防御拦截：如果用户手速极快按了停止
        if not getattr(self, "is_tts_playing", False): return
        
        # 本章播完判定
        if self.tts_current_chunk_idx >= len(self.tts_chunks):
            if self.current_chapter_idx < len(self.engine.chapters_info) - 1:
                self.show_snack_bar("自动为您播放下一章...")
                self.page.run_task(self.close_reader_overlays)
                self.load_next() # 翻页！
                await asyncio.sleep(1) # 等待页面渲染和数据落盘
                self.start_tts() # 重新触发连播
            else:
                self.stop_tts()
                self.show_snack_bar("🎧 全书已播放完毕")
            return

        text_to_read = self.tts_chunks[self.tts_current_chunk_idx]
        
        # 贴心细节：文字自动下卷，跟着声音走
        try:
            if hasattr(self, "text_scroll_col") and getattr(self, "current_max_scroll_extent", 0.0) > 0:
                progress = self.tts_current_chunk_idx / max(1, len(self.tts_chunks))
                await self.text_scroll_col.scroll_to(offset=self.current_max_scroll_extent * progress, duration=500)
        except Exception: pass

        try:
            import edge_tts
            import pygame
            
            # 确保音频混音器已初始化
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            voice = self.ai_config.get("tts_voice", "zh-CN-XiaoxiaoNeural")
            rate = self.ai_config.get("tts_rate", "+0%")
            
            # 核心：获取微软数据流
            communicate = edge_tts.Communicate(text_to_read, voice, rate=rate)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            
            if not getattr(self, "is_tts_playing", False): return 
            
            # 💥 Python 底层混音黑魔法：内存直读播放！
            audio_io = io.BytesIO(audio_data)
            pygame.mixer.music.load(audio_io)
            pygame.mixer.music.play()
            
            # 异步监听：只要还在播，且用户没点停止，就挂起等待
            while pygame.mixer.music.get_busy() and getattr(self, "is_tts_playing", False):
                await asyncio.sleep(0.1)

            # 如果顺利跳出循环且依然是播放状态，说明本段自然播完了，触发下一段
            if getattr(self, "is_tts_playing", False):
                self.tts_current_chunk_idx += 1
                self.page.run_task(self._play_current_tts_chunk)
            
        except ImportError:
            self.show_snack_bar(f"❌ 缺少核心依赖，请执行 pip install edge-tts pygame")
            self.stop_tts()
        except Exception as e:
            print(f"TTS Error: {e}")
            self.show_snack_bar(f"❌ 语音网络异常或超时，已停止。")
            self.stop_tts()