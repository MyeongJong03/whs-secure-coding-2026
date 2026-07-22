import os

from dotenv import load_dotenv

from app import create_app
from app.extensions import socketio

load_dotenv()

app = create_app(os.getenv("FLASK_CONFIG"))


if __name__ == "__main__":
    socketio.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=app.config["DEBUG"],
    )
