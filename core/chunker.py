# ==============================================================================
# 文件：core/chunker.py[cite: 30]
# 职责：滑动窗口文本分块器 (Sliding Window Text Chunker)[cite: 30]
# 
# 详细功能介绍：
# 1. 物理安全切割：将动辄数万字的单章小说文本，强行切分为符合大模型 Embedding 输入限制（如 512 token）的小尺寸文本块[cite: 30]。
# 2. 上下文防断裂：采用“滑动窗口”算法。通过设定 `overlap` (重叠余量)，强制相邻的两个文本块之间保留一部分重复文字（如 50 字）。
#    这一机制完美解决了关键线索（如人名、关键对话）刚好被一刀切断导致向量检索失效的致命问题[cite: 30]。
# 3. 极简防御逻辑：自动跳过并清理空文本，防止脏数据污染后续的向量数据库[cite: 30]。
#
# 架构定位：AI 建库前置流水线。它是小说文本从“供人阅读的形态”转化为“供 AI 计算的形态”的第一道工序[cite: 30]。
# ==============================================================================
class NovelChunker:
    def __init__(self, chunk_size=350, overlap=50):
        """
        滑动窗口分块算法
        :param chunk_size: 每个文本块的最大字符数
        :param overlap: 相邻文本块之间的重叠字符数，确保关键上下文不断裂
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []
            
        chunks = []
        text_len = len(text)
        start = 0
        
        while start < text_len:
            end = min(start + self.chunk_size, text_len)
            chunk = text[start:end].strip()
            
            if chunk:
                chunks.append(chunk)
                
            if end == text_len:
                break
                
            # 滑动窗口推进，保留 overlap 的重叠量
            start += (self.chunk_size - self.overlap)
            
        return chunks