"""Define package constants."""
import logging
import base64

LOGGER = logging.getLogger(__package__)

DEFAULT_API_VERSION = "1.3"

HOST_APP = "https://appapi.vaillant.com.cn"
HOST_API = "https://api.vaillant.com.cn"

APP_ID = base64.b64decode("MWY1YjkzNzNmZTk2NGYyNTgxYjBhM2EzZTI2MzYxZTY=").decode("ascii")
DEFAULT_USER_AGENT = "Mozilla/5.0 (Linux; Android 7.1.2; Redmi 4X Build/N2G47H; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/66.0.3359.158 Mobile Safari/537.36"

STATE_CONNECTING = "connecting"
STATE_CONNECTED = "connected"
STATE_SUBSCRIBED = "subscribed"
STATE_STOPPED = "stopped"
STATE_DISCONNECTED = "disconnected"

EVT_DEVICE_ATTR_UPDATE = "device:attr:update"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_TOKEN = "token"
CONF_DID = "did"
CONF_UID = "uid"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_MAC = "mac"
CONF_PRODUCT_NAME = "product_name"
CONF_APP_ID = "app_id"