---
title: 环境变量
description: 环境变量管理 API — 列表、创建、删除。
---

## 列出环境变量

```
GET /projects/{id}/env-vars
```

**示例：**

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/env-vars
```

**响应：**

```json
{
  "data": [
    {
      "id": 10,
      "project_id": 1,
      "key": "DATABASE_URL",
      "value": "••••••••",
      "is_secret": true,
      "created_at": "2026-02-15T10:00:00+00:00",
      "updated_at": "2026-02-15T10:00:00+00:00"
    },
    {
      "id": 11,
      "project_id": 1,
      "key": "SITE_TITLE",
      "value": "My Blog",
      "is_secret": false,
      "created_at": "2026-02-15T10:01:00+00:00",
      "updated_at": "2026-02-15T10:01:00+00:00"
    }
  ]
}
```

:::note
标记为 `is_secret: true` 的环境变量，其值会被遮蔽显示为 `••••••••`。
:::

---

## 创建环境变量

```
POST /projects/{id}/env-vars
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | string | 是 | 变量名称 |
| `value` | string | 是 | 变量值 |
| `is_secret` | boolean | 否 | 是否为敏感值（默认 `false`） |

**示例：**

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "API_KEY", "value": "sk-abc123", "is_secret": true}' \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/env-vars
```

**响应：** `201 Created`

```json
{
  "data": {
    "id": 12,
    "project_id": 1,
    "key": "API_KEY",
    "value": "••••••••",
    "is_secret": true,
    "created_at": "2026-02-19T10:00:00+00:00",
    "updated_at": "2026-02-19T10:00:00+00:00"
  }
}
```

:::caution
同一项目中不能有重复的变量名称。如果 key 已存在，将返回 `409 Conflict` 错误。
:::

---

## 删除环境变量

```
DELETE /projects/{id}/env-vars/{var_id}
```

**示例：**

```bash
curl -X DELETE \
  -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu1.metavm.tech/api/v1/public/projects/1/env-vars/12
```

**响应：** `204 No Content`

:::note
删除环境变量后，需要重新部署项目才能使更改生效。
:::
