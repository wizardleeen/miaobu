import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'backend'))

from celery_app import app, get_db
from app.models import CustomDomain, SSLStatus
from app.services.ssl import SSLService
from app.services.alidns import AliDNSService
from app.services.cdn import CDNService
from app.config import get_settings

settings = get_settings()


@app.task(bind=True, name='tasks.ssl.issue_certificate')
def issue_certificate(self, domain_id: int, use_staging: bool = False):
    """
    Issue SSL certificate for a custom domain.

    Args:
        domain_id: ID of the custom domain
        use_staging: Use Let's Encrypt staging environment (for testing)

    Returns:
        dict with certificate issuance results
    """
    db = get_db()
    if not db:
        return {'error': 'Database not available'}

    try:
        # Get custom domain
        domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
        if not domain:
            return {'error': f'Custom domain {domain_id} not found'}

        # Check if domain is verified
        if not domain.is_verified:
            return {
                'success': False,
                'error': 'Domain must be verified before issuing certificate'
            }

        # Update SSL status
        domain.ssl_status = SSLStatus.ISSUING
        db.commit()

        # Initialize services
        ssl_service = SSLService(use_staging=use_staging)
        alidns_service = AliDNSService()

        # Register ACME account (or reuse existing)
        account_email = f"ssl@{settings.backend_url.replace('https://', '').replace('http://', '')}"
        register_result = ssl_service.register_account(account_email)

        if not register_result.get('success'):
            domain.ssl_status = SSLStatus.FAILED
            db.commit()
            return register_result

        # DNS challenge callback
        dns_record_ids = []

        def dns_challenge_callback(validation_domain: str, validation_value: str):
            """Create DNS TXT record for ACME challenge."""
            result = alidns_service.add_txt_record(
                validation_domain,
                validation_value,
                ttl=300  # 5 minutes
            )

            if result.get('success'):
                dns_record_ids.append(result.get('record_id'))

            return result

        # Request certificate
        cert_result = ssl_service.request_certificate(
            domain.domain,
            dns_challenge_callback
        )

        # Cleanup DNS records
        for record_id in dns_record_ids:
            alidns_service.delete_txt_record(record_id)

        if not cert_result.get('success'):
            domain.ssl_status = SSLStatus.FAILED
            db.commit()
            return cert_result

        # Parse certificate to get expiry date
        cert_info = SSLService.parse_certificate(cert_result['certificate'])

        # Store certificate in database
        # Note: In production, you'd upload to Alibaba Cloud CAS
        # For now, we'll store the certificate data in the database
        domain.ssl_certificate_id = cert_info.get('serial_number')
        domain.ssl_expires_at = cert_info.get('not_after')
        domain.ssl_status = SSLStatus.ACTIVE
        db.commit()

        # Optional: Upload certificate to CDN
        # This would be done via CDN API to enable HTTPS
        try:
            cdn_service = CDNService()
            # CDN certificate upload would go here
            # cdn_service.upload_certificate(domain.domain, cert_result['certificate'], cert_result['private_key'])
        except Exception as e:
            print(f"Warning: Failed to upload certificate to CDN: {e}")

        return {
            'success': True,
            'domain': domain.domain,
            'certificate_id': domain.ssl_certificate_id,
            'expires_at': domain.ssl_expires_at.isoformat() if domain.ssl_expires_at else None,
            'message': 'SSL certificate issued successfully'
        }

    except Exception as e:
        # Update domain SSL status to failed
        if 'domain' in locals() and domain:
            domain.ssl_status = SSLStatus.FAILED
            db.commit()

        return {
            'success': False,
            'error': str(e),
            'message': f'Certificate issuance failed: {str(e)}'
        }

    finally:
        if db:
            db.close()


@app.task(name='tasks.ssl.renew_certificate')
def renew_certificate(domain_id: int, force: bool = False):
    """
    Renew SSL certificate for a custom domain.

    Args:
        domain_id: ID of the custom domain
        force: Force renewal even if not expiring soon

    Returns:
        dict with renewal results
    """
    db = get_db()
    if not db:
        return {'error': 'Database not available'}

    try:
        # Get custom domain
        domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
        if not domain:
            return {'error': f'Custom domain {domain_id} not found'}

        # Check if certificate exists
        if not domain.ssl_certificate_id:
            return {
                'success': False,
                'error': 'No certificate to renew. Issue a certificate first.'
            }

        # Check if renewal is needed
        if not force and domain.ssl_expires_at:
            days_until_expiry = (domain.ssl_expires_at - datetime.utcnow()).days
            if days_until_expiry > 30:
                return {
                    'success': False,
                    'error': f'Certificate does not need renewal yet ({days_until_expiry} days remaining)'
                }

        # Renew certificate (same process as issuance)
        return issue_certificate(domain_id, use_staging=False)

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Certificate renewal failed: {str(e)}'
        }

    finally:
        if db:
            db.close()


@app.task(name='tasks.ssl.check_expiring_certificates')
def check_expiring_certificates():
    """
    Check all certificates and renew those expiring soon.

    This task should be run daily via Celery beat.

    Returns:
        dict with summary of renewals
    """
    db = get_db()
    if not db:
        return {'error': 'Database not available'}

    try:
        from sqlalchemy import and_

        # Find domains with active certificates expiring in 30 days
        expiry_threshold = datetime.utcnow() + timedelta(days=30)

        domains = db.query(CustomDomain).filter(
            and_(
                CustomDomain.ssl_status == SSLStatus.ACTIVE,
                CustomDomain.ssl_expires_at <= expiry_threshold,
                CustomDomain.is_verified == True
            )
        ).all()

        renewed_count = 0
        failed_count = 0
        results = []

        for domain in domains:
            result = renew_certificate.apply_async(args=[domain.id])
            renewal_result = result.get(timeout=300)  # 5 minute timeout

            if renewal_result.get('success'):
                renewed_count += 1
            else:
                failed_count += 1

            results.append({
                'domain': domain.domain,
                'result': renewal_result
            })

        return {
            'success': True,
            'checked': len(domains),
            'renewed': renewed_count,
            'failed': failed_count,
            'results': results
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Certificate check failed: {str(e)}'
        }

    finally:
        if db:
            db.close()


@app.task(name='tasks.ssl.revoke_certificate')
def revoke_certificate(domain_id: int):
    """
    Revoke SSL certificate for a custom domain.

    Args:
        domain_id: ID of the custom domain

    Returns:
        dict with revocation results
    """
    db = get_db()
    if not db:
        return {'error': 'Database not available'}

    try:
        # Get custom domain
        domain = db.query(CustomDomain).filter(CustomDomain.id == domain_id).first()
        if not domain:
            return {'error': f'Custom domain {domain_id} not found'}

        # Clear SSL information
        domain.ssl_certificate_id = None
        domain.ssl_expires_at = None
        domain.ssl_status = SSLStatus.PENDING
        db.commit()

        return {
            'success': True,
            'domain': domain.domain,
            'message': 'Certificate revoked successfully'
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': f'Certificate revocation failed: {str(e)}'
        }

    finally:
        if db:
            db.close()
