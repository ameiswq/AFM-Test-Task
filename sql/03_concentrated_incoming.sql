with incoming_by_source as (
    select receiver_id, sender_id, sum(abs(amount_kzt)) as source_turnover
    from transactions group by receiver_id, sender_id), incoming_total as (
    select receiver_id, sum(source_turnover) as total_incoming_turnover from incoming_by_source group by receiver_id)
select s.receiver_id, s.sender_id as main_source_id, s.source_turnover, t.total_incoming_turnover, round(s.source_turnover / t.total_incoming_turnover, 4) as source_share
from incoming_by_source s join incoming_total t on s.receiver_id = t.receiver_id
where s.source_turnover / t.total_incoming_turnover > 0.7 order by source_share desc;