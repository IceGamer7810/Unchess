import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from concurrent.futures import ProcessPoolExecutor
import json
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
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 7777
SETTINGS_PATH = Path(".settings.toml")

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


def write_client_settings(settings):
    content = (
        "[client]\n"
        f'server_host = "{settings["server_host"]}"\n'
        f"server_port = {int(settings['server_port'])}\n\n"
        "[gameplay]\n"
        f'auto_role_policy = "{settings["auto_role_policy"]}"\n'
        f'bot_tempo = "{settings["bot_tempo"]}"\n'
        f"move_limit = {int(settings['move_limit'])}\n"
    )
    SETTINGS_PATH.write_text(content, encoding="utf-8")


def load_client_settings():
    defaults = {
        "server_host": DEFAULT_SERVER_HOST,
        "server_port": DEFAULT_SERVER_PORT,
        "auto_role_policy": "ask",
        "bot_tempo": "normal",
        "move_limit": -1,
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
    gameplay = data.get("gameplay", {})
    settings["server_host"] = str(client.get("server_host", defaults["server_host"]))
    try:
        settings["server_port"] = int(client.get("server_port", defaults["server_port"]))
    except (TypeError, ValueError):
        settings["server_port"] = defaults["server_port"]
    settings["auto_role_policy"] = str(gameplay.get("auto_role_policy", defaults["auto_role_policy"]))
    settings["bot_tempo"] = str(gameplay.get("bot_tempo", defaults["bot_tempo"]))
    try:
        settings["move_limit"] = int(gameplay.get("move_limit", defaults["move_limit"]))
    except (TypeError, ValueError):
        settings["move_limit"] = defaults["move_limit"]
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
        self.root.minsize(WINDOW_WIDTH, WINDOW_HEIGHT)

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
        self.network_client = self.mode_config.get("network_client")
        self.pending_network_move = None

        self.status_var = tk.StringVar()
        self.score_var = tk.StringVar()
        self.turn_var = tk.StringVar()
        self.info_var = tk.StringVar()

        header = tk.Frame(self.container, bg=BG_COLOR, padx=16, pady=12)
        header.pack(fill="x")

        tk.Label(
            header,
            text=f"Mod: {self.mode_title()}",
            font=("Segoe UI", 11, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(side="left")

        tk.Button(
            header,
            text="Undo",
            command=self.undo_move,
            padx=12,
        ).pack(side="right", padx=(0, 8))

        tk.Button(
            header,
            text="Redo",
            command=self.redo_move,
            padx=12,
        ).pack(side="right", padx=(0, 8))

        tk.Button(
            header,
            text="Vissza a menübe",
            command=self.app.show_main_menu,
            padx=12,
        ).pack(side="right")

        if self.mode_config["mode"] == "bot_vs_bot":
            self.pause_button = tk.Button(
                header,
                text="Pause",
                command=self.toggle_bot_pause,
                padx=12,
            )
            self.pause_button.pack(side="right", padx=(0, 8))

        board_area = tk.Frame(self.container, bg=BG_COLOR)
        board_area.pack(fill="both", expand=True)
        board_area.grid_rowconfigure(0, weight=1)
        board_area.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            board_area,
            width=BOARD_PIXELS,
            height=BOARD_PIXELS,
            bg=BG_COLOR,
            highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self.on_mouse_click)
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        sidebar = tk.Frame(board_area, width=SIDEBAR_WIDTH, bg=BG_COLOR, padx=18, pady=20)
        sidebar.grid(row=0, column=1, sticky="ns")
        sidebar.grid_propagate(False)

        title = tk.Label(
            sidebar,
            text="Unchess",
            font=("Segoe UI", 24, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        )
        title.pack(anchor="w")

        subtitle = tk.Label(
            sidebar,
            text="Fordított irányítású sakk",
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
        )
        subtitle.pack(anchor="w", pady=(2, 16))

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

        self.draw()
        self.start_turn()

    def destroy(self):
        self.container.destroy()

    def toggle_bot_pause(self):
        if self.mode_config["mode"] != "bot_vs_bot":
            return
        self.bot_paused = not self.bot_paused
        if self.pause_button is not None:
            self.pause_button.configure(text="Resume" if self.bot_paused else "Pause")
        if self.bot_paused:
            if not self.bot_thinking:
                self.status_var.set("Bot párbaj szüneteltetve.")
                self.draw()
        else:
            if self.pending_bot_move is not None and not self.animating and not self.game_over:
                move = self.pending_bot_move
                self.pending_bot_move = None
                self.status_var.set("A bot gondolkodik...")
                self.draw()
                self.execute_move(move)
                return
            if not self.bot_thinking and self.is_bot_turn() and not self.game_over:
                self.status_var.set("A bot gondolkodik...")
                self.draw()
                self.root.after(80, self.run_bot_turn)

    def mode_title(self):
        if self.mode_config["mode"] == "singleplayer":
            return "Singleplayer"
        if self.mode_config["mode"] == "bot":
            return f"Bot - {self.mode_config['difficulty_label']}"
        if self.mode_config["mode"] == "bot_vs_bot":
            return f"Bot vs Bot - {self.mode_config['white_label']} / {self.mode_config['black_label']}"
        return "Multiplayer"

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
            messagebox.showinfo("Undo", "A multiplayer undo kesobb kulon jovahagyassal lesz kezelve.")
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
            messagebox.showinfo("Redo", "A multiplayer redo jelenleg nincs tamogatva.")
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
        square_size = max(24, board_pixels / BOARD_SIZE)
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
        player_name = "FEHÉR" if self.current_actor() == "white" else "FEKETE"
        moving_side = "fehér" if self.side_to_move == "white" else "fekete"
        self.turn_var.set(f"Játékos: {player_name}\nMost mozog: {moving_side}")
        limit_text = "∞" if self.move_limit < 0 else str(self.move_limit)
        self.score_var.set(
            f"Pontok\nFEHÉR: {self.score_white}\nFEKETE: {self.score_black}\nLépések: {self.move_count}/{limit_text}"
        )
        self.info_var.set(
            "Szabály: a mozgási rend sakk szerint normális, de mindig a másik játékos kattint a soron következő szín bábujaira. "
            "A pont a leütő bábu tulajdonosáé."
        )
        if self.mode_config["mode"] == "bot":
            bot_name = "FEHÉR" if self.mode_config["bot_color"] == "white" else "FEKETE"
            player_name = "FEHÉR" if self.mode_config["player_color"] == "white" else "FEKETE"
            self.info_var.set(
                f"{self.info_var.get()}\nTe: {player_name}\nBot: {bot_name} ({self.mode_config['difficulty_label']})"
            )
        if self.mode_config["mode"] == "bot_vs_bot":
            self.info_var.set(
                f"{self.info_var.get()}\nFehér bot: {self.mode_config['white_label']}\nFekete bot: {self.mode_config['black_label']}"
            )
        if self.mode_config["mode"] == "multiplayer":
            player_name = "FEHÉR" if self.mode_config["player_color"] == "white" else "FEKETE"
            room_code = self.mode_config.get("room_code", "??????")
            self.info_var.set(f"{self.info_var.get()}\nTe: {player_name}\nSzoba: {room_code}")

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
        return self.side_to_move == "white"

    def to_display_coords(self, row, col):
        if self.mode_config["mode"] == "bot_vs_bot":
            return col, BOARD_SIZE - 1 - row
        if self.board_flipped():
            return BOARD_SIZE - 1 - row, BOARD_SIZE - 1 - col
        return row, col

    def from_display_coords(self, draw_row, draw_col):
        if self.mode_config["mode"] == "bot_vs_bot":
            return BOARD_SIZE - 1 - draw_col, draw_row
        if self.board_flipped():
            return BOARD_SIZE - 1 - draw_row, BOARD_SIZE - 1 - draw_col
        return draw_row, draw_col

    def on_mouse_click(self, event):
        if self.animating or self.game_over or self.is_bot_turn() or self.pending_network_move is not None or self.bot_thinking:
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
                self.status_var.set(f"Kijelolt babu: {PIECE_SYMBOLS[clicked_piece]}")
            else:
                self.status_var.set("Ennek a bábunak most nincs szabályos lépése.")
        else:
            self.selected = None
            self.legal_moves = []
            self.status_var.set("Válassz egy mozgatható ellenfél-bábut.")

        self.draw()

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
        self.animating = False
        self.animating_from = None
        self.draw()
        self.start_turn()

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
        messagebox.showinfo("Játék vége", message)


class UnchessApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Unchess")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.resizable(True, True)
        self.root.minsize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)
        self.current_view = None
        self.pending_bot_difficulty = None
        self.pending_bvb = {}
        settings = load_client_settings()
        self.server_host = settings["server_host"]
        self.server_port = settings["server_port"]
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
        self.pending_multiplayer_action = None
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
        self.root.after(120, self.poll_network_events)
        self.show_main_menu()

    def on_app_close(self):
        self.close_multiplayer_client()
        self.root.destroy()

    def clear_view(self):
        self.close_settings_panel()
        if self.current_view is not None:
            self.current_view.destroy()
            self.current_view = None

    def close_multiplayer_client(self):
        self.ignore_next_disconnect = True
        if self.multiplayer_client is not None:
            self.multiplayer_client.close()
            self.multiplayer_client = None
        self.multiplayer_room = None
        self.multiplayer_is_host = False
        self.multiplayer_status_var = None
        self.multiplayer_room_var = None
        self.multiplayer_join_code_var = None
        self.multiplayer_host_controls = None
        self.multiplayer_move_limit_var = None
        self.pending_multiplayer_action = None

    def ensure_multiplayer_connection(self):
        if self.multiplayer_client is not None and self.multiplayer_client.connected:
            return
        client = MultiplayerClient(self.server_host, self.server_port)
        client.connect()
        self.ignore_next_disconnect = False
        self.multiplayer_client = client

    def poll_network_events(self):
        if self.multiplayer_client is not None:
            for event in self.multiplayer_client.poll_events():
                self.handle_network_event(event)
        self.root.after(120, self.poll_network_events)

    def show_main_menu(self):
        self.close_multiplayer_client()
        self.clear_view()
        frame = tk.Frame(self.root, bg=BG_COLOR, padx=40, pady=36)
        frame.pack(fill="both", expand=True)
        self.current_view = frame

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
            text="Válassz játékmódot",
            font=("Segoe UI", 13),
            bg=BG_COLOR,
            fg="#5a5a5a",
        ).pack(anchor="center", pady=(0, 24))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")

        self.menu_button(menu_card, "Singleplayer", self.start_singleplayer).pack(fill="x", pady=6)
        self.menu_button(menu_card, "Multiplayer", self.show_multiplayer_placeholder).pack(fill="x", pady=6)
        self.menu_button(menu_card, "Bot", self.show_bot_menu).pack(fill="x", pady=6)
        self.menu_button(menu_card, "Bot vs Bot", self.show_bot_vs_bot_white_menu).pack(fill="x", pady=6)

        tk.Label(
            frame,
            text="Helyi hálón vagy külön TCP szerverrel használható.",
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg="#6a6a6a",
        ).pack(anchor="center", pady=(20, 0))

    def show_bot_menu(self):
        self.clear_view()
        frame = tk.Frame(self.root, bg=BG_COLOR, padx=40, pady=36)
        frame.pack(fill="both", expand=True)
        self.current_view = frame

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text="Bot nehézség",
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text="Válaszd ki a bot nehézségét. A bot a fekete játékost irányítja, így ő lép először a fehér bábukkal.",
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
            wraplength=560,
            justify="center",
        ).pack(anchor="center", pady=(0, 24))

        tk.Label(
            frame,
            text=f"Auto role policy: {self.role_policy_label(self.auto_role_policy)}",
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg="#6a6a6a",
        ).pack(anchor="center", pady=(0, 12))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")

        difficulties = [
            ("easy", "Könnyű"),
            ("normal", "Normal"),
            ("hard", "Nehéz"),
            ("unbeatable", "Verhetetlen"),
        ]
        for difficulty, label in difficulties:
            self.menu_button(
                menu_card,
                label,
                lambda d=difficulty, l=label: self.show_bot_color_menu(d, l),
            ).pack(fill="x", pady=6)

        tk.Button(frame, text="Vissza", command=self.show_main_menu, padx=12).pack(pady=(18, 0))

    def show_match_options(self, title, subtitle, start_callback, back_callback):
        self.clear_view()
        frame = tk.Frame(self.root, bg=BG_COLOR, padx=40, pady=36)
        frame.pack(fill="both", expand=True)
        self.current_view = frame

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

        tk.Label(card, text="Lépéslimit", font=("Segoe UI", 11, "bold"), bg="#efe5d8", fg=TEXT_COLOR).pack(anchor="w")
        tk.Label(
            card,
            text="Adj meg számot. A -1 végtelen partit jelent.",
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
                messagebox.showerror("Indítás", "A lépéslimit csak egész szám lehet.")
                return
            start_callback(move_limit)

        self.menu_button(card, "Start", begin).pack(fill="x", pady=6)
        tk.Button(frame, text="Vissza", command=back_callback, padx=12).pack(pady=(18, 0))

    def show_bot_vs_bot_white_menu(self):
        self.pending_bvb = {}
        self.show_bot_vs_bot_selector("white")

    def show_bot_vs_bot_black_menu(self):
        self.show_bot_vs_bot_selector("black")

    def show_bot_vs_bot_selector(self, color):
        self.clear_view()
        frame = tk.Frame(self.root, bg=BG_COLOR, padx=40, pady=36)
        frame.pack(fill="both", expand=True)
        self.current_view = frame

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        side_label = "Fehér bot" if color == "white" else "Fekete bot"
        tk.Label(
            frame,
            text=f"{side_label} nehézsége",
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text="Válassz nehézséget a következő botnak.",
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
        ).pack(anchor="center", pady=(0, 24))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")

        difficulties = [
            ("easy", "Könnyű"),
            ("normal", "Normál"),
            ("hard", "Nehéz"),
            ("unbeatable", "Verhetetlen"),
        ]
        for difficulty, label in difficulties:
            self.menu_button(
                menu_card,
                label,
                lambda d=difficulty, l=label, c=color: self.select_bvb_difficulty(c, d, l),
            ).pack(fill="x", pady=6)

        tk.Button(
            frame,
            text="Vissza",
            command=self.show_main_menu if color == "white" else self.show_bot_vs_bot_white_menu,
            padx=12,
        ).pack(pady=(18, 0))

    def select_bvb_difficulty(self, color, difficulty, label):
        self.pending_bvb[color] = {"difficulty": difficulty, "label": label}
        if color == "white":
            self.show_bot_vs_bot_black_menu()
        else:
            self.show_match_options(
                "Bot vs Bot",
                "Állítsd be a parti lépéslimitjét.",
                self.start_bot_vs_bot_game,
                self.show_bot_vs_bot_black_menu,
            )

    def show_bot_color_menu(self, difficulty, label):
        self.pending_bot_difficulty = {"difficulty": difficulty, "label": label}
        if self.auto_role_policy != "ask":
            self.show_match_options(
                "Bot meccs",
                "Állítsd be a parti lépéslimitjét.",
                lambda move_limit: self.start_bot_game(self.resolve_player_color(self.auto_role_policy), move_limit),
                self.show_bot_menu,
            )
            return
        self.clear_view()
        frame = tk.Frame(self.root, bg=BG_COLOR, padx=40, pady=36)
        frame.pack(fill="both", expand=True)
        self.current_view = frame

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text="Te színed",
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text="Mivel szeretnél játszani?",
            font=("Segoe UI", 12),
            bg=BG_COLOR,
            fg="#5a5a5a",
        ).pack(anchor="center", pady=(0, 24))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")

        self.menu_button(menu_card, "Fehér", lambda: self.show_bot_match_options("white")).pack(fill="x", pady=6)
        self.menu_button(menu_card, "Fekete", lambda: self.show_bot_match_options("black")).pack(fill="x", pady=6)
        self.menu_button(menu_card, "Random", self.start_random_bot_game).pack(fill="x", pady=6)

        tk.Button(frame, text="Vissza", command=self.show_bot_menu, padx=12).pack(pady=(18, 0))

    def show_multiplayer_placeholder(self):
        self.clear_view()
        frame = tk.Frame(self.root, bg=BG_COLOR, padx=40, pady=36)
        frame.pack(fill="both", expand=True)
        self.current_view = frame

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text="Multiplayer",
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text=f"Szerver: {self.server_host}:{self.server_port}",
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#5a5a5a",
            wraplength=560,
            justify="center",
        ).pack(anchor="center", pady=(0, 24))

        menu_card = tk.Frame(frame, bg="#efe5d8", padx=22, pady=22)
        menu_card.pack(anchor="center")

        self.menu_button(menu_card, "Új játék létrehozása", self.multiplayer_create_room).pack(fill="x", pady=6)
        self.menu_button(menu_card, "Csatlakozás meglévőhöz", self.show_multiplayer_join_menu).pack(fill="x", pady=6)

        tk.Label(
            frame,
            text=f"Host auto role: {self.role_policy_label(self.auto_role_policy)}",
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg="#6a6a6a",
        ).pack(anchor="center", pady=(18, 0))

        tk.Button(frame, text="Vissza", command=self.show_main_menu, padx=12).pack(pady=(18, 0))

    def multiplayer_create_room(self):
        try:
            self.ensure_multiplayer_connection()
            self.pending_multiplayer_action = {"kind": "create"}
            self.multiplayer_client.send({"type": "create_room"})
        except OSError as exc:
            messagebox.showerror("Multiplayer", f"Nem sikerult csatlakozni a szerverhez: {exc}")

    def show_multiplayer_join_menu(self):
        self.clear_view()
        frame = tk.Frame(self.root, bg=BG_COLOR, padx=40, pady=36)
        frame.pack(fill="both", expand=True)
        self.current_view = frame

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        tk.Label(
            frame,
            text="Csatlakozás",
            font=("Segoe UI", 26, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="center", pady=(10, 8))

        tk.Label(
            frame,
            text="Add meg a játékkódot",
            font=("Segoe UI", 12),
            bg=BG_COLOR,
            fg="#5a5a5a",
        ).pack(anchor="center", pady=(0, 18))

        self.multiplayer_join_code_var = tk.StringVar()
        entry = tk.Entry(frame, textvariable=self.multiplayer_join_code_var, font=("Consolas", 20), justify="center", width=10)
        entry.pack(pady=(0, 18))
        entry.focus_set()

        self.menu_button(frame, "Csatlakozás", self.multiplayer_join_room).pack(anchor="center")
        tk.Button(frame, text="Vissza", command=self.show_multiplayer_placeholder, padx=12).pack(pady=(18, 0))

    def multiplayer_join_room(self):
        code = (self.multiplayer_join_code_var.get() if self.multiplayer_join_code_var is not None else "").strip().upper()
        if not code:
            messagebox.showerror("Multiplayer", "Adj meg egy játékkódot.")
            return
        try:
            self.ensure_multiplayer_connection()
            self.pending_multiplayer_action = {"kind": "join", "code": code}
            self.multiplayer_client.send({"type": "join_room", "room_code": code})
        except OSError as exc:
            messagebox.showerror("Multiplayer", f"Nem sikerult csatlakozni a szerverhez: {exc}")

    def show_multiplayer_waiting_room(self, host, code="......"):
        self.multiplayer_is_host = host
        self.clear_view()
        frame = tk.Frame(self.root, bg=BG_COLOR, padx=40, pady=36)
        frame.pack(fill="both", expand=True)
        self.current_view = frame

        top_bar = tk.Frame(frame, bg=BG_COLOR)
        top_bar.pack(fill="x")
        self.mount_settings_button(top_bar)

        self.multiplayer_room_var = tk.StringVar(value=code)
        self.multiplayer_status_var = tk.StringVar(value="Várakozás ellenfélre...")

        tk.Label(frame, text="Multiplayer lobby", font=("Segoe UI", 26, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(10, 8))
        tk.Label(frame, text="Játékkód", font=("Segoe UI", 11), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center")
        tk.Label(frame, textvariable=self.multiplayer_room_var, font=("Consolas", 24, "bold"), bg=BG_COLOR, fg=TEXT_COLOR).pack(anchor="center", pady=(0, 18))
        tk.Label(frame, textvariable=self.multiplayer_status_var, font=("Segoe UI", 11), bg=BG_COLOR, fg="#5a5a5a").pack(anchor="center", pady=(0, 18))

        self.multiplayer_host_controls = tk.Frame(frame, bg=BG_COLOR)
        self.multiplayer_host_controls.pack(anchor="center")
        if host:
            tk.Label(
                self.multiplayer_host_controls,
                text=f"Host auto role: {self.role_policy_label(self.auto_role_policy)}",
                font=("Segoe UI", 10),
                bg=BG_COLOR,
                fg="#6a6a6a",
            ).pack()

        tk.Button(frame, text="Mégse", command=self.cancel_multiplayer, padx=12).pack(pady=(18, 0))

    def show_multiplayer_role_choice(self):
        if self.multiplayer_host_controls is None:
            return
        for child in self.multiplayer_host_controls.winfo_children():
            child.destroy()
        self.multiplayer_move_limit_var = tk.StringVar(value=str(self.default_move_limit))
        tk.Label(
            self.multiplayer_host_controls,
            text="Az ellenfél megérkezett. Állítsd be a parti indulását:",
            font=("Segoe UI", 10, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(pady=(0, 8))
        tk.Label(
            self.multiplayer_host_controls,
            text="Lépéslimit (-1 = végtelen)",
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
        if self.auto_role_policy == "ask":
            tk.Button(row, text="Fehér", command=lambda: self.send_role_choice("white"), padx=12).pack(side="left", padx=4)
            tk.Button(row, text="Fekete", command=lambda: self.send_role_choice("black"), padx=12).pack(side="left", padx=4)
            tk.Button(row, text="Random", command=lambda: self.send_role_choice("random"), padx=12).pack(side="left", padx=4)
        else:
            tk.Label(
                row,
                text=f"Szerep: {self.role_policy_label(self.auto_role_policy)}",
                font=("Segoe UI", 10),
                bg=BG_COLOR,
                fg=TEXT_COLOR,
            ).pack(side="left", padx=(0, 8))
            tk.Button(row, text="Start", command=lambda: self.send_role_choice(self.auto_role_policy), padx=12).pack(side="left", padx=4)

    def send_role_choice(self, choice):
        if self.multiplayer_client is not None:
            try:
                move_limit = int((self.multiplayer_move_limit_var.get() if self.multiplayer_move_limit_var is not None else str(self.default_move_limit)).strip())
            except ValueError:
                messagebox.showerror("Multiplayer", "A lépéslimit csak egész szám lehet.")
                return
            self.multiplayer_status_var.set("Szerepkiosztás elküldve...")
            self.multiplayer_client.send({"type": "choose_role", "preference": choice, "move_limit": move_limit})

    def cancel_multiplayer(self):
        self.close_multiplayer_client()
        self.show_multiplayer_placeholder()

    def start_singleplayer(self):
        self.show_match_options(
            "Singleplayer",
            "Állítsd be a parti lépéslimitjét.",
            self.start_singleplayer_game,
            self.show_main_menu,
        )

    def start_singleplayer_game(self, move_limit):
        self.start_game({"mode": "singleplayer", "difficulty": None, "difficulty_label": None, "move_limit": move_limit})

    def start_random_bot_game(self):
        self.show_bot_match_options(random.choice(["white", "black"]))

    def show_bot_match_options(self, player_color):
        self.show_match_options(
            "Bot meccs",
            "Állítsd be a parti lépéslimitjét.",
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

    def start_multiplayer_game(self, player_color, room_code, move_limit):
        self.start_game(
            {
                "mode": "multiplayer",
                "difficulty": None,
                "difficulty_label": None,
                "player_color": player_color,
                "network_client": self.multiplayer_client,
                "room_code": room_code,
                "move_limit": move_limit,
            }
        )

    def start_game(self, mode_config):
        self.clear_view()
        self.current_view = UnchessGame(self, self.root, mode_config)

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
            messagebox.showerror("Multiplayer", event.get("message", "Szerverhiba"))
            if self.pending_multiplayer_action and self.pending_multiplayer_action["kind"] == "join":
                self.show_multiplayer_join_menu()
            elif self.pending_multiplayer_action and self.pending_multiplayer_action["kind"] == "create":
                self.show_multiplayer_placeholder()
            self.pending_multiplayer_action = None
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
                self.multiplayer_status_var.set("Csatlakozva. Várakozás a hostra...")
            return
        if event_type == "room_ready_for_role_choice":
            self.multiplayer_room = event["room"]
            if self.multiplayer_room_var is not None:
                self.multiplayer_room_var.set(event["room"]["room_code"])
            if self.multiplayer_status_var is not None:
                self.multiplayer_status_var.set("Az ellenfél megérkezett.")
            if self.multiplayer_is_host:
                self.show_multiplayer_role_choice()
            return
        if event_type == "game_start":
            room = event["room"]
            self.multiplayer_room = room
            if self.multiplayer_client is None:
                return
            if room["host_connected"] and room["guest_connected"]:
                if self.multiplayer_room_var is not None:
                    self.multiplayer_room_var.set(room["room_code"])
                assignment = room["role_assignment"]
                # If we created the room, we are the host. Otherwise we are the guest.
                player_color = assignment["host"] if self.multiplayer_is_host else assignment["guest"]
                self.start_multiplayer_game(player_color, room["room_code"], room.get("move_limit", self.default_move_limit))
            return
        if event_type == "player_left":
            room = event["room"]
            self.multiplayer_room = room
            if isinstance(self.current_view, UnchessGame) and self.current_view.mode_config["mode"] == "multiplayer":
                leaver = event.get("player_name", "Az ellenfél")
                if event.get("game_was_started"):
                    messagebox.showinfo("Multiplayer", f"{leaver} kilépett. Nyertél.")
                else:
                    messagebox.showinfo("Multiplayer", f"{leaver} kilépett. A szoba bezárult.")
                self.close_multiplayer_client()
                self.show_multiplayer_placeholder()
                return
            if self.multiplayer_status_var is not None:
                self.multiplayer_status_var.set("Az ellenfél kilépett.")
            self.close_multiplayer_client()
            self.show_multiplayer_placeholder()
            return
        if event_type == "move_broadcast":
            if isinstance(self.current_view, UnchessGame) and self.current_view.mode_config["mode"] == "multiplayer":
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

    def draw_settings_icon(self, canvas, angle_degrees, scale):
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

        self.settings_anim_start = time.perf_counter()
        self.settings_anim_duration_ms = duration_ms
        self.settings_anim_from_angle = self.settings_icon_angle
        self.settings_anim_to_angle = target_angle
        self.settings_anim_from_scale = self.settings_icon_scale
        self.settings_anim_to_scale = target_scale

        def ease_in_out_sine(t):
            return 0.5 - 0.5 * math.cos(math.pi * t)

        def step():
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

    def close_settings_panel(self):
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
        if self.settings_button is not None and not self.settings_hovered:
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
            text="Beállítások",
            font=("Segoe UI", 12, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(
            panel,
            text="Auto role policy",
            font=("Segoe UI", 11, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(0, 8))

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
            text="Bot tempó",
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
            text="Alap lépéslimit",
            font=("Segoe UI", 11, "bold"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(14, 8))

        tk.Label(
            panel,
            text="Negatív szám = végtelen",
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
            text="Multiplayer szerver",
            font=("Segoe UI", 11, "bold"),
            bg="#efe5d8",
            fg=TEXT_COLOR,
        ).pack(anchor="w", pady=(14, 8))

        host_row = tk.Frame(panel, bg=BG_COLOR)
        host_row.pack(fill="x", pady=(0, 6))
        tk.Label(host_row, text="Host", width=8, anchor="w", bg=BG_COLOR, fg=TEXT_COLOR).pack(side="left")
        host_var = tk.StringVar(value=self.server_host)
        self.settings_host_var = host_var
        host_entry = tk.Entry(host_row, textvariable=host_var)
        host_entry.pack(side="left", fill="x", expand=True)

        port_row = tk.Frame(panel, bg=BG_COLOR)
        port_row.pack(fill="x", pady=(0, 6))
        tk.Label(port_row, text="Port", width=8, anchor="w", bg=BG_COLOR, fg=TEXT_COLOR).pack(side="left")
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

        tk.Button(panel, text="Bezárás", command=self.close_settings_panel, padx=12).pack(anchor="e", pady=(14, 0))
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
                "auto_role_policy": self.auto_role_policy,
                "bot_tempo": self.bot_tempo,
                "move_limit": self.default_move_limit,
            }
        )

    def role_policy_label(self, policy):
        labels = {
            "ask": "Mindig kérdezzen",
            "white": "Mindig Fehér",
            "black": "Mindig Fekete",
            "random": "Mindig Random",
        }
        return labels[policy]

    def bot_tempo_label(self, tempo):
        labels = {
            "slow": "Lassú",
            "normal": "Normál",
            "fast": "Gyors",
            "instant": "Instant",
        }
        return labels[tempo]

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
