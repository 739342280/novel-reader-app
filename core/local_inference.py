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
                    # 提取返回的多个向量，并严格按照原数组的索引顺序排列
                    embeddings = [item["embedding"] for item in sorted(res_body["data"], key=lambda x: x["index"])]
                    return embeddings
                    
            except urllib.error.HTTPError as e:
                err_msg = e.read().decode('utf-8')
                raise Exception(f"批量建库失败，引擎拒绝了格式 (HTTP {e.code}): {err_msg}")
                
            except urllib.error.URLError as e:
                raise Exception(f"请求本地引擎发生网络错误: {e}")
        
        # 💥 接收 n_parallel 参数
        def __init__(self, model_path: str, n_parallel: int = 8):
            self.model_path = model_path
            self.n_parallel = n_parallel
            self.port = 18080 
            self.server_url = f"http://127.0.0.1:{self.port}/v1/embeddings"
            self.process = None
            # self.dim = 1024 
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
                "-ngl", "99",
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
    # 【Android / 移动端 NDK 核心】带 C++ 深度日志探针版
    # ---------------------------------------------------------
    import ctypes

    # 💥 全局日志拦截器：用于截获 C++ 哑巴引擎的真实求救信号
    _llama_internal_logs = []
    llama_log_cb_func = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)

    def _llama_log_callback(level, text, user_data):
        try:
            msg = text.decode('utf-8', errors='ignore').strip()
            if msg:
                # 过滤掉罗嗦的权重加载进度，只留核心信息
                if "loading tensor" not in msg and "load_weights" not in msg:
                    _llama_internal_logs.append(msg)
        except:
            pass

    _global_llama_log_cb = llama_log_cb_func(_llama_log_callback)

    class LlamaModelParams(ctypes.Structure):
        _fields_ = [
            ("n_gpu_layers", ctypes.c_int32),
            ("split_mode", ctypes.c_int32),
            ("main_gpu", ctypes.c_int32),
            ("tensor_split", ctypes.POINTER(ctypes.c_float)),
            ("rpc_servers", ctypes.c_char_p),
            ("progress_callback", ctypes.c_void_p),
            ("progress_callback_user_data", ctypes.c_void_p),
            ("kv_overrides", ctypes.c_void_p),
            ("vocab_only", ctypes.c_bool),
            ("use_mmap", ctypes.c_bool),
            ("use_mlock", ctypes.c_bool),
            ("check_tensors", ctypes.c_bool),
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
            ("logits_all", ctypes.c_bool),
            ("embeddings", ctypes.c_bool),
            ("offload_kqv", ctypes.c_bool),
            ("flash_attn", ctypes.c_bool),
            ("no_perf", ctypes.c_bool),         
            ("abort_callback", ctypes.c_void_p),
            ("abort_callback_data", ctypes.c_void_p),
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
            ("all_pos_0", ctypes.c_int32),
            ("all_pos_1", ctypes.c_int32),
            ("all_seq_id", ctypes.c_int32),
        ]

    class LocalEmbeddingEngine:
        def __init__(self, model_path: str, n_parallel: int = 8):
            self.model_path = model_path
            self.n_parallel = n_parallel
            
            global _llama_internal_logs
            _llama_internal_logs.clear()
            
            if not os.path.exists(self.model_path):
                raise Exception(f"系统找不到模型文件！\n路径: {self.model_path}")
            
            try:
                with open(self.model_path, 'rb') as f:
                    magic = f.read(4)
                    if magic != b'GGUF':
                        raise Exception(f"【模型损坏】该文件根本不是 GGUF 格式！开头字节: {magic}")
            except Exception as e:
                if "模型损坏" in str(e): raise e
                raise Exception(f"【权限锁死】Python 无法读取该文件: {e}")

            # 1. 仅加载核心库与接口绑定
            self.lib = self._load_library()
            
            try:
                self.lib.llama_log_set(_global_llama_log_cb, None)
            except Exception: pass

            # 2. 必须先初始化引擎大脑
            self.lib.llama_backend_init()
            
            # 💥 3. 终极大招：Python 级反射注入 (完美绕过安卓 dlopen 黑洞)
            native_lib_dir = os.environ.get("GGML_BACKEND_PATH", "")
            # 抓取框架核心，准备接收肌肉模块
            lib_ggml = ctypes.CDLL(os.path.join(native_lib_dir, "libggml.so")) if native_lib_dir else self.lib
            
            registered_count = 0
            if native_lib_dir and os.path.exists(native_lib_dir):
                for file_name in os.listdir(native_lib_dir):
                    if file_name.startswith("libggml-cpu") and file_name.endswith(".so"):
                        try:
                            # 第一步：用 Python 强行把肌肉模块拉进全局内存
                            cpu_lib = ctypes.CDLL(os.path.join(native_lib_dir, file_name), mode=ctypes.RTLD_GLOBAL)
                            
                            # 第二步：反向侦测它的内部注册函数
                            if hasattr(cpu_lib, "ggml_backend_reg_get"):
                                cpu_lib.ggml_backend_reg_get.restype = ctypes.c_void_p
                                reg_ptr = cpu_lib.ggml_backend_reg_get() # 获取肌肉的物理指针
                                
                                # 第三步：强行插回主框架！
                                if reg_ptr and hasattr(lib_ggml, "ggml_backend_register"):
                                    lib_ggml.ggml_backend_register.argtypes = [ctypes.c_void_p]
                                    lib_ggml.ggml_backend_register(reg_ptr)
                                    registered_count += 1
                                    _llama_internal_logs.append(f"✅ 反射注册成功: {file_name}")
                        except Exception as e:
                            _llama_internal_logs.append(f"反射失败 {file_name}: {e}")

            # 兜底：保留官方指令，万一反射漏了什么
            original_cwd = os.getcwd()
            try:
                if native_lib_dir: os.chdir(native_lib_dir)
                if hasattr(lib_ggml, 'ggml_backend_load_all'):
                    lib_ggml.ggml_backend_load_all()
            except Exception: pass
            finally:
                os.chdir(original_cwd)
                
            mparams = self.lib.llama_model_default_params()
            b_path = self.model_path.encode('utf-8')
            self.model = self.lib.llama_load_model_from_file(ctypes.c_char_p(b_path), mparams)
            
            if not self.model:
                log_details = "\n".join(_llama_internal_logs[-12:])
                raise Exception(f"【引擎内部报错】加载失败！C++ 底层真实原因如下:\n{log_details}")
                
            cparams = self.lib.llama_context_default_params()
            cparams.embeddings = True
            cparams.n_threads = 4 
            
            self.ctx = self.lib.llama_new_context_with_model(self.model, cparams)
            if not self.ctx:
                log_details = "\n".join(_llama_internal_logs[-5:])
                raise Exception(f"无法创建本地模型上下文！底层原因:\n{log_details}")
            
            self.dim = self.lib.llama_n_embd(self.model)

        def _load_library(self):
            global _llama_internal_logs
            
            native_lib_dir = ""
            try:
                import glob
                paths = glob.glob("/data/app/*/com.shoubeier*/lib/arm64*")
                if paths:
                    native_lib_dir = paths[0]
                    os.environ["GGML_BACKEND_PATH"] = native_lib_dir
            except Exception as e:
                _llama_internal_logs.append(f"寻找原生库路径失败: {e}")

            # 提前按族谱把基础环境铺垫好
            if native_lib_dir:
                for base_lib in ["libggml-base.so", "libggml.so"]:
                    try:
                        ctypes.CDLL(os.path.join(native_lib_dir, base_lib), mode=ctypes.RTLD_GLOBAL)
                    except Exception: pass

            main_path = os.path.join(native_lib_dir, "libllama.so") if native_lib_dir else "libllama.so"
            try:
                lib_llama = ctypes.CDLL(main_path, mode=ctypes.RTLD_GLOBAL)
            except Exception as e:
                raise Exception(f"主引擎 libllama.so 彻底加载失败: {e}")

            # 接口绑定不变
            lib_llama.llama_backend_init.argtypes = []
            lib_llama.llama_model_default_params.restype = LlamaModelParams
            lib_llama.llama_context_default_params.restype = LlamaContextParams
            lib_llama.llama_load_model_from_file.argtypes = [ctypes.c_char_p, LlamaModelParams]
            lib_llama.llama_load_model_from_file.restype = ctypes.c_void_p
            lib_llama.llama_new_context_with_model.argtypes = [ctypes.c_void_p, LlamaContextParams]
            lib_llama.llama_new_context_with_model.restype = ctypes.c_void_p
            lib_llama.llama_n_embd.argtypes = [ctypes.c_void_p]
            lib_llama.llama_n_embd.restype = ctypes.c_int
            lib_llama.llama_tokenize.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int32), ctypes.c_int, ctypes.c_bool, ctypes.c_bool]
            lib_llama.llama_tokenize.restype = ctypes.c_int
            lib_llama.llama_decode.argtypes = [ctypes.c_void_p, LlamaBatch]
            lib_llama.llama_decode.restype = ctypes.c_int
            lib_llama.llama_get_embeddings.argtypes = [ctypes.c_void_p]
            lib_llama.llama_get_embeddings.restype = ctypes.POINTER(ctypes.c_float)
            
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
            text_bytes = text.encode('utf-8')
            n_max_tokens = 512
            tokens_array = (ctypes.c_int32 * n_max_tokens)()
            n_tokens = self.lib.llama_tokenize(self.model, text_bytes, len(text_bytes), tokens_array, n_max_tokens, ctypes.c_bool(True), ctypes.c_bool(True))
            
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
            for i in range(n_tokens): logits_array[i] = 0
            logits_array[n_tokens - 1] = 1 
            batch.logits = ctypes.cast(logits_array, ctypes.POINTER(ctypes.c_int8))
            
            batch.all_pos_0 = 0
            batch.all_pos_1 = 0
            batch.all_seq_id = 0

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

        def __del__(self):
            if hasattr(self, 'ctx') and self.ctx: self.lib.llama_free(self.ctx)
            if hasattr(self, 'model') and self.model: self.lib.llama_free_model(self.model)
            if hasattr(self, 'lib') and self.lib: self.lib.llama_backend_free()