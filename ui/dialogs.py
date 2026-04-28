import flet as ft
import asyncio
import threading
import time
# --- 新增的依赖导入 ---
import os
import sys
import shutil
import io
import zipfile
from datetime import datetime
from data.storage import StorageManager
# ---------------------
from core.ai_service import AIService

class DialogManager:
    
    @staticmethod
    def show_book_options_dialog(app, path, current_name):
        app.global_dialog.modal = False
        app.global_dialog.inset_padding = None
        app.global_dialog.content_padding = None
        
        rename_tf = ft.TextField(label="重命名书籍", value=current_name)

        def on_save(e):
            new_name = rename_tf.value.strip()
            if new_name and new_name != current_name:
                app.rename_book(path, new_name)
                app.show_snack_bar("✅ 书名已更新")
            app._close_dialog()

        def confirm_delete(e):
            app.remove_from_bookshelf(path)
            app._close_dialog()
            app.show_snack_bar(f"✅ 《{current_name}》已移出书架")

        async def on_export(e):
            app._close_dialog()
            await app.trigger_export_picker(path, current_name)

        export_btn = ft.ElevatedButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.DOWNLOAD), ft.Text("导出书籍到本地")], 
                alignment=ft.MainAxisAlignment.CENTER
            ),
            on_click=on_export,
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_50, color=ft.Colors.BLUE_900)
        )

        app.global_dialog.title = ft.Text("书籍管理", size=18, weight=ft.FontWeight.BOLD, color="onSurface")
        app.global_dialog.content = ft.Column([
            rename_tf,
            ft.Container(height=5),
            export_btn,
            ft.Container(height=5),
            ft.Text("注：移出书架不会删除原文件，导出则会另存一份副本", size=12, color=ft.Colors.GREY)
        ], tight=True) 
        
        app.global_dialog.actions = [
            ft.TextButton(content=ft.Text("保存名称"), on_click=on_save),
            ft.TextButton(content=ft.Text("移出书架"), style=ft.ButtonStyle(color=ft.Colors.RED), on_click=confirm_delete),
            ft.TextButton(content=ft.Text("取消"), on_click=lambda _: app._close_dialog())
        ]
        app._open_dialog()

    # ==========================================
    # --- 【新增】从 main.py 迁移过来的备份导出逻辑 ---
    # ==========================================
    @staticmethod
    async def export_app_data(app, e):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            suggested_name = f"小说智读备份_{timestamp}.zip"
            base_dir = StorageManager.get_base_dir()

            all_files = []
            for root, dirs, files in os.walk(base_dir):
                if 'models' in dirs:
                    dirs.remove('models')
                    
                for file in files:
                    all_files.append(os.path.join(root, file))
            
            total_files = len(all_files)
            if total_files == 0:
                app.show_snack_bar("⚠️ 没有可导出的数据")
                return
            
            # 使用 app.page.platform 准确识别，避免安卓被误判为 Linux
            platform_str = str(app.page.platform).lower()
            is_mobile_or_web = "android" in platform_str or "ios" in platform_str or "web" in platform_str
            
            if not is_mobile_or_web:
                # --- PC 端逻辑 ---
                save_path = await ft.FilePicker().save_file(
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["zip"],
                    file_name=suggested_name
                )
                
                if not save_path:
                    app.show_snack_bar("⚠️ 已取消导出")
                    return

                prog_bar = ft.ProgressBar(value=0, color=ft.Colors.BLUE, height=8, width=300)
                prog_text = ft.Text("正在打包写入硬盘...", size=13, color="onSurface")
                
                app.global_dialog.title = ft.Text("正在导出备份", size=18, weight=ft.FontWeight.BOLD)
                app.global_dialog.content = ft.Column([
                    ft.Container(height=10), prog_bar, prog_text, ft.Container(height=10)
                ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                app.global_dialog.actions = []
                app.page.update()

                with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for i, abs_path in enumerate(all_files):
                        rel_path = os.path.relpath(abs_path, base_dir)
                        zipf.write(abs_path, rel_path)
                        
                        if i % max(1, total_files // 20) == 0 or i == total_files - 1:
                            prog_bar.value = (i + 1) / total_files
                            prog_text.value = f"正在写入硬盘... {i+1} / {total_files}"
                            app.page.update()
                            await asyncio.sleep(0.01)

                app.show_snack_bar("✅ 应用数据已完整导出到本地")
                app._close_dialog()

            else:
                # --- 移动端逻辑 (Android/iOS) ---
                prog_bar = ft.ProgressBar(value=0, color=ft.Colors.BLUE, height=8, width=300)
                prog_text = ft.Text("正在内存中构建数据包...", size=13, color="onSurface")
                
                app.global_dialog.title = ft.Text("正在导出备份", size=18, weight=ft.FontWeight.BOLD)
                app.global_dialog.content = ft.Column([
                    ft.Container(height=10), prog_bar, prog_text, ft.Container(height=10)
                ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                app.global_dialog.actions = []
                app.page.update()

                zip_buffer = io.BytesIO()

                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for i, abs_path in enumerate(all_files):
                        rel_path = os.path.relpath(abs_path, base_dir)
                        zipf.write(abs_path, rel_path)
                        
                        if i % max(1, total_files // 20) == 0 or i == total_files - 1:
                            prog_bar.value = (i + 1) / total_files
                            prog_text.value = f"正在构建数据包... {i+1} / {total_files}"
                            app.page.update()
                            await asyncio.sleep(0.01)

                zip_bytes = zip_buffer.getvalue()
                prog_bar.value = 1.0
                prog_text.value = "构建完成！请在系统弹窗中选择保存..."
                app.page.update()
                
                # Android 真正带着 src_bytes 去调用底层保存
                await ft.FilePicker().save_file(
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["zip"],
                    file_name=suggested_name,
                    src_bytes=zip_bytes
                )
                
                app.show_snack_bar("✅ 操作结束 (若未取消，备份已保存)")
                app._close_dialog()

        except Exception as ex:
            app.show_snack_bar(f"❌ 导出失败: {str(ex)}")
            app._close_dialog()


    # ==========================================
    # --- 【新增】从 main.py 迁移过来的备份恢复逻辑 ---
    # ==========================================
    @staticmethod
    async def import_app_data(app, e):
        try:
            prog_bar = ft.ProgressBar(value=0, color=ft.Colors.BLUE, height=8, width=300)
            prog_text = ft.Text("正在准备恢复环境...", size=13, color="onSurface")
            
            app.global_dialog.title = ft.Text("正在恢复备份", size=18, weight=ft.FontWeight.BOLD)
            app.global_dialog.content = ft.Column([
                ft.Container(height=10), prog_bar, prog_text, ft.Container(height=10)
            ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            app.global_dialog.actions = []
            app.page.update()

            files = await ft.FilePicker().pick_files(
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["zip"]
            )

            if files and len(files) > 0:
                zip_path = files[0].path
                if zip_path:
                    app.current_book_path = "" 
                    app.engine.chapters_info = []
                    
                    prog_text.value = "正在验证备份文件..."
                    app.page.update()

                    base_dir = StorageManager.get_base_dir()
                    
                    with zipfile.ZipFile(zip_path, 'r') as zipf:
                        zip_infos = zipf.infolist()
                        total_files = len(zip_infos)
                        
                        for i, zip_info in enumerate(zip_infos):
                            try:
                                target_path = os.path.join(base_dir, zip_info.filename)
                                if os.path.exists(target_path):
                                    import stat
                                    try:
                                        os.chmod(target_path, stat.S_IWRITE) 
                                    except Exception:
                                        pass 

                                zipf.extract(zip_info, base_dir)
                                
                            except PermissionError:
                                filename = zip_info.filename
                                raise Exception(f"文件正在被占用：{filename}\n请确保已关闭所有正在阅读的界面，并重试。")
                            
                            if i % max(1, total_files // 20) == 0 or i == total_files - 1:
                                prog_bar.value = (i + 1) / total_files
                                prog_text.value = f"正在还原文件... {i+1} / {total_files}"
                                app.page.update()
                                await asyncio.sleep(0.01)

                    app.show_snack_bar("✅ 数据已完美恢复，请重启应用生效")
                    app._load_config_from_appdata()
                    app._load_bookshelf()
                    app.refresh_bookshelf_ui()
                    
                    if sys.platform == "win32":
                        os.system("taskkill /F /IM llama-server.exe >nul 2>&1")

                else:
                    app.show_snack_bar("❌ 无法获取文件路径")
            else:
                app.show_snack_bar("⚠️ 已取消恢复")
            
            app._close_dialog()
            
        except Exception as ex:
            app.show_snack_bar(f"❌ 恢复失败: {str(ex)}")
            app._close_dialog()

   
    @staticmethod
    def show_global_settings_dialog(app, e):
        app.global_dialog.modal = False
        app.global_dialog.inset_padding = None
        app.global_dialog.content_padding = ft.padding.only(left=20, top=15, right=20, bottom=15)

        # 💥 【修改说明】此处修改了绑定事件，使用 lambda 和 page.run_task 调用本类的静态方法
        backup_row = ft.Row([
            ft.ElevatedButton(
                content=ft.Row([ft.Icon(ft.Icons.UPLOAD), ft.Text("导出备份", color="onSurface")]), 
                on_click=lambda e: app.page.run_task(DialogManager.export_app_data, app, e), 
                style=app.get_action_button_style()
            ),
            ft.ElevatedButton(
                content=ft.Row([ft.Icon(ft.Icons.DOWNLOAD), ft.Text("恢复备份", color="onSurface")]), 
                on_click=lambda e: app.page.run_task(DialogManager.import_app_data, app, e), 
                style=app.get_action_button_style()
            )
        ], alignment=ft.MainAxisAlignment.SPACE_AROUND)

        app.global_dialog.title = ft.Text("⚙️ 全局设置", size=18, weight=ft.FontWeight.BOLD, color="onSurface")
        app.global_dialog.content = ft.Column([
            ft.Text("数据安全", weight=ft.FontWeight.BOLD, size=14, color="onSurface"),
            ft.Text("本地备份包含所有书籍、阅读进度及 AI 总结数据", size=12, color=ft.Colors.GREY_500),
            ft.Container(height=5),
            backup_row
        ], tight=True)
        
        app.global_dialog.actions = [
            ft.TextButton(content=ft.Text("关闭", color="onSurface"), on_click=lambda _: app._close_dialog(), style=app.get_action_button_style())
        ]
        app._open_dialog()

    @staticmethod
    def show_changelog_dialog(app, e):
        app.global_dialog.modal = False
        app.global_dialog.inset_padding = None
        app.global_dialog.content_padding = ft.padding.only(left=20, top=24, right=4, bottom=24)

        log_text = """【v0.4.6】端云混合 RAG 架构启航
- (重构) 知识库控制中心：重塑原有的 AI 接口面板，全新引入三段式 Tab 视图。
- (新增) 向量引擎接入底盘：支持自由切换云端 Embedding 接口或本地大模型，为全书 RAG（检索增强生成）铺平道路。
- (新增) 本书知识库管理面板：支持动态查看与管控当前阅读书籍的向量索引状态。

【v0.4.5】功能扩展与交互优化
- (新增) 键盘快捷键控制：PC端支持左右键切换章节，上下键与空格键控制正文平滑滚动，大幅提升桌面端手感。
- (新增) 应用数据全局备份与恢复：支持一键导出所有 JSON 配置、书籍文件及 AI 总结记录，换机无忧。

【v0.4.4】上帝类代码结构重塑
- (优化) 对高达 1200 行的主控制器进行视觉层架构大扫除。划定六大专属业务防区 (Region)，彻底根治“找函数如大海捞针”的开发痛点，提升代码长效可维护性。
- (优化) 重塑生命周期承重墙 `load_chapter` 物理结构，防御潜在的时序竞态问题。

【v0.4.3】解析提速与架构打通
- (新增) TXT 目录结构缓存：首次解析书籍后将自动在本地生成目录索引。下次阅读同一本书时，将彻底跳过耗时的正则扫描流程，实现秒开阅读。
- (优化) 核心引擎解耦：支持从外部注入预解析数据，大幅降低 CPU 开销。
"""
        app.global_dialog.title = ft.Text("历史更新记录", size=18, weight=ft.FontWeight.BOLD, color="onSurface")
        
        app.global_dialog.content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Text(log_text, selectable=True),
                        padding=ft.padding.only(left=0, top=0, right=16, bottom=0)
                    )
                ], 
                scroll=ft.ScrollMode.AUTO
            ), 
            padding=0,
            height=400, width=500
        )
        
        app.global_dialog.actions = [
            ft.TextButton(
                content=ft.Text("关闭", color="onSurface"), 
                on_click=lambda _: app._close_dialog(), 
                style=app.get_action_button_style()
            )
        ]
        app._open_dialog()