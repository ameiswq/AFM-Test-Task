create table transactions (
  id bigserial primary key,
  sender_id varchar(12) not null,
  receiver_id varchar(12) not null,
  date date not null,
  amount_kzt numeric(18, 2) not null,
  description text,
  doc_type varchar(32) not null
);