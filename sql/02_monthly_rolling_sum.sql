with monthly as (select sender_id, date_trunc('month', date)::date as month, sum(abs(amount_kzt)) as monthly_turnover
    from transactions group by sender_id, date_trunc('month', date)::date)
select sender_id, month, monthly_turnover, sum(monthly_turnover) over (partition by sender_id order by month
rows between 2 preceding and current row) as rolling_sum_turnover from monthly order by sender_id, month;