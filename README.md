# Unchess Client

Az Unchess egy `tkinter`-es, fordított irányítású sakkjáték. A tábla és a bábumozgás sakk, de mindig az ellenfél bábuit mozgatod.

## Alapötlet

- A fehér játékos a fehérrel van, a fekete játékos a feketével.
- Amikor `white` van soron, a fekete játékos lép a fehér bábukkal.
- Amikor `black` van soron, a fehér játékos lép a fekete bábukkal.
- A pont annak jár, akinek a színe ütött, nem annak, aki fizikailag kattintott.

Az Unchess lényege a kényszerhelyzetek felépítése: saját királyodnak menekülőhálót akarsz hagyni, az ellenfél királyát pedig úgy akarod szorítani, hogy rossz válaszokra kényszerüljön.

## Jelenlegi funkciók

- teljes grafikus tábla `Canvas`-szal
- Unicode sakkfigurák
- animált lépések
- sakkvizualizáció és kijelölés
- pontozás
- gyalogátalakulás
- undo / redo
- bot mód
- bot vs bot mód
- dedikált szerveres TCP multiplayer
- multiplayer account rendszer:
  - regisztráció
  - login
  - logout
  - maradjak bejelentkezve
  - mesterkulcsos jelszó-reset kliensfolyam
- multiplayer report gomb
- admin accounttal közvetlen ban gomb multiplayer meccs közben
- átméretezhető ablak, skálázódó játéktér

## Játékmódok

- `Singleplayer`
- `Bot`
- `Bot vs Bot`
- `Multiplayer`

Multiplayerben a kliens dedikált szerverhez csatlakozik. A meccs létrehozása és a csatlakozás után a szerver kezeli a szobát, a szerepkiosztást és a multiplayer állapotot.

## Beállítások

A fogaskerék alatti panelből állítható:

- automatikus szerepválasztási policy
- bot tempó
- alap lépéslimit
- multiplayer szerver host
- multiplayer szerver port

Ezek a kliensoldali `settings.toml` fájlba mentődnek.

Az új meccsek indítása előtt külön is megadható lépéslimit. A mező alapértéke a settingsben elmentett értékből jön.

## Konfiguráció

Fájl: `settings.toml`

Példa:

```toml
[client]
server_host = "127.0.0.1"
server_port = 7777

[auth]
user_name = ""
remember_token = ""

[gameplay]
auto_role_policy = "ask"
bot_tempo = "normal"
move_limit = -1
```

Ha hiányzik, a kliens automatikusan létrehozza. A fájl `.gitignore` alatt van.

## Fájlok

- `app.py`: kliens, GUI, helyi játékmotor, botok, multiplayer kliens
- `settings.toml`: helyi kliensbeállítások

## Futtatás

```powershell
python app.py
```

Multiplayerhez a `settings.toml`-ban megadott hoston és porton futó dedikált szerver kell.
