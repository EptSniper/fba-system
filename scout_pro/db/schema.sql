-- ============================================================================
-- scout_pro — PostgreSQL reference schema
-- ============================================================================
-- database.py creates these tables automatically (SQLAlchemy) on Postgres OR
-- SQLite. This file is the canonical Postgres DDL for teams that provision the
-- warehouse directly. Optional: enable pgvector for title/image embeddings.
--
--   CREATE EXTENSION IF NOT EXISTS vector;   -- if you want embedding columns
-- ============================================================================

CREATE TABLE IF NOT EXISTS asin_snapshot_daily (
    asin                    TEXT        NOT NULL,
    marketplace             TEXT        NOT NULL,
    snapshot_date           DATE        NOT NULL,
    category_id             TEXT,
    brand                   TEXT,
    title                   TEXT,
    -- title_embedding      vector(384),         -- optional (pgvector)
    image_count             INT,
    bullet_count            INT,
    buy_box_price           NUMERIC(12,2),
    price_new_fba           NUMERIC(12,2),
    price_new_fbm           NUMERIC(12,2),
    price_amazon            NUMERIC(12,2),
    sales_rank              INT,
    offer_count_new         INT,
    offer_count_used        INT,
    rating                  NUMERIC(3,2),
    review_count            INT,
    weight_lb               NUMERIC(8,3),
    featured_offer_eligible BOOLEAN,
    est_sales               INT,
    raw                     JSONB,
    PRIMARY KEY (asin, marketplace, snapshot_date)
);
-- Event-heavy table: partition by month in production for cheap pruning.
CREATE TABLE IF NOT EXISTS asin_offer_event (
    id                BIGSERIAL PRIMARY KEY,
    asin              TEXT,
    seller_id         TEXT,
    event_time        TIMESTAMPTZ,
    is_fba            BOOLEAN,
    is_featured_offer BOOLEAN,
    offer_price       NUMERIC(12,2),
    shipping_price    NUMERIC(12,2),
    stock_proxy       INT,
    condition         TEXT
);
CREATE INDEX IF NOT EXISTS idx_offer_event_asin ON asin_offer_event(asin);

CREATE TABLE IF NOT EXISTS seller_storefront_daily (
    seller_id              TEXT NOT NULL,
    snapshot_date          DATE NOT NULL,
    storefront_asin_count  INT,
    top_asins              JSONB,
    portfolio_category_mix JSONB,
    estimated_buy_box_share NUMERIC(6,4),
    avg_price_band         TEXT,
    PRIMARY KEY (seller_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS ads_keyword_daily (
    id               BIGSERIAL PRIMARY KEY,
    asin             TEXT,
    campaign_id      TEXT,
    ad_group_id      TEXT,
    keyword          TEXT,
    date             DATE,
    impressions      INT,
    clicks           INT,
    ctr              NUMERIC(8,5),
    cpc              NUMERIC(12,2),
    spend            NUMERIC(12,2),
    attributed_sales NUMERIC(12,2),
    acos             NUMERIC(8,5),
    roas             NUMERIC(8,5)
);
CREATE INDEX IF NOT EXISTS idx_ads_keyword_asin ON ads_keyword_daily(asin);

CREATE TABLE IF NOT EXISTS inventory_daily (
    sku            TEXT NOT NULL,
    date           DATE NOT NULL,
    on_hand        INT,
    days_of_cover  NUMERIC(8,2),
    inbound_units  INT,
    stockout_flag  BOOLEAN,
    lead_time_days INT,
    reorder_point  INT,
    PRIMARY KEY (sku, date)
);

CREATE TABLE IF NOT EXISTS product_label_window (
    asin                TEXT NOT NULL,
    marketplace         TEXT NOT NULL,
    label_end_date      DATE NOT NULL,
    horizon_days        INT  NOT NULL,
    label_version       TEXT NOT NULL,
    success_proxy       BOOLEAN,       -- weak / public
    success_realized    BOOLEAN,       -- strong / owned-account
    proxy_score         NUMERIC(6,4),
    contribution_margin NUMERIC(12,2),
    units_sold          INT,
    return_rate         NUMERIC(6,4),
    compliance_flag     BOOLEAN,
    censored            BOOLEAN,        -- stockout-censored window
    features            JSONB,
    PRIMARY KEY (asin, marketplace, label_end_date, horizon_days, label_version)
);

CREATE TABLE IF NOT EXISTS picks (
    id      BIGSERIAL PRIMARY KEY,
    asin    TEXT,
    score   NUMERIC(6,2),
    proba   NUMERIC(6,4),
    payload JSONB,
    sent_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_picks_asin ON picks(asin);

CREATE TABLE IF NOT EXISTS review_queue (
    id          BIGSERIAL PRIMARY KEY,
    asin        TEXT,
    proba       NUMERIC(6,4),
    score       NUMERIC(6,2),
    reason      TEXT,
    status      TEXT DEFAULT 'pending',
    created_at  TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS research_feedback (
    id                BIGSERIAL PRIMARY KEY,
    asin              TEXT,
    analyst_id        TEXT,
    decision          TEXT,   -- approve|reject|defer|supplier_issue|compliance_issue|margin_issue|false_positive
    reason_code       TEXT,
    confidence        NUMERIC(6,4),
    supplier_rejected BOOLEAN,
    notes             TEXT,
    created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS youtube_match (
    id               BIGSERIAL PRIMARY KEY,
    topic_id         TEXT,
    video_id         TEXT,
    search_query     TEXT,
    semantic_score   NUMERIC(6,4),
    credibility_score NUMERIC(6,4),
    engagement_score NUMERIC(6,4),
    final_rank_score NUMERIC(6,4),
    matched_claims   JSONB
);

CREATE TABLE IF NOT EXISTS model_registry (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT,       -- classifier|regressor|ranker
    version     TEXT,
    kind        TEXT,
    path        TEXT,
    metrics     JSONB,
    is_champion BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT now()
);
