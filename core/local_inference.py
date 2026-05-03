import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error

# =========================================================================
# 智能双核本地推理引擎 (Win11 测试核心 / Android 原生 NDK 核心)
# =========================================================================

if sys.platform == "win32":
    # ---------------------------------------------------------
    # 【Win11 桌面端测试核心】
    # 彻底避开 Windows 编译器 ABI 指针越界崩溃 (0x1B00000199)
    # 使用官方自带的 llama-server.exe 物理隔离内存，通过 HTTP 高速获取向量
    # ---------------------------------------------------------
    class LocalEmbeddingEngine:
        def get_embeddings(self, texts: list[str]) -> list[list[float]]:
            """【终极降维打击】批量请求接口，榨干 4070 Super 并发算力"""
            if not self.process or self.process.poll() is not None:
                raise Exception("底层推理引擎已意外退出")

            # 将单个字符串改为字符串数组，一次性砸给大模型
            payload = json.dumps({
                "input": texts,
                "model": "qwen3-embedding" 
            }).encode('utf-8')
            
            req = urllib.request.Request(
                self.server_url, 
                data=payload, 
                headers={'Content-Type': 'application/json'}
            )

            try:
                with urllib.request.urlopen(req, timeout=120) as response:
                    res_body = json.loads(response.read().decode('utf-8'))
                    
                    data_list = res_body.get("data", [])
                    
                    # 1. 防御性检查：返回的数据条数是否与请求的条数一致
                    if len(data_list) != len(texts):
                        raise Exception(f"数据丢失！发送了 {len(texts)} 条文本，但引擎只返回了 {len(data_list)} 条结果。")

                    # 2. 安全提取：不使用脆弱的列表推导式
                    embeddings = []
                    # 先按照引擎返回的 index 排序（兼容 OpenAI 规范）
                    sorted_data = sorted(data_list, key=lambda x: x.get("index", 0))
                    
                    for i, item in enumerate(sorted_data):
                        emb = item.get("embedding")
                        if not emb:
                            raise Exception(f"批处理失败！第 {i} 条返回的数据中缺失 'embedding' 字段。")
                        embeddings.append(emb)

                    return embeddings
                    
            except urllib.error.HTTPError as e:
                err_msg = e.read().decode('utf-8')
                raise Exception(f"批量建库失败，引擎拒绝了格式 (HTTP {e.code}): {err_msg}")
                
            except urllib.error.URLError as e:
                raise Exception(f"请求本地引擎发生网络错误: {e}")
        
        # 💥 接收 hardware_mode 参数
        def __init__(self, model_path: str, n_parallel: int = 1, n_ubatch: int = 512, hardware_mode: str = "强制GPU模式", n_gpu_layers: int = 0):
            self.model_path = model_path
            self.n_parallel = n_parallel
            self.n_ubatch = n_ubatch  
            self.hardware_mode = hardware_mode # 💥 保存状态
            self.target_gpu_layers = n_gpu_layers # 保存 UI 传来的目标层数
            self.port = 18080 
            self.server_url = f"http://127.0.0.1:{self.port}/v1/embeddings"
            self.process = None
            self._start_local_server()

        def _start_local_server(self):
            """静默启动底层的独立 C++ 推理服务器"""
            import multiprocessing
            optimal_threads = str(max(1, multiprocessing.cpu_count() // 2))

            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.getcwd()  # 💡 修改点1：改回 os.getcwd() 以匹配你实际的工作目录
                
            exe_path = os.path.join(base_dir, "assets", "llama-server.exe")
            
            if not os.path.exists(exe_path):
                # 💡 修改点2：将拼装好的绝对路径直接打印在报错里，实现精准定位
                raise FileNotFoundError(f"【引擎缺失】未找到引擎文件！\n程序正在此处寻找：{exe_path}\n请确保文件在上述准确位置，且没被系统隐藏后缀导致变成了 .exe.exe")

            # 💥 让代码自动计算上下文！每个通道死保 1024 容量
            ctx_size = str(self.n_parallel * 1024)

            # 💥 判断是否使用 CPU 模式
            ngl_value = "99" if self.hardware_mode == "强制GPU模式" else "0"

            # 核心启动参数：加载模型，开启向量模式，绑定端口
            cmd = [
                exe_path,
                "-m", self.model_path,
                "--port", str(self.port),
                "--embedding",
                "--parallel", str(self.n_parallel),  # 💥 注入 UI 传来的并发通道数
                "-c", ctx_size,                      # 💥 注入算好的总容量
                "-b", ctx_size,                      # 💥 批处理同步放大
                "-t", optimal_threads,
                "-ngl", ngl_value,  # 💥 动态注入 GPU 层数
                "--pooling", "mean"
            ]

            # 隐藏 Windows 背后弹出的黑色 CMD 窗口
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            # 启动独立进程
            self.process = subprocess.Popen(
                cmd,
                startupinfo=startupinfo, # 💥 1. 恢复这行，不再让黑框弹出来烦人
                stdout=subprocess.PIPE,  # 💥 2. 开启管道，截获标准输出日志
                stderr=subprocess.STDOUT,# 💥 3. 截获报错信息合并进日志
                text=True,               # 💥 4. 自动解码为文本
                encoding='utf-8',
                errors='ignore'
            )

            # 轮询探测服务是否就绪
            for _ in range(60):
                if self.process.poll() is not None:
                    self._stop_local_server()
                    raise Exception("引擎刚启动就崩溃退出了！")
                    
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{self.port}/health")
                    with urllib.request.urlopen(req, timeout=1) as response:
                        if response.status == 200:
                            return # 启动成功！
                            
                except urllib.error.HTTPError as e:
                    # 💥 核心修复：精准狙击引擎内部报错
                    if e.code == 500:
                        err_body = e.read().decode('utf-8')
                        self._stop_local_server()
                        raise Exception(f"模型加载彻底失败！引擎返回致命错误: {err_body}")
                    # 如果是 503 (Service Unavailable)，说明还在努力加载，继续等
                    
                except Exception:
                    pass
                time.sleep(0.5)
            
            self._stop_local_server()
            raise Exception("本地微服务启动超时，请检查模型文件是否完好。")

        def get_embedding(self, text: str) -> list[float]:
            if not self.process or self.process.poll() is not None:
                raise Exception("底层推理引擎已意外退出")

            # 💡 修改点1：补全严格遵循 OpenAI 规范的 JSON 请求体
            payload = json.dumps({
                "input": text,
                "model": "qwen3-embedding"  # 最新版 server 强制要求携带此字段，否则报 400
            }).encode('utf-8')
            
            req = urllib.request.Request(
                self.server_url, 
                data=payload, 
                headers={'Content-Type': 'application/json'}
            )

            try:
                with urllib.request.urlopen(req, timeout=120) as response:
                    res_body = json.loads(response.read().decode('utf-8'))
                    return res_body["data"][0]["embedding"]
                    
            # 💡 修改点2：精准捕获 HTTPError，打印服务器底层的真实抱怨信息
            except urllib.error.HTTPError as e:
                err_msg = e.read().decode('utf-8')
                raise Exception(f"建库失败，引擎拒绝了格式 (HTTP {e.code}): {err_msg}")
                
            except urllib.error.URLError as e:
                raise Exception(f"请求本地引擎发生网络错误: {e}")

        def _stop_local_server(self):
            """严谨的资源回收，确保软件关闭时引擎一并退出"""
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()

        def __del__(self):
            self._stop_local_server()

else:
    # ---------------------------------------------------------
    # 【Android / 移动端 NDK 核心】带 C++ 深度日志与多态反射探针版
    # ---------------------------------------------------------
    import ctypes

    _llama_internal_logs = []
    _debug_log_path = None
    llama_log_cb_func = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)

    def _llama_log_callback(level, text, user_data):
        try:
            msg = text.decode('utf-8', errors='ignore').strip()
            if msg: # 💥 测试阶段：不要过滤 "loading tensor" 了，全量输出！看看死在第几个张量！
                _llama_internal_logs.append(f"[C++] {msg}")
                # 💥 核心绝杀：一旦有日志，立刻、强行写入物理硬盘！不用管性能损耗，只求留住遗言！
                global _debug_log_path
                if _debug_log_path:
                    with open(_debug_log_path, 'a', encoding='utf-8') as f:
                        f.write(f"[C++] {msg}\n")
                        f.flush() # 强制刷入硬盘，防止系统缓存还没落地就崩溃了
                        os.fsync(f.fileno()) 
        except:
            pass

    _global_llama_log_cb = llama_log_cb_func(_llama_log_callback)

    class LlamaModelParams(ctypes.Structure):
        _fields_ = [
            ("devices", ctypes.c_void_p),
            ("tensor_buft_overrides", ctypes.c_void_p),
            ("n_gpu_layers", ctypes.c_int32),
            ("split_mode", ctypes.c_int32),
            ("main_gpu", ctypes.c_int32),
            ("tensor_split", ctypes.POINTER(ctypes.c_float)),
            ("progress_callback", ctypes.c_void_p),
            ("progress_callback_user_data", ctypes.c_void_p),
            ("kv_overrides", ctypes.c_void_p),
            ("vocab_only", ctypes.c_bool),
            ("use_mmap", ctypes.c_bool),
            ("use_direct_io", ctypes.c_bool),
            ("use_mlock", ctypes.c_bool),
            ("check_tensors", ctypes.c_bool),
            ("use_extra_bufts", ctypes.c_bool),
            ("no_host", ctypes.c_bool),
            ("no_alloc", ctypes.c_bool),
        ]

    class LlamaContextParams(ctypes.Structure):
        _fields_ = [
            ("n_ctx", ctypes.c_uint32),
            ("n_batch", ctypes.c_uint32),
            ("n_ubatch", ctypes.c_uint32),
            ("n_seq_max", ctypes.c_uint32),
            ("n_threads", ctypes.c_int32),
            ("n_threads_batch", ctypes.c_int32),
            ("rope_scaling_type", ctypes.c_int32),
            ("pooling_type", ctypes.c_int32),
            ("attention_type", ctypes.c_int32),
            ("flash_attn_type", ctypes.c_int32),
            ("rope_freq_base", ctypes.c_float),
            ("rope_freq_scale", ctypes.c_float),
            ("yarn_ext_factor", ctypes.c_float),
            ("yarn_attn_factor", ctypes.c_float),
            ("yarn_beta_fast", ctypes.c_float),
            ("yarn_beta_slow", ctypes.c_float),
            ("yarn_orig_ctx", ctypes.c_uint32),
            ("defrag_thold", ctypes.c_float),
            ("cb_eval", ctypes.c_void_p),
            ("cb_eval_user_data", ctypes.c_void_p),
            ("type_k", ctypes.c_int32),
            ("type_v", ctypes.c_int32),
            ("abort_callback", ctypes.c_void_p),
            ("abort_callback_data", ctypes.c_void_p),
            ("embeddings", ctypes.c_bool),
            ("offload_kqv", ctypes.c_bool),
            ("no_perf", ctypes.c_bool),
            ("op_offload", ctypes.c_bool),
            ("swa_full", ctypes.c_bool),
            ("kv_unified", ctypes.c_bool),
            ("samplers", ctypes.c_void_p),
            ("n_samplers", ctypes.c_size_t),
        ]

    class LlamaBatch(ctypes.Structure):
        _fields_ = [
            ("n_tokens", ctypes.c_int32),
            ("token", ctypes.POINTER(ctypes.c_int32)),
            ("embd", ctypes.POINTER(ctypes.c_float)),
            ("pos", ctypes.POINTER(ctypes.c_int32)),
            ("n_seq_id", ctypes.POINTER(ctypes.c_int32)),
            ("seq_id", ctypes.POINTER(ctypes.POINTER(ctypes.c_int32))),
            ("logits", ctypes.POINTER(ctypes.c_int8)),
        ]

    class LocalEmbeddingEngine:
        
        def __init__(self, model_path: str, n_parallel: int = 1, n_ubatch: int = 512, hardware_mode: str = "强制GPU模式", n_gpu_layers: int = 0):
            self.model_path = model_path
            self.n_parallel = n_parallel
            self.n_ubatch = n_ubatch
            self.hardware_mode = hardware_mode 
            self.target_gpu_layers = n_gpu_layers # 保存 UI 传来的目标层数
            
            # 💥 1. 初始化黑匣子文件（和你的 Qwen 模型放在同一个目录下）
            global _debug_log_path
            _debug_log_path = self.model_path + ".vk_debug_blackbox.txt"
            
            # 每次初始化，清空旧的日志，开始新的记录
            with open(_debug_log_path, 'w', encoding='utf-8') as f:
                f.write("========== VULKAN 极限测试黑匣子日志启动 ==========\n")
                f.flush()

            def log_milestone(step_msg):
                """写 Python 里程碑的辅助函数"""
                with open(_debug_log_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n[Python 哨兵] ---> {step_msg} <---\n")
                    f.flush()
                    os.fsync(f.fileno())

            log_milestone("开始执行 _load_library (加载动态库)")
            self.lib = self._load_library()
            
            try:
                self.lib.llama_log_set(_global_llama_log_cb, None)
            except Exception: pass

            log_milestone("执行 llama_backend_init")
            self.lib.llama_backend_init()

            mparams = self.lib.llama_model_default_params()
            
            # 💥 2. 贯彻测试意志：只要是智能模式，无视探针的 vulkan_available 结果，强上 GPU 层数！
            if self.hardware_mode == "强制GPU模式":
                mparams.n_gpu_layers = self.target_gpu_layers
                log_milestone(f"已强制设定 GPU 层数为: {mparams.n_gpu_layers}")
                # 💥 核心修复一：在 GPU 模式下，必须彻底关闭 mmap！
                # 只有关闭它，才能避免 Vulkan_Host 拷贝时的内存越界崩溃
                mparams.use_mmap = False
            else:
                mparams.n_gpu_layers = 0                 
                mparams.use_mmap = True
            
            b_path = self.model_path.encode('utf-8')
            
            # 💥 3. 死亡雷区前瞻
            log_milestone("【高危操作】准备执行 llama_model_load_from_file (向显卡塞入模型权重)")
            self.model = self.lib.llama_model_load_from_file(ctypes.c_char_p(b_path), mparams)
            
            if not self.model:
                raise Exception("模型加载失败，返回了空指针。")
                
            log_milestone("【存活确认】llama_model_load_from_file 成功通过！模型权重已进入显存。")
            
            self.vocab = self.lib.llama_model_get_vocab(self.model)
                
            cparams = self.lib.llama_context_default_params()
            cparams.embeddings = True
            cparams.pooling_type = 1            

            import multiprocessing
            cpu_cores = multiprocessing.cpu_count()
            optimal_threads = min(4, max(1, cpu_cores - 2)) 
            cparams.n_threads = optimal_threads 
            cparams.n_threads_batch = optimal_threads

            # ---------------------------------------------------------
            # 🎯 内存与吞吐量核心调优区 (黄金参数)
            # ---------------------------------------------------------

            # 1. cparams.n_ctx (总物理上下文 / 总仓库面积)
            # 【功能】决定了引擎能占用多少 RAM，以及最多能同时记住多少个 Token。
            # 【优化】设为 8192 约消耗 1.5GB-2.5GB 运存，对于 8GB/12GB 运存的手机是最安全的甜点值。
            # 如果设得太大（如 65536），极易被安卓低内存杀手（LMK）直接闪退。
            cparams.n_ctx = 2048

            # 2. cparams.n_batch (逻辑批处理量 / 卸货区大小)
            # 【功能】告诉底层引擎，上层 Python 一次性最多会扔多少个 Token 过来。
            # 【作用】必须大于等于你一次传入的总 Token 数。设为 8192，意味着你 UI 上的 Batch Size 
            # 即使拉到 15 块（15 * 512 = 7680），引擎也愿意接收。
            cparams.n_batch = 2048
            
            # 3. cparams.n_ubatch (物理吞吐量 / 运算切片大小) —— 💥 手机防爆缸救命参数
            # 【功能】CPU ALU（算术逻辑单元）在一次底层的矩阵乘法（GEMM）中真正吞食的 Token 数量。
            # 【作用】自动切片！虽然逻辑上你一次扔了 7680 个 Token，但如果 n_ubatch=512，
            # 引擎会在底层自动将这 7680 个 Token 切成 15 份（每份 512）排队计算。
            # 这不仅保住了真批处理“只加载一次模型权重”的巨大优势，还把计算瞬时内存峰值压低了 90%！
            cparams.n_ubatch = self.n_ubatch
            
            # 4. cparams.n_seq_max (最大序列数 / 互不干扰的独立车道)
            # 【功能】KV Cache 中最多能同时存放多少个“独立的上下文”。
            # 【作用】你切出来的每一块小说，都是一个独立的序列（需要赋予不同的 seq_id 0, 1, 2...）。
            # 这个数字必须大于等于你 UI 上允许的极限批处理量（Batch Size）。设为 128 绝对够用。
            cparams.n_seq_max = 8
            
            # 5. cparams.kv_unified (全局统一内存池)
            # 【功能】打破物理隔离！如果不设为 True，n_ctx(8192) 会被 n_seq_max(128) 静态平分，
            # 导致每个序列只能塞进 64 个 Token（导致大块文本直接报错 Error 1）。
            # 设为 True 后，变成共享大平层，只要总和不超过 8192，内存随便用。
            cparams.kv_unified = True

            # 🔧 关键：强制关闭 Flash Attention，防止驱动因大型着色器崩溃
            cparams.flash_attn_type = 0 

            # 💥 新增这行代码：把配置参数保存下来
            self.cparams = cparams

            # =========================================================================

            # 💥 4. 第二死亡雷区前瞻
            log_milestone("【高危操作】准备执行 llama_init_from_model (向显卡申请 KV Cache 和计算缓存)")
            self.ctx = self.lib.llama_init_from_model(self.model, cparams)
            
            if not self.ctx:
                raise Exception(f"无法创建本地模型上下文！")
                
            log_milestone("【存活确认】llama_init_from_model 成功通过！全部初始化完毕。")
            
            self.dim = self.lib.llama_n_embd(self.model)
            self.memory = self.lib.llama_get_memory(self.ctx)

        def _load_library(self):
            # 💥 1. 恢复丢失的核心护盾：如果用户选了纯 CPU，必须从物理底层彻底屏蔽 GPU 设备！
            if getattr(self, 'hardware_mode', "") == "强制 CPU 模式":
                os.environ["GGML_VK_VISIBLE_DEVICES"] = "none"
            else:
                # 切回 GPU 模式时，解除屏蔽
                if "GGML_VK_VISIBLE_DEVICES" in os.environ:
                    del os.environ["GGML_VK_VISIBLE_DEVICES"]

            os.environ["GGML_VULKAN_DISABLE_BAD_DEVICES"] = "1"
            
            self.vulkan_available = False
            self.vulkan_disable_reason = "初始化未完成"
            
            dependencies = [
                "libggml-base.so",
                "libggml.so",
                "libggml-cpu.so",       # 必须保留
                "libggml-vulkan.so",    # 必须保留
            ]
            for lib_name in dependencies:
                try:
                    ctypes.CDLL(lib_name, mode=ctypes.RTLD_GLOBAL)
                except Exception:
                    pass

            # 💥 2. 优化逻辑：如果是强制 CPU 模式，直接跳过探针探测，防止引发意外崩溃
            if getattr(self, 'hardware_mode', "") == "强制 CPU 模式":
                self.vulkan_available = False
                self.vulkan_disable_reason = "用户已手动强制使用 CPU"
            else:
                # 只有在“智能模式”下，才去探测 Vulkan
                try:
                    vk_lib = ctypes.CDLL("libggml-vulkan.so", mode=ctypes.RTLD_GLOBAL)
                    if hasattr(vk_lib, "ggml_backend_vk_reg"):
                        vk_lib.ggml_backend_vk_reg.restype = ctypes.c_void_p
                        reg_ptr = vk_lib.ggml_backend_vk_reg()
                        if reg_ptr is not None and reg_ptr != 0:
                            self.vulkan_available = True
                            self.vulkan_disable_reason = ""
                            _llama_internal_logs.append("[Python] Vulkan 后端初始化成功，将尝试启用 GPU 加速")
                        else:
                            vk_err = "驱动不支持或缺少必要扩展"
                            if _llama_internal_logs:
                                for log in reversed(_llama_internal_logs):
                                    if "vulkan" in log.lower() or "vk" in log.lower() or "error" in log.lower():
                                        vk_err = log.replace("[C++] ", "")
                                        break
                            self.vulkan_disable_reason = f"底层注册被拒 ({vk_err})"
                            _llama_internal_logs.append(f"[Python] Vulkan 探测失败: {self.vulkan_disable_reason}")
                    else:
                        self.vulkan_disable_reason = "库文件受损，找不到 Vulkan 注册入口"
                except Exception as e:
                    self.vulkan_disable_reason = f"加载动态库异常: {str(e)}"

            try:
                lib_llama = ctypes.CDLL("libllama.so", mode=ctypes.RTLD_GLOBAL)
            except Exception as e:
                raise Exception(f"主引擎彻底加载失败: {e}")

            # --- 下面雷打不动的接口绑定保持原样 ---
            lib_llama.llama_backend_init.argtypes = []
            lib_llama.llama_model_default_params.restype = LlamaModelParams
            lib_llama.llama_context_default_params.restype = LlamaContextParams            
            lib_llama.llama_n_embd.argtypes = [ctypes.c_void_p]
            lib_llama.llama_n_embd.restype = ctypes.c_int
            lib_llama.llama_tokenize.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int32), ctypes.c_int, ctypes.c_bool, ctypes.c_bool]
            lib_llama.llama_tokenize.restype = ctypes.c_int
            lib_llama.llama_decode.argtypes = [ctypes.c_void_p, LlamaBatch]
            lib_llama.llama_decode.restype = ctypes.c_int
            lib_llama.llama_get_embeddings.argtypes = [ctypes.c_void_p]
            lib_llama.llama_get_embeddings.restype = ctypes.POINTER(ctypes.c_float)
            # 新增/替换的绑定
            lib_llama.llama_model_get_vocab.argtypes = [ctypes.c_void_p]
            lib_llama.llama_model_get_vocab.restype = ctypes.c_void_p            
            lib_llama.llama_init_from_model.argtypes = [ctypes.c_void_p, LlamaContextParams]
            lib_llama.llama_init_from_model.restype = ctypes.c_void_p
            lib_llama.llama_model_load_from_file.argtypes = [ctypes.c_char_p, LlamaModelParams]
            lib_llama.llama_model_load_from_file.restype = ctypes.c_void_p
            lib_llama.llama_get_memory.argtypes = [ctypes.c_void_p]
            lib_llama.llama_get_memory.restype = ctypes.c_void_p        
            lib_llama.llama_memory_seq_rm.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
            lib_llama.llama_memory_seq_rm.restype = ctypes.c_bool
            lib_llama.llama_n_seq_max.argtypes = [ctypes.c_void_p]
            lib_llama.llama_n_seq_max.restype = ctypes.c_uint32
            # 💥 新增的物理重置接口绑定
            lib_llama.llama_memory_clear.argtypes = [ctypes.c_void_p, ctypes.c_bool]
            lib_llama.llama_memory_clear.restype = None
            # 💥 新增：官方的上下文强制同步接口
            try:
                lib_llama.llama_synchronize.argtypes = [ctypes.c_void_p]
                lib_llama.llama_synchronize.restype = None
            except Exception:
                pass

            
            try: lib_llama.llama_log_set.argtypes = [llama_log_cb_func, ctypes.c_void_p]
            except Exception: pass
            try:
                lib_llama.llama_get_embeddings_seq.argtypes = [ctypes.c_void_p, ctypes.c_int32]
                lib_llama.llama_get_embeddings_seq.restype = ctypes.POINTER(ctypes.c_float)
                lib_llama.llama_get_embeddings_ith.argtypes = [ctypes.c_void_p, ctypes.c_int32]
                lib_llama.llama_get_embeddings_ith.restype = ctypes.POINTER(ctypes.c_float)
            except Exception: pass
            
            lib_llama.llama_free.argtypes = [ctypes.c_void_p]
            lib_llama.llama_free_model.argtypes = [ctypes.c_void_p]
            lib_llama.llama_backend_free.argtypes = []
            
            return lib_llama
        
        def get_embedding(self, text: str) -> list[float]:
            if not self.ctx: return []
            
            # 💥 1. 彻底干掉 llama_memory_clear，用定向清理 0 号车道代替。
            # 完美避开高通驱动物理填零的 10 秒死锁！
            self.lib.llama_memory_seq_rm(self.memory, 0, 0, -1)

            text_bytes = text.encode('utf-8')
            n_max_tokens = 512
            tokens_array = (ctypes.c_int32 * n_max_tokens)()
            n_tokens = self.lib.llama_tokenize(self.vocab, text_bytes, len(text_bytes), tokens_array, n_max_tokens, ctypes.c_bool(True), ctypes.c_bool(True))
            
            if n_tokens <= 0: raise Exception("文本分词失败")

            batch = LlamaBatch()
            batch.n_tokens = n_tokens
            batch.token = ctypes.cast(tokens_array, ctypes.POINTER(ctypes.c_int32))
            batch.embd = ctypes.cast(None, ctypes.POINTER(ctypes.c_float))
            
            pos_array = (ctypes.c_int32 * n_tokens)()
            for i in range(n_tokens): pos_array[i] = i
            batch.pos = ctypes.cast(pos_array, ctypes.POINTER(ctypes.c_int32))
            
            n_seq_id_array = (ctypes.c_int32 * n_tokens)()
            for i in range(n_tokens): n_seq_id_array[i] = 1
            batch.n_seq_id = ctypes.cast(n_seq_id_array, ctypes.POINTER(ctypes.c_int32))
            
            seq_id_ptrs = (ctypes.POINTER(ctypes.c_int32) * n_tokens)()
            inner_seqs = [] 
            for i in range(n_tokens):
                inner = (ctypes.c_int32 * 1)(0)
                inner_seqs.append(inner)
                seq_id_ptrs[i] = ctypes.cast(inner, ctypes.POINTER(ctypes.c_int32))
            batch.seq_id = ctypes.cast(seq_id_ptrs, ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)))
            
            logits_array = (ctypes.c_int8 * n_tokens)() 
            
            # 💥 2. 只有最后一个 Token 赋 1！
            # 彻底终结 "1024 个结果塞进 8 个空位" 的显存越界大爆炸！
            for i in range(n_tokens): logits_array[i] = 0
            logits_array[n_tokens - 1] = 1
            
            batch.logits = ctypes.cast(logits_array, ctypes.POINTER(ctypes.c_int8))
            
            self._memory_shield = (pos_array, n_seq_id_array, seq_id_ptrs, inner_seqs, logits_array)

            res = self.lib.llama_decode(self.ctx, batch)
            if res != 0: raise Exception(f"向量计算失败，llama_decode 返回错误码: {res}")
            
            emb_ptr = self.lib.llama_get_embeddings(self.ctx)
            if not emb_ptr and hasattr(self.lib, 'llama_get_embeddings_seq'):
                emb_ptr = self.lib.llama_get_embeddings_seq(self.ctx, 0)
            if not emb_ptr and hasattr(self.lib, 'llama_get_embeddings_ith'):
                emb_ptr = self.lib.llama_get_embeddings_ith(self.ctx, n_tokens - 1)
                
            if not emb_ptr: raise Exception("未能成功获取 Embedding 指针")
                
            result = [emb_ptr[i] for i in range(self.dim)]
            self._memory_shield = None
            return result
        
        def get_embeddings(self, texts: list[str]) -> list[list[float]]:
            if not self.ctx: return []
            
            # 经过多轮测试，当前 Adreno 840 Vulkan 驱动在多序列批量解码时存在缺陷。
            # 因此，这里通过逐条调用已加固的 get_embedding 来保证稳定，同时对外保持批量接口不变。
            embeddings = []
            for text in texts:
                emb = self.get_embedding(text)
                embeddings.append(emb)
            return embeddings
        
        # def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        #     if not self.ctx: return []

        #     # 1. 批量分词 (保持不变)
        #     tokenized_texts = []
        #     total_tokens = 0
        #     n_max_tokens = 512
        #     for text in texts:
        #         text_bytes = text.encode('utf-8')
        #         tokens_array = (ctypes.c_int32 * n_max_tokens)()
        #         n_tokens = self.lib.llama_tokenize(self.vocab, text_bytes, len(text_bytes), tokens_array, n_max_tokens, ctypes.c_bool(True), ctypes.c_bool(True))
        #         if n_tokens > 0:
        #             tokenized_texts.append((n_tokens, tokens_array))
        #             total_tokens += n_tokens

        #     if total_tokens == 0: return []

        #     # 1. 精准定向清除：只清理本次建库实际用到的 seq_id
        #     for seq_id in range(len(tokenized_texts)):
        #         self.lib.llama_memory_seq_rm(self.memory, seq_id, 0, -1)

        #     # 2. 逻辑级清空：重置指针，但不触发物理零填充死锁
        #     self.lib.llama_memory_clear(self.memory, False)

        #     # 3. 强制同步：强迫 Vulkan 驱动执行完刚才所有内存指令，排空队列
        #     try:
        #         self.lib.llama_synchronize(self.ctx)
        #     except Exception:
        #         pass

        #     # 4. 物理休眠：给 Android 系统看门狗 0.1 秒时间重置 TDR 计时器
        #     time.sleep(0.1)

        #     # 3. 构造超级 Batch (保持不变)
        #     token_arr = (ctypes.c_int32 * total_tokens)()
        #     pos_arr = (ctypes.c_int32 * total_tokens)()
        #     n_seq_id_arr = (ctypes.c_int32 * total_tokens)()
        #     logits_arr = (ctypes.c_int8 * total_tokens)()

        #     batch = LlamaBatch()
        #     batch.n_tokens = total_tokens
        #     batch.token = ctypes.cast(token_arr, ctypes.POINTER(ctypes.c_int32))
        #     batch.embd = ctypes.cast(None, ctypes.POINTER(ctypes.c_float))
        #     batch.pos = ctypes.cast(pos_arr, ctypes.POINTER(ctypes.c_int32))
        #     batch.n_seq_id = ctypes.cast(n_seq_id_arr, ctypes.POINTER(ctypes.c_int32))
        #     batch.logits = ctypes.cast(logits_arr, ctypes.POINTER(ctypes.c_int8))
            
        #     seq_id_ptrs = (ctypes.POINTER(ctypes.c_int32) * total_tokens)()
        #     inner_seqs = []
        #     for i in range(total_tokens):
        #         inner = (ctypes.c_int32 * 1)(0)
        #         inner_seqs.append(inner)
        #         seq_id_ptrs[i] = ctypes.cast(inner, ctypes.POINTER(ctypes.c_int32))
        #     batch.seq_id = ctypes.cast(seq_id_ptrs, ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)))

        #     # 💥 关键点：每个独立分块分配一个独立的 Sequence ID，且位置都从 0 开始
        #     idx = 0
        #     for seq_id, (n_tokens, tokens_array) in enumerate(tokenized_texts):
        #         for i in range(n_tokens):
        #             token_arr[idx] = tokens_array[i]
        #             pos_arr[idx] = i          
        #             n_seq_id_arr[idx] = 1
        #             inner_seqs[idx][0] = seq_id 
        #             # 💥 经典输出：只有该切块的最后一个 Token 给 1
        #             logits_arr[idx] = 1 if i == n_tokens - 1 else 0
        #             idx += 1

        #     self._memory_shield = (token_arr, pos_arr, n_seq_id_arr, logits_arr, seq_id_ptrs, inner_seqs)

        #     # 5. 一次性解码
        #     res = self.lib.llama_decode(self.ctx, batch)
        #     if res != 0: 
        #         raise Exception(f"批量向量计算失败，llama_decode 返回错误码: {res}。")
            
        #     # 强制同步：在提取向量前，确保 GPU 已经算完了
        #     try:
        #         self.lib.llama_synchronize(self.ctx)
        #     except Exception:
        #         pass

        #     # 6. 分离并提取向量 (保持不变)
        #     embeddings = []
        #     for seq_id in range(len(tokenized_texts)):
        #         emb_ptr = self.lib.llama_get_embeddings_seq(self.ctx, seq_id)
        #         if not emb_ptr:
        #             raise Exception(f"未能成功获取序列 {seq_id} 的 Embedding 指针")
        #         embeddings.append([emb_ptr[i] for i in range(self.dim)])

        #     self._memory_shield = None
        #     return embeddings
        
        def __del__(self):
            if hasattr(self, 'ctx') and self.ctx: self.lib.llama_free(self.ctx)
            if hasattr(self, 'model') and self.model: self.lib.llama_free_model(self.model)
            if hasattr(self, 'lib') and self.lib: self.lib.llama_backend_free()