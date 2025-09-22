# /// script
# dependencies = [
#   'requests<3',
#   'pydantic<3',
# ]
# ///

from datetime import date, datetime
from glob import glob
from io import BytesIO
import json
import os.path
from tempfile import NamedTemporaryFile
import shutil

from pydantic import BaseModel, ConfigDict, Field
import requests


LOGIN_URL = "https://main.tomojdom.pl/login/OsLoginPass"
API_URL = "https://aries.tomojdom.pl/app/api"

USER_AGENT = "tmd/1.0 (+https://github.com/miedzinski/tmd)"


class Database(BaseModel):
    username: int
    password: str
    discord_webhook_url: str | None = None
    settlements: list["Settlement"] = Field(default_factory=list)
    payments: list["Payment"] = Field(default_factory=list)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class Settlement(FrozenModel):
    id: int | None = None
    year: int
    period: int
    title: str
    due_date: date
    value: float


class Payment(FrozenModel):
    date: date
    value: float


def read_db(path) -> Database:
    with open(path, "r") as f:
        return Database.model_validate_json(f.read())


def login(session, username, password) -> None:
    response = session.post(LOGIN_URL, json={"User": username, "Pass": password})
    response.raise_for_status()
    jwt = response.json()[2]
    session.headers.update({"Authorization": f"Bearer {jwt}"})


def fetch_wid(session) -> int:
    response = session.post(API_URL + "/WmsOsoby")
    response.raise_for_status()
    return response.json()[0][6][0][1]


def fetch_records(session, wid) -> tuple[list[Settlement], list[Payment]]:
    this_year = date.today().year
    settlements = []
    payments = []

    for year in range(this_year, this_year - 30, -1):
        response = session.post(API_URL + "/RozliczeniaSzczegolowe", json={"Rok": year, "WId": wid})
        response.raise_for_status()
        response_data = response.json()

        if not response_data and year != this_year:
            break

        for month in response_data:
            for record in month[2]:
                settlements.append(
                    Settlement(
                        id=record[4],
                        year=year,
                        period=record[3],
                        title=record[1],
                        due_date=datetime.fromisoformat(record[0]).date(),
                        value=-record[2],
                    )
                )

            for record in month[4]:
                payments.append(
                    Payment(
                        date=datetime.fromisoformat(record[0]).date(),
                        value=record[1],
                    )
                )

    return settlements, payments


def diff[T](seen: list[T], new: list[T]) -> list[T]:
    seen_set = set(seen)
    return [x for x in new if x not in seen_set]


def download_document(session, settlement: Settlement, wid: int) -> tuple[str, BytesIO, str]:
    payload = {
        "WId": wid,
        "Rok": settlement.year,
        "NTId": settlement.period,
        "rId": settlement.id,
    }
    response = session.post(API_URL + "/WydrukDokument", json=payload)
    response.raise_for_status()
    return settlement.title + ".pdf", BytesIO(response.content), "application/pdf"


def send_message(session, webhook_url: str, content: str, file: tuple[str, BytesIO, str] | None = None) -> None:
    files = {}
    if file:
        files["file"] = file
    payload = {"content": f"@everyone {content}", "allowed_mentions": {"parse": ["everyone"]}}
    response = session.post(webhook_url, data={"payload_json": json.dumps(payload)}, files=files)
    response.raise_for_status()


def notify(tmd_session, settlements: list[Settlement], payments: list[Payment], wid: int, discord_webhook_url: str):
    with requests.Session() as discord_session:
        discord_session.headers.update({"User-Agent": USER_AGENT})
        for settlement in settlements:
            send_message(
                session=discord_session,
                webhook_url=discord_webhook_url,
                content=f"📢 You have a new settlement: **{settlement.title}**\nAmount: **{settlement.value:.2f} PLN**\nDue date: **{settlement.due_date.strftime('%d %b %Y')}**",
                file=download_document(tmd_session, settlement, wid),
            )
        for payment in payments:
            send_message(
                session=discord_session,
                webhook_url=discord_webhook_url,
                content=f"💸 New payment recorded!\nAmount: **{payment.value:.2f} PLN**\nDate: **{payment.date.strftime('%d %b %Y')}**",
            )


def save(db_path, db):
    with NamedTemporaryFile(mode="w", delete=False) as tmp_file:
        tmp_file.write(db.model_dump_json(indent=2))
        tmp_path = tmp_file.name
    shutil.move(tmp_path, db_path)


def sync_account(db: Database):
    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT})

        login(session, db.username, db.password)

        wid = fetch_wid(session)
        settlements, payments = fetch_records(session, wid)

        if db.discord_webhook_url:
            new_settlements = diff(db.settlements, settlements)
            new_payments = diff(db.payments, payments)
            notify(session, new_settlements, new_payments, wid, db.discord_webhook_url)

    db.settlements = settlements
    db.payments = payments


def main():
    db_root_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
    for db_filename in glob("*.json", root_dir=db_root_path):
        db_path = os.path.join(db_root_path, db_filename)
        db = read_db(db_path)
        sync_account(db)
        save(db_path, db)


if __name__ == "__main__":
    main()
