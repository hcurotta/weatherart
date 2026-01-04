import argparse
import logging
import os
from datetime import datetime

from config import (
    DEFAULT_TIMEOUT_S,
    DEFAULT_TV_IP,
    DEFAULT_UPLOAD_TIMEOUT_S,
    IMAGE_PATH_OVERRIDE,
    MY_PICTURES_CATEGORY,
    SCRIPT_DIR,
    DEFAULT_WOL_BROADCAST,
    DEFAULT_WOL_PORT,
    DEFAULT_WOL_WAIT_S,
    TV_MAC,
)
from image_generation import build_prompt_text, generate_image, write_prompt_file
from logging_utils import setup_logging
from tv_utils import (
    connect_tv,
    load_last_id,
    pick_latest_content_id,
    save_last_id,
    select_tv_ip,
    upload_with_timeout,
    wake_and_wait,
)

DEFAULT_IMAGE_PATH = os.path.join(SCRIPT_DIR, "test-art.png")


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a weather-based image and upload it to the Frame TV.",
        epilog=(
            "Examples:\n"
            "  uv run python main.py\n"
            "  uv run python main.py --prompt-id sydney-nolan\n"
            "  uv run python main.py --ip 192.168.1.50 --log-level DEBUG\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--prompt-id",
        help="Prompt id to use from prompts.yaml (default: random).",
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
        "--matte",
        default="none",
        help="Matte style to use (default: none).",
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


def _resolve_upload_path(generated_path: str | None) -> str:
    if generated_path:
        return generated_path
    if IMAGE_PATH_OVERRIDE:
        return IMAGE_PATH_OVERRIDE
    return DEFAULT_IMAGE_PATH


def test_upload(args) -> None:
    logger = logging.getLogger(__name__)

    try:
        if args.wake:
            if not args.mac:
                logger.warning("Wake requested but no MAC provided.")
            else:
                wake_and_wait(
                    args.mac, args.wake_broadcast, args.wake_port, args.wake_wait, logger
                )

        tv_ip = select_tv_ip(args.ip, args.mac, DEFAULT_TV_IP, logger)
        tv = connect_tv(tv_ip, args.timeout, logger)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        prompt_text = None
        try:
            prompt_text = build_prompt_text(prompt_id=args.prompt_id)
            prompt_path = write_prompt_file(prompt_text, timestamp)
            logger.info("Prompt saved to %s", prompt_path)
        except Exception as exc:
            logger.warning("Failed to build prompt: %s", exc)

        generated_path = None
        if prompt_text:
            try:
                generated_path = generate_image(prompt_text, timestamp)
                logger.info("Generated image saved to %s", generated_path)
            except Exception as exc:
                logger.warning("Failed to generate image: %s", exc)

        upload_path = _resolve_upload_path(generated_path)
        if not os.path.exists(upload_path):
            logger.error("Could not find image at %s", upload_path)
            return

        art_upload = tv.art()
        last_id = load_last_id()

        before_list = art_upload.available(category=MY_PICTURES_CATEGORY) or []
        before_ids = {
            item.get("content_id")
            for item in before_list
            if isinstance(item, dict)
        }

        logger.info("Uploading image to Frame TV...")
        content_id, upload_error = upload_with_timeout(
            art_upload,
            upload_path,
            matte=args.matte,
            upload_timeout_s=args.upload_timeout,
        )
        if upload_error:
            logger.warning("Upload did not complete cleanly: %s", upload_error)
            content_id = None
            try:
                art_upload.close()
            except Exception:
                pass

        if not content_id:
            art_query = tv.art()
            after_list = art_query.available(category=MY_PICTURES_CATEGORY) or []
            new_items = [
                item
                for item in after_list
                if isinstance(item, dict)
                and item.get("content_id") not in before_ids
            ]
            content_id = pick_latest_content_id(new_items) or pick_latest_content_id(
                after_list
            )

        if content_id:
            logger.info("Selecting the new image...")
            art_query = tv.art()
            art_query.select_image(content_id, category=MY_PICTURES_CATEGORY)
            save_last_id(content_id)
            if last_id and last_id != content_id:
                logger.info("Removing previously uploaded image: %s", last_id)
                try:
                    art_query.delete(last_id)
                except Exception as exc:
                    logger.warning("Could not delete previous image: %s", exc)
        else:
            logger.warning("Upload likely succeeded, but the new image ID wasn't found.")
            logger.info("Open Art Mode on the TV and check My Photos.")

        logger.info("Done! Look at your TV.")

    except Exception as exc:
        logger.error("Failed to upload image: %s", exc)
        logger.info("Tip: Ensure TV is ON and on the same Wifi.")
        logger.info("Tip: If you see 'Connection refused', check the IP address.")


if __name__ == "__main__":
    args = _parse_args()
    setup_logging(args.log_level, args.log_file)
    test_upload(args)
