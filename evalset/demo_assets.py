"""Makes a fresh price list (not in the eval set) to attach to the live demo email.

    uv run python evalset/demo_assets.py   ->  demo/Riverside_Pricelist.pdf
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from build import pdf_table  # noqa: E402

ROWS = [
    ["RS-101", "KitchenPro", "Stainless steel saucepan 2L", "New", 240, "18.90"],
    ["RS-102", "KitchenPro", "Non-stick frying pan 28cm", "New", 360, "14.25"],
    ["RS-205", "BrewMate", "French press coffee maker 1L", "New", 150, "11.40"],
    ["RS-310", "ChefLine", "Knife block set, 6 pieces", "New", 90, "32.00"],
]

out = HERE.parent / "demo" / "Riverside_Pricelist.pdf"
out.parent.mkdir(exist_ok=True)
out.write_bytes(pdf_table(dict(
    title="Riverside Housewares - Price List",
    subtitle="Prices USD per unit, FOB Portland, OR. Valid until December 15, 2026. MOQ 24 units per SKU.",
    columns=["SKU", "Brand", "Description", "Condition", "Qty", "Price (USD)"],
    rows=ROWS,
)))
print(f"wrote {out}")
