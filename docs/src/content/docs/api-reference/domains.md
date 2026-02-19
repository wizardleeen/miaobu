---
title: 域名
description: 自定义域名管理 API — 添加、验证、删除域名。
---

## 列出域名

```
GET /projects/{id}/domains
```

**示例：**

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/domains
```

**响应：**

```json
{
  "data": [
    {
      "id": 5,
      "project_id": 1,
      "domain": "blog.example.com",
      "is_verified": true,
      "ssl_status": "active",
      "esa_status": "online",
      "active_deployment_id": 42,
      "auto_update_enabled": true,
      "created_at": "2026-02-10T10:00:00+00:00",
      "verified_at": "2026-02-10T10:15:00+00:00"
    }
  ]
}
```

---

## 添加域名

```
POST /projects/{id}/domains
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `domain` | string | 是 | 自定义域名 |

**示例：**

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"domain": "blog.example.com"}' \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/domains
```

**响应：** `201 Created`

```json
{
  "data": {
    "id": 5,
    "domain": "blog.example.com",
    "is_verified": false,
    "ssl_status": "pending",
    "verification_token": "miaobu-verify-abc123...",
    "cname_target": "cname.metavm.tech",
    ...
  }
}
```

添加域名后，需要在 DNS 服务商配置以下记录：

1. **TXT 记录**（所有权验证）：
   - 名称：`_miaobu-verification.blog.example.com`
   - 值：返回的 `verification_token`

2. **CNAME 记录**（流量路由）：
   - 名称：`blog.example.com`
   - 值：`cname.metavm.tech`

配置完成后调用验证接口。

---

## 验证域名

```
POST /projects/{id}/domains/{domain_id}/verify
```

验证 DNS 配置并自动配置边缘网络和 SSL 证书。

**示例：**

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/domains/5/verify
```

:::note
验证过程会检查 TXT 和 CNAME 记录。SSL 证书将自动签发，通常需要 5-30 分钟。
:::

---

## 删除域名

```
DELETE /projects/{id}/domains/{domain_id}
```

删除自定义域名及相关的边缘网络资源。

**示例：**

```bash
curl -X DELETE \
  -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/domains/5
```

**响应：** `204 No Content`
