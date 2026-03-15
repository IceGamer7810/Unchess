import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from concurrent.futures import ProcessPoolExecutor
import json
import locale
import math
import os
from pathlib import Path
import random
import socket
import threading
import queue
import time
import tomllib


BOARD_SIZE = 8
SQUARE_SIZE = 84
BOARD_PIXELS = BOARD_SIZE * SQUARE_SIZE
SIDEBAR_WIDTH = 260
WINDOW_WIDTH = BOARD_PIXELS + SIDEBAR_WIDTH
WINDOW_HEIGHT = BOARD_PIXELS + 70
MIN_WINDOW_WIDTH = 640
MIN_WINDOW_HEIGHT = 420
MIN_BOARD_SQUARE_PIXELS = 12
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 7777
BASE_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = BASE_DIR / "settings.toml"

LIGHT_SQUARE = "#f0d9b5"
DARK_SQUARE = "#b58863"
SELECT_COLOR = "#f4d35e"
MOVE_COLOR = "#3a7d44"
CAPTURE_COLOR = "#c0392b"
CHECK_COLOR = "#d62828"
TEXT_COLOR = "#1f1f1f"
BG_COLOR = "#f6f1eb"
CHECK_PATH_COLOR = "#f6b5c0"
CHECK_TEXT_COLOR = "#9d0208"

INITIAL_BOARD = [
    ["r", "n", "b", "q", "k", "b", "n", "r"],
    ["p", "p", "p", "p", "p", "p", "p", "p"],
    ["", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
    ["P", "P", "P", "P", "P", "P", "P", "P"],
    ["R", "N", "B", "Q", "K", "B", "N", "R"],
]

PIECE_SYMBOLS = {
    "P": "♙",
    "R": "♖",
    "N": "♘",
    "B": "♗",
    "Q": "♕",
    "K": "♔",
    "p": "♟",
    "r": "♜",
    "n": "♞",
    "b": "♝",
    "q": "♛",
    "k": "♚",
}

PIECE_VALUES = {
    "p": 1,
    "n": 3,
    "b": 3,
    "r": 5,
    "q": 9,
}


def deep_copy_board(board):
    return [row[:] for row in board]


def in_bounds(row, col):
    return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE


def piece_color(piece):
    if not piece:
        return ""
    return "white" if piece.isupper() else "black"


def opposite(color):
    return "black" if color == "white" else "white"


def detect_default_language():
    try:
        system_locale = locale.getlocale()[0] or locale.getdefaultlocale()[0]
    except Exception:
        system_locale = None
    system_locale = (system_locale or "").lower()
    return "hu" if system_locale.startswith("hu") else "en"


def blank_stat_bucket():
    return {"wins": 0, "losses": 0, "draws": 0, "points": 0}


def default_profile_stats():
    return {"multiplayer": blank_stat_bucket(), "bot": blank_stat_bucket()}


def normalize_profile_stats(stats):
    normalized = default_profile_stats()
    if not isinstance(stats, dict):
        return normalized
    for bucket in ("multiplayer", "bot"):
        raw_bucket = stats.get(bucket, {})
        if not isinstance(raw_bucket, dict):
            continue
        for key in ("wins", "losses", "draws", "points"):
            try:
                normalized[bucket][key] = int(raw_bucket.get(key, 0) or 0)
            except (TypeError, ValueError):
                normalized[bucket][key] = 0
    return normalized


def write_client_settings(settings):
    multiplayer_stats = normalize_profile_stats(settings["profile_stats"])["multiplayer"]
    bot_stats = normalize_profile_stats(settings["profile_stats"])["bot"]
    content = (
        "[client]\n"
        f'server_host = "{settings["server_host"]}"\n'
        f"server_port = {int(settings['server_port'])}\n\n"
        "[auth]\n"
        f'user_name = "{settings["user_name"]}"\n'
        f'session_role = "{settings["session_role"]}"\n'
        f'remember_token = "{settings["remember_token"]}"\n'
        f"suppress_auth_prompt = {'true' if settings['suppress_auth_prompt'] else 'false'}\n\n"
        "[gameplay]\n"
        f'auto_role_policy = "{settings["auto_role_policy"]}"\n'
        f'bot_tempo = "{settings["bot_tempo"]}"\n'
        f"move_limit = {int(settings['move_limit'])}\n\n"
        "[ui]\n"
        f'language = "{settings["language"]}"\n\n'
        "[stats.multiplayer]\n"
        f"wins = {multiplayer_stats['wins']}\n"
        f"losses = {multiplayer_stats['losses']}\n"
        f"draws = {multiplayer_stats['draws']}\n"
        f"points = {multiplayer_stats['points']}\n\n"
        "[stats.bot]\n"
        f"wins = {bot_stats['wins']}\n"
        f"losses = {bot_stats['losses']}\n"
        f"draws = {bot_stats['draws']}\n"
        f"points = {bot_stats['points']}\n"
    )
    SETTINGS_PATH.write_text(content, encoding="utf-8")


def load_client_settings():
    defaults = {
        "server_host": DEFAULT_SERVER_HOST,
        "server_port": DEFAULT_SERVER_PORT,
        "user_name": "",
        "session_role": "",
        "remember_token": "",
        "suppress_auth_prompt": False,
        "auto_role_policy": "ask",
        "bot_tempo": "normal",
        "move_limit": -1,
        "language": detect_default_language(),
        "profile_stats": default_profile_stats(),
    }
    if not SETTINGS_PATH.exists():
        write_client_settings(defaults)
        return defaults.copy()

    settings = defaults.copy()
    try:
        data = tomllib.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        write_client_settings(defaults)
        return defaults.copy()

    client = data.get("client", {})
    auth = data.get("auth", {})
    gameplay = data.get("gameplay", {})
    ui = data.get("ui", {})
    settings["server_host"] = str(client.get("server_host", defaults["server_host"]))
    try:
        settings["server_port"] = int(client.get("server_port", defaults["server_port"]))
    except (TypeError, ValueError):
        settings["server_port"] = defaults["server_port"]
    settings["user_name"] = str(auth.get("user_name", defaults["user_name"]))
    settings["session_role"] = str(auth.get("session_role", defaults["session_role"])).lower()
    settings["remember_token"] = str(auth.get("remember_token", defaults["remember_token"]))
    settings["suppress_auth_prompt"] = bool(auth.get("suppress_auth_prompt", defaults["suppress_auth_prompt"]))
    if settings["session_role"] not in {"", "player", "admin", "console"}:
        settings["session_role"] = ""
    settings["auto_role_policy"] = str(gameplay.get("auto_role_policy", defaults["auto_role_policy"]))
    settings["bot_tempo"] = str(gameplay.get("bot_tempo", defaults["bot_tempo"]))
    try:
        settings["move_limit"] = int(gameplay.get("move_limit", defaults["move_limit"]))
    except (TypeError, ValueError):
        settings["move_limit"] = defaults["move_limit"]
    settings["language"] = str(ui.get("language", defaults["language"])).lower()
    if settings["language"] not in {"hu", "en"}:
        settings["language"] = defaults["language"]
    settings["profile_stats"] = normalize_profile_stats(data.get("stats", defaults["profile_stats"]))
    write_client_settings(settings)
    return settings


class SearchGameAdapter:
    def __init__(self, state):
        self.board = deep_copy_board(state["board"])
        self.side_to_move = state["side_to_move"]
        self.score_white = state["score_white"]
        self.score_black = state["score_black"]
        self.state_history = state["state_history"][:]
        self.move_history = state["move_history"][:]
        self.last_executed_move = state["last_executed_move"]

    def all_legal_moves(self, board, color):
        moves = []
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                piece = board[row][col]
                if piece and piece_color(piece) == color:
                    for move in self.generate_pseudo_moves(board, row, col):
                        next_board = self.simulate_move(board, move)
                        if not self.is_in_check(next_board, color):
                            moves.append(move)
        return moves

    def apply_move_state(self, board, side_to_move, score_white, score_black, move):
        next_board = self.simulate_move(board, move)
        next_white = score_white
        next_black = score_black
        if move["captured"]:
            points = PIECE_VALUES.get(move["captured"].lower(), 0)
            if side_to_move == "white":
                next_white += points
            else:
                next_black += points
        return next_board, opposite(side_to_move), next_white, next_black

    def repetition_key(self, board, side_to_move):
        return tuple(tuple(row) for row in board), side_to_move

    def generate_pseudo_moves(self, board, row, col):
        piece = board[row][col]
        if not piece:
            return []
        lower = piece.lower()
        if lower == "p":
            return self.generate_pawn_moves(board, row, col, piece)
        if lower == "n":
            return self.generate_knight_moves(board, row, col, piece)
        if lower == "b":
            return self.generate_sliding_moves(board, row, col, piece, [(-1, -1), (-1, 1), (1, -1), (1, 1)])
        if lower == "r":
            return self.generate_sliding_moves(board, row, col, piece, [(-1, 0), (1, 0), (0, -1), (0, 1)])
        if lower == "q":
            return self.generate_sliding_moves(
                board,
                row,
                col,
                piece,
                [(-1, -1), (-1, 1), (1, -1), (1, 1), (-1, 0), (1, 0), (0, -1), (0, 1)],
            )
        if lower == "k":
            return self.generate_king_moves(board, row, col, piece)
        return []

    def generate_pawn_moves(self, board, row, col, piece):
        moves = []
        direction = -1 if piece.isupper() else 1
        start_row = 6 if piece.isupper() else 1
        one_forward = row + direction
        if in_bounds(one_forward, col) and board[one_forward][col] == "":
            moves.append(self.make_move_dict(board, row, col, one_forward, col))
            two_forward = row + 2 * direction
            if row == start_row and in_bounds(two_forward, col) and board[two_forward][col] == "":
                moves.append(self.make_move_dict(board, row, col, two_forward, col))
        for dc in (-1, 1):
            target_row = row + direction
            target_col = col + dc
            if not in_bounds(target_row, target_col):
                continue
            target_piece = board[target_row][target_col]
            if target_piece and piece_color(target_piece) != piece_color(piece) and target_piece.lower() != "k":
                moves.append(self.make_move_dict(board, row, col, target_row, target_col))
        return moves

    def generate_knight_moves(self, board, row, col, piece):
        moves = []
        for dr, dc in [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]:
            nr = row + dr
            nc = col + dc
            if not in_bounds(nr, nc):
                continue
            target_piece = board[nr][nc]
            if target_piece and target_piece.lower() == "k":
                continue
            if target_piece and piece_color(target_piece) == piece_color(piece):
                continue
            moves.append(self.make_move_dict(board, row, col, nr, nc))
        return moves

    def generate_sliding_moves(self, board, row, col, piece, directions):
        moves = []
        for dr, dc in directions:
            nr = row + dr
            nc = col + dc
            while in_bounds(nr, nc):
                target_piece = board[nr][nc]
                if target_piece == "":
                    moves.append(self.make_move_dict(board, row, col, nr, nc))
                else:
                    if piece_color(target_piece) != piece_color(piece) and target_piece.lower() != "k":
                        moves.append(self.make_move_dict(board, row, col, nr, nc))
                    break
                nr += dr
                nc += dc
        return moves

    def generate_king_moves(self, board, row, col, piece):
        moves = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr = row + dr
                nc = col + dc
                if not in_bounds(nr, nc):
                    continue
                target_piece = board[nr][nc]
                if target_piece and target_piece.lower() == "k":
                    continue
                if target_piece and piece_color(target_piece) == piece_color(piece):
                    continue
                moves.append(self.make_move_dict(board, row, col, nr, nc))
        return moves

    def make_move_dict(self, board, from_row, from_col, to_row, to_col):
        piece = board[from_row][from_col]
        target = board[to_row][to_col]
        promotion = None
        if piece.lower() == "p" and (to_row == 0 or to_row == BOARD_SIZE - 1):
            promotion = "Q" if piece.isupper() else "q"
        return {
            "from": (from_row, from_col),
            "to": (to_row, to_col),
            "piece": piece,
            "captured": target,
            "promotion": promotion,
        }

    def simulate_move(self, board, move):
        next_board = deep_copy_board(board)
        from_row, from_col = move["from"]
        to_row, to_col = move["to"]
        moving_piece = next_board[from_row][from_col]
        next_board[from_row][from_col] = ""
        if move["promotion"]:
            moving_piece = move["promotion"]
        next_board[to_row][to_col] = moving_piece
        return next_board

    def find_king(self, board, color):
        target = "K" if color == "white" else "k"
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                if board[row][col] == target:
                    return (row, col)
        return None

    def is_in_check(self, board, color):
        return bool(self.find_checkers(board, color))

    def find_checkers(self, board, color):
        king_pos = self.find_king(board, color)
        if king_pos is None:
            return []
        enemy_color = opposite(color)
        checkers = []
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                piece = board[row][col]
                if piece and piece_color(piece) == enemy_color:
                    if self.piece_attacks_square(board, row, col, king_pos[0], king_pos[1]):
                        checkers.append({"row": row, "col": col, "piece": piece})
        return checkers

    def piece_attacks_square(self, board, from_row, from_col, target_row, target_col):
        piece = board[from_row][from_col]
        if not piece:
            return False
        lower = piece.lower()
        dr = target_row - from_row
        dc = target_col - from_col
        if lower == "p":
            direction = -1 if piece.isupper() else 1
            return dr == direction and abs(dc) == 1
        if lower == "n":
            return (abs(dr), abs(dc)) in {(1, 2), (2, 1)}
        if lower == "k":
            return max(abs(dr), abs(dc)) == 1
        if lower in {"b", "r", "q"}:
            step_row = 0
            step_col = 0
            if lower in {"b", "q"} and abs(dr) == abs(dc) and dr != 0:
                step_row = 1 if dr > 0 else -1
                step_col = 1 if dc > 0 else -1
            elif lower in {"r", "q"} and (dr == 0) != (dc == 0):
                step_row = 0 if dr == 0 else (1 if dr > 0 else -1)
                step_col = 0 if dc == 0 else (1 if dc > 0 else -1)
            else:
                return False
            row = from_row + step_row
            col = from_col + step_col
            while (row, col) != (target_row, target_col):
                if board[row][col] != "":
                    return False
                row += step_row
                col += step_col
            return True
        return False


def evaluate_root_move_parallel(payload):
    state = payload["state"]
    move = payload["move"]
    depth = payload["depth"]
    strategy_name = payload["strategy_name"]
    bot_color = payload["bot_color"]
    difficulty = payload["difficulty"]
    node_limit = payload["node_limit"]
    time_limit_ms = payload["time_limit_ms"]

    game = SearchGameAdapter(state)
    engine = BotEngine(game, bot_color, difficulty)
    engine.nodes = 0
    engine.node_limit = node_limit
    engine.transposition = {}
    engine.deadline = time.perf_counter() + (time_limit_ms / 1000.0)

    next_board, next_side, next_white, next_black = game.apply_move_state(
        game.board,
        game.side_to_move,
        game.score_white,
        game.score_black,
        move,
    )
    score = engine.minimax(next_board, next_side, next_white, next_black, depth - 1, -10**9, 10**9, strategy_name)
    return score, move


class MultiplayerClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None
        self.reader = None
        self.file = None
        self.events = queue.Queue()
        self.connected = False

    def connect(self, name="Unchess Player"):
        self.socket = socket.create_connection((self.host, self.port), timeout=5)
        self.socket.settimeout(None)
        self.file = self.socket.makefile("r", encoding="utf-8", newline="\n")
        self.connected = True
        self.reader = threading.Thread(target=self.read_loop, daemon=True)
        self.reader.start()
        self.send({"type": "hello", "name": name})

    def read_loop(self):
        try:
            while self.connected:
                line = self.file.readline()
                if not line:
                    break
                self.events.put(json.loads(line))
        except Exception as exc:
            self.events.put({"type": "network_error", "message": str(exc)})
        finally:
            self.connected = False
            self.events.put({"type": "disconnected"})

    def send(self, payload):
        if not self.connected or self.socket is None:
            raise RuntimeError("Client is not connected")
        encoded = (json.dumps(payload) + "\n").encode("utf-8")
        self.socket.sendall(encoded)

    def poll_events(self):
        events = []
        while True:
            try:
                events.append(self.events.get_nowait())
            except queue.Empty:
                return events

    def close(self):
        self.connected = False
        if self.socket is not None:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None
        if self.file is not None:
            try:
                self.file.close()
            except OSError:
                pass
            self.file = None


class BotEngine:
    MAX_PARALLEL_WORKERS = max(1, min(os.cpu_count() or 1, 4))
    STRATEGY_WEIGHTS = {
        "easy": [("gagyi", 0.9), ("kozepes", 0.1)],
        "normal": [("gagyi", 0.1), ("kozepes", 0.8), ("jo", 0.1)],
        "hard": [("kozepes", 0.1), ("jo", 0.8), ("verhetetlen", 0.1)],
        "unbeatable": [("verhetetlen", 1.0)],
    }

    STRATEGY_CONFIG = {
        "gagyi": {"depth": 1, "random_top": 5, "noise": 50, "iterative": False, "node_limit": 300, "time_limit_ms": 150},
        "kozepes": {"depth": 2, "random_top": 3, "noise": 20, "iterative": False, "node_limit": 2000, "time_limit_ms": 500},
        "jo": {"depth": 3, "random_top": 2, "noise": 6, "iterative": False, "node_limit": 12000, "time_limit_ms": 1500},
        "verhetetlen": {"depth": 4, "random_top": 1, "noise": 0, "iterative": True, "node_limit": 50000, "time_limit_ms": 3500},
    }

    def __init__(self, game, bot_color, difficulty):
        self.game = game
        self.bot_color = bot_color
        self.difficulty = difficulty
        self.nodes = 0
        self.node_limit = 0
        self.transposition = {}
        self.deadline = 0.0

    def choose_move(self):
        strategy_name = self.pick_strategy_name()
        config = self.STRATEGY_CONFIG[strategy_name]
        legal_moves = self.game.all_legal_moves(self.game.board, self.game.side_to_move)
        if not legal_moves:
            return None

        self.nodes = 0
        self.node_limit = config["node_limit"]
        self.transposition = {}
        self.deadline = time.perf_counter() + (config["time_limit_ms"] / 1000.0)

        if config["iterative"]:
            best_scored = self.iterative_search(legal_moves, config)
        else:
            best_scored = self.search_moves(legal_moves, config["depth"], strategy_name)

        if not best_scored:
            return random.choice(legal_moves)

        best_scored.sort(key=lambda item: item[0], reverse=True)
        top_count = min(len(best_scored), config["random_top"])
        return random.choice(best_scored[:top_count])[1]

    def pick_strategy_name(self):
        roll = random.random()
        cumulative = 0.0
        for strategy_name, weight in self.STRATEGY_WEIGHTS[self.difficulty]:
            cumulative += weight
            if roll <= cumulative:
                return strategy_name
        return self.STRATEGY_WEIGHTS[self.difficulty][-1][0]

    def iterative_search(self, legal_moves, config):
        best_scored = []
        for depth in range(1, config["depth"] + 1):
            if self.nodes >= self.node_limit or self.timed_out():
                break
            candidate = self.search_moves(legal_moves, depth, "verhetetlen")
            if candidate:
                best_scored = candidate
        return best_scored

    def search_moves(self, legal_moves, depth, strategy_name):
        if self.should_parallelize(legal_moves, depth, strategy_name):
            parallel_scored = self.parallel_search_moves(legal_moves, depth, strategy_name)
            if parallel_scored:
                return self.add_noise(parallel_scored, strategy_name)
        scored = []
        ordered_moves = self.order_moves(
            legal_moves,
            self.game.board,
            self.game.side_to_move,
            self.game.score_white,
            self.game.score_black,
            strategy_name,
        )
        alpha = -10**9
        beta = 10**9

        for move in ordered_moves:
            if self.nodes >= self.node_limit or self.timed_out():
                break
            next_board, next_side, next_white, next_black = self.game.apply_move_state(
                self.game.board,
                self.game.side_to_move,
                self.game.score_white,
                self.game.score_black,
                move,
            )
            score = self.minimax(
                next_board,
                next_side,
                next_white,
                next_black,
                depth - 1,
                alpha,
                beta,
                strategy_name,
            )
            scored.append((score, move))
            if score > alpha:
                alpha = score
        return self.add_noise(scored, strategy_name)

    def should_parallelize(self, legal_moves, depth, strategy_name):
        return (
            strategy_name == "verhetetlen"
            and depth >= 3
            and len(legal_moves) >= 2
            and self.MAX_PARALLEL_WORKERS > 1
        )

    def parallel_search_moves(self, legal_moves, depth, strategy_name):
        ordered_moves = self.order_moves(
            legal_moves,
            self.game.board,
            self.game.side_to_move,
            self.game.score_white,
            self.game.score_black,
            strategy_name,
        )
        worker_count = min(self.MAX_PARALLEL_WORKERS, len(ordered_moves))
        if worker_count <= 1:
            return []

        state = self.serialize_search_state()
        per_worker_limit = max(4000, self.node_limit // worker_count)
        time_left_ms = max(250, int((self.deadline - time.perf_counter()) * 1000))
        payloads = [
            {
                "state": state,
                "move": move,
                "depth": depth,
                "strategy_name": strategy_name,
                "bot_color": self.bot_color,
                "difficulty": self.difficulty,
                "node_limit": per_worker_limit,
                "time_limit_ms": time_left_ms,
            }
            for move in ordered_moves
        ]

        try:
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                results = list(executor.map(evaluate_root_move_parallel, payloads))
        except Exception:
            return []

        self.nodes += len(results) * per_worker_limit
        return results

    def serialize_search_state(self):
        return {
            "board": deep_copy_board(self.game.board),
            "side_to_move": self.game.side_to_move,
            "score_white": self.game.score_white,
            "score_black": self.game.score_black,
            "state_history": self.game.state_history[:],
            "move_history": self.game.move_history[:],
            "last_executed_move": self.game.last_executed_move,
        }

    def minimax(self, board, side_to_move, score_white, score_black, depth, alpha, beta, strategy_name):
        self.nodes += 1
        if self.timed_out():
            return self.evaluate_position(
                board,
                side_to_move,
                score_white,
                score_black,
                strategy_name,
                self.game.all_legal_moves(board, side_to_move),
            )
        state_key = self.make_state_key(board, side_to_move, score_white, score_black, depth)
        if state_key in self.transposition:
            return self.transposition[state_key]

        legal_moves = self.game.all_legal_moves(board, side_to_move)
        terminal_score = self.evaluate_terminal(board, side_to_move, score_white, score_black, legal_moves)
        if terminal_score is not None:
            self.transposition[state_key] = terminal_score
            return terminal_score

        if depth <= 0 or self.nodes >= self.node_limit or self.timed_out():
            value = self.evaluate_position(board, side_to_move, score_white, score_black, strategy_name, legal_moves)
            self.transposition[state_key] = value
            return value

        actor = opposite(side_to_move)
        maximizing = actor == self.bot_color
        ordered_moves = self.order_moves(legal_moves, board, side_to_move, score_white, score_black, strategy_name)

        if maximizing:
            value = -10**9
            for move in ordered_moves:
                next_board, next_side, next_white, next_black = self.game.apply_move_state(
                    board, side_to_move, score_white, score_black, move
                )
                value = max(
                    value,
                    self.minimax(next_board, next_side, next_white, next_black, depth - 1, alpha, beta, strategy_name),
                )
                alpha = max(alpha, value)
                if beta <= alpha or self.nodes >= self.node_limit or self.timed_out():
                    break
        else:
            value = 10**9
            for move in ordered_moves:
                next_board, next_side, next_white, next_black = self.game.apply_move_state(
                    board, side_to_move, score_white, score_black, move
                )
                value = min(
                    value,
                    self.minimax(next_board, next_side, next_white, next_black, depth - 1, alpha, beta, strategy_name),
                )
                beta = min(beta, value)
                if beta <= alpha or self.nodes >= self.node_limit or self.timed_out():
                    break

        self.transposition[state_key] = value
        return value

    def evaluate_terminal(self, board, side_to_move, score_white, score_black, legal_moves):
        if not legal_moves:
            if self.game.is_in_check(board, side_to_move):
                winner = opposite(side_to_move)
                return 1_000_000 if winner == self.bot_color else -1_000_000
            return self.score_delta(score_white, score_black) * 1000
        return None

    def evaluate_position(self, board, side_to_move, score_white, score_black, strategy_name, legal_moves):
        my_color = self.bot_color
        enemy_color = opposite(my_color)
        my_king = self.game.find_king(board, my_color)
        enemy_king = self.game.find_king(board, enemy_color)
        weights = self.strategy_weights(strategy_name)

        point_score = self.score_delta(score_white, score_black) * weights["points"]
        my_escapes = self.king_escape_count(board, my_color, my_king)
        enemy_escapes = self.king_escape_count(board, enemy_color, enemy_king)
        king_network = my_escapes * weights["self_escape"] - enemy_escapes * weights["enemy_escape"]
        my_zone = self.king_zone_pressure(board, my_color)
        enemy_zone = self.king_zone_pressure(board, enemy_color)
        zone_score = enemy_zone * weights["enemy_zone"] - my_zone * weights["self_zone"]
        hunt_score = (
            self.king_hunt_score(board, my_color, enemy_king)
            - self.king_hunt_score(board, enemy_color, my_king)
        ) * weights["hunt"]

        my_check = self.game.is_in_check(board, my_color)
        enemy_check = self.game.is_in_check(board, enemy_color)
        self_response = self.response_profile(board, my_color)
        enemy_response = self.response_profile(board, enemy_color)

        self_defense = self.response_profile_score(self_response, strategy_name, own=True)
        enemy_defense = self.response_profile_score(enemy_response, strategy_name, own=False)
        shield_score = self.interposition_shield_score(board, my_color, strategy_name) - self.interposition_shield_score(board, enemy_color, strategy_name)

        check_state = 0
        if my_check:
            check_state -= weights["self_in_check"]
        if enemy_check:
            check_state += weights["enemy_in_check"]

        return point_score + king_network + zone_score + hunt_score + self_defense - enemy_defense + shield_score + check_state

    def check_shape_bonus(self, board, color, strategy_name):
        profile = self.response_profile(board, color)
        return self.response_profile_score(profile, strategy_name, own=(color == self.bot_color))

    def trap_pressure(self, board, color, strategy_name):
        enemy_color = opposite(color)
        profile = self.response_profile(board, enemy_color)
        return -self.response_profile_score(profile, strategy_name, own=False)

    def interposition_shield_score(self, board, color, strategy_name):
        profile = self.response_profile(board, color)
        if not profile["in_check"]:
            return 0
        multiplier = {"gagyi": 1, "kozepes": 2, "jo": 4, "verhetetlen": 6}[strategy_name]
        return profile["high_value_blocks"] * multiplier

    def king_escape_count(self, board, color, king_pos):
        if king_pos is None:
            return 0
        row, col = king_pos
        piece = board[row][col]
        escapes = 0
        for move in self.game.generate_king_moves(board, row, col, piece):
            next_board = self.game.simulate_move(board, move)
            if not self.game.is_in_check(next_board, color):
                escapes += 1
        return escapes

    def is_square_attacked_by(self, board, row, col, attacker_color):
        for from_row in range(BOARD_SIZE):
            for from_col in range(BOARD_SIZE):
                piece = board[from_row][from_col]
                if piece and piece_color(piece) == attacker_color:
                    if self.game.piece_attacks_square(board, from_row, from_col, row, col):
                        return True
        return False

    def king_zone_pressure(self, board, king_color):
        king_pos = self.game.find_king(board, king_color)
        if king_pos is None:
            return 0
        king_row, king_col = king_pos
        attacker_color = opposite(king_color)
        pressure = 0
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                row = king_row + dr
                col = king_col + dc
                if not in_bounds(row, col):
                    pressure += 2
                    continue
                occupant = board[row][col]
                if occupant and piece_color(occupant) == king_color:
                    pressure += 1
                if self.is_square_attacked_by(board, row, col, attacker_color):
                    pressure += 3
        return pressure

    def king_hunt_score(self, board, attacker_color, king_pos):
        if king_pos is None:
            return 0
        king_row, king_col = king_pos
        total = 0
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                piece = board[row][col]
                if not piece or piece_color(piece) != attacker_color:
                    continue
                lower = piece.lower()
                if lower == "k":
                    continue
                distance = abs(king_row - row) + abs(king_col - col)
                closeness = max(0, 10 - distance)
                total += closeness
                if self.game.piece_attacks_square(board, row, col, king_row, king_col):
                    total += 24
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        zr = king_row + dr
                        zc = king_col + dc
                        if in_bounds(zr, zc) and self.game.piece_attacks_square(board, row, col, zr, zc):
                            total += 6
        return total

    def order_moves(self, legal_moves, board, side_to_move, score_white, score_black, strategy_name="kozepes"):
        actor = opposite(side_to_move)
        responder_color = side_to_move
        actor_in_check = self.game.is_in_check(board, responder_color)
        has_non_capture_king_escape = any(
            move["piece"].lower() == "k" and not move["captured"] for move in legal_moves
        )
        legal_moves = self.prefer_check_responses(legal_moves, board, responder_color, strategy_name)
        actor_king = self.game.find_king(board, actor)
        enemy_king = self.game.find_king(board, opposite(actor))
        current_actor_escapes = self.king_escape_count(board, actor, actor_king)
        current_enemy_escapes = self.king_escape_count(board, opposite(actor), enemy_king)
        ordered = []
        for move in legal_moves:
            bonus = 0
            if move["captured"]:
                bonus -= self.capture_penalty(move, strategy_name)
            if actor_in_check and has_non_capture_king_escape and move["captured"]:
                bonus -= {"gagyi": 25, "kozepes": 120, "jo": 500, "verhetetlen": 5000}[strategy_name]
            next_board, next_side, next_white, next_black = self.game.apply_move_state(
                board, side_to_move, score_white, score_black, move
            )
            bonus -= self.reversal_penalty(move, board, side_to_move, strategy_name)
            bonus -= self.repetition_penalty(next_board, next_side, move, strategy_name)
            next_actor_king = self.game.find_king(next_board, actor)
            next_enemy_king = self.game.find_king(next_board, opposite(actor))
            next_actor_escapes = self.king_escape_count(next_board, actor, next_actor_king)
            next_enemy_escapes = self.king_escape_count(next_board, opposite(actor), next_enemy_king)
            bonus += self.produced_check_score(next_board, next_side, strategy_name)
            if move["piece"].lower() == "k":
                bonus += 8
            bonus += (next_actor_escapes - current_actor_escapes) * {"gagyi": 4, "kozepes": 8, "jo": 16, "verhetetlen": 24}[strategy_name]
            bonus += (current_enemy_escapes - next_enemy_escapes) * {"gagyi": 6, "kozepes": 14, "jo": 28, "verhetetlen": 44}[strategy_name]
            bonus += (self.king_hunt_score(next_board, actor, next_enemy_king) - self.king_hunt_score(board, actor, enemy_king)) * {"gagyi": 0.4, "kozepes": 0.8, "jo": 1.4, "verhetetlen": 2.0}[strategy_name]
            bonus += self.check_shape_bonus(next_board, next_side, strategy_name)
            bonus += self.trap_pressure(next_board, actor, strategy_name)
            bonus += self.interposition_shield_score(next_board, actor, strategy_name)
            bonus += self.king_zone_pressure(next_board, opposite(actor)) * {"gagyi": 1, "kozepes": 2, "jo": 4, "verhetetlen": 7}[strategy_name]
            ordered.append((bonus, move))
        ordered.sort(key=lambda item: item[0], reverse=True)
        return [move for _, move in ordered]

    def prefer_check_responses(self, legal_moves, board, actor_color, strategy_name):
        if not self.game.is_in_check(board, actor_color):
            return legal_moves

        king_escape_moves = [move for move in legal_moves if move["piece"].lower() == "k" and not move["captured"]]
        king_capture_moves = [move for move in legal_moves if move["piece"].lower() == "k" and move["captured"]]
        capture_moves = [move for move in legal_moves if move["piece"].lower() != "k" and move["captured"]]
        block_moves = [move for move in legal_moves if move["piece"].lower() != "k" and not move["captured"]]
        non_capture_responses = king_escape_moves + block_moves

        if strategy_name == "verhetetlen":
            if non_capture_responses:
                return non_capture_responses
            if king_capture_moves:
                return king_capture_moves
            return capture_moves or legal_moves

        if strategy_name == "jo":
            if non_capture_responses:
                return non_capture_responses + king_capture_moves + capture_moves
            return king_capture_moves + capture_moves

        if strategy_name == "kozepes":
            if non_capture_responses:
                return king_escape_moves + block_moves + king_capture_moves + capture_moves
            return king_capture_moves + capture_moves

        # A gagyi bot még hibázhat, de az elmenekülést így is előre vesszük.
        if non_capture_responses:
            return king_escape_moves + king_capture_moves + capture_moves + block_moves
        return king_capture_moves + capture_moves + block_moves

    def add_noise(self, scored, strategy_name):
        noise = self.STRATEGY_CONFIG[strategy_name]["noise"]
        if noise <= 0:
            return scored
        return [(score + random.randint(-noise, noise), move) for score, move in scored]

    def score_delta(self, score_white, score_black):
        return score_black - score_white if self.bot_color == "black" else score_white - score_black

    def make_state_key(self, board, side_to_move, score_white, score_black, depth):
        rows = tuple(tuple(row) for row in board)
        return rows, side_to_move, score_white, score_black, depth

    def timed_out(self):
        return time.perf_counter() >= self.deadline

    def capture_penalty(self, move, strategy_name):
        captured_value = PIECE_VALUES.get(move["captured"].lower(), 0) if move["captured"] else 0
        mover_value = PIECE_VALUES.get(move["piece"].lower(), 0)
        if strategy_name == "gagyi":
            return 8 + captured_value * 4
        if strategy_name == "kozepes":
            return 16 + captured_value * 7 + mover_value * 2
        if strategy_name == "jo":
            return 24 + captured_value * 10 + mover_value * 4
        return 32 + captured_value * 14 + mover_value * 6

    def reversal_penalty(self, move, board, side_to_move, strategy_name):
        if board is not self.game.board or side_to_move != self.game.side_to_move:
            return 0
        last_move = self.game.last_executed_move
        if not last_move:
            return 0
        same_piece = move["piece"] == last_move["piece"]
        direct_undo = move["from"] == last_move["to"] and move["to"] == last_move["from"]
        if not (same_piece and direct_undo):
            return 0
        penalties = {"gagyi": 40, "kozepes": 140, "jo": 320, "verhetetlen": 1200}
        return penalties[strategy_name]

    def repetition_penalty(self, next_board, next_side, move, strategy_name):
        if next_board is self.game.board:
            return 0
        penalties = {
            "gagyi": {"state": 80, "two_ply": 40},
            "kozepes": {"state": 260, "two_ply": 180},
            "jo": {"state": 900, "two_ply": 650},
            "verhetetlen": {"state": 5000, "two_ply": 2500},
        }[strategy_name]

        penalty = 0
        repeat_count = self.game.state_history.count(self.game.repetition_key(next_board, next_side))
        if repeat_count >= 1:
            penalty += penalties["state"] * repeat_count

        if len(self.game.move_history) >= 2:
            same_side_previous = self.game.move_history[-2]
            if (
                same_side_previous["piece"] == move["piece"]
                and same_side_previous["from"] == move["to"]
                and same_side_previous["to"] == move["from"]
            ):
                penalty += penalties["two_ply"]

        return penalty

    def produced_check_score(self, board, checked_color, strategy_name):
        if not self.game.is_in_check(board, checked_color):
            return 0
        legal_moves = self.game.all_legal_moves(board, checked_color)
        if not legal_moves:
            return -100_000

        profile = self.response_profile(board, checked_color, legal_moves)
        scores = {
            "gagyi": {"escape": 20, "block": 30, "capture": 44, "forced_bonus": 22},
            "kozepes": {"escape": 80, "block": 115, "capture": 180, "forced_bonus": 70},
            "jo": {"escape": 160, "block": 240, "capture": 380, "forced_bonus": 140},
            "verhetetlen": {"escape": 280, "block": 420, "capture": 760, "forced_bonus": 260},
        }[strategy_name]

        score = 0
        if profile["escape_count"] > 0:
            score += scores["escape"]
            score += max(0, 3 - profile["escape_count"]) * (scores["escape"] // 3)
        if profile["block_count"] > 0:
            score += scores["block"]
        if profile["capture_count"] > 0:
            score += scores["capture"]
            score += profile["capture_value"] * (scores["capture"] // 8)

        forced_options = sum(1 for count in (profile["escape_count"], profile["block_count"], profile["capture_count"]) if count > 0)
        if forced_options == 1:
            score += scores["forced_bonus"]
            if profile["capture_count"] > 0:
                score += scores["forced_bonus"] * 2

        return score

    def strategy_weights(self, strategy_name):
        if strategy_name == "gagyi":
            return {
                "points": 90,
                "self_escape": 5,
                "enemy_escape": 3,
                "self_zone": 2,
                "enemy_zone": 5,
                "hunt": 2,
                "self_in_check": 35,
                "enemy_in_check": 10,
            }
        if strategy_name == "kozepes":
            return {
                "points": 120,
                "self_escape": 10,
                "enemy_escape": 8,
                "self_zone": 5,
                "enemy_zone": 10,
                "hunt": 5,
                "self_in_check": 60,
                "enemy_in_check": 18,
            }
        if strategy_name == "jo":
            return {
                "points": 150,
                "self_escape": 18,
                "enemy_escape": 14,
                "self_zone": 8,
                "enemy_zone": 18,
                "hunt": 9,
                "self_in_check": 95,
                "enemy_in_check": 24,
            }
        return {
            "points": 180,
            "self_escape": 26,
            "enemy_escape": 18,
            "self_zone": 10,
            "enemy_zone": 26,
            "hunt": 14,
            "self_in_check": 130,
            "enemy_in_check": 30,
        }

    def response_profile(self, board, color, legal_moves=None):
        in_check = self.game.is_in_check(board, color)
        if legal_moves is None:
            legal_moves = self.game.all_legal_moves(board, color)
        profile = {
            "in_check": in_check,
            "total": len(legal_moves),
            "escape_count": 0,
            "block_count": 0,
            "capture_count": 0,
            "capture_value": 0,
            "high_value_blocks": 0,
        }
        for move in legal_moves:
            piece = move["piece"]
            if piece.lower() == "k":
                profile["escape_count"] += 1
            elif move["captured"]:
                profile["capture_count"] += 1
                profile["capture_value"] += PIECE_VALUES.get(move["captured"].lower(), 0)
            else:
                profile["block_count"] += 1
                profile["high_value_blocks"] += PIECE_VALUES.get(piece.lower(), 0)
        return profile

    def response_profile_score(self, profile, strategy_name, own):
        if not profile["in_check"]:
            return 0
        multipliers = {
            "gagyi": {"escape": 4, "block": 2, "capture": -2, "tight": -1, "shield": 1},
            "kozepes": {"escape": 10, "block": 5, "capture": -8, "tight": -3, "shield": 2},
            "jo": {"escape": 18, "block": 10, "capture": -14, "tight": -5, "shield": 3},
            "verhetetlen": {"escape": 28, "block": 14, "capture": -22, "tight": -8, "shield": 4},
        }[strategy_name]
        score = (
            profile["escape_count"] * multipliers["escape"]
            + profile["block_count"] * multipliers["block"]
            + profile["capture_count"] * multipliers["capture"]
            + profile["high_value_blocks"] * multipliers["shield"]
            + profile["total"] * multipliers["tight"]
        )
        return score if own else score * 1.2


class UnchessGame:
    def __init__(self, app, parent, mode_config):
        self.app = app
        self.root = app.root
        self.mode_config = mode_config
        self.root.title("Unchess")
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(True, True)
        self.root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        self.container = tk.Frame(parent, bg=BG_COLOR)
        self.container.pack(fill="both", expand=True)

        self.board = deep_copy_board(INITIAL_BOARD)
        self.side_to_move = "white"
        self.selected = None
        self.legal_moves = []
        self.score_white = 0
        self.score_black = 0
        self.move_count = 0
        self.move_limit = self.mode_config.get("move_limit", self.app.default_move_limit)
        self.animating = False
        self.animating_from = None
        self.game_over = False
        self.state_history = [self.repetition_key(self.board, self.side_to_move)]
        self.last_executed_move = None
        self.move_history = []
        self.match_started_at = time.time()
        self.check_path = set()
        self.checker_positions = set()
        self.check_king = None
        self.undo_stack = []
        self.redo_stack = []
        self.bot_engines = {}
        if "bot_players" in self.mode_config:
            for color, difficulty in self.mode_config["bot_players"].items():
                self.bot_engines[color] = BotEngine(self, color, difficulty)
        elif self.mode_config["mode"] == "bot":
            self.bot_engines[self.mode_config["bot_color"]] = BotEngine(
                self, self.mode_config["bot_color"], self.mode_config["difficulty"]
            )
        self.bot_thread = None
        self.bot_result_queue = queue.Queue()
        self.bot_thinking = False
        self.pending_bot_move = None
        self.bot_paused = False
        self.pause_button = None
        self.destroyed = False
        self.network_client = self.mode_config.get("network_client")
        self.pending_network_move = None
        self.pending_network_sync = None

        self.status_var = tk.StringVar()
        self.score_var = tk.StringVar()
        self.turn_var = tk.StringVar()
        self.info_var = tk.StringVar()

        header = tk.Frame(self.container, bg=BG_COLOR, padx=16, pady=12)
        header.pack(fill="x")

        self.mode_label = tk.Label(
            header,
            text=f"{self.app.ui_label('mode')}: {self.mode_title()}",
            font=("Segoe UI", 11, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        )
        self.mode_label.pack(side="left")

        self.undo_button = tk.Button(
            header,
            text=self.app.ui_label("undo"),
            command=self.undo_move,
            padx=12,
        )
        self.undo_button.pack(side="right", padx=(0, 8))

        self.redo_button = tk.Button(
            header,
            text=self.app.ui_label("redo"),
            command=self.redo_move,
            padx=12,
        )
        self.redo_button.pack(side="right", padx=(0, 8))

        self.back_button = tk.Button(
            header,
            text=self.app.ui_label("back_to_menu"),
            command=self.app.return_to_main_menu,
            padx=12,
        )
        self.back_button.pack(side="right")

        if self.mode_config["mode"] in {"multiplayer", "spectator"}:
            if self.app.is_admin and self.mode_config["mode"] == "spectator":
                self.ban_button = tk.Button(
                    header,
                    text=self.app.ui_label("ban"),
                    command=self.ban_spectated_target if self.mode_config["mode"] == "spectator" else self.ban_opponent,
                    padx=12,
                )
                self.ban_button.pack(side="right", padx=(0, 8))
            else:
                self.ban_button = None
            if self.mode_config["mode"] == "spectator":
                self.report_button = tk.Button(
                    header,
                    text=self.app.ui_label("spectate_target"),
                    command=self.toggle_spectate_target,
                    padx=12,
                )
            elif not self.app.is_admin:
                self.report_button = tk.Button(
                    header,
                    text=self.app.ui_label("report"),
                    command=self.report_opponent,
                    padx=12,
                )
            else:
                self.report_button = None
            if self.report_button is not None:
                self.report_button.pack(side="right", padx=(0, 8))
        else:
            self.ban_button = None
            self.report_button = None

        if self.mode_config["mode"] == "bot_vs_bot":
            self.pause_button = tk.Button(
                header,
                text=self.app.ui_label("pause"),
                command=self.toggle_bot_pause,
                padx=12,
            )
            self.pause_button.pack(side="right", padx=(0, 8))
        else:
            self.pause_button = None

        board_area = tk.Frame(self.container, bg=BG_COLOR)
        board_area.pack(fill="both", expand=True, pady=(12, 12))
        board_area.grid_rowconfigure(0, weight=1)
        board_column = 0
        if self.mode_config["mode"] == "multiplayer" and self.app.is_admin:
            admin_panel = tk.Frame(board_area, width=180, bg="#efe5d8", padx=14, pady=16)
            admin_panel.grid(row=0, column=0, sticky="ns", padx=(0, 12))
            admin_panel.grid_propagate(False)
            tk.Label(admin_panel, text=self.app.ui_label("admin_ingame_tools"), font=("Segoe UI", 12, "bold"), bg="#efe5d8", fg=TEXT_COLOR, justify="left").pack(anchor="w", pady=(0, 10))
            tk.Label(admin_panel, text=self.app.ui_label("admin_ingame_tools_subtitle"), font=("Segoe UI", 10), bg="#efe5d8", fg="#5a5a5a", wraplength=150, justify="left").pack(anchor="w", pady=(0, 12))
            tk.Button(admin_panel, text=self.app.ui_label("console_revoke_report"), command=self.revoke_opponent_report_permission, padx=10, pady=8, wraplength=140, justify="center").pack(fill="x", pady=(0, 8))
            tk.Button(admin_panel, text=self.app.ui_label("ban"), command=self.ban_opponent, padx=10, pady=8, wraplength=140, justify="center").pack(fill="x")
            board_column = 1
        board_area.grid_columnconfigure(board_column, weight=1)

        self.canvas = tk.Canvas(
            board_area,
            width=BOARD_PIXELS,
            height=BOARD_PIXELS,
            bg=BG_COLOR,
            highlightthickness=0,
        )
        self.canvas.grid(row=0, column=board_column, sticky="nsew")
        self.canvas.bind("<Button-1>", self.on_mouse_click)
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        sidebar = tk.Frame(board_area, width=SIDEBAR_WIDTH, bg=BG_COLOR, padx=18, pady=20)
        sidebar.grid(row=0, column=board_column + 1, sticky="ns")
        sidebar.grid_propagate(False)

        self.sidebar_title_label = tk.Label(
            sidebar,
            text="Unchess",
            font=("Segoe UI", 24, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        )
        self.sidebar_title_label.pack(anchor="w")

        self.sidebar_subtitle_label = tk.Label(
            sidebar,
            text=self.app.ui_label("game_subtitle"),
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
        )
        self.sidebar_subtitle_label.pack(anchor="w", pady=(2, 16))

        turn_label = tk.Label(
            sidebar,
            textvariable=self.turn_var,
            justify="left",
            font=("Segoe UI", 12, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        )
        turn_label.pack(anchor="w", pady=(0, 12))

        score_label = tk.Label(
            sidebar,
            textvariable=self.score_var,
            justify="left",
            font=("Consolas", 12),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        )
        score_label.pack(anchor="w", pady=(0, 12))

        status_label = tk.Label(
            sidebar,
            textvariable=self.status_var,
            wraplength=SIDEBAR_WIDTH - 36,
            justify="left",
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        )
        status_label.pack(anchor="w", pady=(0, 12))

        info_label = tk.Label(
            sidebar,
            textvariable=self.info_var,
            wraplength=SIDEBAR_WIDTH - 36,
            justify="left",
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg="#4e4e4e",
        )
        info_label.pack(anchor="w")

        initial_state = self.mode_config.get("initial_state")
        if initial_state is not None:
            self.board = deep_copy_board(initial_state.get("board", self.board))
            self.side_to_move = initial_state.get("side_to_move", self.side_to_move)
            self.score_white = int(initial_state.get("score_white", self.score_white))
            self.score_black = int(initial_state.get("score_black", self.score_black))
            self.move_count = int(initial_state.get("move_count", self.move_count))
            self.game_over = bool(initial_state.get("game_over", False))

        self.draw()
        self.start_turn()

    def destroy(self):
        self.destroyed = True
        self.game_over = True
        self.bot_paused = True
        self.pending_bot_move = None
        if self.mode_config["mode"] == "spectator" and self.network_client is not None:
            try:
                self.network_client.send({"type": "admin_leave_spectate"})
            except OSError:
                pass
        self.container.destroy()

    def toggle_bot_pause(self):
        if self.mode_config["mode"] != "bot_vs_bot":
            return
        self.bot_paused = not self.bot_paused
        if self.pause_button is not None:
            self.pause_button.configure(text=self.app.ui_label("resume") if self.bot_paused else self.app.ui_label("pause"))
        if self.bot_paused:
            if not self.bot_thinking:
                self.status_var.set(self.app.ui_label("bot_duel_paused"))
                self.draw()
        else:
            if self.pending_bot_move is not None and not self.animating and not self.game_over:
                move = self.pending_bot_move
                self.pending_bot_move = None
                self.status_var.set(self.app.ui_label("bot_thinking"))
                self.draw()
                self.execute_move(move)
                return
            if not self.bot_thinking and self.is_bot_turn() and not self.game_over:
                self.status_var.set(self.app.ui_label("bot_thinking"))
                self.draw()
                self.root.after(80, self.run_bot_turn)

    def mode_title(self):
        if self.mode_config["mode"] == "singleplayer":
            return self.app.ui_label("singleplayer")
        if self.mode_config["mode"] == "bot":
            return f"Bot - {self.mode_config['difficulty_label']}"
        if self.mode_config["mode"] == "bot_vs_bot":
            return f"{self.app.ui_label('bot_vs_bot')} - {self.mode_config['white_label']} / {self.mode_config['black_label']}"
        if self.mode_config["mode"] == "spectator":
            return self.app.ui_label("spectator")
        return self.app.ui_label("multiplayer")

    def color_label(self, color, upper=False):
        key = f"{color}_{'upper' if upper else 'lower'}"
        return self.app.ui_label(key)

    def refresh_language(self):
        self.mode_label.configure(text=f"{self.app.ui_label('mode')}: {self.mode_title()}")
        self.undo_button.configure(text=self.app.ui_label("undo"))
        self.redo_button.configure(text=self.app.ui_label("redo"))
        self.back_button.configure(text=self.app.ui_label("back_to_menu"))
        self.sidebar_subtitle_label.configure(text=self.app.ui_label("game_subtitle"))
        if self.pause_button is not None:
            self.pause_button.configure(text=self.app.ui_label("resume") if self.bot_paused else self.app.ui_label("pause"))
        if self.report_button is not None:
            if self.mode_config["mode"] == "spectator":
                self.report_button.configure(text=self.app.ui_label("spectate_target"))
            else:
                self.report_button.configure(text=self.app.ui_label("report"))
        if self.ban_button is not None:
            self.ban_button.configure(text=self.app.ui_label("ban"))
        self.update_sidebar()
        self.draw()

    def snapshot_state(self):
        return {
            "board": deep_copy_board(self.board),
            "side_to_move": self.side_to_move,
            "score_white": self.score_white,
            "score_black": self.score_black,
            "move_count": self.move_count,
            "game_over": self.game_over,
            "status": self.status_var.get(),
            "state_history": self.state_history[:],
            "last_executed_move": self.last_executed_move,
            "move_history": self.move_history[:],
        }

    def restore_state(self, state):
        self.board = deep_copy_board(state["board"])
        self.side_to_move = state["side_to_move"]
        self.score_white = state["score_white"]
        self.score_black = state["score_black"]
        self.move_count = state["move_count"]
        self.game_over = state["game_over"]
        self.state_history = state["state_history"][:]
        self.last_executed_move = state["last_executed_move"]
        self.move_history = state["move_history"][:]
        self.selected = None
        self.legal_moves = []
        self.animating = False
        self.animating_from = None
        self.status_var.set(state["status"])
        self.draw()
        if not self.game_over:
            self.start_turn()

    def undo_move(self):
        if self.mode_config["mode"] == "multiplayer":
            messagebox.showinfo(self.app.ui_label("undo"), self.app.ui_label("multiplayer_undo_unavailable"))
            return
        if self.animating or self.bot_thinking or not self.undo_stack:
            return
        if self.mode_config["mode"] == "bot":
            if len(self.undo_stack) < 2:
                return
            current_state = self.snapshot_state()
            intermediate_state = self.undo_stack.pop()
            previous = self.undo_stack.pop()
            self.redo_stack.append(
                {
                    "kind": "bot_round",
                    "final": current_state,
                    "intermediate": intermediate_state,
                }
            )
            self.restore_state(previous)
            return

        self.redo_stack.append(self.snapshot_state())
        previous = self.undo_stack.pop()
        self.restore_state(previous)

    def redo_move(self):
        if self.mode_config["mode"] == "multiplayer":
            messagebox.showinfo(self.app.ui_label("redo"), self.app.ui_label("multiplayer_redo_unavailable"))
            return
        if self.animating or self.bot_thinking or not self.redo_stack:
            return
        entry = self.redo_stack.pop()
        if self.mode_config["mode"] == "bot":
            if not isinstance(entry, dict) or entry.get("kind") != "bot_round":
                return
            self.undo_stack.append(self.snapshot_state())
            self.undo_stack.append(entry["intermediate"])
            self.restore_state(entry["final"])
            return

        self.undo_stack.append(self.snapshot_state())
        self.restore_state(entry)

    def draw(self):
        self.canvas.delete("all")
        self.draw_board()
        self.draw_pieces()
        self.update_sidebar()

    def on_canvas_resize(self, _event):
        if not self.animating:
            self.draw()

    def board_metrics(self):
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        board_pixels = min(canvas_width, canvas_height)
        square_size = max(MIN_BOARD_SQUARE_PIXELS, board_pixels / BOARD_SIZE)
        board_pixels = square_size * BOARD_SIZE
        offset_x = (canvas_width - board_pixels) / 2
        offset_y = (canvas_height - board_pixels) / 2
        return square_size, board_pixels, offset_x, offset_y

    def square_to_canvas(self, draw_row, draw_col):
        square_size, _, offset_x, offset_y = self.board_metrics()
        return (
            offset_x + draw_col * square_size,
            offset_y + draw_row * square_size,
            square_size,
        )

    def draw_board(self):
        square_size, board_pixels, offset_x, offset_y = self.board_metrics()
        check_path = set()
        checker_positions = set()
        check_king = None
        checkers = self.find_checkers(self.board, self.side_to_move)
        if checkers:
            check_king = self.find_king(self.board, self.side_to_move)
            for checker in checkers:
                checker_positions.add((checker["row"], checker["col"]))
                for square in self.attack_visual_path(
                    checker["piece"],
                    (checker["row"], checker["col"]),
                    check_king,
                ):
                    check_path.add(square)
        self.check_path = check_path
        self.checker_positions = checker_positions
        self.check_king = check_king

        self.canvas.create_rectangle(
            offset_x,
            offset_y,
            offset_x + board_pixels,
            offset_y + board_pixels,
            fill=LIGHT_SQUARE,
            outline="",
        )

        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                draw_row, draw_col = self.to_display_coords(row, col)
                x1, y1, _ = self.square_to_canvas(draw_row, draw_col)
                x2 = x1 + square_size
                y2 = y1 + square_size
                fill = LIGHT_SQUARE if (row + col) % 2 == 0 else DARK_SQUARE

                if self.selected == (row, col):
                    fill = SELECT_COLOR

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline="")
                if (row, col) in self.check_path:
                    self.canvas.create_rectangle(
                        x1,
                        y1,
                        x2,
                        y2,
                        fill=CHECK_PATH_COLOR,
                        outline="",
                        stipple="gray50",
                    )

        for move in self.legal_moves:
            row, col = move["to"]
            draw_row, draw_col = self.to_display_coords(row, col)
            x1, y1, _ = self.square_to_canvas(draw_row, draw_col)
            cx = x1 + square_size / 2
            cy = y1 + square_size / 2
            occupied = self.board[row][col] != ""
            radius = square_size * (0.22 if occupied else 0.14)
            color = CAPTURE_COLOR if occupied else MOVE_COLOR
            self.canvas.create_oval(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                fill=color,
                outline="",
                stipple="gray50",
            )

    def draw_pieces(self):
        square_size, _, _, _ = self.board_metrics()
        piece_font_size = max(16, int(square_size * 0.52))
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                if self.animating and self.animating_from == (row, col):
                    continue
                piece = self.board[row][col]
                if not piece:
                    continue
                draw_row, draw_col = self.to_display_coords(row, col)
                x1, y1, _ = self.square_to_canvas(draw_row, draw_col)
                cx = x1 + square_size / 2
                cy = y1 + square_size / 2
                fill = TEXT_COLOR
                if self.check_king == (row, col) or (row, col) in self.checker_positions:
                    fill = CHECK_TEXT_COLOR
                self.canvas.create_text(
                    cx,
                    cy,
                    text=PIECE_SYMBOLS[piece],
                    font=("Segoe UI Symbol", piece_font_size),
                    fill=fill,
                )

    def update_sidebar(self):
        player_name = self.color_label(self.current_actor(), upper=True)
        moving_side = self.color_label(self.side_to_move, upper=False)
        self.turn_var.set(f"{self.app.ui_label('player')}: {player_name}\n{self.app.ui_label('now_moving')}: {moving_side}")
        limit_text = "∞" if self.move_limit < 0 else str(self.move_limit)
        self.score_var.set(
            f"{self.app.ui_label('points')}\n{self.app.ui_label('white_upper')}: {self.score_white}\n{self.app.ui_label('black_upper')}: {self.score_black}\n{self.app.ui_label('moves')}: {self.move_count}/{limit_text}"
        )
        self.info_var.set(self.app.ui_label("rule_text"))
        if self.mode_config["mode"] == "bot":
            bot_name = self.color_label(self.mode_config["bot_color"], upper=True)
            player_name = self.color_label(self.mode_config["player_color"], upper=True)
            self.info_var.set(
                f"{self.info_var.get()}\n{self.app.ui_label('you')}: {player_name}\n{self.app.ui_label('bot')}: {bot_name} ({self.mode_config['difficulty_label']})"
            )
        if self.mode_config["mode"] == "bot_vs_bot":
            self.info_var.set(
                f"{self.info_var.get()}\n{self.app.ui_label('white_bot')}: {self.mode_config['white_label']}\n{self.app.ui_label('black_bot')}: {self.mode_config['black_label']}"
            )
        if self.mode_config["mode"] == "multiplayer":
            player_name = self.color_label(self.mode_config["player_color"], upper=True)
            room_code = self.mode_config.get("room_code", "??????")
            self.info_var.set(f"{self.info_var.get()}\n{self.app.ui_label('you')}: {player_name}\n{self.app.ui_label('room')}: {room_code}")
        if self.mode_config["mode"] == "spectator":
            room_code = self.mode_config.get("room_code", "??????")
            host_name = self.mode_config.get("host_username") or "?"
            guest_name = self.mode_config.get("guest_username") or "?"
            target_slot = self.mode_config.get("ban_target_slot", "host")
            target_name = host_name if target_slot == "host" else guest_name
            self.info_var.set(
                f"{self.info_var.get()}\n{self.app.ui_label('room')}: {room_code}\nHost: {host_name}\nGuest: {guest_name}\n{self.app.ui_label('spectate_target')}: {target_name}"
            )

    def current_actor(self):
        return opposite(self.side_to_move)

    def is_bot_turn(self):
        if self.mode_config["mode"] == "bot":
            return self.current_actor() == self.mode_config["bot_color"]
        if self.mode_config["mode"] == "bot_vs_bot":
            return True
        return False

    def is_local_multiplayer_turn(self):
        return self.mode_config["mode"] == "multiplayer" and self.current_actor() == self.mode_config["player_color"]

    def board_flipped(self):
        if self.mode_config["mode"] == "bot":
            return self.mode_config["player_color"] == "black"
        if self.mode_config["mode"] == "multiplayer":
            return self.mode_config["player_color"] == "black"
        if self.mode_config["mode"] == "spectator":
            return False
        return self.side_to_move == "white"

    def to_display_coords(self, row, col):
        if self.mode_config["mode"] in {"bot_vs_bot", "spectator"}:
            return col, BOARD_SIZE - 1 - row
        if self.board_flipped():
            return BOARD_SIZE - 1 - row, BOARD_SIZE - 1 - col
        return row, col

    def from_display_coords(self, draw_row, draw_col):
        if self.mode_config["mode"] in {"bot_vs_bot", "spectator"}:
            return BOARD_SIZE - 1 - draw_col, draw_row
        if self.board_flipped():
            return BOARD_SIZE - 1 - draw_row, BOARD_SIZE - 1 - draw_col
        return draw_row, draw_col

    def on_mouse_click(self, event):
        if self.animating or self.game_over or self.is_bot_turn() or self.pending_network_move is not None or self.bot_thinking or self.mode_config["mode"] == "spectator":
            return
        if self.mode_config["mode"] == "multiplayer" and not self.is_local_multiplayer_turn():
            return

        square_size, board_pixels, offset_x, offset_y = self.board_metrics()
        if not (offset_x <= event.x < offset_x + board_pixels and offset_y <= event.y < offset_y + board_pixels):
            return
        draw_col = int((event.x - offset_x) // square_size)
        draw_row = int((event.y - offset_y) // square_size)
        row, col = self.from_display_coords(draw_row, draw_col)
        if not in_bounds(row, col):
            return

        clicked_piece = self.board[row][col]

        if self.selected and any(move["to"] == (row, col) for move in self.legal_moves):
            move = next(move for move in self.legal_moves if move["to"] == (row, col))
            if self.mode_config["mode"] == "multiplayer":
                self.submit_multiplayer_move(move)
            else:
                self.execute_move(move)
            return

        if clicked_piece and piece_color(clicked_piece) == self.side_to_move:
            self.selected = (row, col)
            self.legal_moves = self.generate_legal_moves(row, col)
            if self.legal_moves:
                self.status_var.set(f"{self.app.ui_label('selected_piece')}: {PIECE_SYMBOLS[clicked_piece]}")
            else:
                self.status_var.set(self.app.ui_label("piece_no_legal"))
        else:
            self.selected = None
            self.legal_moves = []
            self.status_var.set(self.app.ui_label("pick_movable_enemy"))

        self.draw()

    def report_opponent(self):
        if self.mode_config["mode"] != "multiplayer" or self.network_client is None:
            return
        if not messagebox.askyesno(self.app.ui_label("report"), self.app.ui_label("confirm_report")):
            return
        self.network_client.send({"type": "report_player"})

    def ban_opponent(self):
        if self.mode_config["mode"] != "multiplayer" or self.network_client is None or not self.app.is_admin:
            return
        if not messagebox.askyesno(self.app.ui_label("ban"), self.app.ui_label("confirm_ban")):
            return
        self.network_client.send({"type": "ban_player"})

    def revoke_opponent_report_permission(self):
        if self.mode_config["mode"] != "multiplayer" or self.network_client is None or not self.app.is_admin:
            return
        if not messagebox.askyesno(self.app.ui_label("console_revoke_report"), self.app.ui_label("confirm_revoke_opponent_report")):
            return
        self.network_client.send({"type": "admin_revoke_opponent_report"})

    def ban_spectated_target(self):
        if self.mode_config["mode"] != "spectator" or self.network_client is None or not self.app.is_admin:
            return
        target_slot = self.mode_config.get("ban_target_slot")
        if target_slot not in {"host", "guest"}:
            return
        if not messagebox.askyesno(self.app.ui_label("ban"), self.app.ui_label("confirm_ban")):
            return
        self.network_client.send(
            {
                "type": "admin_ban_room_player",
                "room_code": self.mode_config.get("room_code", ""),
                "target_slot": target_slot,
            }
        )

    def toggle_spectate_target(self):
        if self.mode_config["mode"] != "spectator":
            return
        current = self.mode_config.get("ban_target_slot", "host")
        self.mode_config["ban_target_slot"] = "guest" if current == "host" else "host"
        self.update_sidebar()

    def generate_legal_moves(self, row, col):
        return self.generate_legal_moves_for_board(self.board, self.side_to_move, row, col)

    def generate_legal_moves_for_board(self, board, side_to_move, row, col):
        piece = board[row][col]
        if not piece:
            return []

        pseudo_moves = self.generate_pseudo_moves(board, row, col)
        legal_moves = []

        for move in pseudo_moves:
            next_board = self.simulate_move(board, move)
            if not self.is_in_check(next_board, side_to_move):
                legal_moves.append(move)
        return legal_moves

    def all_legal_moves_for_color(self, color):
        return self.all_legal_moves(self.board, color)

    def all_legal_moves(self, board, color):
        moves = []
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                piece = board[row][col]
                if piece and piece_color(piece) == color:
                    for move in self.generate_pseudo_moves(board, row, col):
                        next_board = self.simulate_move(board, move)
                        if not self.is_in_check(next_board, color):
                            moves.append(move)
        return moves

    def apply_move_state(self, board, side_to_move, score_white, score_black, move):
        next_board = self.simulate_move(board, move)
        next_white = score_white
        next_black = score_black
        if move["captured"]:
            points = PIECE_VALUES.get(move["captured"].lower(), 0)
            if side_to_move == "white":
                next_white += points
            else:
                next_black += points
        return next_board, opposite(side_to_move), next_white, next_black

    def repetition_key(self, board, side_to_move):
        return tuple(tuple(row) for row in board), side_to_move

    def generate_pseudo_moves(self, board, row, col):
        piece = board[row][col]
        if not piece:
            return []

        lower = piece.lower()
        if lower == "p":
            return self.generate_pawn_moves(board, row, col, piece)
        if lower == "n":
            return self.generate_knight_moves(board, row, col, piece)
        if lower == "b":
            return self.generate_sliding_moves(board, row, col, piece, [(-1, -1), (-1, 1), (1, -1), (1, 1)])
        if lower == "r":
            return self.generate_sliding_moves(board, row, col, piece, [(-1, 0), (1, 0), (0, -1), (0, 1)])
        if lower == "q":
            return self.generate_sliding_moves(
                board,
                row,
                col,
                piece,
                [(-1, -1), (-1, 1), (1, -1), (1, 1), (-1, 0), (1, 0), (0, -1), (0, 1)],
            )
        if lower == "k":
            return self.generate_king_moves(board, row, col, piece)
        return []

    def generate_pawn_moves(self, board, row, col, piece):
        moves = []
        direction = -1 if piece.isupper() else 1
        start_row = 6 if piece.isupper() else 1

        one_forward = row + direction
        if in_bounds(one_forward, col) and board[one_forward][col] == "":
            moves.append(self.make_move_dict(board, row, col, one_forward, col))
            two_forward = row + 2 * direction
            if row == start_row and in_bounds(two_forward, col) and board[two_forward][col] == "":
                moves.append(self.make_move_dict(board, row, col, two_forward, col))

        for dc in (-1, 1):
            target_row = row + direction
            target_col = col + dc
            if not in_bounds(target_row, target_col):
                continue
            target_piece = board[target_row][target_col]
            if target_piece and piece_color(target_piece) != piece_color(piece) and target_piece.lower() != "k":
                moves.append(self.make_move_dict(board, row, col, target_row, target_col))
        return moves

    def generate_knight_moves(self, board, row, col, piece):
        moves = []
        for dr, dc in [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]:
            nr = row + dr
            nc = col + dc
            if not in_bounds(nr, nc):
                continue
            target_piece = board[nr][nc]
            if target_piece and target_piece.lower() == "k":
                continue
            if target_piece and piece_color(target_piece) == piece_color(piece):
                continue
            moves.append(self.make_move_dict(board, row, col, nr, nc))
        return moves

    def generate_sliding_moves(self, board, row, col, piece, directions):
        moves = []
        for dr, dc in directions:
            nr = row + dr
            nc = col + dc
            while in_bounds(nr, nc):
                target_piece = board[nr][nc]
                if target_piece == "":
                    moves.append(self.make_move_dict(board, row, col, nr, nc))
                else:
                    if piece_color(target_piece) != piece_color(piece) and target_piece.lower() != "k":
                        moves.append(self.make_move_dict(board, row, col, nr, nc))
                    break
                nr += dr
                nc += dc
        return moves

    def generate_king_moves(self, board, row, col, piece):
        moves = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr = row + dr
                nc = col + dc
                if not in_bounds(nr, nc):
                    continue
                target_piece = board[nr][nc]
                if target_piece and target_piece.lower() == "k":
                    continue
                if target_piece and piece_color(target_piece) == piece_color(piece):
                    continue
                moves.append(self.make_move_dict(board, row, col, nr, nc))
        return moves

    def make_move_dict(self, board, from_row, from_col, to_row, to_col):
        piece = board[from_row][from_col]
        target = board[to_row][to_col]
        promotion = None
        if piece.lower() == "p" and (to_row == 0 or to_row == BOARD_SIZE - 1):
            promotion = "Q" if piece.isupper() else "q"

        return {
            "from": (from_row, from_col),
            "to": (to_row, to_col),
            "piece": piece,
            "captured": target,
            "promotion": promotion,
        }

    def simulate_move(self, board, move):
        next_board = deep_copy_board(board)
        from_row, from_col = move["from"]
        to_row, to_col = move["to"]
        moving_piece = next_board[from_row][from_col]
        next_board[from_row][from_col] = ""
        if move["promotion"]:
            moving_piece = move["promotion"]
        next_board[to_row][to_col] = moving_piece
        return next_board

    def find_king(self, board, color):
        target = "K" if color == "white" else "k"
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                if board[row][col] == target:
                    return (row, col)
        return None

    def is_in_check(self, board, color):
        return bool(self.find_checkers(board, color))

    def find_checkers(self, board, color):
        king_pos = self.find_king(board, color)
        if king_pos is None:
            return []

        enemy_color = opposite(color)
        checkers = []
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                piece = board[row][col]
                if piece and piece_color(piece) == enemy_color:
                    if self.piece_attacks_square(board, row, col, king_pos[0], king_pos[1]):
                        checkers.append({"row": row, "col": col, "piece": piece})
        return checkers

    def piece_attacks_square(self, board, from_row, from_col, target_row, target_col):
        piece = board[from_row][from_col]
        if not piece:
            return False

        lower = piece.lower()
        dr = target_row - from_row
        dc = target_col - from_col

        if lower == "p":
            direction = -1 if piece.isupper() else 1
            return dr == direction and abs(dc) == 1

        if lower == "n":
            return (abs(dr), abs(dc)) in {(1, 2), (2, 1)}

        if lower == "k":
            return max(abs(dr), abs(dc)) == 1

        if lower in {"b", "r", "q"}:
            step_row = 0
            step_col = 0

            if lower in {"b", "q"} and abs(dr) == abs(dc) and dr != 0:
                step_row = 1 if dr > 0 else -1
                step_col = 1 if dc > 0 else -1
            elif lower in {"r", "q"} and (dr == 0) != (dc == 0):
                step_row = 0 if dr == 0 else (1 if dr > 0 else -1)
                step_col = 0 if dc == 0 else (1 if dc > 0 else -1)
            else:
                return False

            row = from_row + step_row
            col = from_col + step_col
            while (row, col) != (target_row, target_col):
                if board[row][col] != "":
                    return False
                row += step_row
                col += step_col
            return True

        return False

    def attack_visual_path(self, piece, from_pos, king_pos):
        from_row, from_col = from_pos
        king_row, king_col = king_pos
        lower = piece.lower()

        if lower in {"b", "r", "q"}:
            path = []
            step_row = 0 if king_row == from_row else (1 if king_row > from_row else -1)
            step_col = 0 if king_col == from_col else (1 if king_col > from_col else -1)
            row = from_row
            col = from_col
            while (row, col) != (king_row, king_col):
                path.append((row, col))
                row += step_row
                col += step_col
            return path

        if lower == "n":
            return self.knight_visual_path(from_pos, king_pos)

        return [from_pos]

    def knight_visual_path(self, from_pos, king_pos):
        from_row, from_col = from_pos
        king_row, king_col = king_pos
        dr = king_row - from_row
        dc = king_col - from_col
        path = [from_pos]

        if abs(dr) == 2 and abs(dc) == 1:
            step = 1 if dr > 0 else -1
            path.append((from_row + step, from_col))
            path.append((from_row + 2 * step, from_col))
            return [square for square in path if in_bounds(square[0], square[1])]

        if abs(dr) == 1 and abs(dc) == 2:
            step = 1 if dc > 0 else -1
            path.append((from_row, from_col + step))
            path.append((from_row, from_col + 2 * step))
            return [square for square in path if in_bounds(square[0], square[1])]

        return path

    def execute_move(self, move):
        self.animating = True
        self.animating_from = move["from"]
        self.selected = None
        self.legal_moves = []

        from_row, from_col = move["from"]
        to_row, to_col = move["to"]
        start_draw_row, start_draw_col = self.to_display_coords(from_row, from_col)
        end_draw_row, end_draw_col = self.to_display_coords(to_row, to_col)
        moving_piece = move["piece"]
        captured_piece = move["captured"]

        self.draw()

        square_size, _, _, _ = self.board_metrics()
        piece_font_size = max(16, int(square_size * 0.52))

        start_x, start_y, _ = self.square_to_canvas(start_draw_row, start_draw_col)
        end_x, end_y, _ = self.square_to_canvas(end_draw_row, end_draw_col)
        start_x += square_size / 2
        start_y += square_size / 2
        end_x += square_size / 2
        end_y += square_size / 2

        moving_id = self.canvas.create_text(
            start_x,
            start_y,
            text=PIECE_SYMBOLS[moving_piece],
            font=("Segoe UI Symbol", piece_font_size),
            fill=TEXT_COLOR,
        )

        frames = 10
        dx = (end_x - start_x) / frames
        dy = (end_y - start_y) / frames

        def step(frame=0):
            if self.destroyed or not self.container.winfo_exists():
                return
            if frame < frames:
                self.canvas.move(moving_id, dx, dy)
                self.root.after(24, step, frame + 1)
            else:
                self.canvas.delete(moving_id)
                self.finish_move(move, captured_piece)

        step()

    def submit_multiplayer_move(self, move):
        if self.network_client is None:
            return
        self.pending_network_move = move
        self.selected = None
        self.legal_moves = []
        self.status_var.set("Lépés elküldve a szervernek...")
        self.draw()
        self.network_client.send(
            {
                "type": "submit_move",
                "move": {
                    "from": list(move["from"]),
                    "to": list(move["to"]),
                    "piece": move["piece"],
                    "captured": move["captured"],
                    "promotion": move["promotion"],
                },
            }
        )

    def apply_network_move(self, payload):
        move_payload = payload["move"]
        move = {
            "from": tuple(move_payload["from"]),
            "to": tuple(move_payload["to"]),
            "piece": move_payload["piece"],
            "captured": move_payload["captured"],
            "promotion": move_payload["promotion"],
        }
        self.pending_network_move = None
        self.pending_network_sync = payload
        self.execute_move(move)

    def finish_move(self, move, captured_piece):
        self.undo_stack.append(self.snapshot_state())
        self.redo_stack.clear()
        bot_turn_before_move = self.is_bot_turn()
        moving_side = self.side_to_move
        self.board = self.simulate_move(self.board, move)
        if move["promotion"]:
            promotion_piece = move["promotion"]
            if not bot_turn_before_move:
                chosen_piece = self.ask_promotion(piece_color(move["piece"]))
                if chosen_piece:
                    promotion_piece = chosen_piece
            to_row, to_col = move["to"]
            self.board[to_row][to_col] = promotion_piece

        if captured_piece:
            points = PIECE_VALUES.get(captured_piece.lower(), 0)
            if self.side_to_move == "white":
                self.score_white += points
            else:
                self.score_black += points

        if moving_side == "white":
            self.move_count += 1
        self.side_to_move = opposite(self.side_to_move)
        self.last_executed_move = {
            "piece": move["piece"],
            "from": move["from"],
            "to": move["to"],
        }
        self.move_history.append(self.last_executed_move.copy())
        self.state_history.append(self.repetition_key(self.board, self.side_to_move))
        server_sync = self.pending_network_sync
        self.pending_network_sync = None
        if server_sync is not None:
            if "score_white" in server_sync:
                self.score_white = server_sync["score_white"]
            if "score_black" in server_sync:
                self.score_black = server_sync["score_black"]
            if "move_count" in server_sync:
                self.move_count = server_sync["move_count"]
            if "side_to_move" in server_sync:
                self.side_to_move = server_sync["side_to_move"]
        self.animating = False
        self.animating_from = None
        self.draw()
        self.start_turn()
        if server_sync is not None and server_sync.get("game_over") and not self.game_over:
            self.end_game(server_sync.get("result_text", "A meccs véget ért."))

    def ask_promotion(self, color):
        choices = {
            "Q": "Vezér",
            "R": "Bástya",
            "B": "Futó",
            "N": "Huszár",
        }
        result = {"value": None}
        dialog = tk.Toplevel(self.root)
        dialog.title("Gyalog átalakulás")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg=BG_COLOR, padx=16, pady=16)

        tk.Label(
            dialog,
            text="Válassz új bábut:",
            font=("Segoe UI", 11, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(0, 10))

        def choose(code):
            result["value"] = code if color == "white" else code.lower()
            dialog.destroy()

        for code, label in choices.items():
            tk.Button(
                dialog,
                text=f"{PIECE_SYMBOLS[code if color == 'white' else code.lower()]}  {label}",
                width=16,
                command=lambda c=code: choose(c),
            ).pack(fill="x", pady=2)

        dialog.wait_window()
        return result["value"]

    def start_turn(self):
        if self.destroyed or not self.container.winfo_exists():
            return
        if self.game_over:
            return

        if self.state_history.count(self.repetition_key(self.board, self.side_to_move)) >= 3:
            self.end_game(self.score_winner_text("Állásismétlés. A pontszám döntött."))
            return

        legal_moves = self.all_legal_moves_for_color(self.side_to_move)
        in_check = self.is_in_check(self.board, self.side_to_move)

        if not legal_moves:
            if in_check:
                winner = opposite(self.side_to_move)
                self.end_game(f"Matt. {'FEHÉR' if winner == 'white' else 'FEKETE'} nyert.")
            else:
                self.end_game(self.score_winner_text("Patt. A pontszám döntött."))
            return

        if self.move_limit >= 0 and self.move_count >= self.move_limit:
            self.end_game(self.score_winner_text("Elértétek a lépéslimitet."))
            return

        if not in_check and self.mode_config["mode"] == "multiplayer":
            if self.is_local_multiplayer_turn():
                self.status_var.set("Te következel. Válassz egy bábut, majd kattints a célmezőre.")
            else:
                self.status_var.set("Az ellenfél lép.")
            self.draw()
            return

        if self.mode_config["mode"] == "spectator":
            self.status_var.set(self.app.ui_label("spectating_status"))
            self.draw()
            return

        if in_check:
            self.status_var.set("Sakk: a soron következő szín királya támadás alatt van, ezt a most kattintó játékosnak kell megoldania.")
        else:
            self.status_var.set("Válassz egy bábut, majd kattints a célmezőre.")
        self.draw()
        if self.is_bot_turn():
            if self.mode_config["mode"] == "bot_vs_bot" and self.bot_paused:
                self.status_var.set("Bot párbaj szüneteltetve.")
                self.draw()
                return
            self.status_var.set("A bot gondolkodik...")
            self.draw()
            self.root.after(self.app.bot_delay_ms(), self.run_bot_turn)

    def run_bot_turn(self):
        if self.destroyed or not self.container.winfo_exists():
            return
        if self.game_over or self.animating or not self.is_bot_turn() or self.bot_thinking:
            return
        if self.mode_config["mode"] == "bot_vs_bot" and self.bot_paused:
            return
        current_bot_color = self.current_actor()
        bot_engine = self.bot_engines.get(current_bot_color)
        if bot_engine is None:
            return
        self.bot_thinking = True
        self.status_var.set("A bot gondolkodik...")
        self.draw()

        def worker():
            try:
                move = bot_engine.choose_move()
                self.bot_result_queue.put(("move", move))
            except Exception as exc:
                self.bot_result_queue.put(("error", str(exc)))

        self.bot_thread = threading.Thread(target=worker, daemon=True)
        self.bot_thread.start()
        self.root.after(40, self.poll_bot_result)

    def poll_bot_result(self):
        if self.destroyed or not self.container.winfo_exists():
            self.bot_thinking = False
            self.bot_thread = None
            return
        if not self.bot_thinking:
            return
        try:
            result_type, payload = self.bot_result_queue.get_nowait()
        except queue.Empty:
            self.root.after(40, self.poll_bot_result)
            return

        self.bot_thinking = False
        self.bot_thread = None
        if result_type == "error":
            self.status_var.set(f"Bot hiba: {payload}")
            self.draw()
            return
        move = payload
        if self.mode_config["mode"] == "bot_vs_bot" and self.bot_paused:
            self.pending_bot_move = move
            self.status_var.set("Bot párbaj szüneteltetve.")
            self.draw()
            return
        if move is None or self.game_over or self.animating or not self.is_bot_turn():
            return
        self.execute_move(move)

    def score_winner_text(self, prefix):
        if self.score_white > self.score_black:
            return f"{prefix} FEHÉR nyert pontokkal."
        if self.score_black > self.score_white:
            return f"{prefix} FEKETE nyert pontokkal."
        return f"{prefix} Döntetlen."

    def end_game(self, message):
        self.game_over = True
        self.status_var.set(message)
        self.draw()
        self.app.report_finished_local_match(self)
        messagebox.showinfo("Játék vége", message)


class UnchessApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Unchess")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.resizable(True, True)
        self.root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)
        self.current_view = None
        self.pending_bot_difficulty = None
        self.pending_bvb = {}
        settings = load_client_settings()
        self.server_host = settings["server_host"]
        self.server_port = settings["server_port"]
        self.user_name = settings["user_name"]
        self.session_role = settings["session_role"]
        self.remember_token = settings["remember_token"]
        self.suppress_auth_prompt = settings["suppress_auth_prompt"]
        self.profile_stats = normalize_profile_stats(settings["profile_stats"])
        self.is_admin = self.session_role == "admin"
        self.session_confirmed = False
        self.language = settings["language"]
        self.auto_role_policy = settings["auto_role_policy"]
        self.bot_tempo = settings["bot_tempo"]
        self.default_move_limit = settings["move_limit"]
        self.multiplayer_client = None
        self.multiplayer_room = None
        self.multiplayer_status_var = None
        self.multiplayer_room_var = None
        self.multiplayer_join_code_var = None
        self.multiplayer_host_controls = None
        self.multiplayer_move_limit_var = None
        self.multiplayer_is_host = False
        self.admin_rooms_cache = []
        self.pending_multiplayer_action = None
        self.auth_username_var = None
        self.auth_password_var = None
        self.auth_remember_var = None
        self.delete_account_password_var = None
        self.delete_account_confirm_var = None
        self.console_target_username_var = None
        self.console_new_password_var = None
        self.console_reason_var = None
        self.console_users_cache = []
        self.console_search_var = None
        self.console_list_container = None
        self.console_selected_username = ""
        self.console_action_confirm_var = None
        self.ignore_next_disconnect = False
        self.settings_button = None
        self.settings_parent = None
        self.settings_panel = None
        self.settings_canvas = None
        self.settings_scrollable = None
        self.settings_anim_job = None
        self.settings_anchor_widget = None
        self.settings_icon_angle = 0.0
        self.settings_icon_scale = 1.0
        self.settings_hovered = False
        self.settings_anim_start = None
        self.settings_anim_duration_ms = 0
        self.settings_anim_from_angle = 0.0
        self.settings_anim_to_angle = 0.0
        self.settings_anim_from_scale = 1.0
        self.settings_anim_to_scale = 1.0
        self.settings_move_limit_var = None
        self.settings_host_var = None
        self.settings_port_var = None
        self.profile_button = None
        self.profile_panel = None
        self.profile_anchor_widget = None
        self.auth_target_screen = "main"
        self.account_prompt_remind_var = None
        self.account_prompt_username_var = None
        self.account_prompt_password_var = None
        self.profile_delete_back = None
        self.current_screen_refresh = None
        self.current_scroll_canvas = None
        self.global_return_action = None
        self.root.bind_all("<MouseWheel>", self.on_global_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self.on_global_mousewheel, add="+")
        self.root.bind_all("<Button-5>", self.on_global_mousewheel, add="+")
        self.root.after(120, self.poll_network_events)
        self.bootstrap_app()

    def bootstrap_app(self):
        if self.user_name and self.remember_token:
            self.show_main_menu()
            self.root.after(0, self.restore_saved_login)
            return
        if not self.user_name and not self.remember_token and not self.suppress_auth_prompt:
            self.show_startup_account_prompt()
            return
        self.show_main_menu()

    def on_app_close(self):
        self.close_multiplayer_client()
        self.root.destroy()

    def clear_view(self):
        self.clear_global_return_action()
        self.close_profile_panel(redraw_icon=False)
        self.close_settings_panel(redraw_icon=False)
        if self.current_view is not None:
            self.current_view.destroy()
            self.current_view = None
        self.current_scroll_canvas = None
        self.profile_button = None
        self.profile_anchor_widget = None
        self.settings_button = None
        self.settings_anchor_widget = None

    def set_global_return_action(self, callback):
        self.global_return_action = callback
        self.root.bind("<Return>", self.on_global_return)

    def clear_global_return_action(self):
        self.global_return_action = None
        self.root.unbind("<Return>")

    def on_global_return(self, _event):
        if callable(self.global_return_action):
            self.global_return_action()

    def create_scrollable_view(self, padx=40, pady=36):
        shell = tk.Frame(self.root, bg=BG_COLOR)
        shell.pack(fill="both", expand=True)
        canvas = tk.Canvas(shell, bg=BG_COLOR, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG_COLOR, padx=padx, pady=pady)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def sync_scrollbar():
            shell.update_idletasks()
            bbox = canvas.bbox("all")
            canvas.configure(scrollregion=bbox)
            needs_scroll = inner.winfo_reqheight() > canvas.winfo_height() + 1
            if needs_scroll:
                if not scrollbar.winfo_ismapped():
                    scrollbar.pack(side="right", fill="y")
            elif scrollbar.winfo_ismapped():
                scrollbar.pack_forget()

        def on_inner_configure(_event=None):
            sync_scrollbar()

        def on_canvas_configure(event):
            canvas.itemconfigure(window_id, width=event.width)
            sync_scrollbar()

        inner.bind("<Configure>", on_inner_configure)
        canvas.bind("<Configure>", on_canvas_configure)
        self.current_view = shell
        self.current_scroll_canvas = canvas
        return inner

    def on_global_mousewheel(self, event):
        canvas = self.current_scroll_canvas
        if canvas is None:
            return
        try:
            if not int(canvas.winfo_exists()):
                self.current_scroll_canvas = None
                return
        except tk.TclError:
            self.current_scroll_canvas = None
            return
        bbox = canvas.bbox("all")
        if not bbox:
            return
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            raw_delta = getattr(event, "delta", 0)
            if raw_delta == 0:
                return
            delta = -1 * int(raw_delta / 120 if raw_delta % 120 == 0 else (1 if raw_delta > 0 else -1))
        canvas.yview_scroll(delta, "units")

    def refresh_current_view_language(self):
        if isinstance(self.current_view, UnchessGame):
            self.current_view.refresh_language()
            return
        if self.current_screen_refresh is not None:
            self.current_screen_refresh()

    def close_multiplayer_client(self):
        self.ignore_next_disconnect = True
        if self.multiplayer_client is not None:
            self.multiplayer_client.close()
            self.multiplayer_client = None
        self.multiplayer_room = None
        self.session_confirmed = False
        self.admin_rooms_cache = []
        self.multiplayer_is_host = False
        self.multiplayer_status_var = None
        self.multiplayer_room_var = None
        self.multiplayer_join_code_var = None
        self.multiplayer_host_controls = None
        self.multiplayer_move_limit_var = None
        self.pending_multiplayer_action = None
        self.ignore_next_disconnect = False

    def reset_account_state(self):
        self.user_name = ""
        self.session_role = ""
        self.is_admin = False
        self.remember_token = ""
        self.session_confirmed = False
        self.profile_stats = default_profile_stats()
        self.console_users_cache = []
        self.console_selected_username = ""
        self.save_settings()

    def has_confirmed_account(self):
        return bool(self.session_confirmed and self.user_name and self.session_role in {"player", "admin", "console"})

    def update_profile_snapshot(self, profile):
        if not isinstance(profile, dict):
            return
        self.profile_stats = normalize_profile_stats(profile.get("stats"))
        if profile.get("username"):
            self.user_name = str(profile.get("username"))
        if profile.get("role") in {"player", "admin", "console"}:
            self.session_role = str(profile.get("role"))
            self.is_admin = self.session_role == "admin"
        self.save_settings()

    def after_successful_auth(self):
        if self.auth_target_screen == "multiplayer":
            self.show_post_login_multiplayer_view()
        else:
            if self.session_role == "console":
                self.show_console_placeholder()
            else:
                self.show_main_menu()

    def ensure_multiplayer_connection(self):
        if self.multiplayer_client is not None and self.multiplayer_client.connected:
            return
        client = MultiplayerClient(self.server_host, self.server_port)
        client.connect(name=self.user_name or "Unchess Player")
        self.ignore_next_disconnect = False
        self.multiplayer_client = client

    def show_multiplayer_entry(self):
        self.auth_target_screen = "multiplayer"
        if self.has_confirmed_account():
            self.show_post_login_multiplayer_view()
        elif self.remember_token:
            self.show_multiplayer_auth_menu()
            self.root.after(0, self.restore_saved_login)
        else:
            self.show_multiplayer_auth_menu()

    def show_post_login_multiplayer_view(self):
        if self.session_role == "console":
            self.show_console_placeholder()
            return
        self.show_multiplayer_placeholder()

    def poll_network_events(self):
        if self.multiplayer_client is not None:
            for event in self.multiplayer_client.poll_events():
                self.handle_network_event(event)
        self.root.after(120, self.poll_network_events)

    def show_main_menu(self):
        if self.has_confirmed_account() and self.session_role == "console":
            self.show_console_placeholder()
            return
        self.current_screen_refresh = self.show_main_menu
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text="Unchess",
            font=("Segoe UI", 30, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text=self.ui_label("choose_mode"),
            font=("Segoe UI", 13),
            bg=BG_COLOR,
            fg="#5a5a5a",
        ).pack(anchor="center", pady=(0, 24))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")

        self.menu_button(menu_card, self.ui_label("singleplayer"), self.start_singleplayer).pack(fill="x", pady=6)
        self.menu_button(menu_card, self.ui_label("multiplayer"), self.show_multiplayer_entry).pack(fill="x", pady=6)
        self.menu_button(menu_card, self.ui_label("bot"), self.show_bot_menu).pack(fill="x", pady=6)
        self.menu_button(menu_card, self.ui_label("bot_vs_bot"), self.show_bot_vs_bot_white_menu).pack(fill="x", pady=6)

        tk.Label(
            frame,
            text=self.ui_label("local_or_tcp"),
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg="#6a6a6a",
        ).pack(anchor="center", pady=(20, 0))

    def show_startup_account_prompt(self):
        self.auth_target_screen = "main"
        self.current_screen_refresh = self.show_startup_account_prompt
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text=self.ui_label("account_prompt_title"),
            font=("Segoe UI", 28, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(14, 8))
        tk.Label(
            frame,
            text=self.ui_label("account_prompt_subtitle"),
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
            wraplength=620,
            justify="center",
        ).pack(anchor="center", pady=(0, 20))

        card = tk.Frame(frame, bg="#efe5d8", padx=24, pady=24)
        card.pack(anchor="center")
        self.account_prompt_remind_var = tk.BooleanVar(value=False)

        self.menu_button(card, self.ui_label("login"), lambda: self.show_startup_auth_menu("login")).pack(fill="x")
        tk.Button(
            card,
            text=self.ui_label("switch_to_register"),
            command=lambda: self.show_startup_auth_menu("register"),
            font=("Segoe UI", 10, "bold"),
            bg="#efe5d8",
            fg="#5b3b26",
            relief="flat",
            cursor="hand2",
            anchor="center",
            justify="center",
            wraplength=340,
        ).pack(anchor="center", pady=(10, 2))

        guest_button = tk.Button(
            card,
            text=self.ui_label("continue_as_guest"),
            command=self.continue_as_guest,
            font=("Segoe UI", 10),
            bg="#efe5d8",
            fg="#6a5240",
            relief="flat",
            cursor="hand2",
            padx=6,
            pady=4,
        )
        guest_button.pack(anchor="center", pady=(12, 6))
        tk.Checkbutton(
            card,
            text=self.ui_label("dont_remind_again"),
            variable=self.account_prompt_remind_var,
            bg="#efe5d8",
            fg="#6a5240",
            activebackground="#efe5d8",
            selectcolor="#efe5d8",
        ).pack(anchor="center")

    def show_startup_auth_menu(self, mode):
        self.auth_target_screen = "main"
        self.current_screen_refresh = lambda m=mode: self.show_startup_auth_menu(m)
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        title_key = "login" if mode == "login" else "register"
        tk.Label(frame, text=self.ui_label(title_key), font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(
            frame,
            text=self.ui_label("account_auth_subtitle"),
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
            wraplength=620,
            justify="center",
        ).pack(anchor="center", pady=(0, 18))

        card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        card.pack(anchor="center")

        self.account_prompt_username_var = tk.StringVar(value=self.user_name)
        self.account_prompt_password_var = tk.StringVar()
        self.auth_username_var = self.account_prompt_username_var
        self.auth_password_var = self.account_prompt_password_var
        self.auth_remember_var = tk.BooleanVar(value=True if mode == "login" else False)

        submit_action = self.submit_login if mode == "login" else self.submit_register
        tk.Label(card, text=self.ui_label("username"), font=("Segoe UI", 11, "bold"), bg="#efe5d8", fg=TEXT_COLOR).pack(anchor="w")
        username_entry = tk.Entry(card, textvariable=self.auth_username_var, font=("Segoe UI", 12), width=28)
        username_entry.pack(fill="x", pady=(4, 12))
        tk.Label(card, text=self.ui_label("password"), font=("Segoe UI", 11, "bold"), bg="#efe5d8", fg=TEXT_COLOR).pack(anchor="w")
        password_entry = tk.Entry(card, textvariable=self.auth_password_var, font=("Segoe UI", 12), show="*", width=28)
        password_entry.pack(fill="x", pady=(4, 10))
        username_entry.bind("<Return>", lambda _event: submit_action())
        password_entry.bind("<Return>", lambda _event: submit_action())
        username_entry.focus_set()
        if self.auth_username_var.get().strip():
            password_entry.focus_set()
        if mode == "login":
            tk.Checkbutton(card, text=self.ui_label("remember_me"), variable=self.auth_remember_var, bg="#efe5d8", activebackground="#efe5d8").pack(anchor="w", pady=(0, 12))
            self.menu_button(card, self.ui_label("login"), self.submit_login).pack(fill="x", pady=4)
            tk.Button(
                card,
                text=self.ui_label("switch_to_register"),
                command=lambda: self.show_startup_auth_menu("register"),
                font=("Segoe UI", 10, "bold"),
                bg="#efe5d8",
                fg="#5b3b26",
                relief="flat",
                cursor="hand2",
                anchor="center",
                justify="center",
                wraplength=340,
            ).pack(anchor="center", pady=(10, 0))
        else:
            self.menu_button(card, self.ui_label("register"), self.submit_register).pack(fill="x", pady=4)
            tk.Button(
                card,
                text=self.ui_label("switch_to_login"),
                command=lambda: self.show_startup_auth_menu("login"),
                font=("Segoe UI", 10, "bold"),
                bg="#efe5d8",
                fg="#5b3b26",
                relief="flat",
                cursor="hand2",
                anchor="center",
                justify="center",
                wraplength=340,
            ).pack(anchor="center", pady=(10, 0))
        tk.Button(frame, text=self.ui_label("back"), command=self.show_startup_account_prompt, padx=12).pack(pady=(18, 0))

    def show_bot_menu(self):
        self.current_screen_refresh = self.show_bot_menu
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text=self.ui_label("bot_difficulty"),
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text=self.ui_label("bot_difficulty_subtitle"),
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
            wraplength=560,
            justify="center",
        ).pack(anchor="center", pady=(0, 24))

        tk.Label(
            frame,
            text=f"{self.ui_label('auto_role_policy')}: {self.role_policy_label(self.auto_role_policy)}",
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg="#6a6a6a",
        ).pack(anchor="center", pady=(0, 12))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")

        difficulties = [
            ("easy", self.ui_label("easy")),
            ("normal", self.ui_label("normal")),
            ("hard", self.ui_label("hard")),
            ("unbeatable", self.ui_label("unbeatable")),
        ]
        for difficulty, label in difficulties:
            self.menu_button(
                menu_card,
                label,
                lambda d=difficulty, l=label: self.show_bot_color_menu(d, l),
            ).pack(fill="x", pady=6)

        tk.Button(frame, text=self.ui_label("back"), command=self.show_main_menu, padx=12).pack(pady=(18, 0))

    def show_match_options(self, title, subtitle, start_callback, back_callback):
        self.current_screen_refresh = lambda: self.show_match_options(title, subtitle, start_callback, back_callback)
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text=title,
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text=subtitle,
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
            wraplength=560,
            justify="center",
        ).pack(anchor="center", pady=(0, 24))

        card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        card.pack(anchor="center")

        tk.Label(card, text=self.ui_label("move_limit"), font=("Segoe UI", 11, "bold"), bg="#efe5d8", fg=TEXT_COLOR).pack(anchor="w")
        tk.Label(
            card,
            text=self.ui_label("move_limit_hint"),
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg="#6a6a6a",
        ).pack(anchor="w", pady=(2, 8))

        move_limit_var = tk.StringVar(value=str(self.default_move_limit))
        self.settings_move_limit_var = move_limit_var
        self.settings_move_limit_var = move_limit_var
        entry = tk.Entry(card, textvariable=move_limit_var, font=("Consolas", 18), justify="center", width=10)
        entry.pack(anchor="center", pady=(0, 16))
        entry.focus_set()

        def begin():
            try:
                move_limit = int(move_limit_var.get().strip())
            except ValueError:
                messagebox.showerror(self.ui_label("start"), self.ui_label("launch_error"))
                return
            start_callback(move_limit)

        self.menu_button(card, self.ui_label("start"), begin).pack(fill="x", pady=6)
        tk.Button(frame, text=self.ui_label("back"), command=back_callback, padx=12).pack(pady=(18, 0))

    def show_bot_vs_bot_white_menu(self):
        self.pending_bvb = {}
        self.show_bot_vs_bot_selector("white")

    def show_bot_vs_bot_black_menu(self):
        self.show_bot_vs_bot_selector("black")

    def show_bot_vs_bot_selector(self, color):
        self.current_screen_refresh = lambda c=color: self.show_bot_vs_bot_selector(c)
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        side_label = self.ui_label("white_bot") if color == "white" else self.ui_label("black_bot")
        tk.Label(
            frame,
            text=f"{side_label} {self.ui_label('difficulty_suffix')}",
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text=self.ui_label("bot_select_subtitle"),
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
        ).pack(anchor="center", pady=(0, 24))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")

        difficulties = [
            ("easy", self.ui_label("easy")),
            ("normal", self.ui_label("normal")),
            ("hard", self.ui_label("hard")),
            ("unbeatable", self.ui_label("unbeatable")),
        ]
        for difficulty, label in difficulties:
            self.menu_button(
                menu_card,
                label,
                lambda d=difficulty, l=label, c=color: self.select_bvb_difficulty(c, d, l),
            ).pack(fill="x", pady=6)

        tk.Button(
            frame,
            text=self.ui_label("back"),
            command=self.show_main_menu if color == "white" else self.show_bot_vs_bot_white_menu,
            padx=12,
        ).pack(pady=(18, 0))

    def select_bvb_difficulty(self, color, difficulty, label):
        self.pending_bvb[color] = {"difficulty": difficulty, "label": label}
        if color == "white":
            self.show_bot_vs_bot_black_menu()
        else:
            self.show_match_options(
                self.ui_label("bot_vs_bot"),
                self.ui_label("move_limit_hint"),
                self.start_bot_vs_bot_game,
                self.show_bot_vs_bot_black_menu,
            )

    def show_bot_color_menu(self, difficulty, label):
        self.current_screen_refresh = lambda d=difficulty, l=label: self.show_bot_color_menu(d, l)
        self.pending_bot_difficulty = {"difficulty": difficulty, "label": label}
        if self.auto_role_policy != "ask":
            self.show_match_options(
                self.ui_label("bot_match"),
                self.ui_label("move_limit_hint"),
                lambda move_limit: self.start_bot_game(self.resolve_player_color(self.auto_role_policy), move_limit),
                self.show_bot_menu,
            )
            return
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text=self.ui_label("your_color"),
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text=self.ui_label("what_color"),
            font=("Segoe UI", 12),
            bg=BG_COLOR,
            fg="#5a5a5a",
        ).pack(anchor="center", pady=(0, 24))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")

        self.menu_button(menu_card, self.ui_label("white"), lambda: self.show_bot_match_options("white")).pack(fill="x", pady=6)
        self.menu_button(menu_card, self.ui_label("black"), lambda: self.show_bot_match_options("black")).pack(fill="x", pady=6)
        self.menu_button(menu_card, self.ui_label("random"), self.start_random_bot_game).pack(fill="x", pady=6)

        tk.Button(frame, text=self.ui_label("back"), command=self.show_bot_menu, padx=12).pack(pady=(18, 0))

    def show_multiplayer_auth_menu(self, mode="login"):
        self.auth_target_screen = "multiplayer"
        self.current_screen_refresh = lambda m=mode: self.show_multiplayer_auth_menu(m)
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        title_key = "login" if mode == "login" else "register"
        tk.Label(frame, text=self.ui_label(title_key), font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text=f"{self.ui_label('server')}: {self.server_host}:{self.server_port}", font=("Segoe UI", 11), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center", pady=(0, 18))

        card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        card.pack(anchor="center")

        self.auth_username_var = tk.StringVar(value=self.user_name)
        self.auth_password_var = tk.StringVar()
        self.auth_remember_var = tk.BooleanVar(value=bool(self.remember_token) if mode == "login" else False)

        submit_action = self.submit_login if mode == "login" else self.submit_register
        tk.Label(card, text=self.ui_label("username"), font=("Segoe UI", 11, "bold"), bg="#efe5d8", fg=TEXT_COLOR).pack(anchor="w")
        username_entry = tk.Entry(card, textvariable=self.auth_username_var, font=("Segoe UI", 12), width=28)
        username_entry.pack(fill="x", pady=(4, 12))
        tk.Label(card, text=self.ui_label("password"), font=("Segoe UI", 11, "bold"), bg="#efe5d8", fg=TEXT_COLOR).pack(anchor="w")
        password_entry = tk.Entry(card, textvariable=self.auth_password_var, font=("Segoe UI", 12), show="*", width=28)
        password_entry.pack(fill="x", pady=(4, 10))
        username_entry.bind("<Return>", lambda _event: submit_action())
        password_entry.bind("<Return>", lambda _event: submit_action())
        username_entry.focus_set()
        if self.auth_username_var.get().strip():
            password_entry.focus_set()
        if mode == "login":
            tk.Checkbutton(card, text=self.ui_label("remember_me"), variable=self.auth_remember_var, bg="#efe5d8", activebackground="#efe5d8").pack(anchor="w", pady=(0, 12))
            self.menu_button(card, self.ui_label("login"), self.submit_login).pack(fill="x", pady=4)
            tk.Button(
                card,
                text=self.ui_label("switch_to_register"),
                command=lambda: self.show_multiplayer_auth_menu("register"),
                font=("Segoe UI", 10, "bold"),
                bg="#efe5d8",
                fg="#5b3b26",
                relief="flat",
                cursor="hand2",
                anchor="center",
                justify="center",
                wraplength=340,
            ).pack(anchor="center", pady=(10, 0))
            if self.remember_token:
                self.menu_button(card, self.ui_label("stored_login"), self.restore_saved_login).pack(fill="x", pady=(10, 4))
        else:
            self.menu_button(card, self.ui_label("register"), self.submit_register).pack(fill="x", pady=4)
            tk.Button(
                card,
                text=self.ui_label("switch_to_login"),
                command=lambda: self.show_multiplayer_auth_menu("login"),
                font=("Segoe UI", 10, "bold"),
                bg="#efe5d8",
                fg="#5b3b26",
                relief="flat",
                cursor="hand2",
                anchor="center",
                justify="center",
                wraplength=340,
            ).pack(anchor="center", pady=(10, 0))
        tk.Button(frame, text=self.ui_label("back"), command=self.show_main_menu, padx=12).pack(pady=(18, 0))

    def continue_as_guest(self):
        self.suppress_auth_prompt = bool(self.account_prompt_remind_var.get()) if self.account_prompt_remind_var is not None else False
        self.save_settings()
        self.show_main_menu()

    def show_delete_account_menu(self):
        if not self.user_name:
            self.show_multiplayer_auth_menu()
            return
        self.current_screen_refresh = self.show_delete_account_menu
        self.clear_view()
        frame = self.create_scrollable_view()

        tk.Label(frame, text=self.ui_label("delete_account"), font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text=self.ui_label("delete_account_warning"), font=("Segoe UI", 11), bg=BG_COLOR, fg="#5a5a5a", wraplength=560, justify="center").pack(anchor="center", pady=(0, 18))
        tk.Label(frame, text=f"{self.ui_label('account')}: {self.user_name}", font=("Segoe UI", 11, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(0, 18))

        card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        card.pack(anchor="center")
        self.delete_account_password_var = tk.StringVar()
        self.delete_account_confirm_var = tk.StringVar()
        tk.Label(card, text=self.ui_label("password"), font=("Segoe UI", 11, "bold"), bg="#efe5d8", fg=TEXT_COLOR).pack(anchor="w")
        tk.Entry(card, textvariable=self.delete_account_password_var, font=("Segoe UI", 12), show="*", width=28).pack(fill="x", pady=(4, 12))
        tk.Label(card, text=self.ui_label("confirm_password"), font=("Segoe UI", 11, "bold"), bg="#efe5d8", fg=TEXT_COLOR).pack(anchor="w")
        tk.Entry(card, textvariable=self.delete_account_confirm_var, font=("Segoe UI", 12), show="*", width=28).pack(fill="x", pady=(4, 12))
        self.menu_button(card, self.ui_label("delete_account"), self.submit_delete_account).pack(fill="x", pady=4)
        back_action = self.profile_delete_back if callable(self.profile_delete_back) else self.show_main_menu
        tk.Button(frame, text=self.ui_label("back"), command=back_action, padx=12).pack(pady=(18, 0))

    def show_multiplayer_placeholder(self):
        self.current_screen_refresh = self.show_multiplayer_placeholder
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text=self.ui_label("multiplayer"),
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text=f"{self.ui_label('server')}: {self.server_host}:{self.server_port}",
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
            wraplength=560,
            justify="center",
        ).pack(anchor="center", pady=(0, 24))

        if self.has_confirmed_account():
            suffix = " (admin)" if self.is_admin else ""
            tk.Label(frame, text=f"{self.ui_label('logged_in')}: {self.user_name}{suffix}", font=("Segoe UI", 11, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(0, 18))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")

        self.menu_button(menu_card, self.ui_label("create_room"), self.multiplayer_create_room).pack(fill="x", pady=6)
        self.menu_button(menu_card, self.ui_label("join_room"), self.show_multiplayer_join_menu).pack(fill="x", pady=6)
        self.set_global_return_action(self.multiplayer_create_room)
        if self.is_admin:
            self.menu_button(menu_card, self.ui_label("active_rooms"), self.show_admin_rooms_menu).pack(fill="x", pady=6)
        tk.Label(
            frame,
            text=f"{self.ui_label('host_auto_role')}: {self.role_policy_label(self.auto_role_policy)}",
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg="#6a6a6a",
        ).pack(anchor="center", pady=(18, 0))

        if self.has_confirmed_account():
            tk.Button(frame, text=self.ui_label("logout"), command=self.submit_logout, padx=12).pack(pady=(18, 0))
        tk.Button(frame, text=self.ui_label("back"), command=self.show_main_menu, padx=12).pack(pady=(18, 0))

    def show_console_placeholder(self):
        self.current_screen_refresh = self.show_console_placeholder
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text=self.ui_label("console_title"),
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text=f"{self.ui_label('logged_in')}: {self.user_name} ({self.ui_label('console_role')})",
            font=("Segoe UI", 11, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(0, 16))

        tk.Label(
            frame,
            text=self.ui_label("console_placeholder_text"),
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
            wraplength=620,
            justify="center",
        ).pack(anchor="center", pady=(0, 20))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")
        self.menu_button(menu_card, self.ui_label("player_list"), self.show_console_player_list).pack(fill="x", pady=4)
        self.menu_button(menu_card, self.ui_label("console_refresh"), self.request_console_snapshot).pack(fill="x", pady=4)
        tk.Label(
            menu_card,
            text=self.ui_label("console_tools_soon"),
            font=("Segoe UI", 10),
            bg="#efe5d8",
            fg="#6a6a6a",
            wraplength=420,
            justify="center",
        ).pack(anchor="center", pady=(10, 0))

        tk.Button(frame, text=self.ui_label("logout"), command=self.submit_logout, padx=12).pack(pady=(18, 0))

    def sorted_console_users(self):
        users = []
        for record in self.console_users_cache:
            username = str(record.get("username", "") or "")
            if not username or self.session_role == "console" and username == self.user_name:
                continue
            users.append(record)
        admins = sorted((u for u in users if u.get("is_admin")), key=lambda item: item.get("username", ""))
        regulars = sorted((u for u in users if not u.get("is_admin")), key=lambda item: item.get("username", ""))
        return admins + regulars

    def filtered_console_users(self):
        query = (self.console_search_var.get() if self.console_search_var is not None else "").strip().lower()
        users = self.sorted_console_users()
        if not query:
            return users
        return [record for record in users if query in str(record.get("username", "")).lower()]

    def show_console_player_list(self):
        self.current_screen_refresh = self.show_console_player_list
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(frame, text=self.ui_label("player_list"), font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text=self.ui_label("console_players_subtitle"), font=("Segoe UI", 11), bg=BG_COLOR, fg="#5a5a5a", wraplength=620, justify="center").pack(anchor="center", pady=(0, 18))

        search_card = tk.Frame(frame, bg="#efe5d8", padx=18, pady=18)
        search_card.pack(anchor="center", fill="x")
        tk.Label(search_card, text=self.ui_label("search"), font=("Segoe UI", 11, "bold"), bg="#efe5d8", fg=TEXT_COLOR).pack(anchor="w")
        self.console_search_var = tk.StringVar()
        search_entry = tk.Entry(search_card, textvariable=self.console_search_var, font=("Segoe UI", 12))
        search_entry.pack(fill="x", pady=(6, 0))
        search_entry.focus_set()

        list_card = tk.Frame(frame, bg="#efe5d8", padx=18, pady=18)
        list_card.pack(anchor="center", fill="both", expand=True, pady=(14, 0))
        self.console_list_container = list_card
        self.console_search_var.trace_add("write", lambda *_args: self.render_console_player_rows())
        self.render_console_player_rows()

        action_row = tk.Frame(frame, bg=BG_COLOR)
        action_row.pack(anchor="center", pady=(18, 0))
        tk.Button(action_row, text=self.ui_label("console_refresh"), command=self.request_console_snapshot, padx=12).pack(side="left", padx=4)
        tk.Button(action_row, text=self.ui_label("back"), command=self.show_console_placeholder, padx=12).pack(side="left", padx=4)

    def render_console_player_rows(self):
        if self.console_list_container is None:
            return
        for child in self.console_list_container.winfo_children():
            child.destroy()
        users = self.filtered_console_users()
        if not users:
            tk.Label(self.console_list_container, text=self.ui_label("console_empty_snapshot"), font=("Segoe UI", 11), bg="#efe5d8", fg="#5a5a5a").pack(anchor="center", pady=12)
            return
        for record in users:
            username = str(record.get("username", "?"))
            status_bits = []
            if record.get("is_admin"):
                status_bits.append(self.ui_label("admin"))
            if record.get("is_banned"):
                status_bits.append(self.ui_label("banned"))
            suffix = f" [{', '.join(status_bits)}]" if status_bits else ""
            row = tk.Frame(self.console_list_container, bg="#efe5d8", pady=4)
            row.pack(fill="x")
            tk.Button(
                row,
                text=f"{username}{suffix}",
                command=lambda u=username: self.show_console_account_details(u),
                font=("Consolas", 11),
                bg="#f7efe4",
                fg=TEXT_COLOR,
                relief="raised",
                cursor="hand2",
                anchor="w",
                padx=12,
                pady=8,
            ).pack(fill="x")

    def find_console_user(self, username):
        for record in self.console_users_cache:
            if str(record.get("username", "")).lower() == str(username).lower():
                return record
        return None

    def show_console_account_details(self, username):
        record = self.find_console_user(username)
        if record is None:
            messagebox.showerror(self.ui_label("console_title"), self.ui_label("console_target_required"))
            return
        self.console_selected_username = str(record.get("username", username))
        self.current_screen_refresh = lambda u=self.console_selected_username: self.show_console_account_details(u)
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(frame, text=self.console_selected_username, font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        details = []
        details.append(self.ui_label("admin") if record.get("is_admin") else self.ui_label("player"))
        details.append(self.ui_label("banned") if record.get("is_banned") else self.ui_label("not_banned"))
        details.append(self.ui_label("report_allowed") if record.get("can_report", True) else self.ui_label("report_revoked"))
        tk.Label(frame, text=" | ".join(details), font=("Segoe UI", 11), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center", pady=(0, 18))
        stats = normalize_profile_stats(record.get("stats"))
        tk.Label(frame, text=self.ui_label("multiplayer_stats"), font=("Segoe UI", 10, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center")
        tk.Label(frame, text=self.format_external_stats_text(stats, "multiplayer"), font=("Consolas", 10), bg=BG_COLOR, fg="#5a5a5a", justify="center").pack(anchor="center", pady=(0, 8))
        tk.Label(frame, text=self.ui_label("bot_stats"), font=("Segoe UI", 10, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center")
        tk.Label(frame, text=self.format_external_stats_text(stats, "bot"), font=("Consolas", 10), bg=BG_COLOR, fg="#5a5a5a", justify="center").pack(anchor="center", pady=(0, 18))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")
        self.menu_button(menu_card, self.ui_label("console_reset_password"), lambda u=self.console_selected_username: self.show_console_password_reset_menu(u)).pack(fill="x", pady=4)
        self.menu_button(menu_card, self.ui_label("console_clear_balance"), lambda u=self.console_selected_username: self.show_console_clear_balance_menu(u)).pack(fill="x", pady=4)
        self.menu_button(menu_card, self.ui_label("console_delete_user"), lambda u=self.console_selected_username: self.show_console_delete_user_menu(u)).pack(fill="x", pady=4)
        if record.get("is_banned"):
            self.menu_button(menu_card, self.ui_label("console_unban_user"), lambda u=self.console_selected_username: self.show_console_ban_action_menu(u, False)).pack(fill="x", pady=4)
        else:
            self.menu_button(menu_card, self.ui_label("console_ban_user"), lambda u=self.console_selected_username: self.show_console_ban_action_menu(u, True)).pack(fill="x", pady=4)
        if record.get("is_admin"):
            self.menu_button(menu_card, self.ui_label("console_remove_admin"), lambda u=self.console_selected_username: self.show_console_admin_action_menu(u, False)).pack(fill="x", pady=4)
        else:
            self.menu_button(menu_card, self.ui_label("console_make_admin"), lambda u=self.console_selected_username: self.show_console_admin_action_menu(u, True)).pack(fill="x", pady=4)
        if record.get("can_report", True):
            self.menu_button(menu_card, self.ui_label("console_revoke_report"), lambda u=self.console_selected_username: self.show_console_report_action_menu(u, False)).pack(fill="x", pady=4)
        else:
            self.menu_button(menu_card, self.ui_label("console_grant_report"), lambda u=self.console_selected_username: self.show_console_report_action_menu(u, True)).pack(fill="x", pady=4)

        tk.Button(frame, text=self.ui_label("back"), command=self.show_console_player_list, padx=12).pack(pady=(18, 0))

    def show_console_password_reset_menu(self, username):
        self.console_selected_username = username
        self.current_screen_refresh = lambda u=username: self.show_console_password_reset_menu(u)
        self.clear_view()
        frame = self.create_scrollable_view()
        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)
        tk.Label(frame, text=self.ui_label("console_reset_password"), font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text=username, font=("Segoe UI", 11, "bold"), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center", pady=(0, 18))
        card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        card.pack(anchor="center")
        self.console_new_password_var = tk.StringVar()
        self.console_action_confirm_var = tk.BooleanVar(value=False)
        tk.Label(card, text=self.ui_label("new_password"), font=("Segoe UI", 11, "bold"), bg="#efe5d8", fg=TEXT_COLOR).pack(anchor="w")
        password_entry = tk.Entry(card, textvariable=self.console_new_password_var, show="*", font=("Segoe UI", 12), width=28)
        password_entry.pack(fill="x", pady=(4, 12))
        tk.Checkbutton(card, text=self.ui_label("console_action_confirm"), variable=self.console_action_confirm_var, bg="#efe5d8", activebackground="#efe5d8", justify="left", wraplength=360).pack(anchor="w", pady=(0, 12))
        password_entry.focus_set()
        password_entry.bind("<Return>", lambda _event: self.submit_console_password_reset())
        self.menu_button(card, self.ui_label("save_new_password"), self.submit_console_password_reset).pack(fill="x", pady=4)
        tk.Button(frame, text=self.ui_label("back"), command=lambda u=username: self.show_console_account_details(u), padx=12).pack(pady=(18, 0))

    def show_console_delete_user_menu(self, username):
        self.console_selected_username = username
        self.current_screen_refresh = lambda u=username: self.show_console_delete_user_menu(u)
        self.clear_view()
        frame = self.create_scrollable_view()
        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)
        tk.Label(frame, text=self.ui_label("console_delete_user"), font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text=username, font=("Segoe UI", 11, "bold"), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center", pady=(0, 18))
        card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        card.pack(anchor="center")
        self.console_action_confirm_var = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text=self.ui_label("console_delete_confirm"), variable=self.console_action_confirm_var, bg="#efe5d8", activebackground="#efe5d8", justify="left", wraplength=360).pack(anchor="w", pady=(0, 12))
        self.menu_button(card, self.ui_label("delete_account"), self.submit_console_delete_user).pack(fill="x", pady=4)
        tk.Button(frame, text=self.ui_label("back"), command=lambda u=username: self.show_console_account_details(u), padx=12).pack(pady=(18, 0))

    def show_console_clear_balance_menu(self, username):
        self.console_selected_username = username
        self.current_screen_refresh = lambda u=username: self.show_console_clear_balance_menu(u)
        self.clear_view()
        frame = self.create_scrollable_view()
        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)
        tk.Label(frame, text=self.ui_label("console_clear_balance"), font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text=username, font=("Segoe UI", 11, "bold"), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center", pady=(0, 18))
        record = self.find_console_user(username) or {}
        stats = normalize_profile_stats(record.get("stats"))
        tk.Label(frame, text=self.ui_label("multiplayer_stats"), font=("Segoe UI", 10, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center")
        tk.Label(frame, text=self.format_external_stats_text(stats, "multiplayer"), font=("Consolas", 10), bg=BG_COLOR, fg="#5a5a5a", justify="center").pack(anchor="center", pady=(0, 8))
        tk.Label(frame, text=self.ui_label("bot_stats"), font=("Segoe UI", 10, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center")
        tk.Label(frame, text=self.format_external_stats_text(stats, "bot"), font=("Consolas", 10), bg=BG_COLOR, fg="#5a5a5a", justify="center").pack(anchor="center", pady=(0, 18))
        card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        card.pack(anchor="center")
        self.console_action_confirm_var = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text=self.ui_label("console_clear_balance_confirm"), variable=self.console_action_confirm_var, bg="#efe5d8", activebackground="#efe5d8", justify="left", wraplength=360).pack(anchor="w", pady=(0, 12))
        self.menu_button(card, self.ui_label("console_clear_balance"), self.submit_console_clear_balance).pack(fill="x", pady=4)
        tk.Button(frame, text=self.ui_label("back"), command=lambda u=username: self.show_console_account_details(u), padx=12).pack(pady=(18, 0))

    def show_console_ban_action_menu(self, username, should_ban):
        self.console_selected_username = username
        self.current_screen_refresh = lambda u=username, b=should_ban: self.show_console_ban_action_menu(u, b)
        self.clear_view()
        frame = self.create_scrollable_view()
        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)
        title = self.ui_label("console_ban_user") if should_ban else self.ui_label("console_unban_user")
        tk.Label(frame, text=title, font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text=username, font=("Segoe UI", 11, "bold"), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center", pady=(0, 18))
        card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        card.pack(anchor="center")
        self.console_reason_var = tk.StringVar()
        if should_ban:
            tk.Label(card, text=self.ui_label("reason"), font=("Segoe UI", 11, "bold"), bg="#efe5d8", fg=TEXT_COLOR).pack(anchor="w")
            tk.Entry(card, textvariable=self.console_reason_var, font=("Segoe UI", 12), width=28).pack(fill="x", pady=(4, 12))
        self.console_action_confirm_var = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text=self.ui_label("console_action_confirm"), variable=self.console_action_confirm_var, bg="#efe5d8", activebackground="#efe5d8", justify="left", wraplength=360).pack(anchor="w", pady=(0, 12))
        self.menu_button(card, title, self.submit_console_ban_user if should_ban else self.submit_console_unban_user).pack(fill="x", pady=4)
        tk.Button(frame, text=self.ui_label("back"), command=lambda u=username: self.show_console_account_details(u), padx=12).pack(pady=(18, 0))

    def show_console_admin_action_menu(self, username, make_admin):
        self.console_selected_username = username
        self.current_screen_refresh = lambda u=username, a=make_admin: self.show_console_admin_action_menu(u, a)
        self.clear_view()
        frame = self.create_scrollable_view()
        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)
        title = self.ui_label("console_make_admin") if make_admin else self.ui_label("console_remove_admin")
        tk.Label(frame, text=title, font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text=username, font=("Segoe UI", 11, "bold"), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center", pady=(0, 18))
        card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        card.pack(anchor="center")
        self.console_action_confirm_var = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text=self.ui_label("console_action_confirm"), variable=self.console_action_confirm_var, bg="#efe5d8", activebackground="#efe5d8", justify="left", wraplength=360).pack(anchor="w", pady=(0, 12))
        self.menu_button(card, title, self.submit_console_make_admin if make_admin else self.submit_console_remove_admin).pack(fill="x", pady=4)
        tk.Button(frame, text=self.ui_label("back"), command=lambda u=username: self.show_console_account_details(u), padx=12).pack(pady=(18, 0))

    def show_console_report_action_menu(self, username, can_report):
        self.console_selected_username = username
        self.current_screen_refresh = lambda u=username, c=can_report: self.show_console_report_action_menu(u, c)
        self.clear_view()
        frame = self.create_scrollable_view()
        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)
        title = self.ui_label("console_grant_report") if can_report else self.ui_label("console_revoke_report")
        tk.Label(frame, text=title, font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text=username, font=("Segoe UI", 11, "bold"), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center", pady=(0, 18))
        card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        card.pack(anchor="center")
        self.console_action_confirm_var = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text=self.ui_label("console_action_confirm"), variable=self.console_action_confirm_var, bg="#efe5d8", activebackground="#efe5d8", justify="left", wraplength=360).pack(anchor="w", pady=(0, 12))
        self.menu_button(card, title, self.submit_console_grant_report if can_report else self.submit_console_revoke_report).pack(fill="x", pady=4)
        tk.Button(frame, text=self.ui_label("back"), command=lambda u=username: self.show_console_account_details(u), padx=12).pack(pady=(18, 0))

    def multiplayer_create_room(self):
        if self.pending_multiplayer_action and self.pending_multiplayer_action.get("kind") == "create":
            return
        try:
            self.ensure_multiplayer_connection()
            self.pending_multiplayer_action = {"kind": "create"}
            self.multiplayer_client.send({"type": "create_room"})
        except OSError as exc:
            messagebox.showerror("Multiplayer", f"Nem sikerult csatlakozni a szerverhez: {exc}")

    def show_multiplayer_join_menu(self):
        self.current_screen_refresh = self.show_multiplayer_join_menu
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text=self.ui_label("join"),
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text=self.ui_label("enter_room_code"),
            font=("Segoe UI", 12),
            bg=BG_COLOR,
            fg="#5a5a5a",
        ).pack(anchor="center", pady=(0, 18))

        self.multiplayer_join_code_var = tk.StringVar()
        entry = tk.Entry(frame, textvariable=self.multiplayer_join_code_var, font=("Consolas", 20), justify="center", width=10)
        entry.pack(pady=(0, 18))
        entry.focus_set()
        self.set_global_return_action(self.multiplayer_join_room)

        self.menu_button(frame, self.ui_label("join"), self.multiplayer_join_room).pack(anchor="center")
        tk.Button(frame, text=self.ui_label("back"), command=self.show_multiplayer_placeholder, padx=12).pack(pady=(18, 0))

    def multiplayer_join_room(self):
        if self.pending_multiplayer_action and self.pending_multiplayer_action.get("kind") == "join":
            return
        code = (self.multiplayer_join_code_var.get() if self.multiplayer_join_code_var is not None else "").strip().upper()
        if not code:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("enter_room_code_error"))
            return
        try:
            self.ensure_multiplayer_connection()
            self.pending_multiplayer_action = {"kind": "join", "code": code}
            self.multiplayer_client.send({"type": "join_room", "room_code": code})
        except OSError as exc:
            messagebox.showerror(self.ui_label("multiplayer"), f"{self.ui_label('server_connect_error')}: {exc}")

    def submit_register(self):
        username = (self.auth_username_var.get() if self.auth_username_var is not None else "").strip()
        password = self.auth_password_var.get() if self.auth_password_var is not None else ""
        if not username or not password:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("enter_username_password"))
            return
        try:
            self.ensure_multiplayer_connection()
            self.multiplayer_client.send({"type": "register", "username": username, "password": password})
        except OSError as exc:
            messagebox.showerror(self.ui_label("multiplayer"), f"{self.ui_label('server_connect_error')}: {exc}")

    def submit_login(self):
        username = (self.auth_username_var.get() if self.auth_username_var is not None else "").strip()
        password = self.auth_password_var.get() if self.auth_password_var is not None else ""
        if not username or not password:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("enter_username_password"))
            return
        try:
            self.ensure_multiplayer_connection()
            self.multiplayer_client.send(
                {
                    "type": "login",
                    "username": username,
                    "password": password,
                    "remember_me": bool(self.auth_remember_var.get()) if self.auth_remember_var is not None else False,
                }
            )
        except OSError as exc:
            messagebox.showerror(self.ui_label("multiplayer"), f"{self.ui_label('server_connect_error')}: {exc}")

    def restore_saved_login(self):
        if not self.remember_token:
            if self.auth_target_screen == "multiplayer":
                messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("no_stored_login"))
            return
        try:
            self.ensure_multiplayer_connection()
            self.pending_multiplayer_action = {"kind": "restore"}
            self.multiplayer_client.send({"type": "restore_session", "remember_token": self.remember_token})
        except OSError as exc:
            if self.auth_target_screen == "multiplayer":
                messagebox.showerror(self.ui_label("multiplayer"), f"{self.ui_label('server_connect_error')}: {exc}")

    def submit_logout(self):
        if self.multiplayer_client is None or not self.multiplayer_client.connected:
            self.reset_account_state()
            self.show_main_menu()
            return
        self.multiplayer_client.send({"type": "logout"})

    def request_profile_snapshot(self):
        if self.multiplayer_client is None or not self.multiplayer_client.connected:
            if self.remember_token:
                try:
                    self.ensure_multiplayer_connection()
                    self.pending_multiplayer_action = {"kind": "profile_restore"}
                    self.multiplayer_client.send({"type": "restore_session", "remember_token": self.remember_token})
                except OSError:
                    return
            return
        self.multiplayer_client.send({"type": "profile_snapshot"})

    def submit_delete_account(self):
        password = self.delete_account_password_var.get() if self.delete_account_password_var is not None else ""
        confirm_password = self.delete_account_confirm_var.get() if self.delete_account_confirm_var is not None else ""
        if not password or not confirm_password:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("delete_account_fill_both"))
            return
        if password != confirm_password:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("passwords_do_not_match"))
            return
        if not messagebox.askyesno(self.ui_label("delete_account"), self.ui_label("delete_account_confirm_prompt")):
            return
        if self.multiplayer_client is None or not self.multiplayer_client.connected:
            if not self.remember_token:
                messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("no_active_server_connection"))
                return
            try:
                self.ensure_multiplayer_connection()
                self.pending_multiplayer_action = {
                    "kind": "delete_account",
                    "payload": {
                        "type": "delete_account",
                        "password": password,
                        "confirm_password": confirm_password,
                    },
                }
                self.multiplayer_client.send({"type": "restore_session", "remember_token": self.remember_token})
            except OSError as exc:
                messagebox.showerror(self.ui_label("multiplayer"), f"{self.ui_label('server_connect_error')}: {exc}")
            return
        self.multiplayer_client.send(
            {
                "type": "delete_account",
                "password": password,
                "confirm_password": confirm_password,
            }
        )

    def submit_console_password_reset(self):
        username = self.console_selected_username.strip()
        new_password = self.console_new_password_var.get() if self.console_new_password_var is not None else ""
        if not username or not new_password:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("enter_username_password"))
            return
        if self.console_action_confirm_var is None or not self.console_action_confirm_var.get():
            messagebox.showerror(self.ui_label("console_title"), self.ui_label("console_action_confirm_required"))
            return
        if self.multiplayer_client is None:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("no_active_server_connection"))
            return
        self.multiplayer_client.send({"type": "console_reset_password", "username": username, "new_password": new_password})

    def submit_console_delete_user(self):
        username = self.console_selected_username.strip()
        if not username:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("console_target_required"))
            return
        if self.console_action_confirm_var is None or not self.console_action_confirm_var.get():
            messagebox.showerror(self.ui_label("console_title"), self.ui_label("console_action_confirm_required"))
            return
        if self.multiplayer_client is None:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("no_active_server_connection"))
            return
        self.multiplayer_client.send({"type": "console_delete_user", "username": username})

    def request_console_snapshot(self):
        if self.multiplayer_client is None:
            return
        self.multiplayer_client.send({"type": "console_snapshot"})

    def console_target_username(self):
        return self.console_selected_username.strip()

    def submit_console_ban_user(self):
        username = self.console_target_username()
        if not username:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("console_target_required"))
            return
        if self.console_action_confirm_var is None or not self.console_action_confirm_var.get():
            messagebox.showerror(self.ui_label("console_title"), self.ui_label("console_action_confirm_required"))
            return
        reason = self.console_reason_var.get().strip() if self.console_reason_var is not None else ""
        self.multiplayer_client.send({"type": "console_set_ban", "username": username, "is_banned": True, "reason": reason})

    def submit_console_unban_user(self):
        username = self.console_target_username()
        if not username:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("console_target_required"))
            return
        if self.console_action_confirm_var is None or not self.console_action_confirm_var.get():
            messagebox.showerror(self.ui_label("console_title"), self.ui_label("console_action_confirm_required"))
            return
        self.multiplayer_client.send({"type": "console_set_ban", "username": username, "is_banned": False, "reason": ""})

    def submit_console_make_admin(self):
        username = self.console_target_username()
        if not username:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("console_target_required"))
            return
        if self.console_action_confirm_var is None or not self.console_action_confirm_var.get():
            messagebox.showerror(self.ui_label("console_title"), self.ui_label("console_action_confirm_required"))
            return
        self.multiplayer_client.send({"type": "console_set_admin", "username": username, "is_admin": True})

    def submit_console_remove_admin(self):
        username = self.console_target_username()
        if not username:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("console_target_required"))
            return
        if self.console_action_confirm_var is None or not self.console_action_confirm_var.get():
            messagebox.showerror(self.ui_label("console_title"), self.ui_label("console_action_confirm_required"))
            return
        self.multiplayer_client.send({"type": "console_set_admin", "username": username, "is_admin": False})

    def submit_console_grant_report(self):
        username = self.console_target_username()
        if not username:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("console_target_required"))
            return
        if self.console_action_confirm_var is None or not self.console_action_confirm_var.get():
            messagebox.showerror(self.ui_label("console_title"), self.ui_label("console_action_confirm_required"))
            return
        self.multiplayer_client.send({"type": "console_set_report_permission", "username": username, "can_report": True})

    def submit_console_revoke_report(self):
        username = self.console_target_username()
        if not username:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("console_target_required"))
            return
        if self.console_action_confirm_var is None or not self.console_action_confirm_var.get():
            messagebox.showerror(self.ui_label("console_title"), self.ui_label("console_action_confirm_required"))
            return
        self.multiplayer_client.send({"type": "console_set_report_permission", "username": username, "can_report": False})

    def submit_console_clear_balance(self):
        username = self.console_target_username()
        if not username:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("console_target_required"))
            return
        if self.console_action_confirm_var is None or not self.console_action_confirm_var.get():
            messagebox.showerror(self.ui_label("console_title"), self.ui_label("console_action_confirm_required"))
            return
        if self.multiplayer_client is None:
            messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("no_active_server_connection"))
            return
        self.multiplayer_client.send({"type": "console_clear_balance", "username": username})

    def render_console_snapshot(self, users):
        self.console_users_cache = [record for record in users if isinstance(record, dict)]
        refresh_name = getattr(self.current_screen_refresh, "__name__", "") if callable(self.current_screen_refresh) else ""
        if refresh_name == "show_console_player_list":
            self.current_screen_refresh()
            return
        if callable(self.current_screen_refresh):
            refresh_name = getattr(self.current_screen_refresh, "__name__", "")
            if refresh_name == "<lambda>" and self.session_role == "console":
                self.current_screen_refresh()

    def show_admin_rooms_menu(self, fetch=True):
        self.current_screen_refresh = lambda: self.show_admin_rooms_menu(fetch=False)
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(frame, text=self.ui_label("active_rooms"), font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text=self.ui_label("active_rooms_subtitle"), font=("Segoe UI", 11), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center", pady=(0, 18))

        list_frame = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        list_frame.pack(anchor="center", fill="both", expand=True)

        rooms = self.admin_rooms_cache
        if not rooms:
            tk.Label(list_frame, text=self.ui_label("no_active_rooms"), font=("Segoe UI", 11), bg="#efe5d8", fg="#5a5a5a").pack(anchor="center", pady=12)
        else:
            for room in rooms:
                row = tk.Frame(list_frame, bg="#efe5d8", pady=6)
                row.pack(fill="x")
                status = self.ui_label("started") if room.get("started") else self.ui_label("waiting")
                host = room.get("host_username") or "?"
                guest = room.get("guest_username") or "?"
                text = f"{room.get('room_code', '??????')} | {status} | {host} vs {guest} | {self.ui_label('moves')}: {room.get('move_count', 0)}"
                tk.Label(row, text=text, font=("Consolas", 11), bg="#efe5d8", fg=TEXT_COLOR, anchor="w", justify="left").pack(side="left", fill="x", expand=True)
                if room.get("started"):
                    tk.Button(row, text=self.ui_label("spectate"), command=lambda c=room.get("room_code"): self.start_spectating_room(c), padx=10).pack(side="right")

        action_row = tk.Frame(frame, bg=BG_COLOR)
        action_row.pack(anchor="center", pady=(18, 0))
        tk.Button(action_row, text=self.ui_label("refresh"), command=lambda: self.show_admin_rooms_menu(fetch=True), padx=12).pack(side="left", padx=4)
        tk.Button(action_row, text=self.ui_label("back"), command=self.show_post_login_multiplayer_view, padx=12).pack(side="left", padx=4)
        if fetch:
            self.request_admin_rooms_snapshot()

    def request_admin_rooms_snapshot(self):
        if self.multiplayer_client is None:
            return
        self.multiplayer_client.send({"type": "admin_list_rooms"})

    def start_spectating_room(self, room_code):
        if self.multiplayer_client is None:
            return
        self.multiplayer_client.send({"type": "admin_spectate_room", "room_code": room_code})

    def show_multiplayer_waiting_room(self, host, code="......"):
        self.current_screen_refresh = lambda h=host, c=code: self.show_multiplayer_waiting_room(h, c)
        self.multiplayer_is_host = host
        self.clear_view()
        frame = self.create_scrollable_view()

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        self.multiplayer_room_var = tk.StringVar(value=code)
        self.multiplayer_status_var = tk.StringVar(value=self.ui_label("waiting_opponent"))

        tk.Label(frame, text=self.ui_label("multiplayer_lobby"), font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text=self.ui_label("room_code"), font=("Segoe UI", 11), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center")
        tk.Label(frame, textvariable=self.multiplayer_room_var, font=("Consolas", 24, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(0, 18))
        tk.Label(frame, textvariable=self.multiplayer_status_var, font=("Segoe UI", 11), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center", pady=(0, 18))

        self.multiplayer_host_controls = tk.Frame(frame, bg=BG_COLOR)
        self.multiplayer_host_controls.pack(anchor="center")

        tk.Button(frame, text=self.ui_label("cancel"), command=self.cancel_multiplayer, padx=12).pack(pady=(18, 0))

    def show_multiplayer_role_choice(self):
        if self.multiplayer_host_controls is None:
            return
        code = self.multiplayer_room_var.get() if self.multiplayer_room_var is not None else "......"
        self.current_screen_refresh = lambda h=self.multiplayer_is_host, c=code: (self.show_multiplayer_waiting_room(h, c), self.show_multiplayer_role_choice())
        for child in self.multiplayer_host_controls.winfo_children():
            child.destroy()
        self.multiplayer_move_limit_var = tk.StringVar(value=str(self.default_move_limit))
        tk.Label(
            self.multiplayer_host_controls,
            text=self.ui_label("role_setup"),
            font=("Segoe UI", 10, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(pady=(0, 8))
        tk.Label(
            self.multiplayer_host_controls,
            text=self.ui_label("move_limit_short"),
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg="#6a6a6a",
        ).pack()
        tk.Entry(
            self.multiplayer_host_controls,
            textvariable=self.multiplayer_move_limit_var,
            font=("Consolas", 16),
            justify="center",
            width=8,
        ).pack(pady=(4, 10))
        row = tk.Frame(self.multiplayer_host_controls, bg=BG_COLOR)
        row.pack()
        tk.Button(row, text=self.ui_label("white"), command=lambda: self.send_role_choice("white"), padx=12).pack(side="left", padx=4)
        tk.Button(row, text=self.ui_label("black"), command=lambda: self.send_role_choice("black"), padx=12).pack(side="left", padx=4)
        tk.Button(row, text=self.ui_label("random"), command=lambda: self.send_role_choice("random"), padx=12).pack(side="left", padx=4)

    def send_role_choice(self, choice):
        if self.multiplayer_client is not None:
            try:
                move_limit = int((self.multiplayer_move_limit_var.get() if self.multiplayer_move_limit_var is not None else str(self.default_move_limit)).strip())
            except ValueError:
                messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("launch_error"))
                return
            self.multiplayer_status_var.set(self.ui_label("role_sent"))
            self.multiplayer_client.send({"type": "choose_role", "preference": choice, "move_limit": move_limit})

    def cancel_multiplayer(self):
        if self.multiplayer_client is not None and self.multiplayer_client.connected:
            self.multiplayer_client.send({"type": "leave_room"})
        self.multiplayer_room = None
        self.multiplayer_is_host = False
        self.show_post_login_multiplayer_view()

    def start_singleplayer(self):
        self.show_match_options(
            self.ui_label("singleplayer"),
            self.ui_label("match_options_subtitle"),
            self.start_singleplayer_game,
            self.show_main_menu,
        )

    def start_singleplayer_game(self, move_limit):
        self.start_game({"mode": "singleplayer", "difficulty": None, "difficulty_label": None, "move_limit": move_limit})

    def start_random_bot_game(self):
        self.show_bot_match_options(random.choice(["white", "black"]))

    def show_bot_match_options(self, player_color):
        self.show_match_options(
            self.ui_label("bot_match"),
            self.ui_label("match_options_subtitle"),
            lambda move_limit: self.start_bot_game(player_color, move_limit),
            lambda: self.show_bot_color_menu(self.pending_bot_difficulty["difficulty"], self.pending_bot_difficulty["label"]),
        )

    def start_bot_game(self, player_color, move_limit):
        if not self.pending_bot_difficulty:
            self.show_bot_menu()
            return
        bot_color = opposite(player_color)
        self.start_game(
            {
                "mode": "bot",
                "difficulty": self.pending_bot_difficulty["difficulty"],
                "difficulty_label": self.pending_bot_difficulty["label"],
                "bot_color": bot_color,
                "player_color": player_color,
                "move_limit": move_limit,
            }
        )

    def start_bot_vs_bot_game(self, move_limit):
        if "white" not in self.pending_bvb or "black" not in self.pending_bvb:
            self.show_bot_vs_bot_white_menu()
            return
        self.start_game(
            {
                "mode": "bot_vs_bot",
                "bot_players": {
                    "white": self.pending_bvb["white"]["difficulty"],
                    "black": self.pending_bvb["black"]["difficulty"],
                },
                "white_label": self.pending_bvb["white"]["label"],
                "black_label": self.pending_bvb["black"]["label"],
                "move_limit": move_limit,
            }
        )

    def start_multiplayer_game(self, player_color, room_code, move_limit, initial_state=None):
        self.start_game(
            {
                "mode": "multiplayer",
                "difficulty": None,
                "difficulty_label": None,
                "player_color": player_color,
                "network_client": self.multiplayer_client,
                "room_code": room_code,
                "move_limit": move_limit,
                "initial_state": initial_state,
            }
        )

    def start_game(self, mode_config):
        self.clear_view()
        self.current_view = UnchessGame(self, self.root, mode_config)
        self.current_screen_refresh = self.current_view.refresh_language

    def return_to_main_menu(self):
        if isinstance(self.current_view, UnchessGame):
            mode = self.current_view.mode_config.get("mode")
            if mode == "multiplayer" and self.multiplayer_client is not None and self.multiplayer_client.connected:
                self.multiplayer_client.send({"type": "leave_room"})
            elif mode == "spectator" and self.multiplayer_client is not None and self.multiplayer_client.connected:
                self.multiplayer_client.send({"type": "admin_leave_spectate"})
        self.show_main_menu()

    def report_finished_local_match(self, game):
        if game.mode_config.get("mode") != "bot":
            return
        if not self.user_name or self.session_role not in {"player", "admin"}:
            return
        player_color = game.mode_config.get("player_color")
        if player_color not in {"white", "black"}:
            return
        own_points = game.score_white if player_color == "white" else game.score_black
        enemy_points = game.score_black if player_color == "white" else game.score_white
        if own_points > enemy_points:
            outcome = "win"
        elif own_points < enemy_points:
            outcome = "loss"
        else:
            outcome = "draw"
        payload = {
            "type": "submit_local_result",
            "mode": "bot",
            "difficulty": game.mode_config.get("difficulty", ""),
            "outcome": outcome,
            "points": own_points,
            "move_count": game.move_count,
            "duration_sec": max(0, int(time.time() - getattr(game, "match_started_at", time.time()))),
        }
        if self.multiplayer_client is not None and self.multiplayer_client.connected and self.session_confirmed:
            self.multiplayer_client.send(payload)
            return
        if not self.remember_token:
            return
        try:
            self.ensure_multiplayer_connection()
            self.pending_multiplayer_action = {"kind": "local_result", "payload": payload}
            self.multiplayer_client.send({"type": "restore_session", "remember_token": self.remember_token})
        except OSError:
            return

    def handle_network_event(self, event):
        event_type = event.get("type")
        if event_type == "hello_ack":
            return
        if event_type == "network_error":
            messagebox.showerror("Multiplayer", event.get("message", "Halozati hiba"))
            self.close_multiplayer_client()
            return
        if event_type == "disconnected":
            if self.ignore_next_disconnect:
                self.ignore_next_disconnect = False
                return
            if self.multiplayer_client is not None:
                messagebox.showwarning("Multiplayer", "A kapcsolat megszakadt.")
            self.close_multiplayer_client()
            return
        if event_type == "error":
            raw_message = event.get("message", "Server error")
            if raw_message == "You have already reported your opponent once in this match.":
                messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("report_already_used_this_match"))
            elif raw_message == "You are already assigned to a room.":
                messagebox.showerror(self.ui_label("multiplayer"), self.ui_label("already_assigned_to_room"))
            else:
                messagebox.showerror(self.ui_label("multiplayer"), raw_message)
            if self.pending_multiplayer_action and self.pending_multiplayer_action["kind"] == "join":
                self.show_multiplayer_join_menu()
            elif self.pending_multiplayer_action and self.pending_multiplayer_action["kind"] == "create":
                self.show_multiplayer_placeholder()
            self.pending_multiplayer_action = None
            return
        if event_type == "auth_error":
            pending_kind = self.pending_multiplayer_action.get("kind") if self.pending_multiplayer_action else ""
            if pending_kind in {"restore", "profile_restore", "local_result", "delete_account"}:
                self.reset_account_state()
            self.pending_multiplayer_action = None
            messagebox.showerror("Multiplayer", event.get("message", "Hitelesítési hiba"))
            if pending_kind == "restore" and self.auth_target_screen == "main" and not self.suppress_auth_prompt:
                self.show_startup_account_prompt()
            return
        if event_type == "register_success":
            self.user_name = ""
            self.auth_username_var = tk.StringVar(value="")
            self.auth_password_var = tk.StringVar()
            messagebox.showinfo("Multiplayer", self.ui_label("register_success_return_login"))
            if self.auth_target_screen == "multiplayer":
                self.show_multiplayer_auth_menu("login")
            else:
                self.show_startup_auth_menu("login")
            return
        if event_type == "login_success":
            self.user_name = event.get("username", "")
            self.session_role = str(event.get("session_role", "player") or "player")
            self.is_admin = self.session_role == "admin"
            self.remember_token = str(event.get("remember_token", "") or "")
            self.session_confirmed = True
            profile = event.get("profile")
            if profile:
                self.update_profile_snapshot(profile)
            pending_action = self.pending_multiplayer_action
            self.pending_multiplayer_action = None
            self.save_settings()
            if pending_action and pending_action.get("kind") == "local_result":
                if self.multiplayer_client is not None and self.multiplayer_client.connected:
                    self.multiplayer_client.send(pending_action["payload"])
                return
            if pending_action and pending_action.get("kind") == "delete_account":
                if self.multiplayer_client is not None and self.multiplayer_client.connected:
                    self.multiplayer_client.send(pending_action["payload"])
                return
            if pending_action and pending_action.get("kind") == "profile_restore":
                self.request_profile_snapshot()
                return
            self.after_successful_auth()
            return
        if event_type == "logout_success":
            self.reset_account_state()
            self.close_multiplayer_client()
            self.show_main_menu()
            return
        if event_type == "delete_account_success":
            deleted_username = event.get("username", self.user_name)
            self.reset_account_state()
            self.close_multiplayer_client()
            messagebox.showinfo(self.ui_label("multiplayer"), f"{self.ui_label('delete_account_success')}: {deleted_username}")
            self.show_startup_account_prompt()
            return
        if event_type == "force_logout":
            self.reset_account_state()
            self.close_multiplayer_client()
            messagebox.showwarning("Multiplayer", event.get("message", "Kijelentkeztetve."))
            self.show_startup_account_prompt()
            return
        if event_type == "banned":
            self.reset_account_state()
            messagebox.showerror("Multiplayer", f"{event.get('message', 'A fiók tiltva van.')}\nVitatás: {event.get('appeal_email', 'appeal@example.com')}")
            self.show_startup_account_prompt()
            return
        if event_type == "profile_snapshot":
            self.update_profile_snapshot(event.get("profile"))
            return
        if event_type == "local_result_saved":
            return
        if event_type == "report_success":
            messagebox.showinfo("Multiplayer", f"Report elküldve: {event.get('reported_username', 'ismeretlen')}")
            return
        if event_type == "ban_success":
            messagebox.showinfo("Multiplayer", f"Játékos tiltva: {event.get('banned_username', 'ismeretlen')}")
            return
        if event_type == "admin_action_success":
            messagebox.showinfo(self.ui_label("multiplayer"), event.get("message", self.ui_label("admin_action_done")))
            return
        if event_type == "console_action_success":
            if self.console_new_password_var is not None:
                self.console_new_password_var.set("")
            self.request_console_snapshot()
            self.show_console_player_list()
            messagebox.showinfo(self.ui_label("console_title"), event.get("message", self.ui_label("console_action_done")))
            return
        if event_type == "console_snapshot":
            self.render_console_snapshot(event.get("users", []))
            return
        if event_type == "admin_rooms_snapshot":
            self.admin_rooms_cache = event.get("rooms", [])
            if callable(self.current_screen_refresh):
                refresh_name = getattr(self.current_screen_refresh, "__name__", "")
                if refresh_name in {"<lambda>", "show_admin_rooms_menu"}:
                    self.show_admin_rooms_menu(fetch=False)
            return
        if event_type == "spectate_started":
            room = event.get("room", {})
            game_state = event.get("game_state") or {}
            self.start_spectator_game(room, game_state)
            return
        if event_type == "spectate_ended":
            if isinstance(self.current_view, UnchessGame) and self.current_view.mode_config["mode"] == "spectator":
                message = event.get("message", self.ui_label("spectate_ended"))
                messagebox.showinfo(self.ui_label("active_rooms"), message)
                self.show_admin_rooms_menu(fetch=True)
            return
        if event_type == "server_shutdown":
            message = event.get("message", "A szerver leáll.")
            immediate = bool(event.get("immediate"))
            seconds_remaining = int(event.get("seconds_remaining", 0) or 0)
            if immediate or seconds_remaining <= 0:
                messagebox.showwarning("Multiplayer", message)
                self.close_multiplayer_client()
                self.show_main_menu()
                return
            minutes = max(1, seconds_remaining // 60)
            messagebox.showwarning("Multiplayer", f"{message}\nHátralévő idő: ~{minutes} perc")
            return
        if event_type == "server_shutdown_cancelled":
            messagebox.showinfo("Multiplayer", event.get("message", "A tervezett szerverleállás megszakítva."))
            return
        if event_type == "left_room":
            self.multiplayer_room = None
            self.multiplayer_is_host = False
            return
        if event_type == "room_created":
            self.multiplayer_room = event["room"]
            self.pending_multiplayer_action = None
            self.show_multiplayer_waiting_room(host=True, code=event["room"]["room_code"])
            return
        if event_type == "room_joined":
            self.multiplayer_room = event["room"]
            self.pending_multiplayer_action = None
            self.show_multiplayer_waiting_room(host=False, code=event["room"]["room_code"])
            if self.multiplayer_status_var is not None:
                self.multiplayer_status_var.set(self.ui_label("waiting_opponent"))
            return
        if event_type == "room_ready_for_role_choice":
            self.multiplayer_room = event["room"]
            if self.multiplayer_room_var is not None:
                self.multiplayer_room_var.set(event["room"]["room_code"])
            if self.multiplayer_status_var is not None:
                self.multiplayer_status_var.set(self.ui_label("opponent_arrived"))
            if self.multiplayer_is_host:
                self.show_multiplayer_role_choice()
            return
        if event_type == "game_start":
            room = event["room"]
            self.multiplayer_room = room
            if self.multiplayer_client is None:
                return
            assignment = room.get("role_assignment") or {}
            game_state = event.get("game_state")
            if self.multiplayer_room_var is not None:
                self.multiplayer_room_var.set(room.get("room_code", ""))
            host_color = assignment.get("host")
            guest_color = assignment.get("guest")
            if host_color in {"white", "black"} and guest_color not in {"white", "black"}:
                guest_color = "black" if host_color == "white" else "white"
            player_color = host_color if self.multiplayer_is_host else guest_color
            if player_color in {"white", "black"}:
                self.start_multiplayer_game(
                    player_color,
                    room.get("room_code", ""),
                    room.get("move_limit", self.default_move_limit),
                    initial_state=game_state,
                )
            return
        if event_type == "player_left":
            room = event["room"]
            self.multiplayer_room = room
            if isinstance(self.current_view, UnchessGame) and self.current_view.mode_config["mode"] == "spectator":
                leaver = event.get("player_name", "A jÃ¡tÃ©kos")
                messagebox.showinfo(self.ui_label("active_rooms"), f"{leaver} kilÃ©pett. A spectate leÃ¡llt.")
                self.show_admin_rooms_menu(fetch=True)
                return
            if isinstance(self.current_view, UnchessGame) and self.current_view.mode_config["mode"] == "multiplayer":
                leaver = event.get("player_name", "Az ellenfél")
                if event.get("game_was_started"):
                    messagebox.showinfo("Multiplayer", f"{leaver} kilépett. Nyertél.")
                else:
                    messagebox.showinfo("Multiplayer", f"{leaver} kilépett. A szoba bezárult.")
                self.multiplayer_room = None
                self.multiplayer_is_host = False
                self.show_post_login_multiplayer_view()
                return
            if self.multiplayer_status_var is not None:
                self.multiplayer_status_var.set("Az ellenfél kilépett.")
            self.multiplayer_room = None
            self.multiplayer_is_host = False
            self.show_post_login_multiplayer_view()
            return
        if event_type == "move_broadcast":
            if isinstance(self.current_view, UnchessGame) and self.current_view.mode_config["mode"] in {"multiplayer", "spectator"}:
                self.current_view.apply_network_move(event)

    def menu_button(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=("Segoe UI", 12, "bold"),
            width=24,
            padx=12,
            pady=10,
            bg="#d9c3a4",
            activebackground="#c6aa84",
            fg=TEXT_COLOR,
            relief="flat",
            cursor="hand2",
        )

    def mount_settings_button(self, parent):
        self.settings_parent = parent
        button = tk.Canvas(
            parent,
            bg=BG_COLOR,
            cursor="hand2",
            width=40,
            height=40,
            highlightthickness=0,
            bd=0,
        )
        button.pack(side="left", anchor="nw", padx=(0, 8))
        self.draw_settings_icon(button, 0.0, 1.0)
        button.bind("<Enter>", lambda _event: self.on_settings_hover_enter())
        button.bind("<Leave>", lambda _event: self.on_settings_hover_leave())
        button.bind("<Button-1>", lambda _event: self.toggle_settings_panel())
        self.settings_button = button
        self.settings_anchor_widget = button
        tk.Frame(parent, bg=BG_COLOR).pack(side="left", fill="x", expand=True)
        self.mount_profile_button(parent)

    def mount_profile_button(self, parent):
        button = tk.Canvas(
            parent,
            bg=BG_COLOR,
            cursor="hand2",
            width=40,
            height=40,
            highlightthickness=0,
            bd=0,
        )
        button.pack(side="right", anchor="ne")
        self.draw_profile_icon(button)
        button.bind("<Button-1>", lambda _event: self.toggle_profile_panel())
        self.profile_button = button
        self.profile_anchor_widget = button

    def draw_profile_icon(self, canvas):
        if canvas is None:
            return
        try:
            if not int(canvas.winfo_exists()):
                return
        except tk.TclError:
            return
        canvas.delete("all")
        fill = "#6d4c35" if self.profile_panel is not None else TEXT_COLOR
        canvas.create_oval(13, 7, 27, 21, fill=fill, outline=fill)
        canvas.create_arc(9, 16, 31, 36, start=0, extent=180, style="chord", fill=fill, outline=fill)

    def toggle_profile_panel(self):
        if self.profile_panel is not None:
            self.close_profile_panel()
        else:
            self.open_profile_panel()

    def close_profile_panel(self, redraw_icon=True):
        if self.profile_panel is not None:
            self.profile_panel.destroy()
            self.profile_panel = None
        if redraw_icon and self.profile_button is not None:
            try:
                if not int(self.profile_button.winfo_exists()):
                    self.profile_button = None
                    self.profile_anchor_widget = None
                    return
            except tk.TclError:
                self.profile_button = None
                self.profile_anchor_widget = None
                return
            self.draw_profile_icon(self.profile_button)

    def format_stats_text(self, bucket):
        stats = normalize_profile_stats(self.profile_stats).get(bucket, blank_stat_bucket())
        return (
            f"{self.ui_label('wins')}: {stats['wins']}  "
            f"{self.ui_label('losses')}: {stats['losses']}  "
            f"{self.ui_label('draws')}: {stats['draws']}  "
            f"{self.ui_label('points')}: {stats['points']}"
        )

    def format_external_stats_text(self, stats, bucket):
        safe_stats = normalize_profile_stats(stats).get(bucket, blank_stat_bucket())
        return (
            f"{self.ui_label('wins')}: {safe_stats['wins']}  "
            f"{self.ui_label('losses')}: {safe_stats['losses']}  "
            f"{self.ui_label('draws')}: {safe_stats['draws']}  "
            f"{self.ui_label('points')}: {safe_stats['points']}"
        )

    def open_profile_panel(self):
        if self.profile_anchor_widget is None:
            return
        try:
            if not int(self.profile_anchor_widget.winfo_exists()):
                self.profile_button = None
                self.profile_anchor_widget = None
                return
        except tk.TclError:
            self.profile_button = None
            self.profile_anchor_widget = None
            return
        self.close_settings_panel()
        if self.profile_panel is not None:
            self.profile_panel.destroy()
        self.profile_panel = tk.Frame(
            self.root,
            bg=BG_COLOR,
            bd=0,
            highlightthickness=1,
            highlightbackground="#dac7b1",
            padx=16,
            pady=16,
        )
        self.root.update_idletasks()
        anchor_x = self.profile_anchor_widget.winfo_rootx() - self.root.winfo_rootx()
        anchor_y = self.profile_anchor_widget.winfo_rooty() - self.root.winfo_rooty()
        panel = self.profile_panel
        tk.Label(panel, text=self.ui_label("profile"), font=("Segoe UI", 12, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w")
        signed_in = self.has_confirmed_account()
        username = self.user_name if signed_in else self.ui_label("guest")
        role_text = self.session_role if signed_in else self.ui_label("guest")
        tk.Label(panel, text=username, font=("Segoe UI", 16, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w", pady=(8, 2))
        tk.Label(panel, text=f"{self.ui_label('role')}: {role_text}", font=("Segoe UI", 10), bg=BG_COLOR, fg="#6a6a6a").pack(anchor="w", pady=(0, 10))

        if signed_in and self.session_role != "console":
            tk.Label(panel, text=self.ui_label("multiplayer_stats"), font=("Segoe UI", 10, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w")
            tk.Label(panel, text=self.format_stats_text("multiplayer"), font=("Consolas", 10), bg=BG_COLOR, fg="#5a5a5a", justify="left").pack(anchor="w", pady=(0, 8))
            tk.Label(panel, text=self.ui_label("bot_stats"), font=("Segoe UI", 10, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="w")
            tk.Label(panel, text=self.format_stats_text("bot"), font=("Consolas", 10), bg=BG_COLOR, fg="#5a5a5a", justify="left").pack(anchor="w", pady=(0, 8))
            tk.Label(panel, text=self.ui_label("milestones_coming"), font=("Segoe UI", 10), bg=BG_COLOR, fg="#6a6a6a", wraplength=250, justify="left").pack(anchor="w", pady=(2, 10))
        elif signed_in and self.session_role == "console":
            tk.Label(panel, text=self.ui_label("console_profile_hint"), font=("Segoe UI", 10), bg=BG_COLOR, fg="#6a6a6a", wraplength=250, justify="left").pack(anchor="w", pady=(2, 10))
        else:
            tk.Label(panel, text=self.ui_label("guest_profile_hint"), font=("Segoe UI", 10), bg=BG_COLOR, fg="#6a6a6a", wraplength=250, justify="left").pack(anchor="w", pady=(2, 10))

        action_row = tk.Frame(panel, bg=BG_COLOR)
        action_row.pack(anchor="w", pady=(6, 0))
        if signed_in and self.session_role in {"player", "admin", "console"}:
            tk.Button(action_row, text=self.ui_label("refresh"), command=self.request_profile_snapshot, padx=10).pack(side="left", padx=(0, 6))
            tk.Button(action_row, text=self.ui_label("logout"), command=self.submit_logout, padx=10).pack(side="left")
        else:
            tk.Button(action_row, text=self.ui_label("login"), command=lambda: self.show_startup_auth_menu("login"), padx=10).pack(side="left")

        if signed_in and self.session_role in {"player", "admin"}:
            tk.Button(
                panel,
                text=self.ui_label("delete_account"),
                command=self.show_profile_delete_account_menu,
                font=("Segoe UI", 10),
                bg=BG_COLOR,
                fg="#b00020",
                activebackground=BG_COLOR,
                activeforeground="#7f0015",
                relief="flat",
                cursor="hand2",
                padx=4,
                pady=4,
            ).pack(anchor="w", pady=(12, 0))

        panel.update_idletasks()
        panel_width = panel.winfo_reqwidth()
        panel_height = panel.winfo_reqheight()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        panel_x = max(8, min(anchor_x + self.profile_anchor_widget.winfo_width() - panel_width, root_width - panel_width - 8))
        panel_y = max(8, min(anchor_y + self.profile_anchor_widget.winfo_height() + 8, root_height - panel_height - 8))
        panel.place(x=panel_x, y=panel_y)
        self.draw_profile_icon(self.profile_button)

    def show_profile_delete_account_menu(self):
        self.profile_delete_back = self.current_screen_refresh
        self.close_profile_panel()
        self.show_delete_account_menu()

    def draw_settings_icon(self, canvas, angle_degrees, scale):
        if canvas is None:
            return
        try:
            if not int(canvas.winfo_exists()):
                return
        except tk.TclError:
            return
        canvas.delete("all")
        size = 40
        center = size / 2
        ring_outer = 8.7 * scale
        ring_inner = 4.4 * scale
        tooth_inner = 10.3 * scale
        tooth_outer = 14.0 * scale
        tooth_half_width = 1.85 * scale
        stroke = max(2, int(round(1.8 * scale)))
        fill = "#6d4c35" if self.settings_hovered else TEXT_COLOR
        angle_offset = math.radians(angle_degrees)

        for index in range(8):
            theta = angle_offset + index * (math.pi / 4.0)
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)
            tx = -sin_t
            ty = cos_t
            p1 = (
                center + cos_t * tooth_inner + tx * tooth_half_width,
                center + sin_t * tooth_inner + ty * tooth_half_width,
            )
            p2 = (
                center + cos_t * tooth_inner - tx * tooth_half_width,
                center + sin_t * tooth_inner - ty * tooth_half_width,
            )
            p3 = (
                center + cos_t * tooth_outer - tx * tooth_half_width,
                center + sin_t * tooth_outer - ty * tooth_half_width,
            )
            p4 = (
                center + cos_t * tooth_outer + tx * tooth_half_width,
                center + sin_t * tooth_outer + ty * tooth_half_width,
            )
            canvas.create_polygon(
                p1,
                p2,
                p3,
                p4,
                fill=fill,
                outline=fill,
            )
        canvas.create_oval(
            center - ring_outer,
            center - ring_outer,
            center + ring_outer,
            center + ring_outer,
            fill=fill,
            outline=fill,
        )
        canvas.create_oval(
            center - ring_inner,
            center - ring_inner,
            center + ring_inner,
            center + ring_inner,
            fill=BG_COLOR,
            outline=BG_COLOR,
        )
        canvas.create_oval(
            center - 0.9 * scale,
            center - 0.9 * scale,
            center + 0.9 * scale,
            center + 0.9 * scale,
            fill=fill,
            outline=fill,
        )

    def on_settings_hover_enter(self):
        self.settings_hovered = True
        self.animate_settings_icon(target_angle=360.0, target_scale=1.17, duration_ms=1000)

    def on_settings_hover_leave(self):
        self.settings_hovered = False
        self.animate_settings_icon(target_angle=0.0, target_scale=1.0, duration_ms=180)

    def animate_settings_icon(self, target_angle, target_scale, duration_ms):
        if self.settings_anim_job is not None:
            self.root.after_cancel(self.settings_anim_job)
            self.settings_anim_job = None
        if self.settings_button is None:
            return
        try:
            if not int(self.settings_button.winfo_exists()):
                self.settings_button = None
                return
        except tk.TclError:
            self.settings_button = None
            return

        self.settings_anim_start = time.perf_counter()
        self.settings_anim_duration_ms = duration_ms
        self.settings_anim_from_angle = self.settings_icon_angle
        self.settings_anim_to_angle = target_angle
        self.settings_anim_from_scale = self.settings_icon_scale
        self.settings_anim_to_scale = target_scale

        def ease_in_out_sine(t):
            return 0.5 - 0.5 * math.cos(math.pi * t)

        def step():
            if self.settings_button is None:
                self.settings_anim_job = None
                return
            try:
                if not int(self.settings_button.winfo_exists()):
                    self.settings_button = None
                    self.settings_anim_job = None
                    return
            except tk.TclError:
                self.settings_button = None
                self.settings_anim_job = None
                return
            elapsed_ms = (time.perf_counter() - self.settings_anim_start) * 1000.0
            t = min(1.0, elapsed_ms / self.settings_anim_duration_ms)
            eased = ease_in_out_sine(t)
            angle = self.settings_anim_from_angle + (self.settings_anim_to_angle - self.settings_anim_from_angle) * eased
            if self.settings_anim_to_scale > self.settings_anim_from_scale:
                scale = 1.0 + 0.17 * math.sin(math.pi * t)
            else:
                scale = self.settings_anim_from_scale + (self.settings_anim_to_scale - self.settings_anim_from_scale) * eased
            self.settings_icon_angle = angle
            self.settings_icon_scale = scale
            self.draw_settings_icon(self.settings_button, angle, scale)
            if t < 1.0:
                self.settings_anim_job = self.root.after(16, step)
            else:
                self.settings_anim_job = None
                self.settings_icon_angle = target_angle % 360.0
                self.settings_icon_scale = target_scale
                self.draw_settings_icon(self.settings_button, self.settings_icon_angle, self.settings_icon_scale)

        step()

    def toggle_settings_panel(self):
        if self.settings_panel is not None:
            self.close_settings_panel()
        else:
            self.open_settings_panel()

    def close_settings_panel(self, redraw_icon=True):
        self.flush_settings_panel_inputs()
        if self.settings_panel is not None:
            self.root.unbind_all("<MouseWheel>")
            self.settings_panel.destroy()
            self.settings_panel = None
            self.settings_canvas = None
            self.settings_scrollable = None
            self.settings_move_limit_var = None
            self.settings_host_var = None
            self.settings_port_var = None
        if redraw_icon and self.settings_button is not None and not self.settings_hovered:
            try:
                if not int(self.settings_button.winfo_exists()):
                    self.settings_button = None
                    return
            except tk.TclError:
                self.settings_button = None
                return
            self.draw_settings_icon(self.settings_button, self.settings_icon_angle, self.settings_icon_scale)

    def flush_settings_panel_inputs(self):
        if self.settings_move_limit_var is not None:
            raw = self.settings_move_limit_var.get().strip()
            if raw not in {"", "-"}:
                try:
                    self.default_move_limit = int(raw)
                except ValueError:
                    pass
        if self.settings_host_var is not None and self.settings_port_var is not None:
            host = self.settings_host_var.get().strip() or DEFAULT_SERVER_HOST
            try:
                port = int(self.settings_port_var.get().strip())
            except ValueError:
                port = None
            if port is not None:
                self.server_host = host
                self.server_port = port
        self.save_settings()

    def open_settings_panel(self):
        if self.settings_parent is None or self.settings_anchor_widget is None:
            return
        try:
            if not int(self.settings_anchor_widget.winfo_exists()):
                self.settings_button = None
                self.settings_anchor_widget = None
                return
        except tk.TclError:
            self.settings_button = None
            self.settings_anchor_widget = None
            return

        self.settings_panel = tk.Frame(
            self.root,
            bg=BG_COLOR,
            bd=0,
            highlightthickness=1,
            highlightbackground="#dac7b1",
            padx=0,
            pady=0,
        )
        self.root.update_idletasks()
        anchor_x = self.settings_anchor_widget.winfo_rootx() - self.root.winfo_rootx()
        anchor_y = self.settings_anchor_widget.winfo_rooty() - self.root.winfo_rooty()
        anchor_width = self.settings_anchor_widget.winfo_width()

        self.settings_canvas = tk.Canvas(
            self.settings_panel,
            width=340,
            height=250,
            bg=BG_COLOR,
            highlightthickness=0,
        )
        self.settings_canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(self.settings_panel, orient="vertical", command=self.settings_canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.settings_canvas.configure(yscrollcommand=scrollbar.set)

        self.settings_scrollable = tk.Frame(self.settings_canvas, bg=BG_COLOR, padx=16, pady=16)
        self.settings_canvas.create_window((0, 0), window=self.settings_scrollable, anchor="nw")
        self.settings_scrollable.bind(
            "<Configure>",
            lambda _event: self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all")),
        )
        self.settings_canvas.bind_all("<MouseWheel>", self.on_settings_mousewheel)

        panel = self.settings_scrollable
        tk.Label(
            panel,
            text=self.settings_ui_label("title"),
            font=("Segoe UI", 12, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(
            panel,
            text=self.settings_ui_label("language"),
            font=("Segoe UI", 11, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(0, 8))

        language_values = ("hu", "en")
        language_display = {value: self.language_label(value) for value in language_values}
        language_reverse = {label: value for value, label in language_display.items()}
        language_var = tk.StringVar(value=language_display[self.language])

        def set_language(_event=None):
            self.language = language_reverse[language_var.get()]
            self.save_settings()
            self.close_settings_panel()
            self.refresh_current_view_language()
            self.open_settings_panel()

        language_combo = ttk.Combobox(
            panel,
            textvariable=language_var,
            values=[language_display[value] for value in language_values],
            state="readonly",
        )
        language_combo.pack(fill="x", pady=(0, 10))
        language_combo.bind("<<ComboboxSelected>>", set_language)

        tk.Label(
            panel,
            text=self.settings_ui_label("auto_role_policy"),
            font=("Segoe UI", 11, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(4, 8))

        policy_values = ("ask", "white", "black", "random")
        policy_display = {value: self.role_policy_label(value) for value in policy_values}
        policy_reverse = {label: value for value, label in policy_display.items()}
        policy_var = tk.StringVar(value=policy_display[self.auto_role_policy])

        def set_policy(_event=None):
            self.auto_role_policy = policy_reverse[policy_var.get()]
            self.save_settings()
        policy_combo = ttk.Combobox(
            panel,
            textvariable=policy_var,
            values=[policy_display[value] for value in policy_values],
            state="readonly",
        )
        policy_combo.pack(fill="x", pady=(0, 4))
        policy_combo.bind("<<ComboboxSelected>>", set_policy)

        tk.Label(
            panel,
            text=self.settings_ui_label("bot_tempo"),
            font=("Segoe UI", 11, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(14, 8))

        tempo_values = ("slow", "normal", "fast", "instant")
        tempo_display = {value: self.bot_tempo_label(value) for value in tempo_values}
        tempo_reverse = {label: value for value, label in tempo_display.items()}
        tempo_var = tk.StringVar(value=tempo_display[self.bot_tempo])

        def set_tempo(_event=None):
            self.bot_tempo = tempo_reverse[tempo_var.get()]
            self.save_settings()
        tempo_combo = ttk.Combobox(
            panel,
            textvariable=tempo_var,
            values=[tempo_display[value] for value in tempo_values],
            state="readonly",
        )
        tempo_combo.pack(fill="x", pady=(0, 4))
        tempo_combo.bind("<<ComboboxSelected>>", set_tempo)

        tk.Label(
            panel,
            text=self.settings_ui_label("default_move_limit"),
            font=("Segoe UI", 11, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(14, 8))

        tk.Label(
            panel,
            text=self.settings_ui_label("negative_is_infinite"),
            font=("Segoe UI", 10),
            bg="#efe5d8",
            fg="#6a6a6a",
            justify="left",
            wraplength=260,
        ).pack(anchor="w", pady=(0, 6))

        move_limit_var = tk.StringVar(value=str(self.default_move_limit))

        def save_default_move_limit(*_args):
            raw = move_limit_var.get().strip()
            if raw in {"", "-"}:
                return
            try:
                self.default_move_limit = int(raw)
            except ValueError:
                return
            self.save_settings()

        move_limit_entry = tk.Entry(panel, textvariable=move_limit_var, font=("Consolas", 14), justify="center", width=10)
        move_limit_entry.pack(anchor="w", pady=(0, 2))
        move_limit_entry.bind("<FocusOut>", save_default_move_limit)
        move_limit_entry.bind("<Return>", save_default_move_limit)

        tk.Label(
            panel,
            text=self.settings_ui_label("multiplayer_server"),
            font=("Segoe UI", 11, "bold"),
            bg="#efe5d8",
            fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(14, 8))

        host_row = tk.Frame(panel, bg=BG_COLOR)
        host_row.pack(fill="x", pady=(0, 6))
        tk.Label(host_row, text=self.settings_ui_label("host"), width=8, anchor="w", bg=BG_COLOR, fg=TEXT_COLOR).pack(side="left")
        host_var = tk.StringVar(value=self.server_host)
        self.settings_host_var = host_var
        host_entry = tk.Entry(host_row, textvariable=host_var)
        host_entry.pack(side="left", fill="x", expand=True)

        port_row = tk.Frame(panel, bg=BG_COLOR)
        port_row.pack(fill="x", pady=(0, 6))
        tk.Label(port_row, text=self.settings_ui_label("port"), width=8, anchor="w", bg=BG_COLOR, fg=TEXT_COLOR).pack(side="left")
        port_var = tk.StringVar(value=str(self.server_port))
        self.settings_port_var = port_var
        port_entry = tk.Entry(port_row, textvariable=port_var)
        port_entry.pack(side="left", fill="x", expand=True)

        def save_server_target(*_args):
            host = host_var.get().strip() or DEFAULT_SERVER_HOST
            try:
                port = int(port_var.get().strip())
            except ValueError:
                return
            self.server_host = host
            self.server_port = port
            self.save_settings()
        host_entry.bind("<FocusOut>", save_server_target)
        host_entry.bind("<Return>", save_server_target)
        port_entry.bind("<FocusOut>", save_server_target)
        port_entry.bind("<Return>", save_server_target)

        tk.Button(panel, text=self.settings_ui_label("close"), command=self.close_settings_panel, padx=12).pack(anchor="e", pady=(14, 0))
        self.settings_panel.update_idletasks()
        panel_width = self.settings_panel.winfo_reqwidth()
        panel_height = self.settings_panel.winfo_reqheight()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        preferred_right_x = anchor_x + anchor_width + 10
        preferred_left_x = anchor_x - panel_width - 10
        if preferred_right_x + panel_width <= root_width - 8:
            panel_x = preferred_right_x
        elif preferred_left_x >= 8:
            panel_x = preferred_left_x
        else:
            panel_x = max(8, min(preferred_right_x, root_width - panel_width - 8))
        panel_y = max(8, anchor_y - 2)
        if panel_y + panel_height > root_height - 8:
            panel_y = max(8, root_height - panel_height - 8)
        self.settings_panel.place(x=panel_x, y=panel_y)

    def on_settings_mousewheel(self, event):
        if self.settings_canvas is None:
            return
        self.settings_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def save_settings(self):
        write_client_settings(
            {
                "server_host": self.server_host,
                "server_port": self.server_port,
                "user_name": self.user_name,
                "session_role": self.session_role,
                "remember_token": self.remember_token,
                "suppress_auth_prompt": self.suppress_auth_prompt,
                "auto_role_policy": self.auto_role_policy,
                "bot_tempo": self.bot_tempo,
                "move_limit": self.default_move_limit,
                "language": self.language,
                "profile_stats": self.profile_stats,
            }
        )

    def start_spectator_game(self, room, game_state):
        self.start_game(
            {
                "mode": "spectator",
                "difficulty": None,
                "difficulty_label": None,
                "network_client": self.multiplayer_client,
                "room_code": room["room_code"],
                "move_limit": room.get("move_limit", self.default_move_limit),
                "initial_state": game_state,
                "host_username": room.get("host_username"),
                "guest_username": room.get("guest_username"),
                "ban_target_slot": "host",
            }
        )

    def settings_ui_label(self, key):
        labels = {
            "hu": {
                "title": "Beállítások",
                "language": "Nyelv",
                "auto_role_policy": "Automatikus szerepválasztás",
                "bot_tempo": "Bot tempó",
                "default_move_limit": "Alap lépéslimit",
                "negative_is_infinite": "Negatív szám = végtelen",
                "multiplayer_server": "Multiplayer szerver",
                "host": "Host",
                "port": "Port",
                "close": "Bezárás",
            },
            "en": {
                "title": "Settings",
                "language": "Language",
                "auto_role_policy": "Auto role policy",
                "bot_tempo": "Bot tempo",
                "default_move_limit": "Default move limit",
                "negative_is_infinite": "Negative number = infinite",
                "multiplayer_server": "Multiplayer server",
                "host": "Host",
                "port": "Port",
                "close": "Close",
            },
        }
        lang = self.language if self.language in labels else "en"
        return labels[lang][key]

    def ui_label(self, key):
        labels = {
            "hu": {
                "choose_mode": "Válassz játékmódot",
                "singleplayer": "Singleplayer",
                "multiplayer": "Multiplayer",
                "bot": "Bot",
                "bot_vs_bot": "Bot vs Bot",
                "mode": "Mód",
                "auto_role_policy": "Automatikus szerepválasztás",
                "undo": "Undo",
                "redo": "Redo",
                "back_to_menu": "Vissza a menübe",
                "report": "Report",
                "ban": "Ban",
                "pause": "Pause",
                "resume": "Resume",
                "game_subtitle": "Fordított irányítású sakk",
                "local_or_tcp": "Helyi hálón vagy külön TCP szerverrel használható.",
                "back": "Vissza",
                "start": "Start",
                "bot_difficulty": "Bot nehézség",
                "bot_difficulty_subtitle": "Válaszd ki a bot nehézségét. A bot a fekete játékost irányítja, így ő lép először a fehér bábukkal.",
                "easy": "Könnyű",
                "normal": "Normál",
                "hard": "Nehéz",
                "unbeatable": "Verhetetlen",
                "move_limit": "Lépéslimit",
                "move_limit_hint": "Adj meg számot. A -1 végtelen partit jelent.",
                "launch_error": "A lépéslimit csak egész szám lehet.",
                "white_bot": "Fehér bot",
                "black_bot": "Fekete bot",
                "bot_select_subtitle": "Válassz nehézséget a következő botnak.",
                "bot_match": "Bot meccs",
                "your_color": "Te színed",
                "what_color": "Mivel szeretnél játszani?",
                "white": "Fehér",
                "black": "Fekete",
                "random": "Random",
                "white_upper": "FEHÉR",
                "black_upper": "FEKETE",
                "white_lower": "fehér",
                "black_lower": "fekete",
                "multiplayer_login": "Multiplayer belépés",
                "server": "Szerver",
                "username": "Felhasználónév",
                "password": "Jelszó",
                "profile": "Profil",
                "guest": "Vendég",
                "remember_me": "Maradjak bejelentkezve",
                "login": "Belépés",
                "register": "Regisztráció",
                "switch_to_register": "Még nincs fiókod? Regisztrálj egyet ide kattintva!",
                "switch_to_login": "Már van fiókod? Jelentkezz be ide kattintva!",
                "register_success_return_login": "Sikeres regisztráció. Most jelentkezz be a frissen létrehozott fiókoddal.",
                "continue_as_guest": "Folytatás vendégként",
                "dont_remind_again": "Ne emlékeztessen újra",
                "account_prompt_title": "Belépés ajánlott",
                "account_prompt_subtitle": "Ha belépsz, a rendszer menti a multiplayer és bot elleni eredményeidet. A multiplayer statok a hitelesebbek, a bot elleni eredmények külön kerülnek tárolásra.",
                "account_auth_subtitle": "A helyi játék mehet vendégként is, de a mentett profilhoz és multiplayerhez bejelentkezés kell.",
                "stored_login": "Tárolt belépés",
                "account": "Fiók",
                "save_new_password": "Új jelszó mentése",
                "logged_in": "Bejelentkezve",
                "console_title": "Console",
                "console_role": "console",
                "console_placeholder_text": "Ez a console session csak szerveroldali fiok- es moderacios muveletekre valo. A meccsfigyeles nem ide tartozik.",
                "console_tools_soon": "Valassz egy kulon nezetet a lenti muveletekhez.",
                "new_password": "Uj jelszo",
                "console_reset_password": "Jelszo reset",
                "console_clear_balance": "Pontok torlese",
                "console_delete_user": "Fiok torlese",
                "console_target_required": "Adj meg egy felhasznalonevet.",
                "console_delete_confirm": "Biztosan torolni szeretned ezt a fiokot?",
                "console_action_done": "Console muvelet sikeres.",
                "console_ban_user": "Fiok tiltasa",
                "console_unban_user": "Fiok feloldasa",
                "console_make_admin": "Admin jog adasa",
                "console_remove_admin": "Admin jog elvetele",
                "console_refresh": "Frissites",
                "console_empty_snapshot": "Nincs megjelenitheto fiok.",
                "player_list": "Player lista",
                "console_players_subtitle": "Valassz ki egy fiokot a listabol. Az adminok vannak elol, utana mindenki ASCII sorrendben.",
                "search": "Kereses",
                "console_action_confirm": "Biztos vagyok benne, hogy ezt a muveletet akarom vegrehajtani.",
                "console_action_confirm_required": "Jelold be a megerosito negyzetet.",
                "console_clear_balance_confirm": "Biztos vagyok benne, hogy torolni akarom ennek a fioknak az osszes multiplayer es bot pontjat/statjat.",
                "admin": "Admin",
                "banned": "Tiltva",
                "not_banned": "Nincs tiltva",
                "admin_action_done": "Admin muvelet vegrehajtva.",
                "admin_ingame_tools": "Admin eszkozok",
                "admin_ingame_tools_subtitle": "In-match admin muveletek az aktualis ellenfeledhez.",
                "report_allowed": "Report jog: van",
                "report_revoked": "Report jog: elveve",
                "confirm_revoke_opponent_report": "Biztosan el akarod venni az ellenfeled report jogat?",
                "console_grant_report": "Report jog megadasa",
                "console_revoke_report": "Report jog elvetele",
                "console_profile_hint": "Ez egy operátori session. Itt szerveroldali account- és moderációs műveletek vannak, nem meccsfigyelés.",
                "guest_profile_hint": "Vendég módban játszol. A pontok és statok csak bejelentkezett fiókhoz menthetők.",
                "create_room": "Új játék létrehozása",
                "join_room": "Csatlakozás meglévőhöz",
                "logout": "Kijelentkezés",
                "delete_account": "Fiók törlése",
                "delete_account_warning": "Ez végleg törli a fiókodat. Írd be kétszer a jelenlegi jelszavad a megerősítéshez.",
                "confirm_password": "Jelszó újra",
                "join": "Csatlakozás",
                "enter_room_code": "Add meg a játékkódot",
                "multiplayer_lobby": "Multiplayer lobby",
                "room_code": "Játékkód",
                "waiting_opponent": "Várakozás ellenfélre...",
                "cancel": "Mégse",
                "host_auto_role": "Host auto role",
                "opponent_arrived": "Az ellenfél megérkezett.",
                "role_setup": "Az ellenfél megérkezett. Állítsd be a parti indulását:",
                "move_limit_short": "Lépéslimit (-1 = végtelen)",
                "role": "Szerep",
                "role_sent": "Szerepkiosztás elküldve...",
                "difficulty_suffix": "nehézsége",
                "enter_room_code_error": "Adj meg egy játékkódot.",
                "server_connect_error": "Nem sikerült csatlakozni a szerverhez",
                "enter_username_password": "Adj meg felhasználónevet és jelszót.",
                "no_stored_login": "Nincs mentett belépés.",
                "no_active_server_connection": "Nincs aktív kapcsolat a szerverhez.",
                "confirm_report": "Biztosan reportolni szeretnéd az ellenfelet?",
                "report_already_used_this_match": "Ebben a meccsben már egyszer reportoltad az ellenfeledet.",
                "already_assigned_to_room": "Már hozzá vagy rendelve egy szobához.",
                "confirm_ban": "Biztosan tiltani szeretnéd az ellenfelet?",
                "match_options_subtitle": "Állítsd be a parti lépéslimitjét.",
                "player": "Játékos",
                "wins": "Győzelem",
                "losses": "Vereség",
                "draws": "Döntetlen",
                "multiplayer_stats": "Multiplayer statok",
                "bot_stats": "Bot statok",
                "milestones_coming": "A mérföldkövek később ide kerülnek.",
                "now_moving": "Most mozog",
                "points": "Pontok",
                "moves": "Lépések",
                "rule_text": "Szabály: a mozgási rend sakk szerint normális, de mindig a másik játékos kattint a soron következő szín bábujaira. A pont a leütő bábu tulajdonosáé.",
                "you": "Te",
                "room": "Szoba",
                "selected_piece": "Kijelölt bábu",
                "piece_no_legal": "Ennek a bábunak most nincs szabályos lépése.",
                "pick_movable_enemy": "Válassz egy mozgatható ellenfél-bábut.",
                "bot_thinking": "A bot gondolkodik...",
                "bot_duel_paused": "Bot párbaj szüneteltetve.",
                "multiplayer_undo_unavailable": "A multiplayer undo később külön jóváhagyással lesz kezelve.",
                "multiplayer_redo_unavailable": "A multiplayer redo jelenleg nincs támogatva.",
                "delete_account_fill_both": "Mindkét jelszómezőt ki kell tölteni.",
                "passwords_do_not_match": "A két jelszó nem egyezik.",
                "delete_account_confirm_prompt": "Biztosan végleg törölni szeretnéd a fiókodat?",
                "delete_account_success": "Fiók törölve",
                "active_rooms": "Aktiv szobak",
                "active_rooms_subtitle": "Az admin itt tud belepni a futo meccsek megfigyeloi nezetebe.",
                "no_active_rooms": "Jelenleg nincs aktiv szoba.",
                "started": "Fut",
                "waiting": "Var",
                "spectate": "Nezes",
                "refresh": "Frissites",
                "spectator": "Spectator",
                "spectating_status": "Megfigyeloi nezet. A jatek csak olvashato.",
                "spectate_target": "Ban celpont",
                "spectate_ended": "A spectate munkamenet befejezodott.",
                "reason": "Ok",
            },
            "en": {
                "choose_mode": "Choose game mode",
                "singleplayer": "Singleplayer",
                "multiplayer": "Multiplayer",
                "bot": "Bot",
                "bot_vs_bot": "Bot vs Bot",
                "mode": "Mode",
                "auto_role_policy": "Auto role policy",
                "undo": "Undo",
                "redo": "Redo",
                "back_to_menu": "Back to menu",
                "report": "Report",
                "ban": "Ban",
                "pause": "Pause",
                "resume": "Resume",
                "game_subtitle": "Reverse-control chess",
                "local_or_tcp": "Usable on local network or through a dedicated TCP server.",
                "back": "Back",
                "start": "Start",
                "bot_difficulty": "Bot difficulty",
                "bot_difficulty_subtitle": "Choose the bot difficulty. The bot controls the black player, so it moves first with the white pieces.",
                "easy": "Easy",
                "normal": "Normal",
                "hard": "Hard",
                "unbeatable": "Unbeatable",
                "move_limit": "Move limit",
                "move_limit_hint": "Enter a number. -1 means an infinite match.",
                "launch_error": "Move limit must be an integer.",
                "white_bot": "White bot",
                "black_bot": "Black bot",
                "bot_select_subtitle": "Choose a difficulty for the next bot.",
                "bot_match": "Bot match",
                "your_color": "Your color",
                "what_color": "Which side do you want to play?",
                "white": "White",
                "black": "Black",
                "random": "Random",
                "white_upper": "WHITE",
                "black_upper": "BLACK",
                "white_lower": "white",
                "black_lower": "black",
                "multiplayer_login": "Multiplayer login",
                "server": "Server",
                "username": "Username",
                "password": "Password",
                "profile": "Profile",
                "guest": "Guest",
                "remember_me": "Stay signed in",
                "login": "Login",
                "register": "Register",
                "switch_to_register": "Don't have an account yet? Register one here!",
                "switch_to_login": "Already have an account? Click here to log in!",
                "register_success_return_login": "Registration successful. Now log in with your new account.",
                "continue_as_guest": "Continue as guest",
                "dont_remind_again": "Don't remind me again",
                "account_prompt_title": "Signing in is recommended",
                "account_prompt_subtitle": "Sign in to save your multiplayer and bot-match results. Multiplayer stats are the trusted ones; bot results are stored separately.",
                "account_auth_subtitle": "Local play can continue as a guest, but saved profiles and multiplayer require signing in.",
                "stored_login": "Stored login",
                "account": "Account",
                "save_new_password": "Save new password",
                "logged_in": "Logged in",
                "console_title": "Console",
                "console_role": "console",
                "console_placeholder_text": "This console session is only for server-side account and moderation work. Match supervision does not belong here.",
                "console_tools_soon": "Choose a dedicated workflow below.",
                "new_password": "New password",
                "console_reset_password": "Reset password",
                "console_clear_balance": "Clear balance",
                "console_delete_user": "Delete account",
                "console_target_required": "Enter a username.",
                "console_delete_confirm": "Are you sure you want to delete this account?",
                "console_action_done": "Console action completed.",
                "console_ban_user": "Ban account",
                "console_unban_user": "Unban account",
                "console_make_admin": "Grant admin",
                "console_remove_admin": "Remove admin",
                "console_refresh": "Refresh",
                "console_empty_snapshot": "There are no accounts to display.",
                "player_list": "Player list",
                "console_players_subtitle": "Pick an account from the list. Admins are shown first, then everyone else in ASCII order.",
                "search": "Search",
                "console_action_confirm": "I am sure I want to perform this action.",
                "console_action_confirm_required": "Tick the confirmation checkbox first.",
                "console_clear_balance_confirm": "I understand that this will clear this account's multiplayer and bot stats.",
                "admin": "Admin",
                "banned": "Banned",
                "not_banned": "Not banned",
                "admin_action_done": "Admin action completed.",
                "admin_ingame_tools": "Admin tools",
                "admin_ingame_tools_subtitle": "In-match admin actions for your current opponent.",
                "report_allowed": "Report permission: granted",
                "report_revoked": "Report permission: revoked",
                "confirm_revoke_opponent_report": "Are you sure you want to revoke your opponent's report permission?",
                "console_grant_report": "Grant report permission",
                "console_revoke_report": "Revoke report permission",
                "console_profile_hint": "This is an operator session for server-side account and moderation actions, not for match supervision.",
                "guest_profile_hint": "You are playing as a guest. Points and long-term stats are only saved for signed-in accounts.",
                "create_room": "Create new game",
                "join_room": "Join existing room",
                "logout": "Logout",
                "delete_account": "Delete account",
                "delete_account_warning": "This permanently deletes your account. Enter your current password twice to confirm.",
                "confirm_password": "Confirm password",
                "join": "Join",
                "enter_room_code": "Enter the room code",
                "multiplayer_lobby": "Multiplayer lobby",
                "room_code": "Room code",
                "waiting_opponent": "Waiting for opponent...",
                "cancel": "Cancel",
                "host_auto_role": "Host auto role",
                "opponent_arrived": "Opponent arrived.",
                "role_setup": "Your opponent arrived. Configure the match start:",
                "move_limit_short": "Move limit (-1 = infinite)",
                "role": "Role",
                "role_sent": "Role selection sent...",
                "difficulty_suffix": "difficulty",
                "enter_room_code_error": "Enter a room code.",
                "server_connect_error": "Could not connect to the server",
                "enter_username_password": "Enter a username and password.",
                "no_stored_login": "No stored login found.",
                "no_active_server_connection": "There is no active server connection.",
                "confirm_report": "Are you sure you want to report your opponent?",
                "report_already_used_this_match": "You have already reported your opponent once in this match.",
                "already_assigned_to_room": "You are already assigned to a room.",
                "confirm_ban": "Are you sure you want to ban your opponent?",
                "match_options_subtitle": "Set the match move limit.",
                "player": "Player",
                "wins": "Wins",
                "losses": "Losses",
                "draws": "Draws",
                "multiplayer_stats": "Multiplayer stats",
                "bot_stats": "Bot stats",
                "milestones_coming": "Milestones will appear here later.",
                "now_moving": "Now moving",
                "points": "Points",
                "moves": "Moves",
                "rule_text": "Rule: movement order is normal chess order, but the other player always clicks the side-to-move pieces. Points belong to the owner of the captured piece.",
                "you": "You",
                "room": "Room",
                "selected_piece": "Selected piece",
                "piece_no_legal": "This piece currently has no legal move.",
                "pick_movable_enemy": "Choose a movable opponent piece.",
                "bot_thinking": "The bot is thinking...",
                "bot_duel_paused": "Bot duel paused.",
                "multiplayer_undo_unavailable": "Multiplayer undo will be handled later with separate approval.",
                "multiplayer_redo_unavailable": "Multiplayer redo is currently not supported.",
                "delete_account_fill_both": "Both password fields are required.",
                "passwords_do_not_match": "The two passwords do not match.",
                "delete_account_confirm_prompt": "Are you sure you want to permanently delete your account?",
                "delete_account_success": "Account deleted",
                "active_rooms": "Active rooms",
                "active_rooms_subtitle": "Admins can enter active matches here in spectator mode.",
                "no_active_rooms": "There are no active rooms right now.",
                "started": "Started",
                "waiting": "Waiting",
                "spectate": "Spectate",
                "refresh": "Refresh",
                "spectator": "Spectator",
                "spectating_status": "Spectator view. This match is read-only.",
                "spectate_target": "Ban target",
                "spectate_ended": "The spectator session has ended.",
                "reason": "Reason",
            },
        }
        lang = self.language if self.language in labels else "en"
        return labels[lang][key]

    def role_policy_label(self, policy):
        labels = {
            "hu": {
                "ask": "Mindig kérdezzen",
                "white": "Mindig Fehér",
                "black": "Mindig Fekete",
                "random": "Mindig véletlen",
            },
            "en": {
                "ask": "Always ask",
                "white": "Always white",
                "black": "Always black",
                "random": "Always random",
            },
        }
        lang = self.language if self.language in labels else "en"
        return labels[lang][policy]

    def language_label(self, language):
        labels = {
            "hu": {"hu": "Magyar", "en": "Angol"},
            "en": {"hu": "Hungarian", "en": "English"},
        }
        lang = self.language if self.language in labels else "en"
        return labels[lang][language]

    def bot_tempo_label(self, tempo):
        labels = {
            "hu": {
                "slow": "Lassú",
                "normal": "Normál",
                "fast": "Gyors",
                "instant": "Azonnali",
            },
            "en": {
                "slow": "Slow",
                "normal": "Normal",
                "fast": "Fast",
                "instant": "Instant",
            },
        }
        lang = self.language if self.language in labels else "en"
        return labels[lang][tempo]

    def resolve_player_color(self, policy):
        if policy == "white":
            return "white"
        if policy == "black":
            return "black"
        return random.choice(["white", "black"])

    def bot_delay_ms(self):
        delays = {
            "slow": 450,
            "normal": 220,
            "fast": 80,
            "instant": 0,
        }
        return delays[self.bot_tempo]


def main():
    root = tk.Tk()
    UnchessApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
