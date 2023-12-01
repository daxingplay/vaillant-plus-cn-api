"""Module to help store and retrieve credentials"""

from __future__ import annotations
from dataclasses import dataclass, field

import json
import base64

from .const import APP_ID, CONF_USERNAME, CONF_PASSWORD, CONF_UID, CONF_TOKEN, CONF_APP_ID, CONF_DID, CONF_MAC

@dataclass
class User:
    token: Token
    devices: list[Device] = field(default_factory=list)

@dataclass
class Device:
    id: str
    mac: str
    product_key: str
    product_id: int
    product_name: str
    product_verbose_name: str
    is_online: bool
    is_manager: bool
    group_id: int
    sno: str
    create_time: str
    last_offline_time: str
    model_alias: str
    model: str
    serial_number: str
    services_count: int

@dataclass
class Token:
    app_id: str
    username: str
    password: str
    access_token: str = ""
    uid: str = ""

    def serialize(self) -> str:
        """Serialize token object into a JSON string."""

        s = json.dumps({
            f"{CONF_APP_ID}": self.app_id,
            f"{CONF_USERNAME}": self.username,
            f"{CONF_PASSWORD}": self.password,
            f"{CONF_TOKEN}": self.access_token,
            f"{CONF_UID}": self.uid,
        })
        return base64.b64encode(s.encode("ascii")).decode("ascii")

    @classmethod
    def deserialize(cls, token: str) -> Token:
        """Deserialize JSON string into a token object."""

        data = json.loads(base64.b64decode(token.encode("ascii")))
        return Token(
            app_id=data[CONF_APP_ID],
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            access_token=data[CONF_TOKEN],
            uid=data[CONF_UID],
        )
