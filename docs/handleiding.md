# Handleiding KaraokeTool

Korte gids voor de werkwijze, de tekstnotatie, de editors en de keuzes.
Voor de technische stand van zaken zie `docs/doorontwikkeling.md`; voor
de vraag wat er vervalt als je iets aan het begin vervangt zie
`docs/afhankelijkheden.md`.

De knoppen dragen een dubbel nummer: het eerste cijfer is het tabblad,
het tweede de volgorde daarop. "2.2. Timing verfijnen" is dus de tweede
knop op tabblad 2 (Karaokevideo).

## Werkwijze in het kort

De knoppen hieronder staan in dezelfde volgorde als in de app. Stappen
met *(optioneel)* kun je overslaan; de overige gebruiken elkaars uitvoer.

1. **Muziek laden en analyse** (tab 1)
   - Kies het **origineel** (mp3/wav) en de **karaoke**. Heb je geen
     karaoke, maak er dan één met **"Karaoke uit origineel"** (Demucs
     haalt de zang eruit; het resultaat komt ook als
     `karaoke_demucs.mp3` in de outputmap).
   - Zet de **songtekst** (`songtekst.txt`), de **karaoketekst**
     (`karaoketekst.txt`) en eventueel een **logo** klaar op deze tab. De
     originele tekst is leidend voor de taaldetectie en de koppeling; de
     karaoketekst en het logo worden in de video gebruikt. Achter elk
     bestand staat de naam die het bij jou had, niet de interne naam.
   - **1.1. Detecteer woorden** → transcribeert met Whisper. Is Demucs
     beschikbaar, dan draait dit op de geïsoleerde zangstem, wat de
     woorden en tijden veel betrouwbaarder maakt. Deze stap bepaalt ook
     de offset tussen origineel en karaoke.
   - **1.2. Woorden koppelen** → koppelt de getranscribeerde woorden van
     het **origineel** aan de **songtekst** (handmatig bij te sturen).
     Beide rijen tonen dus tekst van het origineel, niet de karaoke; de
     karaoke komt pas in beeld bij "2.2. Timing verfijnen" en de
     golfvorm-editor.
   - **1.3. Analyse** → klankclusters (voor het dempen van restzang).
     Levert ook een HTML-rapport op ("HTML-rapport openen") waarin je
     per cluster de vondsten naast elkaar ziet.
   - **1.4. Karaoke aanpassen** *(optioneel)* → dempt de aangevinkte
     clusters en exporteert `karaoke_edit`. Alleen nodig als er restzang
     uit het origineel in de karaoke zit die je wilt verzachten. Daarna
     vervangt een lijst **gedempte fragmenten** de clusterlijst: een
     vinkje weghalen past de demping meteen opnieuw toe.
   - **1.5. Test** *(tijdelijk)* → opent een aanvinklijst met tien
     genummerde onderzoeken (1.5.1 tot en met 1.5.10): de cache
     terugzetten, de ijkset-status, de projectcontrole (teksten, filters
     en structuur in één), ontbrekende herhalingen, de meetlat, unieke
     tegen herhaalde regels, de woord- en lettergreeptoetsen, de
     Whisper-venstertest, de weglaatproef en de grote proef. Die laatste
     zet alle modellen tegen elkaar af — apart, in alle paren en in
     omgekeerde volgorde, op blok-, zin-, koppel- en woordniveau — en
     doet daar ongeveer een half uur over; hij schrijft onderweg weg in
     `docs/modelmatrix.md`, dus afbreken kost je alleen de variant waar
     hij mee bezig is. Tien is het maximum: komt er iets bij, dan worden
     kleine tests samengevoegd.

     Bovenin staat **Alles aanvinken** (nog eens klikken is alles weer
     uit) en een vinkje **Opnieuw meten**. Dat laatste heb je meestal
     niet nodig: er wordt per actie, project en versie bijgehouden wat er
     al gemeten is, dus een project dat sinds de vorige draai niet
     veranderd is wordt overgeslagen, en de meetlat zet zijn cijfers
     naast die van de drie vorige versies. Verander je een tekst, een
     timing of een modelstand, dan telt dat als nieuwe gegevens en wordt
     er vanzelf opnieuw gemeten. Onderaan staat Start; de vinkjes staan
     bij het openen altijd uit, zodat je nooit per ongeluk een lange
     meting start. Met de twee rondjes eronder kies je of de metingen
     over alle projecten gaan of alleen over het project dat nu
     openstaat. Stop werkt ook hier. Elke test zet zijn uitslag in het
     logvenster zodra hij klaar is, dus je hoeft niet op de rest te
     wachten.

     Duurt een onderzoek langer dan een half uur, dan komt het niet in
     deze lijst maar onder **1.5.11 Zware proeven** — de nachtklussen.
     Die doet nooit mee met "Alles aanvinken", en als er niets onder
     staat is hij helemaal niet zichtbaar. Elk onderzoek daar slaat
     zichzelf over tot het twintig versies geleden is.

     Deze knop is er om onderzoek op jouw machine te kunnen doen en
     verdwijnt weer.

2. **Karaokevideo** (tab 2)
   - **2.1. Klemtoon bewerken** *(optioneel)* → elk woord krijgt
     automatisch klemtoon op de eerste lettergreep; hier corrigeer je dat
     waar nodig. Let op de volgorde: deze knop heeft een `timing.json`
     nodig, dus draai eerst "2.2. Timing verfijnen".
   - **2.2. Timing verfijnen** → maakt de timing op lettergreepniveau,
     gekoppeld aan de songtekst.
   - **2.3. Timing bewerken (golfvorm)** → fijnregelen: regels
     verschuiven/rekken, origineel en karaoke staan boven elkaar.
   - **2.4. Video maken** → rendert de karaokevideo. In het venster dat
     opengaat kies je zowel de **tekst** (getimede karaoketekst of
     getimede originele tekst) als de **muziek**.

Volgorde is belangrijk: een latere stap gebruikt de uitvoer van een
eerdere. Ontbreekt die, dan meldt de knop welke stap eerst (opnieuw)
moet. Vervang je een invoerbestand, dan worden de afgeleide resultaten
gewist en moeten de stappen opnieuw - zie "Wat werkt waarin door".

Terwijl een stap loopt kleurt zijn knop geel. **Stop** breekt de lopende
stap af; die knop kleurt zelf nooit geel, want hij start niets.

## Tekstnotatie (karaoketekst.txt)

- **Eén logische zin per regel.** Nooit willekeurig afbreken.
- **Lege regel** = sectiescheiding (blok).
- `# commentaar` (bv. `# Intro`, `# Couplet 2`): niet gezongen, niet
  getoond.
- **Crowd** (publiek zingt mee): kleurt wit → rood → grijs.
  - Als blok:

        [crowd]
        La-la-la...
        Hey...
        [/crowd]

  - Inline (midden in een regel): `G Z R, G Z R [crowd]Waertje![/crowd]`
    blijft één zin; alleen dat stukje ("Waertje!") kleurt in de video rood,
    de rest blijft groen. Een `[pause]` ervoor houdt de gewone kleur.
  - Een regel die helemaal `[crowd]...[/crowd]` is, telt gewoon mee bij de
    zin-koppeling zodra het aantal karaokeregels van het blok (crowd
    inbegrepen) precies het aantal songtekstregels evenaart - dan koppelt
    hij 1-op-1 aan zijn songtekst-equivalent (bv. een parodie-refrein op de
    plek van "Met bloed, zweet en tranen"). Klopt het aantal niet, dan valt
    hij terug op een kort "tussenroep"-tijdvak na de vorige zin en wordt hij
    in de golfvorm-editor (2.3. Timing bewerken (golfvorm)) ter oriëntatie
    gespiegeld in de originele-tekstbaan, met een rode gestippelde rand en
    het label "[crowd]" zodat duidelijk blijft dat het geen echte originele
    tekst is.
- **Achtergrondzang, gelijktijdig** (`[bg]...[/bg]`): voor een tweede stem
  die *tegelijk* met de vorige regel klinkt, bijvoorbeeld een backing-vocal
  die "Tonight, tonight" zingt terwijl de leadzang doorgaat - vaak in de
  songtekst tussen haakjes genoteerd, bv. "Sunday, Bloody Sunday (Tonight,
  tonight)". Werkt zowel in `songtekst.txt` (origineel) als in
  `karaoketekst.txt` (karaoke), onafhankelijk van elkaar - je kunt het in
  het ene bestand gebruiken zonder het andere.
  - Als blok:

        [bg]
        Tonight, tonight
        [/bg]

  - Of aan één regel geplakt: `[bg]Tonight, tonight[/bg]`.
  - Een `[bg]`-regel krijgt géén eigen plek in de zin-koppeling (telt niet
    mee bij het regelaantal per blok) maar hetzelfde tijdvak als de
    voorgaande regel, en wordt standaard niet getoond in "2.2. Timing
    verfijnen" en niet gerenderd (net als een uitgeschakelde regel) - de
    tekst helpt wel bij Whisper's herkenning en de hallucinatiecontrole.
    Wil je hem toch tonen/renderen, zet dat dan per regel aan in de
    timing-editor.
- **`[pause]`** (of `[pauze]`): markeert binnen één logische zin een
  zang-pauze, bv. `Want as de zangers [pause] weer gaan hossen`. De zin
  blijft in de render één geheel, maar telt voor de plaatsing/timing als
  twee delen met een eigen tijdvak voor de pauze. In de video verschijnen
  op die plek puntjes die tijdens de pauze één voor één oplichten (op de
  gemiddelde beat). Werkt ook binnen een `[crowd]`-blok.
- **Klemtoon** *(optioneel; knop "2.1. Klemtoon bewerken" op de
  video-tab)*: elk woord krijgt automatisch een klemtoon op de eerste
  lettergreep. Klopt dat niet (bv. ko-MEN i.p.v. KO-men), klik dan de
  juiste lettergreep aan; klik de gemarkeerde nog eens om de klemtoon weg
  te halen. De beklemtoonde lettergreep krijgt in de video een subtiel
  accent. Sla je deze stap over, dan geldt overal de automatische
  klemtoon.

## De editors

Vier vensters doen het handwerk. Ze lijken op elkaar, maar ze gaan
**verschillend om met sluiten** - dat is het eerste om te onthouden:

| Venster | "Sluiten" (en Esc) |
| --- | --- |
| 1.2. Woorden koppelen | slaat op |
| 2.1. Klemtoon bewerken | slaat op |
| 2.3. Timing bewerken (golfvorm) | gooit niet-opgeslagen werk weg |
| Demping bewerken | gooit niet-opgeslagen werk weg |

### 1.2. Woorden koppelen

Boven staan de woorden die Whisper hoorde, onder de songtekst. Klik een
woord boven én onder om ze te koppelen; klik op een lijn om die weg te
halen. Klik hetzelfde woord nog eens om de selectie los te laten. Zit een
woord in een samengevoegd blok, dan landt je klik op het woord waar je
werkelijk op wijst (de stippellijntjes in het blok laten de woordgrenzen
zien) en haalt een klik op de lijn de hele groep los.

De kleuren staan als **legenda** boven de rijen, bij de rest van de
uitleg - niet als tekst vóór de woorden zelf. De lijn tussen twee woorden
is groen bij een hoge gelijkenis, oranje bij een middelmatige, rood bij
een lage en **blauw als je hem zelf hebt gelegd**. Alleen die handmatige
koppelingen worden bewaard; de automatische worden elke keer opnieuw
bepaald. Een kader om een woord betekent:

- **oranje gestippeld** - overgeslagen stopwoord;
- **roze/rood gestippeld** - geen match gevonden;
- **paars gestippeld** - als hallucinatie eruit gefilterd;
- **grijsblauw gestippeld** - Whisper hoorde hier niets (een gat in de
  transcriptie);
- **groenblauw gestippeld** - niet gekoppeld, maar wel getimed op de
  zangstem: de tool heeft de plek op de zangenergie gemeten.

Een **doorgestreept** woord in de bovenste rij is een gevonden woord dat
eruit is gefilterd. Je mag het gewoon handmatig koppelen als het toch
klopt.

Twee vakjes in de legenda zijn knoppen: **"als hallucinatie eruit
gefilterd"** en **"overgeslagen stopwoord"**. Selecteer een woord en klik
erop om het zelf zo aan te merken - hallucinatie op de bovenste rij (wat
Whisper vond), stopwoord op de onderste (de songtekst). Het woord komt in
de lijst van de taal van dit lied, dus elk volgend lied in die taal heeft
er baat bij; nog eens klikken haalt het er weer af. De andere drie
markeringen zijn metingen en staan er alleen ter uitleg.

"Knippen" splitst het geselecteerde woord in tweeën, "Samenvoegen" plakt
het aan zijn rechterbuurman. Beide werken op de bovenste én de onderste
rij. Opslaan laat de zin-koppeling, de timing en de video vervallen;
knippen of samenvoegen in de songtekst laat ook de opgeslagen klemtonen
en handmatige regeltijden vervallen, want de woorden hernummeren.

### 2.1. Klemtoon bewerken

Klik de lettergreep die de klemtoon draagt; klik de gemarkeerde nog eens
om hem weg te halen. Eén klemtoon per woord. Naast de karaokeregels staan
de originele regels, zodat de klemtoon van de parodie op die van het
origineel gelegd kan worden. Opslaan verdeelt de best-effort regelduur
opnieuw op basis van de klemtonen.

### 2.3. Timing bewerken (golfvorm)

Vijf banen onder elkaar: de golfvorm van het **origineel**, de
**originele tekst**, de golfvorm van de **karaoke**, de
**karaokeregels** en de **zangstem**. Het origineel en de zangstem staan
op de karaoke-tijdlijn geprojecteerd, dus de pieken liggen recht boven
elkaar, ook bij tempoverschil.

- **Klikken in een golfvorm, op de tijdbalk of in de zangstembaan** zet
  de afspeellijn daar neer en laat een blijvend grijs streepje achter, om
  tegenaan te kunnen uitlijnen. Het afspelen blijft staan.
- **Slepen in het midden van een blok** verschuift de regel; het begin
  **snapt naar de afspeellijn** als die dichtbij is.
- **Slepen aan de rand** (de cursor wordt ↔) rekt of krimpt. Een regel
  wordt nooit korter dan 0,2 s en botst niet tegen een andere regel;
  crowd-regels mogen wel overlappen en over een uitgezette regel heen mag
  ook.
- Versleep je een **originele zin**, dan schuiven de karaokeregels die
  eraan gekoppeld zijn mee. Andersom werkt het ook: een karakoke-regel
  die 1-op-1 gekoppeld is, wordt in de originele baan meegespiegeld.
- **Weergave: Blokken / Zinnen / Woorden.** In *Blokken* sleep je een
  heel blok in één keer (de regels erin schalen mee), in *Zinnen* één
  regel; *Woorden* is alleen om te lezen, daar sleep je niet.
- **Regel uit/aan** zet de geselecteerde regel (of blok, of woord) uit:
  hij wordt grijs, krijgt "[uit]" ervoor en komt niet in de render. Weer
  aanzetten maakt zelf ruimte vrij bij de buren.
- **Herstel origineel-timing** gooit de handmatige correcties op de
  originele baan weg en bouwt de koppeling opnieuw op. Let op: dat zet
  ook de karaokeregels terug.
- **Opslaan (timing.json)** bewaart de regels plus alleen de gewijzigde
  originele zinnen. **Sluiten slaat niet op.**

### Demping bewerken

Bereikbaar vanaf tab 1 zodra "1.1. Detecteer woorden" heeft gelopen.
Rode blokken dempen een stuk karaoke; de groene blokken
(**"Terug uit origineel"**) doen het omgekeerde - daar wordt het
overeenkomstige stuk uit het origineel over de karaoke gelegd. Dat is bedoeld voor materiaal
dat Demucs heeft weggehaald terwijl het er hoorde te blijven. Klik in de
golfvorm om de afspeellijn te zetten, sleep een blok of zijn rand,
"Verwijderen" haalt het geselecteerde blok weg. "Opslaan en toepassen"
past alles toe en exporteert opnieuw; **Sluiten slaat niet op.**

## Wat voor liedjes werken goed?

Het gereedschap leunt op wat Whisper van de zangstem maakt. Eén stem die
verstaanbaar zingt levert de beste koppeling. Lastig worden liedjes met
een achtergrondkoor dat tegelijk iets ánders zingt, met veel korte
tussenroepsels achter elkaar, of met een outro waarin dezelfde regel zes
of zeven keer bijna hetzelfde herhaalt. Whisper schrijft daar vaak niets
op, of hij loopt vast en herhaalt één woord tientallen keren.

Je herkent het in de koppel-editor: veel woorden met het groenblauwe
kader (wel een tijd, niet gekoppeld) of het roze kader (geen match),
meestal aan het eind van het lied. De tool doet daar het juiste - hij
zet die regels op de zangenergie - maar de plaatsing is dan een
schatting, en de golfvorm-editor is je gereedschap. In zo'n staart kan
de fout bovendien oplopen: de regels worden tegen hun minimumduur aan
geperst en duwen elkaar vooruit, wat over een lange outro tot tien
seconden of meer kan worden. Het begin en het midden van het lied hebben
daar geen last van - die staan meestal op een fractie van een seconde.

Overlapt een tweede stem echt, dan help je hem met `[bg]` (zie
Tekstnotatie). Voor een strak gezongen lied met één stem hoef je meestal
niets te doen.

## Keuzes en instellingen

Instellingen gelden voor de hele app (niet per project), behalve de
titels en de artiest - die horen bij het lied en staan op tab 1.

- **Grote modellen (Demucs / forced alignment):** aanrader; zonder deze
  draait de transcriptie op de volledige mix en is de timing minder
  nauwkeurig. Vallen netjes terug als ze ontbreken. Aanvinken haalt het
  model meteen binnen, zodat de eerste echte run niet wacht.
- **Parallelle detectie:** origineel en karaoke tegelijk (sneller, meer
  geheugen; terugval op één-voor-één).
- **Zangstem-analyse (aangehouden noten + vulregels):** staat standaard
  aan. Gebruikt de gescheiden zangstem om aangehouden noten te verlengen,
  om "na-na"-regels die niet getranscribeerd zijn op hun energie-pulsen te
  zetten, en om songtekstwoorden die bij het exact matchen zijn
  overgeslagen alsnog een tijd te geven (die krijgen in de koppel-editor
  het groenblauwe kader), en om een geschat regelbegin op de zanginzet te
  leggen waar het bij hoort. Vereist Demucs; valt anders netjes terug.
- **Ritme van het lied:** waar een lied strak wordt gezongen, meet de tool
  zelf hoe lang een regel duurt (de frase) en hoe lang een herhaalde zin
  hoort te zijn. Zo blijft een refrein dat vier keer terugkomt overal even
  lang, ook op een plek waar Whisper de tekst niet heeft opgepikt. Bij een
  lied met een los ritme merkt de tool dat en laat hij het achterwege; je
  hoeft er niets voor in te stellen.
- **Diagnostiek (alleen lokaal):** schrijft transcriptie-historie en
  `timing_diagnostiek.txt` naar `output/<titel>/diagnostiek/`. Handig om
  problemen te analyseren; niets wordt verstuurd.
- **Cache:** "Cache wissen bij opstarten en afsluiten" staat standaard
  uit, en dat is met opzet - zonder transcriptie in de cache valt de
  timing terug op gelijkmatig verdelen. "Nu legen" leegt hem eenmalig,
  voor **alle** projecten.
- **Output-map:** waar de projectmappen komen te staan; ook een
  netwerklocatie (UNC) mag. Bij het wijzigen verhuizen bestaande
  projecten mee en worden de verwijzingen aangepast; invoer en cache
  blijven bij de app.
- **Interfacetaal:** Nederlands/Engels (los van de audiotaal, die uit de
  songtekst/karaoketekst wordt gedetecteerd). Werkt na herstarten.
- **Videotekst-kleuren en lettertype:** de kleur vóór, tijdens en na het
  zingen, de crowd-kleur en de video-achtergrond, plus het lettertype
  (`.ttf` uit `assets/fonts`, met een voorbeeldregel). Naast elke
  tekstkleur staat de kleur van de **omlijning**: een dunne rand om de
  letters van de regel die nu aan de beurt is, zodat de tekst afsteekt
  tegen een achtergrondfoto. Laat je die leeg, dan kiest de tool zelf de
  contrakleur (zwart onder een lichte letter, wit onder een donkere).
  "Terug naar standaard" zet kleuren, omlijningen én lettertype terug.
- **Achtergrondafbeelding:** staat onder Video-achtergrond en hoort bij
  het liedje. Een gekozen afbeelding wordt bewaard in een centrale
  verzameling (naast de instellingen, als `background_001`,
  `background_002`, ...) én als kopie in de invoermap van het project.
  Staat er iets in die verzameling, dan zie je de miniaturen: klik er
  een aan en druk op **Deze gebruiken** (of dubbelklik) om hem voor dit
  project te nemen, of op **Opgeslagen achtergrond wissen** om hem uit
  de verzameling te halen — projecten die hem gebruiken houden hun eigen
  kopie. **Afbeelding verwijderen** haalt de achtergrond uit dít
  project; staat er geen, dan zie je "Geen".
- **Interface-kleuren:** achtergrond, knoppen en de kleur van een knop
  die bezig is.
- **Uit origineel terughalen (2.3):** wijs in de timing-editor een zin
  aan met de knop **Uit origineel terughalen**. Die zin kleurt blauw in
  beide banen, en bij **1.4. Karaoke aanpassen** staat hij als blauw blok
  klaar: daar wordt op die tijd het geluid van het origineel 1-op-1 in de
  plaats van de karaoke gezet, met een korte in- en uitloop. Handig voor
  losse kreten die uit de karaokeversie zijn verdwenen. Verschuif je de
  zin later, dan schuift het stuk origineel mee.
- **Lettergrepen bijstellen (2.3):** verdeelt de lettergrepen bínnen elke
  zin opnieuw op de zangenergie, zonder de zinsgrenzen aan te raken.
  Bedoeld voor nadat je de zinnen zelf op hun plek hebt gezet.
- **Open video:** de knop naast "2.4. Video maken" kijkt in de uitvoermap van
  het project dat openstaat, dus ook een video van gisteren is gewoon te
  openen. Staan er meerdere versies, dan vraagt hij welke; de nieuwste
  (hoogste volgnummer) staat voorgeselecteerd.
- **Muziek bij het renderen:** in het render-venster kies je de muziek:
  **Karaoke-muziek** (de audio waartegen de uitlijning en timing gemaakt
  zijn — of die nu een losse karaoke is of uit het origineel komt maakt niet
  uit), **Originele muziek**, of **Alleen zang**. Daarnaast kies je daar
  welke **tekst** in beeld komt: de karaoketekst of de originele tekst.
- **Taal (fonetische timing):** de audiotaal wordt uit de songtekst
  gedetecteerd. Ontbreekt een taalmodel (bv. Frans voor een Frans nummer),
  dan zet de tool er zelf één neer. Nederlands, Engels en Frans zijn
  ingebouwd; andere talen worden automatisch aangemaakt.

## Wat werkt waarin door

Alles komt via een keten van tussenstappen uit vier bronbestanden: het
origineel, de karaokeversie, de songtekst en de karaoketekst. Verander je
iets aan het begin van zo'n keten, dan vervalt bijna alles daarna, en
meldt de app welke stappen opnieuw moeten. De volledige lijst staat in
`docs/afhankelijkheden.md`.

Twee koppelingen zijn niet vanzelfsprekend en verklaren de meeste
verrassingen:

- de **karaoketekst** stuurt via de vulwoord-prioriteit ook de
  woordkoppeling van de songtekst, en dus de regeltijden;
- de **songtekst** gaat als beginprompt mee naar Whisper en zit daarmee
  in de cachesleutel: het bestand vervangen kan een volledige
  hertranscriptie afdwingen. Een correctie in de koppel-editor doet dat
  bewust *niet*.

Wat juist níet vervalt is net zo belangrijk: de parodietekst wijzigen
raakt de transcriptie en je handmatige woordkoppelingen niet, een ander
beeldmerk maakt alleen de video oud, en de gerenderde video wordt nooit
automatisch weggegooid.

## Diagnostiek gebruiken

Loopt de timing ergens mis, kijk dan in
`output/<titel>/diagnostiek/timing_diagnostiek.txt`: één regel per zin
met begin/eind/duur/aantal-lettergrepen/kwaliteit en automatische
markeringen (te kort, overlap). De bovenste regel toont de app-versie en
de gebruikte offset. `transcriptie_<track>.json` bewaart per detectie een
run met tijdstempel, zodat zichtbaar is óf en wanneer een stap opnieuw is
gedaan. Is er een taal on-the-go aangemaakt, dan staat die als
`<code>.json` (met header en build-versie) in dezelfde diagnostiekmap, zodat
je de hele map in één keer kunt opsturen.
