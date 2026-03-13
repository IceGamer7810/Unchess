# Unchess

Az Unchess egy Pythonban írt sakk-prototípus `tkinter` GUI-val, amely a klasszikus sakk egyik alapfeltevését fordítja meg: a játékosok nem a saját, hanem az ellenfél bábuit mozgatják.

## Miről szól a játék?

A szerepek és a célok ugyanazok maradnak, mint sakkban:

- a fehér játékos a fehérrel van
- a fekete játékos a feketével van
- a cél az ellenfél királyának mattot adni

A csavar az, hogy:

- amikor fehér van soron, a fekete játékos lép a fehér bábukkal
- amikor fekete van soron, a fehér játékos lép a fekete bábukkal

Vagyis a soron következő szín bábui mozognak, de mindig a másik játékos kattint rájuk.

## Alapszabályok

- A bábu-mozgások a normál sakk szabályait követik.
- A saját színű bábu leütése nem szabályos.
- A sakkot kötelező megszüntetni.
- A királyok nem állhatnak egymás mellett.
- Gyalogátváltozás van.

## Pontozás

A matt mellett pontozás is van. Minden leütött bábu pontot ér.

- gyalog: 1 pont
- huszár: 3 pont
- futó: 3 pont
- bástya: 5 pont
- vezér: 9 pont

A pont mindig annak a játékosnak jár, akinek a színe ütött, függetlenül attól, hogy fizikailag ki kattintott a lépésre.

Ez azért fontos, mert az Unchess taktikai lényege sokszor nem a közvetlen támadás, hanem az, hogy az ellenfelet kellemetlen, kényszerített válaszokra vidd rá.

## Az Unchess lényege

A játék központi ötlete a manipulált kényszerhelyzet.

Tipikus helyzet:

1. Olyan lépést teszel az ellenfél bábujával, amely sakkhelyzetet vagy más kényszerhelyzetet hoz létre.
2. Az ellenfélnek erre kötelező reagálnia.
3. Mivel ő sem a saját bábuit mozgatja, gyakran rossz, pontot adó vagy pozíciót rontó válaszok maradnak neki.

Az erős játék tehát nem abból áll, hogy „összevissza támadsz”, hanem abból, hogy olyan állást építesz, ahol az ellenfél kötelező válasza neked kedvez.

## Játékvégi feltételek

A játszma kétféleképpen érhet véget:

- mattal
- lépéslimittel

Ha a lépéslimit letelik matt nélkül, a pontszám dönt.

## Jelenlegi funkciók

A jelenlegi prototípus tudja:

- a teljes grafikus sakktáblát `Canvas` alapon
- a Unicode sakkfigurák megjelenítését
- kattintásos bábu-kiválasztást
- szabályos lépések kiemelését
- animált lépésvégrehajtást
- sakkhelyzet vizuális kiemelését
- pontszámolást
- gyalogátváltozást
- undo / redo funkciót
- bot elleni játékot több nehézségi szinttel
- multiplayer alapot külön szerverrel

## Játékmódok

### Singleplayer

Helyi prototípus egy gépen, egy egérrel, két játékossal.

### Bot

Bot elleni mód több nehézséggel:

- Könnyű
- Normál
- Nehéz
- Verhetetlen

A bot mód előtt választható, hogy a játékos:

- Fehér
- Fekete
- Random

A botnál van automatikus szerepbeállítás is a beállításokban.

### Multiplayer

A multiplayerhez külön szerver tartozik.

Jelenlegi állapot:

- szoba létrehozás működik
- meglévő szobához csatlakozás működik
- lobby és szerepválasztási flow működik
- a szerver szoba- és kapcsolatkezelése működik

Ez még fejlesztés alatt álló rész, de már nem csak üres placeholder.

## Kezelés

- Kattints egy mozgatható bábra.
- A program kiemeli a szabályos célmezőket.
- Kattints a célmezőre.
- A bábu animációval átcsúszik az új helyére.

Az oldalsó panel mutatja:

- ki van soron
- melyik szín mozog
- a pontszámot
- a lépésszámot

## Beállítások

A főmenüben és a kapcsolódó képernyőkön van egy fogaskerék ikon.

Jelenleg egy beállítás érhető el:

- automatikus szerepválasztási policy
- bot tempó

Értékei:

- Mindig kérdezzen
- Mindig Fehér
- Mindig Fekete
- Mindig Random

Ez jelenleg a bot módra és a multiplayer host szerepválasztására is hat.

A bot tempó értékei:

- Lassú
- Normál
- Gyors
- Instant

Ez a botlépések közti mesterséges várakozást szabályozza, főleg bot elleni és bot vs bot módban.

## Fájlok

- `app.py`: kliens, GUI, játéklogika, bot, menük
- `server.py`: multiplayer szerveralap
- `start_server.bat`: kényelmi indító a szerverhez
- `README.md`: projektleírás

## Futtatás

Kliens indítása:

```powershell
python app.py
```

Szerver indítása:

```powershell
python server.py
```
