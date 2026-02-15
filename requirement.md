**Project Title:** Miaobu - Static Frontend Deployment Platform (MVP)

**Role:**
Act as a Full Stack Software Architect and Senior Developer.

**Objective:**
Build a frontend deployment platform (PaaS) similar to Vercel/Netlify, but specifically for the Alibaba Cloud (Aliyun) ecosystem. The platform is named **Miaobu**.

**Scope:**
Miaobu focuses exclusively on static frontend projects (SPA/SSG). Server-side rendering (e.g., Next.js backend features) is **not** supported.

**Technical Stack:**
*   **Backend:** Python (Recommended: FastAPI or Django Ninja) with Celery/Redis for asynchronous build queues.
*   **Database:** PostgreSQL.
*   **Frontend:** Modern stack (React + TypeScript + Vite + Tailwind CSS).
*   **Infrastructure:** Alibaba Cloud (Aliyun) OSS (Object Storage) and CDN.

**Key Features & Requirements:**

1.  **Authentication:**
    *   User login via GitHub OAuth.

2.  **Git Integration:**
    *   Import repositories directly from GitHub.
    *   **Build Detection:** Automatically infer build commands (e.g., `npm run build`) and output directories (e.g., `dist/` or `build/`) via `package.json` analysis, while allowing user overrides.

3.  **Deployment Pipeline:**
    *   Triggered automatically via Webhooks upon pushing to the `main` branch.
    *   **Process:** Clone repo $\to$ Install dependencies $\to$ Build $\to$ Upload artifacts to OSS $\to$ Purge/Refresh CDN cache.

4.  **Cloud Architecture (Aliyun Constraint Handling):**
    *   **Constraint:** Aliyun has strict limits on the number of OSS buckets per account.
    *   **Solution:** Implement a **Multi-tenant Monolithic Bucket Strategy**. Do not create a bucket per project. Instead, store all projects in a single (or few) master buckets using path-based isolation (e.g., `s3://miaobu-master/user_id/project_id/commit_hash/`).
    *   Use CDN logic/Edge scripts to route custom domains to the specific OSS sub-folders.

5.  **Domain & SSL:**
    *   Support custom domain binding.
    *   **Automated SSL:** The system must provision SSL certificates for custom domains automatically (e.g., using Let's Encrypt/ACME protocol or Aliyun CAS API) to ensure HTTPS support.

**Deliverables:**
1.  **Complete Source Code:** A fully functional repository containing backend, frontend, and worker services.
2.  **Documentation:** A comprehensive `README.md` detailing:
    *   Local development setup.
    *   Aliyun credentials configuration.
    *   Deployment guide for the platform itself.
