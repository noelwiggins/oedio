"""Planted usability defects for Web Lab test shops.

Each defect is a real, reproducible usability problem with a known location,
mapped to Jakob Nielsen's ten heuristics and the 0-4 severity scale:
0 none, 1 cosmetic, 2 minor, 3 major, 4 task-blocking catastrophe.

HOLDOUT_ONLY defect types never appear in training shops, so held-out shops
test whether an evolved audit strategy generalises to problems it was never
tuned on, not just to new combinations of familiar ones.

Decoys are deliberate design choices that are unusual but not usability
problems (an aesthetic preference at most). Reporting one is a false alarm.
"""

HEURISTICS = {
    1: "Visibility of system status",
    2: "Match between the system and the real world",
    3: "User control and freedom",
    4: "Consistency and standards",
    5: "Error prevention",
    6: "Recognition rather than recall",
    7: "Flexibility and efficiency of use",
    8: "Aesthetic and minimalist design",
    9: "Help users recognize, diagnose, and recover from errors",
    10: "Help and documentation",
}

# id: (title, heuristics, severity, page, symptom shown to the judge, area)
DEFECTS = {
    "D01": ("No feedback after adding to cart", [1], 3, "product",
            "Clicking 'Add to cart' gives no confirmation at all: no message, no change on the page.", "add"),
    "D02": ("Cart count does not update", [1], 2, "product",
            "The cart count in the header stays at its old number after adding an item until the page is reloaded.", "add"),
    "D03": ("Search typo returns nothing, no suggestion", [9, 5], 3, "search",
            "A search with a small typo (e.g. one wrong letter) returns 'No results' with no spelling suggestion or alternatives.", "typo_search"),
    "D04": ("Out-of-stock variant only revealed at checkout", [1, 5], 3, "product",
            "Sold-out sizes/colours can be selected and added with no warning; the problem only appears at checkout.", "variant"),
    "D05": ("No way to remove an item from the cart", [3], 3, "cart",
            "The cart has no remove/delete control; the only way is to set quantity to 0 and press Update.", "remove"),
    "D06": ("Inconsistent action labels", [4], 1, "product",
            "The same action is labelled differently across pages ('Add to bag', 'Buy', 'Add to basket').", "product"),
    "D07": ("Internal jargon in customer-facing labels", [2], 2, "product",
            "Labels use internal terms such as 'SKU variant matrix' and 'Fulfilment SLA' instead of plain words.", "product"),
    "D08": ("Form error with no message", [9], 3, "checkout",
            "An invalid postcode turns the field red but no message says what is wrong or how to fix it.", "checkout"),
    "D09": ("Shipping and returns information not findable", [10], 2, "cart",
            "No link to shipping or returns information anywhere in the navigation, footer, product page or cart.", "help"),
    "D10": ("Broken navigation link", [4, 9], 3, "home",
            "A main navigation category link leads to a 'Page not found' error.", "nav"),
    "D11": ("Surprise fee at checkout", [1, 2], 3, "checkout",
            "A 'service fee' appears for the first time at checkout; the cart total did not mention it.", "checkout"),
    "D12": ("Quantity accepts invalid values", [5], 2, "cart",
            "Quantity accepts negative numbers and zero without complaint, producing a nonsensical cart total.", "quantity"),
    "D13": ("Cart is a dead end", [3], 2, "cart",
            "The cart page has no header navigation and no 'continue shopping' link; only the browser back button escapes.", "cart"),
    "D14": ("Search gives no loading indication", [1], 2, "search",
            "Searching takes several seconds with no spinner or 'searching' message, so the page looks frozen.", "search"),
    "D15": ("Product page overloaded with promotions", [8], 1, "product",
            "Many stacked promotional banners push the product details and Add button far down the page.", "product"),
    "D16": ("Variant choice not remembered", [6], 2, "product",
            "After adding an item and returning to the product, the chosen size/colour is reset and the cart line does not show which variant was added.", "variant"),
    "D17": ("Large collection with no filtering or sorting", [7], 2, "collection",
            "A collection of many products has no filters, no sort and no pagination aids.", "nav"),
    "D18": ("Tiny tap targets on mobile", [4, 7], 2, "mobile",
            "On a phone-width screen, the Add, quantity and remove controls are very small and crowded together.", "mobile"),
}
HOLDOUT_ONLY = ("D16", "D17", "D18", "D12")

DECOYS = {
    "X1": "Unusual but legible colour scheme (deep green and cream).",
    "X2": "A serif display typeface for headings.",
    "X3": "A deliberately minimal home page with only three featured products.",
    "X4": "A large footer with many links.",
}

AREAS = ["home", "nav", "search", "typo_search", "product", "variant", "add", "quantity", "remove", "cart",
         "checkout", "help"]


def card(did):
    t, h, sev, page, sym, area = DEFECTS[did]
    return {"id": did, "title": t, "heuristics": h, "severity": sev, "page": page, "symptom": sym, "area": area}
