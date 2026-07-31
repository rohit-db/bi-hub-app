from dataclasses import field
from config import settings
from utils.logging import logger
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from pydantic import BaseModel, field_validator
from threading import Lock
from typing import Optional
from datetime import datetime, timedelta, timezone
import uuid


class Credential(BaseModel):
    token: str
    expiration_time: datetime

    @field_validator("expiration_time")
    @classmethod
    def _tz_aware_datetime(cls, v: datetime) -> datetime:
        return v if v.tzinfo else v.astimezone(timezone.utc)

    def valid_for(self) -> timedelta:
        return self.expiration_time - datetime.now(timezone.utc)


class LakebaseCredentialProvider:
    def __init__(self):
        self.lock = Lock()
        self._cached: Optional[Credential] = None

    def _client(self) -> WorkspaceClient:
        return WorkspaceClient()

    def get_credential(self) -> Credential:
        with self.lock:
            if self._cached and self._cached.valid_for() > timedelta(minutes=1):
                return self._cached
            
            w = self._client()
            request_id = str(uuid.uuid4())
            cred = w.database.generate_database_credential(
                request_id=request_id, instance_names=[settings.pg_database_instance]
                )
            self._cached = Credential(token=cred.token, expiration_time=cred.expiration_time)
            return self._cached
    
    def invalidate(self) -> None:
        with self.lock:
            self._cached = None