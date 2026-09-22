"""프로토콜 검증용 로컬 시험 수신기. 메인 서버가 아니다."""

from __future__ import annotations

import argparse
import json
import logging
import socket
import struct
import threading
import time
from typing import Callable, Optional

from dolbom import protocol as proto

log = logging.getLogger("dolbom.receiver")


class TestReceiver:
    def __init__(self, host: str = "127.0.0.1", tcp_port: int = 45757, udp_port: int = 45004):
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self._running = False
        self._threads: list[threading.Thread] = []
        self.tcp_messages = 0
        self.udp_packets = 0
        self.last_tcp: Optional[dict] = None
        self.on_tcp: Optional[Callable[[dict], None]] = None
        self._clients: list[socket.socket] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        t1 = threading.Thread(target=self._tcp_loop, name="dolbom-tcp", daemon=True)
        t2 = threading.Thread(target=self._udp_loop, name="dolbom-udp", daemon=True)
        self._threads = [t1, t2]
        t1.start()
        t2.start()

    def stop(self) -> None:
        self._running = False
        with self._lock:
            for c in self._clients:
                try:
                    c.close()
                except OSError:
                    pass
            self._clients.clear()
        # poke sockets so accept/recv unwind
        try:
            s = socket.create_connection((self.host, self.tcp_port), timeout=0.3)
            s.close()
        except OSError:
            pass
        try:
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            u.sendto(b"x", (self.host, self.udp_port))
            u.close()
        except OSError:
            pass

    def broadcast_event(self, payload: dict) -> None:
        data = proto.encode_message(payload)
        with self._lock:
            clients = list(self._clients)
        for c in clients:
            try:
                c.sendall(data)
            except OSError:
                pass

    def _tcp_loop(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.tcp_port))
        srv.listen(4)
        srv.settimeout(0.5)
        log.info("test TCP listening on %s:%s", self.host, self.tcp_port)
        while self._running:
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._client, args=(conn,), name="dolbom-cli", daemon=True
            ).start()
        srv.close()

    def _client(self, conn: socket.socket) -> None:
        with self._lock:
            self._clients.append(conn)
        buf = bytearray()
        conn.settimeout(0.5)
        try:
            while self._running:
                try:
                    chunk = conn.recv(8192)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buf.extend(chunk)
                while True:
                    try:
                        msg, buf = proto.try_decode(buf)
                    except proto.ProtocolError:
                        buf.clear()
                        break
                    if msg is None:
                        break
                    self.tcp_messages += 1
                    self.last_tcp = msg
                    if self.on_tcp:
                        self.on_tcp(msg)
                    if msg.get("type") == proto.MSG_HELLO:
                        ack = {
                            "type": proto.MSG_HELLO_ACK,
                            "protocol_status": proto.PROTOCOL_STATUS,
                            "note": "local test receiver, not the production server",
                        }
                        conn.sendall(proto.encode_message(ack))
                    elif msg.get("type") == proto.MSG_PING:
                        conn.sendall(proto.encode_message({"type": proto.MSG_PONG}))
                    elif msg.get("type") == proto.MSG_SESSION_START:
                        event = {
                            "type": proto.MSG_EVENT,
                            "event_id": f"rx-{int(time.time()*1000)}",
                            "severity": "info",
                            "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "content": f"시험 수신기가 {msg.get('mode')} 세션 시작을 확인했습니다.",
                            "is_test": True,
                            "navigate_to": msg.get("mode") if msg.get("mode") != "cctv" else "cctv",
                        }
                        conn.sendall(proto.encode_message(event))
        finally:
            with self._lock:
                if conn in self._clients:
                    self._clients.remove(conn)
            try:
                conn.close()
            except OSError:
                pass

    def _udp_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.udp_port))
        sock.settimeout(0.5)
        log.info("test UDP listening on %s:%s", self.host, self.udp_port)
        while self._running:
            try:
                data, _addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            if data:
                self.udp_packets += 1
        sock.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="돌봄 시험 수신기 (메인 서버 아님)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--tcp", type=int, default=45757)
    parser.add_argument("--udp", type=int, default=45004)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    rx = TestReceiver(args.host, args.tcp, args.udp)
    rx.start()
    print(f"시험 수신기 대기 중 TCP {args.tcp} / UDP {args.udp} — Ctrl+C 종료")
    try:
        while True:
            time.sleep(2)
            print(f"TCP 메시지 {rx.tcp_messages} / UDP 패킷 {rx.udp_packets}")
    except KeyboardInterrupt:
        rx.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
