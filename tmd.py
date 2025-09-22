# /// script
# dependencies = [
#   'requests<3',
#   'pydantic<3',
# ]
# ///

from datetime import date, datetime
from glob import glob
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
    charges: list["Charge"] = Field(default_factory=list)
    payments: list["Payment"] = Field(default_factory=list)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class Charge(FrozenModel):
    id: int | None = None
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


def fetch_records(session, wid) -> tuple[list[Charge], list[Payment]]:
    this_year = date.today().year
    charges = []
    payments = []

    for year in range(this_year, this_year - 30, -1):
        response = session.post(API_URL + "/RozliczeniaSzczegolowe", json={"Rok": year, "WId": wid})
        response.raise_for_status()
        response_data = response.json()

        if not response_data and year != this_year:
            break

        for month in response_data:
            for record in month[2]:
                charges.append(
                    Charge(
                        id=record[4],
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

    return charges, payments


def diff[T](seen: list[T], new: list[T]) -> list[T]:
    seen_set = set(seen)
    return [x for x in new if x not in seen_set]


def notify(charges, payments):
    print("New charges:", charges)
    print("New payments:", payments)


def save(db_path, db):
    with NamedTemporaryFile(mode="w", delete=False) as tmp_file:
        tmp_file.write(db.model_dump_json(indent=2))
        tmp_path = tmp_file.name
    shutil.move(tmp_path, db_path)


def sync_account(db):
    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT})

        login(session, db.username, db.password)

        wid = fetch_wid(session)
        charges, payments = fetch_records(session, wid)

    new_charges = diff(db.charges, charges)
    new_payments = diff(db.payments, payments)

    if new_charges or new_payments:
        notify(new_charges, new_payments)

    db.charges = charges
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
