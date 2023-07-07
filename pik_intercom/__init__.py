"""Pik Intercom API"""

__version__ = "0.0.4"

import json
import random
import string
from typing import (
    TypeVar,
    ClassVar,
    Tuple,
    MutableMapping,
    Iterable,
    Type,
)

import aiohttp
from multidict import CIMultiDict, CIMultiDictProxy

from .base import *
from .errors import *
from .icm import *
from .iot import *

_LOGGER: Final = logging.getLogger(__name__)

DEFAULT_DEVICE_MODEL: Final = "Python API"
DEFAULT_USER_AGENT: Final = "okhttp/4.9.0"
DEFAULT_CLIENT_APP: Final = "alfred"
DEFAULT_CLIENT_VERSION: Final = "2023.6.1"
DEFAULT_CLIENT_OS: Final = "Android"

_TBaseObject = TypeVar("_TBaseObject", bound=BaseObject)


@dataclass(slots=True)
class PikAccount(BaseObject):
    """Placeholder for data related to user account."""

    phone: Optional[str] = None
    email: Optional[str] = None
    apartment_id: Optional[int] = None
    number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        BaseObject.update_from_dict(self, data)

        self.phone = data.get("phone") or None
        self.email = data.get("email") or None
        self.number = data.get("number") or None
        self.apartment_id = data.get("apartment_id") or None
        self.first_name = data.get("first_name") or None
        self.last_name = data.get("last_name") or None
        self.middle_name = data.get("middle_name") or None


@dataclass(slots=True)
class CustomerDevice(ObjectWithSIP):
    """Placeholder for data related to customer device."""

    account_id: Optional[int] = None
    """Account identifier"""

    uid: Optional[str] = None
    """Unique identifier"""

    apartment_id: Optional[int] = None
    """Apartment identifier (for installed devices)"""

    model: Optional[str] = None
    kind: Optional[str] = None
    firmware_version: Optional[str] = None
    mac_address: Optional[str] = None
    os: Optional[str] = None
    deleted_at: Any = None

    # From sip_account parameter
    sip_user: Optional[str] = None
    sip_proxy: Optional[str] = None
    sip_realm: Optional[str] = None
    sip_enable: bool = False
    sip_alias: Optional[str] = None
    sip_status: Optional[str] = None
    sip_password: Optional[str] = None

    def update_from_dict(self, data: Mapping[str, Any]) -> None:
        ObjectWithSIP.update_from_dict(self, data)

        self.apartment_id = data.get("apartment_id") or None
        self.model = data.get("model") or None
        self.kind = data.get("kind") or None
        self.firmware_version = data.get("firmware_version") or None
        self.mac_address = data.get("mac_address") or None
        self.os = data.get("os") or None
        self.deleted_at = data.get("deleted_at") or None

        if sip_account_data := data.get("sip_account") or None:
            self.sip_user = sip_account_data.get("ex_user") or None
            self.sip_proxy = sip_account_data.get("proxy") or None
            self.sip_realm = sip_account_data.get("realm") or None
            self.sip_enable = bool(sip_account_data.get("ex_enable"))
            self.sip_alias = sip_account_data.get("alias") or None
            self.sip_status = (
                sip_account_data.get("remote_request_status") or None
            )
            self.sip_password = sip_account_data.get("password") or None


class PikIntercomAPI:
    """HTTP API for Pik Intercom"""

    BASE_ICM_URL: ClassVar[str] = "https://intercom.rubetek.com"
    BASE_IOT_URL: ClassVar[str] = "https://iot.rubetek.com"

    __slots__ = (
        "account",
        "authorization",
        "client_app",
        "client_os",
        "client_version",
        "customer_devices",
        "device_id",
        "device_model",
        "icm_buildings",
        "icm_call_sessions",
        "icm_intercoms",
        "icm_properties",
        "iot_call_sessions",
        "iot_cameras",
        "iot_intercoms",
        "iot_meters",
        "iot_relays",
        "password",
        "refresh_token",
        "request_counter",
        "session",
        "user_agent",
        "username",
    )

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        device_id: Optional[str] = None,
        *,
        device_model: str = DEFAULT_DEVICE_MODEL,
        user_agent: str = DEFAULT_USER_AGENT,
        client_app: str = DEFAULT_CLIENT_APP,
        client_version: str = DEFAULT_CLIENT_VERSION,
        client_os: str = DEFAULT_CLIENT_OS,
    ) -> None:
        self.username = username
        self.password = password

        self.session = session

        self.device_id = device_id or "".join(
            random.choices(
                string.ascii_uppercase + string.digits,
                k=16,
            )
        )
        self.client_app = client_app
        self.client_os = client_os
        self.client_version = client_version
        self.device_model = device_model
        self.user_agent = user_agent

        self.authorization: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.request_counter: int = 0

        # General
        self.account: Optional[PikAccount] = None
        self.customer_devices: dict[int, CustomerDevice] = {}

        # Placeholders for ICM requests
        self.icm_buildings: dict[int, IcmBuilding] = {}
        self.icm_call_sessions: dict[int, IcmCallSession] = {}
        self.icm_intercoms: dict[int, IcmIntercom] = {}
        self.icm_properties: dict[int, IcmProperty] = {}

        # Placeholders for IoT requests
        self.iot_call_sessions: dict[int, IotCallSession] = {}
        self.iot_cameras: dict[int, IotCamera] = {}
        self.iot_intercoms: dict[int, IotIntercom] = {}
        self.iot_meters: dict[int, IotMeter] = {}
        self.iot_relays: dict[int, IotRelay] = {}

        # @TODO: add other properties

    @property
    def is_authenticated(self) -> bool:
        """Whether an authorization token is already present."""
        return self.authorization is not None

    @property
    def customer_device(self) -> Optional["CustomerDevice"]:
        """Return current customer device object."""
        for device in self.customer_devices.values():
            if device.uid == self.device_id:
                return device

    def get_last_call_session(
        self,
    ) -> Optional[Union[IotCallSession, IcmCallSession]]:
        """
        Find last call session.

        It will search both IoT and ICM call session stores
        to fetch whatever call session is more recent.

        :return: The most recent call session, if found
        """
        last_call_session = None
        for source in (self.iot_call_sessions, self.icm_call_sessions):
            iterator = iter(source.values())
            if last_call_session is None:
                try:
                    last_call_session = next(iterator)
                except StopIteration:
                    continue
            for call_session in iterator:
                if call_session.created_at > last_call_session.created_at:
                    last_call_session = call_session
        return last_call_session

    def increment_request_counter(self) -> int:
        request_counter = self.request_counter + 1
        self.request_counter = request_counter
        return request_counter

    async def make_request(
        self,
        method: str,
        url: str,
        headers: Optional[CIMultiDict] = None,
        authenticated: bool = True,
        title: str = "request",
        api_version: int = 2,
        **kwargs: Any,
    ) -> Tuple[Any, CIMultiDictProxy[str], int]:
        """
        Request wrapper.

        This injects necessary authentication and validation
        before making an aiohttp request. It is a helper method.

        :param method: HTTP method
        :param url: URL of API endpoint
        :param headers: Request headers (optional)
        :param authenticated: Use authentication (true by default)
        :param title: Logging title ("request" by default)
        :param api_version: API version for request (2 by default)
        :param kwargs: Additional aiohttp.ClientSession.request keyword arguments
        :return: Tuple of (Response data, Response headers, Request counter value)
        """
        if headers is None:
            headers = CIMultiDict()
        elif not isinstance(headers, MutableMapping):
            headers = CIMultiDict(headers)

        headers.update(
            {
                aiohttp.hdrs.USER_AGENT: self.user_agent,
                "API-VERSION": str(api_version),
                "device-client-app": self.client_app,
                "device-client-version": self.client_version,
                "device-client-os": self.client_os,
                "device-client-uid": self.device_id,
            }
        )

        if authenticated:
            if not self.is_authenticated:
                raise PikIntercomException("API not authenticated")

            headers[aiohttp.hdrs.AUTHORIZATION] = self.authorization

        request_counter = self.increment_request_counter()
        log_prefix = f"[{request_counter}] "

        _LOGGER.info(
            log_prefix + f"Performing {title} request: {method} -> {url}"
        )

        try:
            async with self.session.request(
                method,
                url,
                headers=headers,
                raise_for_status=True,
                **kwargs,
            ) as request:
                resp_data = await request.json()

        except json.JSONDecodeError:
            _LOGGER.error(
                log_prefix + f"Could not perform {title} request, "
                f"invalid JSON body: {await request.text()}"
            )
            raise MalformedDataError(
                f"Could not perform {title} request (body decoding failed)"
            )

        else:
            if isinstance(resp_data, dict) and resp_data.get("error"):
                code, description = resp_data.get(
                    "code", "unknown"
                ), resp_data.get("description", "none provided")

                _LOGGER.error(
                    log_prefix + f"Could not perform {title}, "
                    f"code: {code}, "
                    f"description: {description}"
                )
                raise ServerResponseError(
                    f"Could not perform {title} ({code})"
                )

            _LOGGER.info(
                log_prefix + f"Performed {title} request successfully"
            )
            _LOGGER.debug(log_prefix + f"Response data: {resp_data}")

            return resp_data, request.headers, request_counter

    async def iterate_paginated_request(
        self,
        url: str,
        title: str = "paginated request",
        method: str = aiohttp.hdrs.METH_GET,
        params: Optional[Mapping[str, Any]] = None,
        max_pages: Optional[int] = None,
        **kwargs,
    ):
        """
        Asynchronous generator to iterate paginated requests.

        Perform requests until it meets 'no data' condition,
        or max requested pages limit is reached.

        :param url: URL of API endpoint
        :param title:
        :param method: HTTP method ("GET" by default)
        :param params: Query parameters (none by default)
        :param max_pages: Max pages to request (unlimited by default)
        :param kwargs: Additional PikIntercomAPI.make_request keyword arguments
        :return: Generator of response data per each page with data
        """
        params = {} if params is None else dict(params)
        page_number = 0

        while max_pages is None or (page_number < max_pages):
            page_number += 1
            params["page"] = page_number
            (
                resp_data,
                headers,
                request_counter,
            ) = await self.make_request(
                method,
                url,
                title=title,
                params=params,
                **kwargs,
            )

            if not resp_data:
                _LOGGER.debug(
                    f"[{request_counter}] Page does not contain data, stopping"
                )
                break

            _LOGGER.debug(f"page {resp_data}")
            yield resp_data

    async def update_single_item_from_request(
        self,
        url: str,
        container: MutableMapping[int, _TBaseObject],
        data_cls: Type[_TBaseObject],
        title: str = "single item request",
        method: str = aiohttp.hdrs.METH_GET,
        item_id: Optional[int] = None,
        **kwargs,
    ) -> _TBaseObject:
        """
        Perform single request and update single item.

        This is a shorthand to avoid mistakes and reuse code.

        :param url: URL of API endpoint
        :param title:
        :param container:
        :param data_cls:
        :param method:
        :param item_id:
        :param kwargs:
        :return:
        """
        resp_data, _, __ = await self.make_request(
            method,
            url,
            title=title,
            **kwargs,
        )

        if item_id is None:
            item_id = data_cls.get_id_from_data(resp_data)

        try:
            item = container[item_id]
        except KeyError:
            container[item_id] = item = data_cls.create_from_dict(
                self, resp_data
            )
        else:
            item.update_from_dict(resp_data)

        return item

    def iterate_data_list_and_update(
        self,
        container: MutableMapping[int, _TBaseObject],
        data_list: Iterable[Mapping[str, Any]],
        data_cls: Type[_TBaseObject],
    ):
        if not data_list:
            return

        for data in data_list:
            try:
                obj_id = data_cls.get_id_from_data(data)
            except (TypeError, ValueError, KeyError):
                continue

            try:
                obj = container[obj_id]
            except KeyError:
                container[obj_id] = obj = data_cls.create_from_dict(self, data)
            else:
                obj.update_from_dict(data)

            yield obj_id, obj, data

    def _deserialize_customer_device(
        self, data: Mapping[str, Any]
    ) -> Optional["CustomerDevice"]:
        customer_device_id = int(data["id"])

        try:
            customer_device = self.customer_devices[customer_device_id]
        except KeyError:
            customer_device = CustomerDevice.create_from_dict(self, data)
            self.customer_devices[customer_device_id] = customer_device
        else:
            customer_device.update_from_dict(data)

        return customer_device

    async def authenticate(self) -> None:
        try:
            resp_data, headers, request_counter = await self.make_request(
                aiohttp.hdrs.METH_POST,
                f"{self.BASE_ICM_URL}/api/customers/sign_in",
                json={
                    "account": {
                        "phone": self.username,
                        "password": self.password,
                    },
                    "customer_device": {
                        "uid": self.device_id,
                    },
                },
                title="authentication",
                authenticated=False,
            )
        except aiohttp.ClientResponseError as exc:
            _LOGGER.debug(f"Client response: {exc.headers}")
            raise

        if not (authorization := headers.get(aiohttp.hdrs.AUTHORIZATION)):
            _LOGGER.error(
                f"[{request_counter}] Could not perform authentication, "
                f"({aiohttp.hdrs.AUTHORIZATION} header not found)"
            )
            raise PikIntercomException(
                f"Could not perform authentication "
                f"({aiohttp.hdrs.AUTHORIZATION} header not found)"
            )

        self.authorization = authorization

        # Update account data
        account_data = resp_data["account"]

        if account := self.account:
            account.update_from_dict(account_data)
        else:
            self.account = PikAccount.create_from_dict(self, account_data)

        for device_data in resp_data.get("customer_devices") or ():
            self._deserialize_customer_device(device_data)

        _LOGGER.debug(f"[{request_counter}] Authentication successful")

    async def update_customer_device(self) -> Any:
        if not (device_id := self.device_id):
            raise PikIntercomException("device ID not set")
        try:
            (
                resp_data,
                headers,
                request_counter,
            ) = await self.make_request(
                aiohttp.hdrs.METH_GET,
                f"{self.BASE_ICM_URL}/api/customers/devices/lookup",
                title="customer device lookup",
                params={"customer_device[uid]": device_id},
            )
        except aiohttp.ClientResponseError as exc:
            if exc.status != 404:
                raise
            (
                resp_data,
                headers,
                request_counter,
            ) = await self.make_request(
                aiohttp.hdrs.METH_POST,
                f"{self.BASE_ICM_URL}/api/customers/devices",
                title="customer device initialization",
                params={
                    "customer_device[model]": self.device_model,
                    "customer_device[kind]": "mobile",
                    "customer_device[uid]": device_id,
                    "customer_device[os]": self.client_os.lower(),
                    "customer_device[push_version]": "2.0.0",
                },
            )

        return self._deserialize_customer_device(resp_data)

    async def set_customer_device_push_token(self, push_token: str) -> None:
        customer_device_id = None
        for device_id, device in self.customer_devices.items():
            if device.uid == self.device_id:
                customer_device_id = device_id
                break
        if customer_device_id is None:
            raise PikIntercomException("device by id not found")
        await self.make_request(
            aiohttp.hdrs.METH_PATCH,
            f"/api/customers/devices/{customer_device_id}",
            title="customer device push token update",
            params={"customer_device[push_token]": push_token},
        )

    async def fetch_last_active_session(
        self,
    ) -> Optional[Union[IcmActiveCallSession, IotActiveCallSession]]:
        # Current call session is None
        create_task = asyncio.get_running_loop().create_task
        tasks = [
            create_task(self.iot_fetch_last_active_session()),
            create_task(self.icm_fetch_last_active_session()),
        ]

        await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)

        call_session, other_call_session = tasks[0].result(), tasks[1].result()

        if isinstance(call_session, BaseException):
            if isinstance(call_session := other_call_session, BaseException):
                raise call_session
            _LOGGER.debug(
                f"[{self}] Retrieved last call session from ICM: {call_session}"
            )
            return call_session
        elif isinstance(call_session, IotActiveCallSession) and isinstance(
            other_call_session, IcmActiveCallSession
        ):
            if other_call_session.created_at > call_session.created_at:
                _LOGGER.debug(
                    f"[{self}] Retrieved both call from IOT "
                    f"({call_session}) and ICM ({other_call_session}),"
                    f"but ICM appears to be newer"
                )
                return other_call_session
            _LOGGER.debug(
                f"[{self}] Retrieved both call from IOT "
                f"({call_session}) and ICM ({other_call_session}),"
                f"but IOT appears to be newer"
            )
        elif call_session is None:
            if isinstance(other_call_session, IcmActiveCallSession):
                _LOGGER.debug(
                    f"[{self}] Retrieved last call session from ICM: {call_session}"
                )
                return other_call_session
            _LOGGER.debug(
                f"[{self}] Did not receive any last call session data"
            )
            return
        _LOGGER.debug(
            f"[{self}] Retrieved last call session from IOT: {call_session}"
        )
        return call_session

    async def icm_update_properties(self) -> dict[int, IcmProperty]:
        """
        Retrieve properties from ICM API.
        :return:
        """
        resp_data, _, __ = await self.make_request(
            aiohttp.hdrs.METH_GET,
            f"{self.BASE_ICM_URL}/api/customers/properties",
            title="properties fetching",
        )

        retrieved_objects = {}
        for property_type, properties_data in resp_data.items():
            for obj_id, obj, _ in self.iterate_data_list_and_update(
                self.icm_properties, properties_data, IcmProperty
            ):
                retrieved_objects[obj_id] = obj
                obj.category = property_type
        return retrieved_objects

    async def icm_update_building(self, building_id: int) -> IcmBuilding:
        """
        Update data about a single ICM building.
        :param building_id: ICM building identifier
        :return: Updated ICM building object
        """
        return await self.update_single_item_from_request(
            f"{self.BASE_ICM_URL}/api/buildings/{building_id}",
            container=self.icm_buildings,
            data_cls=IcmBuilding,
            title="building fetching",
            item_id=building_id,
        )

    async def icm_update_intercoms(
        self, property_id: Optional[int] = None
    ) -> dict[int, IcmIntercom]:
        """
        Retrieve intercoms from ICM API.
        :param property_id: Property identifier.
        :return:
        """
        retrieved_objects = {}
        if property_id is None:
            create_task = asyncio.get_running_loop().create_task
            if not (
                tasks := [
                    create_task(self.icm_update_intercoms(property_id))
                    for property_id in self.icm_properties
                ]
            ):
                _LOGGER.warning(
                    "Update for intercoms on all properties called but no properties present"
                )
                return retrieved_objects
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in pending:
                task.cancel()
            if exc := next(iter(done)).exception():
                raise exc
            for task in done:
                retrieved_objects.update(task.result())
            return retrieved_objects

        async for resp_data in self.iterate_paginated_request(
            f"{self.BASE_ICM_URL}/api/customers/properties/{property_id}/intercoms",
            "ICM intercoms fetching",
        ):
            for obj_id, obj, _ in self.iterate_data_list_and_update(
                self.icm_intercoms, resp_data, IcmIntercom
            ):
                obj.property_ids.add(property_id)
                retrieved_objects[obj_id] = obj
        return retrieved_objects

    async def icm_update_intercom(self, intercom_id: int) -> IcmIntercom:
        """
        Update data about a single ICM intercom device.
        :param intercom_id: ICM intercom identifier
        :return: Updated ICM intercom object
        """
        return await self.update_single_item_from_request(
            f"{self.BASE_ICM_URL}/api/intercoms/{intercom_id}",
            container=self.icm_intercoms,
            data_cls=IcmIntercom,
            title="building fetching",
            item_id=intercom_id,
        )

    async def icm_unlock_intercom(self, intercom_id: int, mode: str) -> None:
        """
        Send command to property device to unlock.
        :param intercom_id: Property device identifier
        :param mode: <unknown parameter, comes from PropertyDevice data object>
        """
        resp_data, headers, request_counter = await self.make_request(
            aiohttp.hdrs.METH_POST,
            f"{self.BASE_ICM_URL}/api/customers/intercoms/{intercom_id}/unlock",
            data={"id": intercom_id, "door": mode},
            title="intercom unlocking",
        )

        if resp_data.get("request") is not True:
            _LOGGER.error(f"[{request_counter}] Timed out unlocking intercom")
            raise PikIntercomException("Timed out unlocking intercom")

        _LOGGER.debug(f"[{request_counter}] Intercom unlocking successful")

    async def icm_update_call_sessions(
        self, max_pages: Optional[int] = 10
    ) -> dict[int, IcmCallSession]:
        retrieved_objects = {}
        async for resp_data in self.iterate_paginated_request(
            f"{self.BASE_ICM_URL}/api/call_sessions",
            f"intercom call sessions fetching",
            max_pages=max_pages,
        ):
            if not (call_sessions_list := resp_data.get("call_sessions")):
                break

            for obj_id, obj, _ in self.iterate_data_list_and_update(
                self.icm_call_sessions,
                call_sessions_list,
                IcmCallSession,
            ):
                retrieved_objects[obj_id] = obj
        return retrieved_objects

    async def icm_fetch_last_active_session(
        self,
    ) -> Optional["IcmActiveCallSession"]:
        try:
            resp_data, _, __ = await self.make_request(
                aiohttp.hdrs.METH_GET,
                f"{self.BASE_ICM_URL}/api/call_sessions/last_open",
                title="current call session",
            )
        except aiohttp.ClientResponseError as exc:
            if exc.status == 404:
                return None
            raise

        return (
            IcmActiveCallSession.create_from_dict(self, resp_data)
            if resp_data.get("id")
            else None
        )

    async def iot_update_intercoms(self) -> dict[int, IotIntercom]:
        """
        Retrieve intercoms from IOT API.
        :return:
        """
        retrieved_objects = {}
        async for resp_data in self.iterate_paginated_request(
            f"{self.BASE_IOT_URL}/api/alfred/v1/personal/intercoms",
            "IoT intercoms & relays fetching",
        ):
            # Iterate through intercoms
            for (
                intercom_id,
                intercom,
                intercom_data,
            ) in self.iterate_data_list_and_update(
                self.iot_intercoms,
                resp_data,
                IotIntercom,
            ):
                retrieved_objects[intercom_id] = intercom
                # Iterate through relays embedded into intercoms
                for _, relay, data in self.iterate_data_list_and_update(
                    self.iot_relays,
                    intercom_data.get("relays"),
                    IotRelay,
                ):
                    relay.geo_unit_short_name = intercom.geo_unit_short_name
        return retrieved_objects

    async def iot_update_cameras(self) -> dict[int, IotCamera]:
        """
        Retrieve cameras from IOT API.
        :return:
        """
        retrieved_objects = {}
        async for resp_data in self.iterate_paginated_request(
            f"{self.BASE_IOT_URL}/api/alfred/v1/personal/cameras",
            "IoT cameras fetching",
        ):
            # Iterate through cameras
            for obj_id, obj, _ in self.iterate_data_list_and_update(
                self.iot_cameras, resp_data, IotCamera
            ):
                retrieved_objects[obj_id] = obj
        return retrieved_objects

    async def iot_update_meters(self) -> dict[int, IotMeter]:
        """
        Retrieve meters from IOT API.
        :return:
        """
        retrieved_objects = {}
        async for resp_data in self.iterate_paginated_request(
            f"{self.BASE_IOT_URL}/api/alfred/v1/personal/meters",
            "IoT meters fetching",
        ):
            for obj_id, obj, _ in self.iterate_data_list_and_update(
                self.iot_meters, resp_data, IotMeter
            ):
                retrieved_objects[obj_id] = obj
        return retrieved_objects

    async def iot_unlock_relay(self, iot_relay_id: int) -> None:
        """
        Send command to IoT relay to unlock.
        :param iot_relay_id: IoT relay identifier.
        """
        resp_data, headers, request_counter = await self.make_request(
            aiohttp.hdrs.METH_POST,
            f"{self.BASE_IOT_URL}/api/alfred/v1/personal/relays/{iot_relay_id}/unlock",
            title="IoT relay unlocking",
        )

        # @TODO: rule out correct response

        _LOGGER.debug(
            f"[{request_counter}] Intercom unlocking successful (assumed)"
        )

    async def iot_fetch_last_active_session(
        self,
    ) -> Optional["IotActiveCallSession"]:
        try:
            resp_data, _, __ = await self.make_request(
                aiohttp.hdrs.METH_GET,
                f"{self.BASE_IOT_URL}/api/alfred/v1/personal/call_sessions/current",
                title="current call session",
            )
        except aiohttp.ClientResponseError as exc:
            if exc.status == 404:
                return None
            raise

        return IotActiveCallSession.create_from_dict(self, resp_data)

    async def iot_update_call_sessions(
        self, max_pages: Optional[int] = 10
    ) -> dict[int, IotCallSession]:
        retrieved_objects = {}
        async for resp_data in self.iterate_paginated_request(
            f"{self.BASE_IOT_URL}/api/alfred/v1/personal/call_sessions",
            title="IoT call sessions fetching",
            params={"q[s]": "created_at DESC"},
            max_pages=max_pages,
        ):
            for obj_id, obj, _ in self.iterate_data_list_and_update(
                self.iot_call_sessions, resp_data, IotCallSession
            ):
                retrieved_objects[obj_id] = obj
        return retrieved_objects
