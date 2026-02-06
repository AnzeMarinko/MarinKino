var nPlayersSlider = document.getElementById("nPlayersSlider");
var nPlayersText = document.getElementById("nPlayersText");
var nPlayers = 0;
var maxOthers = 2;
var minOthers = 1;
var nUndercoverSlider = document.getElementById("nUndercoverSlider");
var nUndercoversText = document.getElementById("nUndercoversText");
var nUndercovers = 0;
var nWhitesSlider = document.getElementById("nWhitesSlider");
var nWhitesText = document.getElementById("nWhitesText");
var nWhites = 0;
var isMrMeme = -1;

var hiddenTemplate = document.getElementById("hidden-template").innerHTML;
var namesInput = document.getElementById("namesInput");

function set_number_of_players() {
    nPlayersText.innerHTML = nPlayersSlider.value;
    for (var i = 0; i < Math.max(nPlayersSlider.value, nPlayers); i++) {
        if (i >= nPlayers) {
            namesInput.insertAdjacentHTML("beforeend", hiddenTemplate);
            var last_div = document.getElementById("-1");
            last_div.id = i.toString();
            last_div.querySelector('input[id="m"]').name = last_div.id;
            last_div.querySelector('input[id="f"]').name = last_div.id;
        };
        if (i >= nPlayersSlider.value) {
            var ninp = document.getElementsByClassName("nameInput");
            ninp[0].parentNode.removeChild(ninp[ninp.length - 1]);
        }
    };
    nPlayers = nPlayersSlider.value;
    maxOthers = Math.floor(nPlayers / 2);
    nUndercoversSlider.value = Math.ceil(maxOthers / 2);
    nUndercoversSlider.max = maxOthers;
    nWhitesSlider.value = Math.floor(maxOthers / 2);
    nWhitesSlider.max = Math.ceil(maxOthers / 2);
    set_number_of_undercovers();
    set_number_of_whites();
}

function set_number_of_undercovers() {
    nUndercoversText.innerHTML = nUndercoversSlider.value;
    nUndercovers = nUndercoversSlider.value;
    if (nWhitesSlider.value > maxOthers - nUndercoversSlider.value) {
        nWhitesSlider.value = maxOthers - nUndercoversSlider.value;
        set_number_of_whites();
    } else if (nWhitesSlider.value + nUndercoversSlider.value < minOthers) {
        nWhitesSlider.value = minOthers - nUndercoversSlider.value;
        set_number_of_whites();
    }
}

function set_number_of_whites() {
    nWhitesText.innerHTML = nWhitesSlider.value;
    nWhites = nWhitesSlider.value;
    if (nUndercoversSlider.value > maxOthers - nWhitesSlider.value) {
        nUndercoversSlider.value = maxOthers - nWhitesSlider.value;
        set_number_of_undercovers();
    } else if (nWhitesSlider.value + nUndercoversSlider.value < minOthers) {
        nUndercoversSlider.value = minOthers - nWhitesSlider.value;
        set_number_of_undercovers();
    }
}

nPlayersSlider.oninput = function () {
    set_number_of_players()
}

nUndercoversSlider.oninput = function () {
    set_number_of_undercovers()
}

nWhitesSlider.oninput = function () {
    set_number_of_whites()
}

function reset_game() {
    nPlayers = 0;
    nUndercovers = nUndercoversSlider.min + 1;
    nWhites = nWhitesSlider.min;
    namesInput.innerHTML = "";
    nPlayersSlider.value = nPlayersSlider.min;
    nUndercoversSlider.value = nUndercovers;
    nWhitesSlider.value = nWhites;
    set_number_of_players();
    set_number_of_undercovers();
    set_number_of_whites();
}
reset_game()

function pravila_igre(mode) {
    if (mode == "none") {
        document.getElementById("navodila").style.display = "none";
        document.getElementById("nastavitve").style.display = "block";
    } else {
        document.getElementById("navodila").style.display = "block";
        document.getElementById("nastavitve").style.display = "none";
    }
}

// logika igre
const deli_igre = Object.freeze({
    IZBIRA_BESED: 0,
    KROG_BESED_IZLOCANJE: 1,
    BELI_UGIBA: 2,
    BELI_ZGRESIL: 3,
    BELI_UGANIL: 4,
    KONEC_IGRE: 5
})

var igralci = [];
var beseda_prebivalci = "";
var beseda_vohuni = "";
var del_igre = deli_igre.IZBIRA_BESED;
var krog_igre = 0;

var ugibajoci_beli = 0;
var zmagovalci = {};

var nerazdeljene_vloge = [];
const randomItem = arr => arr.splice((Math.random() * arr.length) | 0, 1);
var hiddenCardTemplate = document.getElementById("hidden-card-template").innerHTML;
var kartice = document.getElementById("kartice");

function calculateSum(property) {
    const total = igralci.reduce((accumulator, object) => {
        return accumulator + object[property];
    }, 0);
    return total;
}

function prestej_vloge(vloga) {
    const total = igralci.reduce((accumulator, object) => {
        return accumulator + ((object["vloga"] == vloga) & (object["aktiven"]));
    }, 0);
    return total;
}

function change_badge_visibility(mode) {
    for (let element of document.getElementsByClassName("izkljuci")) {
        if (mode == "block") {
            element.style.display = "block";
        } else {
            element.style.display = "none";
        }
    }
}

function overlay_display_mode(element, mode) {
    if (mode == "block") {
        if ((del_igre == deli_igre.IZBIRA_BESED) & (igralci.length != calculateSum("videl_besedo"))) {
            document.getElementById("overlay").style.display = mode;
            document.getElementById("overlay_name").innerHTML = igralci[parseInt(element.id.substring(4))].ime + ":";
            var vloga = igralci[parseInt(element.id.substring(4))].vloga;
            if (vloga == "prebivalec") {
                document.getElementById("overlay_word").innerHTML = beseda_prebivalci;
            } else if (vloga == "vohun") {
                document.getElementById("overlay_word").innerHTML = beseda_vohuni;
            } else {
                document.getElementById("overlay_word").innerHTML = "Ti si gospod v belem ;)";
            }
            igralci[parseInt(element.id.substring(4))].videl_besedo = true;
        }
    } else if (del_igre == deli_igre.BELI_UGIBA) {
        return 0;
    } else if (del_igre == deli_igre.BELI_ZGRESIL) {
        document.getElementById("overlay_izkljucitev").style.display = "none";
        document.getElementById("igra").style.display = "block";
        document.getElementById("overlay_name").innerHTML = "Več sreče prihodnjič &#128549;";
        document.getElementById("overlay_word").innerHTML = "";
        document.getElementById("overlay").style.display = "block";
        setTimeout(function () { del_igre = deli_igre.KROG_BESED_IZLOCANJE; }, 1000);
    } else if (del_igre == deli_igre.KONEC_IGRE) {
        return 0;
    } else {
        document.getElementById("overlay").style.display = mode;
        document.getElementById("overlay_izkljucitev").style.display = mode;
        document.getElementById("overlay_rezultati").style.display = mode;
        document.getElementById("igra").style.display = "block";
        if (del_igre == deli_igre.IZBIRA_BESED) {
            if (igralci.length == calculateSum("videl_besedo")) {
                del_igre = deli_igre.KROG_BESED_IZLOCANJE;
                if (isMrMeme >= 0) {
                    setTimeout(function () { alert(igralci[isMrMeme].ime + " je gospod Nemec."); }, 1000);
                }
                change_badge_visibility("block");
            } else {
                return 0
            }
        }
        var nebeli = [];
        for (var i = 0; i < igralci.length; i++) {
            if (((igralci[i].vloga != "gospod-v-belem") & (igralci[i].aktiven)) | (krog_igre > 0)) {
                nebeli.push(i);
            }
        }
        prvi_namig = igralci[nebeli[Math.floor(Math.random() * nebeli.length)]].ime;
        document.getElementById("navodilo").innerHTML = "Prvi namig poda " + prvi_namig + ".<br>Po enem krogu začnite z izločanjem.";
        if (isMrMeme >= 0) {
            document.getElementById("navodilo").innerHTML += "<br>" + igralci[isMrMeme].ime + " je gospod Nemec.";
        }

        var aktivni_prebivalci = prestej_vloge("prebivalec");
        var aktivni_vohuni = prestej_vloge("vohun");
        var aktivni_beli = prestej_vloge("gospod-v-belem");
        document.getElementById("stanje_prebivalci").innerHTML = "Preostali prebivalci: " + aktivni_prebivalci;
        document.getElementById("stanje_vohuni").innerHTML = "Preostali vohuni: " + aktivni_vohuni;
        document.getElementById("stanje_beli").innerHTML = "Preostali gospodje v belem: " + aktivni_beli;

        if (del_igre == deli_igre.BELI_UGANIL) {
            if (isMrMeme == ugibajoci_beli) {
                igralci[ugibajoci_beli].nove_tocke = 9;
            } else {
                igralci[ugibajoci_beli].nove_tocke = 7;
            }
            del_igre = deli_igre.KONEC_IGRE;
        } else if (aktivni_prebivalci == 1) {
            for (var i = 0; i < igralci.length; i++) {
                if (igralci[i].aktiven) {
                    if (igralci[i].vloga == "vohun") {
                        if (isMrMeme >= 0) {
                            if ((igralci[isMrMeme].vloga == "vohun") & igralci[isMrMeme].aktiven) {
                                igralci[i].nove_tocke = 7;
                            } else {
                                igralci[i].nove_tocke = 5;
                            }
                        } else {
                            igralci[i].nove_tocke = 5;
                        }
                    } else if (igralci[i].vloga == "gospod-v-belem") {
                        if (isMrMeme >= 0) {
                            if ((igralci[isMrMeme].vloga == "gospod-v-belem") & igralci[isMrMeme].aktiven) {
                                igralci[i].nove_tocke = 9;
                            } else {
                                igralci[i].nove_tocke = 7;
                            }
                        } else {
                            igralci[i].nove_tocke = 7;
                        }
                    }
                }
            }
            del_igre = deli_igre.KONEC_IGRE;
        } else if (aktivni_vohuni + aktivni_beli == 0) {
            for (var i = 0; i < igralci.length; i++) {
                if ((igralci[i].aktiven) & (igralci[i].vloga == "prebivalec")) {
                    if (isMrMeme >= 0) {
                        if ((igralci[isMrMeme].vloga == "prebivalec") & igralci[isMrMeme].aktiven) {
                            igralci[i].nove_tocke = 4;
                        } else {
                            igralci[i].nove_tocke = 2;
                        }
                    } else {
                        igralci[i].nove_tocke = 2;
                    }
                }
            }
            del_igre = deli_igre.KONEC_IGRE;
        }
        if ((isMrMeme >= 0) & (del_igre == deli_igre.KONEC_IGRE)) {
            if (igralci[isMrMeme].nove_tocke > 0) {
                alert("Gospod Nemec je v zmagovalni ekipi.");
            }
        }

        if (del_igre == deli_igre.KONEC_IGRE) {
            for (var i = 0; i < igralci.length; i++) {
                igralci[i].tocke += igralci[i].nove_tocke;
            }
            rezultati();
        }
    }
}

function dokončaj_izključitev(element) {
    var card = element.parentNode;
    var izkljuceni = parseInt(card.id.substring(4));
    element.style.display = "none";

    if (igralci[izkljuceni].vloga == "gospod-v-belem") {
        document.getElementById("overlay_text_izkljucitev").innerHTML = igralci[izkljuceni].ime + " je gospod v belem";
    } else {
        document.getElementById("overlay_text_izkljucitev").innerHTML = igralci[izkljuceni].ime + " je " + igralci[izkljuceni].vloga;
    }

    document.getElementById("ugibanje_beli").style.display = "none";
    if (igralci[izkljuceni].vloga == "gospod-v-belem") {
        card.className = "button button_beli";
        document.getElementById("overlay_image").src = "/static/pod_krinko_avatars/gospod_v_belem.png";
        document.querySelector('input[id="ugibanje"]').value = ""
        document.getElementById("ugibanje_beli").style.display = "block";
        del_igre = deli_igre.BELI_UGIBA;

        ugibajoci_beli = izkljuceni;
    } else if (igralci[izkljuceni].vloga == "vohun") {
        card.className = "button button_agent";
        document.getElementById("overlay_image").src = "/static/pod_krinko_avatars/pod_krinko.png";
    } else if (igralci[izkljuceni].vloga == "prebivalec") {
        if (igralci[izkljuceni].spol == "m") {
            card.className = "button button_civilist";
            document.getElementById("overlay_image").src = "/static/pod_krinko_avatars/civilist.png";
        } else {
            card.className = "button button_civilistka";
            document.getElementById("overlay_image").src = "/static/pod_krinko_avatars/civilistka.png";
        }
    }
    document.getElementById("overlay_izkljucitev").style.display = "block";
    document.getElementById("igra").style.display = "none";

    card.style.opacity = 0.5;
    element.classList.remove("izkljuci_on");
    igralci[izkljuceni].aktiven = false;
}

let playerToEliminate = null;
let elementToEliminate = null;

function izkljuci(element) {
    elementToEliminate = element;
    playerToEliminate = parseInt(element.parentNode.id.substring(4));
    
    const modalText = document.getElementById("modal-body-text");
    modalText.innerHTML = `Ali res želite izločiti igralca <b>${igralci[playerToEliminate].ime}</b>?`;
    
    const myModal = new bootstrap.Modal(document.getElementById('confirmModal'));
    myModal.show();
}

// Dogodek za gumb v modalu
document.getElementById("confirmEliminationBtn").onclick = function() {
    const modalEl = document.getElementById('confirmModal');
    const modal = bootstrap.Modal.getInstance(modalEl);
    modal.hide();
    
    // Tukaj pokliči svojo originalno logiko izključitve, ki si jo imel prej
    dokončaj_izključitev(elementToEliminate); 
};

// Preveri podvojena imena (case-insensitive)
function hasDuplicateNames(names) {
    const lowerNames = names.map(n => n.toLowerCase());
    return new Set(lowerNames).size !== lowerNames.length;
}

// Shranjevanje točk in nastavitev
function saveGameState() {
    const data = {
        nPlayers: nPlayersSlider.value,
        nUndercovers: nUndercoversSlider.value,
        nWhites: nWhitesSlider.value,
        tocke: igralci.map(p => ({ ime: p.ime, tocke: p.tocke }))
    };
    localStorage.setItem('podKrinko_data', JSON.stringify(data));
}

async function start_new_game() {
    // Hide overlays/results so only one view is visible when starting a new game
    var el = document.getElementById("overlay_rezultati"); if (el) el.style.display = "none";
    var el2 = document.getElementById("overlay"); if (el2) el2.style.display = "none";
    var el3 = document.getElementById("overlay_izkljucitev"); if (el3) el3.style.display = "none";
    var el4 = document.getElementById("menu_results"); if (el4) el4.style.display = "none";

    let namesInputElements = document.querySelectorAll('.nameInput input[type="text"]');
    let names = Array.from(namesInputElements).map(i => i.value.trim());

    if (names.some(n => n === "")) {
        alert("Prosim, vnesi imena vseh igralcev.");
        return;
    }

    if (hasDuplicateNames(names)) {
        alert("Napaka: Dva igralca imata isto ime!");
        return;
    }

    // --- Ostala logika za vloge (iz tvoje originalne kode) ---
    nerazdeljene_vloge = [];
    for (var i = 0; i < nPlayers - nUndercovers - nWhites; i++) nerazdeljene_vloge.push("prebivalec");
    for (var i = 0; i < nUndercovers; i++) nerazdeljene_vloge.push("vohun");
    for (var i = 0; i < nWhites; i++) nerazdeljene_vloge.push("gospod-v-belem");
    
    isMrMeme = document.getElementById("nemec").checked ? Math.max(0, Math.ceil(Math.random() * nPlayers) - 1) : -1;

    for (var i = 0; i < nPlayers; i++) {
        let currentName = names[i];
        let currentGender = document.querySelector(`input[name="${i}"]:checked`).value;

        // Posodobimo ali ustvarimo igralca
        if (i >= igralci.length) {
            igralci.push({
                ime: currentName,
                spol: currentGender,
                tocke: 0,
                vloga: randomItem(nerazdeljene_vloge),
                aktiven: true,
                videl_besedo: false,
                nove_tocke: 0
            });
            kartice.insertAdjacentHTML("beforeend", hiddenCardTemplate);
            var last_div = document.getElementById("card-1");
            last_div.id = "card" + i.toString();
        } else {
            igralci[i].ime = currentName;
            igralci[i].spol = currentGender;
            igralci[i].vloga = randomItem(nerazdeljene_vloge);
            igralci[i].aktiven = true;
            igralci[i].videl_besedo = false;
            igralci[i].nove_tocke = 0;
            var last_div = document.getElementById("card" + i.toString());
        }
        
        last_div.querySelector('.name').innerHTML = currentName;
        last_div.style.opacity = 1;
        last_div.className = (currentGender === "m") ? "button button_neznanec" : "button button_neznanka";
    }

    saveGameState(); // Shrani ob vsakem novem krogu
    
    // UI preklop
    document.getElementById("igra").style.display = "block";
    document.getElementById("menu").style.display = "block";
    document.getElementById("nastavitve").style.display = "none";
    
    // Besede
    const response = await fetch(`/pod_krinko/new_words`);
    const besedi = await response.json();
    beseda_prebivalci = besedi[0];
    if (nUndercovers > 0) beseda_vohuni = besedi[1];
    
    del_igre = deli_igre.IZBIRA_BESED;

    zmagovalci = {};
    change_badge_visibility("none");
    document.getElementById("navodilo").innerHTML = "Vsak igralec naj na skrivaj pogleda svojo besedo.";
    document.getElementById("stanje_prebivalci").innerHTML = "";
    document.getElementById("stanje_vohuni").innerHTML = "";
    document.getElementById("stanje_beli").innerHTML = "";
}

// Funkcija za nalaganje ob osvežitvi strani
window.onload = function() {
    const savedData = localStorage.getItem('podKrinkoData');
    if (savedData) {
        const data = JSON.parse(savedData);
        nPlayersSlider.value = data.nPlayers;
        set_number_of_players(); // To bo generiralo input polja
        
        data.igralci.forEach((savedPlayer, index) => {
            const inputDiv = document.getElementById(index.toString());
            if (inputDiv) {
                inputDiv.querySelector('input[type="text"]').value = savedPlayer.ime;
                inputDiv.querySelector(`input[value="${savedPlayer.spol}"]`).checked = true;
            }
        });
    }
};

function pojdi_v_nastavitve() {
    if (confirm("Želite res nazaj v nastavitve?\nPodatki o igralcih se bodo ohranili,\n" +
            "ampak točke se bodo ponastavile!")) {
        document.getElementById("overlay").style.display = "none";
        document.getElementById("overlay_rezultati").style.display = "none";
        document.getElementById("overlay_izkljucitev").style.display = "none";
        document.getElementById("igra").style.display = "none";
        document.getElementById("menu").style.display = "none";
        document.getElementById("nastavitve").style.display = "block";
        igralci = [];
        kartice.innerHTML = "";
    }
}

function ugibaj() {
    var poskus = document.querySelector('input[id="ugibanje"]').value.toLowerCase();
    var uspeh = (poskus == beseda_prebivalci.toLowerCase());
    if (uspeh) {
        igralci[ugibajoci_beli].aktiven = true;
        var card = document.getElementById("card" + ugibajoci_beli.toString());
        card.style.opacity = 1.0;
        del_igre = deli_igre.BELI_UGANIL;
        overlay_display_mode("", "none");
    } else {
        del_igre = deli_igre.BELI_ZGRESIL;
        overlay_display_mode("", "none");
    }
}

var hiddenResultTemplate = document.getElementById("hidden-result-template").innerHTML;
var osebe_rezultati = document.getElementById("osebe_rezultati");
var besedi_rezultati = document.getElementById("besedi_rezultati");

function rezultati() {
    var igralci_sortirani = igralci.slice();
    igralci_sortirani.sort((a, b) => b.tocke - a.tocke);
    osebe_rezultati.innerHTML = "";
    besedi_rezultati.innerHTML = "";
    var max_tock = Math.max(1, igralci_sortirani[0].tocke);

    for (var i = 0; i < igralci_sortirani.length; i++) {
        // spol, vloga, aktiven
        osebe_rezultati.insertAdjacentHTML("beforeend", hiddenResultTemplate);
        var last_div = document.getElementById("result-1");
        last_div.id = "result" + i.toString();
        last_div.querySelector('span[class="name"]').innerHTML = igralci_sortirani[i].ime.toString() + ": " + igralci_sortirani[i].tocke.toString() + " točk" + (igralci_sortirani[i].tocke == 2 ? "i" : (igralci_sortirani[i].tocke < 5 ? "e" : ""));
        last_div.querySelector('progress[id="progress"]').value = igralci_sortirani[i].tocke / max_tock * 100;

        if (igralci_sortirani[i].nove_tocke > 0) {
            last_div.querySelector('span[class="nove_tocke"]').innerHTML = "(+" + igralci_sortirani[i].nove_tocke.toString() + ")";
        }
        if (igralci_sortirani[i].aktiven) {
            last_div.style.opacity = 1;
        } else {
            last_div.style.opacity = 0.5;
        }
        if ((del_igre == deli_igre.KONEC_IGRE) | (!igralci_sortirani[i].aktiven)) {
            if (igralci_sortirani[i].vloga == "prebivalec") {
                if (igralci_sortirani[i].spol == "m") {
                    last_div.className = "button_result button_civilist";
                } else {
                    last_div.className = "button_result button_civilistka";
                }
            } else if (igralci_sortirani[i].vloga == "vohun") {
                last_div.className = "button_result button_agent";
            } else {
                last_div.className = "button_result button_beli";
            }
        } else {
            if (igralci_sortirani[i].spol == "m") {
                last_div.className = "button_result button_neznanec";
            } else {
                last_div.className = "button_result button_neznanka";
            }
        }
    }

    if (del_igre == deli_igre.KONEC_IGRE) {
        besedi_rezultati.innerHTML = "Prebivalci: " + beseda_prebivalci + "<br>Vohuni: " + beseda_vohuni;
    }
    document.getElementById("menu_results").style.display = "block";
    document.getElementById("overlay_rezultati").style.display = "block";
    document.getElementById("igra").style.display = "none";
}

// Pomožna funkcija za nalaganje zadnjih uporabljenih imen
function nalozi_zadnja_imena() {
    const savedData = localStorage.getItem('podKrinko_zadnjaImena');
    if (savedData) {
        const prejsnjaImena = JSON.parse(savedData);
        const inputs = document.querySelectorAll('.nameInput input[type="text"]');
        
        prejsnjaImena.forEach((podatki, index) => {
            if (index < inputs.length) {
                inputs[index].value = podatki.ime;
                // Nastavi še spol, če obstaja
                const radioSpol = document.querySelector(`input[name="${index}"][value="${podatki.spol}"]`);
                if (radioSpol) radioSpol.checked = true;
            }
        });
    }
}

// To funkcijo pokliči znotraj start_new_game(), ko so imena validirana
function shrani_imena_za_naslednjic() {
    const trenutnaImena = igralci.map(p => ({ ime: p.ime, spol: p.spol }));
    localStorage.setItem('podKrinko_zadnjaImena', JSON.stringify(trenutnaImena));
}

// Posodobljena funkcija set_number_of_players, da po generiranju polj poskusi vstaviti stara imena
const original_set_players = set_number_of_players;
set_number_of_players = function() {
    original_set_players();
    nalozi_zadnja_imena();
};

