# 測試覆蓋度：Imervue

測量日期：2026-10-28。數字來自這台 Windows 機器上的一次實測，不是估計，也不是只數檔案。

| 項目 | 內容 |
|---|---|
| 直譯器 | 3.14.4 |
| 直譯器說明 | 專案 .venv |
| 工具 | coverage 7.15.0，`coverage run --branch` |
| 測量範圍 | `Imervue` |
| 測試路徑 | `tests` |
| 命令 | `python -m coverage run --branch --source=Imervue -m pytest tests` |
| 敘述覆蓋 | 77.05%（60248 / 78192） |
| 分支覆蓋 | 66.31%（12683 / 19126） |
| 測試結果 | 14308 passed, 1431 skipped in 794.09s (0:13:14) |
| 耗時 | 804.7 秒 |

敘述覆蓋是執行到的敘述數除以全部敘述數。分支覆蓋是執行到的分支數除以全部分支數。兩者分開算，沒有把分支混進敘述百分比。

## 這次怎麼量

測量套件 `Imervue`。同倉庫的 `plugins/` 目錄如果不是這個套件的一部分，就不會進 source。

## 覆蓋較低的檔案

只列這次測量裡敘述覆蓋最低的檔案，最多 12 個。

| 檔案 | 敘述覆蓋 | 已覆蓋 / 敘述 |
|---|---:|---:|
| `Imervue/mcp_server/__main__.py` | 0.0% | 0 / 5 |
| `Imervue/gpu_image_view/view_state_init.py` | 9.52% | 12 / 126 |
| `Imervue/paint/brush_cursor.py` | 11.38% | 33 / 290 |
| `Imervue/gui/macro_manager_dialog.py` | 12.12% | 28 / 231 |
| `Imervue/gpu_image_view/view_mouse.py` | 12.9% | 12 / 93 |
| `Imervue/gui/main_window_layout.py` | 13.68% | 29 / 212 |
| `Imervue/paint/crop_tool.py` | 13.89% | 5 / 36 |
| `Imervue/paint/canvas_view.py` | 14.81% | 16 / 108 |
| `Imervue/paint/stroke_selection.py` | 14.93% | 10 / 67 |
| `Imervue/gui/annotation_destructive.py` | 15.07% | 22 / 146 |
| `Imervue/paint/welcome_overlay.py` | 15.09% | 16 / 106 |
| `Imervue/gui/annotation_drawing.py` | 15.13% | 46 / 304 |
