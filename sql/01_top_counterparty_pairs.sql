with pairs as (select least(sender_id, receiver_id) as counterparty_1,
                greatest(sender_id, receiver_id) as counterparty_2,
                abs(amount_kzt) as turnover from transactions)
select counterparty_1, counterparty_2, sum(turnover) as total_turnover
from pairs group by counterparty_1, counterparty_2 order by total_turnover desc limit 10;