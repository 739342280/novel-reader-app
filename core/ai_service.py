import urllib.request
import urllib.error
import json

class AIService:
    _session = None

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
            # 💥 工业级重试机制：应对 10054 强迫关闭和 429 大厂限流
            # 如果请求失败，自动等待 0.5s, 1s, 2s... 并最多重试 5 次
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
        if config.get("embed_mode") == "本地模型":
            raise NotImplementedError("本地算力引擎暂未指定，请先在云端 API 模式下进行联调测试！")
            
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
        
        # 💥 使用自带重试策略的长连接池发起请求
        session = cls.get_session()
        
        for payload in payloads_to_try:
            data_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            try:
                # 注意：这里改用 session.post，而不是 requests.post
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
                # urllib3 的重试机制会在底层尝试 5 次，如果 5 次都失败（或者严重网络断开），才会抛出到这里
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