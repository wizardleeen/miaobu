---
title: 项目
description: 项目相关 API 端点 — 创建、列表、查询、更新、删除。
---

## 创建项目

```
POST /projects
```

从 GitHub 仓库创建新项目。`repo` 是唯一必填字段，平台会尝试自动检测构建配置，但不一定准确——建议根据实际情况传入 `project_type`、`build_command` 等字段。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `repo` | string | 是 | GitHub 仓库，格式为 `owner/repo` |
| `branch` | string | 否 | 分支名称（默认使用仓库默认分支） |
| `root_directory` | string | 否 | 根目录（monorepo 支持） |
| `project_type` | string | 否 | 项目类型：`static`、`node`、`python`（自动检测） |
| `name` | string | 否 | 项目名称（默认使用仓库名） |
| `build_command` | string | 否 | 构建命令 |
| `install_command` | string | 否 | 安装命令 |
| `output_directory` | string | 否 | 输出目录（静态项目） |
| `node_version` | string | 否 | Node.js 版本 |
| `is_spa` | boolean | 否 | 是否为单页应用（静态项目） |
| `python_version` | string | 否 | Python 版本 |
| `start_command` | string | 否 | 启动命令（Node.js/Python 项目） |
| `python_framework` | string | 否 | Python 框架 |
| `environment_variables` | array | 否 | 环境变量列表，每项包含 `key`、`value`、`is_secret` |

**示例（最简）：**

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"repo": "user/my-blog"}' \
  https://miaobu-api.metavm.tech/api/v1/public/projects
```

**示例（自定义配置）：**

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "user/my-blog",
    "project_type": "static",
    "build_command": "pnpm run build",
    "install_command": "pnpm install",
    "environment_variables": [
      {"key": "API_URL", "value": "https://api.example.com"},
      {"key": "SECRET_KEY", "value": "s3cret", "is_secret": true}
    ]
  }' \
  https://miaobu-api.metavm.tech/api/v1/public/projects
```

**响应（`201 Created`）：**

```json
{
  "data": {
    "id": 1,
    "name": "my-blog",
    "slug": "my-blog",
    "project_type": "static",
    "github_repo_name": "user/my-blog",
    "github_repo_url": "https://github.com/user/my-blog",
    "default_branch": "main",
    "root_directory": "",
    "build_command": "npm run build",
    "install_command": "npm install",
    "output_directory": "dist",
    "is_spa": true,
    "node_version": "18",
    "python_version": null,
    "start_command": null,
    "default_domain": "my-blog.metavm.tech",
    "active_deployment_id": null,
    "created_at": "2026-02-25T10:00:00+00:00",
    "updated_at": "2026-02-25T10:00:00+00:00",
    "detected_framework": "vite",
    "detection_confidence": "high",
    "webhook_created": true,
    "deployment": {
      "id": 42,
      "status": "queued"
    }
  }
}
```

---

## 列出所有项目

```
GET /projects
```

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int | 页码 |
| `per_page` | int | 每页数量 |

**示例：**

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://miaobu-api.metavm.tech/api/v1/public/projects?page=1&per_page=10"
```

**响应：**

```json
{
  "data": [
    {
      "id": 1,
      "name": "my-blog",
      "slug": "my-blog",
      "project_type": "static",
      "github_repo_name": "user/my-blog",
      "github_repo_url": "https://github.com/user/my-blog",
      "default_branch": "main",
      "root_directory": "",
      "build_command": "npm run build",
      "install_command": "npm install",
      "output_directory": "dist",
      "is_spa": true,
      "node_version": "18",
      "python_version": null,
      "start_command": null,
      "default_domain": "my-blog.metavm.tech",
      "active_deployment_id": 42,
      "created_at": "2026-01-20T10:00:00+00:00",
      "updated_at": "2026-02-18T15:30:00+00:00"
    }
  ],
  "meta": {
    "page": 1,
    "per_page": 10,
    "total": 1,
    "total_pages": 1
  }
}
```

---

## 获取单个项目

```
GET /projects/{id}
```

**示例：**

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu-api.metavm.tech/api/v1/public/projects/1
```

**响应：**

```json
{
  "data": {
    "id": 1,
    "name": "my-blog",
    "slug": "my-blog",
    ...
  }
}
```

---

## 通过 slug 获取项目

```
GET /projects/slug/{slug}
```

**示例：**

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu-api.metavm.tech/api/v1/public/projects/slug/my-blog
```

---

## 更新项目

```
PATCH /projects/{id}
```

**请求体（仅传需要更新的字段）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 项目名称 |
| `build_command` | string | 构建命令 |
| `install_command` | string | 安装命令 |
| `output_directory` | string | 输出目录 |
| `root_directory` | string | 根目录（monorepo） |
| `is_spa` | boolean | 是否为单页应用 |
| `node_version` | string | Node.js 版本 |
| `python_version` | string | Python 版本 |
| `start_command` | string | 启动命令 |

**示例：**

```bash
curl -X PATCH \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"build_command": "pnpm run build", "install_command": "pnpm install"}' \
  https://miaobu-api.metavm.tech/api/v1/public/projects/1
```

---

## 删除项目

```
DELETE /projects/{id}
```

删除项目及其所有关联资源（部署、域名、环境变量、云端资源）。

:::caution[不可逆操作]
此操作不可撤销，所有部署和云端资源将被永久删除。
:::

**示例：**

```bash
curl -X DELETE \
  -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu-api.metavm.tech/api/v1/public/projects/1
```

**响应：** `204 No Content`
