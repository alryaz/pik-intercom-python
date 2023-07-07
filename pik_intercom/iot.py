import asyncio
import logging
from abc import ABC
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional, Any, List, Mapping, Final, Union, Tuple

try:
    from enum import StrEnum
except ImportError:
    from strenum import StrEnum

from .base import (
    BaseObject,
    ObjectWithSnapshot,
    ObjectWithVideo,
    ObjectWithUnlocker,
    ObjectWithSIP,
    BaseCallSession,
)
from .errors import (
    PikIntercomException,
)

_LOGGER: Final = logging.getLogger(__name__)


class IotMeterKind(StrEnum):
    """Known kinds of IoT meters."""

    HOT = "hot"
    COLD = "cold"
    HEAT = "heat"
    ELECTRO = "electro"


@dataclass(slots=True)
class IotMeter(BaseObject):
    """IoT meter representation."""

    serial: Optional[str] = None
    """Meter serial number"""

    kind: Optional[IotMeterKind] = None
    """Type of meter"""

    pipe_identifier: Optional[int] = None
    """Identifier of pipe (for water meters)"""

    status: Optional[str] = None
    """Current status (for meters with communication)"""

    title: Optional[str] = None
    """Meter name"""

    current_value: Optional[str] = None
    """Current (total) value"""

    month_value: Optional[str] = None
    """Total usage this month"""

    geo_unit_short_name: Optional[str] = None
    """Location short name"""

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        BaseObject.update_from_dict(self, data)

        try:
            pipe_identifier = int(data.get("pipe_identifier"))
        except (TypeError, ValueError):
            pipe_identifier = None

        self.serial = data.get("serial") or None
        self.kind = data.get("kind") or None
        self.pipe_identifier = pipe_identifier
        self.status = data.get("status") or None
        self.title = data.get("title") or None
        self.current_value = data.get("current_value") or None
        self.month_value = data.get("month_value") or None
        self.geo_unit_short_name = data.get("geo_unit_short_name") or None

    @staticmethod
    def _convert_value(value: Any) -> float:
        """
        Convert incoming value formatted as human-readable string.
        :param value: Incoming value
        :return: Numeric representation (float)
        """
        if value is None:
            raise TypeError("cannot convert NoneType to float")
        return float(str(value).rpartition(" ")[0].replace(" ", ""))

    @property
    def current_value_numeric(self) -> Optional[float]:
        """Convert current value to numeric representation."""
        return (
            IotMeter._convert_value(value)
            if (value := self.current_value)
            else None
        )

    @property
    def month_value_numeric(self) -> Optional[float]:
        """Convert month value to numeric representation."""
        return (
            IotMeter._convert_value(value)
            if (value := self.month_value)
            else None
        )


@dataclass(slots=True)
class BaseIotCamera(ObjectWithSnapshot, ABC):
    name: Optional[str] = None
    snapshot_url: Optional[str] = None

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        ObjectWithSnapshot.update_from_dict(self, data)

        self.name = data.get("name") or None
        self.snapshot_url = data.get("live_snapshot_url") or None


@dataclass(slots=True)
class BaseIotCameraWithRTSP(BaseIotCamera, ObjectWithVideo, ABC):
    stream_url: Optional[str] = None

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        BaseIotCamera.update_from_dict(self, data)
        ObjectWithVideo.update_from_dict(self, data)

        self.stream_url = data.get("rtsp_url") or None


class IotIntercomStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"


@dataclass(slots=True)
class IotIntercom(BaseIotCamera, ObjectWithSIP, ObjectWithUnlocker):
    client_id: Optional[int] = None
    is_face_detection: bool = False
    relay_ids: tuple[int, ...] = ()

    # From geo_unit parameter
    geo_unit_id: Optional[int] = None
    geo_unit_short_name: Optional[str] = None
    geo_unit_full_name: Optional[str] = None

    # From sip_account parameter
    sip_proxy: Optional[str] = None
    sip_user: Optional[str] = None

    # Non-expected properties
    status: Optional[Union[IotIntercomStatus, str]] = None
    webrtc_supported: Optional[bool] = None

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        BaseIotCamera.update_from_dict(self, data)
        ObjectWithSIP.update_from_dict(self, data)
        ObjectWithUnlocker.update_from_dict(self, data)

        self.client_id = data.get("client_id") or None
        self.is_face_detection = bool(data.get("is_face_detection"))
        self.status = data.get("status") or None
        self.webrtc_supported = (
            bool(data["webrtc_supported"])
            if "webrtc_supported" in data
            else None
        )

        if relays := data.get("relays"):
            relay_ids = set()
            for relay_data in relays:
                try:
                    relay_ids.add(int(relay_data["id"]))
                except (LookupError, ValueError, TypeError):
                    continue
            self.relay_ids = tuple(sorted(relay_ids))
        else:
            self.relay_ids = ()

        if (sip_data := data.get("sip_account")) and (
            sip_data := sip_data.get("settings")
        ):
            self.sip_user = sip_data.get("ex_user")
            self.sip_proxy = sip_data.get("proxy")

        if geo_unit_data := data.get("geo_unit"):
            self.geo_unit_id = geo_unit_data.get("id") or None
            self.geo_unit_full_name = geo_unit_data.get("full_name") or None
            self.geo_unit_short_name = geo_unit_data.get("short_name") or None

    @property
    def relays(self) -> List["IotRelay"]:
        relay_ids = self.relay_ids
        return [
            relay
            for key, relay in self.api.iot_relays.items()
            if key in relay_ids
        ]

    @property
    def stream_url(self) -> Optional[str]:
        # Return relay matching snapshot url
        if snapshot_url := self.snapshot_url:
            for relay in self.relays:
                if relay.snapshot_url == snapshot_url:
                    return relay.stream_url

        # Return first relay
        for relay in self.relays:
            if relay.stream_url:
                return relay.stream_url

    async def unlock(self) -> None:
        if not (relay_ids := self.relay_ids):
            raise RuntimeError("intercom does not have any relays")
        await asyncio.gather(*map(self.api.iot_unlock_relay, relay_ids))


@dataclass(slots=True)
class IotRelay(BaseIotCameraWithRTSP, ObjectWithUnlocker):
    # From geo_unit parameter
    geo_unit_id: Optional[int] = None
    geo_unit_full_name: Optional[str] = None
    property_geo_units: Optional[Mapping[int, Tuple[str, str]]] = None

    # From user_settings parameter
    custom_name: Optional[str] = None
    is_favorite: bool = False
    is_hidden: bool = False

    # Propagated from parent intercom
    geo_unit_short_name: Optional[str] = None

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        BaseIotCameraWithRTSP.update_from_dict(self, data)
        ObjectWithUnlocker.update_from_dict(self, data)

        if property_geo_units := data.get("property_geo_units"):
            units = {}
            for geo_unit_data in property_geo_units:
                units[geo_unit_data["id"]] = (
                    geo_unit_data["post_name"],
                    geo_unit_data["type"],
                )
            self.property_geo_units = MappingProxyType(units)
        else:
            self.property_geo_units = None

        # Parse geo_unit parameter
        geo_unit_data = data.get("geo_unit") or {}
        self.geo_unit_id = geo_unit_data.get("id") or None
        self.geo_unit_full_name = geo_unit_data.get("full_name") or None

        # Parse user_settings parameter
        relay_settings_data = data.get("user_settings") or {}
        self.custom_name = relay_settings_data.get("custom_name") or None
        self.is_favorite = bool(relay_settings_data.get("is_favorite"))
        self.is_hidden = bool(relay_settings_data.get("is_hidden"))

    @property
    def property_geo_unit(self) -> Optional[Tuple[int, str, str]]:
        for geo_unit_id, (
            geo_unit_name,
            geo_unit_type,
        ) in self.property_geo_units.items():
            return geo_unit_id, geo_unit_name, geo_unit_type

    @property
    def intercoms(self) -> List["IotIntercom"]:
        """Retrieve list of related intercoms."""
        relay_id = self.id
        return [
            intercom
            for intercom in self.api.iot_intercoms.values()
            if relay_id in intercom.relay_ids
        ]

    @property
    def intercom(self) -> Optional["IotIntercom"]:
        """Return first intercom that contains this relay."""
        relay_id = self.id
        for intercom in self.api.iot_intercoms.values():
            if relay_id in intercom.relay_ids:
                return intercom

    @property
    def friendly_name(self) -> str:
        return self.custom_name or self.name

    async def unlock(self) -> None:
        """Unlock IoT relay"""
        return await self.api.iot_unlock_relay(self.id)


@dataclass(slots=True)
class IotCamera(BaseIotCameraWithRTSP):
    geo_unit_short_name: Optional[str] = None

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        BaseIotCameraWithRTSP.update_from_dict(self, data)

        self.geo_unit_short_name = data.get("geo_unit_short_name") or None


@dataclass(slots=True)
class IotCallSession(BaseCallSession):
    geo_unit_id: Optional[int] = None
    geo_unit_short_name: Optional[str] = None
    snapshot_url: Optional[str] = None
    identifier: Optional[str] = None
    provider: Optional[str] = None

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        BaseCallSession.update_from_dict(self, data)

        self.geo_unit_id = data.get("geo_unit_id") or None
        self.geo_unit_short_name = data.get("geo_unit_short_name") or None
        self.snapshot_url = data.get("snapshot_url") or None
        self.identifier = data.get("identifier") or None
        self.provider = data.get("iot_pik") or None

        # Bypass lack of attribute
        if self.created_at is None and (notified_at := self.notified_at):
            self.created_at = notified_at

    async def unlock(self) -> None:
        await self.api.iot_intercoms[self.intercom_id].unlock()


@dataclass(slots=True)
class IotActiveCallSession(IotCallSession):
    intercom_name: Optional[str] = None
    property_name: Optional[str] = None
    sip_proxy: Optional[str] = None
    target_relay_ids: tuple[int, ...] = ()

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        IotCallSession.update_from_dict(self, data)

        self.intercom_name = data.get("intercom_name") or None
        self.property_name = data.get("property_name") or None
        self.sip_proxy = data.get("proxy") or None
        self.target_relay_ids = (
            (
                int(relay_data["id"])
                for relay_data in data["target_relays"]
                if relay_data
            )
            if data.get("target_relays")
            else ()
        )

    @property
    def target_relays(self) -> List["IotRelay"]:
        relay_ids = self.target_relay_ids
        return [
            relay
            for key, relay in self.api.iot_relays.items()
            if key in relay_ids
        ]

    async def unlock(self) -> None:
        if not self.target_relays:
            raise PikIntercomException("no target relays provided")

        errors = []
        for task in (
            await asyncio.wait(
                [
                    asyncio.create_task(relay.unlock())
                    for relay in self.target_relays
                ],
                return_when=asyncio.ALL_COMPLETED,
            )
        )[0]:
            if (exc := task.exception()) and not isinstance(
                exc, asyncio.CancelledError
            ):
                _LOGGER.error(
                    f"Error occurred on unlocking: {exc}", exc_info=exc
                )
                errors.append(exc)

        if errors:
            raise PikIntercomException(
                f"Error(s) occurred while unlocking: {', '.join(map(str, errors))}"
            )
