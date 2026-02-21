"""
Custom Domains API with ESA (Edge Security Acceleration) support.

This replaces the legacy CDN-based custom domain management.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone

from ...database import get_db
from ...models import User, Project, CustomDomain, Deployment, DeploymentStatus, SSLStatus
from ...schemas import CustomDomainCreate, CustomDomainResponse
from ...core.security import get_current_user
from ...core.exceptions import NotFoundException, ForbiddenException, BadRequestException, ConflictException
from ...services.dns import DNSService
from ...services.esa import ESAService
from ...config import get_settings

settings = get_settings()
router = APIRouter(prefix="/domains", tags=["Custom Domains (ESA)"])


@router.get("", response_model=List[CustomDomainResponse])
async def list_custom_domains(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all custom domains for the current user or a specific project.
    """
    query = db.query(CustomDomain).join(Project).filter(Project.user_id == current_user.id)

    if project_id:
        query = query.filter(CustomDomain.project_id == project_id)

    domains = query.order_by(CustomDomain.created_at.desc()).all()
    return domains


@router.post("", response_model=CustomDomainResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_domain(
    domain_data: CustomDomainCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Add a custom domain to a project.

    Steps:
    1. Generate verification token
    2. User adds TXT record for verification
    3. User calls /verify to create ESA SaaS manager
    """
    # Get project and verify ownership
    project = db.query(Project).filter(Project.id == domain_data.project_id).first()
    if not project:
        raise NotFoundException("Project not found")

    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this project")

    # Validate domain format
    domain = domain_data.domain.lower().strip()
    if not domain or "." not in domain:
        raise BadRequestException("Invalid domain format")

    # Check if domain already exists
    existing = db.query(CustomDomain).filter(CustomDomain.domain == domain).first()
    if existing:
        if existing.project_id == project.id:
            raise ConflictException("Domain already added to this project")
        else:
            raise ConflictException("Domain already in use by another project")

    # Generate verification token
    verification_token = DNSService.generate_verification_token()

    # Create custom domain record (ESA type)
    custom_domain = CustomDomain(
        project_id=project.id,
        domain=domain,
        is_verified=False,
        verification_token=verification_token,
        ssl_status=SSLStatus.PENDING,
        domain_type="esa",
        cname_target=settings.aliyun_esa_cname_target,
        esa_status="pending"
    )

    db.add(custom_domain)
    db.commit()
    db.refresh(custom_domain)

    return custom_domain


@router.post("/{domain_id}/verify")
async def verify_custom_domain(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Verify custom domain and provision ESA resources.

    Steps:
    1a. Verify domain ownership via DNS TXT record (SECURITY: prevents abuse)
    1b. Verify CNAME record points to correct target
    2. Get latest successful deployment
    3. Provision ESA resources (create Custom Hostname on Aliyun)
    4. Verify using ESA's verification mechanism
    5. Update database and Edge KV store

    IMPORTANT: Both TXT and CNAME verification happen BEFORE creating Aliyun resources
    to prevent resource abuse and ensure domain ownership AND proper DNS configuration.
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    if domain.is_verified:
        return {
            "success": True,
            "verified": True,
            "message": "Domain is already verified",
            "esa_saas_id": domain.esa_saas_id,
            "active_deployment_id": domain.active_deployment_id
        }

    # Step 1: SECURITY - Verify domain ownership and DNS configuration
    # This prevents anyone from "verifying" domains they don't own
    # AND prevents wasting Aliyun resources on unverified domains

    # Step 1a: Verify domain ownership via DNS TXT record
    txt_verification = DNSService.verify_txt_record(
        domain.domain,
        domain.verification_token
    )

    if not txt_verification.get("verified"):
        return {
            "success": False,
            "verified": False,
            "message": "Domain ownership verification failed. Please add the TXT record to your DNS.",
            "dns_check": {
                "txt_record": txt_verification
            },
            "instructions": {
                "step1": f"Add TXT record to your DNS provider",
                "record_name": f"_miaobu-verification.{domain.domain}",
                "record_type": "TXT",
                "record_value": domain.verification_token,
                "step2": "Wait 5-10 minutes for DNS propagation",
                "step3": "Click 'Verify Domain' again"
            }
        }

    # Step 1b: Verify CNAME record points to correct target
    cname_target = domain.cname_target or settings.aliyun_esa_cname_target
    cname_verification = DNSService.verify_cname_record(
        domain.domain,
        cname_target
    )

    if not cname_verification.get("verified"):
        # CNAME not configured yet - provide instructions
        return {
            "success": False,
            "verified": False,
            "message": "Domain ownership verified, but CNAME record not configured correctly.",
            "dns_check": {
                "txt_record": txt_verification,
                "cname_record": cname_verification
            },
            "instructions": {
                "step1": "✓ TXT record verified",
                "step2": f"Add CNAME record to your DNS provider",
                "record_name": domain.domain,
                "record_type": "CNAME",
                "record_value": cname_target,
                "step3": "Wait 5-10 minutes for DNS propagation",
                "step4": "Click 'Verify Domain' again",
                "note": cname_verification.get("message", "")
            }
        }

    # Step 2: Get latest successful deployment
    latest_deployment = db.query(Deployment).filter(
        Deployment.project_id == project.id,
        Deployment.status == DeploymentStatus.DEPLOYED
    ).order_by(Deployment.created_at.desc()).first()

    if not latest_deployment:
        return {
            "success": False,
            "verified": False,
            "message": "No successful deployment found. Deploy your project first."
        }

    # Step 3: NOW provision ESA resources (only after DNS verification passed)
    # This prevents creating Aliyun resources for domains the user doesn't own
    esa_service = ESAService()
    provision_result = esa_service.provision_custom_domain(
        domain=domain.domain,
        user_id=project.user_id,
        project_id=project.id,
        deployment_id=latest_deployment.id,
        commit_sha=latest_deployment.commit_sha
    )

    if not provision_result['success']:
        return {
            "success": False,
            "verified": False,
            "message": f"ESA provisioning failed: {provision_result.get('error')}",
            "error": provision_result.get('error')
        }

    # Step 4: Verify custom hostname using ESA's verification
    custom_hostname_id = provision_result.get('custom_hostname_id')
    icp_required = False

    if custom_hostname_id:
        verify_result = esa_service.verify_custom_hostname(custom_hostname_id)

        # Check if verification failed due to missing ICP
        if not verify_result['success']:
            error_msg = verify_result.get('error', '')
            if 'InvalidICP' in error_msg or 'ICP filing' in error_msg:
                icp_required = True
            else:
                # Other verification error
                print(f"Warning: Failed to initiate verification for {domain.domain}: {error_msg}")

        # Get custom hostname status to check ICP and domain status
        status_result = esa_service.get_custom_hostname_status(custom_hostname_id)
        if status_result.get('success'):
            # Check if ICP is required based on offline reason
            if status_result.get('icp_required'):
                icp_required = True

    # Step 5: Update database (DNS ownership confirmed, ESA resources created)
    is_base_subdomain = domain.domain.endswith(f'.{settings.cdn_base_domain}') or domain.domain == settings.cdn_base_domain

    domain.is_verified = True
    domain.verified_at = datetime.now(timezone.utc)
    domain.esa_saas_id = provision_result.get('custom_hostname_id')  # Store custom hostname ID
    domain.esa_status = "pending" if icp_required else "online"
    domain.active_deployment_id = latest_deployment.id
    domain.edge_kv_synced = True
    domain.edge_kv_synced_at = datetime.now(timezone.utc)

    # For *.{base_domain} subdomains, SSL is already active via wildcard cert
    if is_base_subdomain:
        domain.ssl_status = SSLStatus.ACTIVE
    else:
        domain.ssl_status = SSLStatus.VERIFYING

    db.commit()

    response = {
        "success": True,
        "verified": True,
        "esa_saas_id": domain.esa_saas_id,
        "active_deployment_id": latest_deployment.id,
        "cname_target": domain.cname_target,
        "edge_kv_synced": True,
        "ssl_status": domain.ssl_status.value,
    }

    if is_base_subdomain:
        response["ssl_note"] = "SSL is active via wildcard certificate."
    else:
        response["ssl_note"] = "SSL certificate is being provisioned by Aliyun ESA. This may take 5-30 minutes. Use the 'Refresh SSL Status' button to check progress."

    if icp_required:
        response["message"] = "域名已配置，但该域名需要完成 ICP 备案才能正常使用。请前往 beian.aliyun.com 完成备案。"
        response["icp_required"] = True
        response["icp_filing_url"] = "https://beian.aliyun.com"
        response["instructions"] = {
            "action_required": "Complete ICP filing for your domain",
            "filing_url": "https://beian.aliyun.com",
            "note": "Your domain will remain offline until ICP filing is completed. SSL certificate will be issued automatically after ICP approval."
        }
    else:
        response["message"] = "Domain verified and provisioned successfully." + (
            " SSL is active via wildcard certificate." if is_base_subdomain
            else " SSL certificate will be issued automatically."
        )
        response["instructions"] = {
            "next_step": f"Add CNAME record: {domain.domain} → {domain.cname_target}",
            "note": "SSL is already active." if is_base_subdomain
            else "SSL certificate will be automatically provisioned by ESA (may take a few minutes)"
        }

    return response


@router.post("/{domain_id}/refresh-ssl-status")
async def refresh_ssl_status(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Refresh SSL certificate status from Aliyun ESA.

    Queries ESA API to get the latest SSL certificate status and updates the database.
    Use this to check if certificate has been issued after domain verification.
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    if not domain.is_verified:
        return {
            "success": False,
            "message": "Domain is not verified yet. Verify domain first."
        }

    # For *.{base_domain} subdomains, SSL is always active via wildcard cert
    is_base_subdomain = domain.domain.endswith(f'.{settings.cdn_base_domain}') or domain.domain == settings.cdn_base_domain
    if is_base_subdomain:
        domain.ssl_status = SSLStatus.ACTIVE
        db.commit()
        return {
            "success": True,
            "domain": domain.domain,
            "ssl_status": SSLStatus.ACTIVE.value,
            "esa_status": domain.esa_status,
            "is_https_ready": True,
            "message": f"SSL is active via wildcard certificate for *.{settings.cdn_base_domain}"
        }

    if not domain.esa_saas_id:
        return {
            "success": False,
            "message": "ESA SaaS ID not found. Domain may not be provisioned on ESA."
        }

    # Get status from ESA
    esa_service = ESAService()

    # Get custom hostname status (includes SSL cert status)
    hostname_status = esa_service.get_custom_hostname_status(domain.esa_saas_id)

    if not hostname_status.get('success'):
        return {
            "success": False,
            "message": f"Failed to get status from ESA: {hostname_status.get('error')}",
            "error": hostname_status.get('error')
        }

    # Update domain with latest status
    esa_status = hostname_status.get('status', '').lower()
    cert_apply_message = hostname_status.get('cert_apply_message', '').lower()
    cert_status_ok = hostname_status.get('cert_status', '').lower()  # This is 'ok' or 'failed'
    ssl_flag = hostname_status.get('ssl_flag')

    # Map ESA cert_apply_message to our SSLStatus enum
    # cert_apply_message values: 'issued', 'issuing', 'applying', 'pending_issue', 'verifying', etc.
    if cert_apply_message in ['issued'] and cert_status_ok == 'ok':
        domain.ssl_status = SSLStatus.ACTIVE
    elif cert_apply_message in ['issuing', 'pending_issue', 'applying']:
        domain.ssl_status = SSLStatus.ISSUING
    elif cert_apply_message in ['verifying', 'pending_validation', '']:
        domain.ssl_status = SSLStatus.VERIFYING
    else:
        domain.ssl_status = SSLStatus.PENDING

    # Update ESA status
    domain.esa_status = esa_status

    # Update cert expiry if available
    cert_not_after = hostname_status.get('cert_not_after')
    if cert_not_after:
        try:
            # Parse timestamp (format may vary, handle common formats)
            if isinstance(cert_not_after, (int, float)):
                # Unix timestamp
                domain.ssl_expires_at = datetime.fromtimestamp(cert_not_after)
            elif isinstance(cert_not_after, str):
                # ISO format or other string format
                from dateutil import parser
                domain.ssl_expires_at = parser.parse(cert_not_after)
        except Exception as e:
            print(f"Failed to parse cert expiry date: {e}")

    db.commit()

    return {
        "success": True,
        "domain": domain.domain,
        "ssl_status": domain.ssl_status.value,
        "esa_status": domain.esa_status,
        "ssl_flag": ssl_flag,
        "cert_status": cert_status_ok,  # 'ok' or 'failed'
        "cert_apply_message": cert_apply_message,  # 'issued', 'issuing', etc.
        "cert_expires_at": domain.ssl_expires_at.isoformat() if domain.ssl_expires_at else None,
        "is_https_ready": domain.ssl_status == SSLStatus.ACTIVE,
        "message": "SSL status updated from ESA",
        "details": {
            "hostname": hostname_status.get('hostname'),
            "offline_reason": hostname_status.get('offline_reason'),
            "icp_required": hostname_status.get('icp_required', False)
        }
    }


@router.get("/{domain_id}/deployments")
async def list_domain_deployments(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all deployments for this domain's project.

    Shows which deployment is currently active on this domain.
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    # Get all successful deployments for this project
    deployments = db.query(Deployment).filter(
        Deployment.project_id == project.id,
        Deployment.status == DeploymentStatus.DEPLOYED
    ).order_by(Deployment.created_at.desc()).all()

    deployment_list = []
    for dep in deployments:
        deployment_list.append({
            "id": dep.id,
            "commit_sha": dep.commit_sha,
            "commit_message": dep.commit_message,
            "commit_author": dep.commit_author,
            "branch": dep.branch,
            "status": dep.status.value,
            "created_at": dep.created_at.isoformat(),
            "deployed_at": dep.deployed_at.isoformat() if dep.deployed_at else None,
            "is_active": dep.id == domain.active_deployment_id
        })

    return {
        "domain": domain.domain,
        "active_deployment_id": domain.active_deployment_id,
        "auto_update_enabled": domain.auto_update_enabled,
        "deployments": deployment_list
    }


class PromoteDeploymentRequest(BaseModel):
    deployment_id: int


@router.post("/{domain_id}/promote-deployment")
async def promote_deployment(
    domain_id: int,
    body: PromoteDeploymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Promote a deployment to be served on this custom domain.

    Updates Edge KV store to route domain traffic to the specified deployment.
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    if not domain.is_verified:
        raise BadRequestException("Domain must be verified before promoting deployments")

    # Get deployment
    deployment = db.query(Deployment).filter(Deployment.id == body.deployment_id).first()
    if not deployment:
        raise NotFoundException("Deployment not found")

    if deployment.project_id != project.id:
        raise BadRequestException("Deployment does not belong to this project")

    if deployment.status != DeploymentStatus.DEPLOYED:
        raise BadRequestException(f"Deployment is not successful (status: {deployment.status.value})")

    # Update Edge KV store
    esa_service = ESAService()
    kv_result = esa_service.update_edge_kv_mapping(
        domain=domain.domain,
        user_id=project.user_id,
        project_id=project.id,
        deployment_id=deployment.id,
        commit_sha=deployment.commit_sha
    )

    if not kv_result['success']:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update Edge KV: {kv_result.get('error')}"
        )

    # Update database
    domain.active_deployment_id = deployment.id
    domain.edge_kv_synced = True
    domain.edge_kv_synced_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "success": True,
        "domain": domain.domain,
        "active_deployment_id": deployment.id,
        "commit_sha": deployment.commit_sha,
        "edge_kv_synced": True,
        "message": f"Deployment #{deployment.id} is now live on {domain.domain}"
    }


class DomainSettingsUpdate(BaseModel):
    auto_update_enabled: Optional[bool] = None


@router.post("/{domain_id}/settings")
async def update_domain_settings(
    domain_id: int,
    body: DomainSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update domain settings.

    Settings:
    - auto_update_enabled: Automatically promote new deployments
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    # Update settings
    if body.auto_update_enabled is not None:
        domain.auto_update_enabled = body.auto_update_enabled

    db.commit()

    return {
        "success": True,
        "domain": domain.domain,
        "auto_update_enabled": domain.auto_update_enabled,
        "message": "Settings updated successfully"
    }


@router.post("/{domain_id}/sync-edge-kv")
async def sync_edge_kv(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Manually sync Edge KV store.

    Use this if Edge KV sync failed or to force a resync.
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    if not domain.is_verified:
        raise BadRequestException("Domain must be verified first")

    if not domain.active_deployment_id:
        raise BadRequestException("No active deployment set")

    deployment = db.query(Deployment).filter(Deployment.id == domain.active_deployment_id).first()
    if not deployment:
        raise NotFoundException("Active deployment not found")

    # Sync Edge KV
    esa_service = ESAService()
    kv_result = esa_service.update_edge_kv_mapping(
        domain=domain.domain,
        user_id=project.user_id,
        project_id=project.id,
        deployment_id=deployment.id,
        commit_sha=deployment.commit_sha
    )

    if not kv_result['success']:
        domain.edge_kv_synced = False
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Edge KV sync failed: {kv_result.get('error')}"
        )

    # Update database
    domain.edge_kv_synced = True
    domain.edge_kv_synced_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "success": True,
        "domain": domain.domain,
        "edge_kv_synced": True,
        "synced_at": domain.edge_kv_synced_at.isoformat(),
        "message": "Edge KV synchronized successfully"
    }


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_domain(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a custom domain.

    Removes ESA SaaS manager and Edge KV mapping.
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    # Deprovision ESA resources
    if domain.is_verified and domain.domain_type == "esa" and domain.esa_saas_id:
        esa_service = ESAService()

        # Delete SaaS manager (Custom Hostname)
        saas_result = esa_service.delete_saas_manager(domain.esa_saas_id)
        if not saas_result['success']:
            print(f"Warning: Failed to delete SaaS manager: {saas_result.get('error')}")

        # Delete Edge KV mapping
        kv_result = esa_service.delete_edge_kv_mapping(domain.domain)
        if not kv_result['success']:
            print(f"Warning: Failed to delete Edge KV mapping: {kv_result.get('error')}")

    # Delete from database
    db.delete(domain)
    db.commit()

    return None


@router.get("/{domain_id}/status")
async def get_domain_status(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive domain status.

    Includes:
    - Verification status
    - ESA SaaS manager status
    - SSL status
    - Edge KV sync status
    - Active deployment info
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    # Get active deployment info
    active_deployment_info = None
    if domain.active_deployment:
        dep = domain.active_deployment
        active_deployment_info = {
            "id": dep.id,
            "commit_sha": dep.commit_sha,
            "commit_message": dep.commit_message,
            "deployed_at": dep.deployed_at.isoformat() if dep.deployed_at else None
        }

    # Check ESA SaaS manager status (if verified)
    esa_status_info = None
    if domain.is_verified and domain.esa_saas_id:
        esa_service = ESAService()
        esa_status_result = esa_service.get_saas_manager_status(domain.domain)

        if esa_status_result['success']:
            esa_status_info = {
                "status": esa_status_result.get('status'),
                "ssl_status": esa_status_result.get('ssl_status'),
                "verified": esa_status_result.get('verified')
            }

    return {
        "domain": domain.domain,
        "is_verified": domain.is_verified,
        "verified_at": domain.verified_at.isoformat() if domain.verified_at else None,
        "domain_type": domain.domain_type,
        "cname_target": domain.cname_target,
        "esa_saas_id": domain.esa_saas_id,
        "esa_status": domain.esa_status,
        "esa_live_status": esa_status_info,
        "ssl_status": domain.ssl_status.value,
        "edge_kv_synced": domain.edge_kv_synced,
        "edge_kv_synced_at": domain.edge_kv_synced_at.isoformat() if domain.edge_kv_synced_at else None,
        "active_deployment": active_deployment_info,
        "auto_update_enabled": domain.auto_update_enabled,
        "created_at": domain.created_at.isoformat(),
        "instructions": {
            "cname_record": f"{domain.domain} → {domain.cname_target}",
            "note": "CNAME must be configured in your DNS provider" if domain.is_verified else "Verify domain first"
        }
    }
