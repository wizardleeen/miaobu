from aliyunsdkcore.client import AcsClient
from aliyunsdkalidns.request.v20150109 import (
    AddDomainRecordRequest,
    DeleteDomainRecordRequest,
    DescribeDomainRecordsRequest,
    UpdateDomainRecordRequest
)
from typing import Dict, Any, Optional, List
import time

from ..config import get_settings

settings = get_settings()


class AliDNSService:
    """
    Service for managing Alibaba Cloud DNS records.

    Used for DNS-01 ACME challenges and general DNS management.
    """

    def __init__(self):
        """Initialize Alibaba Cloud DNS client."""
        self.client = AcsClient(
            settings.aliyun_access_key_id,
            settings.aliyun_access_key_secret,
            settings.aliyun_region
        )

    def extract_domain_parts(self, full_domain: str) -> tuple:
        """
        Extract root domain and subdomain from full domain.

        Examples:
            _acme-challenge.www.example.com -> (example.com, _acme-challenge.www)
            www.example.com -> (example.com, www)
            example.com -> (example.com, @)

        Args:
            full_domain: Full domain name

        Returns:
            Tuple of (root_domain, rr) where rr is the record name
        """
        parts = full_domain.split('.')

        if len(parts) <= 2:
            # Root domain (example.com)
            return full_domain, "@"

        # Try common TLD patterns
        # For simplicity, assume last two parts are root domain
        root_domain = '.'.join(parts[-2:])
        rr = '.'.join(parts[:-2])

        return root_domain, rr

    def add_txt_record(
        self,
        domain: str,
        value: str,
        ttl: int = 600
    ) -> Dict[str, Any]:
        """
        Add TXT record to DNS.

        Args:
            domain: Full domain name (e.g., _acme-challenge.example.com)
            value: TXT record value
            ttl: Time to live in seconds

        Returns:
            Operation result with record ID
        """
        try:
            root_domain, rr = self.extract_domain_parts(domain)

            request = AddDomainRecordRequest.AddDomainRecordRequest()
            request.set_accept_format('json')
            request.set_DomainName(root_domain)
            request.set_RR(rr)
            request.set_Type("TXT")
            request.set_Value(value)
            request.set_TTL(ttl)

            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            return {
                'success': True,
                'record_id': result.get('RecordId'),
                'domain': domain,
                'value': value,
                'message': 'TXT record added successfully'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to add TXT record: {str(e)}'
            }

    def delete_txt_record(self, record_id: str) -> Dict[str, Any]:
        """
        Delete TXT record from DNS.

        Args:
            record_id: Record ID to delete

        Returns:
            Operation result
        """
        try:
            request = DeleteDomainRecordRequest.DeleteDomainRecordRequest()
            request.set_accept_format('json')
            request.set_RecordId(record_id)

            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            return {
                'success': True,
                'record_id': record_id,
                'message': 'TXT record deleted successfully'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to delete TXT record: {str(e)}'
            }

    def find_txt_record(
        self,
        domain: str,
        value: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Find TXT record by domain and optionally value.

        Args:
            domain: Full domain name
            value: Optional TXT record value to match

        Returns:
            Search result with record details
        """
        try:
            root_domain, rr = self.extract_domain_parts(domain)

            request = DescribeDomainRecordsRequest.DescribeDomainRecordsRequest()
            request.set_accept_format('json')
            request.set_DomainName(root_domain)
            request.set_RRKeyWord(rr)
            request.set_TypeKeyWord("TXT")

            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            records = result.get('DomainRecords', {}).get('Record', [])

            # Filter by value if provided
            if value:
                records = [r for r in records if r.get('Value') == value]

            if records:
                return {
                    'success': True,
                    'found': True,
                    'records': records,
                    'record_id': records[0].get('RecordId')
                }
            else:
                return {
                    'success': True,
                    'found': False,
                    'records': []
                }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to find TXT record: {str(e)}'
            }

    def cleanup_acme_records(self, domain: str) -> Dict[str, Any]:
        """
        Clean up ACME challenge TXT records for a domain.

        Removes all _acme-challenge TXT records.

        Args:
            domain: Domain name (will look for _acme-challenge.domain)

        Returns:
            Cleanup result
        """
        try:
            acme_domain = f"_acme-challenge.{domain}" if not domain.startswith("_acme-challenge") else domain

            # Find all ACME challenge records
            find_result = self.find_txt_record(acme_domain)

            if not find_result.get('success'):
                return find_result

            records = find_result.get('records', [])
            deleted_count = 0

            for record in records:
                record_id = record.get('RecordId')
                delete_result = self.delete_txt_record(record_id)

                if delete_result.get('success'):
                    deleted_count += 1

            return {
                'success': True,
                'deleted_count': deleted_count,
                'message': f'Cleaned up {deleted_count} ACME challenge records'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to cleanup ACME records: {str(e)}'
            }

    def add_cname_record(
        self,
        domain: str,
        target: str,
        ttl: int = 600
    ) -> Dict[str, Any]:
        """
        Add or update (upsert) a CNAME record.

        If the record already exists (DomainRecordDuplicate), finds the
        existing record and updates its target value instead.

        Args:
            domain: Full domain name
            target: CNAME target
            ttl: Time to live in seconds

        Returns:
            Operation result with record_id
        """
        try:
            root_domain, rr = self.extract_domain_parts(domain)

            request = AddDomainRecordRequest.AddDomainRecordRequest()
            request.set_accept_format('json')
            request.set_DomainName(root_domain)
            request.set_RR(rr)
            request.set_Type("CNAME")
            request.set_Value(target)
            request.set_TTL(ttl)

            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            return {
                'success': True,
                'record_id': result.get('RecordId'),
                'domain': domain,
                'target': target,
                'message': 'CNAME record added successfully'
            }

        except Exception as e:
            if 'DomainRecordDuplicate' in str(e):
                return self._update_existing_cname(root_domain, rr, target, ttl)
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to add CNAME record: {str(e)}'
            }

    def _update_existing_cname(
        self, root_domain: str, rr: str, target: str, ttl: int
    ) -> Dict[str, Any]:
        """Find and update an existing CNAME record."""
        try:
            # Find the existing record
            desc_req = DescribeDomainRecordsRequest.DescribeDomainRecordsRequest()
            desc_req.set_accept_format('json')
            desc_req.set_DomainName(root_domain)
            desc_req.set_RRKeyWord(rr)
            desc_req.set_TypeKeyWord("CNAME")

            response = self.client.do_action_with_exception(desc_req)
            result = eval(response.decode('utf-8'))
            records = result.get('DomainRecords', {}).get('Record', [])

            # Match exact RR (keyword search can be partial)
            record = next((r for r in records if r.get('RR') == rr), None)
            if not record:
                return {'success': False, 'error': f'Duplicate reported but record not found for RR={rr}'}

            record_id = record['RecordId']

            # Update with new target
            upd_req = UpdateDomainRecordRequest.UpdateDomainRecordRequest()
            upd_req.set_accept_format('json')
            upd_req.set_RecordId(record_id)
            upd_req.set_RR(rr)
            upd_req.set_Type("CNAME")
            upd_req.set_Value(target)
            upd_req.set_TTL(ttl)

            self.client.do_action_with_exception(upd_req)
            return {
                'success': True,
                'record_id': record_id,
                'domain': f'{rr}.{root_domain}',
                'target': target,
                'message': 'CNAME record updated (upsert)',
            }
        except Exception as ue:
            return {
                'success': False,
                'error': str(ue),
                'message': f'Failed to update existing CNAME: {str(ue)}',
            }

    def delete_cname_record(self, domain: str) -> Dict[str, Any]:
        """
        Delete a CNAME record by domain name.

        Looks up the record via DescribeDomainRecords, then deletes it.
        Returns success if the record doesn't exist (idempotent).

        Args:
            domain: Full domain name (e.g. myapp.metavm.tech)

        Returns:
            Operation result
        """
        try:
            root_domain, rr = self.extract_domain_parts(domain)

            desc_req = DescribeDomainRecordsRequest.DescribeDomainRecordsRequest()
            desc_req.set_accept_format('json')
            desc_req.set_DomainName(root_domain)
            desc_req.set_RRKeyWord(rr)
            desc_req.set_TypeKeyWord("CNAME")

            response = self.client.do_action_with_exception(desc_req)
            result = eval(response.decode('utf-8'))
            records = result.get('DomainRecords', {}).get('Record', [])

            record = next((r for r in records if r.get('RR') == rr), None)
            if not record:
                return {'success': True, 'message': 'CNAME record not found (already deleted)'}

            record_id = record['RecordId']
            del_req = DeleteDomainRecordRequest.DeleteDomainRecordRequest()
            del_req.set_accept_format('json')
            del_req.set_RecordId(record_id)

            self.client.do_action_with_exception(del_req)
            return {
                'success': True,
                'record_id': record_id,
                'domain': domain,
                'message': 'CNAME record deleted successfully',
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to delete CNAME record: {str(e)}',
            }

    def list_domain_records(
        self,
        domain: str,
        record_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List all DNS records for a domain.

        Args:
            domain: Root domain name
            record_type: Optional filter by record type (A, CNAME, TXT, etc.)

        Returns:
            List of DNS records
        """
        try:
            request = DescribeDomainRecordsRequest.DescribeDomainRecordsRequest()
            request.set_accept_format('json')
            request.set_DomainName(domain)

            if record_type:
                request.set_TypeKeyWord(record_type)

            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            records = result.get('DomainRecords', {}).get('Record', [])

            return {
                'success': True,
                'records': records,
                'total_count': len(records)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to list domain records: {str(e)}'
            }
