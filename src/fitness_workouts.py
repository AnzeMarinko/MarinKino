"""Editable workout examples; separate from users' saved templates."""

CYCLING_SOURCE = (
    "https://www.britishcycling.org.uk/news/article/"
    "20120704-Insight-Zone--Basic-tips-%E2%80%93-Gear-Selection-0"
)
RUNNING_SOURCE = (
    "https://www.nhs.uk/better-health/get-active/get-running-with-couch-to-5k/"
)
STRENGTH_SOURCE = "https://www.nhs.uk/live-well/exercise/strength-exercises/"

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
GENERAL_ADVICE = {
    "cycling": (
        "Primer razporeditve: 1 umirjena daljša vožnja in 1 vadba kadence "
        "tedensko; vmes lahka vadba ali počitek. Kadenca ni merilo napora: "
        "prilagodi tudi prestavo, upor in dihanje."
    ),
    "running": (
        "Če že redno tečeš, je primer tedna 1 umirjen tek na razdaljo in "
        "1 intervalni tek, z dnevom regeneracije vmes. Za začetek izberi "
        "izmenjavanje hoje in teka ter postopno podaljšuj znano razdaljo."
    ),
    "strength": (
        "Primer: 2 dneva moči tedensko z vmesnim dnem za regeneracijo. "
        "Menjaj vadbo z lastno težo in utežjo; breme in ponovitve prilagodi "
        "tako, da ohraniš nadzor nad izvedbo."
    ),
    "cardio": (
        "Izberi krožno vadbo z lastno težo ali kettlebellom. Izmenjuj delo "
        "in odmor, začni z lažjo različico ter prilagodi kroge in tempo."
    ),
}

# The schedules and repetitions below are editable examples, not individual
# prescriptions. Sources provide technique and general training principles.
SUGGESTIONS = (
    {
        "id": "cycling-steady",
        "kind": "cycling",
        "title": "Umirjeno kolesarjenje",
        "training_style": "steady",
        "duration_min": 50,
        "intensity": "moderate",
        "cadence_rpm": 85,
        "description": (
            "10 min lahkega ogrevanja; 35 min enakomerne vožnje pri udobnih "
            "približno 80–90 obr./min; 5 min umirjanja. Traso prilagodi."
        ),
        "advice": (
            "Primer: 1 takšna vožnja tedensko. Uporabi prestavo, ki omogoča "
            "mirno vrtenje in pogovor; obrati niso cilj za vsako ceno."
        ),
        "tutorial_url": CYCLING_SOURCE,
    },
    {
        "id": "cycling-cadence",
        "kind": "cycling",
        "title": "Kolesarjenje: intervali kadence",
        "training_style": "intervals",
        "duration_min": 30,
        "intensity": "moderate",
        "cadence_rpm": 95,
        "description": (
            "8 min ogrevanja; 6 × (1 min pri približno 90–100 obr./min "
            "+ 2 min lahkotno pri 75–85 obr./min); 4 min umirjanja. "
            "Lahka prestava, gladko vrtenje brez poskakovanja na sedežu."
        ),
        "advice": (
            "Primer: 1 vadba kadence tedensko poleg umirjene vožnje. "
            "To je vaja tehnike, ne sprint; najprej prilagodi število "
            "ponovitev. Za intervale izberi trenažer ali varen odsek."
        ),
        "tutorial_url": CYCLING_SOURCE,
    },
    {
        "id": "running-distance",
        "kind": "running",
        "title": "Umirjen tek na razdaljo",
        "training_style": "distance",
        "duration_min": 40,
        "intensity": "moderate",
        "description": (
            "5 min hitre hoje; približno 30 min lahkotnega teka po izbrani "
            "trasi; 5 min hoje. Pred vadbo dopiši načrtovano razdaljo, "
            "po izvedbi pa dejanske kilometre in čas."
        ),
        "advice": (
            "Primer: 1 daljši umirjen tek tedensko. Izberi že obvladljivo "
            "razdaljo in pogovorni tempo; podaljšuj postopno. Čas je "
            "ocena, ne zahteva glede hitrosti."
        ),
        "tutorial_url": RUNNING_SOURCE,
    },
    {
        "id": "running-intervals",
        "kind": "running",
        "title": "Tek: kratki intervali",
        "training_style": "intervals",
        "duration_min": 30,
        "intensity": "moderate",
        "description": (
            "8 min hoje ali lahkotnega teka; 6 × (1 min živahnejšega teka "
            "+ 2 min zelo lahkotnega teka ali hoje); 4 min umirjanja. "
            "Hitri odseki naj bodo nadzorovani, brez maksimalnega sprinta."
        ),
        "advice": (
            "Primer za rednega tekača: 1 intervalni tek tedensko, med njim "
            "in daljšim tekom dan lahke aktivnosti ali počitka. Začetnik "
            "lahko hitre odseke zamenja z običajnim tekom in odmore s hojo."
        ),
        "tutorial_url": RUNNING_SOURCE,
    },
    {
        "id": "strength-bodyweight",
        "kind": "strength",
        "title": "Moč z lastno težo",
        "training_style": "circuit",
        "equipment": "bodyweight",
        "duration_min": 25,
        "intensity": "moderate",
        "description": (
            "5 min ogrevanja. Primer 2–3 krogov: 8–12 počepov na stol, "
            "6–10 sklec ob steni ali opori, 10 dvigov bokov, 6 iztegov "
            "nasprotne roke in noge na vsako stran, 20 s opore. "
            "Med krogi 60–90 s odmora; na koncu umirjanje."
        ),
        "advice": GENERAL_ADVICE["strength"],
        "tutorial_url": STRENGTH_SOURCE,
    },
    {
        "id": "strength-kettlebell",
        "kind": "strength",
        "title": "Moč s kettlebellom",
        "training_style": "circuit",
        "equipment": "kettlebell",
        "duration_min": 30,
        "intensity": "moderate",
        "description": (
            "5 min ogrevanja. Primer 2–3 serij: 6–10 počepov z utežjo "
            "pred prsmi, 8–10 mrtvih dvigov in 8 veslanj na vsako stran. "
            "Med serijami 60–90 s odmora; na koncu lahkotno umirjanje."
        ),
        "advice": (
            "Izberi eno od dveh tedenskih vadb moči. Uporabi breme in "
            "vaje, katerih tehniko obvladaš; najprej nadzor, nato več "
            "ponovitev ali teže. Tutorial za lastno težo lahko zamenjaš "
            "s prikazom svojih vaj s kettlebellom."
        ),
        "tutorial_url": STRENGTH_SOURCE,
    },
    {
        "id": "cardio-bodyweight",
        "kind": "cardio",
        "title": "Krožni kardio z lastno težo",
        "training_style": "circuit",
        "equipment": "bodyweight",
        "duration_min": 20,
        "intensity": "moderate",
        "description": (
            "4 min ogrevanja; 3 krogi po 4 vaje, vsaka 40 s dela + 20 s "
            "odmora: živahna hoja na mestu, koraki vstran, počep na stol, "
            "izmenični korak nazaj. 4 min umirjanja."
        ),
        "advice": GENERAL_ADVICE["cardio"],
        "tutorial_url": STRENGTH_SOURCE,
    },
    {
        "id": "cardio-kettlebell",
        "kind": "cardio",
        "title": "Krožni kardio s kettlebellom",
        "training_style": "circuit",
        "equipment": "kettlebell",
        "duration_min": 20,
        "intensity": "moderate",
        "description": (
            "4 min ogrevanja; 3 krogi po 4 odseke, vsak 40 s dela + 20 s "
            "odmora: nadzorovani mrtvi dvigi, počepi z utežjo pred prsmi, "
            "hoja z utežjo in hoja brez uteži. 4 min umirjanja."
        ),
        "advice": (
            "Izmenjuj z vadbo brez opreme. Izberi lahko utež in znano "
            "tehniko; po potrebi skrajšaj delo ali podaljšaj odmor. "
            "Breme, krogi in tutorial so prilagodljivi."
        ),
        "tutorial_url": "",
    },
)
