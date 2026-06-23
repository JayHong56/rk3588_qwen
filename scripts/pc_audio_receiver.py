#!/usr/bin/env python3
"""PC-side audio receiver — continuous streaming (single-threaded).

Protocol:
  1. Board sends 4B header: [4B BE sample_rate]
  2. Then: fixed-size raw S16_LE PCM chunks (4096 bytes each)
  3. Board sends at real-time rate; receiver just reads and plays.

First install:  pip install sounddevice numpy
"""

import socket
import struct
import sys
import numpy as np

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9876
CHUNK = 4096


def dbg(msg):
    print(f"  [DBG] {msg}", flush=True)


def recv_exactly(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("disconnected")
        buf += chunk
    return buf


def main():
    import sounddevice as sd
    print("sounddevice OK", flush=True)

    try:
        device = sd.default.device[1] or sd.default.device[0]
        dbg(f"output device: {sd.query_devices(device)['name']}")
    except Exception:
        pass

    print(f"Listening on port {PORT} ... (Ctrl+C to stop)", flush=True)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen(1)

    conn = None
    stream = None

    while True:
        try:
            print("Waiting for board connection ...", flush=True)
            conn, addr = server.accept()
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print(f"  connected from {addr[0]}", flush=True)

            # Read 4-byte sample_rate header
            header = recv_exactly(conn, 4)
            sample_rate = struct.unpack(">I", header)[0]
            print(f"  sr={sample_rate}", flush=True)

            stream = sd.OutputStream(
                samplerate=sample_rate, channels=1, dtype="int16",
                latency="high", blocksize=0,
            )
            stream.start()
            dbg(f"stream started sr={sample_rate}")

            total = 0
            try:
                while True:
                    raw = recv_exactly(conn, CHUNK)
                    samples = np.frombuffer(raw, dtype=np.int16).copy()
                    stream.write(samples)
                    total += len(raw)
            except ConnectionError:
                dbg(f"disconnected, total={total}")

        except KeyboardInterrupt:
            print("\nDone.")
            break
        except ConnectionError as e:
            print(f"  disconnected: {e}", flush=True)
        except Exception as e:
            print(f"  error: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                stream = None
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None


if __name__ == "__main__":
    main()
