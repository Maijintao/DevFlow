# DevFlow AI

DevFlow AI 面向 GitHub 仓库中的研发协作，项目包含 FastAPI 后端与 Next.js 前端。

## 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

后端健康检查地址为 `http://localhost:8000/health`。

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址为 `http://localhost:3000`。
