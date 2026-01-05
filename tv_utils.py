import re
import socket
import subprocess
import threading
import time
from datetime import datetime
from typing import Iterable, Optional

from samsungtvws import SamsungTVWS

from config import LAST_ID_FILE


def _normalize_mac(mac: str) -> Optional[str]:
    if not mac:
        return None
    parts = [part for part in re.split(r"[^0-9a-fA-F]", mac) if part]
    if len(parts) == 1:
        hexstr = parts[0].lower()
        if len(hexstr) == 12:
            return hexstr
        if len(hexstr) == 11:
            return f"0{hexstr}"
        return None
    if len(parts) != 6:
        return None
    padded = [part.zfill(2).lower() for part in parts]
    hexstr = "".join(padded)
    return hexstr if len(hexstr) == 12 else None


def resolve_ip_from_mac(mac: str) -> Optional[str]:
    normalized = _normalize_mac(mac)
    if not normalized:
        return None
    try:
        output = subprocess.check_output(["arp", "-a"], text=True)
    except (OSError, subprocess.CalledProcessError):
        return None

    pattern = re.compile(r"\((?P<ip>[^)]+)\)\s+at\s+(?P<mac>\S+)\s", re.IGNORECASE)
    for line in output.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        candidate = _normalize_mac(match.group("mac"))
        if candidate and candidate == normalized:
            return match.group("ip")
    return None


def select_tv_ip(ip: Optional[str], mac: Optional[str], fallback_ip: str, logger) -> str:
    if ip:
        return ip
    if mac:
        resolved = resolve_ip_from_mac(mac)
        if resolved:
            logger.info("Resolved TV IP from MAC %s: %s", mac, resolved)
            return resolved
        logger.warning("Could not resolve IP from MAC %s, using fallback.", mac)
    return fallback_ip


def wake_on_lan(mac: str, broadcast: str, port: int, logger) -> bool:
    clean = _normalize_mac(mac)
    if not clean:
        logger.warning("Invalid MAC address for WOL: %s", mac)
        return False

    try:
        mac_bytes = bytes.fromhex(clean)
    except ValueError:
        logger.warning("Invalid MAC address for WOL: %s", mac)
        return False

    packet = b"\xff" * 6 + mac_bytes * 16
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))
        sock.close()
    except OSError as exc:
        logger.warning("Failed to send WOL packet: %s", exc)
        return False

    logger.info("Sent WOL packet to %s via %s:%s", mac, broadcast, port)
    return True


def wake_and_wait(mac: str, broadcast: str, port: int, wait_s: int, logger) -> None:
    if wake_on_lan(mac, broadcast, port, logger):
        if wait_s > 0:
            logger.info("Waiting %s seconds for TV to wake...", wait_s)
            time.sleep(wait_s)


def connect_tv(ip: str, timeout: int, logger):
    logger.info("Attempting to connect to %s...", ip)
    tv = SamsungTVWS(ip, timeout=timeout)
    info = tv.rest_device_info()
    name = info.get("device", {}).get("name", "Unknown")
    logger.info("Connection successful! TV Name: %s", name)
    return tv


def upload_with_timeout(art, image_path: str, *, matte: str, upload_timeout_s: int):
    result = {"content_id": None, "error": None}

    def runner():
        try:
            result["content_id"] = art.upload(image_path, matte=matte)
        except Exception as exc:  # pragma: no cover - diagnostic path
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(upload_timeout_s)

    if thread.is_alive():
        return None, TimeoutError("Upload timed out waiting for image_added event")

    return result["content_id"], result["error"]


def pick_latest_content_id(items: Iterable[dict]) -> Optional[str]:
    items = [item for item in items if isinstance(item, dict)]
    if not items:
        return None

    def score(item):
        for key in ("date", "create_time", "added_time", "timestamp", "content_time"):
            value = item.get(key)
            if isinstance(value, (int, float)):
                return value
            if isinstance(value, str):
                for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        return datetime.strptime(value, fmt).timestamp()
                    except ValueError:
                        continue
        return 0

    sorted_items = sorted(items, key=score, reverse=True)
    return sorted_items[0].get("content_id")


def load_last_id(path: str = LAST_ID_FILE) -> Optional[str]:
    try:
        with open(path, "r") as f:
            value = f.read().strip()
            return value or None
    except OSError:
        return None


def save_last_id(content_id: str, path: str = LAST_ID_FILE) -> None:
    try:
        with open(path, "w") as f:
            f.write(str(content_id))
    except OSError:
        pass
