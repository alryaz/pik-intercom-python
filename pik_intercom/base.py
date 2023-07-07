__all__ = (
    "BaseObject",
    "ObjectWithSnapshot",
    "ObjectWithUnlocker",
    "ObjectWithVideo",
    "ObjectWithSIP",
    "BaseCallSession",
)

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TYPE_CHECKING, Final, Mapping, Any

import aiohttp

from .errors import PikIntercomException

if TYPE_CHECKING:
    from . import PikIntercomAPI

_LOGGER: Final = logging.getLogger(__name__)


@dataclass(slots=True)
class BaseObject(ABC):
    """Base class for PIK Intercom Objects"""

    api: "PikIntercomAPI"
    id: int
    source_data: Any = None

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        """Update object attributes from provided source dictionary."""
        self.source_data = data

    @classmethod
    def get_id_from_data(cls, data: Mapping[str, Any]) -> int:
        return int(data["id"])

    @classmethod
    def create_from_dict(
        cls, api: "PikIntercomAPI", data: Mapping[str, Any], **kwargs
    ):
        """Create new object from provided source dictionary."""
        if "id" not in kwargs:
            kwargs["id"] = cls.get_id_from_data(data)
        obj = cls(api=api, **kwargs)
        obj.update_from_dict(data)
        return obj


class ObjectWithSnapshot(BaseObject, ABC):
    @property
    @abstractmethod
    def snapshot_url(self) -> Optional[str]:
        raise NotImplementedError

    @property
    def has_camera(self) -> bool:
        return bool(self.snapshot_url) or getattr(super(), "has_camera", False)

    async def get_snapshot(self) -> bytes:
        snapshot_url = self.snapshot_url
        api = self.api

        if not snapshot_url:
            # @TODO: add diversion to get snapshot off RTSP
            raise PikIntercomException("Photo URL is empty")

        request_counter = api.increment_request_counter()
        log_prefix = f"[{request_counter}] "

        title = "camera snapshot retrieval"
        try:
            async with api.session.get(
                snapshot_url, raise_for_status=True
            ) as request:
                return await request.read()

        except asyncio.TimeoutError:
            _LOGGER.error(
                log_prefix + f"Could not perform {title}, "
                f"waited for {api.session.timeout.total} seconds"
            )
            raise PikIntercomException(
                f"Could not perform {title} (timed out)"
            )

        except aiohttp.ClientError as e:
            _LOGGER.error(
                log_prefix + f"Could not perform {title}, client error: {e}"
            )
            raise PikIntercomException(
                f"Could not perform {title} (client error)"
            )


class ObjectWithVideo(BaseObject, ABC):
    @property
    @abstractmethod
    def stream_url(self) -> Optional[str]:
        raise NotImplementedError

    @property
    def has_camera(self) -> bool:
        return bool(self.stream_url) or getattr(super(), "has_camera", False)


class ObjectWithUnlocker(BaseObject, ABC):
    @abstractmethod
    async def unlock(self) -> None:
        raise NotImplementedError


class ObjectWithSIP(BaseObject, ABC):
    @property
    @abstractmethod
    def sip_user(self) -> Optional[str]:
        raise NotImplementedError

    @property
    def sip_password(self) -> Optional[str]:
        if user := self.sip_user:
            for device in self.api.customer_devices.values():
                if device.sip_user == user and (
                    password := device.sip_password
                ):
                    return password


@dataclass(slots=True)
class BaseCallSession(ObjectWithSnapshot, ObjectWithUnlocker, ABC):
    intercom_id: Optional[int] = None
    # property_id: Optional[int] = None
    notified_at: Optional[datetime] = None
    pickedup_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        ObjectWithSnapshot.update_from_dict(self, data)
        ObjectWithUnlocker.update_from_dict(self, data)

        self.intercom_id = (
            int(data["intercom_id"]) if data.get("intercom_id") else None
        )
        for timestamp in (
            "notified_at",
            "pickedup_at",
            "finished_at",
            "deleted_at",
            "created_at",
        ):
            setattr(
                self,
                timestamp,
                datetime.fromisoformat(data[timestamp])
                if data.get(timestamp)
                else None,
            )
