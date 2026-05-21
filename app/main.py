from fastapi import FastAPI, HTTPException, Query
from typing import Optional
from app.db import db

app = FastAPI(title="Transactions API")

@app.get("/counterparty/{counterparty_id}")
def get_counterparty(counterparty_id: str):
    with db() as db:
        with db.cursor() as cur:
            cur.execute("""SELECT 1 FROM transactions WHERE sender_id = %s OR receiver_id = %s LIMIT 1""", (counterparty_id, counterparty_id))
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Counterparty not found")

            cur.execute(
                """SELECT
                    COUNT(*)                          AS total_operations,
                    COALESCE(SUM(amount_kzt), 0)      AS total_turnover,
                    COALESCE(SUM(CASE WHEN receiver_id = %s THEN amount_kzt ELSE 0 END), 0) AS incoming,
                    COALESCE(SUM(CASE WHEN sender_id   = %s THEN amount_kzt ELSE 0 END), 0) AS outgoing
                FROM transactions
                WHERE sender_id = %s OR receiver_id = %s
                """,
                (counterparty_id, counterparty_id, counterparty_id, counterparty_id),
            )
            summary = dict(cur.fetchone())

            # Топ-3 партнёра по суммарному обороту
            cur.execute(
                """
                SELECT
                    partner,
                    SUM(amount_kzt) AS turnover
                FROM (
                    SELECT receiver_id AS partner, amount_kzt FROM transactions WHERE sender_id = %s
                    UNION ALL
                    SELECT sender_id   AS partner, amount_kzt FROM transactions WHERE receiver_id = %s
                ) t
                GROUP BY partner
                ORDER BY turnover DESC
                LIMIT 3
                """,
                (counterparty_id, counterparty_id),
            )
            top_partners = [dict(row) for row in cur.fetchall()]

            # Помесячная динамика
            cur.execute(
                """
                SELECT
                    TO_CHAR(date, 'YYYY-MM')          AS month,
                    COUNT(*)                          AS operations,
                    SUM(amount_kzt)                   AS turnover
                FROM transactions
                WHERE sender_id = %s OR receiver_id = %s
                GROUP BY TO_CHAR(date, 'YYYY-MM')
                ORDER BY month
                """,
                (counterparty_id, counterparty_id),
            )
            monthly = [dict(row) for row in cur.fetchall()]

    return {
        "counterparty_id": counterparty_id,
        **summary,
        "top_partners": top_partners,
        "monthly_dynamics": monthly,
    }


# ──────────────────────────────────────────────
# GET /search?q=...
# Поиск по описанию (fuzzy через ILIKE),
# пагинация, фильтры по периоду и диапазону сумм
# ──────────────────────────────────────────────
@app.get("/search")
def search_transactions(
    q: str = Query(default="", description="Поисковый запрос по description"),
    date_from: Optional[str] = Query(default=None, description="Дата от (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(default=None, description="Дата до (YYYY-MM-DD)"),
    amount_min: Optional[float] = Query(default=None, description="Минимальная сумма"),
    amount_max: Optional[float] = Query(default=None, description="Максимальная сумма"),
    page: int = Query(default=1, ge=1, description="Номер страницы"),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы"),
):
    # Валидация дат
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=400, detail="date_from не может быть позже date_to"
        )

    conditions = []
    params = []

    # Fuzzy-поиск: разбиваем запрос на слова и ищем каждое через ILIKE
    if q.strip():
        for word in q.strip().split():
            conditions.append("description ILIKE %s")
            params.append(f"%{word}%")

    if date_from:
        conditions.append("date >= %s")
        params.append(date_from)

    if date_to:
        conditions.append("date <= %s")
        params.append(date_to)

    if amount_min is not None:
        conditions.append("amount_kzt >= %s")
        params.append(amount_min)

    if amount_max is not None:
        conditions.append("amount_kzt <= %s")
        params.append(amount_max)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with db() as conn:
        with conn.cursor() as cur:

            # Общее число результатов
            cur.execute(
                f"SELECT COUNT(*) AS total FROM transactions {where_clause}",
                params,
            )
            total = cur.fetchone()["total"]

            # Сами записи с пагинацией
            offset = (page - 1) * page_size
            cur.execute(
                f"""
                SELECT id, sender_id, receiver_id, date, amount_kzt, description, doc_type
                FROM transactions
                {where_clause}
                ORDER BY date DESC
                LIMIT %s OFFSET %s
                """,
                params + [page_size, offset],
            )
            rows = [dict(row) for row in cur.fetchall()]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "results": rows,
    }


# ──────────────────────────────────────────────
# GET /counterparty/{id}/anomalies
# Признаки аномалий:
#   1. Концентрация входящих от одного источника
#   2. Всплески оборота
# ──────────────────────────────────────────────
@app.get("/counterparty/{counterparty_id}/anomalies")
def get_anomalies(counterparty_id: str):
    with db() as conn:
        with conn.cursor() as cur:

            # Проверяем существование
            cur.execute(
                """
                SELECT 1 FROM transactions
                WHERE sender_id = %s OR receiver_id = %s
                LIMIT 1
                """,
                (counterparty_id, counterparty_id),
            )
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Counterparty not found")

            # 1. Концентрация входящих: доля от каждого отправителя
            cur.execute(
                """
                SELECT
                    sender_id,
                    COUNT(*)                                         AS tx_count,
                    SUM(amount_kzt)                                  AS total_amount,
                    ROUND(
                        100.0 * SUM(amount_kzt)
                        / NULLIF(SUM(SUM(amount_kzt)) OVER (), 0),
                        2
                    ) AS share_pct
                FROM transactions
                WHERE receiver_id = %s
                GROUP BY sender_id
                ORDER BY total_amount DESC
                """,
                (counterparty_id,),
            )
            incoming_concentration = [dict(row) for row in cur.fetchall()]

            # Флаг: есть ли источник с долей > 70%
            concentrated = any(
                row["share_pct"] and row["share_pct"] > 70
                for row in incoming_concentration
            )

            # 2. Всплески оборота: месяцы, где оборот > среднего + 2σ
            cur.execute(
                """
                WITH monthly AS (
                    SELECT
                        TO_CHAR(date, 'YYYY-MM') AS month,
                        SUM(amount_kzt)          AS turnover
                    FROM transactions
                    WHERE sender_id = %s OR receiver_id = %s
                    GROUP BY TO_CHAR(date, 'YYYY-MM')
                ),
                stats AS (
                    SELECT
                        AVG(turnover)    AS avg_turnover,
                        STDDEV(turnover) AS std_turnover
                    FROM monthly
                )
                SELECT
                    m.month,
                    m.turnover,
                    ROUND(s.avg_turnover, 2) AS avg_turnover,
                    ROUND(s.std_turnover, 2) AS std_turnover
                FROM monthly m, stats s
                WHERE m.turnover > s.avg_turnover + 2 * COALESCE(s.std_turnover, 0)
                ORDER BY m.month
                """,
                (counterparty_id, counterparty_id),
            )
            spikes = [dict(row) for row in cur.fetchall()]

    return {
        "counterparty_id": counterparty_id,
        "incoming_concentration": {
            "concentrated": concentrated,
            "threshold_pct": 70,
            "by_sender": incoming_concentration,
        },
        "turnover_spikes": {
            "spike_months": spikes,
            "spike_count": len(spikes),
        },
    }