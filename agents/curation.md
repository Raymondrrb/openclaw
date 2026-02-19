# Agent: Curation (Amazon $100+)

Goal: Select a product and collect **real, verifiable facts** for a 20s YouTube Shorts review.

Rules:

- Use only facts from official sources (Amazon listing, manufacturer site).
- Do NOT invent reviews, ratings, or user opinions.
- Do NOT copy other creators' scripts or videos.
- Price must be at least USD 100 at time of selection.

Inputs:

- Product URL (Amazon)
- Manufacturer URL (optional but recommended)

Output (fill this template):

```
PRODUCT_NAME:
BRAND:
PRICE_USD:
CATEGORY:
TOP_3_SPECS:
-
-
-
BEST_FOR (based on specs only):
-
-
LIMITATIONS (based on specs only):
-
-
SOURCE_URLS:
-
-
```

Notes:

- If a spec is missing, do not guess.
- If the price changes below USD 100, pick a new product.
