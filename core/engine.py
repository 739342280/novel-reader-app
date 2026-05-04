# ==============================================================================
# 文件：core/engine.py[cite: 28]
# 职责：文本解析与小说结构化引擎 (Text Parsing & Structural Engine)[cite: 28]
# 
# 详细功能介绍：
# 1. 智能编码读取：内置多编码探测（UTF-8, GBK, UTF-16 等），确保导入各种老旧 TXT 文本时不会乱码报错[cite: 28]。
# 2. 章节正则扫描：使用高性能正则表达式匹配“第X章”、“卷X”等常见网文目录特征，瞬间将百万字长文切分为结构化的章节数组[cite: 28]。
# 3. 缓存秒开支持：提供 `load_with_cache` 方法，允许直接读取已固化的目录缓存，避开重复正则计算，实现万章小说的秒速打开[cite: 28]。
# 4. 按需内存提取：通过 `get_chapter_text` 方法，利用起止索引坐标精准从内存池中截取单章文本，极大地节省了运行内存[cite: 28]。
#
# 架构定位：底层数据清洗工厂。负责把无序的 TXT 纯文本，转化为 UI 和 AI 都能理解的“章节块”结构[cite: 28]。
# ==============================================================================
import os
import re

# ==========================================
# 核心引擎 (NovelEngine) - 支持目录缓存秒开
# ==========================================
class NovelEngine:
    def __init__(self):
        self.full_text_content = ""
        self.chapters_info = []
    
    def _read_file_content(self, path):
        """内部私有方法：处理各种编码读取文本内容"""
        content = None
        if os.path.exists(path) and os.path.getsize(path) == 0:
            raise ValueError("文件为空 (0字节)，请检查文件是否完整。")

        encodings = ['utf-8', 'gb18030', 'gbk', 'utf-16', 'utf-16-le', 'utf-16-be']
        for enc in encodings:
            try:
                with open(path, 'r', encoding=enc) as f: 
                    content = f.read()
                    if content: return content
            except: continue
                
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                if content: return content
        except: pass
            
        raise ValueError("编码解析失败，请检查文件格式是否为标准 TXT。")

    def load_with_cache(self, path, toc_data):
        """【新增】跳过正则扫描，直接利用缓存加载目录"""
        self.full_text_content = self._read_file_content(path)
        self.chapters_info = toc_data
        return self.chapters_info

    def load_and_analyze(self, path, progress_callback=None):
        """完整解析流程：读取 + 正则扫描"""
        content = self._read_file_content(path)
        self.full_text_content = content
        
        if progress_callback: progress_callback(0.1, "读取完成，开始正则匹配...")

        chap_pattern = re.compile(r'^\s*(?:第\s*[0-9零一二三四五六七八九十百千万]+\s*[章卷部]|卷\s*[0-9零一二三四五六七八九十百千万]+).*$', re.MULTILINE)
        chaps = list(chap_pattern.finditer(content))
        
        self.chapters_info = []
        total_chaps = len(chaps)
        
        if total_chaps == 0:
            self.chapters_info.append({'start': 0, 'end': len(content), 'title': "正文 (全文无章节)", 'volume': ""})
        else:
            current_vol = ""
            for i, m in enumerate(chaps):
                title = m.group().strip()
                start = m.start()
                
                if re.search(r'^\s*(?:第\s*[0-9零一二三四五六七八九十百千万]+\s*[卷部]|卷\s*[0-9零一二三四五六七八九十百千万]+)', title):
                    current_vol = title
                    
                end = chaps[i+1].start() if i+1 < len(chaps) else len(content)
                self.chapters_info.append({'start': start, 'end': end, 'title': title, 'volume': current_vol})
                
                if progress_callback and i % 1000 == 0:
                    progress_callback(0.1 + (i/total_chaps)*0.8, f"分析中: {title}")

        if progress_callback: progress_callback(1.0, "分析完毕。")
        return self.chapters_info

    def get_chapter_text(self, idx):
        if not self.chapters_info or idx < 0 or idx >= len(self.chapters_info):
            return ""
        ch = self.chapters_info[idx]
        return self.full_text_content[ch['start']:ch['end']]