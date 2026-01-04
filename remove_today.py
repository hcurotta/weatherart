import argparse
import logging
from datetime import datetime

from config import (
    DEFAULT_TIMEOUT_S,
    DEFAULT_TV_IP,
    MY_PICTURES_CATEGORY,
    DEFAULT_WOL_BROADCAST,
    DEFAULT_WOL_PORT,
    DEFAULT_WOL_WAIT_S,
    TV_MAC,
)
from logging_utils import setup_logging
from tv_utils import connect_tv, select_tv_ip, wake_and_wait


def _is_today(item, today_prefix):
    value = item.get("image_date")
    return isinstance(value, str) and value.startswith(today_prefix)


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Remove images added today from the Frame TV.",
        epilog=(
            "Examples:\n"
            "  uv run python remove_today.py\n"
            "  uv run python remove_today.py --category MY-C0002\n"
            "  uv run python remove_today.py --ip 192.168.1.50 --log-level DEBUG\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ip",
        help="TV IP address (default: resolve from MAC or fall back to config).",
    )
    parser.add_argument(
        "--mac",
        default=TV_MAC,
        help="TV MAC address for resolving IP (default: WEATHERART_TV_MAC).",
    )
    parser.add_argument(
        "--wake",
        action="store_true",
        help="Send a Wake-on-LAN packet before connecting.",
    )
    parser.add_argument(
        "--wake-broadcast",
        default=DEFAULT_WOL_BROADCAST,
        help=f"WOL broadcast address (default: {DEFAULT_WOL_BROADCAST}).",
    )
    parser.add_argument(
        "--wake-port",
        type=int,
        default=DEFAULT_WOL_PORT,
        help=f"WOL UDP port (default: {DEFAULT_WOL_PORT}).",
    )
    parser.add_argument(
        "--wake-wait",
        type=int,
        default=DEFAULT_WOL_WAIT_S,
        help=f"Seconds to wait after WOL (default: {DEFAULT_WOL_WAIT_S}).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=f"Connection timeout in seconds (default: {DEFAULT_TIMEOUT_S}).",
    )
    parser.add_argument(
        "--category",
        default=MY_PICTURES_CATEGORY,
        help=(
            "Art category to filter (default: MY Photos). "
            "Use an empty string to scan all categories."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    parser.add_argument(
        "--log-file",
        help="Optional log file path. When set, logs are written to this file too.",
    )
    return parser.parse_args()


def _list_items(art, category):
    if category:
        return art.available(category=category) or []
    return art.available() or []


def remove_today(args):
    logger = logging.getLogger(__name__)
    today_prefix = datetime.now().strftime("%Y:%m:%d")

    if args.wake:
        if not args.mac:
            logger.warning("Wake requested but no MAC provided.")
        else:
            wake_and_wait(
                args.mac, args.wake_broadcast, args.wake_port, args.wake_wait, logger
            )

    tv_ip = select_tv_ip(args.ip, args.mac, DEFAULT_TV_IP, logger)
    tv = connect_tv(tv_ip, args.timeout, logger)
    art = tv.art()

    items = _list_items(art, args.category)
    to_delete = [
        item.get("content_id")
        for item in items
        if isinstance(item, dict) and _is_today(item, today_prefix)
    ]
    to_delete = [cid for cid in to_delete if cid]

    if not to_delete:
        logger.info("No images from today found.")
        return

    logger.info("Deleting %s image(s) from today...", len(to_delete))
    art.delete_list(to_delete)
    logger.info("Done.")


if __name__ == "__main__":
    args = _parse_args()
    setup_logging(args.log_level, args.log_file)
    remove_today(args)
