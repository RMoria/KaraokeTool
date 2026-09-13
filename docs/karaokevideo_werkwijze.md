# Standaardwerkwijze karaokevideo (v1) - RoodWitte Zangers

Vaste standaard voor alle TVX-karaokevideo's. De videoproductie staat
los van de audio-analyse/karaokebewerking, maar gebruikt dezelfde
projectgegevens (offset, songtekst, karaoketekst).

## Werkvolgorde

1. **Liedtekst eerst volledig afronden.** Complete tekst schrijven,
   daarna pas timing. Geen timing aanpassen terwijl de tekst nog
   verandert; tekst daarna als "voorlopig definitief" behandelen.
2. **Audio analyseren**: officiële opname + karaokeversie. Waveform,
   zanginzetten, instrumentale cues, verschillen. Vaste offset zoeken;
   niet aannemen dat overal hetzelfde tijdsverschil zit.
3. **Sectie-ankers**: elke grote sectie (intro, couplet 1, opbouw,
   refrein, crowd, couplet 2, ...) een eigen, volledig onafhankelijk
   anker. Nooit latere timing afleiden uit eerdere; geen
   opeengestapelde timingpatches.
4. **Zang analyseren** op lettergrepen, woordklemtonen, lange noten,
   ademmomenten, natuurlijke uitspraak. Bij twijfel: controle tegen
   officiële zang en karaoke.
5. **Timing per lettergreep** (niet per woord): iedere lettergreep een
   begintijd en eind/hold-tijd. Kleur verandert exact op de inzet.
6. **Lange lettergrepen**: onderstreping via een aparte renderoptie
   (geen rekletters). Voorbeeld: `Groe̲n`, `Éé̲n`, `Laa̲t`.
7. **Crowd-cues** (`La-la-la...`, `Hey...`, `Ho...`) apart behandelen:
   wit -> rood -> grijs. Geen groen.
8. **Kleurverloop** normale zang: wit -> groen (op zanginzet) -> grijs.
9. **Logische tekstregels**: altijd complete zinnen, nooit willekeurig
   afbreken. Regel 2 alvast tonen terwijl regel 1 gezongen wordt.
10. **Intro**: alleen logo, geen tekst, minimaal 5 seconden.
11. **Eerste tekst**: eerste regel verschijnt 5 s vóór de eerste zang.
12. **Outro**: laatste regel minimaal 3 s laten staan, daarna logo +
    liedtitel minimaal 5 s (zoals bij Zangers Paradijs). Muziek te
    kort? Stille videotijd toevoegen.
13. **Renderarchitectuur**: lyrics, timing, kleurregels en render zijn
    vier aparte onderdelen. Nooit timing in de rendercode. De renderer
    is generiek, zonder liedspecifieke uitzonderingen: per lied
    vervang je alleen logo, audio en timingbestand.
14. **Eerste render**: eerst een volledige render, daarna pas zang
    controleren, timing finetunen, lettergreepverschuivingen
    corrigeren.
15. **Eindformaat**: video H.264 + yuv420p, audio AAC
    (Windows-compatibel).

## Opbouw van de tekst in beeld

- Intro: alleen logo, rustig, >= 5 s.
- Tijdens de zang altijd maximaal twee regels:
  - **Regel 1** (actief): wit -> groen per lettergreep -> grijs.
  - **Regel 2** (volgende logische zin): alvast volledig wit.
  - Regel 1 klaar -> regel 2 schuift omhoog, nieuwe regel onderaan.
- Regels verschijnen ~5 s vóór de zang en blijven ~3 s staan.
- Crowd: actieve regel wit -> rood -> grijs; volgende regel wit klaar.
- Outro: laatste regel >= 3 s, dan logo + songtitel >= 5 s.

Lay-out:

    ────────────────────────────
               (logo)

    Actieve regel   (wit -> groen -> grijs)
    Volgende regel  (wit)
    ────────────────────────────

## Notatie karaoketekst

- Eén logische zin per regel (nooit willekeurig afbreken).
- Lege regels scheiden secties.
- `# commentaar` (bv. `# Intro`, `# Couplet 2`): niet gezongen,
  niet getoond.
- Crowd-stukken tussen blokmarkeringen (of inline midden in een
  regel: `[crowd]Waertje![/crowd]` wordt een eigen crowd-regel); die
  kleuren wit -> rood -> grijs:

      [crowd]
      La-la-la...
      Hey...
      [/crowd]

## Vereiste invoer (pas renderen als alles aanwezig is)

- originele songtekst
- karaoketekst (bv. Per_Spoor_RoodWitte_Zangers_Werkversie.txt)
- timinginformatie op lettergreepniveau
- offset origineel/karaoke (uit stap 3 van de audiopijplijn)
- logo (via zoekknop te kiezen, gekopieerd naar input\logo.<ext>)
- songtitel; bij bekende titel krijgen input en output een submap met
  de songtitel waarin alle aanwezige bestanden worden geplaatst, en
  die submap wordt verder in het hele programma gebruikt (per lied een
  eigen projectmap; de hoofdmappen blijven klaar voor volgend gebruik)

Ontbreekt er iets, dan meldt het programma wát er mist en begint het
niet aan de render.

## Status implementatie (v0.25: 3 regels, crowd extra, logo+titel intro/outro, mp4 opent na render)

Werkend sinds v0.15: `modules/timing.py` (lettergrepen, timing.json)
en `modules/video.py` (generieke renderer). Videoresolutie/fps/font in
`config.json` onder `video`. Uitvoer: `output/<lied>/karaoke_video.mp4`,
met de bewerkte karaoke (`karaoke_edit`) als die bestaat, anders de
kale karaoke. Werkvolgorde: "2.2. Timing verfijnen" koppelt de karaoketekst
structureel aan de songtekst op sectieniveau (blok voor blok: refrein
op refrein, couplet op couplet), met interpolatie voor refreinen die
Whisper verhaspelde. De kleur toont het koppelvertrouwen (groen=hoog,
geel=midden, rood=laag). Zonder songtekst is het een best-effort (via de songtekst-uitlijning: lettergreep- -> woord- ->
zinsniveau; anders gelijkmatig verdeeld), daarna eerste render maken
en finetunen met "2.3. Timing bewerken (golfvorm)": golfvormen van
origineel én karaoke met zoom, afspelen van beide bronnen (offset
wordt verrekend), een doorlopende afspeellijn over alle banen (klik in
de golfvorm om daar af te spelen), regels verschuiven (midden slepen)
of oprekken (rand slepen) waarbij het regelbegin naar de afspeellijn
snapt, opslaan schrijft `timing.json`. Is de originele songtekst
aanwezig, dan toont de editor de originele zinnen als eigen baan onder
de origineel-golfvorm (op zinsniveau gekoppeld aan de karaokezinnen);
de originele zin is makkelijk tegen de originele muziek te leggen, en
verschuiven of oprekken ervan beweegt de gekoppelde karaokezin(nen)
relatief mee.
