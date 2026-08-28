# 前端设置

本项目采用 Vite + React SPA，因为前端是一个内部工具，主要需求是快速迭代、带鉴权的应用流程，以及与 FastAPI 后端之间简洁的对接。我们不需要 Next.js 所擅长的服务端渲染、SEO 或全栈路由等额外能力。

## 初始化（从空的 `frontend/` 开始）

```bash
cd frontend
pnpm create vite . --template react-ts
pnpm install
pnpm add react-router-dom
pnpm add -D tailwindcss @tailwindcss/vite
pnpm dlx shadcn@latest init
```

鉴权不需要额外依赖：`src/auth/` 通过 `fetch` 调用后端的 JWT 接口。设置好 `VITE_API_BASE_URL`，应用即可连通。

## 运行

```bash
cd frontend
pnpm install
pnpm dev
```

## 检查

```bash
pnpm tsc --noEmit
pnpm lint
```
