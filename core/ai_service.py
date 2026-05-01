import urllib.request
import urllib.error
import json
import os
# 💥 删除了这里的顶部导入，防止底层 C 库报错“火烧连营”

class AIService:
    _session = None
    # 单例模式存放本地引擎，防止多次加载撑爆手机内存
    _local_engine = None

    @classmethod
    def get_session(cls):
        """
        单例模式获取网络请求 Session。
        核心作用：复用 TCP/SSL 长连接，避免频繁握手被大厂 API 强行阻断 (10054)，提速 50% 以上。
        """
        if cls._session is None:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            cls._session = requests.Session()
            retries = Retry(
                total=5,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["POST"]
            )
            adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
            cls._session.mount('http://', adapter)
            cls._session.mount('https://', adapter)
        return cls._session

    @staticmethod
    def stream_chat(config, messages, on_chunk, on_complete, on_error, is_active=None):
        """
        支持多轮对话的 AI 流式请求方法，完全脱离 UI 控件。
        """
        is_success = True
        has_real_data = False
        full_text = ""
        
        try:
            req_data = {
                "model": config.get("model", "deepseek-chat"),
                "messages": messages,
                "stream": True
            }
            req = urllib.request.Request(
                config["url"], 
                data=json.dumps(req_data).encode("utf-8"), 
                headers={
                    "Content-Type": "application/json", 
                    "Authorization": f"Bearer {config['key']}",
                    "Accept": "text/event-stream" 
                }, 
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=60) as response:
                while True:
                    if is_active and not is_active():
                        is_success = False
                        break
                    
                    line = response.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith("data:"):
                        data_str = line_str[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data_json = json.loads(data_str)
                            delta = data_json["choices"][0].get("delta", {})
                            if "content" in delta:
                                has_real_data = True
                                content = delta["content"]
                                full_text += content
                                on_chunk(content) 
                        except Exception:
                            pass
        except urllib.error.HTTPError as ex:
            is_success = False
            error_msg = str(ex)
            try:
                error_body = ex.read().decode('utf-8')
                error_json = json.loads(error_body)
                if "error" in error_json and "message" in error_json["error"]:
                    error_msg += f"\n详细原因: {error_json['error']['message']}"
                elif "message" in error_json:
                    error_msg += f"\n详细原因: {error_json['message']}"
            except: pass
            on_error(f"\n\n❌ **接口请求失败**: {error_msg}\n\n请检查 API Key 是否填写正确、余额是否充足。")
        except Exception as ex:
            is_success = False
            on_error(f"\n\n❌ **网络异常**: {str(ex)}")
        finally:
            if is_success and not has_real_data:
                on_error("⚠️ 大模型未返回任何有效内容，请稍后重试。")
            elif is_success:
                on_complete(full_text)

    @classmethod
    def get_embedding(cls, config: dict, text: str) -> list[float]:
        """
        获取单段文本的 Embedding 向量。
        """
        # =========================================================
        # 本地建库分支逻辑
        # =========================================================
        if config.get("embed_mode") == "本地模型":
            model_path = config.get("local_model_path", "")
            
            if not model_path or not os.path.exists(model_path):
                raise Exception(f"【本地模式失败】未找到模型文件，请检查设置中的路径：\n{model_path}")
                
            try:
                from .local_inference import LocalEmbeddingEngine
                
                # 💥 获取 UI 配置：顺手把默认值改成 1，并获取刚存好的 n_ubatch
                n_parallel = config.get("n_parallel", 1)
                n_ubatch = config.get("n_ubatch", 512)
                hardware_mode = config.get("hardware_mode", "智能模式 (GPU优先)")

                # 💥 热重载检测：增加硬件模式变化的检测
                if cls._local_engine is not None:
                    old_parallel = getattr(cls._local_engine, 'n_parallel', 1)
                    old_ubatch = getattr(cls._local_engine, 'n_ubatch', 512)
                    old_hw = getattr(cls._local_engine, 'hardware_mode', "智能模式 (GPU优先)")
                    if old_parallel != n_parallel or old_ubatch != n_ubatch or old_hw != hardware_mode:
                        cls._local_engine = None # 参数改变，强制销毁旧引擎

                if cls._local_engine is None:
                    # 💥 将硬件模式传递给底层
                    cls._local_engine = LocalEmbeddingEngine(
                        model_path, 
                        n_parallel=n_parallel, 
                        n_ubatch=n_ubatch,
                        hardware_mode=hardware_mode
                    )
                    
                return cls._local_engine.get_embedding(text)
            except Exception as e:
                raise Exception(f"【本地推理崩溃】无法计算向量: {str(e)}")
            
        import requests
        
        url = config.get("embed_url", "").strip()
        key = config.get("embed_key", "").strip()
        model = config.get("embed_model", "").strip()
        
        if not url or not key:
            raise ValueError("云端 Embedding API 的 URL 或 Key 尚未配置。")
            
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        
        payloads_to_try = [
            {"model": model, "input": [{"type": "text", "text": text}]}, 
            {"model": model, "input": [text]},                           
            {"model": model, "input": text}                              
        ]
        
        error_details = ""
        last_status = 0
        response = None
        data = None
        
        session = cls.get_session()
        
        for payload in payloads_to_try:
            data_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            try:
                response = session.post(url, headers=headers, data=data_bytes, timeout=15)
                
                if response.status_code == 400:
                    last_status = 400
                    try:
                        err_json = response.json()
                        if "error" in err_json and "message" in err_json["error"]:
                            error_details = err_json["error"]["message"]
                    except Exception:
                        error_details = response.text
                    continue
                    
                response.raise_for_status() 
                data = response.json()
                break  
                
            except requests.exceptions.HTTPError as e:
                last_status = response.status_code
                try:
                    err_json = response.json()
                    if "error" in err_json and "message" in err_json["error"]:
                        error_details = err_json["error"]["message"]
                except Exception:
                    if not error_details:
                        error_details = str(e)
                
                if last_status != 400:
                    raise Exception(f"服务器拒绝请求 (HTTP {last_status}): {error_details}")
            except Exception as e:
                raise Exception(f"网络或底层请求抛出异常: {str(e)}")
                
        if data is None:
            raise Exception(f"所有参数格式均被服务器拒绝 (HTTP {last_status}): {error_details}")

        try:
            if "error" in data and isinstance(data["error"], dict) and "message" in data["error"]:
                raise Exception(f"API报错: {data['error']['message']}")
            if "code" in data and str(data["code"]) not in ["0", "200", "10000"]:
                raise Exception(f"API业务警告 (Code {data['code']}): {data.get('msg', data.get('message', '未知错误'))}")
                
            if "data" in data:
                if isinstance(data["data"], list) and len(data["data"]) > 0:
                    if "embedding" in data["data"][0]:
                        return data["data"][0]["embedding"]
                elif isinstance(data["data"], dict):
                    if "embedding" in data["data"]:
                        return data["data"]["embedding"]
            
            if "embedding" in data:
                return data["embedding"]
                
            raise Exception(f"找不到向量字段！大厂原始返回内容为: {json.dumps(data, ensure_ascii=False)[:300]}")
            
        except Exception as e:
            if "找不到向量字段" in str(e) or "API报错" in str(e):
                raise e
            raise Exception(f"解析 JSON 返回结构失败 ({type(e).__name__}: {str(e)}) | 服务器原文: {json.dumps(data, ensure_ascii=False)[:300]}")

    # =========================================================
    # 💡 唯一新增区域：供降维打击路线 (大批量文本建库) 调用的专属接口
    # =========================================================
    @classmethod
    def get_embeddings(cls, config: dict, texts: list[str]) -> list[list[float]]:
        """
        获取多段文本的 Embedding 向量矩阵。
        主要用于建库时的并发冲锋，榨干显卡算力。
        """
        if config.get("embed_mode") == "本地模型":
            model_path = config.get("local_model_path", "")
            
            if not model_path or not os.path.exists(model_path):
                raise Exception(f"【本地模式失败】未找到模型文件，请检查设置中的路径：\n{model_path}")
                
            try:
                from .local_inference import LocalEmbeddingEngine
                
                # 💥 获取参数
                n_parallel = config.get("n_parallel", 1)
                n_ubatch = config.get("n_ubatch", 512)

                # 💥 热重载检测
                if cls._local_engine is not None:
                    old_parallel = getattr(cls._local_engine, 'n_parallel', 1)
                    old_ubatch = getattr(cls._local_engine, 'n_ubatch', 512)
                    if old_parallel != n_parallel or old_ubatch != n_ubatch:
                        cls._local_engine = None

                if cls._local_engine is None:
                    # 💥 关键点：把 n_ubatch 传递给底层的 __init__
                    cls._local_engine = LocalEmbeddingEngine(
                        model_path, 
                        n_parallel=n_parallel, 
                        n_ubatch=n_ubatch
                    )
                    
                return cls._local_engine.get_embeddings(texts)
            except Exception as e:
                raise Exception(f"【本地推理崩溃】批量计算向量失败: {str(e)}")
        
        # ⚠️ 云端兜底策略：目前各大厂的 Batch Embedding 格式极其碎片化，
        # 为了保证现有云端通道的绝对稳定（防回归），这里采用最稳妥的单次循环方案。
        results = []
        for t in texts:
            results.append(cls.get_embedding(config, t))
        return results