---
title: API 参考概述
description: 秒部公开 API 的通用约定、认证方式、错误格式和分页说明。
---

## Base URL

```
https://miaobu1.metavm.tech/api/v1/public
```

## 认证

所有请求都需要在 `Authorization` 请求头中提供 Bearer Token：

```
Authorization: Bearer YOUR_TOKEN
```

支持两种令牌类型：
- **API 令牌**：以 `mb_live_` 开头，通过控制台创建
- **JWT**：通过 GitHub OAuth 登录获取

## 响应格式

### 成功响应（单个资源）

```json
{
  "data": {
    "id": 1,
    "name": "my-project",
    ...
  }
}
```

### 成功响应（列表）

```json
{
  "data": [...],
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 42,
    "total_pages": 3
  }
}
```

### 错误响应

```json
{
  "error": {
    "code": "not_found",
    "message": "Project not found"
  }
}
```

常见错误代码：

| 状态码 | code | 说明 |
|--------|------|------|
| 400 | `bad_request` | 请求参数无效 |
| 401 | `unauthorized` | 认证失败或令牌过期 |
| 403 | `forbidden` | 无权访问该资源 |
| 404 | `not_found` | 资源不存在 |
| 409 | `conflict` | 资源冲突（如重复创建） |
| 422 | `validation_error` | 请求体校验失败 |
| 429 | `rate_limited` | 请求频率超限 |

## 分页

列表端点支持分页参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码（从 1 开始） |
| `per_page` | int | 20 | 每页数量（1-100） |

## 速率限制

响应头中包含速率限制信息：

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1708300800
```
