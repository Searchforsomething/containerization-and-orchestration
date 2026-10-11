import time

from flask import Flask, request

app = Flask(__name__)

# Holds references to allocated memory blocks so they aren't garbage collected.
_memory_hog = []


@app.route("/health")
def health():
    return "ok"


@app.route("/eat")
def eat():
    mb = request.args.get("mb", default=0, type=int)
    if mb <= 0:
        return "mb must be a positive integer", 400

    chunk = bytearray(mb * 1024 * 1024)
    for i in range(0, len(chunk), 4096):
        chunk[i] = 1
    _memory_hog.append(chunk)

    return f"allocated {mb} MB, total held: {sum(len(c) for c in _memory_hog) // (1024 * 1024)} MB"


@app.route("/burn")
def burn():
    while True:
        pass


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
