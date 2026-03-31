# 小宇宙播客转文字

基于 FastAPI 的音视频转文字工具，支持小宇宙、Bilibili、YouTube。

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 启动服务

双击运行：
```
启动.bat
```

或手动启动：
```bash
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. 使用浏览器访问

```
http://localhost:8000/frontend/index.html
```

## 项目结构

```
.
├── app/
│   ├── api/v1/          # API 路由
│   │   ├── tasks.py     # 任务管理 API
│   │   └── transcribe.py # 转录 API
│   ├── schemas/         # 数据模型
│   ├── services/        # 业务逻辑
│   ├── config.py        # 配置
│   └── main.py          # FastAPI 入口
├── core/                # 核心功能
│   ├── audio_processor.py  # 音频处理
│   ├── downloader.py       # 音视频下载
│   └── transcriber.py      # 语音识别
├── frontend/            # 前端页面
├── utils/               # 工具函数
│   └── export_utils.py  # 导出功能
├── data/                # 数据文件
├── temp/                # 临时文件
├── requirements.txt     # 依赖
├── .env                 # 配置
├── 启动.bat             # 启动脚本
└── README.md            # 本文件
```

## 配置

### 1. 复制环境变量模板

```bash
cp .env.example .env
```

Windows 用户手动复制：
```
复制 .env.example 文件并重命名为 .env
```

### 2. 配置 Whisper 模型（可选）

编辑 `.env` 文件中的 Whisper 配置：

```bash
# Whisper 模型大小: tiny, base, small, medium, large
WHISPER_MODEL_SIZE=medium

# 运行设备: cpu 或 cuda
WHISPER_DEVICE=cpu

# 计算类型: int8 或 float16
WHISPER_COMPUTE_TYPE=int8
```

### 3. 配置火山引擎 DeepSeek API（可选，用于语义纠错和说话人分离）

1. 在 [火山引擎控制台](https://console.volcengine.com/) 获取 API Key
2. 加密 API Key：
```bash
python -m utils.encryption "your-api-key-here"
```
3. 将输出的加密字符串填入 `.env`：
```bash
VOLCENGINE_API_KEY_ENC=加密后的字符串
VOLCENGINE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
VOLCENGINE_MODEL_NAME=ep-xxxxxxxxxxxxx  # 你的模型接入点 ID
```

**注意**：如果不配置火山引擎 API，转录功能仍然可用，但不会进行语义纠错和说话人分离。

## 处理流程

1. **提交任务**：前端发送链接到后端
2. **下载音频**：从平台下载音视频
3. **音频处理**：转换为标准格式
4. **语音识别**：使用 Whisper 转录
5. **导出文件**：生成 SRT/VTT/MD/TXT

## 常见问题

### Q: 首次启动慢
A: 首次需要下载 Whisper 模型（约 150MB-1.5GB），请耐心等待

### Q: 转录速度慢
A: 使用 CPU 推理较慢，可尝试更小的模型（如 tiny/base）

### Q: 如何停止服务
A: 关闭 API 服务窗口（按 Ctrl+C）

## License

MIT
