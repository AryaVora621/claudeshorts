"""python -m claudeshorts.telegram_bot — starts the long-polling loop."""

import os

from .bot import build_application
from .client import ApiClient


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = int(os.environ["TELEGRAM_CHAT_ID"])
    base_url = os.environ.get("CLAUDESHORTS_API_BASE_URL", "http://127.0.0.1:8000")
    client = ApiClient(base_url=base_url)
    app = build_application(token, chat_id, client)
    app.run_polling()


if __name__ == "__main__":
    main()
