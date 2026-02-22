# Development Guide

This document outlines the development workflow and environment setup for the Miaobu project.

## Feature/Bugfix Workflow

1. Create a new `feat/` or `fix/` branch.
2. Implement your changes locally.
3. Merge and push your changes to the `staging` branch.
4. Verify the changes in the staging environment.
5. Request User Acceptance Testing (UAT) from the user/client.
6. Once approved, squash changes into a single commit, open a Pull Request (PR) against the `main` branch.
7. Wait for the user/project lead to review and merge the PR.
8. Pull the updated `main` branch locally and delete your feature/bugfix branch.

## Deployment

Miaobu is self-hosted and utilizes an automated CI/CD pipeline. Any changes merged into the `main` branch will automatically trigger a production redeployment. Pushing to the `staging` branch triggers a staging redeployment.

**Production Environment:**
* **Frontend:** Project name is `miaobu` | Domain: `miaobu.metavm.tech`
* **Backend:** Project name is `miaobu-backend` | Domains: `miaobu1.metavm.tech` or `metavm-api.metavm.tech`

**Staging Environment:**
* **Frontend:** Domain: `miaobu-staging.metavm.tech`
* **Backend:** Domain: `miaobu1-staging.metavm.tech`

## Database

The Miaobu database runs on this server on port `5432`. Both the production and staging environments connect to the database securely via a VPC.

* **Production Database:** `miaobu` (Credentials located in `backend/.env`)
* **Staging Database:** `miaobu_staging` (Credentials located in `backend/.env.staging`)
