import argparse
import logging
import os

from config import (
    DEFAULT_TIMEOUT_S,
    DEFAULT_TV_IP,
    DEFAULT_UPLOAD_TIMEOUT_S,
    MY_PICTURES_CATEGORY,
    DEFAULT_WOL_BROADCAST,
    DEFAULT_WOL_PORT,
    DEFAULT_WOL_WAIT_S,
    TV_MAC,
)
from logging_utils import setup_logging
from tv_utils import (
    connect_tv,
    load_last_id,
    save_last_id,
    select_tv_ip,
    upload_with_timeout,
    wake_and_wait,
)


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Upload a specific image to the Frame TV.",
        epilog=(
            "Examples:\n"
            "  uv run python push_image.py ./generated/20260101_120000.png\n"
            "  uv run python push_image.py ./art.png --replace-last\n"
            "  uv run python push_image.py ./art.png --ip 192.168.1.50 --log-level DEBUG\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("image_path", help="Path to the image file to upload.")
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
        "--matte",
        default="none",
        help="Matte style to use (default: none).",
    )
    parser.add_argument(
        "--replace-last",
        action="store_true",
        help="Delete the previously uploaded image after selecting the new one.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=f"Connection timeout in seconds (default: {DEFAULT_TIMEOUT_S}).",
    )
    parser.add_argument(
        "--upload-timeout",
        type=int,
        default=DEFAULT_UPLOAD_TIMEOUT_S,
        help=f"Upload timeout in seconds (default: {DEFAULT_UPLOAD_TIMEOUT_S}).",
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


def main():
    args = _parse_args()
    setup_logging(args.log_level, args.log_file)
    logger = logging.getLogger(__name__)

    image_path = os.path.abspath(args.image_path)
    if not os.path.exists(image_path):
        raise SystemExit(f"Image not found: {image_path}")

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
    last_id = load_last_id()

    logger.info("Uploading image: %s", image_path)
    content_id, upload_error = upload_with_timeout(
        art,
        image_path,
        matte=args.matte,
        upload_timeout_s=args.upload_timeout,
    )
    if upload_error:
        raise SystemExit(f"Upload did not complete cleanly: {upload_error}")
    if not content_id:
        raise SystemExit("Upload likely succeeded, but no content_id was returned.")

    logger.info("Selecting the new image...")
    art.select_image(content_id, category=MY_PICTURES_CATEGORY)
    save_last_id(content_id)

    if args.replace_last and last_id and last_id != content_id:
        logger.info("Removing previously uploaded image: %s", last_id)
        try:
            art.delete(last_id)
        except Exception as exc:
            logger.warning("Could not delete previous image: %s", exc)

    logger.info("Done! Look at your TV.")


if __name__ == "__main__":
    main()
