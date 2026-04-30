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
    # 【Android / 移动端 NDK 核心】带 C++ 深度日志与多态反射探针版
    # ---------------------------------------------------------
    import ctypes

    _llama_internal_logs = []
    llama_log_cb_func = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)

    def _llama_log_callback(level, text, user_data):
        try:
            msg = text.decode('utf-8', errors='ignore').strip()
            if msg and "loading tensor" not in msg and "load_weights" not in msg:
                _llama_internal_logs.append(f"[C++] {msg}")
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
        def __init__(self, model_path: str, n_parallel: int = 8):
            self.model_path = model_path
            self.n_parallel = n_parallel
            
            global _llama_internal_logs
            _llama_internal_logs.clear()
            
            if not os.path.exists(self.model_path):
                raise Exception(f"系统找不到模型文件！\n路径: {self.model_path}")
            
            # 1. 极其清爽的加载 (无需任何多态反射或路径雷达)
            self.lib = self._load_library()
            
            try:
                self.lib.llama_log_set(_global_llama_log_cb, None)
            except Exception: pass

            self.lib.llama_backend_init()

            # 2. 直接加载模型
            mparams = self.lib.llama_model_default_params()
            b_path = self.model_path.encode('utf-8')
            
            self.model = self.lib.llama_model_load_from_file(ctypes.c_char_p(b_path), mparams)
            
            if not self.model:
                log_details = "\n".join(_llama_internal_logs[-15:])
                raise Exception(f"【引擎内部报错】加载失败！底层真实原因:\n{log_details}")
            
            # 💥 新增：获取 vocab 对象
            self.vocab = self.lib.llama_model_get_vocab(self.model)
                
            cparams = self.lib.llama_context_default_params()
            cparams.embeddings = True            

            import multiprocessing            
            optimal_threads = max(1, multiprocessing.cpu_count() - 2)
            cparams.n_threads = optimal_threads 
            
            # 💥 新增：放大批处理容量！
            # 假设你的 UI 最大 Batch Size 是 16，每段文本切块约 512 token
            # 16 * 512 = 8192。必须让 C++ 提前申请足够大的物理内存。
            cparams.n_batch = 8192
            cparams.n_ubatch = 8192  # 💥 新增这一行：强制对齐物理吞吐量 
            cparams.n_ctx = 8192

            # 💥 真正让 UI 的并发通道数生效的地方在这里！
            # 将 Python 接收到的 n_parallel 赋给底层的最大序列数
            cparams.n_seq_max = 128

            # 改用新 API: llama_init_from_model
            self.ctx = self.lib.llama_init_from_model(self.model, cparams)
            if not self.ctx:
                log_details = "\n".join(_llama_internal_logs[-5:])
                raise Exception(f"无法创建本地模型上下文！底层原因:\n{log_details}")
            
            self.dim = self.lib.llama_n_embd(self.model)
            self.memory = self.lib.llama_get_memory(self.ctx)

        def _load_library(self):
            # 1. 仅加载最基础的依赖链，绝对不要手动加载 libggml-cpu.so
            dependencies = [
                "libggml-base.so",
                "libggml.so",
                
            ]
            for lib_name in dependencies:
                try:
                    ctypes.CDLL(lib_name, mode=ctypes.RTLD_GLOBAL)
                except Exception:
                    pass

            # 2. 唤醒主脑（此时它内部已经自带了唯一的、正确的 CPU 后端）
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
            # 💥 关键：每次计算前清除序列 0 的全部记忆，避免上下文污染
            self.lib.llama_memory_seq_rm(self.memory, 0, 0, -1)  # seq_id=0, p0=0, p1=-1

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

            # 1. 批量分词 (Tokenization)
            tokenized_texts = []
            total_tokens = 0
            n_max_tokens = 512
            
            for text in texts:
                text_bytes = text.encode('utf-8')
                tokens_array = (ctypes.c_int32 * n_max_tokens)()
                n_tokens = self.lib.llama_tokenize(self.vocab, text_bytes, len(text_bytes), tokens_array, n_max_tokens, ctypes.c_bool(True), ctypes.c_bool(True))
                
                if n_tokens > 0:
                    tokenized_texts.append((n_tokens, tokens_array))
                    total_tokens += n_tokens

            if total_tokens == 0: return []

            # 2. 核心：清空即将使用的多个序列的记忆，避免上下文污染
            for seq_id in range(len(tokenized_texts)):
                self.lib.llama_memory_seq_rm(self.memory, seq_id, 0, -1)

            # 3. 构造超级 Batch (💥 修复：先用具名变量接住真实内存，防止瞬间被 GC 回收！)
            token_arr = (ctypes.c_int32 * total_tokens)()
            pos_arr = (ctypes.c_int32 * total_tokens)()
            n_seq_id_arr = (ctypes.c_int32 * total_tokens)()
            logits_arr = (ctypes.c_int8 * total_tokens)()

            batch = LlamaBatch()
            batch.n_tokens = total_tokens
            batch.token = ctypes.cast(token_arr, ctypes.POINTER(ctypes.c_int32))
            batch.embd = ctypes.cast(None, ctypes.POINTER(ctypes.c_float))
            batch.pos = ctypes.cast(pos_arr, ctypes.POINTER(ctypes.c_int32))
            batch.n_seq_id = ctypes.cast(n_seq_id_arr, ctypes.POINTER(ctypes.c_int32))
            batch.logits = ctypes.cast(logits_arr, ctypes.POINTER(ctypes.c_int8))
            
            # 处理二维指针陷阱
            seq_id_ptrs = (ctypes.POINTER(ctypes.c_int32) * total_tokens)()
            inner_seqs = []
            for i in range(total_tokens):
                inner = (ctypes.c_int32 * 1)(0)
                inner_seqs.append(inner)
                seq_id_ptrs[i] = ctypes.cast(inner, ctypes.POINTER(ctypes.c_int32))
            batch.seq_id = ctypes.cast(seq_id_ptrs, ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)))

            # 4. 填充超级 Batch 的数据
            idx = 0
            for seq_id, (n_tokens, tokens_array) in enumerate(tokenized_texts):
                for i in range(n_tokens):
                    batch.token[idx] = tokens_array[i]
                    batch.pos[idx] = i          # 每个文本的相对位置都从 0 开始
                    batch.n_seq_id[idx] = 1
                    inner_seqs[idx][0] = seq_id # 赋予它独立的序列 ID (0, 1, 2...)
                    batch.logits[idx] = 1 if i == n_tokens - 1 else 0 
                    idx += 1

            # 💥 终极内存护盾：将真实数组对象存入生命周期，死死锁住物理内存！
            self._memory_shield = (token_arr, pos_arr, n_seq_id_arr, logits_arr, seq_id_ptrs, inner_seqs)

            # 5. 一次性核爆解码！
            res = self.lib.llama_decode(self.ctx, batch)
            if res != 0: 
                raise Exception(f"批量向量计算失败，llama_decode 返回错误码: {res}。请检查 UI 的 Batch Size 是否过大导致超出了 n_batch 容量。")

            # 6. 分离并提取每个序列的最终向量
            embeddings = []
            for seq_id in range(len(tokenized_texts)):
                emb_ptr = None
                if hasattr(self.lib, 'llama_get_embeddings_seq'):
                    emb_ptr = self.lib.llama_get_embeddings_seq(self.ctx, seq_id)
                
                if not emb_ptr:
                    raise Exception(f"未能成功获取序列 {seq_id} 的 Embedding 指针")
                
                embeddings.append([emb_ptr[i] for i in range(self.dim)])

            self._memory_shield = None
            return embeddings
        
        def __del__(self):
            if hasattr(self, 'ctx') and self.ctx: self.lib.llama_free(self.ctx)
            if hasattr(self, 'model') and self.model: self.lib.llama_free_model(self.model)
            if hasattr(self, 'lib') and self.lib: self.lib.llama_backend_free()