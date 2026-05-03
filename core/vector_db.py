import sqlite3
import os
import struct
import math

class VectorDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        
        # 💥 战术标记：是否被迫开启“纯 Python 计算模式”
        self.use_pure_python = False

        try:
            # 试图探测并开启 C 语言扩展权限
            self.conn.enable_load_extension(True)
            
            so_path = os.path.abspath(os.path.join("assets", "libsqlite_vec.so"))
            if os.path.exists(so_path):
                self.conn.load_extension(so_path)
            else:
                import sqlite_vec
                sqlite_vec.load(self.conn)
                
            self.conn.enable_load_extension(False)
        except AttributeError:
            # 💥 核心拦截：检测到 Android serious_python 阉割了扩展权限，静默切换双轨制
            print("Detected restricted SQLite environment. Falling back to Pure Python Vector Search.")
            self.use_pure_python = True
        except Exception as e:
            print(f"Extension load failed, falling back to Pure Python: {e}")
            self.use_pure_python = True

    # ---- 基础二进制序列化工具 ----
    @staticmethod
    def _serialize_float32(vector: list[float]) -> bytes:
        return struct.pack(f"{len(vector)}f", *vector)

    @staticmethod
    def _deserialize_float32(blob: bytes) -> list[float]:
        count = len(blob) // 4
        return list(struct.unpack(f"{count}f", blob))

    def init_tables(self, dimension: int):
        with self.conn:
            if self.use_pure_python:
                # 💥 纯 Python 模式：只建立一张普通的 SQLite 表，将向量存为原生 BLOB
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS chunks_fallback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chapter_idx INTEGER,
                        chunk_text TEXT,
                        embedding BLOB
                    )
                """)
            else:
                # C 扩展模式：建立虚拟表
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
            
            # 💥 新增：创建元数据表，用来记录建库状态和总块数 (双轨制通用)
            self.conn.execute("CREATE TABLE IF NOT EXISTS vdb_meta (key TEXT PRIMARY KEY, value TEXT)")
    def set_meta(self, key: str, value: str):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO vdb_meta (key, value) VALUES (?, ?)", (key, value))

    def get_meta(self, key: str) -> str:
        try:
            cursor = self.conn.execute("SELECT value FROM vdb_meta WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.OperationalError:
            return None
    
    def insert_chunks(self, chunks_data: list[tuple[int, str, list[float]]]):
        with self.conn:
            if self.use_pure_python:
                # 【优化】预先在 Python 层面把数据组装好
                batch_data = [
                    (ch_idx, text, self._serialize_float32(emb)) 
                    for ch_idx, text, emb in chunks_data
                ]
                # 【优化】使用 executemany 进行底层的极速批量插入
                self.conn.executemany(
                    "INSERT INTO chunks_fallback (chapter_idx, chunk_text, embedding) VALUES (?, ?, ?)",
                    batch_data
                )
            else:
                # C 扩展模式：建立虚拟表
                # (这里的 virtual table 插入比较特殊，需要先获取 row_id，所以维持原样或参考 sqlite-vec 官方批量操作说明)
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
        if self.use_pure_python:
            # 💥 破釜沉舟：纯 Python 内存级防剧透相似度暴算
            query = "SELECT chapter_idx, chunk_text, embedding FROM chunks_fallback"
            params = []
            if max_chapter_idx is not None:
                query += " WHERE chapter_idx <= ?"
                params.append(max_chapter_idx)
            
            cursor = self.conn.execute(query, params)
            results = []
            
            # 预先计算查询向量的模长，节省数万次循环开销
            mag_q = math.sqrt(sum(a * a for a in query_embedding))
            if mag_q == 0: mag_q = 1e-9
            
            for row in cursor:
                ch_idx = row[0]
                text = row[1]
                emb = self._deserialize_float32(row[2])
                
                # 纯原生 Python 点积与模长计算
                dot = sum(a * b for a, b in zip(query_embedding, emb))
                mag_e = math.sqrt(sum(b * b for b in emb))
                if mag_e == 0: mag_e = 1e-9
                
                # 转换为 sqlite-vec 兼容的 distance 格式 (越小越近)
                sim = dot / (mag_q * mag_e)
                distance = 1.0 - sim
                
                results.append({
                    "chapter_idx": ch_idx,
                    "chunk_text": text,
                    "distance": distance
                })
            
            # 在内存中瞬间排序并切片
            results.sort(key=lambda x: x["distance"])
            return results[:top_k]

        else:
            # 原有的 sqlite-vec C语言极速检索路径
            query_vec = self._serialize_float32(query_embedding)
            
            if max_chapter_idx is not None:
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
            # 智能检测当前数据库内存在哪种格式的表
            cursor = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name='chunks_meta' OR name='chunks_fallback')")
            tables = [row[0] for row in cursor.fetchall()]
            
            if "chunks_fallback" in tables:
                cursor = self.conn.execute("SELECT COUNT(*) FROM chunks_fallback")
            elif "chunks_meta" in tables:
                cursor = self.conn.execute("SELECT COUNT(*) FROM chunks_meta")
            else:
                return {"is_indexed": False, "chunk_count": 0, "status": "none"}
                
            count = cursor.fetchone()[0]
            
            # 💥 新增：读取 Meta 表中的状态和总数
            status = "completed"
            total = count
            try:
                db_status = self.get_meta("status")
                if db_status: status = db_status
                
                db_total = self.get_meta("total_chunks")
                if db_total: total = int(db_total)
            except Exception: pass
            
            return {"is_indexed": count > 0, "chunk_count": count, "status": status, "total_chunks": total}
        except sqlite3.OperationalError:
            return {"is_indexed": False, "chunk_count": 0, "status": "none"}
            
    def clear_index(self):
        with self.conn:
            self.conn.execute("DROP TABLE IF EXISTS chunks_meta")
            self.conn.execute("DROP TABLE IF EXISTS vec_chunks")
            self.conn.execute("DROP TABLE IF EXISTS chunks_fallback")
            self.conn.execute("VACUUM")