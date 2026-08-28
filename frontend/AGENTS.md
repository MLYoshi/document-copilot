# 前端 — 开发规范

这是 Document Copilot 的 React SPA。请先阅读 [../AGENTS.md](../AGENTS.md)——通用构建规范在那里。本文件补充前端特有的约定。

## 技术栈

- **纯 React SPA**（Vite + TypeScript，严格模式）。**不是 Next.js** —— 不要提议 Next、SSR、服务端组件或基于文件的路由。
- **Tailwind CSS** 负责样式。不使用 CSS modules、styled-components、Emotion 或 `.module.css` 文件编写组件样式。全局主题变量放在 `src/index.css`。
- **shadcn/ui** 提供 UI 基础组件。用 `pnpm dlx shadcn@latest add <name>` 添加组件 —— 不要手写 shadcn 已经提供的东西。
- **React Router** 负责路由。
- **自建 `src/auth/` 模块**处理认证（邮箱 + 密码，对接后端的 JWT 接口 —— 不使用第三方认证 SDK，不接 OAuth 提供方）。

## 包管理器

**只用 `pnpm`。** 不要用 `npm install` 或 `yarn add`。锁文件是 `pnpm-lock.yaml`。如果出现 `package-lock.json` 或 `yarn.lock`，那是 bug —— 直接删掉。

**最低发布时长：7 天。** 通过 `.npmrc` 配置（`minimum-release-age=10080` 分钟）。pnpm 会拒绝安装发布时间不足 7 天的版本。这用于防御域名仿冒 / 发布包投毒攻击 —— 这类攻击中，热门包的恶意版本上线后几小时内就会被大量拉取。

如果确实需要某个刚发布的包（例如我们已在使用的依赖发布了紧急安全修复），请针对单次安装做覆盖，并在提交信息中说明理由 —— 不要调低全局阈值。

## 依赖策略

通用策略见 [../AGENTS.md](../AGENTS.md)。前端补充如下：

- **HTTP：** 通过 `src/lib/http.ts` 中的轻量客户端和 `src/lib/api.ts` 中的 `api` 单例使用原生 `fetch` API。**不用 axios、ky、got、superagent、redaxios。**
- **日期：** 使用原生 `Date` 和 `Intl.DateTimeFormat`。除非确实需要，否则不用 moment、dayjs、date-fns。
- **工具函数：** 使用原生 `Array` / `Object` / `Map` 方法。不用 lodash、ramda。
- **状态：** 优先 `useState` / `useReducer` / `useContext`。只有当确实痛的时候才引入外部状态库。
- **表单：** 优先原生 `<form>` + `FormData`。
- **校验：** 只有当确实需要在边界处做运行时校验时，才引入 schema 库。
- **UI 组件：** 通过 `pnpm dlx shadcn@latest add <name>` 使用 shadcn 基础组件。不要手写 shadcn 已经提供的东西。

添加包之前，先确认：

1. 是否有原生的浏览器或 TS/JS API 可以做到？
2. shadcn/ui 是否已经覆盖了这个需求？
3. 它是否体积小巧、维护良好，值得付出维护成本？

如果第 (3) 点成立，那就加上 —— 但要在提交信息中说明这个决定。

## 目录结构（构建过程中创建）

```text
frontend/
├── src/
│   ├── components/        # 应用组件。shadcn 基础组件放在 components/ui/ 下
│   ├── auth/              # 登录/注册接口调用（api.ts）、token 存储与刷新（auth.ts）、类型（types.ts）
│   ├── lib/               # 与框架无关的工具（http、api、env）
│   ├── pages/             # 路由级组件
│   ├── App.tsx            # 路由
│   ├── main.tsx
│   └── index.css          # Tailwind 指令 + 全局主题变量
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

保持 `import` 一致使用 `@/*` 别名（例如 `@/lib/api`、`@/components/ui/button`）。

## 代码风格（前端特有）

- **TypeScript 严格模式。** 除非别无选择，否则不用 `any`；优先使用 `unknown` 并做类型收窄。
- **小而可组合的函数与组件**胜过巧妙的抽象。三行相似的代码 > 一个过早的泛型。
- **一个组件一个文件。** 组件要保持在一屏之内读完的体量。
- **Tailwind 类名内联。** 不使用 CSS modules、styled-components、Emotion 或 `.module.css` 编写组件样式。全局变量放在 `src/index.css`。

## 配置

- 所有环境变量读取都通过单一的 `src/lib/env.ts` 模块，它在启动时校验必需的变量。绝不在组件中直接读 `import.meta.env.X`。
- 环境变量以 `VITE_` 为前缀（Vite 约定）。没有该前缀的变量不会暴露给客户端。

## 后端对接

- 通过 JSON 与独立的 Python 后端通信。URL 来自 `VITE_API_BASE_URL`。
- 始终使用 `@/lib/api` 中的 `api.get/post/put/patch/delete` —— 它负责 base URL、JSON、JWT bearer token、超时以及带类型的 `ApiError`（包含用于区分 CORS/网络错误与 HTTP 错误的 `isNetworkError` 标志）。
- 认证方式为邮箱 + 密码，换取后端签发的 JWT（`POST /auth/login`）。bearer token 由 `api` 客户端自动注入；绝不要通过组件 props 逐层传递 token。遇到 `401` 时，`src/auth/` 模块会刷新 access token，失败则回退到登录路由。

## 测试

**不写前端测试。** 不要创建 `*.test.ts` / `*.test.tsx` 文件，也不要引入测试运行器。我们通过浏览器手动验证前端，加上 `pnpm tsc --noEmit` 和 `pnpm lint`。如果你发现自己想用 vitest、Playwright 或 Cypress —— 停下来。这不是本项目要做的事。共享逻辑的正确性靠的是保持简单和良好的类型，而不是靠测试套件。

## 反模式（禁止事项）

- 在 `lib/env.ts` 之外直接读取 `import.meta.env.X`。
- 明明 `fetch` 就够用，却引入 HTTP 库。
- 在一个项目里混用多个客户端状态库（Zustand + Jotai + Redux）。
- 用 `any` 注解来屏蔽类型检查错误。
- 在 Tailwind 之外另起自定义 CSS 文件 / styled-components。
- 手写重复实现 shadcn 已有的基础组件。
- 引入 Next.js、SSR，或任何需要在 SPA 前面加 Node 服务器的框架。
