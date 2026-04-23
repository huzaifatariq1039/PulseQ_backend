--
-- PostgreSQL database dump
--

\restrict hXFQveeAvlZaNnI6ktI2LsPc9GsrKgoBlAnRCQXHqHbZNRJ2iLHmaF6aR9Dz18s

-- Dumped from database version 18.3
-- Dumped by pg_dump version 18.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE IF EXISTS ONLY public.wallets DROP CONSTRAINT IF EXISTS wallets_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.tokens DROP CONSTRAINT IF EXISTS tokens_patient_id_fkey;
ALTER TABLE IF EXISTS ONLY public.tokens DROP CONSTRAINT IF EXISTS tokens_hospital_id_fkey;
ALTER TABLE IF EXISTS ONLY public.tokens DROP CONSTRAINT IF EXISTS tokens_doctor_id_fkey;
ALTER TABLE IF EXISTS ONLY public.support_tickets DROP CONSTRAINT IF EXISTS support_tickets_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.refunds DROP CONSTRAINT IF EXISTS refunds_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.refunds DROP CONSTRAINT IF EXISTS refunds_token_id_fkey;
ALTER TABLE IF EXISTS ONLY public.quick_actions DROP CONSTRAINT IF EXISTS quick_actions_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.queues DROP CONSTRAINT IF EXISTS queues_doctor_id_fkey;
ALTER TABLE IF EXISTS ONLY public.pharmacy_sales DROP CONSTRAINT IF EXISTS pharmacy_sales_performed_by_fkey;
ALTER TABLE IF EXISTS ONLY public.pharmacy_sales DROP CONSTRAINT IF EXISTS pharmacy_sales_patient_id_fkey;
ALTER TABLE IF EXISTS ONLY public.pharmacy_sales DROP CONSTRAINT IF EXISTS pharmacy_sales_hospital_id_fkey;
ALTER TABLE IF EXISTS ONLY public.pharmacy_sales DROP CONSTRAINT IF EXISTS pharmacy_sales_doctor_id_fkey;
ALTER TABLE IF EXISTS ONLY public.payments DROP CONSTRAINT IF EXISTS payments_token_id_fkey;
ALTER TABLE IF EXISTS ONLY public.medical_records DROP CONSTRAINT IF EXISTS medical_records_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.hospital_sequences DROP CONSTRAINT IF EXISTS hospital_sequences_hospital_id_fkey;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS fk_users_hospital;
ALTER TABLE IF EXISTS ONLY public.pharmacy_medicines DROP CONSTRAINT IF EXISTS fk_pharmacy_hospital;
ALTER TABLE IF EXISTS ONLY public.doctors DROP CONSTRAINT IF EXISTS fk_doctors_user;
ALTER TABLE IF EXISTS ONLY public.doctors DROP CONSTRAINT IF EXISTS doctors_hospital_id_fkey;
ALTER TABLE IF EXISTS ONLY public.departments DROP CONSTRAINT IF EXISTS departments_hospital_id_fkey;
ALTER TABLE IF EXISTS ONLY public.activity_logs DROP CONSTRAINT IF EXISTS activity_logs_user_id_fkey;
DROP INDEX IF EXISTS public.ix_wallets_id;
DROP INDEX IF EXISTS public.ix_users_id;
DROP INDEX IF EXISTS public.ix_tokens_id;
DROP INDEX IF EXISTS public.ix_support_tickets_id;
DROP INDEX IF EXISTS public.ix_refunds_id;
DROP INDEX IF EXISTS public.ix_quick_actions_id;
DROP INDEX IF EXISTS public.ix_queues_id;
DROP INDEX IF EXISTS public.ix_pharmacy_sales_id;
DROP INDEX IF EXISTS public.ix_pharmacy_medicines_quantity;
DROP INDEX IF EXISTS public.ix_pharmacy_medicines_is_deleted;
DROP INDEX IF EXISTS public.ix_pharmacy_medicines_id;
DROP INDEX IF EXISTS public.ix_pharmacy_medicines_hospital_updated;
DROP INDEX IF EXISTS public.ix_payments_id;
DROP INDEX IF EXISTS public.ix_medical_records_id;
DROP INDEX IF EXISTS public.ix_idempotency_records_id;
DROP INDEX IF EXISTS public.ix_hospitals_id;
DROP INDEX IF EXISTS public.ix_hospital_sequences_id;
DROP INDEX IF EXISTS public.ix_doctors_id;
DROP INDEX IF EXISTS public.ix_departments_id;
DROP INDEX IF EXISTS public.ix_activity_logs_id;
DROP INDEX IF EXISTS public.idx_users_role;
DROP INDEX IF EXISTS public.idx_users_phone;
DROP INDEX IF EXISTS public.idx_users_hospital_id;
DROP INDEX IF EXISTS public.idx_users_email;
DROP INDEX IF EXISTS public.idx_users_created_at;
DROP INDEX IF EXISTS public.idx_tokens_status;
DROP INDEX IF EXISTS public.idx_tokens_payment_status;
DROP INDEX IF EXISTS public.idx_tokens_patient_status_created;
DROP INDEX IF EXISTS public.idx_tokens_mrn;
DROP INDEX IF EXISTS public.idx_tokens_hospital_date_status;
DROP INDEX IF EXISTS public.idx_tokens_doctor_date_status;
DROP INDEX IF EXISTS public.idx_tokens_department;
DROP INDEX IF EXISTS public.idx_tokens_created_at;
DROP INDEX IF EXISTS public.idx_tokens_appointment_date;
DROP INDEX IF EXISTS public.idx_queues_doctor_id;
DROP INDEX IF EXISTS public.idx_pharmacy_sales_sold_at;
DROP INDEX IF EXISTS public.idx_pharmacy_sales_performed_by;
DROP INDEX IF EXISTS public.idx_pharmacy_sales_payment_status;
DROP INDEX IF EXISTS public.idx_pharmacy_sales_patient_id;
DROP INDEX IF EXISTS public.idx_pharmacy_sales_hospital_sold_at;
DROP INDEX IF EXISTS public.idx_pharmacy_sales_hospital_id;
DROP INDEX IF EXISTS public.idx_pharmacy_sales_doctor_id;
DROP INDEX IF EXISTS public.idx_pharmacy_sales_date_revenue;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_updated_at;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_sub_category;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_stock_status;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_selling_price;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_quantity;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_product_id;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_name_trgm;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_hospital_name;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_hospital_id;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_hospital_category;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_generic_name_trgm;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_expiration_date;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_category;
DROP INDEX IF EXISTS public.idx_pharmacy_medicines_batch_no;
DROP INDEX IF EXISTS public.idx_payments_token_id;
DROP INDEX IF EXISTS public.idx_payments_status;
DROP INDEX IF EXISTS public.idx_hospitals_status;
DROP INDEX IF EXISTS public.idx_hospitals_name_trgm;
DROP INDEX IF EXISTS public.idx_hospitals_created_at;
DROP INDEX IF EXISTS public.idx_hospitals_city;
DROP INDEX IF EXISTS public.idx_doctors_subcategory;
DROP INDEX IF EXISTS public.idx_doctors_status;
DROP INDEX IF EXISTS public.idx_doctors_specialization;
DROP INDEX IF EXISTS public.idx_doctors_name_trgm;
DROP INDEX IF EXISTS public.idx_doctors_hospital_status;
DROP INDEX IF EXISTS public.idx_doctors_hospital_specialization;
DROP INDEX IF EXISTS public.idx_doctors_created_at;
DROP INDEX IF EXISTS public.idx_departments_name;
DROP INDEX IF EXISTS public.idx_departments_hospital_id;
ALTER TABLE IF EXISTS ONLY public.wallets DROP CONSTRAINT IF EXISTS wallets_user_id_key;
ALTER TABLE IF EXISTS ONLY public.wallets DROP CONSTRAINT IF EXISTS wallets_pkey;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS users_pkey;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS users_phone_key;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS users_email_key;
ALTER TABLE IF EXISTS ONLY public.tokens DROP CONSTRAINT IF EXISTS tokens_pkey;
ALTER TABLE IF EXISTS ONLY public.support_tickets DROP CONSTRAINT IF EXISTS support_tickets_pkey;
ALTER TABLE IF EXISTS ONLY public.refunds DROP CONSTRAINT IF EXISTS refunds_pkey;
ALTER TABLE IF EXISTS ONLY public.quick_actions DROP CONSTRAINT IF EXISTS quick_actions_pkey;
ALTER TABLE IF EXISTS ONLY public.queues DROP CONSTRAINT IF EXISTS queues_pkey;
ALTER TABLE IF EXISTS ONLY public.pharmacy_sales DROP CONSTRAINT IF EXISTS pharmacy_sales_pkey;
ALTER TABLE IF EXISTS ONLY public.pharmacy_medicines DROP CONSTRAINT IF EXISTS pharmacy_medicines_pkey;
ALTER TABLE IF EXISTS ONLY public.payments DROP CONSTRAINT IF EXISTS payments_pkey;
ALTER TABLE IF EXISTS ONLY public.medical_records DROP CONSTRAINT IF EXISTS medical_records_pkey;
ALTER TABLE IF EXISTS ONLY public.idempotency_records DROP CONSTRAINT IF EXISTS idempotency_records_pkey;
ALTER TABLE IF EXISTS ONLY public.hospitals DROP CONSTRAINT IF EXISTS hospitals_pkey;
ALTER TABLE IF EXISTS ONLY public.hospital_sequences DROP CONSTRAINT IF EXISTS hospital_sequences_pkey;
ALTER TABLE IF EXISTS ONLY public.hospital_sequences DROP CONSTRAINT IF EXISTS hospital_sequences_hospital_id_key;
ALTER TABLE IF EXISTS ONLY public.doctors DROP CONSTRAINT IF EXISTS doctors_pkey;
ALTER TABLE IF EXISTS ONLY public.departments DROP CONSTRAINT IF EXISTS departments_pkey;
ALTER TABLE IF EXISTS ONLY public.activity_logs DROP CONSTRAINT IF EXISTS activity_logs_pkey;
DROP TABLE IF EXISTS public.wallets;
DROP TABLE IF EXISTS public.users;
DROP TABLE IF EXISTS public.tokens;
DROP TABLE IF EXISTS public.support_tickets;
DROP TABLE IF EXISTS public.refunds;
DROP TABLE IF EXISTS public.quick_actions;
DROP TABLE IF EXISTS public.queues;
DROP TABLE IF EXISTS public.pharmacy_sales;
DROP TABLE IF EXISTS public.pharmacy_medicines;
DROP TABLE IF EXISTS public.payments;
DROP TABLE IF EXISTS public.medical_records;
DROP TABLE IF EXISTS public.idempotency_records;
DROP TABLE IF EXISTS public.hospitals;
DROP TABLE IF EXISTS public.hospital_sequences;
DROP TABLE IF EXISTS public.doctors;
DROP TABLE IF EXISTS public.departments;
DROP TABLE IF EXISTS public.activity_logs;
DROP EXTENSION IF EXISTS pg_trgm;
--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activity_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.activity_logs (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    activity_type character varying(50) NOT NULL,
    description text NOT NULL,
    meta_data json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


--
-- Name: departments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.departments (
    id character varying NOT NULL,
    name character varying(100) NOT NULL,
    hospital_id character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: doctors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.doctors (
    id character varying NOT NULL,
    name character varying(100) NOT NULL,
    specialization character varying(100) NOT NULL,
    subcategory character varying(100),
    hospital_id character varying NOT NULL,
    email character varying(255),
    rating double precision,
    review_count integer,
    consultation_fee double precision NOT NULL,
    session_fee double precision,
    has_session boolean,
    pricing_type character varying(20),
    status character varying(20),
    available_days json,
    start_time character varying(10) NOT NULL,
    end_time character varying(10) NOT NULL,
    avatar_initials character varying(10),
    patients_per_day integer,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    user_id character varying
);


--
-- Name: hospital_sequences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hospital_sequences (
    id character varying NOT NULL,
    hospital_id character varying NOT NULL,
    mrn_seq integer,
    updated_at timestamp with time zone
);


--
-- Name: hospitals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hospitals (
    id character varying NOT NULL,
    name character varying(200) NOT NULL,
    address character varying(500) NOT NULL,
    city character varying(100) NOT NULL,
    state character varying(100) NOT NULL,
    phone character varying(20) NOT NULL,
    email character varying(255),
    rating double precision,
    review_count integer,
    status character varying(20),
    specializations json,
    latitude double precision,
    longitude double precision,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


--
-- Name: idempotency_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.idempotency_records (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    key character varying(255) NOT NULL,
    action character varying(100) NOT NULL,
    token_id character varying,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: medical_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.medical_records (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    filename character varying(255) NOT NULL,
    file_path character varying(500) NOT NULL,
    file_type character varying(100) NOT NULL,
    file_size integer NOT NULL,
    record_type character varying(50),
    description text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


--
-- Name: payments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payments (
    id character varying NOT NULL,
    token_id character varying NOT NULL,
    amount double precision NOT NULL,
    method character varying(20) NOT NULL,
    status character varying(20),
    transaction_id character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


--
-- Name: pharmacy_medicines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pharmacy_medicines (
    id character varying NOT NULL,
    product_id integer NOT NULL,
    batch_no character varying(50) NOT NULL,
    name character varying(200) NOT NULL,
    generic_name character varying(200),
    type character varying(100),
    distributor character varying(200),
    purchase_price double precision NOT NULL,
    selling_price double precision NOT NULL,
    stock_unit character varying(50),
    quantity integer,
    expiration_date timestamp with time zone,
    category character varying(100),
    sub_category character varying(100),
    created_at timestamp with time zone DEFAULT now(),
    hospital_id character varying,
    updated_at timestamp with time zone,
    is_deleted boolean DEFAULT false,
    deleted_at timestamp with time zone
);


--
-- Name: pharmacy_sales; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pharmacy_sales (
    id character varying NOT NULL,
    hospital_id character varying,
    patient_id character varying,
    doctor_id character varying,
    medicine_id integer,
    medicine_name character varying(200),
    quantity integer,
    unit_price double precision,
    total_price double precision,
    total_amount double precision,
    items json,
    payment_status character varying(20),
    sold_at timestamp with time zone DEFAULT now(),
    performed_by character varying,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: queues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.queues (
    id character varying NOT NULL,
    doctor_id character varying NOT NULL,
    current_token integer,
    waiting_patients integer,
    estimated_wait_time_minutes integer,
    people_ahead integer,
    total_queue integer,
    updated_at timestamp with time zone
);


--
-- Name: quick_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quick_actions (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    action_type character varying(50) NOT NULL,
    title character varying(100) NOT NULL,
    description character varying(255),
    icon character varying(50),
    route character varying(255),
    is_enabled boolean,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: refunds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.refunds (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    token_id character varying NOT NULL,
    amount double precision NOT NULL,
    status character varying(20),
    method character varying(50) NOT NULL,
    reason character varying(255),
    transaction_id character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


--
-- Name: support_tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.support_tickets (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    subject character varying(255) NOT NULL,
    description text NOT NULL,
    category character varying(50),
    priority character varying(20),
    status character varying(20),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


--
-- Name: tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tokens (
    id character varying NOT NULL,
    patient_id character varying NOT NULL,
    doctor_id character varying NOT NULL,
    hospital_id character varying NOT NULL,
    mrn character varying(50),
    token_number integer NOT NULL,
    hex_code character varying(20) NOT NULL,
    display_code character varying(20),
    appointment_date timestamp with time zone NOT NULL,
    status character varying(20),
    payment_status character varying(20),
    payment_method character varying(20),
    queue_position integer,
    total_queue integer,
    estimated_wait_time integer,
    consultation_fee double precision,
    session_fee double precision,
    total_fee double precision,
    department character varying(100),
    idempotency_key character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    doctor_name character varying(100),
    doctor_specialization character varying(100),
    doctor_avatar_initials character varying(10),
    hospital_name character varying(200),
    patient_name character varying(100),
    patient_phone character varying(20),
    queue_opt_in boolean,
    queue_opted_in_at timestamp with time zone,
    confirmed boolean,
    confirmation_status character varying(50),
    confirmed_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    duration_minutes double precision
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id character varying NOT NULL,
    name character varying(100) NOT NULL,
    email character varying(255),
    phone character varying(20),
    password_hash character varying(255) NOT NULL,
    role character varying(20),
    location_access boolean,
    date_of_birth character varying(20),
    address character varying(500),
    mrn_by_hospital json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    hospital_id character varying,
    gender character varying(20)
);


--
-- Name: wallets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wallets (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    balance double precision,
    currency character varying(10),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


--
-- Data for Name: activity_logs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.activity_logs (id, user_id, activity_type, description, meta_data, created_at, updated_at) FROM stdin;
63f6a8e3-6355-4791-9066-4f6d3e6c04b2	5b29fd07-c4cc-4431-a7e1-5fa66da5b183	PROFILE_UPDATED	User registered with AuthMethod.EMAIL authentication	{"auth_method": "AuthMethod.EMAIL", "location_access": false}	2026-04-20 19:59:38.029812+00	2026-04-20 19:59:38.029812+00
be2314ca-4e80-46fd-9b2d-5144e330d326	7fe06288-c5ae-4f5e-b3d1-61cc363f354a	PROFILE_UPDATED	User registered with AuthMethod.EMAIL authentication	{"auth_method": "AuthMethod.EMAIL", "location_access": false}	2026-04-20 21:23:18.346114+00	2026-04-20 21:23:18.346114+00
49cbee88-096a-4211-9feb-2226c55ccaed	7fe06288-c5ae-4f5e-b3d1-61cc363f354a	profile_updated	Password changed successfully	\N	2026-04-20 21:42:10.574879+00	2026-04-20 21:42:10.574879+00
e7582426-f2f3-4692-a82d-a7628b02a7ef	7fe06288-c5ae-4f5e-b3d1-61cc363f354a	profile_updated	Password changed successfully	\N	2026-04-20 21:51:40.965382+00	2026-04-20 21:51:40.965382+00
86efadcd-9d1d-4a22-b5e2-bcf5035fadb6	725d9ae1-b925-4dc9-934b-2b9df29cd028	PROFILE_UPDATED	User registered with AuthMethod.PHONE authentication	{"auth_method": "AuthMethod.PHONE", "location_access": false}	2026-04-20 21:52:33.905421+00	2026-04-20 21:52:33.905421+00
d3a3a5e6-d6a9-4c9d-8b68-c3354c926362	f5a5a72c-a9f7-4e2e-b892-d6b3a3105d1c	PROFILE_UPDATED	User registered with AuthMethod.EMAIL authentication	{"auth_method": "AuthMethod.EMAIL", "location_access": false}	2026-04-20 21:57:37.20714+00	2026-04-20 21:57:37.20714+00
1ebe49fe-1d7f-40a3-98c5-5be28023e203	f5a5a72c-a9f7-4e2e-b892-d6b3a3105d1c	profile_updated	Password changed successfully	\N	2026-04-20 21:57:38.34895+00	2026-04-20 21:57:38.34895+00
57e576f7-4813-433c-8335-eb9fa0d1ac69	903c9787-0565-42c1-b93e-f0cb17c7157a	PROFILE_UPDATED	User registered with AuthMethod.EMAIL authentication	{"auth_method": "AuthMethod.EMAIL", "location_access": false}	2026-04-20 22:30:28.551488+00	2026-04-20 22:30:28.551488+00
cb1b8e63-6a38-4c14-977b-b3fe6347e18c	3bfd95ee-8351-4890-b5dd-fc94f68d588a	PROFILE_UPDATED	User registered with AuthMethod.EMAIL authentication	{"auth_method": "AuthMethod.EMAIL", "location_access": false}	2026-04-20 22:43:30.801378+00	2026-04-20 22:43:30.801378+00
b597bebc-fe33-41ca-a55b-8e2110d1e00b	7fe06288-c5ae-4f5e-b3d1-61cc363f354a	profile_updated	Password changed successfully	\N	2026-04-20 23:06:07.555834+00	2026-04-20 23:06:07.555834+00
4b2b6371-4c13-4b10-82d3-c9c393a21188	5027b60f-2092-4816-939b-6be2aa6f1479	PROFILE_UPDATED	User registered with AuthMethod.EMAIL authentication	{"auth_method": "AuthMethod.EMAIL", "location_access": false}	2026-04-21 02:41:04.49806+00	2026-04-21 02:41:04.49806+00
\.


--
-- Data for Name: departments; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.departments (id, name, hospital_id, created_at) FROM stdin;
\.


--
-- Data for Name: doctors; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.doctors (id, name, specialization, subcategory, hospital_id, email, rating, review_count, consultation_fee, session_fee, has_session, pricing_type, status, available_days, start_time, end_time, avatar_initials, patients_per_day, created_at, updated_at, user_id) FROM stdin;
0dd0ddcb-48b0-4c4a-b54b-5a0edfdc6e71	Dr Asim Ahmed Khan	Consultant Dermatologist & Asthetic Physician	\N	340435dc-ae68-4ab9-99e8-029d60fb79c9	drasimahmed@pulseq.health	\N	0	500	\N	f	standard	available	["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]	02:00	23:30	DA	10	2026-04-20 22:08:43.150215+00	2026-04-20 22:08:43.150219+00	42b05114-187f-4e86-a095-f3e5d7d1fb64
6b9b7a95-e24c-49c3-b294-fd320cdac3b4	Dr Hassan Sadiq	Clinical Psychologist	\N	340435dc-ae68-4ab9-99e8-029d60fb79c9	drhassansadiqd@pulseq.health	\N	0	700	\N	f	standard	available	["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]	04:00	21:00	DH	10	2026-04-20 22:20:35.035337+00	2026-04-20 22:20:35.03534+00	3455f9ae-2c22-4780-9c5f-3d8f8058b96c
3e588565-6805-4353-9c22-ed1abb911b4e	Dr Rahaf Afzal	Skin Specialist Expertise in PRP,HIFU,Botox threads	\N	340435dc-ae68-4ab9-99e8-029d60fb79c9	drrahafafzal@pulseq.health	\N	0	1500	\N	f	standard	available	["Tuesday", "Thursday", "Saturday"]	04:00	20:00	DR	10	2026-04-20 22:28:16.385055+00	2026-04-20 22:28:16.385057+00	13f6bbf6-5382-4f52-adae-b6b66c2b30b1
9c8ff427-0b0a-4a16-a61b-fd97623073ca	Dr Ali Khan 	BDS/RDS-General Dentist and Oral Medicine Resident	\N	340435dc-ae68-4ab9-99e8-029d60fb79c9	dralikhan@pulseq.health	\N	0	700	\N	f	standard	available	["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]	18:00	21:00	DA	10	2026-04-20 22:31:48.371964+00	2026-04-20 22:31:48.371967+00	5bbbdb73-7dd4-43d3-ac49-d9ef12324cfa
28cebd62-fda4-46b9-bf67-545564a82cb2	Dr Kehkashan	Physical Therapsit - DPT RIU	\N	340435dc-ae68-4ab9-99e8-029d60fb79c9	drkehkashann@pulseq.health	\N	0	700	\N	f	standard	available	["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]	01:00	20:00	DK	10	2026-04-21 02:20:56.954185+00	2026-04-21 02:20:56.954188+00	836e606f-dba4-4f01-9654-fced21eb2489
0fe52691-26f5-443a-9763-ae44c1839f76	Dr Ali	General Medicine	\N	340435dc-ae68-4ab9-99e8-029d60fb79c9	ali@pulseq.health	\N	0	700	\N	f	standard	available	["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]	01:00	20:00	DA	10	2026-04-21 02:26:09.171699+00	2026-04-21 02:26:09.171701+00	6b2aea37-5dca-4ef6-9e91-4eff69d199ac
2c7171ab-3b7e-476c-96b0-477dacc1246c	Dr Ayesha	General Medicine	\N	340435dc-ae68-4ab9-99e8-029d60fb79c9	ayesha@pulseq.health	\N	0	700	\N	f	standard	available	["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]	07:00	23:00	DA	10	2026-04-21 02:27:27.622454+00	2026-04-21 02:27:27.622457+00	6beef5f9-ec1d-4e78-9473-529c8a7d9095
\.


--
-- Data for Name: hospital_sequences; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.hospital_sequences (id, hospital_id, mrn_seq, updated_at) FROM stdin;
4549efc5-44c1-470d-ae44-7fd807643c79	340435dc-ae68-4ab9-99e8-029d60fb79c9	5	2026-04-22 23:41:59.302575+00
\.


--
-- Data for Name: hospitals; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.hospitals (id, name, address, city, state, phone, email, rating, review_count, status, specializations, latitude, longitude, created_at, updated_at) FROM stdin;
340435dc-ae68-4ab9-99e8-029d60fb79c9	Rufayda Health Complex	Ibrahim Plaza, St 25, Soan Gardens Block B Islamabad	Islamabad	Islamabad	+923352015268	\N	\N	0	open	[]	\N	\N	2026-04-20 20:39:46.010342+00	2026-04-20 20:39:46.010342+00
\.


--
-- Data for Name: idempotency_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.idempotency_records (id, user_id, key, action, token_id, created_at) FROM stdin;
\.


--
-- Data for Name: medical_records; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.medical_records (id, user_id, filename, file_path, file_type, file_size, record_type, description, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: payments; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.payments (id, token_id, amount, method, status, transaction_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: pharmacy_medicines; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.pharmacy_medicines (id, product_id, batch_no, name, generic_name, type, distributor, purchase_price, selling_price, stock_unit, quantity, expiration_date, category, sub_category, created_at, hospital_id, updated_at, is_deleted, deleted_at) FROM stdin;
43d5fa96-b4dc-46b5-824d-60fde12eb0e8	182763	026	Mazitron 250mg	azithromycin	medicine	Sheikh Brother Pharma Distributor	30	52.3	Box	12	2027-12-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.384082+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
81d36d11-dbbf-4352-8fc1-713c1b08084e	182762	072	levopharm 250mg	Levocetrize	medicine	Sheikh Brother Pharma Distributor	14	71.8	Box	20	2028-02-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.385571+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
3cac59af-293d-401f-b80e-3c2945f01a7d	182307	ZD155	Zithromed suspension 200mg/5ml	Azithromycin	medicine	Sheikh Brother Pharma Distributor	300	400	Box	3	2027-02-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.386649+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
5976546f-b7d6-4083-bde7-33ddc33aaf64	182239	137	Tict beninco	methylated	medicine	Sheikh Brother Pharma Distributor	75	120	Box	10	2026-08-27 00:00:00+00	\N	\N	2026-04-21 14:08:26.387674+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
ee7483f9-1d10-494e-aac0-9b950eeb94e8	182238	25162	M kort inj	triamcinolone	medicine	Sheikh Brother Pharma Distributor	60	95	Box	3	2027-09-09 00:00:00+00	\N	\N	2026-04-21 14:08:26.388701+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
b8b6757b-bbb9-480a-ae3c-ff826b87c97b	181735	20401	Tab Cloprel 10mg	Metoclopramide	medicine	Sheikh Brother Pharma Distributor	1.5	5	Box	90	2027-02-02 00:00:00+00	\N	\N	2026-04-21 14:08:26.389713+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
370636e9-6b2e-4fd3-af6d-716aca4911e8	181734	015	Dolimol-V TAB 10/160MG	\N	medicine	Sheikh Brother Pharma Distributor	15.7	37.8	Box	56	2027-06-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.390731+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
8ea56058-a34f-4e37-8655-df127ae8e968	181646	5ehf2	tab jantolin 4mg	sulbutamol	medicine	Sheikh Brother Pharma Distributor	1.5	3	Box	100	2027-06-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.391686+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
fb3393b5-14e5-4422-8250-97919e1c98e2	181643	sx038	sofilex 500mg tab	Cefadroxil	medicine	Sheikh Brother Pharma Distributor	19	50	Tab	36	2027-09-08 00:00:00+00	\N	\N	2026-04-21 14:08:26.392639+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
40a3db20-ac93-4eb9-b28f-debaeb0f1247	181642	LF072	Levopharm 500mg	Levofloxacin	medicine	Sheikh Brother Pharma Distributor	20	71	Tab	40	2028-02-08 00:00:00+00	\N	\N	2026-04-21 14:08:26.393577+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
bac8b31e-6bd5-4bcb-b635-622ceccecf16	181634	004	Sitamin 50/1000mg	Sitagliptin Metformin HCL	medicine	Sheikh Brother Pharma Distributor	18.2	57.1	Box	14	2028-07-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.394507+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
907b0a60-2391-45eb-9a23-4a0c62c8d93b	181549	FH021	Monfusi-HC	fusidic acid hydrocortisone acetate	medicine	Sheikh Brother Pharma Distributor	210	403	Box	0	2027-08-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.395434+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
6931ad08-190e-4373-89c5-c8fb7bbcb5a1	181548	25025	Hydrotrim cream	Hydrocortisone	medicine	Sheikh Brother Pharma Distributor	95	100	Box	2	2027-01-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.39632+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
6cf472ed-e9bf-41a8-a9b0-2177ca84b85e	181547	036	Anibret cream 10g	terbinafine hcl	medicine	Sheikh Brother Pharma Distributor	140	272	Box	0	2027-07-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.397221+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
7d347738-013e-4382-9e8f-b92b82d029b6	181174	3606	Tab Fexofax 120mg	fexofenadine HCL	medicine	Sheikh Brother Pharma Distributor	12	16.4	Box	20	2028-04-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.398127+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
f111e1f6-217a-485c-b9c5-d0082adf5be4	181160	009	Onvin syp 50ml	Ondansetron	medicine	Sheikh Brother Pharma Distributor	160	490	Box	3	2027-01-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.399033+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
44e4b9ef-a4b2-4a22-ac75-3147a3184b58	181159	2590	cal-c aid Sachet	\N	medicine	Sheikh Brother Pharma Distributor	9.5	18	BOX	10	2027-02-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.399949+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
c017e0fe-a384-421b-a81e-0b794871d0d3	181158	37	Similone syp 120ml	\N	medicine	Sheikh Brother Pharma Distributor	98	125	Box 3	3	2027-11-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.40088+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
4fecc6e7-121d-4573-83a4-d43f3f176ad4	181064	36027	Octa 50mg tab	Itopride	medicine	Sheikh Brother Pharma Distributor	14.5	37.8	Box	10	2027-07-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.401791+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
a2e55c80-9e44-4775-b13c-415c8adaee7f	180760	5C-394	Moodi 3mg tab	Bromazepam	medicine	Sheikh Brother Pharma Distributor	4.65	17	Box	87	2027-02-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.402663+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
3f9c757d-eaa5-4957-a6fb-16bd9ec57f84	180759	I-106	TRANCID 500MG inj	TRANEXAMIC ACID	medicine	Sheikh Brother Pharma Distributor	35	125	Box	8	2027-08-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.403545+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
57548233-596b-4423-83d5-99f08b164c91	180304	678U	lefin syp 60ml	paracetamol	medicine	Sheikh Brother Pharma Distributor	45	58	Box	2	2026-11-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.404449+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
41a37855-4347-4ae2-86ec-3df938ba838c	180302	548	Pagabin cap 100mg	pregabalin	medicine	Sheikh Brother Pharma Distributor	16.4	40	Box	28	2026-09-01 00:00:00+00	medicine	\N	2026-04-21 14:08:26.405354+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
1264f329-d211-4606-9e4e-72882b7212ce	180267	1027	tab ferrous sulphate	ferrous sulphate 200mg	medicine	Sheikh Brother Pharma Distributor	1.2	3	Tab	100	2028-10-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.406298+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
02206baf-b4af-4195-8e36-9c465187e349	180189	385	Normax tab 5mg	Amlodipine besylate	medicine	Sheikh Brother Pharma Distributor	2.5	6	box	6	2027-07-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.407301+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
b31d3579-0d91-4692-9600-d4f4fb391a6d	179930	MX10	Moxifloxacin 400mg	MOXIFLOXACIN	medicine	Sheikh Brother Pharma Distributor	56	95	Box 1	0	2027-09-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.408267+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
cf992a9f-d130-46aa-bc5f-a1c8af515833	179929	152085	Fixef 200mg/5ml	CEFIXIME	medicine	Sheikh Brother Pharma Distributor	210	349	Box 1	0	2027-05-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.409831+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
70c4c30d-ddf8-4cdd-86b0-780c807a2838	179928	014	Dolimol-V TAB 5/80MG	Amlodipine valsartan	medicine	Sheikh Brother Pharma Distributor	11.7	22.5	Box 1	25	2027-07-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.410774+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
b7f74e91-eddd-4737-8a52-2ec7f0d572a2	179422	018	Lactoro inj 30ml	Ketorolac Tromethamine	medicine	Sheikh Brother Pharma Distributor	22	183	2	1	2026-12-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.411695+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
582520e9-3383-420c-9520-05b66554743c	179414	3739	Pregin 150mg cap	pregabalin	medicine	Sheikh Brother Pharma Distributor	13.9	40.3	Box 2	16	2027-08-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.412635+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
93e8486c-a98a-4c0e-80a7-0b869da8d4a9	179193	003	Dante 4ml inj 8mg	Ondansetron	medicine	Sheikh Brother Pharma Distributor	44	180	Box	4	2027-01-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.413589+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
792f068a-c0cb-4aa0-9016-4bc71b08d230	179035	045	Orimazole HC cream	Clotrimazole Hydrocortisone	medicine	Sheikh Brother Pharma Distributor	70	102	Box	4	2027-06-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.4145+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
98cdeef4-7c4f-42fe-9de2-c4833598bf98	178814	2511	Metrorise vials	Metronidazole	medicine	Sheikh Brother Pharma Distributor	75	160	Box	2	2027-06-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.415441+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
2c5f0b94-d2c4-495a-a81f-fa3e82082e11	178813	017	Pagabin 50MG CAP	Pregabalin	medicine	Sheikh Brother Pharma Distributor	11.7	30.6	Box	28	2027-05-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.416385+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
eec41925-4aa2-4ff4-8c2e-8584a54d69e6	178812	011	Preaed 300mg Cap	Pregabalin	medicine	Sheikh Brother Pharma Distributor	24	67	Box	28	2026-11-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.417338+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
d5e78c1c-b890-435c-9735-331c4f135f45	178811	249	Meroid Tab	Metronidazole	medicine	Sheikh Brother Pharma Distributor	2.5	5	1	18	2027-03-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.41827+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
12d53067-26c3-46c9-a1c7-3e03af8d6bf9	178810	008	Eminol syp	Ammonium chloride	medicine	Sheikh Brother Pharma Distributor	45	150	1	2	2027-08-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.419192+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
ed4f308a-ed11-4128-9c5b-45e70ed89036	178799	A125029	Levitra 500MG TAB	Levetiracetum	medicine	Sheikh Brother Pharma Distributor	25	51	Box	11	2027-01-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.420108+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
5072b3f4-af3a-429a-9b1f-eeac5882221f	178797	25004	lactodil syrup	Lactulose	medicine	Sheikh Brother Pharma Distributor	280	377	Box	0	2027-08-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.421011+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
cb7b4dcf-d4f9-4c46-b175-e47fd28eeaea	178796	1	Needle 24G	\N	medicine	Sheikh Brother Pharma Distributor	3.2	25	Box	88	2028-11-30 00:00:00+00	\N	\N	2026-04-21 14:08:26.4219+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
afc45975-d8cf-416a-bf36-5794224ec9a6	178416	L2623	Ibuped syp	Ibuprofen	medicine	Sheikh Brother Pharma Distributor	45	65	Box	1	2027-06-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.422734+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
36ef461b-236d-45ff-a309-6fa364eea309	177831	01	3 Way Stopper	\N	medicine	Sheikh Brother Pharma Distributor	80	200	Box	6	2028-12-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.42355+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
b5aebed5-9fa5-43b1-bbb8-ba8812aa031e	177830	01-25	Gluta Glow tabs	Gluta	medicine	Sheikh Brother Pharma Distributor	1995	2850	Box	1	2028-06-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.424353+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
c14f1a4f-22c1-4024-ada8-aea43e42f5d2	176998	333	Cecobal	Mecobalamin	medicine	Sheikh Brother Pharma Distributor	21	80	Box	4	2027-07-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.425146+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
fc18d9b7-18d0-490e-971f-95377863175a	176997	034	Clavcort 312.5mg Syp	Co-Amoxiclav	medicine	Sheikh Brother Pharma Distributor	220	312	Box	2	2027-09-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.425994+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
e8ba3770-9e27-476f-9987-f6fd926d27de	176995	447	Lemache syp	ibuprofen	medicine	Sheikh Brother Pharma Distributor	55	93	Box	0	2027-05-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.426829+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
c4f2e2d5-a5c6-42cc-aeab-39488c5d708a	176509	KC065	Keto Craft inj	Ketorolac Tromethamine	medicine	Sheikh Brother Pharma Distributor	26	100	Box	1	2027-01-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.427655+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
ab06973e-8351-4312-89c2-76374f9b8a8f	176508	MZ021	Mazitron 500mg	Azithromycin	medicine	Sheikh Brother Pharma Distributor	46	95	Box	4	2027-08-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.428475+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
29d22bdf-9c8b-40b3-987f-40c9bb424e49	176507	23-ABG-06	Shamz Colic Drops	Colic Drops	medicine	Sheikh Brother Pharma Distributor	54	100	Box	4	2027-08-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.429277+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
2a8aea2c-f4ba-4dfc-a076-682d98657f67	176209	25H222	biotin tab	biofol	medicine	Sheikh Brother Pharma Distributor	750	1450	Box	2	2027-07-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.430101+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
8c858f44-96a3-4c97-9461-719ef6893792	176208	AE034	Anibret 250mg	Terbinafine	medicine	Sheikh Brother Pharma Distributor	26	78	Box	20	2027-01-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.670001+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
7ed4e376-7c9e-4dba-ad5e-297e66c3b5a3	176207	18425	Lipinox 5mg tab	Amlodipine besylate	medicine	Sheikh Brother Pharma Distributor	2.2	9.1	Box	70	2027-05-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.670777+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
de769765-65c6-41b3-a684-5f91d4cd479b	176206	AV011	Atorpharm 20mg	Atorvastatin	medicine	Sheikh Brother Pharma Distributor	12	40	Box	39	2026-06-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.671453+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
0c50c634-5ac9-4b85-8b5d-bad0765c448a	176205	AA016	Atorpharm  10mg	Atorvastatin	medicine	Sheikh Brother Pharma Distributor	9.5	24	Box	30	2027-02-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.672116+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
a34aadb0-1c89-461a-9531-e9d93568b001	176204	T 285	Tab Tramadol plus	tramadol HCL	medicine	Sheikh Brother Pharma Distributor	10	20	Box	33	2027-09-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.672776+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
11eb420e-d1c0-4d07-a329-23593e3c5e38	176202	ADM2410	Arocof DM syp	Epharam Lab	medicine	Sheikh Brother Pharma Distributor	75	300	Box	3	2026-11-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.673516+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
38a7a3ce-b6b5-4f45-820c-1d7c491f07dd	176111	I-110	Tramadol inj	Tramadol	medicine	Sheikh Brother Pharma Distributor	22	100	Box	4	2026-09-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.674619+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
1742b3e7-ba4f-46bc-a5cd-aad2fb478e26	176047	KN-155	Kamenate inj 50mg	Dimenhydrinate	medicine	Sheikh Brother Pharma Distributor	8	50	Box	30	2027-05-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.675478+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
f30d2dbb-7e3b-4dea-ba3f-be1ae9f44e5b	176002	S-071	Clavcort 156.25mg syp	Co-Amoxiclav	medicine	Sheikh Brother Pharma Distributor	160	192	Box	3	2027-09-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.676208+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
a302f726-31fa-473d-a2be-e6f289ab13f8	175995	S-034	Clavcort 312.5mg Syp	Co-Amoxiclav	medicine	Sheikh Brother Pharma Distributor	200	312	Box	1	2027-03-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.676876+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
31ab3c47-1a97-4bff-94ca-e13b8517bc5e	175994	F010	Arthonil 50mg	Diclofenac Sodium	medicine	Sheikh Brother Pharma Distributor	2.3	5.35	Box	48	2027-10-31 00:00:00+00	\N	\N	2026-04-21 14:08:26.67752+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
63a433fd-83c9-458c-82f9-00862fc48062	175993	TC002	Relidol 50mg tab	Tramadol HCL	medicine	Sheikh Brother Pharma Distributor	9.5	25	Box	51	2027-02-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.678157+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
3a9f41ae-b3cd-4730-9a4b-e5369f9ef314	175992	NVS2503JP	Nutrivit jar	Multi vitamins	medicine	Sheikh Brother Pharma Distributor	350	1100	Box	1	2026-12-31 00:00:00+00	\N	\N	2026-04-21 14:08:26.678776+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
9b74ec1f-a72b-449c-b415-ddb2e45afbd3	175987	524	Voveron 100 tab	Diclofenac sodium	medicine	Sheikh Brother Pharma Distributor	3.2	9	Box	79	2027-05-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.679427+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
5ae251fd-df91-4820-aeaf-2a094c339d95	175986	C-065	Mafdic cream	Fusidic Acid	medicine	Sheikh Brother Pharma Distributor	150	265	Box	4	2026-11-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.680061+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
8dc3f42b-7d7d-4c19-b7df-c0285a9fe445	175983	286	Fevamol  100ml	Paracetamol	medicine	Sheikh Brother Pharma Distributor	155	300	Box	1	2027-03-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.680736+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
3ffaf0de-c285-40f2-850a-fe0857dca977	175978	3523	E-Citprim Tab 10mg	Escitalopram	medicine	Sheikh Brother Pharma Distributor	9.2	25	Box	16	2027-05-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.681362+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
c07835c0-fb73-4ce8-bb1d-afea2fea529d	175858	E084	Monti 10mg	Montelukast as sodium	medicine	Sheikh Brother Pharma Distributor	9.5	30	Box	14	2026-12-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.682012+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
525eff1a-5948-45d6-b1c2-f5ece6fd045f	175800	05366	velomed 500mg	cephradine	medicine	Sheikh Brother Pharma Distributor	32	45	1	32	2028-05-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.682617+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
d56963b2-ee3b-4f8e-b476-ca72b97d0e75	175727	PB020	Pagabin 150mg cap	Pregabalin	medicine	Sheikh Brother Pharma Distributor	15	60	Box	31	2027-02-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.683304+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
ffe857ed-c688-465b-9bb5-2e2c422e8b0e	175726	T-197	Citiflex 550mg Tab	Naproxen Sodium	medicine	Sheikh Brother Pharma Distributor	12	22.5	Box	24	2027-08-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.683924+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
a37d8654-830a-48d3-9c7c-84f17816a01c	175617	I7-5	Kamitil 5mg tab	Prochlorperazine	medicine	Sheikh Brother Pharma Distributor	1.5	5	Box	93	2028-03-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.68464+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
087a720d-26af-42ba-893d-92b77368c31a	175480	3575	One Best 10mg	Ebastine	medicine	Sheikh Brother Pharma Distributor	8.5	17.5	Box	24	2027-02-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.685954+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
4ad6e1f6-a772-40ff-93d8-b859c0c64cad	175479	LZ-010	CADLIZO 600MB TAB	LINEZOLID	medicine	Sheikh Brother Pharma Distributor	54.16	70	Box 2	20	2027-08-28 00:00:00+00	\N	\N	2026-04-21 14:08:26.687484+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
3392e543-f8af-47e9-a37e-f7ee52a1dda8	175478	C-253	ESORAL 40MG CAP	Esomeprazole	medicine	Sheikh Brother Pharma Distributor	9	23	Box	29	2027-07-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.688477+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
6ed106ff-4eb9-45f7-aafd-10e2bf0daab9	175477	DVA-491	VITAMIN A DROP	VITAMIN A	medicine	Sheikh Brother Pharma Distributor	90	450	Box 2	0	2026-09-30 00:00:00+00	medicine	\N	2026-04-21 14:08:26.689323+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
2d6e5f5a-e086-44cb-ab2f-a0a371c221f4	175476	DME-419	MERITONE drops	V D3	medicine	Sheikh Brother Pharma Distributor	90	395	Box 2	2	2026-10-30 00:00:00+00	medicine	\N	2026-04-21 14:08:26.690144+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
c93a47f3-265f-4930-9c6b-95029481d3fc	175475	8769	BEXTRIN 20MG	PIROXICAM	medicine	Sheikh Brother Pharma Distributor	5	16	Box 2	40	2027-05-22 00:00:00+00	medicine	\N	2026-04-21 14:08:26.690899+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
d60809ff-fe89-4b56-9db6-91567df71600	175465	T-006	SPASTOP 40MG tab	DROTAVERINE HC	medicine	Sheikh Brother Pharma Distributor	4	10	Box 3	26	2027-07-21 00:00:00+00	medicine	\N	2026-04-21 14:08:26.691639+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
1e541808-ed49-4d27-b2ff-b330245b141c	175248	DL-050	DILARM-L INJ	DICLOFENAC SODIUM	medicine	Sheikh Brother Pharma Distributor	25	50	Box 1	34	2026-07-23 00:00:00+00	medicine	\N	2026-04-21 14:08:26.692396+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
7283d449-25ca-46b5-ae1e-cfe3981bcc0f	175247	PL-136	PIROXIL 20MG  INJ	PIROXICAM	medicine	Sheikh Brother Pharma Distributor	13	22	Box	9	2027-05-20 00:00:00+00	medicine	\N	2026-04-21 14:08:26.693098+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
f1bb0c93-3f39-4238-b01a-45d9dacdbcb4	175242	092	NORAN 40MG CAP	OMEPRAZOLE 40MG	medicine	Sheikh Brother Pharma Distributor	8	30	Box	18	2027-03-16 00:00:00+00	medicine	\N	2026-04-21 14:08:26.693759+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
669cbf55-fabb-4d08-84df-8101e2f063aa	175235	667	Medidol TAB	Paracetamol Caffeine Chlorpheniramine	medicine	Sheikh Brother Pharma Distributor	3	4	Box	23	2028-03-28 00:00:00+00	medicine	\N	2026-04-21 14:08:26.694454+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
48194cfd-ea13-473b-aa9c-4b031c61c12b	174583	1717	CranBerry Sachet	Cranberry	medicine	Sheikh Brother Pharma Distributor	16	45	Box	20	2027-02-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.695099+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
021437d8-9e10-4499-b0c5-5af424ec8d5d	174581	1576	So-Ceph 500mg	Cephradine	medicine	Sheikh Brother Pharma Distributor	24.167	40.417	Box	24	2027-07-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.695729+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
fd6e5e78-c160-4214-9a03-938cdaf527fd	174578	1631	Ro-Relax tab 3mg	brozemapam	medicine	Sheikh Brother Pharma Distributor	4.3	5	Box	18	2026-10-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.696384+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
214a7fb6-c70a-4b9e-a746-01c90810c71c	174576	429608	Vefixime DS Syrup	\N	medicine	Sheikh Brother Pharma Distributor	190	330	Box	1	2026-06-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.697006+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
3e537f02-ea70-4454-8394-ae8abdcc1d27	173869	1753	Rozolam 0.5mg	Alprazolam	medicine	Sheikh Brother Pharma Distributor	5	8	Box	192	2027-04-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.697625+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
a013a828-e113-446a-9400-d210848d48f3	69588	2	NS 100ml	Saline	medicine	Sheikh Brother Pharma Distributor	30	85	Box	14	2028-05-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.698237+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
a211d59b-53f7-4f97-a1c0-cbb214ef8b8c	65152	1	NS 1000ml	Saline	medicine	Sheikh Brother Pharma Distributor	90	150	Box	16	2027-11-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.698852+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
e7efd9fc-cde4-491d-a677-bee9cf216b82	64899	1	RL 500 ml	Ringer	medicine	Sheikh Brother Pharma Distributor	65	130	Bottle	15	2027-01-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.699479+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
d073d9e3-6cf9-446c-afd3-54a048250fd0	63300	1	NEEDLE 26g	\N	medicine	Sheikh Brother Pharma Distributor	3.2	6	Box	96	2029-05-09 00:00:00+00	\N	\N	2026-04-21 14:08:26.700245+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
af2727b2-5cfd-47e0-ba1a-639b90895bb2	63289	019	LINK-D capsule 200000 IU	Cholecalciferol	medicine	Sheikh Brother Pharma Distributor	55	290	8	6	2027-02-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.700943+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
bb0dac2b-a21d-4922-b697-9a20a3843e4a	63124	1	CIXIM syrup 100mg/5ml	cefixime	medicine	Sheikh Brother Pharma Distributor	185	246	Box	2	2026-12-01 00:00:00+00	\N	\N	2026-04-21 14:08:26.701586+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
a1a0a6cb-02f9-4a73-8164-d16e2e267568	1827646	BATCH-A12234	Hamda 200mg	Zehar		Bassam	22	29		5	2026-04-30 00:00:00+00			2026-04-21 21:44:57.218643+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N	f	\N
\.


--
-- Data for Name: pharmacy_sales; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.pharmacy_sales (id, hospital_id, patient_id, doctor_id, medicine_id, medicine_name, quantity, unit_price, total_price, total_amount, items, payment_status, sold_at, performed_by, created_at) FROM stdin;
\.


--
-- Data for Name: queues; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.queues (id, doctor_id, current_token, waiting_patients, estimated_wait_time_minutes, people_ahead, total_queue, updated_at) FROM stdin;
\.


--
-- Data for Name: quick_actions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.quick_actions (id, user_id, action_type, title, description, icon, route, is_enabled, created_at) FROM stdin;
7b80eea5-20b4-4ad8-980f-cb8fa3e0c111	903c9787-0565-42c1-b93e-f0cb17c7157a	generate_token	Generate Token	Create a new SmartToken for appointment	ticket	/tokens/generate	t	2026-04-20 22:30:29.772573+00
46938653-3afa-4408-8a96-d810a43b782c	903c9787-0565-42c1-b93e-f0cb17c7157a	view_tokens	My Tokens	View all your SmartTokens	list	/tokens/my-tokens	t	2026-04-20 22:30:29.772576+00
5707358e-b200-4e88-8900-f9c4f4aa8486	903c9787-0565-42c1-b93e-f0cb17c7157a	find_hospitals	Find Hospitals	Search for nearby hospitals	hospital	/hospitals/search	t	2026-04-20 22:30:29.772576+00
34e10169-b324-4b45-82da-ab9a125e8663	903c9787-0565-42c1-b93e-f0cb17c7157a	profile	Profile	Update your profile information	user	/auth/me	t	2026-04-20 22:30:29.772577+00
616fc037-0a10-4666-8b3c-4736f5ff7c97	7fe06288-c5ae-4f5e-b3d1-61cc363f354a	generate_token	Generate Token	Create a new SmartToken for appointment	ticket	/tokens/generate	t	2026-04-21 00:45:53.355791+00
9843a5fd-604d-44c6-984e-65e661c38997	7fe06288-c5ae-4f5e-b3d1-61cc363f354a	view_tokens	My Tokens	View all your SmartTokens	list	/tokens/my-tokens	t	2026-04-21 00:45:53.355795+00
940eb501-fc23-42fd-9295-3488a9bc1a26	7fe06288-c5ae-4f5e-b3d1-61cc363f354a	find_hospitals	Find Hospitals	Search for nearby hospitals	hospital	/hospitals/search	t	2026-04-21 00:45:53.355796+00
3c8b1c81-84cd-4c14-bd6d-f5a15ff7670e	7fe06288-c5ae-4f5e-b3d1-61cc363f354a	profile	Profile	Update your profile information	user	/auth/me	t	2026-04-21 00:45:53.355797+00
\.


--
-- Data for Name: refunds; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.refunds (id, user_id, token_id, amount, status, method, reason, transaction_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: support_tickets; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.support_tickets (id, user_id, subject, description, category, priority, status, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: tokens; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.tokens (id, patient_id, doctor_id, hospital_id, mrn, token_number, hex_code, display_code, appointment_date, status, payment_status, payment_method, queue_position, total_queue, estimated_wait_time, consultation_fee, session_fee, total_fee, department, idempotency_key, created_at, updated_at, doctor_name, doctor_specialization, doctor_avatar_initials, hospital_name, patient_name, patient_phone, queue_opt_in, queue_opted_in_at, confirmed, confirmation_status, confirmed_at, cancelled_at, started_at, completed_at, duration_minutes) FROM stdin;
114b00d2-b389-41c7-9534-4d1775b75a46	871cb8f4-53fc-4220-b838-2131ce0e4313	0fe52691-26f5-443a-9763-ae44c1839f76	340435dc-ae68-4ab9-99e8-029d60fb79c9	MRN-0001	1	114b00d2	A-001	2026-04-22 23:50:05.592756+00	pending	pending	\N	\N	\N	0	700	\N	750	fever	\N	2026-04-22 23:50:05.578199+00	\N	Dr Ali	\N	\N	Rufayda Health Complex	Ahmed	\N	f	\N	f	\N	\N	\N	\N	\N	\N
9dc750fe-24fb-49ed-88cb-8e65e43f8b04	871cb8f4-53fc-4220-b838-2131ce0e4313	0fe52691-26f5-443a-9763-ae44c1839f76	340435dc-ae68-4ab9-99e8-029d60fb79c9	MRN-0001	1	9dc750fe	A-001	2026-04-23 00:06:05.100968+00	pending	pending	\N	\N	\N	0	700	\N	750	fever\n	\N	2026-04-23 00:06:05.079889+00	\N	Dr Ali	\N	\N	Rufayda Health Complex	Ali	\N	f	\N	f	\N	\N	\N	\N	\N	\N
2799cb54-bb14-405a-8f4d-1977b1466505	6a067f39-452c-4144-a42f-20e36ec213a0	0fe52691-26f5-443a-9763-ae44c1839f76	340435dc-ae68-4ab9-99e8-029d60fb79c9	MRN-0003	2	2799cb54	A-002	2026-04-23 00:20:54.636865+00	pending	pending	\N	\N	\N	15	700	\N	750	feverrr	\N	2026-04-23 00:20:54.59343+00	\N	Dr Ali	\N	\N	Rufayda Health Complex	Ahmed	\N	f	\N	f	\N	\N	\N	\N	\N	\N
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, name, email, phone, password_hash, role, location_access, date_of_birth, address, mrn_by_hospital, created_at, updated_at, hospital_id, gender) FROM stdin;
5b29fd07-c4cc-4431-a7e1-5fa66da5b183	Muhammad Huzaifa Gill	huzaifagill@pulseq.health	+923491394355	$2b$12$y/zDyEm99sM5PlJA4dxswevpbsS6od6ihmn1lZlJ6DlwIXNy28QSS	admin	f	\N	\N	{}	2026-04-20 19:59:37.715286+00	2026-04-20 19:59:37.715286+00	\N	\N
871cb8f4-53fc-4220-b838-2131ce0e4313	Ali	\N	03491394355		patient	f	2006-04-27	\N	{"340435dc-ae68-4ab9-99e8-029d60fb79c9": "MRN-0001"}	2026-04-22 01:35:49.335924+00	2026-04-23 00:06:05.051986+00	\N	Male
6a067f39-452c-4144-a42f-20e36ec213a0	Ahmed	\N	03251714253		patient	f	2006-04-27	\N	{"340435dc-ae68-4ab9-99e8-029d60fb79c9": "MRN-0003"}	2026-04-22 21:59:26.269862+00	2026-04-23 00:20:54.547017+00	\N	Male
725d9ae1-b925-4dc9-934b-2b9df29cd028	Huzaifa Tariq	cadethuzaifatariq@gmail.com	+923251714253	$2b$12$Cp8AzTrCK0FzrXdkIdm8jONsJmffa10ajtFlLbd03O5JkPi1u4ELa	patient	f	\N	\N	{}	2026-04-20 21:52:33.623377+00	2026-04-20 21:52:33.623377+00	\N	\N
f5a5a72c-a9f7-4e2e-b892-d6b3a3105d1c	Test User	testuser_1776722256402@example.com	\N	$2b$12$61X6kqraWzVpv0S9oA2elOdsNjncJD74YEixcooNlWHD2ohOTXd9q	patient	f	\N	\N	{}	2026-04-20 21:57:36.852728+00	2026-04-20 21:57:38.339511+00	\N	\N
42b05114-187f-4e86-a095-f3e5d7d1fb64	Dr Asim Ahmed Khan	drasimahmed@pulseq.health	\N	$2b$12$GGtnpDfCVEx3ZdPz6fHJDupGbI4nHuJSgJVoHXDegNeOXDIpyv/1S	doctor	f	\N	\N	{}	2026-04-20 22:08:43.140497+00	2026-04-20 22:08:43.140517+00	\N	\N
3455f9ae-2c22-4780-9c5f-3d8f8058b96c	Dr Hassan Sadiq	drhassansadiqd@pulseq.health	\N	$2b$12$n/htKYqX9.4l.QS0NwVDzOYPdrUmdOhoRGs1tPaKcT7ZKGoSbK/02	doctor	f	\N	\N	{}	2026-04-20 22:20:35.02869+00	2026-04-20 22:20:35.028694+00	\N	\N
13f6bbf6-5382-4f52-adae-b6b66c2b30b1	Dr Rahaf Afzal	drrahafafzal@pulseq.health	\N	$2b$12$nMc23SL6Zsb4nt8QWUAScePwzzFHI6yMXy0wWernZvRGTTHBCDM1a	doctor	f	\N	\N	{}	2026-04-20 22:28:16.380953+00	2026-04-20 22:28:16.380957+00	\N	\N
903c9787-0565-42c1-b93e-f0cb17c7157a	Test User	test_dash_1776724227416@example.com	\N	$2b$12$f3JkUIFZ8HcKV9uYKHzoreOk8BeMYbg4hPpEC3tJ/l3Yhh14lFXYK	patient	f	\N	\N	{}	2026-04-20 22:30:28.243953+00	2026-04-20 22:30:28.243953+00	\N	\N
5bbbdb73-7dd4-43d3-ac49-d9ef12324cfa	Dr Ali Khan 	dralikhan@pulseq.health	\N	$2b$12$9D9AN/QeLIXNcpmlYNVgV.dPaH86NxoHpaprNlcvW1RKIDFDq9BlW	doctor	f	\N	\N	{}	2026-04-20 22:31:48.362802+00	2026-04-20 22:31:48.362808+00	\N	\N
c20848bb-d0e5-464b-add0-7089c73658d6	Dr Kehkashan	drkehkashan@pulseq.health	\N	$2b$12$RGVSjjbo8UgggxBXh5JNJ.kAGBuvkzD11mbD8bL8kpABFg2e9uxem	doctor	f	\N	\N	{}	2026-04-20 22:36:48.918649+00	2026-04-20 22:36:48.918654+00	\N	\N
3bfd95ee-8351-4890-b5dd-fc94f68d588a	Test Doc	test_dash_1776725009947@example.com	\N	$2b$12$TCRH0g1rRZEQDRv22gw9FOBGMvif7.M5gMU8YZoHT5TK/ncMBdekG	patient	f	\N	\N	{}	2026-04-20 22:43:30.454462+00	2026-04-20 22:43:30.454462+00	\N	\N
7fe06288-c5ae-4f5e-b3d1-61cc363f354a	Muhammad Huzaifa Gill	huzaifagill283@gmail.com	+923491394344	$2b$12$Nrcv8XaMwfbi.xsIRBfidO0ngPuB9Lvvl7TnogcDTc58uXippCd4e	patient	f	\N	\N	{}	2026-04-20 21:23:17.828542+00	2026-04-20 23:06:07.545273+00	\N	\N
836e606f-dba4-4f01-9654-fced21eb2489	Dr Kehkashan	drkehkashann@pulseq.health	\N	$2b$12$aw/x8O9OFKqTlYMneBIZ1e8ebehQ44gMxAsbpuhZUPWi1eh59FFny	doctor	f	\N	\N	{}	2026-04-21 02:20:56.947596+00	2026-04-21 02:20:56.947602+00	\N	\N
6b2aea37-5dca-4ef6-9e91-4eff69d199ac	Dr Ali	ali@pulseq.health	\N	$2b$12$CKuxH5pdUtTyxR6WiexXT.tNSle9nrrJgltgyKfmLnlcE0pcNzWoO	doctor	f	\N	\N	{}	2026-04-21 02:26:09.168273+00	2026-04-21 02:26:09.168298+00	\N	\N
6beef5f9-ec1d-4e78-9473-529c8a7d9095	Dr Ayesha	ayesha@pulseq.health	\N	$2b$12$.Hm8F1nP.91UBekk3h34weUNNlszRaqjudMxvJsoaRNqyBTxaNwwO	doctor	f	\N	\N	{}	2026-04-21 02:27:27.616123+00	2026-04-21 02:27:27.616129+00	\N	\N
5027b60f-2092-4816-939b-6be2aa6f1479	Rufayda Pharmacy	rufaydapharmacy@gmail.com	\N	$2b$12$eeqMZWDHL3FchUukxwxmQe2Rukx1aCG31lc1p3QVM44swEn8OeMMG	pharmacy	f	\N	\N	{}	2026-04-21 02:41:04.180946+00	2026-04-21 02:41:04.180946+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N
f173b8f0-4637-450a-821d-a62de234f5a9	Rufayda Receptionist	rufaydareceptionist@pulseq.health	+923352015268	$2b$12$nUOzYZL5ZRk2jntnHr8Ua.Qpc7eARgq2mGtsIb3OSIibPM2clvecW	receptionist	f	\N	\N	{}	2026-04-21 22:47:33.43264+00	2026-04-21 22:47:33.43264+00	340435dc-ae68-4ab9-99e8-029d60fb79c9	\N
915fcae9-43cc-4dc6-bd94-2cbc89bf72b4	Test Walkin	\N	9999999999		patient	f	\N	\N	{}	2026-04-22 00:41:28.620202+00	\N	\N	\N
4e1ea444-acc3-4335-beed-5b9ef6e1604c	Test MRN	\N	1231231231		patient	f	\N	\N	{}	2026-04-22 20:57:54.586966+00	\N	\N	\N
c2ac38d6-066e-49b8-a85b-97e856fda332	Ali	\N	03458455555		patient	f	2006-04-27	\N	{"340435dc-ae68-4ab9-99e8-029d60fb79c9": "MRN-0002"}	2026-04-22 21:13:29.678656+00	2026-04-22 21:13:29.708665+00	\N	\N
5311d673-5740-451b-abdf-2c4cb9b0e12b	ahmed	\N	03217627927		patient	f	2006-04-27	\N	{"340435dc-ae68-4ab9-99e8-029d60fb79c9": "MRN-0004"}	2026-04-22 22:52:57.554098+00	2026-04-22 22:52:57.583551+00	\N	Male
e82663f6-ab49-45db-b3ee-d3f4d2cc90ce	Saim	\N	03457889977		patient	f	2006-04-27	\N	{"340435dc-ae68-4ab9-99e8-029d60fb79c9": "MRN-0005"}	2026-04-22 23:41:59.28828+00	2026-04-22 23:41:59.310205+00	\N	Male
\.


--
-- Data for Name: wallets; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.wallets (id, user_id, balance, currency, created_at, updated_at) FROM stdin;
\.


--
-- Name: activity_logs activity_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_pkey PRIMARY KEY (id);


--
-- Name: departments departments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_pkey PRIMARY KEY (id);


--
-- Name: doctors doctors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doctors
    ADD CONSTRAINT doctors_pkey PRIMARY KEY (id);


--
-- Name: hospital_sequences hospital_sequences_hospital_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospital_sequences
    ADD CONSTRAINT hospital_sequences_hospital_id_key UNIQUE (hospital_id);


--
-- Name: hospital_sequences hospital_sequences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospital_sequences
    ADD CONSTRAINT hospital_sequences_pkey PRIMARY KEY (id);


--
-- Name: hospitals hospitals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospitals
    ADD CONSTRAINT hospitals_pkey PRIMARY KEY (id);


--
-- Name: idempotency_records idempotency_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_records
    ADD CONSTRAINT idempotency_records_pkey PRIMARY KEY (id);


--
-- Name: medical_records medical_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_records
    ADD CONSTRAINT medical_records_pkey PRIMARY KEY (id);


--
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);


--
-- Name: pharmacy_medicines pharmacy_medicines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pharmacy_medicines
    ADD CONSTRAINT pharmacy_medicines_pkey PRIMARY KEY (id);


--
-- Name: pharmacy_sales pharmacy_sales_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pharmacy_sales
    ADD CONSTRAINT pharmacy_sales_pkey PRIMARY KEY (id);


--
-- Name: queues queues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.queues
    ADD CONSTRAINT queues_pkey PRIMARY KEY (id);


--
-- Name: quick_actions quick_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quick_actions
    ADD CONSTRAINT quick_actions_pkey PRIMARY KEY (id);


--
-- Name: refunds refunds_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_pkey PRIMARY KEY (id);


--
-- Name: support_tickets support_tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_tickets
    ADD CONSTRAINT support_tickets_pkey PRIMARY KEY (id);


--
-- Name: tokens tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tokens
    ADD CONSTRAINT tokens_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_phone_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_phone_key UNIQUE (phone);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: wallets wallets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT wallets_pkey PRIMARY KEY (id);


--
-- Name: wallets wallets_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT wallets_user_id_key UNIQUE (user_id);


--
-- Name: idx_departments_hospital_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_departments_hospital_id ON public.departments USING btree (hospital_id);


--
-- Name: idx_departments_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_departments_name ON public.departments USING btree (name);


--
-- Name: idx_doctors_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_doctors_created_at ON public.doctors USING btree (created_at DESC);


--
-- Name: idx_doctors_hospital_specialization; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_doctors_hospital_specialization ON public.doctors USING btree (hospital_id, specialization);


--
-- Name: idx_doctors_hospital_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_doctors_hospital_status ON public.doctors USING btree (hospital_id, status);


--
-- Name: idx_doctors_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_doctors_name_trgm ON public.doctors USING gin (name public.gin_trgm_ops);


--
-- Name: idx_doctors_specialization; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_doctors_specialization ON public.doctors USING btree (specialization);


--
-- Name: idx_doctors_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_doctors_status ON public.doctors USING btree (status);


--
-- Name: idx_doctors_subcategory; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_doctors_subcategory ON public.doctors USING btree (subcategory);


--
-- Name: idx_hospitals_city; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hospitals_city ON public.hospitals USING btree (city);


--
-- Name: idx_hospitals_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hospitals_created_at ON public.hospitals USING btree (created_at DESC);


--
-- Name: idx_hospitals_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hospitals_name_trgm ON public.hospitals USING gin (name public.gin_trgm_ops);


--
-- Name: idx_hospitals_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hospitals_status ON public.hospitals USING btree (status);


--
-- Name: idx_payments_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_payments_status ON public.payments USING btree (status);


--
-- Name: idx_payments_token_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_payments_token_id ON public.payments USING btree (token_id);


--
-- Name: idx_pharmacy_medicines_batch_no; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_batch_no ON public.pharmacy_medicines USING btree (batch_no);


--
-- Name: idx_pharmacy_medicines_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_category ON public.pharmacy_medicines USING btree (category);


--
-- Name: idx_pharmacy_medicines_expiration_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_expiration_date ON public.pharmacy_medicines USING btree (expiration_date);


--
-- Name: idx_pharmacy_medicines_generic_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_generic_name_trgm ON public.pharmacy_medicines USING gin (generic_name public.gin_trgm_ops);


--
-- Name: idx_pharmacy_medicines_hospital_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_hospital_category ON public.pharmacy_medicines USING btree (hospital_id, category);


--
-- Name: idx_pharmacy_medicines_hospital_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_hospital_id ON public.pharmacy_medicines USING btree (hospital_id);


--
-- Name: idx_pharmacy_medicines_hospital_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_hospital_name ON public.pharmacy_medicines USING btree (hospital_id, name);


--
-- Name: idx_pharmacy_medicines_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_name_trgm ON public.pharmacy_medicines USING gin (name public.gin_trgm_ops);


--
-- Name: idx_pharmacy_medicines_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_product_id ON public.pharmacy_medicines USING btree (product_id);


--
-- Name: idx_pharmacy_medicines_quantity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_quantity ON public.pharmacy_medicines USING btree (quantity);


--
-- Name: idx_pharmacy_medicines_selling_price; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_selling_price ON public.pharmacy_medicines USING btree (selling_price);


--
-- Name: idx_pharmacy_medicines_stock_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_stock_status ON public.pharmacy_medicines USING btree (hospital_id, quantity, expiration_date);


--
-- Name: idx_pharmacy_medicines_sub_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_sub_category ON public.pharmacy_medicines USING btree (sub_category);


--
-- Name: idx_pharmacy_medicines_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_medicines_updated_at ON public.pharmacy_medicines USING btree (updated_at DESC);


--
-- Name: idx_pharmacy_sales_date_revenue; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_sales_date_revenue ON public.pharmacy_sales USING btree (sold_at, total_price);


--
-- Name: idx_pharmacy_sales_doctor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_sales_doctor_id ON public.pharmacy_sales USING btree (doctor_id);


--
-- Name: idx_pharmacy_sales_hospital_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_sales_hospital_id ON public.pharmacy_sales USING btree (hospital_id);


--
-- Name: idx_pharmacy_sales_hospital_sold_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_sales_hospital_sold_at ON public.pharmacy_sales USING btree (hospital_id, sold_at DESC);


--
-- Name: idx_pharmacy_sales_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_sales_patient_id ON public.pharmacy_sales USING btree (patient_id);


--
-- Name: idx_pharmacy_sales_payment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_sales_payment_status ON public.pharmacy_sales USING btree (payment_status);


--
-- Name: idx_pharmacy_sales_performed_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_sales_performed_by ON public.pharmacy_sales USING btree (performed_by);


--
-- Name: idx_pharmacy_sales_sold_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pharmacy_sales_sold_at ON public.pharmacy_sales USING btree (sold_at DESC);


--
-- Name: idx_queues_doctor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_queues_doctor_id ON public.queues USING btree (doctor_id);


--
-- Name: idx_tokens_appointment_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tokens_appointment_date ON public.tokens USING btree (appointment_date);


--
-- Name: idx_tokens_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tokens_created_at ON public.tokens USING btree (created_at DESC);


--
-- Name: idx_tokens_department; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tokens_department ON public.tokens USING btree (department);


--
-- Name: idx_tokens_doctor_date_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tokens_doctor_date_status ON public.tokens USING btree (doctor_id, appointment_date, status);


--
-- Name: idx_tokens_hospital_date_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tokens_hospital_date_status ON public.tokens USING btree (hospital_id, appointment_date, status);


--
-- Name: idx_tokens_mrn; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tokens_mrn ON public.tokens USING btree (mrn);


--
-- Name: idx_tokens_patient_status_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tokens_patient_status_created ON public.tokens USING btree (patient_id, status, created_at DESC);


--
-- Name: idx_tokens_payment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tokens_payment_status ON public.tokens USING btree (payment_status);


--
-- Name: idx_tokens_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tokens_status ON public.tokens USING btree (status);


--
-- Name: idx_users_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_created_at ON public.users USING btree (created_at DESC);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_users_hospital_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_hospital_id ON public.users USING btree (hospital_id);


--
-- Name: idx_users_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_phone ON public.users USING btree (phone);


--
-- Name: idx_users_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_role ON public.users USING btree (role);


--
-- Name: ix_activity_logs_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_activity_logs_id ON public.activity_logs USING btree (id);


--
-- Name: ix_departments_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_departments_id ON public.departments USING btree (id);


--
-- Name: ix_doctors_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_doctors_id ON public.doctors USING btree (id);


--
-- Name: ix_hospital_sequences_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hospital_sequences_id ON public.hospital_sequences USING btree (id);


--
-- Name: ix_hospitals_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hospitals_id ON public.hospitals USING btree (id);


--
-- Name: ix_idempotency_records_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_idempotency_records_id ON public.idempotency_records USING btree (id);


--
-- Name: ix_medical_records_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_medical_records_id ON public.medical_records USING btree (id);


--
-- Name: ix_payments_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_payments_id ON public.payments USING btree (id);


--
-- Name: ix_pharmacy_medicines_hospital_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pharmacy_medicines_hospital_updated ON public.pharmacy_medicines USING btree (hospital_id, updated_at);


--
-- Name: ix_pharmacy_medicines_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pharmacy_medicines_id ON public.pharmacy_medicines USING btree (id);


--
-- Name: ix_pharmacy_medicines_is_deleted; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pharmacy_medicines_is_deleted ON public.pharmacy_medicines USING btree (is_deleted);


--
-- Name: ix_pharmacy_medicines_quantity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pharmacy_medicines_quantity ON public.pharmacy_medicines USING btree (quantity);


--
-- Name: ix_pharmacy_sales_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pharmacy_sales_id ON public.pharmacy_sales USING btree (id);


--
-- Name: ix_queues_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_queues_id ON public.queues USING btree (id);


--
-- Name: ix_quick_actions_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quick_actions_id ON public.quick_actions USING btree (id);


--
-- Name: ix_refunds_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_refunds_id ON public.refunds USING btree (id);


--
-- Name: ix_support_tickets_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_support_tickets_id ON public.support_tickets USING btree (id);


--
-- Name: ix_tokens_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tokens_id ON public.tokens USING btree (id);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_wallets_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallets_id ON public.wallets USING btree (id);


--
-- Name: activity_logs activity_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: departments departments_hospital_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_hospital_id_fkey FOREIGN KEY (hospital_id) REFERENCES public.hospitals(id);


--
-- Name: doctors doctors_hospital_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doctors
    ADD CONSTRAINT doctors_hospital_id_fkey FOREIGN KEY (hospital_id) REFERENCES public.hospitals(id);


--
-- Name: doctors fk_doctors_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.doctors
    ADD CONSTRAINT fk_doctors_user FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: pharmacy_medicines fk_pharmacy_hospital; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pharmacy_medicines
    ADD CONSTRAINT fk_pharmacy_hospital FOREIGN KEY (hospital_id) REFERENCES public.hospitals(id) ON DELETE SET NULL;


--
-- Name: users fk_users_hospital; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_hospital FOREIGN KEY (hospital_id) REFERENCES public.hospitals(id);


--
-- Name: hospital_sequences hospital_sequences_hospital_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospital_sequences
    ADD CONSTRAINT hospital_sequences_hospital_id_fkey FOREIGN KEY (hospital_id) REFERENCES public.hospitals(id);


--
-- Name: medical_records medical_records_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_records
    ADD CONSTRAINT medical_records_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: payments payments_token_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_token_id_fkey FOREIGN KEY (token_id) REFERENCES public.tokens(id);


--
-- Name: pharmacy_sales pharmacy_sales_doctor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pharmacy_sales
    ADD CONSTRAINT pharmacy_sales_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(id);


--
-- Name: pharmacy_sales pharmacy_sales_hospital_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pharmacy_sales
    ADD CONSTRAINT pharmacy_sales_hospital_id_fkey FOREIGN KEY (hospital_id) REFERENCES public.hospitals(id);


--
-- Name: pharmacy_sales pharmacy_sales_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pharmacy_sales
    ADD CONSTRAINT pharmacy_sales_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.users(id);


--
-- Name: pharmacy_sales pharmacy_sales_performed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pharmacy_sales
    ADD CONSTRAINT pharmacy_sales_performed_by_fkey FOREIGN KEY (performed_by) REFERENCES public.users(id);


--
-- Name: queues queues_doctor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.queues
    ADD CONSTRAINT queues_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(id);


--
-- Name: quick_actions quick_actions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quick_actions
    ADD CONSTRAINT quick_actions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: refunds refunds_token_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_token_id_fkey FOREIGN KEY (token_id) REFERENCES public.tokens(id);


--
-- Name: refunds refunds_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: support_tickets support_tickets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_tickets
    ADD CONSTRAINT support_tickets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: tokens tokens_doctor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tokens
    ADD CONSTRAINT tokens_doctor_id_fkey FOREIGN KEY (doctor_id) REFERENCES public.doctors(id);


--
-- Name: tokens tokens_hospital_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tokens
    ADD CONSTRAINT tokens_hospital_id_fkey FOREIGN KEY (hospital_id) REFERENCES public.hospitals(id);


--
-- Name: tokens tokens_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tokens
    ADD CONSTRAINT tokens_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.users(id);


--
-- Name: wallets wallets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT wallets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict hXFQveeAvlZaNnI6ktI2LsPc9GsrKgoBlAnRCQXHqHbZNRJ2iLHmaF6aR9Dz18s

