import urllib.request
import urllib.error
import json

class AIService:
    @staticmethod
    def stream_summary(config, chapter_text, on_chunk, on_complete, on_error, is_active=None):
        """
        核心的 AI 流式请求方法，完全脱离 UI 控件。
        is_active: 用于检测是否中途关闭了弹窗的回调函数
        """
        is_success = True
        has_real_data = False
        full_text = ""
        
        try:
            req_data = {
                "model": config["model"],
                "messages": [
                    {"role": "system", "content": config["prompt"]},
                    {"role": "user", "content": f"请总结以下内容：\n\n{chapter_text}"}
                ],
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
                    # 允许外部中断请求（如用户关掉弹窗）
                    if is_active and not is_active():
                        is_success = False
                        break

                    line = response.readline()
                    if not line:
                        break
                    
                    decoded_line = line.decode("utf-8").strip()
                    if not decoded_line:
                        continue
                        
                    if decoded_line.startswith("data: "):
                        data_str = decoded_line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data_json = json.loads(data_str)
                            delta = data_json["choices"][0].get("delta", {})
                            if "content" in delta:
                                has_real_data = True
                                content = delta["content"]
                                full_text += content
                                on_chunk(content) # 把增量文本回调给 UI
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
            elif is_success and has_real_data:
                on_complete(full_text)