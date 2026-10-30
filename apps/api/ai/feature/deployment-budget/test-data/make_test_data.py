"""Generate manual-test JSONs for the deployment token budget (ADR-0025).

Run from this folder:  python3 make_test_data.py
Deterministic (seeded), so regenerated files are identical.
"""

import json
import random
from pathlib import Path

OUT = Path(__file__).parent
rng = random.Random(25)


def write(name: str, doc: dict) -> None:
    path = OUT / name
    path.write_text(json.dumps(doc, indent=2))
    print(f"{name}: {path.stat().st_size // 1024} KB")


# 1. Small → full JSON inline, one call.
write(
    "1-small-flags.json",
    {
        "service": "web-app",
        "environment": "production",
        "flags": {
            "darkMode": {"enabled": False, "rollout": 10, "segments": ["beta"]},
            "newCheckout": {"enabled": True, "rollout": 50, "segments": []},
            "aiAssistant": {"enabled": False, "rollout": 0, "segments": ["staff"]},
        },
        "refreshIntervalSeconds": 300,
    },
)

# 2. Mid-size (~100 KB): old 120k-char cap inlined it (~40k tokens → 429 on
# Google free tier). Now: skeleton + lookup tools.
statuses = ["pending", "paid", "shipped", "delivered", "cancelled"]
write(
    "2-orders-mid.json",
    {
        "source": "shop-export",
        "orders": [
            {
                "id": f"ORD-{i:04d}",
                "customerId": f"C-{rng.randint(1, 60):03d}",
                "status": rng.choice(statuses),
                "total": round(rng.uniform(5, 900), 2),
                "currency": "EUR",
                "createdAt": f"2026-{1 + i % 9:02d}-{1 + i % 27:02d}T10:00:00Z",
                "shippingAddress": {
                    "city": rng.choice(["Berlin", "Paris", "Madrid", "Rome", "Oslo"]),
                    "zip": f"{rng.randint(10000, 99999)}",
                },
                "items": [
                    {"sku": f"SKU-{rng.randint(1, 400):04d}", "qty": rng.randint(1, 4)}
                    for _ in range(rng.randint(1, 3))
                ],
                "note": "Leave at the front desk if nobody answers. " * 2,
            }
            for i in range(300)
        ],
    },
)

# 3. Large (~700 KB), heterogeneous: "bundle" products only appear after
# index 1500, so a first-N sample would hide them — the key-union skeleton
# shows them. Multi-hop lookups need several tool rounds → budget waits.
products = []
for i in range(2000):
    base = {
        "id": f"P-{i:04d}",
        "name": f"Product {i}",
        "category": rng.choice(["audio", "video", "home", "garden", "toys"]),
        "price": round(rng.uniform(3, 500), 2),
        "description": "Durable, well reviewed and shipped in recyclable packaging. " * 2,
    }
    if i >= 1500 and i % 25 == 0:
        base |= {
            "$type": "bundle",
            "contains": [f"P-{rng.randint(0, 1499):04d}" for _ in range(3)],
            "discountPercent": 5,
        }
    else:
        base |= {"$type": "simple", "stock": rng.randint(0, 300)}
    products.append(base)
products[1525]["contains"][0] = "P-0042"  # the multi-hop target
write("3-catalog-large.json", {"store": "demo-store", "products": products})

# 4. Too large even as a skeleton: 250 tenants, each with its own keys (the
# skeleton must list every key). Small sections (/defaults, /billing,
# /tenants/t-001 …) still fit → "Edit one section" + trimmed copy.
tenants = {}
for t in range(1, 251):
    tid = f"t-{t:03d}"
    tenants[tid] = {
        f"{tid}_setting_{k:02d}": f"value {k} for {tid} — configured by the onboarding team"
        for k in range(30)
    }
    tenants[tid]["sso"] = {"enabled": False, "provider": "none"}
write(
    "4-tenants-too-large.json",
    {
        "defaults": {"sessionTimeoutMinutes": 60, "mfaRequired": False, "locale": "en"},
        "billing": {"plan": "enterprise", "currency": "EUR", "invoiceDay": 1},
        "tenants": tenants,
    },
)
