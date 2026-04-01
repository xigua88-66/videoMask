# 🚀 视频标注工具 - 编译指南

## 📋 功能完成清单

### ✅ 1. 任务列表状态同步刷新
- 从图片列表返回任务列表时，自动刷新视频合成状态标记
- 🎬 表示已合成视频，📁 表示未合成视频

### ✅ 2. 删除功能
**任务删除：**
- 📍 位置：任务列表页面
- 🔘 按钮：「删除选中任务」
- 🗑️ 功能：删除整个任务目录、相关视频文件、所有图片和标注数据
- 🔒 安全：双重确认对话框防止误删

**图片删除：**
- 📍 位置：图片列表页面
- 🔘 按钮：「删除选中图片」
- 🗑️ 功能：删除原始图片、标注图片、标注数据JSON文件
- 🔒 安全：双重确认对话框防止误删

## 🖥️ 编译指南

### 🍎 macOS 系统编译

```bash
# 1. 激活虚拟环境
source venv/bin/activate

# 2. 安装PyInstaller（如果还没安装）
pip install pyinstaller

# 3. 编译为独立应用程序
pyinstaller videoMask.spec --noconfirm

# 4. 编译后的应用位置
# dist/videoMask.app (macOS应用包)
```

**macOS特殊注意事项：**
- 生成的 `.app` 文件包含所有依赖
- 可直接双击运行，无需安装Python
- 支持拖拽到Applications文件夹安装

### 🪟 Windows 系统编译

**在Windows环境中：**

```cmd
# 1. 激活虚拟环境
env\Scripts\activate

# 2. 安装PyInstaller
pip install pyinstaller

# 3. 编译为独立可执行文件（Windows 专用 spec）
pyinstaller videoMask_windows.spec --noconfirm

# 4. 编译后的应用位置
# dist\videoMask.exe (Windows可执行文件)
```

**Windows特殊注意事项：**
- 生成的 `.exe` 文件包含所有依赖
- 可直接双击运行，无需安装Python
- 建议创建桌面快捷方式

### 📦 PyInstaller配置说明

当前推荐使用双 spec：
- `videoMask.spec`：macOS 打包
- `videoMask_windows.spec`：Windows 打包

示例（macOS）：
```python
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['app/main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyi_to_exe = EXE(
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='videoMask',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.icns',  # 如果有图标文件可取消注释
)

# macOS特有配置
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='videoMask.app',
        icon=None,  # 'icon.icns'
        bundle_identifier='com.example.videomask',
    )
```

### 🔧 编译过程包含的依赖

编译后的应用自动包含：
- ✅ **Python运行时** - 无需安装Python
- ✅ **PyQt6** - GUI框架
- ✅ **OpenCV** - 视频和图像处理
- ✅ **Pillow** - 中文标签渲染（防止视频合成文字乱码）
- ✅ **所有标准库** - json, os, sys等
- ✅ **应用代码** - 完整的功能实现

### 📊 编译文件大小预期

- **macOS**: ~150-200MB (.app包)
- **Windows**: ~120-150MB (.exe文件)
- **首次启动**: 可能需要3-5秒解压缓存

## 📝 日志输出位置

### 🖥️ 开发环境（源码运行）
```bash
# 日志直接输出到终端
source venv/bin/activate
python app/main.py
```

### 📦 编译后应用
**macOS:**
```bash
# 查看应用日志
Console.app > 搜索 "videoMask"
# 或在终端运行
/Applications/videoMask.app/Contents/MacOS/videoMask
```

**Windows:**
```cmd
# 方法1: 从命令行运行查看日志
videoMask.exe

# 方法2: 修改spec文件启用控制台
console=True  # 在videoMask.spec中修改此行
```

### 📋 日志内容说明

应用日志包含：
- 🚀 **启动信息** - 应用启动状态
- 🎯 **用户操作** - 点击、选择、编辑等操作
- 🔧 **功能执行** - 视频处理、图片保存等
- ❌ **错误信息** - 异常和错误详情
- 🎨 **调试信息** - 开发调试日志（DEBUG标记）

### 🔇 静默运行模式

如需要静默运行（无日志输出），修改spec文件：
```python
# 在videoMask.spec中设置
console=False,        # 隐藏控制台
debug=False,          # 关闭调试模式
```

然后在代码中移除所有 `print()` 语句。

## 🎯 使用建议

### 🔄 版本管理
- 建议为不同平台创建不同的发布版本
- 版本号可在 `app/main.py` 中的窗口标题中设置

### 📋 分发清单
**分发包应包含：**
- ✅ 编译后的应用文件 (.app/.exe)
- ✅ 用户手册（使用说明）
- ✅ 示例视频文件（可选）

### 🔍 测试建议
1. **功能测试** - 所有标注和视频合成功能
2. **删除测试** - 任务删除和图片删除功能
3. **兼容性测试** - 不同视频格式支持
4. **性能测试** - 大文件处理能力

## 🚨 重要提示

- 📱 **首次运行**：可能需要几秒钟初始化
- 🔒 **权限要求**：需要文件读写权限
- 🎥 **视频格式**：建议使用常见格式（MP4, AVI等）
- 💾 **存储空间**：确保有足够空间存储图片和视频
- 🗑️ **删除提醒**：删除操作不可撤销，请谨慎操作

编译完成后，应用即可独立运行，无需任何额外的Python环境或库安装！🎉