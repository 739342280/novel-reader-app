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
import flet_audio as fta  # 💥 新增：导入最新的 flet_audio 独立包
import asyncio
import io
import os
import base64

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

        # ==========================================
        # 💥 新增：懒加载初始化 Flet 原生跨平台音频播放器
        # ==========================================
        if not hasattr(self, "tts_audio_player"):
            self.tts_audio_completed_event = asyncio.Event()
            # 标志位：是否正在等待播放完成
            self._waiting_for_stop = False

            def _on_audio_state(e):
                state_str = str(e.state).lower() if e.state else ""
                print(f"📢 音频状态变化: {e.state} (raw: {state_str})")
                # 只有在消费者主动等待时，才去设置事件
                if getattr(self, "_waiting_for_stop", False):
                    if "stopped" in state_str or "completed" in state_str:
                        print("   -> 设置播放完成事件")
                        self.tts_audio_completed_event.set()
                        self._waiting_for_stop = False

            self.tts_audio_player = fta.Audio(
                autoplay=True,
                on_state_change=_on_audio_state,
                volume=1.0
            )
            # ✅ 保存回调引用，供消费者重建播放器时使用
            self._on_audio_state_callback = _on_audio_state

            self.page.services.append(self.tts_audio_player)
            self.page.update()

        # 创建异步预加载队列 (提前缓存 3 个段落的音频，足以抵消任何网络延迟)
        self.tts_queue = asyncio.Queue(maxsize=3)
        
        # 生成独一无二的“世代令牌”，防止旧线程死灰复燃
        self.tts_run_token = getattr(self, "tts_run_token", 0) + 1
        current_token = self.tts_run_token
        
        # 启动兵分两路的双引擎，并将当前令牌授予它们
        self.tts_producer_task = self.page.run_task(self._tts_producer, start_idx, current_token)
        self.tts_consumer_task = self.page.run_task(self._tts_consumer, current_token)
        
        # 引擎刚启动时，立刻高亮第一句！
        self.page.run_task(self._update_tts_highlight)

    def stop_tts(self):
        self.is_tts_playing = False
        
        # 清空预加载队列，释放内存，防止幽灵缓存
        if hasattr(self, "tts_queue"):
            while not self.tts_queue.empty():
                try: self.tts_queue.get_nowait()
                except asyncio.QueueEmpty: break
            
            # 丢入一颗“毒药”信号，唤醒正在死等的消费者，让它体面地结束
            try: self.tts_queue.put_nowait((None, None))
            except Exception: pass

        # 瞬间物理掐断声音
        if hasattr(self, "tts_audio_player"):
            # 清空音频源
            self.tts_audio_player.src = None
            try: self.tts_audio_player.update()
            except Exception: pass
            
            # 💥 使用后台任务安全触发异步的 pause，防止出现 RuntimeWarning
            try: self.page.run_task(self.tts_audio_player.pause)
            except Exception: pass
            
            # 设置事件，防止消费者协程的 await wait() 永久阻塞
            
        # 变回青色听书按钮
        if hasattr(self, "btn_tts"):
            self.btn_tts.content.value = "听书"
            self.btn_tts.icon = ft.Icons.HEADSET
            self.btn_tts.style.bgcolor = ft.Colors.TEAL_500
            try: self.btn_tts.update()
            except Exception: pass
            
        # 停止听书时，全场擦除高亮
        self.page.run_task(self._update_tts_highlight)

    # ==============================================================
    # 引擎1：生产者 (只管疯狂向微软索要下一段音频，放入托盘)
    # ==============================================================
    async def _tts_producer(self, start_idx, token): # 接收令牌
        try:
            import edge_tts
            voice = self.ai_config.get("tts_voice", "zh-CN-XiaoxiaoNeural")
            rate = self.ai_config.get("tts_rate", "+0%")

            for idx in range(start_idx, len(self.tts_chunks)):
                # 核心防线 1：如果令牌不符，说明自己是前朝遗老，立刻自尽！
                if not getattr(self, "is_tts_playing", False) or getattr(self, "tts_run_token", 0) != token: 
                    break
                
                text_to_read = self.tts_chunks[idx]
                audio_data = b""
                
                communicate = edge_tts.Communicate(text_to_read, voice, rate=rate)
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                
                # 核心防线 2：网络请求归来后（可能过了好几秒），再次核对令牌！绝对不许把旧声音塞进新队列！
                if getattr(self, "is_tts_playing", False) and getattr(self, "tts_run_token", 0) == token and audio_data:
                    await self.tts_queue.put((idx, audio_data))

            if getattr(self, "is_tts_playing", False) and getattr(self, "tts_run_token", 0) == token:
                await self.tts_queue.put((None, None))
                
        except Exception as e:
            print(f"TTS 预加载网络异常: {e}")

    # ==============================================================
    # 💥 引擎2：消费者 (只管从托盘取现成的音频播放，负责翻页与UI联动)
    # ==============================================================
    async def _tts_consumer(self, token):
        try:
            while getattr(self, "is_tts_playing", False):
                if getattr(self, "tts_run_token", 0) != token:
                    break

                item = await self.tts_queue.get()
                chunk_idx, audio_data = item

                if chunk_idx is None:
                    if not getattr(self, "is_tts_playing", False) or getattr(self, "tts_run_token", 0) != token:
                        break

                    if self.current_chapter_idx < len(self.engine.chapters_info) - 1:
                        self.show_snack_bar("自动为您播放下一章...")
                        self.page.run_task(self.close_reader_overlays)
                        self.load_next()
                        await asyncio.sleep(1)
                        self.start_tts()
                    else:
                        self.stop_tts()
                        self.show_snack_bar("🎧 全书已播放完毕")
                    break

                self.tts_current_chunk_idx = chunk_idx
                self.page.run_task(self._update_tts_highlight)

                # 滚动定位
                # 💥 核心修复 2：增加 getattr(..., "page", None) 判断。
                # 只有当控件确实存活且挂载在当前页面上时，才执行滚动！
                if hasattr(self, "text_scroll_col") and getattr(self.text_scroll_col, "page", None) is not None:
                    try:
                        render_id = getattr(self, "current_render_id", 0)
                        target_key = f"chunk_{render_id}_{self.tts_current_chunk_idx}"
                        scroll_result = self.text_scroll_col.scroll_to(scroll_key=target_key, duration=500)
                        if asyncio.iscoroutine(scroll_result):
                            await scroll_result
                    except Exception as e:
                        print(f"TTS 滚动定位失败: {e}")

                if not audio_data:
                    continue

                # 写入物理文件
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                assets_dir = os.path.join(base_dir, "assets")
                temp_audio_dir = os.path.join(assets_dir, "temp_audio")
                if not os.path.exists(temp_audio_dir):
                    os.makedirs(temp_audio_dir)

                filename = f"novel_tts_{self.tts_run_token}_{chunk_idx}.mp3"
                temp_file_path = os.path.join(temp_audio_dir, filename)

                with open(temp_file_path, "wb") as f:
                    f.write(audio_data)

                # 清理上一段文件
                if hasattr(self, "last_temp_file") and os.path.exists(getattr(self, "last_temp_file", "")):
                    try:
                        os.remove(self.last_temp_file)
                    except Exception:
                        pass
                self.last_temp_file = temp_file_path

                # ---------- 正确的同步调用 + 事件等待 ----------
                if not os.path.exists(temp_file_path):
                    print(f"❌ 文件不存在，跳过: {temp_file_path}")
                    continue
                file_size = os.path.getsize(temp_file_path)
                if file_size < 100:
                    print(f"⚠️ 音频文件太小 ({file_size} bytes)，跳过")
                    continue
                print(f"🎵 准备播放: {temp_file_path} ({file_size} bytes)")

                # ---- 播放新音频 ----
                # 1. 彻底释放并销毁旧播放器资源
                if getattr(self, "tts_audio_player", None):
                    try:
                        # 💥 致命修复 1：必须加上 await 唤醒底层音频驱动去真正执行暂停和释放！
                        await self.tts_audio_player.pause()
                        if hasattr(self.tts_audio_player, "release"):
                            await self.tts_audio_player.release()
                    except Exception as e:
                        print(f"释放旧播放器失败: {e}")
                    
                    # 💥 致命修复 2：必须将废弃的播放器从服务列表中“连根拔起”，绝不留内存隐患！
                    if self.tts_audio_player in getattr(self.page, "services", []):
                        self.page.services.remove(self.tts_audio_player)
                        
                await asyncio.sleep(0.2)

                # 2. 创建全新的 Audio 控件
                self.tts_audio_player = fta.Audio(
                    src=f"temp_audio/{filename}",
                    autoplay=True,
                    on_state_change=self._on_audio_state_callback,
                    volume=1.0,
                    release_mode=fta.ReleaseMode.STOP,
                )
                # 重新挂载到干净的页面服务中
                self.page.services.append(self.tts_audio_player)
                self.page.update()
                await asyncio.sleep(0.3)      # 等待前端完成挂载和加载

                # 3. 准备等待播放完成
                self.tts_audio_completed_event.clear()
                self._waiting_for_stop = True
                print(f"   -> 新播放器已创建并挂载，等待播放完成: {filename}")

                try:
                    await asyncio.wait_for(
                        self.tts_audio_completed_event.wait(),
                        timeout=60.0
                    )
                    print(f"✅ 段落 {chunk_idx} 播放完成")
                except asyncio.TimeoutError:
                    print(f"⚠️ 段落 {chunk_idx} 播放超时，强制继续")
                finally:
                    self._waiting_for_stop = False
                # -----------------------------------------------------------

        except Exception as e:
            print(f"TTS 播放异常: {e}")
            self.show_snack_bar("❌ 语音播放异常，已停止。")
            self.stop_tts()

    # ==============================================================
    # 引擎3：UI 伴读渲染器 (动态高亮当前段落)
    # ==============================================================
    async def _update_tts_highlight(self): # 添加 async，使其成为标准的协程函数
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
