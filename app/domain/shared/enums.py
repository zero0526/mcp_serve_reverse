from enum import Enum


class SessionStatus(str, Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class SessionSource(str, Enum):
    BROWSER = "browser"
    ANDROID = "android"
    PROXY = "proxy"
    MANUAL = "manual"
