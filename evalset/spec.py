"""The eval set: 18 fake emails and their hand-written expected output.

Each email lists what the supplier "sends" (body + attachments) and what a buyer would
expect to see extracted. A label value may be a list of acceptable answers, for fields
where more than one reading is fair (e.g. a model number that could be read as the SKU
or left blank). `notes` labels are scored separately and loosely (see evaluate.py).

build.py turns this file into .eml files and labels/*.json.
"""

from __future__ import annotations

import random

# ---------------------------------------------------------------- helpers

def items(header: dict, rows: list[dict]) -> list[dict]:
    """Applies header-level terms to every row (rows can override)."""
    return [{**header, **r} for r in rows]


NULL_ITEM = dict(brand=None, sku=None, condition=None, quantity_available=None, quantity_unit=None,
                 unit_price=None, currency=None, price_basis=None, ship_from=None, valid_until=None, notes=None)


# ---------------------------------------------------------------- 01 digital PDF price list

NORTHWIND_ROWS = [
    # sku, brand, description, qty, price, moq
    ("EM-2210", "ErgoMax", "Office chair, mesh back", 120, 84.50, 20),
    ("EM-3100", "ErgoMax", "Executive chair, leather", 45, 189.00, 5),
    ("DS-1460", "DeskLine", "Standing desk, 60in, electric", 60, 312.00, 10),
    ("DS-1200", "DeskLine", "Desk, 48in, laminate", 200, 96.75, 25),
    ("FC-0402", "SteelCo", "Filing cabinet, 4 drawer", 80, 142.00, 10),
    ("BK-0505", "SteelCo", "Bookcase, 5 shelf", 150, 68.40, None),
    ("CT-8810", "ConferPro", "Conference table, 8ft", 12, 545.00, 2),
    ("GC-0100", "ErgoMax", "Guest chair, stackable", 300, 39.90, 50),
]

E01 = dict(
    id="01_northwind_pdf",
    kind="digital PDF price list",
    from_=("Northwind Supply Co.", "sales@northwind.example"),
    date="2026-11-02T09:14:00-06:00",
    subject="November price list - Northwind Supply",
    body=("Hello,\n\nPlease find attached our November price list for office furniture.\n"
          "Let me know if you would like to reserve stock.\n\nBest regards,\nJenna Park\n"
          "Northwind Supply Co.\nsales@northwind.example | +1 312 555 0148"),
    attachments=[dict(type="pdf_table", filename="Northwind_Pricelist_Nov2026.pdf",
                      title="Northwind Supply Co. - Price List, November 2026",
                      subtitle="Prices in USD per unit, FOB Chicago. Valid until November 20, 2026.",
                      columns=["SKU", "Brand", "Description", "Condition", "Qty", "Price (USD)", "MOQ"],
                      rows=[[s, b, d, "New", q, f"{p:.2f}", m or "-"] for s, b, d, q, p, m in NORTHWIND_ROWS])],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name="Northwind Supply Co.", category="Furniture", condition="New",
             quantity_unit="units", currency="USD", price_basis="per unit", ship_from="FOB Chicago",
             valid_until="2026-11-20", source_attachment="Northwind_Pricelist_Nov2026.pdf"),
        [dict(sku=s, brand=b, product_name=d, quantity_available=q, unit_price=p,
              notes=f"MOQ {m} units" if m else None) for s, b, d, q, p, m in NORTHWIND_ROWS],
    ),
)

# ---------------------------------------------------------------- 02 phone photo of a printed sheet

HARBOR_ROWS = [
    ("Visionex", "VX-55U4K", "55in 4K UHD TV", 80, 289.00),
    ("Visionex", "VX-65U4K", "65in 4K UHD TV", 40, 419.00),
    ("SonicWave", "SW-BAR200", "Soundbar 2.1ch", 150, 74.50),
    ("SonicWave", "SW-EB10", "Wireless earbuds", 600, 18.25),
    ("ChargeIt", "CI-PB20K", "Power bank 20000mAh", 900, 11.80),
    ("ChargeIt", "CI-W15", "Wireless charger 15W", 1200, 6.40),
]

E02 = dict(
    id="02_harbor_photo",
    kind="phone photo of a printed price sheet",
    from_=("Mike Tran", "mike.tran@harborelectronics.example"),
    date="2026-11-03T16:41:00-08:00",
    subject="pic of the stock sheet from today",
    body="Hey, here's the sheet I showed you at the booth. Let me know what you want held.\n\nMike\n\nSent from my iPhone",
    attachments=[dict(type="photo_table", filename="IMG_4471.jpg",
                      title="HARBOR ELECTRONICS LTD - STOCK OFFER",
                      subtitle="All brand new, factory sealed. Prices USD per unit, EXW Long Beach CA. Valid to 30 Nov 2026.",
                      columns=["Brand", "Model", "Description", "Qty avail", "Price ea"],
                      rows=[[b, m, d, q, f"${p:.2f}"] for b, m, d, q, p in HARBOR_ROWS])],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name=["Harbor Electronics Ltd", "Harbor Electronics"], category="Electronics",
             condition="New", quantity_unit="units", currency="USD", price_basis="per unit",
             ship_from=["EXW Long Beach CA", "EXW Long Beach, CA"], valid_until="2026-11-30",
             source_attachment="IMG_4471.jpg"),
        [dict(brand=b, sku=m, product_name=d, quantity_available=q, unit_price=p) for b, m, d, q, p in HARBOR_ROWS],
    ),
)

# ---------------------------------------------------------------- 03 spreadsheet attachment

PACIFIC_ROWS = [
    ("PB-1001", "Sparkling water 330ml", "AquaPura", "24 x 330ml", 1500, 6.90),
    ("PB-1002", "Still water 500ml", "AquaPura", "24 x 500ml", 1800, 5.40),
    ("PB-1101", "Cola 330ml can", "FizzCo", "24 x 330ml", 900, 9.80),
    ("PB-1102", "Cola Zero 330ml can", "FizzCo", "24 x 330ml", 700, 9.80),
    ("PB-1201", "Orange juice 1L", "Sunvale", "12 x 1L", 400, 14.20),
    ("PB-1202", "Apple juice 1L", "Sunvale", "12 x 1L", 350, 13.60),
    ("PB-1301", "Iced tea lemon 500ml", "TeaTime", "24 x 500ml", 600, 11.30),
    ("PB-1302", "Iced tea peach 500ml", "TeaTime", "24 x 500ml", 550, 11.30),
    ("PB-1401", "Energy drink 250ml", "VoltX", "24 x 250ml", 1000, 15.90),
    ("PB-1402", "Energy drink sugar-free 250ml", "VoltX", "24 x 250ml", 800, 15.90),
]

E03 = dict(
    id="03_pacific_xlsx",
    kind="spreadsheet attachment",
    from_=("Pacific Beverage GmbH", "export@pacific-beverage.example"),
    date="2026-11-04T08:02:00+01:00",
    subject="Weekly stock offer KW45",
    body=("Dear partners,\n\nattached our weekly stock offer. All goods available from our warehouse.\n\n"
          "Kind regards\nLukas Weber\nExport Sales\nPacific Beverage GmbH, Hamburg"),
    attachments=[dict(type="xlsx", filename="Stock_offer_KW45.xlsx",
                      preamble=["Pacific Beverage GmbH - Weekly stock offer",
                                "Terms: EXW Hamburg, prices in EUR per case, valid until 27.11.2026", ""],
                      columns=["Item no", "Product", "Brand", "Pack", "Cases available", "Price per case (EUR)"],
                      rows=[list(r) for r in PACIFIC_ROWS])],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name="Pacific Beverage GmbH", category="Food & Beverage", quantity_unit="cases",
             currency="EUR", ship_from="EXW Hamburg", valid_until="2026-11-27",
             source_attachment="Stock_offer_KW45.xlsx"),
        [dict(sku=s, product_name=n, brand=b, quantity_available=q, unit_price=p,
              price_basis=[f"per case of {pack.split(' x ')[0]}", "per case", f"per case ({pack})"])
         for s, n, b, pack, q, p in PACIFIC_ROWS],
    ),
)

# ---------------------------------------------------------------- 04 short offer in the body (relative date)

E04 = dict(
    id="04_greenleaf_body",
    kind="offer written in the email body",
    from_=("Maria Lopez", "maria@greenleafproduce.example"),
    date="2026-11-09T07:30:00-08:00",  # a Monday, so "through Friday" = 2026-11-13
    subject="Good volume this week - romaine, spinach, broccoli",
    body=("Hi team,\n\nGood volume this week out of Salinas:\n\n"
          "- Romaine hearts, 3-pack - 2,400 kg available - $2.15/kg\n"
          "- Baby spinach (bulk) - 900 kg - $4.80/kg\n"
          "- Broccoli crowns - 1,500 kg - $1.95/kg\n\n"
          "All FOB Salinas, CA. Prices good through Friday. Mixed loads OK, min 500 kg per item.\n\n"
          "Maria Lopez\nGreenleaf Produce Co."),
    attachments=[],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name="Greenleaf Produce Co.", category="Fresh Produce", quantity_unit="kg",
             currency="USD", price_basis="per kg", ship_from=["FOB Salinas, CA", "FOB Salinas CA"],
             valid_until="2026-11-13", notes="min 500 kg per item", source_attachment=None),
        [dict(product_name="Romaine hearts, 3-pack", quantity_available=2400, unit_price=2.15),
         dict(product_name="Baby spinach (bulk)", quantity_available=900, unit_price=4.80),
         dict(product_name="Broccoli crowns", quantity_available=1500, unit_price=1.95)],
    ),
)

# ---------------------------------------------------------------- 05 one email with many items (2-page PDF)

def _atlas_rows() -> list[tuple]:
    rnd = random.Random(5)
    tools = [
        ("Claw hammer", ["16oz", "20oz"]), ("Screwdriver set", ["6pc", "12pc"]),
        ("Adjustable wrench", ["8in", "10in", "12in"]), ("Combination wrench set", ["SAE 10pc", "Metric 10pc"]),
        ("Socket set", ["1/4in drive 40pc", "3/8in drive 52pc"]), ("Cordless drill 18V", ["kit", "bare tool"]),
        ("Impact driver 18V", ["kit", "bare tool"]), ("Tape measure", ["16ft", "25ft", "35ft"]),
        ("Utility knife", ["retractable", "folding"]), ("Locking pliers", ["7in", "10in"]),
        ("Hex key set", ["SAE", "Metric"]), ("Level", ["24in", "48in"]), ("Hacksaw", ["12in"]),
        ("Work gloves", ["M", "L", "XL"]), ("Safety glasses", ["clear", "tinted"]),
        ("Extension cord", ["25ft", "50ft"]), ("Shop vacuum", ["5 gal", "12 gal"]),
    ]
    brands = ["Atlas Pro", "TorqueMax", "Ridgeway"]
    rows, n = [], 0
    for name, sizes in tools:
        for size in sizes:
            n += 1
            if n > 45:
                break
            price = round(rnd.uniform(3, 140), 2)
            qty = rnd.choice([48, 60, 96, 120, 144, 200, 240, 300, 480, 600])
            rows.append((f"AT-{1000 + n * 7}", rnd.choice(brands), f"{name}, {size}", qty, price))
    return rows[:45]


ATLAS_ROWS = _atlas_rows()

E05 = dict(
    id="05_atlas_many_items",
    kind="one email with many items (36 rows, PDF)",
    from_=("Atlas Industrial Tools", "offers@atlas-industrial.example"),
    date="2026-11-05T11:20:00-05:00",
    subject="Atlas Q4 hand & power tool availability (36 SKUs)",
    body=("Good morning,\n\nAttached is our full Q4 availability list. All items new in original packaging.\n"
          "Quantities subject to prior sale.\n\nRegards,\nTom Becker\nAtlas Industrial Tools, Cleveland OH"),
    attachments=[dict(type="pdf_table", filename="Atlas_Q4_Availability.pdf",
                      title="Atlas Industrial Tools - Q4 2026 Availability",
                      subtitle="Prices USD per unit, FOB Cleveland, OH. All items new. Quantities subject to prior sale.",
                      columns=["SKU", "Brand", "Item", "Qty", "Unit price"],
                      rows=[[s, b, d, q, f"${p:,.2f}"] for s, b, d, q, p in ATLAS_ROWS])],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name="Atlas Industrial Tools", category="Tools & Hardware", condition="New",
             quantity_unit="units", currency="USD", price_basis="per unit",
             ship_from=["FOB Cleveland, OH", "FOB Cleveland OH"], source_attachment="Atlas_Q4_Availability.pdf"),
        [dict(sku=s, brand=b, product_name=d, quantity_available=q, unit_price=p) for s, b, d, q, p in ATLAS_ROWS],
    ),
)

# ---------------------------------------------------------------- 06 HTML table in the body

SUMMIT_ROWS = [
    ("SA-T100", "Men's crew neck tee, cotton", "S-XL", 2400, 3.10),
    ("SA-T200", "Women's v-neck tee", "XS-L", 1800, 3.25),
    ("SA-H300", "Pullover hoodie, fleece", "S-XXL", 950, 11.75),
    ("SA-J400", "Denim jacket", "M-XL", 300, 18.90),
    ("SA-P500", "Jogger pants", "S-XL", 1200, 7.40),
]

E06 = dict(
    id="06_summit_html_table",
    kind="HTML table in the email body",
    from_=("Summit Apparel Group", "deals@summitapparel.example"),
    date="2026-11-05T14:05:00-06:00",
    subject="Overstock apparel - cancelled order, priced to move",
    html=True,
    body_intro=("Hi,<br><br>We have overstock from a cancelled retail order. Brand new with tags. "
                "FOB Dallas, TX. Offer valid until Nov 25.<br><br>"),
    columns=["Style", "Description", "Sizes", "Qty (pcs)", "Price"],
    rows=[[s, d, z, f"{q:,}", f"${p:.2f}"] for s, d, z, q, p in SUMMIT_ROWS],
    body_outro="<br>Thanks,<br>Rachel Kim<br>Summit Apparel Group",
    attachments=[],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name="Summit Apparel Group", category="Apparel", condition="New",
             quantity_unit=["units", "pcs"], currency="USD", price_basis=["per unit", "per piece"],
             ship_from=["FOB Dallas, TX", "FOB Dallas TX"], valid_until="2026-11-25", source_attachment=None),
        [dict(sku=s, product_name=d, quantity_available=q, unit_price=p, notes=f"Sizes {z}")
         for s, d, z, q, p in SUMMIT_ROWS],
    ),
)

# ---------------------------------------------------------------- 07 refurbished laptops, GBP, body text

E07 = dict(
    id="07_brightline_refurb_gbp",
    kind="offer in body, refurbished goods, GBP",
    from_=("Sam Okafor", "sam@brightline-itr.example"),
    date="2026-11-06T10:12:00+00:00",
    subject="Refurb laptop stock - Grade A",
    body=("Morning,\n\nFresh Grade A refurbished stock available now:\n\n"
          "* Dell Latitude 5420, i5-1145G7, 16GB/256GB - 120 units - GBP 215 each\n"
          "* Lenovo ThinkPad T14 Gen 2, i5, 16GB/512GB - 85 units - GBP 239 each\n"
          "* HP EliteBook 840 G8, i7, 16GB/512GB - 60 units - GBP 289 each\n"
          "* Apple MacBook Air M1 8GB/256GB - 40 units - GBP 395 each\n\n"
          "All with 12-month warranty, UK keyboard. Ex works Manchester. Lead time 3 working days.\n\n"
          "Sam Okafor\nBrightline IT Remarketing Ltd"),
    attachments=[],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name=["Brightline IT Remarketing Ltd", "Brightline IT Remarketing"],
             category="Computers", condition="Refurbished", quantity_unit="units", currency="GBP",
             price_basis="per unit", ship_from=["Ex works Manchester", "EXW Manchester"],
             notes="12-month warranty; lead time 3 working days", source_attachment=None),
        [dict(brand="Dell", sku=["Latitude 5420", None], product_name="Dell Latitude 5420, i5-1145G7, 16GB/256GB",
              quantity_available=120, unit_price=215),
         dict(brand="Lenovo", sku=["ThinkPad T14 Gen 2", None], product_name="Lenovo ThinkPad T14 Gen 2, i5, 16GB/512GB",
              quantity_available=85, unit_price=239),
         dict(brand="HP", sku=["EliteBook 840 G8", None], product_name="HP EliteBook 840 G8, i7, 16GB/512GB",
              quantity_available=60, unit_price=289),
         dict(brand="Apple", sku=["MacBook Air M1", None], product_name="Apple MacBook Air M1 8GB/256GB",
              quantity_available=40, unit_price=395)],
    ),
)

# ---------------------------------------------------------------- 08 forwarded closeout, priced per pallet

E08 = dict(
    id="08_keystone_fwd_closeout",
    kind="forwarded email, single closeout item priced per pallet",
    from_=("Dan Reeves", "dan@keystonepaper.example"),
    date="2026-11-06T13:48:00-05:00",
    subject="Fwd: Closeout - copy paper, 22 pallets",
    body=("FYI - see below, this one will go fast.\n\nDan\n\n"
          "---------- Forwarded message ---------\n"
          "From: Lisa Grant <lisa@keystonepaper.example>\nDate: Fri, Nov 6, 2026 at 11:02 AM\n"
          "Subject: Closeout - copy paper, 22 pallets\n\n"
          "We have a closeout on Keystone letter size copy paper, 20lb, 92 bright.\n"
          "22 pallets available (40 cases per pallet, 10 reams per case).\n"
          "$1,850 per pallet, FOB Allentown, PA. Must move by 11/16.\n\n"
          "Lisa Grant\nKeystone Paper Mills"),
    attachments=[],
    is_offer=True,
    items=[dict(NULL_ITEM, supplier_name="Keystone Paper Mills", brand="Keystone",
                product_name="Letter size copy paper, 20lb, 92 bright", category="Office Supplies",
                quantity_available=22, quantity_unit="pallets", unit_price=1850, currency="USD",
                price_basis="per pallet", ship_from=["FOB Allentown, PA", "FOB Allentown PA"],
                valid_until="2026-11-16", notes="40 cases per pallet, 10 reams per case", source_attachment=None)],
)

# ---------------------------------------------------------------- 09 body offer + CSV attachment

LUMEN_CSV = [
    ("HG-1101", "Ceramic dinner plate 10in", "Lumen", 5000, "units", 1.85),
    ("HG-1102", "Stoneware mug 12oz", "Lumen", 3600, "units", 1.40),
    ("HG-2201", "Microfiber towel 6-pack", "CleanPro", 1200, "packs", 4.95),
    ("HG-2202", "Cotton bath towel", "CleanPro", 2000, "units", 3.60),
    ("HG-4401", "Glass storage container set 10pc", "FreshKeep", 800, "sets", 8.75),
]

E09 = dict(
    id="09_lumen_body_plus_csv",
    kind="items split between body and CSV attachment",
    from_=("Lumen Home Goods", "trade@lumenhome.example"),
    date="2026-11-07T09:00:00-05:00",
    subject="This week's special + availability",
    body=("Hi there,\n\nThis week's special: Bamboo cutting board set (3pc), item HG-3301, 1,000 sets at $7.25/set.\n\n"
          "Our regular availability list is attached (CSV). Everything ships FOB Newark, NJ.\n\n"
          "Cheers,\nPriya Shah\nLumen Home Goods"),
    attachments=[dict(type="csv", filename="lumen_availability.csv",
                      columns=["SKU", "Product", "Brand", "Qty", "Unit", "Price USD"],
                      rows=[list(r) for r in LUMEN_CSV])],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name="Lumen Home Goods", category="Household", currency="USD",
             ship_from=["FOB Newark, NJ", "FOB Newark NJ"]),
        [dict(sku="HG-3301", product_name="Bamboo cutting board set (3pc)", quantity_available=1000,
              quantity_unit="sets", unit_price=7.25, price_basis="per set", source_attachment=None)]
        + [dict(sku=s, product_name=n, brand=b, quantity_available=q, quantity_unit=u, unit_price=p,
                price_basis=["per unit", f"per {u[:-1]}", "per set" if u == "sets" else "per unit"],
                source_attachment="lumen_availability.csv") for s, n, b, q, u, p in LUMEN_CSV],
    ),
)

# ---------------------------------------------------------------- 10 scanned price list (grayscale, noisy)

CRESCENT_ROWS = [
    ("CH-201", "Silkara", "Shampoo 400ml", 7200, 2.10),
    ("CH-202", "Silkara", "Conditioner 400ml", 6000, 2.15),
    ("CH-310", "PureDerm", "Body lotion 250ml", 4800, 1.75),
    ("CH-311", "PureDerm", "Hand cream 75ml", 9600, 0.95),
    ("CH-420", "BrightSmile", "Toothpaste 100ml", 12000, 0.68),
    ("CH-505", "FreshAir", "Deodorant spray 150ml", 5400, 1.20),
    ("CH-610", "Glowa", "Sheet face mask 10-pack", 2000, 3.40),
]

E10 = dict(
    id="10_crescent_scan",
    kind="scanned price list (grayscale, skewed, noisy)",
    from_=("Crescent Health & Beauty", "orders@crescenthb.example"),
    date="2026-11-07T15:22:00-05:00",
    subject="Scan: December price list",
    body="Please see scanned price list attached.\n\nCrescent Health & Beauty\nEdison, NJ",
    attachments=[dict(type="scan_table", filename="scan_20261107_1522.png",
                      title="CRESCENT HEALTH & BEAUTY - PRICE LIST",
                      subtitle="Prices USD per unit. Ship from Edison, NJ. Valid until 05 Dec 2026. MOQ 1 case per SKU (12 units).",
                      columns=["Item code", "Brand", "Product", "Qty (units)", "Price/unit"],
                      rows=[[c, b, p, f"{q:,}", f"{pr:.2f}"] for c, b, p, q, pr in CRESCENT_ROWS])],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name="Crescent Health & Beauty", category="Health & Beauty", quantity_unit="units",
             currency="USD", price_basis="per unit", ship_from=["Edison, NJ", "Ship from Edison, NJ"],
             valid_until="2026-12-05", notes="MOQ 1 case per SKU (12 units)",
             source_attachment="scan_20261107_1522.png"),
        [dict(sku=c, brand=b, product_name=p, quantity_available=q, unit_price=pr) for c, b, p, q, pr in CRESCENT_ROWS],
    ),
)

# ---------------------------------------------------------------- 11 EU food offer, per case, one sold-out line

E11 = dict(
    id="11_vandijk_cases_soldout",
    kind="body offer in EUR per case, with a sold-out line to skip",
    from_=("Van Dijk Foods B.V.", "verkoop@vandijkfoods.example"),
    date="2026-11-08T09:40:00+01:00",
    subject="Offer from stock - Dutch foods",
    body=("Dear buyer,\n\nWe can offer from stock, EXW Rotterdam:\n\n"
          "1. Gouda cheese 48+, 500g wedges - brand Hollandse Trots - 800 cases - EUR 38.40 per case of 12\n"
          "2. Stroopwafels 8-pack - brand Oma's Bakkerij - 1,200 cases - EUR 21.60 per case of 12\n"
          "3. Speculaas cookies 400g - SOLD OUT\n"
          "4. Chocolate sprinkles (hagelslag) 400g - brand Zoet & Co - 650 cases - EUR 19.80 per case of 12\n\n"
          "Offer valid until 20 November 2026. Payment 30 days.\n\nMet vriendelijke groet,\nPieter van Dijk\nVan Dijk Foods B.V."),
    attachments=[],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name="Van Dijk Foods B.V.", category="Food & Beverage", quantity_unit="cases",
             currency="EUR", price_basis="per case of 12", ship_from="EXW Rotterdam", valid_until="2026-11-20",
             notes="Payment 30 days", source_attachment=None),
        [dict(product_name="Gouda cheese 48+, 500g wedges", brand="Hollandse Trots", quantity_available=800, unit_price=38.40),
         dict(product_name="Stroopwafels 8-pack", brand="Oma's Bakkerij", quantity_available=1200, unit_price=21.60),
         dict(product_name="Chocolate sprinkles (hagelslag) 400g", brand="Zoet & Co", quantity_available=650, unit_price=19.80)],
    ),
)

# ---------------------------------------------------------------- 12 Spanish, European number format

E12 = dict(
    id="12_andina_spanish",
    kind="Spanish-language body offer, European number format",
    from_=("Distribuidora Andina S.A.", "ventas@distandina.example"),
    date="2026-11-08T12:15:00-05:00",
    subject="Oferta especial - abarrotes",
    body=("Estimado cliente,\n\nLe ofrecemos los siguientes productos:\n\n"
          "- Café molido premium 500g, marca Montaña Alta - 2.000 unidades - USD 4,20 c/u\n"
          "- Aceite de oliva extra virgen 1L, marca Olivar del Sur - 1.500 unidades - USD 6,85 c/u\n"
          "- Arroz largo fino 5kg, marca La Cosecha - 900 bolsas - USD 5,10 por bolsa\n\n"
          "Precios FOB Miami. Oferta válida hasta el 30 de noviembre de 2026.\n\n"
          "Saludos,\nCarlos Ruiz\nDistribuidora Andina S.A."),
    attachments=[],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name="Distribuidora Andina S.A.", category="Food & Beverage", currency="USD",
             ship_from="FOB Miami", valid_until="2026-11-30", source_attachment=None),
        [dict(product_name=["Café molido premium 500g", "Ground coffee premium 500g"], brand="Montaña Alta",
              quantity_available=2000, quantity_unit="units", unit_price=4.20, price_basis="per unit"),
         dict(product_name=["Aceite de oliva extra virgen 1L", "Extra virgin olive oil 1L"], brand="Olivar del Sur",
              quantity_available=1500, quantity_unit="units", unit_price=6.85, price_basis="per unit"),
         dict(product_name=["Arroz largo fino 5kg", "Long grain rice 5kg"], brand="La Cosecha",
              quantity_available=900, quantity_unit="bags", unit_price=5.10, price_basis="per bag")],
    ),
)

# ---------------------------------------------------------------- 13-18 not offers

E13 = dict(
    id="13_order_confirmation",
    kind="NOT offer: order confirmation with an item/price table",
    from_=("Northwind Supply Co.", "orders@northwind.example"),
    date="2026-11-03T10:00:00-06:00",
    subject="Order confirmation NW-55821",
    body=("Thank you for your order!\n\nOrder NW-55821 (PO 7741)\n\n"
          "Qty  SKU      Description               Unit     Total\n"
          "20   EM-2210  Office chair, mesh back   $84.50   $1,690.00\n"
          "10   DS-1460  Standing desk, 60in       $312.00  $3,120.00\n\n"
          "Order total: $4,810.00. Estimated ship date: Nov 10, 2026.\n\nNorthwind Supply Co. - Order Desk"),
    attachments=[],
    is_offer=False,
    items=[],
)

E14 = dict(
    id="14_customer_rfq",
    kind="NOT offer: a request for quote sent to us",
    from_=("Alex Moreno", "purchasing@brightmart-retail.example"),
    date="2026-11-04T13:30:00-05:00",
    subject="RFQ: 500 office chairs + 200 standing desks",
    body=("Hello,\n\nCould you quote your best price on the following for delivery to Columbus, OH by Dec 15?\n\n"
          "- 500 x office chair, mesh back\n- 200 x standing desk, electric, 60in\n\n"
          "Please include lead time and freight.\n\nThanks,\nAlex Moreno\nPurchasing, BrightMart Retail"),
    attachments=[],
    is_offer=False,
    items=[],
)

E15 = dict(
    id="15_newsletter",
    kind="NOT offer: industry newsletter mentioning prices",
    from_=("Supply Chain Weekly", "newsletter@scweekly.example"),
    date="2026-11-05T06:00:00-05:00",
    subject="Supply Chain Weekly: container rates fall 8%, resin prices climb",
    body=("SUPPLY CHAIN WEEKLY - November 5, 2026\n\n"
          "1. Trans-Pacific container spot rates fell 8% week over week to $2,140/FEU.\n"
          "2. PET resin prices rose 4% on feedstock costs; beverage packaging expected to follow.\n"
          "3. Webinar: Nearshoring in 2027 - register free for Nov 19.\n\n"
          "You are receiving this because you subscribed. Unsubscribe | Manage preferences"),
    attachments=[],
    is_offer=False,
    items=[],
)

E16 = dict(
    id="16_invoice_pdf",
    kind="NOT offer: invoice / payment reminder with a PDF",
    from_=("Pacific Beverage GmbH", "accounting@pacific-beverage.example"),
    date="2026-11-06T09:10:00+01:00",
    subject="Payment reminder - Invoice INV-2026-4471",
    body=("Dear customer,\n\nOur records show invoice INV-2026-4471 is due on 23.11.2026. "
          "Please find the invoice attached.\n\nAccounting\nPacific Beverage GmbH"),
    attachments=[dict(type="pdf_table", filename="INV-2026-4471.pdf",
                      title="INVOICE INV-2026-4471",
                      subtitle="Bill to: Your Company, Customer no. 20931. Due date 23.11.2026. Bank: DE89 3704 0044 0532 0130 00",
                      columns=["Item no", "Product", "Cases", "Price/case EUR", "Amount EUR"],
                      rows=[["PB-1001", "Sparkling water 330ml", 300, "6.90", "2,070.00"],
                            ["PB-1101", "Cola 330ml can", 150, "9.80", "1,470.00"],
                            ["", "Total", "", "", "3,540.00"]])],
    is_offer=False,
    items=[],
)

E17 = dict(
    id="17_shipping_notice",
    kind="NOT offer: shipping notification",
    from_=("Harbor Electronics Logistics", "shipping@harborelectronics.example"),
    date="2026-11-07T08:45:00-08:00",
    subject="Your order HE-90233 has shipped",
    body=("Your order HE-90233 has shipped.\n\nCarrier: XPO Freight\nPRO number: 418-2290-7731\n"
          "Pallets: 3\nEstimated delivery: Nov 12, 2026\n\nTrack your shipment in the customer portal."),
    attachments=[],
    is_offer=False,
    items=[],
)

E18 = dict(
    id="18_chatter",
    kind="NOT offer: general chatter from a supplier rep",
    from_=("Mike Tran", "mike.tran@harborelectronics.example"),
    date="2026-11-08T18:02:00-08:00",
    subject="lunch next week?",
    body=("Hey! Are you free for lunch next Thursday? I'll be in town for a couple of days. "
          "No agenda, just catching up.\n\nMike"),
    attachments=[],
    is_offer=False,
    items=[],
)

# ---------------------------------------------------------------- 19 offer only inside a PDF, vague body
# Targets the two-stage design: the cheap classifier never sees PDF contents.

ORBIT_ROWS = [
    ("OP-5501", "Copy paper A4 80gsm, 5-ream box", "Orbit", 640, 21.40),
    ("OP-5620", "Ballpoint pens, blue, box of 50", "Inkline", 300, 6.90),
    ("OP-5733", "Lever arch files, assorted, pack of 10", "Orbit", 220, 14.75),
    ("OP-5840", "Sticky notes 3x3in, 12-pad pack", "Notely", 900, 3.85),
    ("OP-5902", "Desk organiser, mesh, black", "Orbit", 150, 8.20),
]

E19 = dict(
    id="19_orbit_pdf_only",
    kind="offer only inside a PDF, body just says 'see attached'",
    from_=("Ken Adeyemi", "ken@orbit-office.example"),
    date="2026-11-09T10:05:00+00:00",
    subject="Documents",
    body="Hi,\n\nPlease see attached.\n\nRegards,\nKen",
    attachments=[dict(type="pdf_table", filename="doc_0412.pdf",
                      title="Orbit Office Products - Clearance Offer",
                      subtitle="Prices GBP per unit, ex works Leeds. Offer valid until 30 November 2026. All stock new.",
                      columns=["Code", "Description", "Brand", "Available", "Price GBP"],
                      rows=[[c, d, b, q, f"{p:.2f}"] for c, d, b, q, p in ORBIT_ROWS])],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name=["Orbit Office Products", "Orbit Office"], category="Office Supplies",
             condition="New", quantity_unit="units", currency="GBP", price_basis="per unit",
             ship_from=["Ex works Leeds", "EXW Leeds"], valid_until="2026-11-30", source_attachment="doc_0412.pdf"),
        [dict(sku=c, product_name=d, brand=b, quantity_available=q, unit_price=p) for c, d, b, q, p in ORBIT_ROWS],
    ),
)

# ---------------------------------------------------------------- 20 tiered prices, "call for price", no quantity
# Targets "leave it blank rather than guess".

E20 = dict(
    id="20_medline_tiers_blanks",
    kind="tiered pricing, a call-for-price item, an item with no quantity",
    from_=("Rita Gomez", "rita@safehand-medical.example"),
    date="2026-11-09T15:30:00-05:00",
    subject="PPE availability + pricing",
    body=("Hi,\n\nHere's what we can do on PPE this month:\n\n"
          "1) SafeHand nitrile exam gloves, size M, box of 100 (SKU SH-NG-M) - 400 cases available.\n"
          "   1-49 cases: $42.00/case, 50+ cases: $38.00/case. 10 boxes per case.\n"
          "2) SafeHand 3-ply disposable face masks, box of 50 (SKU SH-FM3) - 1,000 boxes - call for price.\n"
          "3) Hand sanitizer gel 500ml pump (SKU SH-HS500) - $2.35 each, plenty in stock.\n\n"
          "Ships from our Atlanta, GA warehouse.\n\nRita Gomez\nSafeHand Medical Supply"),
    attachments=[],
    is_offer=True,
    items=items(
        dict(NULL_ITEM, supplier_name="SafeHand Medical Supply", category="Health & Beauty", currency="USD",
             ship_from=["Atlanta, GA", "Atlanta, GA warehouse"], source_attachment=None),
        [dict(product_name="Nitrile exam gloves, size M, box of 100", brand="SafeHand", sku="SH-NG-M",
              quantity_available=400, quantity_unit="cases", unit_price=[42.00, 38.00], price_basis="per case",
              notes="50+ cases $38.00/case; 10 boxes per case"),
         dict(product_name="3-ply disposable face masks, box of 50", brand="SafeHand", sku="SH-FM3",
              quantity_available=1000, quantity_unit="boxes", unit_price=None, price_basis=None,
              currency=["USD", None],  # no price given, so a blank currency is also fair
              notes="call for price"),
         dict(product_name="Hand sanitizer gel 500ml pump", brand=["SafeHand", None], sku="SH-HS500",
              quantity_available=None, quantity_unit=None, unit_price=2.35, price_basis="per unit")],
    ),
)

EMAILS = [E01, E02, E03, E04, E05, E06, E07, E08, E09, E10, E11, E12, E13, E14, E15, E16, E17, E18, E19, E20]
