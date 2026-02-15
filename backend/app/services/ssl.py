import josepy as jose
from acme import client, messages, challenges
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend
from cryptography import x509
from cryptography.x509.oid import NameOID
import datetime
from typing import Dict, Any, Optional, List
import time

from ..config import get_settings

settings = get_settings()


class SSLService:
    """
    Service for SSL certificate management using Let's Encrypt.

    Handles certificate issuance, renewal, and management via ACME protocol.
    """

    # Let's Encrypt endpoints
    LETSENCRYPT_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"
    LETSENCRYPT_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"

    def __init__(self, use_staging: bool = False):
        """
        Initialize SSL service.

        Args:
            use_staging: Use Let's Encrypt staging environment (for testing)
        """
        self.directory_url = self.LETSENCRYPT_STAGING if use_staging else self.LETSENCRYPT_PRODUCTION
        self.account_key = None
        self.acme_client = None

    def generate_account_key(self) -> jose.JWKRSA:
        """
        Generate RSA key pair for ACME account.

        Returns:
            JOSE JWK RSA key
        """
        # Generate 2048-bit RSA key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Convert to JOSE JWK
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )

        return jose.JWKRSA(key=serialization.load_pem_private_key(
            private_key_pem,
            password=None,
            backend=default_backend()
        ))

    def register_account(self, email: str) -> Dict[str, Any]:
        """
        Register ACME account with Let's Encrypt.

        Args:
            email: Contact email for certificate notifications

        Returns:
            Account registration result
        """
        try:
            # Generate account key if not exists
            if not self.account_key:
                self.account_key = self.generate_account_key()

            # Create ACME client
            network = client.ClientNetwork(self.account_key, user_agent="Miaobu/1.0")
            directory = client.ClientV2.get_directory(self.directory_url, network)
            acme_client = client.ClientV2(directory, network)

            # Register account
            registration = acme_client.new_account(
                messages.NewRegistration.from_data(
                    email=email,
                    terms_of_service_agreed=True
                )
            )

            self.acme_client = acme_client

            return {
                'success': True,
                'account_uri': registration.uri,
                'message': 'ACME account registered successfully'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to register ACME account: {str(e)}'
            }

    def generate_csr(self, domain: str, additional_domains: List[str] = None) -> tuple:
        """
        Generate Certificate Signing Request (CSR) for domain.

        Args:
            domain: Primary domain
            additional_domains: Additional domains (SANs)

        Returns:
            Tuple of (private_key, csr)
        """
        # Generate private key for certificate
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Build domain list
        domains = [domain]
        if additional_domains:
            domains.extend(additional_domains)

        # Generate CSR
        csr_builder = x509.CertificateSigningRequestBuilder()
        csr_builder = csr_builder.subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, domain),
        ]))

        # Add SANs (Subject Alternative Names)
        san_list = [x509.DNSName(d) for d in domains]
        csr_builder = csr_builder.add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )

        # Sign CSR
        csr = csr_builder.sign(private_key, hashes.SHA256(), default_backend())

        return private_key, csr

    def request_certificate(
        self,
        domain: str,
        dns_challenge_callback,
        additional_domains: List[str] = None
    ) -> Dict[str, Any]:
        """
        Request SSL certificate for domain using DNS-01 challenge.

        Args:
            domain: Primary domain
            dns_challenge_callback: Callback to create DNS TXT record
            additional_domains: Additional domains (SANs)

        Returns:
            Certificate issuance result
        """
        try:
            if not self.acme_client:
                return {
                    'success': False,
                    'error': 'ACME client not initialized. Call register_account() first.'
                }

            # Generate CSR
            private_key, csr = self.generate_csr(domain, additional_domains)

            # Request certificate
            order = self.acme_client.new_order(csr.public_bytes(serialization.Encoding.DER))

            # Process authorizations (DNS-01 challenges)
            authorizations = []
            dns_records = []

            for authz in order.authorizations:
                # Get DNS-01 challenge
                dns_challenge = None
                for challenge in authz.body.challenges:
                    if isinstance(challenge.chall, challenges.DNS01):
                        dns_challenge = challenge
                        break

                if not dns_challenge:
                    return {
                        'success': False,
                        'error': 'DNS-01 challenge not available'
                    }

                # Get challenge details
                domain_name = authz.body.identifier.value
                validation_domain = f"_acme-challenge.{domain_name}"
                validation_value = dns_challenge.validation(self.account_key)

                # Create DNS TXT record via callback
                dns_result = dns_challenge_callback(validation_domain, validation_value)
                if not dns_result.get('success'):
                    return {
                        'success': False,
                        'error': f'Failed to create DNS record: {dns_result.get("error")}'
                    }

                dns_records.append({
                    'domain': domain_name,
                    'validation_domain': validation_domain,
                    'validation_value': validation_value
                })

                authorizations.append((authz, dns_challenge))

            # Wait for DNS propagation
            time.sleep(10)  # Give DNS time to propagate

            # Complete challenges
            for authz, dns_challenge in authorizations:
                # Answer challenge
                response = dns_challenge.response(self.account_key)
                self.acme_client.answer_challenge(dns_challenge, response)

            # Poll for authorization completion
            deadline = datetime.datetime.now() + datetime.timedelta(seconds=90)
            for authz, _ in authorizations:
                while datetime.datetime.now() < deadline:
                    authz_status = self.acme_client.poll(authz)
                    if authz_status.body.status == messages.STATUS_VALID:
                        break
                    if authz_status.body.status == messages.STATUS_INVALID:
                        return {
                            'success': False,
                            'error': 'Authorization failed',
                            'dns_records': dns_records
                        }
                    time.sleep(2)

            # Finalize order (get certificate)
            finalized_order = self.acme_client.poll_and_finalize(order)

            # Get certificate
            certificate = finalized_order.fullchain_pem
            private_key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')

            return {
                'success': True,
                'certificate': certificate,
                'private_key': private_key_pem,
                'dns_records': dns_records,
                'message': 'Certificate issued successfully'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Certificate request failed: {str(e)}'
            }

    @staticmethod
    def parse_certificate(certificate_pem: str) -> Dict[str, Any]:
        """
        Parse certificate and extract information.

        Args:
            certificate_pem: PEM-encoded certificate

        Returns:
            Certificate information
        """
        try:
            cert = x509.load_pem_x509_certificate(
                certificate_pem.encode('utf-8'),
                default_backend()
            )

            # Extract domains from certificate
            domains = []
            try:
                san_ext = cert.extensions.get_extension_for_oid(
                    x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
                domains = [name.value for name in san_ext.value]
            except x509.ExtensionNotFound:
                pass

            # Get common name
            try:
                common_name = cert.subject.get_attributes_for_oid(
                    NameOID.COMMON_NAME
                )[0].value
                if common_name not in domains:
                    domains.insert(0, common_name)
            except:
                pass

            return {
                'success': True,
                'domains': domains,
                'issuer': cert.issuer.rfc4514_string(),
                'not_before': cert.not_valid_before,
                'not_after': cert.not_valid_after,
                'serial_number': cert.serial_number,
                'fingerprint': cert.fingerprint(hashes.SHA256()).hex()
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    def check_certificate_expiry(certificate_pem: str) -> Dict[str, Any]:
        """
        Check if certificate is expiring soon.

        Args:
            certificate_pem: PEM-encoded certificate

        Returns:
            Expiry check result
        """
        cert_info = SSLService.parse_certificate(certificate_pem)

        if not cert_info.get('success'):
            return cert_info

        not_after = cert_info['not_after']
        now = datetime.datetime.now(datetime.timezone.utc)

        days_until_expiry = (not_after - now).days
        needs_renewal = days_until_expiry <= 30  # Renew 30 days before expiry

        return {
            'success': True,
            'expires_at': not_after,
            'days_until_expiry': days_until_expiry,
            'needs_renewal': needs_renewal,
            'is_expired': days_until_expiry <= 0
        }

    def renew_certificate(
        self,
        domain: str,
        current_certificate_pem: str,
        dns_challenge_callback,
        additional_domains: List[str] = None
    ) -> Dict[str, Any]:
        """
        Renew SSL certificate.

        Args:
            domain: Primary domain
            current_certificate_pem: Current certificate (for validation)
            dns_challenge_callback: Callback to create DNS TXT record
            additional_domains: Additional domains

        Returns:
            Renewal result (same as request_certificate)
        """
        # Check if renewal is needed
        expiry_check = self.check_certificate_expiry(current_certificate_pem)

        if not expiry_check.get('needs_renewal'):
            return {
                'success': False,
                'error': 'Certificate does not need renewal yet',
                'days_until_expiry': expiry_check.get('days_until_expiry')
            }

        # Request new certificate (same process as initial request)
        return self.request_certificate(domain, dns_challenge_callback, additional_domains)
