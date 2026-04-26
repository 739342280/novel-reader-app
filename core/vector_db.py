import sqlite3
import os
import struct

class VectorDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.enable_load_extension(True)
        
        # 💥 双端探针加载机制：优先探查 assets 目录下是否有官方预编译包
        so_path = os.path.abspath(os.path.join("assets", "libsqlite_vec.so"))
        
        if os.path.exists(so_path):
            # 这是在 Android 环境下，强行加载 assets 里下载好的官方 .so
            try:
                self.conn.load_extension(so_path)
            except Exception as e:
                raise Exception(f"底层预编译 .so 挂载失败: {e}")
        else:
            # 这是在 Windows 环境下，正常使用 pip install 的扩展
            import sqlite_vec
            sqlite_vec.load(self.conn)
            
        self.conn.enable_load_extension(False)

    # 💥 手动实现序列化：在安卓上脱离了 sqlite_vec 的 Python 包层，需纯原生写入二进制
    @staticmethod
    def _serialize_float32(vector: list[float]) -> bytes:
        return struct.pack(f"{len(vector)}f", *vector)

    def init_tables(self, dimension: int):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks_meta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter_idx INTEGER,
                    chunk_text TEXT
                )
            """)
            self.conn.execute("DROP TABLE IF EXISTS vec_chunks")
            self.conn.execute(f"""
                CREATE VIRTUAL TABLE vec_chunks USING vec0(
                    embedding float[{dimension}]
                )
            """)

    def insert_chunks(self, chunks_data: list[tuple[int, str, list[float]]]):
        """批量插入：[(chapter_idx, chunk_text, embedding), ...]"""
        with self.conn:
            for chapter_idx, chunk_text, embedding in chunks_data:
                cursor = self.conn.execute(
                    "INSERT INTO chunks_meta (chapter_idx, chunk_text) VALUES (?, ?)",
                    (chapter_idx, chunk_text)
                )
                row_id = cursor.lastrowid
                
                self.conn.execute(
                    "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                    (row_id, self._serialize_float32(embedding))
                )

    def search(self, query_embedding: list[float], top_k: int = 5, max_chapter_idx: int = None) -> list[dict]:
        """
        余弦相似度检索
        :param max_chapter_idx: 时间线防剧透隔离。如果设置了该值，则绝对不返回未来的章节切块。
        """
        query_vec = self._serialize_float32(query_embedding)
        
        if max_chapter_idx is not None:
            # 绝对精准的“过滤前置” (Pre-filtering)
            cursor = self.conn.execute(
                """
                SELECT 
                    chunks_meta.chapter_idx, 
                    chunks_meta.chunk_text,
                    vec_distance_cosine(vec_chunks.embedding, ?) AS distance
                FROM chunks_meta
                LEFT JOIN vec_chunks ON vec_chunks.rowid = chunks_meta.id
                WHERE chunks_meta.chapter_idx <= ?
                ORDER BY distance
                LIMIT ?
                """,
                (query_vec, max_chapter_idx, top_k)
            )
        else:
            # 没有时间线限制时，走默认的虚拟表极速匹配
            cursor = self.conn.execute(
                """
                SELECT 
                    chunks_meta.chapter_idx, 
                    chunks_meta.chunk_text,
                    distance
                FROM vec_chunks
                LEFT JOIN chunks_meta ON chunks_meta.id = vec_chunks.rowid
                WHERE embedding MATCH ? AND k = ?
                ORDER BY distance
                """,
                (query_vec, top_k)
            )
            
        results = []
        for row in cursor.fetchall():
            results.append({
                "chapter_idx": row[0],
                "chunk_text": row[1],
                "distance": row[2]
            })
                
        return results

    def get_index_status(self) -> dict:
        try:
            cursor = self.conn.execute("SELECT COUNT(*) FROM chunks_meta")
            count = cursor.fetchone()[0]
            return {"is_indexed": count > 0, "chunk_count": count}
        except sqlite3.OperationalError:
            return {"is_indexed": False, "chunk_count": 0}
            
    def clear_index(self):
        with self.conn:
            self.conn.execute("DROP TABLE IF EXISTS chunks_meta")
            self.conn.execute("DROP TABLE IF EXISTS vec_chunks")
            self.conn.execute("VACUUM")