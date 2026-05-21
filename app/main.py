from fastapi import FastAPI, HTTPException, Query
from typing import Optional
from app.db import DBc

app = FastAPI(title="Transactions API")

@app.get("/counterparty/{counterparty_id}")
def get_counterparty(counterparty_id: str):
    with DBc() as db:
        with db.cursor() as cur:
            cur.execute("""select 1 from transactions where sender_id = %s or receiver_id = %s limit 1""", (counterparty_id, counterparty_id))
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Counterparty not found")

            cur.execute("""select count(*) as total_operations, coalesce(sum(amount_kzt), 0) as total_turnover,
                    coalesce(sum(case when receiver_id = %s then amount_kzt else 0 end), 0) as incoming,
                    coalesce(sum(case when sender_id   = %s then amount_kzt else 0 end), 0) as outgoing
                    from transactions where sender_id = %s OR receiver_id = %s""",
                (counterparty_id, counterparty_id, counterparty_id, counterparty_id),
            )
            summary = dict(cur.fetchone())

            cur.execute(
                """select partner, sum(amount_kzt) as turnover from(
                    select receiver_id as partner, amount_kzt from transactions where sender_id = %s
                    union all
                    select sender_id as partner, amount_kzt from transactions where receiver_id = %s
                ) t group by partner order by turnover desc limit 3""",
                (counterparty_id, counterparty_id),
            )
            top_partners = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """select to_char(date, 'YYYY-MM') as month, count(*) as operations, sum(amount_kzt) as turnover
                from transactions where sender_id = %s or receiver_id = %s group by to_char(date, 'YYYY-MM') order by month""",
                (counterparty_id, counterparty_id),
            )
            monthly = [dict(row) for row in cur.fetchall()]

    return {
        "counterparty_id": counterparty_id,
        **summary,
        "top_partners": top_partners,
        "monthly_dynamics": monthly,
    }

@app.get("/search")
def search_transactions(
    q: str = Query(default="", description="description"),
    date_from: Optional[str] = Query(default=None, description="yyyy-mm-dd"),
    date_to: Optional[str] = Query(default=None, description="yyyy-mm-dd"),
    amount_min: Optional[float] = Query(default=None, description="Минимальная сумма"),
    amount_max: Optional[float] = Query(default=None, description="Максимальная сумма"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100)):
   
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from не может быть позже date_to")

    conditions = []
    params = []

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

    where_clause = ("where " + " and ".join(conditions)) if conditions else ""

    with DBc() as db:
        with db.cursor() as cur:
            cur.execute(f"select count(*) as total from transactions {where_clause}", params)
            total = cur.fetchone()["total"]

            skip = (page - 1) * page_size
            cur.execute(
                f"""select id, sender_id, receiver_id, date, amount_kzt, description, doc_type from transactions
                {where_clause} order by date desc limit %s offset %s """,
                params + [page_size, skip])
            rows = [dict(row) for row in cur.fetchall()]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "results": rows,
    }



@app.get("/counterparty/{counterparty_id}/anomalies")
def get_anomalies(counterparty_id: str):
    with DBc() as db:
        with db.cursor() as cur:
            cur.execute("""select 1 from transactions where sender_id = %s or receiver_id = %s limit 1""", (counterparty_id, counterparty_id))
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Counterparty not found")

            #концентрация от одного источника
            cur.execute(
                """select sender_id, count(*) as num_of_transactions, sum(amount_kzt) as total_amount,
                    round(100.0 * sum(amount_kzt)/ nullif(sum(sum(amount_kzt)) over (), 0), 2) as percentage
                    from transactions where receiver_id = %s
                    group by sender_id order by total_amount desc""",
                    (counterparty_id,))
            incoming_concentration = [dict(row) for row in cur.fetchall()]

            concentrated = any(row["percentage"] and row["percentage"] > 70 for row in incoming_concentration)

            #всплески оборота через среднее арифметическое и среднеквадратичное отклонение
            cur.execute(
                """with monthly as (select to_char(date, 'YYYY-MM') as month,
                    sum(amount_kzt) as turnover from transactions where sender_id = %s or receiver_id = %s
                    group by to_char(date, 'YYYY-MM')
                ),
                stats as (select avg(turnover) as avg_turnover, stddev(turnover) as std_turnover from monthly)
                select m.month, m.turnover, round(s.avg_turnover, 2) as avg_turnover, round(s.std_turnover, 2) as std_turnover
                from monthly m, stats s where m.turnover > s.avg_turnover + 2 * coalesce(s.std_turnover, 0) order by m.month
                """,
                (counterparty_id, counterparty_id),
            )
            spikes = [dict(row) for row in cur.fetchall()]

    return {
        "counterparty_id": counterparty_id,
        "incoming_concentration": {
            "concentrated": concentrated,
            "threshold_percentage": 70,
            "by_sender": incoming_concentration,
        },
        "turnover_spikes": {
            "spike_months": spikes,
            "spike_count": len(spikes),
        },
    }