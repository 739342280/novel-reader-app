# core/config_state.py
import sys
import flet as ft
from data.storage import StorageManager

class ConfigStateMixin:
    """负责管理应用的所有持久化配置与 UI 默认状态"""
    
    def init_config_state(self):
        # --- UI 样式默认配置 ---
        self.font_size = 18
        self.line_height = 1.5           
        self.paragraph_spacing = 10      
        self.letter_spacing = 0.0  
        self.bg_color = "#FFFFFF"
        self.bg_image = None  
        self.reader_text_color = "#212121"
        self.font_family = None
        self.follow_system_theme = True
        self.manual_theme_mode = "light" 
        
        # --- AI 与引擎配置 ---
        self.ai_config = {
            "url": "https://api.deepseek.com/v1/chat/completions",
            "key": "",
            "model": "deepseek-chat",
            "prompt": (
                "请对以下小说章节内容进行深度总结。\n\n"
                "# 角色设定\n"
                "你是一个细心的“追文助手”，擅长捕捉作者的文字留白和情绪张力。\n\n"
                "# 总结维度\n"
                "1. **一句话概括**：用一句话说清这章讲了什么。\n"
                "2. **情节脉络**：\n"
                "   - 起因：\n"
                "   - 经过（转折点）：\n"
                "   - 结果：\n"
                "3. **人物弧光**：主角在这一章的心态变化曲线（例如：从愤怒 -> 冷静 -> 下定决心）。\n"
                "4. **文笔赏析**：指出本章最精彩的一句描写或对话。\n"
                "5. **悬疑/钩子**：本章结尾留下的悬念是什么？\n\n"
                "# 输出限制\n"
                "- 字数控制在300字以内。\n"
                "- 严禁评价剧情“好不好看”，只做客观梳理。"
            ),
            # 人物提示词默认值
            "prompt_char": "提取本章出现的所有人物，写出一段深度的人物梳理。用一句话标明他们的阵营、当前状态、以及与主角的关系。严禁脑补未发生的情节。",
            # 伏笔提示词默认值
            "prompt_clue": "找出本章看似不起眼的环境描写、对话停顿或异常行为，推测作者可能埋下的伏笔与线索。尽量精简干练。",
            "embed_mode": "云端 API",
            "embed_url": "https://api.deepseek.com/v1/embeddings",
            "embed_key": "",
            "embed_model": "text-embedding-3-small",
            "local_embed_path": "",
            "local_model_path": "", # 确保本地模型路径也在初始化里
            "top_k": 5,
            "n_gpu_layers": 10,     # 默认 10 层
            "n_ubatch": 512,        # 默认 512
            "build_batch_size": 15, # 默认 15
            "hardware_mode": "强制GPU模式", # 默认硬件模式
            "snack_duration": 3000
        }

    def _load_config_from_appdata(self):
        data = StorageManager.load_json("ai_config.json")
        if data:
            keys_to_load = ["url", "key", "model", "prompt", "prompt_char", "prompt_clue", 
                            "embed_mode", "embed_url", "embed_key", "embed_model", 
                            "local_embed_path", "local_model_path", "top_k", "build_batch_size", 
                            "n_parallel", "snack_duration", "hardware_mode", "n_gpu_layers", "n_ubatch"]
            for k in keys_to_load:
                if k in data: 
                    self.ai_config[k] = data[k]
            
            bg_c = data.get("bg_color")
            self.bg_color = bg_c if bg_c else "#FFFFFF"
            self.bg_image = data.get("bg_image")  
            self.reader_text_color = data.get("reader_text_color", "#212121")
            self.font_family = data.get("font_family")
            self.letter_spacing = data.get("letter_spacing", 0.0)
            
            self.follow_system_theme = data.get("follow_system_theme", True)
            self.manual_theme_mode = str(data.get("theme_mode", "light")).lower()
            
            if self.follow_system_theme:
                self.page.theme_mode = ft.ThemeMode.SYSTEM
            else:
                if "dark" in self.manual_theme_mode:
                    self.page.theme_mode = ft.ThemeMode.DARK
                else:
                    self.page.theme_mode = ft.ThemeMode.LIGHT
        else:
            self.page.theme_mode = ft.ThemeMode.SYSTEM

    def _save_config_to_appdata(self):
        data_to_save = self.ai_config.copy()
        data_to_save["bg_color"] = self.bg_color
        data_to_save["bg_image"] = self.bg_image  
        data_to_save["reader_text_color"] = self.reader_text_color
        data_to_save["font_family"] = self.font_family
        data_to_save["letter_spacing"] = self.letter_spacing
        
        data_to_save["follow_system_theme"] = self.follow_system_theme
        
        theme_str = str(self.page.theme_mode).lower()
        if "dark" in theme_str:
            data_to_save["theme_mode"] = "dark"
        elif "light" in theme_str:
            data_to_save["theme_mode"] = "light"
        else:
            data_to_save["theme_mode"] = "system"
        
        StorageManager.save_json("ai_config.json", data_to_save)