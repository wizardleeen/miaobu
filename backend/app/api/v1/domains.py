from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from ...database import get_db
from ...models import User, Project, CustomDomain, SSLStatus
from ...schemas import CustomDomainCreate, CustomDomainResponse
from ...core.security import get_current_user
from ...core.exceptions import NotFoundException, ForbiddenException, BadRequestException, ConflictException
from ...services.dns import DNSService
from ...services.cdn import CDNService

router = APIRouter(prefix="/domains", tags=["Custom Domains"])


@router.post("", response_model=CustomDomainResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_domain(
    domain_data: CustomDomainCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Add a custom domain to a project.

    Generates verification token for DNS verification.
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

    # Create custom domain record
    custom_domain = CustomDomain(
        project_id=project.id,
        domain=domain,
        is_verified=False,
        verification_token=verification_token,
        ssl_status=SSLStatus.PENDING
    )

    db.add(custom_domain)
    db.commit()
    db.refresh(custom_domain)

    return custom_domain


@router.get("", response_model=List[CustomDomainResponse])
async def list_custom_domains(
    project_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List custom domains.

    If project_id is provided, returns domains for that project.
    Otherwise, returns all domains for user's projects.
    """
    if project_id:
        # Get domains for specific project
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException("Project not found")

        if project.user_id != current_user.id:
            raise ForbiddenException("You don't have access to this project")

        domains = db.query(CustomDomain).filter(CustomDomain.project_id == project_id).all()
    else:
        # Get all domains for user's projects
        user_projects = db.query(Project).filter(Project.user_id == current_user.id).all()
        project_ids = [p.id for p in user_projects]
        domains = db.query(CustomDomain).filter(CustomDomain.project_id.in_(project_ids)).all()

    return domains


@router.get("/{domain_id}", response_model=CustomDomainResponse)
async def get_custom_domain(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific custom domain."""
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    return domain


@router.post("/{domain_id}/verify")
async def verify_custom_domain(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Verify custom domain via DNS TXT record.

    Checks for verification token in DNS TXT records.
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
            "message": "Domain is already verified"
        }

    # Verify DNS TXT record
    verification_result = DNSService.verify_txt_record(
        domain.domain,
        domain.verification_token
    )

    if verification_result.get("verified"):
        # Update domain as verified
        domain.is_verified = True
        domain.verified_at = datetime.utcnow()
        db.commit()

        # Optionally add domain to CDN (async task)
        # This would be done in a background task
        try:
            cdn_service = CDNService()
            cdn_result = cdn_service.add_custom_domain(domain.domain)

            return {
                "success": True,
                "verified": True,
                "message": "Domain verified successfully",
                "cdn_status": cdn_result.get("message"),
                "dns_check": verification_result
            }
        except Exception as e:
            # Domain verified but CDN addition failed
            return {
                "success": True,
                "verified": True,
                "message": "Domain verified but CDN configuration pending",
                "cdn_error": str(e),
                "dns_check": verification_result
            }
    else:
        return {
            "success": False,
            "verified": False,
            "message": verification_result.get("message", "Verification failed"),
            "dns_check": verification_result
        }


@router.post("/{domain_id}/check-dns")
async def check_domain_dns(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check DNS status of custom domain.

    Returns current DNS configuration without updating verification status.
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    # Check comprehensive DNS status
    dns_status = DNSService.check_domain_status(domain.domain)

    # Check TXT record for verification
    txt_result = DNSService.verify_txt_record(
        domain.domain,
        domain.verification_token
    )

    # Check CNAME record pointing to CDN
    from ...config import get_settings
    settings = get_settings()

    cname_result = None
    if settings.aliyun_cdn_domain:
        cname_result = DNSService.verify_cname_record(
            domain.domain,
            settings.aliyun_cdn_domain
        )

    return {
        "success": True,
        "domain": domain.domain,
        "is_verified": domain.is_verified,
        "dns_status": dns_status,
        "txt_verification": txt_result,
        "cname_status": cname_result,
        "verification_token": domain.verification_token if not domain.is_verified else None
    }


@router.delete("/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_domain(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a custom domain."""
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    # Optionally remove from CDN
    try:
        cdn_service = CDNService()
        cdn_service.delete_custom_domain(domain.domain)
    except Exception as e:
        # Log error but don't fail deletion
        print(f"Warning: Failed to delete domain from CDN: {e}")

    # Delete from database
    db.delete(domain)
    db.commit()

    return None


@router.get("/{domain_id}/dns-instructions")
async def get_dns_instructions(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get DNS configuration instructions for custom domain.

    Returns step-by-step instructions for setting up DNS records.
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    from ...config import get_settings
    settings = get_settings()

    # Determine if domain is apex or subdomain
    is_apex = DNSService.is_apex_domain(domain.domain)

    # Get CDN CNAME target
    cdn_target = settings.aliyun_cdn_domain or "miaobu.app"

    instructions = {
        "domain": domain.domain,
        "is_apex": is_apex,
        "is_verified": domain.is_verified,
        "steps": []
    }

    if not domain.is_verified:
        # Step 1: Add TXT record for verification
        instructions["steps"].append({
            "step": 1,
            "title": "Add DNS TXT Record for Verification",
            "description": "Add the following TXT record to verify domain ownership",
            "record_type": "TXT",
            "name": f"_miaobu-verification.{domain.domain}" if not domain.domain.startswith("_miaobu-verification") else domain.domain,
            "value": domain.verification_token,
            "ttl": 300,
            "example": f"_miaobu-verification.{domain.domain} IN TXT \"{domain.verification_token}\"",
            "note": "This record is used to verify you own the domain"
        })

    # Step 2: Add CNAME or A record for CDN
    if is_apex:
        # Apex domain - cannot use CNAME
        instructions["steps"].append({
            "step": 2 if not domain.is_verified else 1,
            "title": "Add DNS A Record",
            "description": "Apex domains cannot use CNAME. Contact support for CDN IP address.",
            "record_type": "A",
            "name": domain.domain,
            "value": "Contact support for IP address",
            "ttl": 3600,
            "note": "Apex domains (example.com) require A record with CDN IP address"
        })
    else:
        # Subdomain - can use CNAME
        instructions["steps"].append({
            "step": 2 if not domain.is_verified else 1,
            "title": "Add DNS CNAME Record",
            "description": "Point your domain to Miaobu CDN",
            "record_type": "CNAME",
            "name": domain.domain,
            "value": cdn_target,
            "ttl": 3600,
            "example": f"{domain.domain} IN CNAME {cdn_target}",
            "note": "This routes traffic through Miaobu CDN for better performance"
        })

    # Additional information
    instructions["verification_status"] = {
        "is_verified": domain.is_verified,
        "verified_at": domain.verified_at.isoformat() if domain.verified_at else None,
        "next_action": "Add TXT record and click 'Verify Domain'" if not domain.is_verified else "Domain is verified! Add CNAME record to enable."
    }

    instructions["helpful_links"] = {
        "cloudflare": "https://developers.cloudflare.com/dns/manage-dns-records/how-to/create-dns-records/",
        "namecheap": "https://www.namecheap.com/support/knowledgebase/article.aspx/319/2237/how-can-i-set-up-an-a-address-record-for-my-domain/",
        "godaddy": "https://www.godaddy.com/help/add-a-cname-record-19236",
        "aliyun": "https://help.aliyun.com/document_detail/29725.html"
    }

    return instructions


@router.post("/{domain_id}/issue-ssl")
async def issue_ssl_certificate(
    domain_id: int,
    use_staging: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Issue SSL certificate for custom domain.

    Uses Let's Encrypt to automatically provision free SSL certificate.
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    # Check if domain is verified
    if not domain.is_verified:
        raise BadRequestException("Domain must be verified before issuing SSL certificate")

    # Queue SSL issuance task
    from worker.tasks.ssl import issue_certificate
    task = issue_certificate.apply_async(
        args=[domain_id, use_staging],
        queue='default'
    )

    return {
        "success": True,
        "message": "SSL certificate issuance started",
        "task_id": task.id,
        "domain": domain.domain,
        "note": "Certificate issuance may take 1-2 minutes"
    }


@router.post("/{domain_id}/renew-ssl")
async def renew_ssl_certificate(
    domain_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Renew SSL certificate for custom domain.

    Automatically renews certificate if expiring within 30 days.
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    # Check if certificate exists
    if not domain.ssl_certificate_id:
        raise BadRequestException("No certificate to renew. Issue a certificate first.")

    # Queue SSL renewal task
    from worker.tasks.ssl import renew_certificate
    task = renew_certificate.apply_async(
        args=[domain_id, force],
        queue='default'
    )

    return {
        "success": True,
        "message": "SSL certificate renewal started",
        "task_id": task.id,
        "domain": domain.domain
    }


@router.get("/{domain_id}/ssl-status")
async def get_ssl_status(
    domain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get SSL certificate status for custom domain.

    Returns certificate details and expiry information.
    """
    domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
    if not domain:
        raise NotFoundException("Custom domain not found")

    # Verify project ownership
    project = domain.project
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this domain")

    # Calculate days until expiry
    days_until_expiry = None
    needs_renewal = False
    if domain.ssl_expires_at:
        from datetime import datetime
        days_until_expiry = (domain.ssl_expires_at - datetime.utcnow()).days
        needs_renewal = days_until_expiry <= 30

    return {
        "domain": domain.domain,
        "ssl_status": domain.ssl_status.value,
        "certificate_id": domain.ssl_certificate_id,
        "expires_at": domain.ssl_expires_at.isoformat() if domain.ssl_expires_at else None,
        "days_until_expiry": days_until_expiry,
        "needs_renewal": needs_renewal,
        "is_https_enabled": domain.ssl_status == SSLStatus.ACTIVE
    }
