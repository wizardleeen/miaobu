"""
Custom Domains API with ESA (Edge Security Acceleration) support.

This replaces the legacy CDN-based custom domain management.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

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
    1. Create ESA Custom Hostname
    2. Verify using ESA's verification mechanism
    3. Set active deployment (default to latest)
    4. Update Edge KV store
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

    # Step 1: Get latest successful deployment
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

    # Step 2: Provision ESA resources (creates Custom Hostname)
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
            "message": f"ESA provisioning failed: {provision_result.get('message')}",
            "error": provision_result.get('error')
        }

    # Step 3: Verify custom hostname using ESA's verification
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

    # Step 4: Update database
    domain.is_verified = True
    domain.verified_at = datetime.utcnow()
    domain.esa_saas_id = provision_result.get('custom_hostname_id')  # Store custom hostname ID
    domain.esa_status = "pending" if icp_required else "online"
    domain.active_deployment_id = latest_deployment.id
    domain.edge_kv_synced = True
    domain.edge_kv_synced_at = datetime.utcnow()
    domain.ssl_status = SSLStatus.ISSUING  # ESA will provision SSL automatically

    db.commit()

    response = {
        "success": True,
        "verified": True,
        "esa_saas_id": domain.esa_saas_id,
        "active_deployment_id": latest_deployment.id,
        "cname_target": domain.cname_target,
        "edge_kv_synced": True,
    }

    if icp_required:
        response["message"] = "Domain configured but ICP filing is required for domains serving users in mainland China."
        response["icp_required"] = True
        response["icp_filing_url"] = "https://beian.aliyun.com"
        response["instructions"] = {
            "action_required": "Complete ICP filing for your domain",
            "filing_url": "https://beian.aliyun.com",
            "note": "Your domain will remain offline until ICP filing is completed. SSL certificate will be issued automatically after ICP approval."
        }
    else:
        response["message"] = "Domain verified and provisioned successfully. SSL certificate will be issued automatically."
        response["instructions"] = {
            "next_step": f"Add CNAME record: {domain.domain} → {domain.cname_target}",
            "note": "SSL certificate will be automatically provisioned by ESA (may take a few minutes)"
        }

    return response


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


@router.post("/{domain_id}/promote-deployment")
async def promote_deployment(
    domain_id: int,
    deployment_id: int,
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
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
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
    domain.edge_kv_synced_at = datetime.utcnow()

    db.commit()

    return {
        "success": True,
        "domain": domain.domain,
        "active_deployment_id": deployment.id,
        "commit_sha": deployment.commit_sha,
        "edge_kv_synced": True,
        "message": f"Deployment #{deployment.id} is now live on {domain.domain}"
    }


@router.post("/{domain_id}/settings")
async def update_domain_settings(
    domain_id: int,
    auto_update_enabled: Optional[bool] = None,
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
    if auto_update_enabled is not None:
        domain.auto_update_enabled = auto_update_enabled

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
    domain.edge_kv_synced_at = datetime.utcnow()
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
    if domain.is_verified and domain.domain_type == "esa":
        esa_service = ESAService()
        deprovision_result = esa_service.deprovision_custom_domain(domain.domain)

        if not deprovision_result['success']:
            # Log error but don't fail deletion
            print(f"Warning: Failed to deprovision ESA resources: {deprovision_result.get('message')}")

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
