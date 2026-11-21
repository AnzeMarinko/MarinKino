"""Four activity suggestions and legacy journal field labels."""

STYLES = {
    "steady": "Umirjeno / enakomerno",
    "intervals": "Intervali",
    "distance": "Na razdaljo",
    "circuit": "Krožna vadba",
    "recovery": "Regeneracija",
}
EQUIPMENT = {
    "bodyweight": "Lastna teža",
    "kettlebell": "Kettlebell",
    "weights": "Uteži",
    "band": "Elastika",
    "other": "Drugo",
}
GENERAL_ADVICE = {}

# One suggestion per activity type; completed sessions form the journal.
SUGGESTIONS = (
    {"id": "cycling", "kind": "cycling", "title": "Kolesarjenje"},
    {"id": "running", "kind": "running", "title": "Tek"},
    {"id": "strength", "kind": "strength", "title": "Uteži"},
    {"id": "cardio", "kind": "cardio", "title": "Kardio"},
)
