---
title: 项目类型
description: 秒部支持的三种项目类型 — 静态站点、Node.js 应用和 Python 应用。
---

秒部支持部署三种类型的项目。项目类型在导入仓库时自动检测，也可以手动指定。

## 静态站点 (`static`)

适用于：博客、文档站点、营销页面、单页应用（SPA）等前端项目。

**工作流程：**
1. 克隆代码 → 安装依赖 → 执行构建命令
2. 将构建产物（HTML/CSS/JS）上传到云端存储
3. 通过全球 CDN 分发，边缘网络直接提供服务

**关键配置：**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `install_command` | `npm install` | 依赖安装命令 |
| `build_command` | `npm run build` | 构建命令 |
| `output_directory` | `dist` | 构建输出目录 |
| `is_spa` | `true` | SPA 模式（所有路径返回 index.html） |
| `node_version` | `18` | Node.js 版本 |

**支持的框架：** React (Vite/CRA)、Vue、Svelte、Astro、Next.js (静态导出)、Nuxt (静态) 等。

---

## Node.js 应用 (`node`)

适用于：Express、Fastify、NestJS、Koa、Hapi 等 Node.js 后端应用。

**工作流程：**
1. 克隆代码 → 安装依赖 → 可选构建 → 打包
2. 上传到云端存储
3. 部署为云端函数，通过边缘网络路由请求

**关键配置：**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `install_command` | `npm install` | 依赖安装命令 |
| `build_command` | _(空)_ | 构建命令（如有 TypeScript 编译） |
| `start_command` | `node index.js` | 应用启动命令 |

**注意事项：**
- 应用必须监听 `PORT` 环境变量指定的端口（默认 `9000`）
- 设置 `NODE_ENV=production`

---

## Python 应用 (`python`)

适用于：FastAPI、Flask、Django 等 Python Web 应用。

**工作流程：**
1. 克隆代码 → 安装依赖到 `python_deps/` → 打包
2. 上传到云端存储
3. 部署为云端函数，通过边缘网络路由请求

**关键配置：**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `python_version` | `3.10` | Python 版本 |
| `start_command` | `uvicorn main:app --host 0.0.0.0 --port 9000` | 应用启动命令 |

**注意事项：**
- 应用必须监听端口 `9000`
- 使用 `requirements.txt` 管理依赖

---

## 自动检测

导入仓库时，秒部会自动分析 `package.json`（或 `requirements.txt`）来检测：

- **项目类型**：根据依赖判断是静态站点、Node.js 应用还是 Python 应用
- **框架**：识别 React、Vue、Express、FastAPI 等框架
- **构建命令**：根据包管理器（npm/pnpm/yarn）和框架推荐命令
- **输出目录**：根据框架推荐默认输出目录

你可以在导入时或项目设置中修改这些配置。
