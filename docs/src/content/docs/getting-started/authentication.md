---
title: 身份认证
description: 了解如何创建和使用 API 令牌进行身份认证。
---

所有公开 API 请求都需要通过 `Authorization` 请求头进行身份认证。

## 令牌格式

秒部 API 令牌以 `mb_live_` 开头，总长度约 51 个字符：

```
mb_live_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCDEF
```

## 使用令牌

在每个 API 请求中添加 `Authorization` 请求头：

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://miaobu-api.metavm.tech/api/v1/public/user
```

## 创建令牌

### 通过控制台

1. 登录秒部控制台
2. 进入 **设置** 页面
3. 点击 **创建令牌**
4. 输入名称和可选的过期时间
5. 复制令牌（仅显示一次）

### 通过 API（需要 JWT）

如果你已有 JWT 令牌，也可以通过 API 创建：

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{"name": "CI/CD", "expires_in_days": 90}' \
  https://miaobu-api.metavm.tech/api/v1/tokens
```

## 令牌安全

- 令牌使用 SHA-256 哈希存储，服务端不保存明文
- 建议为不同用途创建独立的令牌
- 定期轮换令牌，设置合理的过期时间
- 如果令牌泄露，立即在控制台撤销

## 错误响应

### 令牌无效

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Invalid API token"
  }
}
```

### 令牌已过期

```json
{
  "error": {
    "code": "unauthorized",
    "message": "API token has expired"
  }
}
```
