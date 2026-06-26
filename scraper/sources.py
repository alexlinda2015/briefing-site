"""Source definitions for the Auckland industrial rental dashboard.

Each source is a commercial agency search-results page filtered to Auckland
industrial / warehouse property *for lease*. The scraper visits every URL with a
real headless browser, so JavaScript-rendered single-page apps are supported.

`detail_substrings` are URL fragments that identify a link to an individual
property listing (used by the generic card extractor). `card_selectors` give the
extractor a hint for the repeating "listing card" container; the generic
fallback runs regardless, so imperfect selectors do not break a source.
"""

SOURCES = [
    {
        "name": "Bayleys",
        "url": "https://www.bayleys.co.nz/industrialworkplace/properties/auckland",
        "color": "#d8232a",
        "detail_substrings": ["/property/", "-2", "/commercial-property/"],
        "card_selectors": [
            "[class*='listing']", "[class*='property-card']", "article", ".card",
        ],
        "wait_until": "networkidle",
    },
    {
        "name": "Colliers",
        "url": (
            "https://www.colliers.co.nz/en-nz/properties#sort=relevancy"
            "&f:listingtype=[For%20Lease]&f:propertytype=[Industrial]"
            "&f:recenttransactions=[0]&f:location=Auckland"
        ),
        "color": "#0a2342",
        "detail_substrings": ["/en-nz/properties/", "/p-"],
        "card_selectors": [
            "[class*='coveo-result']", "[class*='property']", "[class*='listing']", "article",
        ],
        "wait_until": "networkidle",
    },
    {
        "name": "JLL",
        "url": "https://property.jll.nz/lease-warehouse/auckland",
        "color": "#e30613",
        "detail_substrings": ["/lease-", "/property/", "/listing"],
        "card_selectors": [
            "[class*='property-card']", "[class*='listing']", "[class*='result']", "article",
        ],
        "wait_until": "networkidle",
    },
    {
        "name": "CBRE",
        "url": (
            "https://www.cbre.co.nz/properties/portfolios/industrial-logistics-leasing/"
            "industrial-and-logistics-property-for-lease-auckland"
        ),
        "color": "#003f2d",
        "detail_substrings": ["/properties/", "/property/", "-for-lease"],
        "card_selectors": [
            "[class*='property-card']", "[class*='listing']", "[class*='card']", "article",
        ],
        "wait_until": "networkidle",
    },
    {
        "name": "James Kirkpatrick",
        "url": "https://jkgl.co.nz/auckland-property-vacancies-and-rentals/warehouses",
        "color": "#1b3a5b",
        "detail_substrings": ["/property", "/listing", "/vacanc", "/warehouse"],
        "card_selectors": [
            "[class*='property']", "[class*='listing']", "[class*='vacanc']",
            "tr", "article", ".card",
        ],
        "wait_until": "networkidle",
    },
    {
        "name": "Commercial Realty",
        "url": (
            "https://commercialrealty.co.nz/properties/?type=lease"
            "&property_type=industrial&district=Manukau%2BCity"
        ),
        "color": "#b8860b",
        "detail_substrings": ["/property/", "/properties/"],
        "card_selectors": [
            "[class*='property']", "[class*='listing']", "[class*='card']", "article",
        ],
        "wait_until": "networkidle",
    },
]
