"""Define package constants."""
import logging
import base64

LOGGER = logging.getLogger(__package__)

API_HOST = "https://vicapi.vaillant.com.cn"

APP_ID = base64.b64decode("MWY1YjkzNzNmZTk2NGYyNTgxYjBhM2EzZTI2MzYxZTY=").decode("ascii")
APP_KEY = base64.b64decode("OTEwOWZiM2VhNmMwNGNmMWJlMzRjNzFmZjgyYTUxZWM=").decode("ascii")
APP_AUTH = base64.b64decode("WVhCd0xYYzZhVzkwTWxFeFdETlk=").decode("ascii")
DEFAULT_USER_AGENT = base64.b64decode("VmFpbGxhbnRQbHVzLzIzMDMyOTAwNSBDRk5ldHdvcmsvMTQ4NSBEYXJ3aW4vMjMuMS4w").decode("ascii")

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