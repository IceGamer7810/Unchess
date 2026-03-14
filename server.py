import json
import logging
from pathlib import Path
import random
import socketserver
import string
import threading
import tomllib


SERVER_CONFIG_PATH = Path(".server.toml")
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 7777
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")


def write_server_config(host, port):
    content = f'[server]\nhost = "{host}"\nport = {int(port)}\n'
    SERVER_CONFIG_PATH.write_text(content, encoding="utf-8")


def load_server_config():
    if not SERVER_CONFIG_PATH.exists():
        write_server_config(DEFAULT_HOST, DEFAULT_PORT)
        return DEFAULT_HOST, DEFAULT_PORT
    try:
        data = tomllib.loads(SERVER_CONFIG_PATH.read_text(encoding="utf-8"))
        server = data.get("server", {})
        host = str(server.get("host", DEFAULT_HOST))
        port = int(server.get("port", DEFAULT_PORT))
    except Exception:
        write_server_config(DEFAULT_HOST, DEFAULT_PORT)
        return DEFAULT_HOST, DEFAULT_PORT
    write_server_config(host, port)
    return host, port


HOST, PORT = load_server_config()


def generate_room_code(length=6):
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


class Room:
    def __init__(self, code, host_session):
        self.code = code
        self.host = host_session
        self.guest = None
        self.role_assignment = None
        self.side_to_move = "white"
        self.started = False
        self.move_limit = -1

    def to_payload(self):
        return {
            "room_code": self.code,
            "host_connected": self.host is not None,
            "guest_connected": self.guest is not None,
            "role_assignment": self.role_assignment,
            "move_limit": self.move_limit,
        }


class UnchessRequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.server.register_session(self)
        logging.info("Client connected from %s:%s", *self.client_address)
        self.send({"type": "hello_ack", "message": "Unchess server ready"})

        try:
            while True:
                raw = self.rfile.readline()
                if not raw:
                    break
                try:
                    message = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    self.send({"type": "error", "message": "Invalid JSON"})
                    continue
                self.server.handle_message(self, message)
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            logging.info("Client connection dropped from %s:%s (%s)", self.client_address[0], self.client_address[1], exc)
        finally:
            self.server.disconnect_session(self)

    def send(self, payload):
        encoded = (json.dumps(payload) + "\n").encode("utf-8")
        self.wfile.write(encoded)
        self.wfile.flush()


class UnchessTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_class):
        super().__init__(server_address, handler_class)
        self.lock = threading.Lock()
        self.rooms = {}
        self.sessions = set()
        self.session_names = {}
        self.session_rooms = {}

    def register_session(self, session):
        with self.lock:
            self.sessions.add(session)

    def safe_send(self, session, payload):
        try:
            session.send(payload)
            return True
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            name = self.session_names.get(session, "Unknown")
            logging.info("Send failed to %s (%s)", name, exc)
            return False

    def disconnect_session(self, session):
        with self.lock:
            self.sessions.discard(session)
            room_code = self.session_rooms.pop(session, None)
            name = self.session_names.pop(session, "Unknown")
            if room_code is None:
                logging.info("Client disconnected: %s", name)
                return
            room = self.rooms.get(room_code)
            if room is None:
                logging.info("Client disconnected from missing room: %s", name)
                return

            if room.host == session:
                room.host = None
            if room.guest == session:
                room.guest = None

            if room.host is None and room.guest is None:
                self.rooms.pop(room_code, None)
                logging.info("Room %s closed", room_code)
                return

            logging.info("Player left room %s: %s", room_code, name)
            payload = {
                "type": "player_left",
                "room": room.to_payload(),
                "player_name": name,
                "game_was_started": room.started,
            }
            remaining_session = room.host if room.host is not None else room.guest
            if room.started and remaining_session is not None:
                winner_role = "host" if room.host is not None else "guest"
                winner_name = self.session_names.get(remaining_session, "Unknown")
                payload["winner_role"] = winner_role
                payload["winner_name"] = winner_name
            self.broadcast_room(room, payload)
            if room.host is not None:
                self.session_rooms.pop(room.host, None)
            if room.guest is not None:
                self.session_rooms.pop(room.guest, None)
            self.rooms.pop(room_code, None)
            logging.info("Room %s closed after disconnect", room_code)

    def handle_message(self, session, message):
        msg_type = message.get("type")
        if msg_type == "hello":
            name = message.get("name") or "Anonymous"
            with self.lock:
                self.session_names[session] = name
            session.send({"type": "hello_ack", "name": name})
            return

        if msg_type == "create_room":
            self.create_room(session, message)
            return

        if msg_type == "join_room":
            self.join_room(session, message)
            return

        if msg_type == "choose_role":
            self.choose_role(session, message)
            return

        if msg_type == "submit_move":
            self.submit_move(session, message)
            return

        session.send({"type": "error", "message": f"Unknown message type: {msg_type}"})

    def create_room(self, session, message):
        with self.lock:
            code = generate_room_code()
            while code in self.rooms:
                code = generate_room_code()
            room = Room(code, session)
            self.rooms[code] = room
            self.session_rooms[session] = code
        logging.info("Room created: %s", code)
        self.safe_send(session, {"type": "room_created", "room": room.to_payload()})

    def join_room(self, session, message):
        code = (message.get("room_code") or "").upper()
        with self.lock:
            room = self.rooms.get(code)
            if room is None:
                self.safe_send(session, {"type": "error", "message": "Room not found"})
                return
            if room.guest is not None:
                self.safe_send(session, {"type": "error", "message": "Room already full"})
                return
            room.guest = session
            self.session_rooms[session] = code
            guest_name = self.session_names.get(session, "Guest")
            logging.info("Room joined: %s by %s", code, guest_name)
            self.safe_send(session, {"type": "room_joined", "room": room.to_payload()})
            self.broadcast_room(room, {"type": "room_ready_for_role_choice", "room": room.to_payload()})

    def choose_role(self, session, message):
        code = self.session_rooms.get(session)
        with self.lock:
            room = self.rooms.get(code)
            if room is None or room.host != session:
                self.safe_send(session, {"type": "error", "message": "Only the host can choose roles"})
                return
            if room.guest is None:
                self.safe_send(session, {"type": "error", "message": "Cannot choose role before guest joins"})
                return
            preference = message.get("preference", "random")
            try:
                room.move_limit = int(message.get("move_limit", -1))
            except (TypeError, ValueError):
                room.move_limit = -1
            room.role_assignment = self.resolve_role_assignment(preference)
            room.started = True
            room.side_to_move = "white"
            logging.info("Room %s role assignment selected: %s", code, preference)
        self.broadcast_room(room, {"type": "game_start", "room": room.to_payload()})

    def submit_move(self, session, message):
        code = self.session_rooms.get(session)
        with self.lock:
            room = self.rooms.get(code)
            if room is None or not room.started or room.role_assignment is None:
                self.safe_send(session, {"type": "error", "message": "Game has not started"})
                return

            actor = "black" if room.side_to_move == "white" else "white"
            expected_session = room.host if room.role_assignment["host"] == actor else room.guest
            if expected_session != session:
                self.safe_send(session, {"type": "error", "message": "Not your turn"})
                return

            room.side_to_move = "black" if room.side_to_move == "white" else "white"
            move_payload = message.get("move")
            logging.info("Room %s move: %s", code, move_payload)
            payload = {"type": "move_broadcast", "move": move_payload, "side_to_move": room.side_to_move}
        self.broadcast_room(room, payload)

    def resolve_role_assignment(self, preference):
        if preference == "white":
            return {"host": "white", "guest": "black"}
        if preference == "black":
            return {"host": "black", "guest": "white"}
        return {"host": random.choice(["white", "black"]), "guest": None}

    def broadcast_room(self, room, payload):
        if payload["type"] == "game_start" and room.role_assignment and room.role_assignment["guest"] is None:
            room.role_assignment["guest"] = "black" if room.role_assignment["host"] == "white" else "white"
            payload["room"] = room.to_payload()
        failed_sessions = []
        for session in (room.host, room.guest):
            if session is not None:
                if not self.safe_send(session, payload):
                    failed_sessions.append(session)
        for session in failed_sessions:
            self.disconnect_session(session)


def main():
    with UnchessTCPServer((HOST, PORT), UnchessRequestHandler) as server:
        print(f"Unchess server listening on {HOST}:{PORT}")
        server.serve_forever()


if __name__ == "__main__":
    main()
