---
title: 部署
description: 部署相关 API 端点 — 列表、触发、取消、回滚、查看日志。
---

## 列出部署

```
GET /projects/{id}/deployments
```

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int | 页码 |
| `per_page` | int | 每页数量 |

**示例：**

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://miaobu1.metavm.tech/api/v1/public/projects/1/deployments?page=1&per_page=5"
```

**响应：**

```json
{
  "data": [
    {
      "id": 42,
      "project_id": 1,
      "commit_sha": "abc123def456...",
      "commit_message": "Update homepage",
      "commit_author": "developer",
      "branch": "main",
      "status": "deployed",
      "deployment_url": "https://my-blog.metavm.tech/",
      "build_time_seconds": 45,
      "error_message": null,
      "created_at": "2026-02-18T15:30:00+00:00",
      "deployed_at": "2026-02-18T15:31:00+00:00"
    }
  ],
  "meta": {
    "page": 1,
    "per_page": 5,
    "total": 12,
    "total_pages": 3
  }
}
```

---

## 获取单个部署

```
GET /projects/{id}/deployments/{deployment_id}
```

**示例：**

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/deployments/42
```

---

## 获取构建日志

```
GET /projects/{id}/deployments/{deployment_id}/logs
```

**示例：**

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/deployments/42/logs
```

**响应：**

```json
{
  "data": {
    "deployment_id": 42,
    "status": "deployed",
    "build_logs": "Cloning repository...\nInstalling dependencies...\nBuilding...\nDone!",
    "error_message": null
  }
}
```

---

## 触发部署

```
POST /projects/{id}/deployments
```

从 GitHub 仓库的最新提交触发一次新的部署。

**请求体（可选）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `branch` | string | 部署分支（默认为项目默认分支） |

**示例：**

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"branch": "main"}' \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/deployments
```

**响应：** `201 Created`

```json
{
  "data": {
    "id": 43,
    "project_id": 1,
    "commit_sha": "def789...",
    "commit_message": "Latest commit message",
    "branch": "main",
    "status": "queued",
    ...
  }
}
```

---

## 取消部署

```
POST /projects/{id}/deployments/{deployment_id}/cancel
```

取消一个正在排队或构建中的部署。

**示例：**

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/deployments/43/cancel
```

:::note
只能取消处于 `queued`、`cloning`、`building`、`uploading` 或 `deploying` 状态的部署。
:::

---

## 回滚部署

```
POST /projects/{id}/deployments/{deployment_id}/rollback
```

将项目回滚到指定的历史部署版本。

**示例：**

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/deployments/41/rollback
```

:::note
- 只能回滚到状态为 `deployed` 的部署
- 不能回滚到当前活跃的部署
- 回滚期间不能有其他正在进行的部署
:::
