"""The disclaimer wording supplied by the owner (2026-10-25), in one place so the layout footer, the Settings hint, the in-plugin Help and
docs/USER_GUIDE.md cannot drift apart (tests/test_disclaimer_text.py checks each against this module).

LAYOUT_DISCLAIMER is the owner's 'Balanced Standard Disclaimer': the footer line of every print layout unless the Settings box holds the
organisation's own wording. TERMS_PARAGRAPHS is the owner's 'Comprehensive Enterprise Disclaimer', shown in the Help and the user guide. This is
the owner's wording, not legal advice from me; it has not been reviewed by a lawyer."""

LAYOUT_DISCLAIMER = (
    "Boundaries, names, and designations shown on this map are for informational and illustrative purposes only and do not imply any official "
    "endorsement, acceptance, or recognition of legal or sovereign status by Cartogen AI or its data licensors. Maps and geospatial outputs are "
    "provided \"as is\" without warranty of any kind, whether express or implied, including accuracy, completeness, or fitness for navigation or "
    "planning. Users remain solely responsible for verifying data licensing, confidentiality classifications, and source permissions prior to "
    "internal use or external distribution."
)

TERMS_TITLE = "Disclaimer and terms of use"

TERMS_PARAGRAPHS = (
    ("1. No Endorsement or Legal Determination:",
     ("Boundaries, territorial depictions, place names, and administrative designations presented herein are illustrative and do not reflect any "
     "opinion, endorsement, or formal position by Cartogen AI or its third-party data providers concerning the legal status of any country, "
     "territory, city, or area, or concerning the delimitation of its frontiers or boundaries.")),
    ("2. Disclaimer of Warranties & Limitation of Reliance:",
     ("This visual output is provided on an \"as is\" and \"as available\" basis without warranties of any kind. Cartogen AI expressly disclaims all "
     "implied warranties of merchantability, fitness for a particular purpose, spatial accuracy, or timeliness. This map must not be relied upon "
     "for maritime or aerial navigation, property boundary delineation, or emergency response operations.")),
    ("3. User Obligations & Third-Party Rights:",
     ("Users are solely responsible for ensuring that the distribution, export, or publication of this map complies with all applicable privacy "
     "laws, data protection regulations, and proprietary data license agreements governing user-supplied or third-party datasets.")),
)
