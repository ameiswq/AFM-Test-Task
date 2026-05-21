copy transactions(sender_id, receiver_id, date, amount_kzt, description, doc_type)
from '/docker-entrypoint-initdb.d/transactions_clean.csv'
with (FORMAT csv, HEADER true, ENCODING 'UTF8');