from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build

import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "#",
    "Title",
    "Company",
    "Location",
    "Job URL",
    "Apply URL",
    "Score",
    "Reasoning",
    "Why You're Strong",
    "What's Missing",
    "Connection Note",
    "Recruiter LinkedIn",
    "Recruiter Email",
    "Guessed Email",
    "Recruiter Mail Draft",
    "Status",
    "Date Added",
]

RECRUITER_HEADERS = [
    "Company",
    "Job Title",
    "Job URL",
    "Recruiter Name",
    "Title",
    "LinkedIn",
    "Email",
    "Confidence",
    "Domain",
    "Date Found",
]


class SheetsWriter:
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        creds = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=SCOPES
        )
        service = build("sheets", "v4", credentials=creds)
        self.sheet = service.spreadsheets()

        self._counters = {"Strong Fit": 0, "Maybe": 0, config.RECRUITER_TAB: 0}
        self._setup_tabs()

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def write_strong_fit(self, card: dict, jd: dict, result: dict):
        self._counters["Strong Fit"] += 1
        self._write_row("Strong Fit", self._counters["Strong Fit"], card, jd, result)

    def write_maybe(self, card: dict, jd: dict, result: dict):
        self._counters["Maybe"] += 1
        self._write_row("Maybe", self._counters["Maybe"], card, jd, result)

    def write_recruiter(self, card: dict, recruiter: dict):
        tab = config.RECRUITER_TAB
        row = [
            card.get("company") or "",
            card.get("title") or "",
            card.get("job_url") or "",
            recruiter.get("recruiter_name") or "",
            recruiter.get("recruiter_title") or "",
            recruiter.get("recruiter_linkedin") or "",
            recruiter.get("email") or "",
            recruiter.get("confidence") or "",
            recruiter.get("domain") or "",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ]

        self.sheet.values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{tab}'!A:A",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        name    = recruiter.get("recruiter_name") or "unknown"
        company = card.get("company") or "?"
        print(f"    📝 → '{tab}': {name} @ {company}")

    # ─────────────────────────────────────────────────────────────
    # Setup
    # ─────────────────────────────────────────────────────────────

    def _setup_tabs(self):
        meta = self.sheet.get(spreadsheetId=self.spreadsheet_id).execute()
        existing = [s["properties"]["title"] for s in meta["sheets"]]

        tabs_to_create = ["Strong Fit", "Maybe"]
        if config.RECRUITER_SEARCH_ENABLED:
            tabs_to_create.append(config.RECRUITER_TAB)

        requests = []
        for tab in tabs_to_create:
            if tab not in existing:
                requests.append({"addSheet": {"properties": {"title": tab}}})

        if requests:
            self.sheet.batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests},
            ).execute()

        # Add headers if tab is empty; count existing rows for serial numbers
        for tab in ["Strong Fit", "Maybe"]:
            rows = (
                self.sheet.values()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"'{tab}'!A:A",
                )
                .execute()
                .get("values", [])
            )
            if not rows:
                self.sheet.values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"'{tab}'!A1",
                    valueInputOption="RAW",
                    body={"values": [HEADERS]},
                ).execute()
                self._format_header(tab)
            else:
                # Subtract 1 for the header row
                self._counters[tab] = max(0, len(rows) - 1)

        if config.RECRUITER_SEARCH_ENABLED:
            tab = config.RECRUITER_TAB
            rows = (
                self.sheet.values()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"'{tab}'!A:A",
                )
                .execute()
                .get("values", [])
            )
            if not rows:
                self.sheet.values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"'{tab}'!A1",
                    valueInputOption="RAW",
                    body={"values": [RECRUITER_HEADERS]},
                ).execute()
                self._format_header(tab)

    def _format_header(self, tab: str):
        """Bold + freeze the header row."""
        sheet_id = self._get_sheet_id(tab)
        if sheet_id is None:
            return
        self.sheet.batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={
                "requests": [
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": 1,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "textFormat": {"bold": True},
                                    "backgroundColor": {
                                        "red": 0.2,
                                        "green": 0.47,
                                        "blue": 0.85,
                                    },
                                }
                            },
                            "fields": "userEnteredFormat(textFormat,backgroundColor)",
                        }
                    },
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": sheet_id,
                                "gridProperties": {"frozenRowCount": 1},
                            },
                            "fields": "gridProperties.frozenRowCount",
                        }
                    },
                ]
            },
        ).execute()

    def _get_sheet_id(self, tab_name: str) -> int | None:
        meta = self.sheet.get(spreadsheetId=self.spreadsheet_id).execute()
        for s in meta["sheets"]:
            if s["properties"]["title"] == tab_name:
                return s["properties"]["sheetId"]
        return None

    # ─────────────────────────────────────────────────────────────
    # Row writer
    # ─────────────────────────────────────────────────────────────

    def _write_row(
        self, tab: str, serial: int, card: dict, jd: dict, r: dict
    ):
        title    = card.get("title") or jd.get("title") or ""
        company  = card.get("company") or jd.get("company") or ""
        location = card.get("location") or jd.get("location") or ""

        apply_url          = r.get("apply_url") or jd.get("apply_url") or ""
        recruiter_linkedin = r.get("recruiter_linkedin") or jd.get("recruiter_linkedin") or ""
        recruiter_email    = r.get("recruiter_email") or jd.get("recruiter_email") or ""

        row = [
            serial,
            title,
            company,
            location,
            card.get("job_url", ""),
            apply_url,
            r.get("score", ""),
            r.get("reasoning", ""),
            r.get("why_strong", ""),
            r.get("what_missing", ""),
            r.get("connection_note", ""),
            recruiter_linkedin,
            recruiter_email,
            r.get("guessed_email") or "",
            r.get("recruiter_mail_draft", ""),
            "New",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ]

        self.sheet.values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{tab}'!A:A",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        print(f"    📝 → '{tab}': {title} @ {company} (score {r.get('score')})")
