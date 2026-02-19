---
title: 快速开始
description: 用 5 分钟开始使用秒部公开 API。
---

秒部公开 API 让你通过编程方式管理项目、触发部署、配置域名等。

## 基本信息

- **Base URL**: `https://miaobu1.metavm.tech/api/v1/public`
- **认证方式**: Bearer Token（API 令牌或 JWT）
- **数据格式**: JSON

## 第一步：创建 API 令牌

1. 登录 [秒部控制台](https://miaobu.metavm.tech)
2. 进入 **设置** 页面
3. 在 **API 令牌** 区域点击 **创建令牌**
4. 输入名称，选择过期时间
5. 复制生成的令牌（仅显示一次）

## 第二步：发起第一个请求

使用你的 API 令牌获取用户信息：

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu1.metavm.tech/api/v1/public/user
```

返回示例：

```json
{
  "data": {
    "id": 1,
    "github_username": "yourname",
    "github_email": "you@example.com",
    "github_avatar_url": "https://avatars.githubusercontent.com/u/...",
    "created_at": "2026-01-15T08:00:00+00:00"
  }
}
```

## 第三步：列出你的项目

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu1.metavm.tech/api/v1/public/projects
```

返回示例：

```json
{
  "data": [
    {
      "id": 1,
      "name": "my-blog",
      "slug": "my-blog",
      "project_type": "static",
      "default_branch": "main",
      "created_at": "2026-01-20T10:00:00+00:00",
      "updated_at": "2026-02-18T15:30:00+00:00"
    }
  ],
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 1,
    "total_pages": 1
  }
}
```

## 下一步

- [身份认证](/getting-started/authentication/) — 了解令牌格式和认证方式
- [API 参考](/api-reference/) — 完整的 API 端点文档
