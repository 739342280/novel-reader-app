# core/chunker.py

class NovelChunker:
    def __init__(self, chunk_size=500, overlap=50):
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