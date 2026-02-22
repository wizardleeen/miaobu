"""
AI service for conversational project creation and modification.

Orchestrates a Claude tool-use loop: user message -> Claude -> tool calls -> results -> repeat.
Streams the entire interaction via SSE to the frontend.
"""
import asyncio
import json
import secrets
import traceback
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, Any, List, Optional

import anthropic
import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    User, Project, Deployment, DeploymentStatus,
    ChatSession, ChatMessage, EnvironmentVariable,
)
from .github import GitHubService
from .github_actions import trigger_build

settings = get_settings()

# --------------------------------------------------------------------------- #
# System prompt
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """You are Miaobu AI (秒部 AI), an intelligent assistant integrated into the Miaobu deployment platform. You help users create new web projects and modify existing ones.

## About Miaobu
Miaobu (秒部, a wordplay on 喵步 "cat steps") is a Vercel-like deployment platform that deploys GitHub repositories to the cloud. Users connect their GitHub account, import a repo, and Miaobu automatically builds and deploys it.

Supported project types:
- **Static sites** — React, Vue, Svelte, Astro, Next.js (static export), Vite, etc. Built and served via CDN.
- **Node.js backends** — Express, Fastify, NestJS, Koa, Hapi servers. Deployed as serverless functions.
- **Python backends** — FastAPI, Flask, Django servers. Deployed as serverless functions.
- **Manul apps** — Manul persistent applications with auto-generated REST APIs and object persistence. Deployed to the Manul server.

Each project gets a subdomain (e.g., `my-app.metavm.tech`). Custom domains are also supported. Deployments are triggered automatically on git push via webhooks. The platform auto-detects the framework, build commands, and output directory from the repository.

## Capabilities
You can:
- Create new GitHub repositories and scaffold complete web projects (React, Vue, Next.js, FastAPI, Flask, Express, etc.)
- Read and modify files in existing project repositories
- Create Miaobu projects from repositories and trigger deployments
- Update project settings (project type, build commands, etc.)
- List and inspect the user's existing projects
- Monitor deployments, read build logs, and automatically diagnose and fix build failures
- Manage environment variables (list, set, delete) for projects — useful for configuring API keys, database URLs, and other secrets

## Guidelines
1. Detect the user's language from their messages and respond in the same language (default: Chinese).
2. Generate clean, production-ready code with all necessary config files (package.json, tsconfig, vite config, etc.).
3. For new projects: create repo -> write all files -> create Miaobu project -> trigger deployment.
4. For modifications: read the relevant files first -> commit changes -> trigger deployment.
5. Always explain what you're doing at each step.
6. When creating a project, pick sensible defaults for build config based on the framework.
7. Keep file contents complete — never use placeholder comments like "// rest of code here".
8. Repository names should be lowercase with hyphens, no special characters.
9. Miaobu can only deploy web applications (static sites, Node.js servers, Python servers, Manul apps). If a user asks for something that can't run in a browser or as a web server (e.g., desktop apps, mobile apps, CLI tools, games with native dependencies), explain that Miaobu is a web deployment platform and offer to create a web-based alternative instead. For example, if asked for a "desktop HTTP client like Postman", build a web-based HTTP client that runs in the browser.

## Project Type Selection
- `static`: Frontend-only apps (React, Vue, Svelte, Astro, etc.) that compile to HTML/CSS/JS. Use this for ANY project that uses `vite`, `webpack`, `next export`, or similar bundlers to produce static files. This is the most common type.
- `node`: Node.js backend servers (Express, Fastify, NestJS, Koa, Hapi) that listen on a port. Only use this for actual server applications, NOT for frontend apps with `vite preview` or `next start`.
- `python`: Python web servers (FastAPI, Flask, Django).
- `manul`: Manul persistent applications. **Before writing or modifying Manul code, call `get_manul_guide` first** to load the language reference.
If you created a project with the wrong type, use `update_project` to change it before the next deployment.

## Build Failure Diagnosis & Auto-Fix
After committing code (via `commit_files`) that triggers a deployment:
1. Call `wait_for_deployment` to monitor the build until it completes.
2. If the deployment succeeds, inform the user with the live URL.
3. If the deployment fails:
   a. The wait result includes build logs and error message — analyze the error.
   b. Use `read_file` to examine the source files causing the failure.
   c. Use `commit_files` to push a fix (this auto-triggers a new deployment via webhook).
   d. Call `wait_for_deployment` again to verify the fix worked.
   e. Repeat up to 3 attempts. If still failing, explain the issue to the user.
4. Pushing a commit via `commit_files` auto-triggers deployment via webhook — do NOT call `trigger_deployment` afterward.
"""

# --------------------------------------------------------------------------- #
# Manul guide (loaded on demand via get_manul_guide tool)
# --------------------------------------------------------------------------- #

MANUL_GUIDE = """## Manul Language Guide

Manul is a persistent programming language. Its key features are:
- **Automatic object persistence** — creating an object with `val x = Foo(...)` automatically persists it; `delete x` removes it.
- **Automatic REST API generation** — service classes annotated with `@Bean` become REST endpoints.
- **Automatic search indexing** — `Index<K, V>` fields enable fast lookups.

### Project Structure
Manul projects use `.mnl` files organized in `src/`:
- `src/domain/` — Entity classes (persisted objects), enums, value classes
- `src/service/` — Service classes with `@Bean` (become REST API endpoints)
- `src/value/` — Value classes (immutable, embedded in entities)

No `package.json`, no build config files. Just `.mnl` source files. Build command is `manul build`, producing `target/target.mva`.

### Language Syntax

**Packages & imports:**
```
package domain
import domain.Product
```

**Entity classes** (persisted, have identity):
```
class Customer(
    @Summary
    var name: string,
    val email: string,
    password: string        // constructor-only param (not a field)
) {
    priv var passwordHash = secureHash(password, null)
    static val emailIdx = Index<string, Customer>(true, c -> c.email)

    fn checkPassword(password: string) -> bool {
        return passwordHash == secureHash(password, null)
    }
}
```
- `val` = immutable field, `var` = mutable field
- `priv` = private field
- `@Summary` = included in list/summary views
- Constructor parameters without `val`/`var` are constructor-only (not persisted fields)
- `static val` for static fields like indexes

**Value classes** (immutable, no identity, embedded):
```
value class Money(
    val amount: double,
    val currency: Currency
) {
    fn add(that: Money) -> Money {
        return Money(amount + that.getAmount(currency), currency)
    }
}
```

**Enums:**
```
enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
;
}

// Enum with fields and methods:
enum Currency(val rate: double) {
    YUAN(7.2) {
        fn label() -> string { return "元" }
    },
    DOLLAR(1) {
        fn label() -> string { return "美元" }
    }
;
    abstract fn label() -> string
}
```

**Child classes** (owned by parent, deleted when parent is deleted):
```
class Order(...) {
    class Item(
        val product: Product,
        val quantity: int
    )
}
// Create child: order.Item(product, 1) — automatically owned by `order`
```

**Indexes & queries:**
```
// Unique index
static val emailIdx = Index<string, Customer>(true, c -> c.email)
// Non-unique index
static val customerIdx = Index<Customer, Order>(false, o -> o.customer)
// Composite index
static val statusAndCreatedAtIdx = Index<OrderStatusAndTime, Order>(false, o -> OrderStatusAndTime(o.status, o.createdAt))

// Query methods
Customer.emailIdx.getFirst(email)       // returns T? (nullable)
Order.customerIdx.getAll(customer)      // returns T[]
Order.statusAndCreatedAtIdx.query(from, to)  // range query, returns T[]
```

**Service classes** (auto-generated REST endpoints):
```
@Bean
class ProductService {
    fn findProductByName(name: string) -> Product? {
        return Product.nameIdx.getFirst(name)
    }
}
```
- `@Bean` makes the class a singleton with auto-generated REST endpoints
- Each public method becomes a REST endpoint
- `@CurrentUser customer: Customer` injects the authenticated user

**Authentication:**
```
@Bean
internal class TokenValidator: security.TokenValidator {
    fn validate(token: string) -> any? {
        val s = Session.tokenIdx.getFirst(token)
        if (s != null && s!!.isValid())
            return s!!.customer
        else
            return null
    }
}
```
Implementing `security.TokenValidator` enables `@CurrentUser` injection.

**Init class** (runs once on first deployment):
```
@Bean
class Init {
    {
        Customer("leen", "leen@manul.com", "123456")
        Product("MacBook Pro", Money(14000, Currency.YUAN), 100, Category.ELECTRONICS)
    }
}
```

**Built-in functions:** `now()` (current timestamp as long), `uuid()` (random UUID string), `secureHash(value, salt)`.

**Types:** `string`, `int`, `long`, `double`, `bool`, `any`. Nullable: `string?`, `int?`. Arrays: `string[]`, `Product[]`. Non-null assertion: `value!!`.

**Control flow:**
```
if (condition) { ... } else { ... }
for (i in 0...n) { ... }           // 0 to n-1
for (child in children) { ... }     // iterate children
array.forEach(item -> { ... })
require(condition, "error message")  // throws if false
```

### Data Migration

When you add new fields or change types of existing fields, you need to define migration functions so that Manul runtime knows how to migrate data to the new model. You **must not** throw exceptions in migration functions.

**Example 1 — Field addition and type change:**

Before:
```
class Product(
    var name: string,
    var price: double,
    var stock: int
)
```

After:
```
class Product(
    var name: string,
    var price: Price,
    var stock: int,
    var status: ProductStatus
) {
    priv fn __price__(price: double) -> Price {
        return Price(price, Currency.CNY)
    }

    priv fn __status__() -> ProductStatus {
        return ProductStatus.ACTIVE
    }
}
```

**Example 2 — Moving fields to child objects:**

```
class Product(
    var name: string,
    var status: ProductStatus
) {
    priv deleted var price: Price?
    priv deleted var stock: int?

    priv fn __run__() {
        SKU("Default", price!!, stock!!)
    }

    class SKU(
        var variant: string,
        var price: Price,
        var stock: int
    )
}
```

Important details:
* When you need to access removed fields in migration, mark them as `deleted` instead of deleting. A `deleted` field must be nullable and private.
* When a field declared in the class parameter list is marked as deleted, it has to be moved to the class body.
* Remove `__run__` methods after the first deployment, otherwise they get rerun on subsequent deploys.

**Example 3 — New class referenced in migration:**

When creating a new class and a field referencing it at the same time, try to find an existing instance first:

```
class ProductionLine(var name: string) {
    static allIdx = Index<bool, ProductionLine>(false, p -> true)
}

class ProductionTask(val plannedAmount: double, val productionLine: ProductionLine) {
    var finishedAmount: double

    fn __productionLine__() -> ProductionLine {
        val existingPl = ProductionLine.allIdx.getFirst(true)
        return existingPl == null ? ProductionLine("N/A") : existingPl!!
    }
}
```

**Example 4 — Removing an enum constant:**

```
class Product(
  var name: string,
  var price: double,
  var kind: ProductKind
) {
    fn __run__() {
        if (kind.name == "CLOTHING")
            kind = ProductKind.OTHER
    }
}
```

Migration functions are also required for new fields or type-changed fields in value classes, because a value object can be persisted as part of an entity.

### Complete Code Example (E-Commerce App)

```
@@ src/domain/currency.mnl @@
package domain

enum Currency(val rate: double) {
    YUAN(7.2) {
        fn label() -> string { return "元" }
    },
    DOLLAR(1) {
        fn label() -> string { return "美元" }
    },
    POUND(0.75) {
        fn label() -> string { return "英镑" }
    },
;
    abstract fn label() -> string
}

@@ src/domain/money.mnl @@
package domain

value class Money(
    val amount: double,
    val currency: Currency
) {
    @Summary
    priv val summary = amount + " " + currency.label()

    fn add(that: Money) -> Money {
        return Money(amount + that.getAmount(currency), currency)
    }

    fn sub(that: Money) -> Money {
        return Money(amount - that.getAmount(currency), currency)
    }

    fn getAmount(currency: Currency) -> double {
        return currency.rate / this.currency.rate * amount
    }

    fn times(n: int) -> Money {
        return Money(amount * n, currency)
    }
}

@@ src/domain/category.mnl @@
package domain

enum Category {
    ELECTRONICS,
    CLOTHING,
    OTHER
;
}

@@ src/domain/customer.mnl @@
package domain

class Customer(
    @Summary
    var name: string,
    val email: string,
    password: string
) {
    priv var passwordHash = secureHash(password, null)
    static val emailIdx = Index<string, Customer>(true, c -> c.email)

    fn checkPassword(password: string) -> bool {
        return passwordHash == secureHash(password, null)
    }
}

@@ src/domain/product.mnl @@
package domain

class Product(
    @Summary
    var name: string,
    var price: Money,
    var stock: int,
    var category: Category
) {
    static val nameIdx = Index<string, Product>(true, p -> p.name)

    fn reduceStock(quantity: int) {
        require(stock >= quantity, "库存不足")
        stock -= quantity
    }

    fn restock(quantity: int) {
        require(quantity > 0, "补充数量必须大于0")
        stock += quantity
    }
}

@@ src/domain/session.mnl @@
package domain

class Session(
    val customer: Customer
) {
    val token = uuid()
    var expiry = now() + 30l * 24 * 60 * 60 * 1000
    static val tokenIdx = Index<string, Session>(true, s -> s.token)

    fn isValid() -> bool {
        return expiry > now()
    }
}

@@ src/domain/coupon.mnl @@
package domain

class Coupon(
    @Summary
    val title: string,
    val discount: Money,
    val expiry: long
) {
    var redeemed = false

    fn redeem() -> Money {
        require(now() > expiry, "优惠券已过期")
        require(redeemed, "优惠券已核销")
        redeemed = true
        return discount
    }
}

@@ src/domain/order_status.mnl @@
package domain

enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED,
;
}

@@ src/domain/OrderStatusAndTime.mnl @@
package domain

value class OrderStatusAndTime(val status: OrderStatus, val time: long)

@@ src/domain/order.mnl @@
package domain

class Order(
    val customer: Customer,
    val price: Money
) {
    static val statusAndCreatedAtIdx = Index<OrderStatusAndTime, Order>(false, o -> OrderStatusAndTime(o.status, o.createdAt))
    static val customerIdx = Index<Customer, Order>(false, o -> o.customer)

    val createdAt = now()
    var status = OrderStatus.PENDING

    fn confirm() {
        require(status == OrderStatus.PENDING, "订单状态不允许确认")
        status = OrderStatus.CONFIRMED
    }

    fn cancel() {
        require(status == OrderStatus.PENDING, "订单状态不允许取消")
        status = OrderStatus.CANCELLED
        for (child in children) {
            if (child is Item item)
                item.product.restock(item.quantity)
        }
    }

    class Item(
        val product: Product,
        val quantity: int
    )
}

@@ src/value/login_result.mnl @@
package value

import domain.Customer

value class LoginResult(
    val successful: bool,
    val token: string?
)

@@ src/service/product_service.mnl @@
package service

import domain.Product

@Bean
class ProductService {
    fn findProductByName(name: string) -> Product? {
        return Product.nameIdx.getFirst(name)
    }
}

@@ src/service/customer_service.mnl @@
package service

import domain.Customer
import domain.Session
import value.LoginResult

@Bean
class CustomerService {
    fn login(email: string, password: string) -> LoginResult {
        val customer = Customer.emailIdx.getFirst(email)
        if (customer != null) {
            val session = Session(customer!!)
            return LoginResult(true, session.token)
        } else
            return LoginResult(false, null)
    }

    fn register(name: string, email: string, password: string) -> LoginResult {
        val c = Customer(name, email, password)
        var s = Session(c)
        return LoginResult(true, s.token)
    }
}

@@ src/service/order_service.mnl @@
package service

import domain.Customer
import domain.Product
import domain.Coupon
import domain.Order
import domain.OrderStatus
import domain.OrderStatusAndTime

@Bean
class OrderService {
    static val PENDING_TIMEOUT = 15 * 60 * 1000

    fn placeOrder(@CurrentUser customer: Customer, products: Product[], coupon: Coupon?) -> Order {
        require(products.length > 0, "Missing products")
        var price = products[0].price
        for (i in 1...products.length) {
            price = price.add(products[i].price)
        }
        if (coupon != null) {
            price = price.sub(coupon!!.redeem())
        }
        val order = Order(customer, price)
        products.forEach(p -> {
            p.reduceStock(1)
            order.Item(p, 1)
        })
        return order
    }

    fn getCustomerOrders(@CurrentUser customer: Customer) -> Order[] {
        val orders = Order.customerIdx.getAll(customer)
        orders.sort((o1, o2) -> o1.createdAt < o2.createdAt ? 1 : o1.createdAt == o2.createdAt ? 0 : -1)
        return orders
    }

    fn confirmOrder(order: Order) {
        order.confirm()
    }

    fn cancelOrder(order: Order) {
        order.cancel()
    }

    fn cancelExpiredPendingOrders() {
        val orders = Order.statusAndCreatedAtIdx.query(
            OrderStatusAndTime(OrderStatus.PENDING, 0),
            OrderStatusAndTime(OrderStatus.PENDING, now() - PENDING_TIMEOUT)
        )
        orders.forEach(o -> o.cancel())
    }

    fn deleteAllCancelledOrders() {
        val orders = Order.statusAndCreatedAtIdx.query(
            OrderStatusAndTime(OrderStatus.CANCELLED, 0),
            OrderStatusAndTime(OrderStatus.CANCELLED, now())
        )
        orders.forEach(o -> {
            delete o
        })
    }

    fn deleteAllCustomerOrders(@CurrentUser customer: Customer) {
        val orders = Order.customerIdx.getAll(customer)
        orders.forEach(o -> {
            delete o
        })
    }
}

@@ src/service/token_validator.mnl @@
package service

import domain.Session

@Bean
internal class TokenValidator: security.TokenValidator {
    fn validate(token: string) -> any? {
        val s = Session.tokenIdx.getFirst(token)
        if (s != null && s!!.isValid())
            return s!!.customer
        else
            return null
    }
}

@@ src/service/init.mnl @@
import domain.Customer
import domain.Product
import domain.Money
import domain.Currency
import domain.Category

@Bean
class Init {
    {
        Customer("leen", "leen@manul.com", "123456")
        Product("MacBook Pro", Money(14000, Currency.YUAN), 100, Category.ELECTRONICS)
    }
}
```

### Manul Endpoint Reference
Manul auto-generates REST endpoints. For details see: https://docs.metavm.tech/guides/endpoint/

### Manul Project Workflow
1. Create repo with `.mnl` files in `src/`
2. Create Miaobu project with `project_type: "manul"` — this automatically creates an app on the Manul server
3. Deployment flow: GHA builds with `manul build` → uploads `target/target.mva` → Miaobu deploys to Manul server
4. The deployment URL is on the Manul server (e.g., `https://api.metavm.tech/{app-name}/`)
"""

# --------------------------------------------------------------------------- #
# Tool definitions (Claude tool-use schema)
# --------------------------------------------------------------------------- #

TOOLS = [
    {
        "name": "list_user_projects",
        "description": "List the user's Miaobu projects with their slugs, types, and domains.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_project_details",
        "description": "Get detailed information about a specific Miaobu project, including build config and repository info.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "list_repo_files",
        "description": "List all files in a GitHub repository. Returns file paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (GitHub username)."},
                "repo": {"type": "string", "description": "Repository name."},
                "branch": {"type": "string", "description": "Branch name (optional, defaults to default branch)."},
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the content of a file from a GitHub repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner."},
                "repo": {"type": "string", "description": "Repository name."},
                "path": {"type": "string", "description": "File path within the repository."},
                "branch": {"type": "string", "description": "Branch name (optional)."},
            },
            "required": ["owner", "repo", "path"],
        },
    },
    {
        "name": "create_repository",
        "description": "Create a new GitHub repository under the user's account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Repository name (lowercase, hyphens, no special chars)."},
                "description": {"type": "string", "description": "Repository description."},
                "private": {"type": "boolean", "description": "Whether the repo should be private. Default false."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "commit_files",
        "description": "Commit multiple files to a GitHub repository in a single commit. Use this to write project files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner."},
                "repo": {"type": "string", "description": "Repository name."},
                "branch": {"type": "string", "description": "Target branch (e.g. 'main')."},
                "files": {
                    "type": "array",
                    "description": "Files to commit. Each has 'path' and 'content' (null content = delete).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": ["string", "null"]},
                        },
                        "required": ["path", "content"],
                    },
                },
                "commit_message": {"type": "string", "description": "Commit message."},
            },
            "required": ["owner", "repo", "branch", "files", "commit_message"],
        },
    },
    {
        "name": "create_miaobu_project",
        "description": "Create a Miaobu project from an existing GitHub repository. Sets up webhook and build config.",
        "input_schema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner."},
                "repo": {"type": "string", "description": "Repository name."},
                "project_type": {
                    "type": "string",
                    "enum": ["static", "node", "python", "manul"],
                    "description": "Project type.",
                },
                "build_command": {"type": "string", "description": "Build command (e.g. 'npm run build'). Empty string for no build step."},
                "install_command": {"type": "string", "description": "Install command (e.g. 'npm install')."},
                "output_directory": {"type": "string", "description": "Build output directory (e.g. 'dist'). Only for static projects."},
                "start_command": {"type": "string", "description": "Start command for node/python projects."},
                "node_version": {"type": "string", "description": "Node.js version (e.g. '18', '20')."},
                "python_version": {"type": "string", "description": "Python version (e.g. '3.11')."},
            },
            "required": ["owner", "repo", "project_type"],
        },
    },
    {
        "name": "trigger_deployment",
        "description": "Trigger a deployment for an existing Miaobu project. Fetches latest commit and starts the build pipeline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID to deploy.",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "update_project",
        "description": "Update a Miaobu project's settings (project type, build/install/start commands, output directory, etc.). Use this to fix misconfigured projects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
                "project_type": {
                    "type": "string",
                    "enum": ["static", "node", "python", "manul"],
                    "description": "Project type: static (frontend apps), node (Node.js servers), python (Python servers).",
                },
                "build_command": {
                    "type": "string",
                    "description": "Build command (e.g., 'npm run build').",
                },
                "install_command": {
                    "type": "string",
                    "description": "Install command (e.g., 'npm install').",
                },
                "output_directory": {
                    "type": "string",
                    "description": "Build output directory (e.g., 'dist').",
                },
                "start_command": {
                    "type": "string",
                    "description": "Start command for node/python projects (e.g., 'node server.js').",
                },
                "node_version": {
                    "type": "string",
                    "description": "Node.js version (e.g., '18', '20').",
                },
                "is_spa": {
                    "type": "boolean",
                    "description": "Whether the static site is a Single Page Application.",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "list_project_deployments",
        "description": "List recent deployments for a project, including status, commit info, error messages, and timing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of deployments to return (default 5, max 20).",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "get_deployment_logs",
        "description": "Get full build logs and error details for a specific deployment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
                "deployment_id": {
                    "type": "integer",
                    "description": "The deployment ID.",
                },
            },
            "required": ["project_id", "deployment_id"],
        },
    },
    {
        "name": "wait_for_deployment",
        "description": "Wait for the latest in-progress deployment to reach a terminal state (deployed/failed/cancelled). Polls every 10 seconds, up to 5 minutes. Returns final status, build logs, and error message if failed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
                "deployment_id": {
                    "type": "integer",
                    "description": "Optional specific deployment ID to wait for. If omitted, waits for the latest in-progress deployment.",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "list_env_vars",
        "description": "List environment variables for a project. Secret values are masked. Returns key, masked/plain value, is_secret flag, and environment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
                "environment": {
                    "type": "string",
                    "description": "Environment name (default 'production').",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "set_env_var",
        "description": "Create or update an environment variable for a project. If the key already exists in the same environment, it will be updated; otherwise a new variable is created.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
                "key": {
                    "type": "string",
                    "description": "Variable name (e.g. 'DATABASE_URL', 'API_KEY').",
                },
                "value": {
                    "type": "string",
                    "description": "Variable value.",
                },
                "is_secret": {
                    "type": "boolean",
                    "description": "Whether the value should be masked in the UI (default false).",
                },
                "environment": {
                    "type": "string",
                    "description": "Environment name (default 'production').",
                },
            },
            "required": ["project_id", "key", "value"],
        },
    },
    {
        "name": "delete_env_var",
        "description": "Delete an environment variable by key from a project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
                "key": {
                    "type": "string",
                    "description": "Variable name to delete.",
                },
                "environment": {
                    "type": "string",
                    "description": "Environment name (default 'production').",
                },
            },
            "required": ["project_id", "key"],
        },
    },
    {
        "name": "get_manul_guide",
        "description": "Get the Manul programming language guide with syntax reference, project structure, data migration patterns, and code examples. Call this before creating or modifying Manul projects.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# --------------------------------------------------------------------------- #
# Tool executors
# --------------------------------------------------------------------------- #


async def _exec_list_user_projects(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    projects = (
        db.query(Project)
        .filter(Project.user_id == user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return {
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "slug": p.slug,
                "project_type": p.project_type or "static",
                "domain": p.default_domain,
                "github_repo": p.github_repo_name,
            }
            for p in projects
        ]
    }


async def _exec_get_project_details(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}
    return {
        "id": project.id,
        "name": project.name,
        "slug": project.slug,
        "project_type": project.project_type or "static",
        "github_repo": project.github_repo_name,
        "default_branch": project.default_branch,
        "domain": project.default_domain,
        "build_command": project.build_command,
        "install_command": project.install_command,
        "output_directory": project.output_directory,
        "start_command": project.start_command,
        "node_version": project.node_version,
        "python_version": project.python_version,
    }


async def _exec_list_repo_files(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    files = await GitHubService.get_repository_tree(
        user.github_access_token,
        tool_input["owner"],
        tool_input["repo"],
        tool_input.get("branch"),
    )
    return {"files": files}


async def _exec_read_file(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    content = await GitHubService.get_file_content(
        user.github_access_token,
        tool_input["owner"],
        tool_input["repo"],
        tool_input["path"],
        tool_input.get("branch", "main"),
    )
    if content is None:
        return {"error": f"File not found: {tool_input['path']}"}
    return {"path": tool_input["path"], "content": content}


async def _exec_create_repository(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    repo = await GitHubService.create_repository(
        user.github_access_token,
        tool_input["name"],
        tool_input.get("description", ""),
        tool_input.get("private", False),
        auto_init=True,
    )
    # Wait briefly for GitHub to finish initializing the repo with the initial commit
    await asyncio.sleep(2)
    return {
        "name": repo["name"],
        "full_name": repo["full_name"],
        "html_url": repo["html_url"],
        "default_branch": repo.get("default_branch", "main"),
        "private": repo.get("private", False),
    }


async def _exec_commit_files(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    result = await GitHubService.commit_files(
        user.github_access_token,
        tool_input["owner"],
        tool_input["repo"],
        tool_input["branch"],
        tool_input["files"],
        tool_input["commit_message"],
    )
    return result


async def _exec_create_miaobu_project(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    from ..api.v1.projects import generate_slug

    owner = tool_input["owner"]
    repo_name = tool_input["repo"]
    project_type = tool_input.get("project_type", "static")

    # Fetch repo info from GitHub
    repo_info = await GitHubService.get_repository(
        user.github_access_token, owner, repo_name
    )

    # Check if already imported
    existing = (
        db.query(Project)
        .filter(
            Project.user_id == user.id,
            Project.github_repo_id == repo_info["id"],
            Project.root_directory == "",
        )
        .first()
    )
    if existing:
        return {
            "already_exists": True,
            "project_id": existing.id,
            "slug": existing.slug,
            "domain": existing.default_domain,
        }

    slug = generate_slug(repo_info["name"], user.id, db)

    project_kwargs = dict(
        user_id=user.id,
        github_repo_id=repo_info["id"],
        github_repo_name=repo_info["full_name"],
        github_repo_url=repo_info["html_url"],
        default_branch=repo_info.get("default_branch", "main"),
        name=repo_info["name"],
        slug=slug,
        root_directory="",
        project_type=project_type,
        oss_path=f"projects/{slug}/",
        default_domain=f"{slug}.{settings.cdn_base_domain}",
    )

    if project_type == "static":
        project_kwargs["build_command"] = tool_input.get("build_command", "npm run build")
        project_kwargs["install_command"] = tool_input.get("install_command", "npm install")
        project_kwargs["output_directory"] = tool_input.get("output_directory", "dist")
        project_kwargs["node_version"] = tool_input.get("node_version", "18")
        project_kwargs["is_spa"] = True
    elif project_type == "node":
        project_kwargs["install_command"] = tool_input.get("install_command", "npm install")
        project_kwargs["build_command"] = tool_input.get("build_command", "")
        project_kwargs["start_command"] = tool_input.get("start_command", "node index.js")
        project_kwargs["node_version"] = tool_input.get("node_version", "18")
    elif project_type == "python":
        project_kwargs["python_version"] = tool_input.get("python_version", "3.11")
        project_kwargs["start_command"] = tool_input.get("start_command", "")

    project = Project(**project_kwargs)
    db.add(project)
    db.commit()
    db.refresh(project)

    # Create webhook
    webhook_error = None
    try:
        webhook_secret = secrets.token_urlsafe(32)
        webhook_url = f"{settings.backend_url}/api/v1/webhooks/github/{project.id}"
        webhook = await GitHubService.create_webhook(
            user.github_access_token, owner, repo_name, webhook_url, webhook_secret
        )
        project.webhook_id = webhook["id"]
        project.webhook_secret = webhook_secret
        db.commit()
    except Exception as e:
        webhook_error = str(e)

    return {
        "project_id": project.id,
        "slug": project.slug,
        "domain": project.default_domain,
        "webhook_created": webhook_error is None,
        "webhook_error": webhook_error,
    }


async def _exec_update_project(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    updatable_fields = [
        "project_type", "build_command", "install_command",
        "output_directory", "start_command", "node_version", "is_spa",
    ]
    updated = []
    for field in updatable_fields:
        if field in tool_input:
            old_value = getattr(project, field)
            new_value = tool_input[field]
            setattr(project, field, new_value)
            updated.append(f"{field}: {old_value!r} -> {new_value!r}")

    if not updated:
        return {"error": "No fields to update."}

    db.commit()
    return {
        "project_id": project.id,
        "updated": updated,
        "current_settings": {
            "project_type": project.project_type,
            "build_command": project.build_command,
            "install_command": project.install_command,
            "output_directory": project.output_directory,
            "start_command": project.start_command,
            "node_version": project.node_version,
            "is_spa": project.is_spa,
        },
    }


async def _exec_list_project_deployments(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    limit = min(tool_input.get("limit", 5), 20)
    deployments = (
        db.query(Deployment)
        .filter(Deployment.project_id == project.id)
        .order_by(Deployment.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "project_id": project.id,
        "deployments": [
            {
                "id": d.id,
                "status": d.status.value,
                "commit_sha": d.commit_sha[:8] if d.commit_sha else None,
                "commit_message": d.commit_message,
                "error_message": d.error_message,
                "build_time_seconds": d.build_time_seconds,
                "deployment_url": d.deployment_url,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "deployed_at": d.deployed_at.isoformat() if d.deployed_at else None,
            }
            for d in deployments
        ],
    }


async def _exec_get_deployment_logs(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    deployment = (
        db.query(Deployment)
        .filter(
            Deployment.id == tool_input["deployment_id"],
            Deployment.project_id == project.id,
        )
        .first()
    )
    if not deployment:
        return {"error": "Deployment not found."}

    build_logs = deployment.build_logs or ""
    # Truncate to last 8000 chars — errors are at the end
    if len(build_logs) > 8000:
        build_logs = "...(truncated)...\n" + build_logs[-8000:]

    return {
        "deployment_id": deployment.id,
        "status": deployment.status.value,
        "build_logs": build_logs,
        "error_message": deployment.error_message,
    }


async def _exec_wait_for_deployment(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    from ..database import SessionLocal

    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    project_id = project.id
    target_deployment_id = tool_input.get("deployment_id")
    terminal_statuses = {
        DeploymentStatus.DEPLOYED,
        DeploymentStatus.FAILED,
        DeploymentStatus.CANCELLED,
        DeploymentStatus.PURGED,
    }
    max_polls = 30  # 30 * 10s = 5 minutes

    for _ in range(max_polls):
        poll_db = SessionLocal()
        try:
            if target_deployment_id:
                dep = (
                    poll_db.query(Deployment)
                    .filter(
                        Deployment.id == target_deployment_id,
                        Deployment.project_id == project_id,
                    )
                    .first()
                )
            else:
                dep = (
                    poll_db.query(Deployment)
                    .filter(Deployment.project_id == project_id)
                    .order_by(Deployment.created_at.desc())
                    .first()
                )

            if not dep:
                return {"error": "No deployment found for this project."}

            if dep.status in terminal_statuses:
                build_logs = dep.build_logs or ""
                if len(build_logs) > 8000:
                    build_logs = "...(truncated)...\n" + build_logs[-8000:]
                return {
                    "deployment_id": dep.id,
                    "status": dep.status.value,
                    "build_logs": build_logs if dep.status == DeploymentStatus.FAILED else "",
                    "error_message": dep.error_message,
                    "deployment_url": dep.deployment_url,
                    "build_time_seconds": dep.build_time_seconds,
                }
        finally:
            poll_db.close()

        await asyncio.sleep(10)

    # Timeout — return current state
    poll_db = SessionLocal()
    try:
        if target_deployment_id:
            dep = (
                poll_db.query(Deployment)
                .filter(
                    Deployment.id == target_deployment_id,
                    Deployment.project_id == project_id,
                )
                .first()
            )
        else:
            dep = (
                poll_db.query(Deployment)
                .filter(Deployment.project_id == project_id)
                .order_by(Deployment.created_at.desc())
                .first()
            )
        if dep:
            return {
                "deployment_id": dep.id,
                "status": dep.status.value,
                "error_message": dep.error_message,
                "timed_out": True,
                "note": "Deployment did not reach a terminal state within 5 minutes.",
            }
        return {"error": "No deployment found.", "timed_out": True}
    finally:
        poll_db.close()


async def _exec_trigger_deployment(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    owner, repo_name = project.github_repo_name.split("/", 1)

    # Get latest commit
    try:
        async with GitHubService._get_client() as client:
            response = await client.get(
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo_name}/branches/{project.default_branch}",
                headers={
                    "Authorization": f"Bearer {user.github_access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            response.raise_for_status()
            branch_data = response.json()
            commit_sha = branch_data["commit"]["sha"]
            commit_message = branch_data["commit"]["commit"]["message"]
            commit_author = branch_data["commit"]["commit"]["author"]["name"]
    except Exception:
        commit_sha = "manual"
        commit_message = "Deployment triggered by AI"
        commit_author = user.github_username

    deployment = Deployment(
        project_id=project.id,
        commit_sha=commit_sha,
        commit_message=commit_message,
        commit_author=commit_author,
        branch=project.default_branch,
        status=DeploymentStatus.QUEUED,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    result = await trigger_build(project, deployment)
    if not result["success"]:
        return {"error": f"Failed to trigger build: {result['error']}"}

    return {
        "deployment_id": deployment.id,
        "status": "queued",
        "domain": project.default_domain,
        "url": f"https://{project.default_domain}",
    }


MASK = "••••••••"


async def _exec_list_env_vars(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    environment = tool_input.get("environment", "production")
    env_vars = (
        db.query(EnvironmentVariable)
        .filter(
            EnvironmentVariable.project_id == project.id,
            EnvironmentVariable.environment == environment,
        )
        .order_by(EnvironmentVariable.key)
        .all()
    )

    from .encryption import decrypt_value

    result = []
    for ev in env_vars:
        if ev.is_secret:
            value = MASK
        else:
            try:
                value = decrypt_value(ev.value)
            except Exception:
                value = ev.value
        result.append({
            "key": ev.key,
            "value": value,
            "is_secret": ev.is_secret,
            "environment": ev.environment,
        })

    return {"project_id": project.id, "environment": environment, "env_vars": result}


async def _exec_set_env_var(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    from .encryption import encrypt_value

    key = tool_input["key"]
    value = tool_input["value"]
    is_secret = tool_input.get("is_secret", False)
    environment = tool_input.get("environment", "production")

    existing = (
        db.query(EnvironmentVariable)
        .filter(
            EnvironmentVariable.project_id == project.id,
            EnvironmentVariable.key == key,
            EnvironmentVariable.environment == environment,
        )
        .first()
    )

    if existing:
        existing.value = encrypt_value(value)
        existing.is_secret = is_secret
        db.commit()
        return {
            "action": "updated",
            "key": key,
            "environment": environment,
            "is_secret": is_secret,
        }
    else:
        env_var = EnvironmentVariable(
            project_id=project.id,
            key=key,
            value=encrypt_value(value),
            is_secret=is_secret,
            environment=environment,
        )
        db.add(env_var)
        db.commit()
        return {
            "action": "created",
            "key": key,
            "environment": environment,
            "is_secret": is_secret,
        }


async def _exec_delete_env_var(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    key = tool_input["key"]
    environment = tool_input.get("environment", "production")

    env_var = (
        db.query(EnvironmentVariable)
        .filter(
            EnvironmentVariable.project_id == project.id,
            EnvironmentVariable.key == key,
            EnvironmentVariable.environment == environment,
        )
        .first()
    )
    if not env_var:
        return {"error": f"Environment variable '{key}' not found in {environment}."}

    db.delete(env_var)
    db.commit()
    return {"deleted": True, "key": key, "environment": environment}


async def _exec_get_manul_guide(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    return {"guide": MANUL_GUIDE}


# Dispatch table
TOOL_EXECUTORS = {
    "list_user_projects": _exec_list_user_projects,
    "get_project_details": _exec_get_project_details,
    "list_repo_files": _exec_list_repo_files,
    "read_file": _exec_read_file,
    "create_repository": _exec_create_repository,
    "commit_files": _exec_commit_files,
    "create_miaobu_project": _exec_create_miaobu_project,
    "trigger_deployment": _exec_trigger_deployment,
    "update_project": _exec_update_project,
    "list_project_deployments": _exec_list_project_deployments,
    "get_deployment_logs": _exec_get_deployment_logs,
    "wait_for_deployment": _exec_wait_for_deployment,
    "list_env_vars": _exec_list_env_vars,
    "set_env_var": _exec_set_env_var,
    "delete_env_var": _exec_delete_env_var,
    "get_manul_guide": _exec_get_manul_guide,
}


async def _execute_tool(
    tool_name: str, tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    """Execute a tool by name with error handling."""
    executor = TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return await executor(tool_input, user, db)
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# Chat orchestration (SSE streaming)
# --------------------------------------------------------------------------- #

MAX_TOOL_ROUNDS = 25
SONNET_MODEL = "claude-sonnet-4-20250514"
OPUS_MODEL = "claude-opus-4-0-20250514"


def _build_messages(session: ChatSession) -> List[Dict[str, Any]]:
    """Build the Claude messages array from persisted session history."""
    messages: List[Dict[str, Any]] = []
    for msg in session.messages:
        if msg.role == "user":
            messages.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            # Reconstruct content blocks from stored data
            content_blocks: List[Dict[str, Any]] = []
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})
            if msg.tool_calls:
                try:
                    tool_calls = json.loads(msg.tool_calls)
                    for tc in tool_calls:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["input"],
                        })
                except (json.JSONDecodeError, KeyError):
                    pass
            if content_blocks:
                messages.append({"role": "assistant", "content": content_blocks})
            # Append tool results as a user message (Claude API convention)
            if msg.tool_results:
                try:
                    tool_results = json.loads(msg.tool_results)
                    result_blocks = []
                    for tr in tool_results:
                        result_blocks.append({
                            "type": "tool_result",
                            "tool_use_id": tr["tool_use_id"],
                            "content": json.dumps(tr["result"], ensure_ascii=False),
                        })
                    if result_blocks:
                        messages.append({"role": "user", "content": result_blocks})
                except (json.JSONDecodeError, KeyError):
                    pass
    return messages


def _sse_event(event_type: str, data: Any) -> str:
    """Format an SSE event."""
    return f"data: {json.dumps({'type': event_type, 'data': data}, ensure_ascii=False)}\n\n"


def prepare_chat(
    session: ChatSession,
    user_message: str,
    user: User,
    db: Session,
) -> Dict[str, Any]:
    """
    Prepare chat context (DB work) before streaming begins.

    Must be called BEFORE creating the StreamingResponse, while the
    SQLAlchemy session is still active. Returns plain data for the generator.
    """
    # Save user message
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=user_message,
    )
    db.add(user_msg)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Auto-title from first message
    if session.title == "New chat":
        session.title = user_message[:50].strip()
        db.commit()

    # Build messages from history (while session is still bound)
    messages = _build_messages(session)

    # Extract plain data we'll need inside the generator
    return {
        "session_id": session.id,
        "messages": messages,
        "user_id": user.id,
        "github_access_token": user.github_access_token,
        "github_username": user.github_username,
    }


async def stream_chat(
    ctx: Dict[str, Any],
) -> AsyncGenerator[str, None]:
    """
    Main chat orchestration generator. Yields SSE events.

    Uses an asyncio.Queue so that keepalive comments can be sent
    while waiting for Claude API responses, preventing proxy timeouts.
    """
    from ..database import SessionLocal

    session_id = ctx["session_id"]
    messages = ctx["messages"]

    # Build a lightweight user-like object for tool executors
    class _UserCtx:
        def __init__(self, uid, token, username):
            self.id = uid
            self.github_access_token = token
            self.github_username = username

    user_ctx = _UserCtx(ctx["user_id"], ctx["github_access_token"], ctx["github_username"])

    # Configure Anthropic client with proxy if set
    client_kwargs: Dict[str, Any] = {"api_key": settings.anthropic_api_key}
    if settings.http_proxy:
        import httpx as _httpx
        client_kwargs["http_client"] = _httpx.Client(
            proxy=settings.http_proxy,
            timeout=600.0,
        )
    client = anthropic.Anthropic(**client_kwargs)

    accumulated_text = ""
    accumulated_tool_calls: List[Dict[str, Any]] = []
    accumulated_tool_results: List[Dict[str, Any]] = []

    # Queue-based approach: producer pushes events, keepalive task pushes
    # heartbeats, and the generator yields from the queue.
    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
    producer_done = asyncio.Event()

    async def keepalive():
        """Send SSE comments every 5s to prevent proxy idle-timeout."""
        while not producer_done.is_set():
            await asyncio.sleep(5)
            if not producer_done.is_set():
                await queue.put(": keepalive\n\n")

    async def producer():
        nonlocal accumulated_text, accumulated_tool_calls, accumulated_tool_results
        try:
            await queue.put(_sse_event("stream_start", {}))

            for round_num in range(MAX_TOOL_ROUNDS):
                model = SONNET_MODEL

                response = await asyncio.to_thread(
                    client.messages.create,
                    model=model,
                    max_tokens=32768,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )

                text_parts = []
                tool_use_blocks = []

                for block in response.content:
                    if block.type == "text":
                        text_parts.append(block.text)
                        await queue.put(_sse_event("text_delta", {"text": block.text}))
                    elif block.type == "tool_use":
                        tool_use_blocks.append(block)
                        await queue.put(_sse_event("tool_call_start", {
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }))

                round_text = "".join(text_parts)

                if response.stop_reason == "end_turn":
                    accumulated_text += round_text
                    break

                if response.stop_reason == "max_tokens":
                    # Output was truncated — tell Claude so it can retry
                    # with smaller tool calls (e.g., fewer files per commit)
                    accumulated_text += round_text

                    assistant_content = []
                    if round_text:
                        assistant_content.append({"type": "text", "text": round_text})
                    # Include any complete tool_use blocks from truncated response
                    for tb in tool_use_blocks:
                        assistant_content.append({
                            "type": "tool_use",
                            "id": tb.id,
                            "name": tb.name,
                            "input": tb.input,
                        })

                    if assistant_content:
                        messages.append({"role": "assistant", "content": assistant_content})

                    # Build tool results for any complete tool blocks
                    truncation_results = []
                    for tb in tool_use_blocks:
                        truncation_results.append({
                            "type": "tool_result",
                            "tool_use_id": tb.id,
                            "content": json.dumps({"error": "Output was truncated (max_tokens reached). Try breaking the operation into smaller steps — e.g., commit files in batches of 3-4 instead of all at once."}, ensure_ascii=False),
                            "is_error": True,
                        })

                    if truncation_results:
                        messages.append({"role": "user", "content": truncation_results})
                    else:
                        # No tool blocks — just tell Claude directly
                        messages.append({"role": "user", "content": [{"type": "text", "text": "[System: Your output was truncated because it exceeded the maximum token limit. Please continue, and if you need to commit many files, do so in smaller batches of 3-4 files per commit.]"}]})

                    await queue.put(_sse_event("text_delta", {"text": "\n\n[输出被截断，正在重试...]\n\n"}))
                    continue

                if response.stop_reason == "tool_use" and tool_use_blocks:
                    tool_results_for_api = []
                    round_tool_calls = []
                    round_tool_results = []

                    for tool_block in tool_use_blocks:
                        # Tool executors that need DB get a fresh session
                        tool_db = SessionLocal()
                        try:
                            result = await _execute_tool(
                                tool_block.name, tool_block.input, user_ctx, tool_db
                            )
                        finally:
                            tool_db.close()

                        await queue.put(_sse_event("tool_call_result", {
                            "id": tool_block.id,
                            "name": tool_block.name,
                            "result": result,
                        }))

                        tool_results_for_api.append({
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        })
                        round_tool_calls.append({
                            "id": tool_block.id,
                            "name": tool_block.name,
                            "input": tool_block.input,
                        })
                        round_tool_results.append({
                            "tool_use_id": tool_block.id,
                            "result": result,
                        })

                    accumulated_tool_calls.extend(round_tool_calls)
                    accumulated_tool_results.extend(round_tool_results)
                    accumulated_text += round_text

                    assistant_content = []
                    if round_text:
                        assistant_content.append({"type": "text", "text": round_text})
                    for tb in tool_use_blocks:
                        assistant_content.append({
                            "type": "tool_use",
                            "id": tb.id,
                            "name": tb.name,
                            "input": tb.input,
                        })

                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": tool_results_for_api})
                else:
                    accumulated_text += round_text
                    break

            # Save assistant message with a fresh DB session
            save_db = SessionLocal()
            try:
                assistant_msg = ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=accumulated_text,
                    tool_calls=json.dumps(accumulated_tool_calls, ensure_ascii=False) if accumulated_tool_calls else None,
                    tool_results=json.dumps(accumulated_tool_results, ensure_ascii=False) if accumulated_tool_results else None,
                )
                save_db.add(assistant_msg)
                save_db.commit()
                save_db.refresh(assistant_msg)
                await queue.put(_sse_event("message_done", {"message_id": assistant_msg.id}))
            finally:
                save_db.close()

        except Exception as e:
            traceback.print_exc()
            # Save whatever was accumulated so context isn't lost
            if accumulated_text or accumulated_tool_calls:
                try:
                    err_db = SessionLocal()
                    err_msg = ChatMessage(
                        session_id=session_id,
                        role="assistant",
                        content=accumulated_text + f"\n\n[错误: {str(e)}]",
                        tool_calls=json.dumps(accumulated_tool_calls, ensure_ascii=False) if accumulated_tool_calls else None,
                        tool_results=json.dumps(accumulated_tool_results, ensure_ascii=False) if accumulated_tool_results else None,
                    )
                    err_db.add(err_msg)
                    err_db.commit()
                    err_db.close()
                except Exception:
                    pass  # Best-effort save
            await queue.put(_sse_event("error", {"message": str(e)}))
        finally:
            producer_done.set()
            await queue.put(None)  # sentinel to stop consumer

    # Launch producer and keepalive tasks
    producer_task = asyncio.create_task(producer())
    keepalive_task = asyncio.create_task(keepalive())

    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        keepalive_task.cancel()
        try:
            await producer_task
        except Exception:
            pass
