"""
Manul server API client.

Wraps the internal API at the Manul server for app management and deployment.
"""
import httpx

from ..config import get_settings

settings = get_settings()


class ManulService:
    """Service for interacting with the Manul persistent language server."""

    def __init__(self):
        self.base_url = settings.manul_server_host.rstrip("/")
        self.owner_id = settings.manul_owner_id

    def create_app(self, name: str) -> dict:
        """Create a new app on the Manul server.

        Returns:
            {"success": True, "app_id": <int>} on success
            {"success": False, "error": "..."} on failure
        """
        url = f"{self.base_url}/internal-api/app/save"
        payload = {"id": None, "name": name, "ownerId": self.owner_id}
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                # Server may return a plain integer (app_id) or a dict
                if isinstance(data, int):
                    return {"success": True, "app_id": data}
                return {"success": True, "app_id": data.get("id") or data.get("app_id")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_app_name(self, app_id: int, new_name: str) -> dict:
        """Update an app's name on the Manul server."""
        url = f"{self.base_url}/internal-api/app/update-name"
        payload = {"id": app_id, "newName": new_name}
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_app(self, app_id: int) -> dict:
        """Delete an app from the Manul server."""
        url = f"{self.base_url}/internal-api/app/delete/{app_id}"
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.delete(url)
                resp.raise_for_status()
                return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def deploy(self, app_id: int, mva_data: bytes, no_backup: bool = False) -> dict:
        """Deploy an .mva binary to the Manul server.

        Returns:
            {"success": True, "deploy_id": "..."} on success
            {"success": False, "error": "..."} on failure
        """
        no_backup_str = "true" if no_backup else "false"
        url = f"{self.base_url}/internal-api/deploy/{app_id}?no-backup={no_backup_str}"
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    url,
                    content=mva_data,
                    headers={"Content-Type": "application/octet-stream"},
                )
                resp.raise_for_status()
                deploy_id = resp.text.strip().strip('"')
                return {"success": True, "deploy_id": deploy_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_deploy_status(self, app_id: int, deploy_id: str) -> str:
        """Get the status of a deployment.

        Returns the status string from the Manul server.
        """
        url = f"{self.base_url}/internal-api/deploy/status/{app_id}/{deploy_id}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text.strip().strip('"')

    def revert(self, app_id: int) -> dict:
        """Revert the app to its previous deployment."""
        url = f"{self.base_url}/internal-api/deploy/revert/{app_id}"
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url)
                resp.raise_for_status()
                return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
