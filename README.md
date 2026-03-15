# Unchess Client

`Unchess` is a `tkinter` reverse-control chess game. The board and piece movement follow chess rules, but you always move the side-to-move pieces for the other player.

## Core idea

- White owns the white pieces, black owns the black pieces.
- When `white` is to move, the black player clicks the white pieces.
- When `black` is to move, the white player clicks the black pieces.
- Points belong to the owner of the capturing piece, not the person physically clicking.

The game is about building forced responses: keep escape routes for your own king while pushing the opponent into worse and worse answers.

## Current features

- local singleplayer
- local bot mode
- local bot-vs-bot mode
- dedicated TCP multiplayer
- scalable window and board canvas
- animated moves
- check visualization
- scoring
- pawn promotion
- undo / redo
- settings overlay panel
- scrollable menu-style screens for smaller windows
- startup account prompt with guest flow and "don't remind me again"
- top-right profile panel with cached stats
- live language switching for menus and the active game view
- multiplayer account flow:
  - register
  - login
  - logout
  - stay signed in
  - delete account
- per-account stat categories:
  - `multiplayer`: authoritative server-tracked wins / losses / draws / points
  - `bot`: client-reported local bot results stored separately
- role-aware multiplayer UI:
  - `player`: normal room creation / joining and reporting
  - `admin`: player UI plus active room list, spectating, and direct bans
  - `console`: server/account management UI after logging in with the console username and master key
- console UI:
  - player list
  - live search
  - account detail view
  - password reset
  - account deletion
  - ban / unban
  - grant / remove admin
  - grant / revoke report permission

## Game modes

- `Singleplayer`
- `Bot`
- `Bot vs Bot`
- `Multiplayer`

Multiplayer connects to the dedicated server. Room creation, joining, role selection, and move synchronization are all server-backed.
Admins can inspect active matches through a spectator view. Console sessions are separated from match supervision and are reserved for account/server operations.
On startup the client can prompt for account login, registration, or guest mode. Guest mode still works for local play, but multiplayer requires a server-confirmed account session.

## Reporting and stats

- players can report an opponent once per active multiplayer match
- duplicate same-match reports are rejected with a normal UI message
- local bot results are stored separately from multiplayer results
- multiplayer stats are server-authoritative
- bot stats are client-reported and therefore less trustworthy than multiplayer stats

## Settings

The gear panel lets you configure:

- language
- auto role policy
- bot tempo
- default move limit
- multiplayer host
- multiplayer port

These values are stored in `settings.toml`.

For new installs, the client detects the system language and defaults to:

- `hu` for Hungarian locales
- `en` otherwise

Each new match can still override the move limit before start. The settings value is only the default prefilled value.

## Config

File: `settings.toml`

Example:

```toml
[client]
server_host = "127.0.0.1"
server_port = 7777

[auth]
user_name = ""
remember_token = ""
session_role = ""
suppress_auth_prompt = false

[gameplay]
auto_role_policy = "ask"
bot_tempo = "normal"
move_limit = -1

[ui]
language = "en"

[stats.multiplayer]
wins = 0
losses = 0
draws = 0
points = 0

[stats.bot]
wins = 0
losses = 0
draws = 0
points = 0
```

If the file does not exist, the client creates it automatically. It is gitignored.

## Files

- `app.py`: GUI, local game logic, bots, multiplayer client
- `settings.toml`: local client settings

## Run

```powershell
python app.py
```

Multiplayer requires a running dedicated server on the host and port configured in `settings.toml`.
