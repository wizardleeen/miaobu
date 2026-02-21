"""Public API — Domain endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List

from ....database import get_db
from ....models import User, Project, CustomDomain, Deployment, DeploymentStatus, SSLStatus
from ....core.security import get_current_user_flexible
from ....core.exceptions import NotFoundException, ForbiddenException
from ....services.dns import DNSService
from ....services.esa import ESAService
from ....config import get_settings
from .helpers import single_response

router = APIRouter(tags=["Public API - Domains"])


def _domain_dict(d: CustomDomain) -> dict:
    return {
        "id": d.id,
        "project_id": d.project_id,
        "domain": d.domain,
        "is_verified": d.is_verified,
        "ssl_status": d.ssl_status.value,
        "esa_status": d.esa_status,
        "active_deployment_id": d.active_deployment_id,
        "auto_update_enabled": d.auto_update_enabled,
        "created_at": d.created_at.isoformat(),
        "verified_at": d.verified_at.isoformat() if d.verified_at else None,
    }


def _get_user_project(project_id: int, user: User, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException("Project not found")
    if project.user_id != user.id:
        raise ForbiddenException("You don't have access to this project")
    return project


@router.get("/projects/{project_id}/domains")
async def list_domains(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """List all custom domains for a project."""
    _get_user_project(project_id, current_user, db)

    domains = (
        db.query(CustomDomain)
        .filter(CustomDomain.project_id == project_id)
        .order_by(CustomDomain.created_at.desc())
        .all()
    )
    return {"data": [_domain_dict(d) for d in domains]}


class AddDomainBody(BaseModel):
    domain: str = Field(..., min_length=3, max_length=255)


@router.post("/projects/{project_id}/domains", status_code=201)
async def add_domain(
    project_id: int,
    body: AddDomainBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Add a custom domain to a project."""
    project = _get_user_project(project_id, current_user, db)
    settings = get_settings()

    domain_name = body.domain.lower().strip()
    if not domain_name or "." not in domain_name:
        raise HTTPException(status_code=400, detail="Invalid domain format")

    existing = db.query(CustomDomain).filter(CustomDomain.domain == domain_name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Domain already in use")

    verification_token = DNSService.generate_verification_token()

    custom_domain = CustomDomain(
        project_id=project.id,
        domain=domain_name,
        is_verified=False,
        verification_token=verification_token,
        ssl_status=SSLStatus.PENDING,
        domain_type="esa",
        cname_target=settings.aliyun_esa_cname_target,
        esa_status="pending",
    )
    db.add(custom_domain)
    db.commit()
    db.refresh(custom_domain)

    return single_response({
        **_domain_dict(custom_domain),
        "verification_token": custom_domain.verification_token,
        "cname_target": custom_domain.cname_target,
    })


@router.post("/projects/{project_id}/domains/{domain_id}/verify")
async def verify_domain(
    project_id: int,
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Verify a custom domain (checks DNS TXT + CNAME, provisions edge resources)."""
    _get_user_project(project_id, current_user, db)

    domain = (
        db.query(CustomDomain)
        .filter(CustomDomain.id == domain_id, CustomDomain.project_id == project_id)
        .first()
    )
    if not domain:
        raise NotFoundException("Domain not found")

    if domain.is_verified:
        return single_response({**_domain_dict(domain), "message": "Domain is already verified"})

    project = domain.project

    # Verify TXT record
    txt_result = DNSService.verify_txt_record(domain.domain, domain.verification_token)
    if not txt_result.get("verified"):
        raise HTTPException(status_code=400, detail="TXT record verification failed. Please add the DNS TXT record.")

    # Verify CNAME record
    settings = get_settings()
    cname_target = domain.cname_target or settings.aliyun_esa_cname_target
    cname_result = DNSService.verify_cname_record(domain.domain, cname_target)
    if not cname_result.get("verified"):
        raise HTTPException(status_code=400, detail="CNAME record not configured correctly.")

    # Get latest deployment
    latest_deployment = (
        db.query(Deployment)
        .filter(Deployment.project_id == project.id, Deployment.status == DeploymentStatus.DEPLOYED)
        .order_by(Deployment.created_at.desc())
        .first()
    )
    if not latest_deployment:
        raise HTTPException(status_code=400, detail="No successful deployment found. Deploy your project first.")

    # Provision ESA
    esa_service = ESAService()
    provision_result = esa_service.provision_custom_domain(
        domain=domain.domain,
        user_id=project.user_id,
        project_id=project.id,
        deployment_id=latest_deployment.id,
        commit_sha=latest_deployment.commit_sha,
    )
    if not provision_result["success"]:
        raise HTTPException(status_code=500, detail=f"Edge provisioning failed: {provision_result.get('error')}")

    custom_hostname_id = provision_result.get("custom_hostname_id")
    icp_required = False
    if custom_hostname_id:
        verify_result = esa_service.verify_custom_hostname(custom_hostname_id)
        if not verify_result["success"]:
            error_msg = verify_result.get("error", "")
            if "InvalidICP" in error_msg or "ICP filing" in error_msg:
                icp_required = True

        status_result = esa_service.get_custom_hostname_status(custom_hostname_id)
        if status_result.get("success") and status_result.get("icp_required"):
            icp_required = True

    is_metavm = domain.domain.endswith(f".{settings.cdn_base_domain}") or domain.domain == settings.cdn_base_domain
    domain.is_verified = True
    domain.verified_at = datetime.now(timezone.utc)
    domain.esa_saas_id = custom_hostname_id
    domain.esa_status = "pending" if icp_required else "online"
    domain.active_deployment_id = latest_deployment.id
    domain.edge_kv_synced = True
    domain.edge_kv_synced_at = datetime.now(timezone.utc)
    domain.ssl_status = SSLStatus.ACTIVE if is_metavm else SSLStatus.VERIFYING
    db.commit()

    return single_response(_domain_dict(domain))


@router.delete("/projects/{project_id}/domains/{domain_id}", status_code=204)
async def delete_domain(
    project_id: int,
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Delete a custom domain."""
    _get_user_project(project_id, current_user, db)

    domain = (
        db.query(CustomDomain)
        .filter(CustomDomain.id == domain_id, CustomDomain.project_id == project_id)
        .first()
    )
    if not domain:
        raise NotFoundException("Domain not found")

    if domain.is_verified and domain.domain_type == "esa" and domain.esa_saas_id:
        esa_service = ESAService()
        esa_service.delete_saas_manager(domain.esa_saas_id)
        esa_service.delete_edge_kv_mapping(domain.domain)

    db.delete(domain)
    db.commit()
    return None
