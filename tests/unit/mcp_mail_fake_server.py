"""A scriptable IMAP-over-TLS server for mcp-mail's tests (plan §R.12 S1-*).

Not a general IMAP implementation: it answers exactly the six commands the
plan permits, with the response shapes `imaplib` parses, and lets a test
inject the faults the acceptance rows name (stalls, dripped or oversized
literals, duplicate or unsolicited responses, a `NO` on one chunk, junk after
LOGOUT, a rejected login, a handshake that never completes). Everything the
server sends is recorded nowhere; everything it receives is kept in
`commands` so a test can assert what was never sent (no LOGIN after the
latch, no SELECT ever).
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import re
import socket
import ssl
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def internaldate(instant: dt.datetime) -> str:
    instant = instant.astimezone(dt.timezone.utc)
    return f"{instant.day:02d}-{_MONTHS[instant.month - 1]}-{instant.year} " \
           f"{instant:%H:%M:%S} +0000"


@dataclass
class Msg:
    uid: int
    arrived: dt.datetime
    sender: str = "Alice <alice@example.com>"
    subject: str = "hello"
    date_header: str | None = None       # sender-claimed; None omits it
    message_id: str | None = None
    unseen: bool = True
    extra_headers: str = ""

    def header_block(self) -> bytes:
        lines = []
        if self.date_header is not None:
            lines.append(f"Date: {self.date_header}")
        lines.append(f"From: {self.sender}")
        lines.append(f"Subject: {self.subject}")
        mid = self.message_id or f"<{self.uid}@example.com>"
        lines.append(f"Message-ID: {mid}")
        block = "\r\n".join(lines) + "\r\n"
        if self.extra_headers:
            block += self.extra_headers
        return block.encode("utf-8", "surrogateescape") + b"\r\n"


# ---------------------------------------------------------------------------
# Certificates (§R.10.1 S1-1): a test CA, and leaf certificates it signs.
# ---------------------------------------------------------------------------


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write(path: Path, data: bytes) -> str:
    path.write_bytes(data)
    return str(path)


@dataclass
class CertSet:
    ca_file: str
    cert_file: str
    key_file: str


def make_certs(tmp: Path, *, hostname: str = "localhost", ca_subject: str = "mcp-mail test CA",
               not_before: dt.datetime | None = None, not_after: dt.datetime | None = None,
               self_signed: bool = False, san_ip: bool = True) -> CertSet:
    now = dt.datetime.now(dt.timezone.utc)
    not_before = not_before or (now - dt.timedelta(days=1))
    not_after = not_after or (now + dt.timedelta(days=1))
    ca_key = _key()
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ca_subject)])
    ca_cert = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
               .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - dt.timedelta(days=2)).not_valid_after(now + dt.timedelta(days=2))
               .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
               .sign(ca_key, hashes.SHA256()))
    leaf_key = _key()
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    names: list[x509.GeneralName] = [x509.DNSName(hostname)]
    if san_ip:
        names.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    san = x509.SubjectAlternativeName(names)
    builder = (x509.CertificateBuilder().subject_name(leaf_name)
               .issuer_name(leaf_name if self_signed else ca_name)
               .public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(not_before).not_valid_after(not_after)
               .add_extension(san, critical=False)
               .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True))
    leaf_cert = builder.sign(leaf_key if self_signed else ca_key, hashes.SHA256())
    pem = serialization.Encoding.PEM
    stem = f"{hostname}-{uuid.uuid4().hex[:8]}"      # every set gets its own files
    return CertSet(
        ca_file=_write(tmp / f"ca-{stem}.pem", ca_cert.public_bytes(pem)),
        cert_file=_write(tmp / f"leaf-{stem}.pem", leaf_cert.public_bytes(pem)),
        key_file=_write(tmp / f"leaf-{stem}.key", leaf_key.private_bytes(
            pem, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption())),
    )


# ---------------------------------------------------------------------------
# The server
# ---------------------------------------------------------------------------


@dataclass
class Faults:
    greeting_delay_s: float = 0.0
    stall_handshake: bool = False          # accept TCP, never speak TLS
    stall_after_greeting: bool = False     # send the greeting, then nothing
    reject_login: bool = False
    op_delay_s: float = 0.0                # delay before every tagged reply
    search_padding: int = 0                # extra bytes of whitespace in the SEARCH line
    literal_size_override: int | None = None   # announce this literal size regardless of content
    drip_literal: float = 0.0              # seconds between literal bytes (0 = whole)
    duplicate_fetch_responses: int = 0     # repeat each FETCH response N extra times
    extra_fetch_uids: list[int] = field(default_factory=list)   # responses for unrequested UIDs
    unsolicited_lines: int = 0             # `* n EXISTS` lines before every tagged reply
    unsolicited_line_bytes: int = 32
    no_on_metadata_chunk: int | None = None    # answer NO to the Nth INTERNALDATE chunk (0-based)
    no_on_header_fetch: bool = False
    drop_metadata_uids: set[int] = field(default_factory=set)   # omit these UIDs' data
    omit_uidvalidity: bool = False
    logout_junk_bytes: int = 0
    stall_logout: bool = False
    oversize_metadata_line: int = 0        # pad INTERNALDATE lines with this many bytes
    expunge_before_fetch: set[int] = field(default_factory=set)  # UIDs that vanish after SEARCH
    renumber_sequence: bool = False
    header_fetch_delay_s: float = 0.0
    close_after_search: bool = False
    search_lines: list[bytes] | None = None   # replaces the `* SEARCH ...` line(s) verbatim
    literal_before_uid: bool = False          # header FETCH item order: BODY[...] first, UID last


class FakeIMAPServer:
    def __init__(self, certs: CertSet, mailbox: list[Msg], *, faults: Faults | None = None,
                 uidvalidity: int = 1700000001) -> None:
        self.certs = certs
        self.mailbox = {m.uid: m for m in mailbox}
        self.faults = faults or Faults()
        self.uidvalidity = uidvalidity
        self.commands: list[str] = []
        self.raw_commands: list[bytes] = []     # whole command lines, tag included
        self.logins: int = 0
        self.greetings_sent: int = 0
        self.connections: int = 0
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._lock = threading.Lock()
        self._ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._ctx.load_cert_chain(certs.cert_file, certs.key_file)

    def start(self) -> "FakeIMAPServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass

    # -- accept loop ---------------------------------------------------------

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, raw: socket.socket) -> None:
        f = self.faults
        try:
            if f.stall_handshake:
                time.sleep(30)
                return
            tls = self._ctx.wrap_socket(raw, server_side=True)
        except (ssl.SSLError, OSError):
            raw.close()
            return
        try:
            tls.settimeout(30)
            if f.greeting_delay_s:
                time.sleep(f.greeting_delay_s)
            self._send(tls, b"* OK fake IMAP ready\r\n")
            with self._lock:
                self.greetings_sent += 1
            if f.stall_after_greeting:
                time.sleep(30)
                return
            rfile = tls.makefile("rb")
            while True:
                line = rfile.readline()
                if not line:
                    return
                if not self._dispatch(tls, line.rstrip(b"\r\n")):
                    return
        except (ssl.SSLError, OSError, BrokenPipeError):
            pass
        finally:
            try:
                tls.close()
            except OSError:
                pass

    @staticmethod
    def _send(sock: ssl.SSLSocket, data: bytes) -> None:
        sock.sendall(data)

    def _unsolicited(self, sock) -> None:
        for _ in range(self.faults.unsolicited_lines):
            self._send(sock, b"* " + str(len(self.mailbox)).encode() + b" EXISTS"
                       + b" " * max(0, self.faults.unsolicited_line_bytes - 12) + b"\r\n")

    def _dispatch(self, sock, line: bytes) -> bool:
        f = self.faults
        parts = line.split(b" ", 2)
        if len(parts) < 2:
            return True
        tag, cmd = parts[0], parts[1].upper()
        rest = parts[2] if len(parts) > 2 else b""
        name = cmd.decode()
        if cmd == b"UID":
            sub = rest.split(b" ", 1)[0].upper().decode()
            name = f"UID {sub}"
            rest = rest.split(b" ", 1)[1] if b" " in rest else b""
        with self._lock:
            self.commands.append(name)
            self.raw_commands.append(line)
        if f.op_delay_s:
            time.sleep(f.op_delay_s)
        self._unsolicited(sock)
        if cmd == b"CAPABILITY":
            self._send(sock, b"* CAPABILITY IMAP4rev1\r\n" + tag + b" OK CAPABILITY completed\r\n")
        elif cmd == b"LOGIN":
            with self._lock:
                self.logins += 1
            if f.reject_login:
                self._send(sock, tag + b" NO [AUTHENTICATIONFAILED] Invalid credentials\r\n")
            else:
                self._send(sock, tag + b" OK LOGIN completed\r\n")
        elif cmd == b"EXAMINE":
            out = [b"* " + str(len(self.mailbox)).encode() + b" EXISTS", b"* 0 RECENT",
                   b"* FLAGS (\\Seen \\Answered)"]
            if not f.omit_uidvalidity:
                out.append(b"* OK [UIDVALIDITY " + str(self.uidvalidity).encode() + b"] UIDs valid")
            out.append(b"* OK [UIDNEXT " + str(max(self.mailbox, default=0) + 1).encode() + b"] Predicted")
            out.append(tag + b" OK [READ-ONLY] EXAMINE completed")
            self._send(sock, b"\r\n".join(out) + b"\r\n")
        elif name == "UID SEARCH":
            uids = sorted(u for u, m in self.mailbox.items() if m.unseen)
            if f.search_lines is not None:
                body = b"".join(line + b"\r\n" for line in f.search_lines)
            else:
                body = (b"* SEARCH " + b" ".join(str(u).encode() for u in uids)
                        + b" " * f.search_padding + b"\r\n")
            self._send(sock, body + tag + b" OK SEARCH completed\r\n")
            if f.close_after_search:
                return False
            for uid in f.expunge_before_fetch:
                self.mailbox.pop(uid, None)
        elif name == "UID FETCH":
            return self._fetch(sock, tag, rest)
        elif cmd == b"LOGOUT":
            if f.stall_logout:
                time.sleep(5)
            if f.logout_junk_bytes:
                self._send(sock, b"* BYE " + b"x" * f.logout_junk_bytes + b"\r\n")
            self._send(sock, b"* BYE see you\r\n" + tag + b" OK LOGOUT completed\r\n")
            return False
        else:
            self._send(sock, tag + b" BAD unknown command\r\n")
        return True

    _metadata_chunks_seen = 0

    def _fetch(self, sock, tag: bytes, rest: bytes) -> bool:
        f = self.faults
        uidset, _, items = rest.partition(b" ")
        requested = [int(x) for x in uidset.decode().split(",") if x.isdigit()]
        header_fetch = b"BODY.PEEK" in items.upper()
        if not header_fetch:
            index = self._metadata_chunks_seen
            self._metadata_chunks_seen += 1
            if f.no_on_metadata_chunk is not None and index == f.no_on_metadata_chunk:
                self._send(sock, tag + b" NO FETCH failed for this chunk\r\n")
                return True
        elif f.no_on_header_fetch:
            self._send(sock, tag + b" NO FETCH failed\r\n")
            return True
        if header_fetch and f.header_fetch_delay_s:
            time.sleep(f.header_fetch_delay_s)
        out = bytearray()
        targets = list(requested) + list(f.extra_fetch_uids)
        for seq, uid in enumerate(targets, start=1):
            msg = self.mailbox.get(uid)
            if msg is None or uid in f.drop_metadata_uids:
                continue
            seqnum = seq * 7 if f.renumber_sequence else seq
            head = (b"* " + str(seqnum).encode() + b" FETCH (UID " + str(uid).encode()
                    + b' INTERNALDATE "' + internaldate(msg.arrived).encode() + b'"')
            if header_fetch:
                block = msg.header_block()
                size = f.literal_size_override if f.literal_size_override is not None else len(block)
                item = b"BODY[HEADER.FIELDS (DATE FROM SUBJECT MESSAGE-ID)]<0> {" + str(size).encode() + b"}\r\n"
                if f.literal_before_uid:
                    line = b"* " + str(seqnum).encode() + b" FETCH (" + item
                    trailer = (b" UID " + str(uid).encode() + b' INTERNALDATE "'
                               + internaldate(msg.arrived).encode() + b'")\r\n')
                else:
                    line, trailer = head + b" " + item, b")\r\n"
                for _ in range(1 + f.duplicate_fetch_responses):
                    self._send(sock, bytes(line))
                    if f.drip_literal:
                        for i in range(min(size, len(block))):
                            self._send(sock, block[i:i + 1])
                            time.sleep(f.drip_literal)
                    else:
                        self._send(sock, block[:size] if size <= len(block) else block)
                    self._send(sock, trailer)
            else:
                pad = b" " * f.oversize_metadata_line
                line = head + pad + b")\r\n"
                for _ in range(1 + f.duplicate_fetch_responses):
                    out += line
        if out:
            self._send(sock, bytes(out))
        self._send(sock, tag + b" OK FETCH completed\r\n")
        return True
