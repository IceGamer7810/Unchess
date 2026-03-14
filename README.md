# Unchess

Az Unchess egy Pythonos, `tkinter`-es sakkprototípus, ahol a tábla és a bábumozgás sakk, de a vezérlés fordított: mindig az ellenfél bábuit mozgatod.

## Alapötlet

- A fehér játékos a fehérrel van, a fekete játékos a feketével.
- A cél továbbra is az ellenfél királyának mattot adni.
- Amikor `white` van soron, a fekete játékos lép a fehér bábukkal.
- Amikor `black` van soron, a fehér játékos lép a fekete bábukkal.

Az Unchess lényege nem a sima támadás, hanem a kényszerhelyzet-manipuláció: olyan állásokat kell építeni, ahol az ellenfél rossz válaszokra kényszerül.

## Pontozás

Minden leütött bábu pontot ér:

- gyalog: 1
- huszár: 3
- futó: 3
- bástya: 5
- vezér: 9

A pont annak a játékosnak jár, akinek a színe ütött, nem annak, aki fizikailag kattintott.

## Jelenlegi funkciók

- teljes grafikus tábla `Canvas`-szal
- Unicode sakkfigurák
- kattintásos kijelölés és lépéskiemelés
- animált lépés
- sakkvizualizáció
- pontszámolás
- gyalogátalakulás
- undo / redo
- bot mód
- bot vs bot mód
- helyi hálós / TCP-s multiplayer alap külön szerverrel
- átméretezhető ablak, skálázódó játéktér

## Játékmódok

### Singleplayer

Két helyi játékos egy gépen.

### Bot

Nehézségek:

- Könnyű
- Normál
- Nehéz
- Verhetetlen

Indulás előtt választható:

- Fehér
- Fekete
- Random

### Bot vs Bot

Mindkét oldalhoz külön nehézség választható. Van `Pause / Resume`, és spectator nézetben fut.

### Multiplayer

Jelenleg tudja:

- szoba létrehozása
- meglévő szobához csatlakozás
- lobby
- host oldali szerepválasztás
- lépésküldés TCP kapcsolaton
- kilépés kezelése

Ha az egyik fél meccs közben kilép, a másik győzelmet kap, a szoba bezárul.

## Beállítások

A fogaskerék alatti panelből állítható:

- automatikus szerepválasztási policy
- bot tempó
- alap lépéslimit
- multiplayer szerver host
- multiplayer szerver port

Ezek a kliens oldali `.settings.toml` fájlba mentődnek.

Minden új meccs indulása előtt külön megadható a lépéslimit is. Az ott látható mező alapértékét a settingsben elmentett alap lépéslimit adja.

## Konfiguráció

### Kliens

Fájl: `.settings.toml`

Példa:

```toml
[client]
server_host = "127.0.0.1"
server_port = 7777

[gameplay]
auto_role_policy = "ask"
bot_tempo = "normal"
move_limit = -1
```

### Szerver

Fájl: `.server.toml`

Példa:

```toml
[server]
host = "0.0.0.0"
port = 7777
```

Mindkét fájl automatikusan létrejön, ha hiányzik. Ezek a fájlok `.gitignore` alatt vannak.

## Fájlok

- `app.py`: kliens, GUI, játékmotor, botok
- `server.py`: multiplayer TCP szerver
- `.settings.toml`: kliens beállítások
- `.server.toml`: szerver bind beállítások

## Futtatás

Kliens:

```powershell
python app.py
```

Szerver:

```powershell
python server.py
```
