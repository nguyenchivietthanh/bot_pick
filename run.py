"""Entrypoint chạy bot đối soát 24/7."""

import logging
import sys

from src.api_client import HttpInternalAPIClient
from src.config import Settings
from src.poller import ReconciliationPoller
from src.sheets.writer import SheetsWriter
from src.storage.db import make_session_factory
from src.storage.repository import ReconciliationRepository

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = Settings.from_env()

    api_client = HttpInternalAPIClient(settings.api_base_url, settings.api_token)

    session_factory = make_session_factory(settings.db_path)
    repository = ReconciliationRepository(session_factory)

    sheets_writer = None
    if settings.google_credentials_path and settings.google_spreadsheet_id:
        sheets_writer = SheetsWriter(
            settings.google_credentials_path,
            settings.google_spreadsheet_id,
            settings.google_worksheet_name,
        )
    else:
        logger.warning(
            "Chưa cấu hình Google Sheets (GOOGLE_SERVICE_ACCOUNT_JSON / "
            "GOOGLE_SPREADSHEET_ID) — bỏ qua đồng bộ Sheet, chỉ ghi SQLite."
        )

    poller = ReconciliationPoller(settings, api_client, repository, sheets_writer)
    poller.run_forever()


if __name__ == "__main__":
    sys.exit(main())
