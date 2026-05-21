import pytest
from fastapi.testclient import TestClient
from app.db import DBc
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def prepare_database():
    test_rows = [
        ("111111111111", "222222222222", "2025-01-10", 1000, "Поставка бумаги А4", "INVOICE"),
        ("333333333333", "222222222222", "2025-01-15", 100, "Канцелярия ручки", "ACT"),
        ("111111111111", "444444444444", "2025-02-10", 300, "Оплата логистики", "WAYBILL"),
        ("555555555555", "222222222222", "2025-03-01", 10000, "Разовая крупная оплата", "INVOICE"),
        ("222222222222", "111111111111", "2025-03-05", 200, "Возврат по поставке", "ACT"),
    ]

    with DBc() as db:
        with db.cursor() as cur:
            cur.execute(
                """create table if not exists transactions (
                    id bigserial primary key,
                    sender_id varchar(12) not null,
                    receiver_id varchar(12) not null,
                    date date not null,
                    amount_kzt numeric(18, 2) not null,
                    description text,
                    doc_type varchar(32) not null);
                """
            )
            cur.execute("truncate table transactions restart identity;")
            cur.executemany(
                """insert into transactions(sender_id, receiver_id, date, amount_kzt, description, doc_type)
                values (%s, %s, %s, %s, %s, %s);""",
                test_rows)
        db.commit()


def test_counterparty_card():
    response = client.get("/counterparty/222222222222")
    assert response.status_code == 200
    data = response.json()
    assert data["counterparty_id"] == "222222222222"
    assert data["total_operations"] == 4
    assert len(data["top_partners"]) == 3
    assert len(data["monthly_dynamics"]) == 3


def test_counterparty_not_found():
    response = client.get("/counterparty/999999999999")
    assert response.status_code == 404

def test_search():
    response = client.get("/search", params={"q": "бумаг", "page": 1, "page_size": 10})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["results"][0]["description"] == "Поставка бумаги А4"


def test_search_empty_query():
    response = client.get("/search", params={"q": ""})
    assert response.status_code == 400


def test_search_with_filters():
    response = client.get("/search",
        params={
            "q": "оплата",
            "date_from": "2025-03-01",
            "date_to": "2025-03-31",
            "amount_min": 9000,
            "amount_max": 11000,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["results"][0]["amount_kzt"] == 10000.0


def test_anomalies():
    response = client.get("/counterparty/222222222222/anomalies")
    assert response.status_code == 200
    data = response.json()
    assert data["counterparty_id"] == "222222222222"
    assert "incoming_concentration" in data
    assert "turnover_spikes" in data


def test_anomalies_not_found():
    response = client.get("/counterparty/999999999999/anomalies")

    assert response.status_code == 404