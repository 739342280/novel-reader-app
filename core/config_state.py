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
                "**【角色设定】**\n"
                "你是一个细心的“追文助手”，擅长捕捉作者的文字留白和情绪张力。\n\n"
                "**【输出要求：严格按以下5点输出，总字数控制在400字左右，排版清爽】**\n"
                "1. 🎯 **核心概括**：一句话说明本章剧情爆点或核心推进。\n"
                "2. 🗺️ **情节脉络**：\n"
                "   - [起因]：...\n"
                "   - [转折]：...\n"
                "   - [结果]：...\n"
                "3. 🎭 **人物弧光**：指出本章谁的心态发生了最关键的转变（格式：XX：从...到...）。\n"
                "4. ✍️ **高光笔触**：摘录本章最绝的一句描写或对话（注意：请直接使用普通中文双引号“”，严禁使用 Markdown 的单反引号 ` 或代码块包裹文字），并用半句话点评为何精彩。\n"
                "5. 🪝 **悬疑钩子**：本章结尾留下了什么迫在眉睫的悬念？\n\n"
                "（注：严禁评价剧情“好不好看”，只做客观且精准的梳理）"
            ),
            # 人物提示词默认值
            "prompt_char": (
                "请提取本章【最具存在感、对剧情有实际推动的 3-5 个人物】。\n\n"
                "**【输出要求：过滤无用路人，极致精简，总字数300字以内】**\n"
                "请严格按照以下“情报卡片”格式单行输出：\n\n"
                "- **[人物名]**（阵营/身份）：【当前状态】——【本章核心动作/态度】。与主角关系：xxx。\n"
                "- **[人物名]**（阵营/身份）：...\n\n"
                "（注：严禁脑补未发生的情节，只总结本章信息）"
            ),
            # 人物+ 专属提示词
            "prompt_char_pro": "你现在拥有上帝视角（仅限已读章节）。请结合【历史档案】与【本章表现】，对本章核心人物进行深度剖析。\n\n**【输出要求：拒绝长篇大论，追求极致精炼与深刻】**\n请按以下结构输出，每个角色单独成段，总字数严格控制在800字以内：\n\n1. **[人物姓名]：【一句话定调其本章命运或状态】**\n2. **命运轨迹（历史呼应）**：精简指出其本章行为与过往档案的联系。\n3. **核心动机与心理**：一针见血地指出其隐藏在行为背后的真正欲望或恐惧。\n\n最后，用一段不超过150字的**【群像暗流】**，总结本章这几个人物交锋背后的政治本质或时代缩影。",
            # 伏笔提示词默认值
            "prompt_clue": (
                "请像侦探一样，找出本章文本中看似不起眼、但极可能埋下伏笔的细节（如：反常的动作、戛然而止的对话、特写的物件、微妙的环境烘托）。\n\n"
                "**【输出要求：宁缺毋滥，最多只提取 3 个最核心的疑似伏笔，总字数300字以内】**\n"
                "请严格按以下格式输出：\n\n"
                "🔍 **【反常细节】**：“（这里必须一字不差地摘录原文片段）”\n"
                "💡 **【暗流推测】**：一针见血地指出这可能暗示了什么后文走向，或暴露了什么隐藏逻辑。\n\n"
                "（注：如果本章属于平铺直叙的过渡章，没有明显伏笔，请直接回复“本章未见明显伏笔。”不要牵强附会。）"
            ),
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
            keys_to_load = ["url", "key", "model", "prompt", "prompt_char", "prompt_char_pro", "prompt_clue", 
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