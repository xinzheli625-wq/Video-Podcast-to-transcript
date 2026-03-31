# 小宇宙音频文字稿工具网站开发方案

## 项目概述
### 功能目标
开发一个在线工具网站，支持用户输入小宇宙播客链接，自动生成全文文字稿，具备音频提取、语音转文字、文本优化功能。

### 目标用户
- 非开发用户：通过网页界面直接使用功能

### 核心功能
1. 播客链接解析与音频提取
2. 多语言语音自动转录
3. 文本智能优化（去填充词、分段、纠错）
4. 文字稿导出（TXT）
5. 用户历史记录管理

## 技术架构
### 技术栈选择
| 模块 | 推荐技术 | 备选方案 |
|------|----------|----------|
| 前端 | React + TypeScript | Vue 3 + Vite |
| 后端 | Node.js (Express) | Python (FastAPI) |
| 数据库 | MongoDB | PostgreSQL |
| 缓存 | Redis | - |
| 容器化 | Docker | - |

### 系统架构图
```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   前端界面    │────▶│   后端服务    │────▶│   第三方API   │
│ (React)       │◀────│ (Node.js)     │◀────│ (33字幕/Cleanvoice)│
└───────────────┘     └───────────────┘     └───────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│ 用户交互      │     │ 业务逻辑处理  │     │ 音频转录/优化 │
└───────────────┘     └───────────────┘     └───────────────┘
                                              │
                                              ▼
                                     ┌───────────────┐
                                     │ 文字稿生成    │
                                     └───────────────┘
```

## 实现步骤
### 1. 需求分析与规划
- 详细功能列表确认
- 用户流程图设计
- API接口文档编写

### 2. 前端开发
```javascript
// 核心组件示例（React）
function AudioToTextConverter() {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState("");

  const handleSubmit = async () => {
    setStatus("processing");
    try {
      const response = await fetch("/api/process", {
        method: "POST",
        body: JSON.stringify({ url }),
        headers: { "Content-Type": "application/json" }
      });
      const data = await response.json();
      setResult(data.transcript);
      setStatus("completed");
    } catch (error) {
      setStatus("error");
    }
  };

  return (
    <div className="converter">
      <input
        type="text"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="输入小宇宙播客链接"
      />
      <button onClick={handleSubmit} disabled={status === "processing"}>
        {status === "processing" ? "处理中..." : "生成文字稿"}
      </button>
      {status === "completed" && (
        <div className="result">
          <MarkdownPreview value={result} />
          <button onClick={() => downloadFile(result)}>下载Markdown</button>
        </div>
      )}
    </div>
  );
}
```

### 3. 后端开发
```javascript
// 后端API示例（Express）
const express = require("express");
const app = express();
const axios = require("axios");
const { transcribeAudio, optimizeText } = require("./services/audioProcessor");

app.use(express.json());

// 音频处理API
app.post("/api/process", async (req, res) => {
  try {
    const { url } = req.body;
    
    // 1. 解析音频URL
    const audioUrl = await parsePodcastUrl(url);
    
    // 2. 下载音频文件
    const audioPath = await downloadAudio(audioUrl);
    
    // 3. 转录音频
    const rawText = await transcribeAudio(audioPath);
    
    // 4. 优化文本
    const optimizedText = await optimizeText(rawText);
    
    // 5. 保存记录
    await saveToDatabase({
      userId: req.user.id,
      url,
      transcript: optimizedText,
      createdAt: new Date()
    });
    
    res.json({ transcript: optimizedText });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// 启动服务器
app.listen(3000, () => console.log("Server running on port 3000"));
```

### 4. 第三方API集成
#### 33字幕API调用
```javascript
async function transcribeWith33Subs(audioPath) {
  const formData = new FormData();
  formData.append("file", fs.createReadStream(audioPath));
  
  const response = await axios.post("https://api.33subs.com/transcribe", formData, {
    headers: {
      "Authorization": `Bearer ${process.env.SUBS33_API_KEY}`,
      "Content-Type": "multipart/form-data"
    }
  });
  
  return response.data.transcript;
}
```

#### Cleanvoice文本优化
```javascript
async function optimizeWithCleanvoice(text) {
  const response = await axios.post("https://api.cleanvoice.ai/clean", {
    text,
    remove_fillers: true,
    remove_silence: true,
    split_sentences: true
  }, {
    headers: { "Authorization": `Bearer ${process.env.CLEANVOICE_API_KEY}` }
  });
  
  return response.data.clean_text;
}
```

## 部署指南
### Docker部署
```dockerfile
# Dockerfile
FROM node:16-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
```

### 环境变量配置
```
# .env文件
PORT=3000
MONGODB_URI=mongodb://localhost:27017/podcast_transcriber
SUBS33_API_KEY=your_33subs_api_key
CLEANVOICE_API_KEY=your_cleanvoice_api_key
JWT_SECRET=your_jwt_secret
```

## 项目进度规划
| 阶段 | 时间 | 任务 |
|------|------|------|
| 1 | 第1-2周 | 需求分析、技术选型、架构设计 |
| 2 | 第3-4周 | 前端开发、UI设计 |
| 3 | 第5-6周 | 后端开发、API集成 |
| 4 | 第7-8周 | 测试、优化、部署 |

## 风险与解决方案
| 风险 | 解决方案 |
|------|----------|
| 音频下载失败 | 实现重试机制，支持手动上传音频 |
| 转录准确率低 | 提供人工校对界面，支持文本编辑 |
| API调用限制 | 实现本地备份方案，使用Whisper模型 |
| 服务器负载高 | 引入Redis缓存，优化数据库查询 |