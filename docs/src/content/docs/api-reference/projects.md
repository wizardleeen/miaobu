---
title: 项目
description: 项目相关 API 端点 — 列表、查询、更新、删除。
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
  "https://miaobu1.metavm.tech/api/v1/public/projects?page=1&per_page=10"
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
  https://miaobu1.metavm.tech/api/v1/public/projects/1
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
  https://miaobu1.metavm.tech/api/v1/public/projects/slug/my-blog
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
  https://miaobu1.metavm.tech/api/v1/public/projects/1
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
  https://miaobu1.metavm.tech/api/v1/public/projects/1
```

**响应：** `204 No Content`
