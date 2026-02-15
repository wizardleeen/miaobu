import dns.resolver
import secrets
from typing import Optional, Dict, Any
from datetime import datetime, timedelta


class DNSService:
    """Service for DNS verification and management."""

    @staticmethod
    def generate_verification_token() -> str:
        """
        Generate a unique verification token for DNS verification.

        Returns a URL-safe token that can be used in TXT records.
        """
        return f"miaobu-verification={secrets.token_urlsafe(32)}"

    @staticmethod
    def verify_txt_record(domain: str, expected_token: str, timeout: int = 5) -> Dict[str, Any]:
        """
        Verify that a TXT record exists for a domain with the expected token.

        Args:
            domain: The domain to check (e.g., "example.com" or "_miaobu-verification.example.com")
            expected_token: The token to look for in TXT records
            timeout: DNS query timeout in seconds

        Returns:
            Dict with verification status and details
        """
        try:
            # Configure resolver with timeout
            resolver = dns.resolver.Resolver()
            resolver.timeout = timeout
            resolver.lifetime = timeout

            # For root domain verification, check _miaobu-verification subdomain
            if not domain.startswith("_miaobu-verification."):
                verification_domain = f"_miaobu-verification.{domain}"
            else:
                verification_domain = domain

            # Query TXT records
            try:
                answers = resolver.resolve(verification_domain, "TXT")
            except dns.resolver.NXDOMAIN:
                # Try root domain if subdomain doesn't exist
                if verification_domain.startswith("_miaobu-verification."):
                    root_domain = domain
                    answers = resolver.resolve(root_domain, "TXT")
                else:
                    raise

            # Check if any TXT record contains the expected token
            found_records = []
            for rdata in answers:
                for txt_string in rdata.strings:
                    txt_value = txt_string.decode("utf-8")
                    found_records.append(txt_value)

                    # Check if this record matches our token
                    if txt_value == expected_token or expected_token in txt_value:
                        return {
                            "success": True,
                            "verified": True,
                            "message": f"Verification token found in TXT record",
                            "record": txt_value,
                            "checked_domain": verification_domain,
                        }

            # Token not found in any TXT records
            return {
                "success": True,
                "verified": False,
                "message": f"TXT records found but verification token not present",
                "found_records": found_records,
                "expected_token": expected_token,
                "checked_domain": verification_domain,
            }

        except dns.resolver.NXDOMAIN:
            return {
                "success": True,
                "verified": False,
                "message": f"No DNS records found for domain",
                "checked_domain": verification_domain,
            }

        except dns.resolver.NoAnswer:
            return {
                "success": True,
                "verified": False,
                "message": f"Domain exists but has no TXT records",
                "checked_domain": verification_domain,
            }

        except dns.resolver.Timeout:
            return {
                "success": False,
                "verified": False,
                "error": "DNS query timeout",
                "message": "DNS server did not respond in time",
            }

        except Exception as e:
            return {
                "success": False,
                "verified": False,
                "error": str(e),
                "message": f"DNS verification failed: {str(e)}",
            }

    @staticmethod
    def verify_cname_record(domain: str, expected_target: str, timeout: int = 5) -> Dict[str, Any]:
        """
        Verify that a CNAME record points to the expected target.

        Args:
            domain: The domain to check (e.g., "www.example.com")
            expected_target: The expected CNAME target (e.g., "miaobu.app")
            timeout: DNS query timeout in seconds

        Returns:
            Dict with verification status and details
        """
        try:
            # Configure resolver with timeout
            resolver = dns.resolver.Resolver()
            resolver.timeout = timeout
            resolver.lifetime = timeout

            # Query CNAME records
            answers = resolver.resolve(domain, "CNAME")

            # Check if CNAME points to expected target
            for rdata in answers:
                cname_target = str(rdata.target).rstrip(".")

                if cname_target == expected_target or cname_target.endswith(f".{expected_target}"):
                    return {
                        "success": True,
                        "verified": True,
                        "message": f"CNAME record points to {cname_target}",
                        "target": cname_target,
                    }

            # CNAME exists but points elsewhere
            cname_targets = [str(rdata.target).rstrip(".") for rdata in answers]
            return {
                "success": True,
                "verified": False,
                "message": f"CNAME record exists but points to wrong target",
                "found_targets": cname_targets,
                "expected_target": expected_target,
            }

        except dns.resolver.NXDOMAIN:
            return {
                "success": True,
                "verified": False,
                "message": f"Domain does not exist",
            }

        except dns.resolver.NoAnswer:
            # Try A record as fallback (might be apex domain)
            try:
                answers = resolver.resolve(domain, "A")
                a_records = [str(rdata) for rdata in answers]
                return {
                    "success": True,
                    "verified": False,
                    "message": f"Domain has A record instead of CNAME",
                    "note": "Apex domains cannot use CNAME. Use A record pointing to CDN IP.",
                    "found_a_records": a_records,
                }
            except:
                return {
                    "success": True,
                    "verified": False,
                    "message": f"Domain exists but has no CNAME record",
                }

        except dns.resolver.Timeout:
            return {
                "success": False,
                "verified": False,
                "error": "DNS query timeout",
            }

        except Exception as e:
            return {
                "success": False,
                "verified": False,
                "error": str(e),
                "message": f"DNS verification failed: {str(e)}",
            }

    @staticmethod
    def check_domain_status(domain: str) -> Dict[str, Any]:
        """
        Check comprehensive DNS status for a domain.

        Args:
            domain: The domain to check

        Returns:
            Dict with DNS status details
        """
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = 5
            resolver.lifetime = 5

            status = {
                "domain": domain,
                "exists": False,
                "has_a_record": False,
                "has_cname_record": False,
                "has_txt_record": False,
                "records": {},
            }

            # Check A records
            try:
                answers = resolver.resolve(domain, "A")
                status["exists"] = True
                status["has_a_record"] = True
                status["records"]["A"] = [str(rdata) for rdata in answers]
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                pass

            # Check CNAME records
            try:
                answers = resolver.resolve(domain, "CNAME")
                status["exists"] = True
                status["has_cname_record"] = True
                status["records"]["CNAME"] = [str(rdata.target).rstrip(".") for rdata in answers]
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                pass

            # Check TXT records
            try:
                answers = resolver.resolve(domain, "TXT")
                status["exists"] = True
                status["has_txt_record"] = True
                txt_records = []
                for rdata in answers:
                    for txt_string in rdata.strings:
                        txt_records.append(txt_string.decode("utf-8"))
                status["records"]["TXT"] = txt_records
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                pass

            return {
                "success": True,
                **status,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    @staticmethod
    def extract_root_domain(domain: str) -> str:
        """
        Extract root domain from a subdomain.

        Examples:
            www.example.com -> example.com
            api.staging.example.com -> example.com
            example.com -> example.com
        """
        parts = domain.split(".")
        if len(parts) >= 2:
            # Return last two parts (handles most cases)
            return ".".join(parts[-2:])
        return domain

    @staticmethod
    def is_apex_domain(domain: str) -> bool:
        """
        Check if domain is an apex/root domain (no subdomain).

        Examples:
            example.com -> True
            www.example.com -> False
            api.example.com -> False
        """
        parts = domain.split(".")
        return len(parts) == 2
