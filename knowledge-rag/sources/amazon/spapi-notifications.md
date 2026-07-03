---
title: SP-API Notifications API — push events (no polling)
source_type: amazon_sp_api
source_url: https://developer-docs.amazon.com/sp-api/docs/notifications-api.md
category: APIs and data
collected: 2026-06-23
---

# Notifications API (SP-API)

Subscribe to **push notifications** for events relevant to your business instead of constantly
polling. Create a destination, subscribe to a notification type, and Amazon sends events as they
happen. Delivery is via **Amazon EventBridge** or **Amazon SQS**; subscriptions can be **filtered**
with CEL expressions so you only get the events you care about. Some operations are **grantless**
(no special role); subscribing requires the role tied to that notification type. v1, sellers + vendors.

> Best practice: keep a backup retrieval path in case a notification is delayed or missed.

**Why it matters:** this is how the scout/control center would react in real time — e.g. get pinged
on an offer/price change, a new order, or an account-health/listing event, instead of re-scanning on
a timer. It's the event backbone for turning the dashboard from "read-only snapshot" into "live."
