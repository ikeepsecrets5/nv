
import os
import json
import time
import secrets
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = os.getenv("PANEL_SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

limiter = Limiter(get_remote_address, app=app, default_limits=["180 per minute"])

API_KEY = os.getenv("BOT_API_KEY", "troque-essa-key")
ADMIN_USER = os.getenv("PANEL_ADMIN_USER", "admin")
ADMIN_PASSWORD_HASH = os.getenv("PANEL_ADMIN_PASSWORD_HASH")

if not ADMIN_PASSWORD_HASH:
    ADMIN_PASSWORD_HASH = generate_password_hash(os.getenv("PANEL_ADMIN_PASSWORD", "troque-essa-senha"))

DATA_PATH = Path(os.getenv("DATA_PATH", "data.json"))
CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "config.json"))

def read_json(path, fallback):
    try:
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback

def write_json(path, data):
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")

def load_data():
    return read_json(DATA_PATH, {})

def save_data(data):
    write_json(DATA_PATH, data)

def load_config():
    return read_json(CONFIG_PATH, {
        "bot_name": os.getenv("BOT_NAME", "Livinho do Maranhão"),
        "idol_user_id": "",
        "idol_role_id": "",
        "maintenance": False
    })

def save_config(config):
    write_json(CONFIG_PATH, config)

def auth_ok():
    return request.headers.get("Authorization") == API_KEY

def get_user(data, user_id):
    user_id = str(user_id)
    if user_id not in data:
        data[user_id] = {}

    user = data[user_id]
    defaults = {
        "money": 100,
        "xp": 0,
        "rolls": 0,
        "anime_rolls": 0,
        "luck": 1.0,
        "classe": None,
        "melhor_aura": None,
        "melhor_aura_poder": 0,
        "kakera": 0,
        "aura_frag": 0,
        "anime_frag": 0,
        "badges": [],
        "titles": [],
        "harem": []
    }

    for k, v in defaults.items():
        user.setdefault(k, v)

    return user

def public_user(user_id, user):
    return {
        "id": str(user_id),
        "money": user.get("money", 0),
        "xp": user.get("xp", 0),
        "rolls": user.get("rolls", 0),
        "anime_rolls": user.get("anime_rolls", 0),
        "luck": user.get("luck", 1.0),
        "classe": user.get("classe"),
        "melhor_aura": user.get("melhor_aura"),
        "melhor_aura_poder": user.get("melhor_aura_poder", 0),
        "kakera": user.get("kakera", 0),
        "aura_frag": user.get("aura_frag", 0),
        "anime_frag": user.get("anime_frag", 0),
        "badges": user.get("badges", []),
        "titles": user.get("titles", []),
        "harem_total": len(user.get("harem", []))
    }

def sorted_users():
    data = load_data()
    users = [public_user(uid, get_user(data, uid)) for uid in data]
    users.sort(key=lambda u: (int(u.get("xp", 0) or 0), int(u.get("money", 0) or 0)), reverse=True)
    return users

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject():
    return {
        "config": load_config(),
        "bot_name": load_config().get("bot_name", "Livinho do Maranhão"),
        "year": time.strftime("%Y")
    }

@app.route("/")
def home():
    return render_template("home.html", users=sorted_users()[:6])

@app.route("/comandos")
def comandos():
    lista = [
        ("Economia", "/daily", "Pega recompensa diária."),
        ("Economia", "/work", "Trabalha para ganhar moedas."),
        ("Economia", "/gamble", "Aposta moedas."),
        ("Loja", "/shop", "Mostra a loja."),
        ("Loja", "/buy", "Compra itens."),
        ("Perfil", "/stats", "Mostra seu perfil."),
        ("Aura RNG", "/roll", "Gira auras."),
        ("Aura RNG", "/auralist", "Lista as auras."),
        ("Aura RNG", "/topaura", "Ranking de auras."),
        ("Anime RNG", "/wish", "Gira personagens."),
        ("Anime RNG", "/claim", "Pega personagem."),
        ("Anime RNG", "/collection", "Mostra coleção."),
        ("Servidor", "/character", "Escolhe personagem."),
        ("Servidor", "/rerace", "Troca personagem.")
    ]
    return render_template("comandos.html", comandos=lista)

@app.route("/ranking")
def ranking():
    return render_template("ranking.html", users=sorted_users()[:50])

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("8 per minute")
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == ADMIN_USER and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session.clear()
            session["logged_in"] = True
            return redirect(url_for("dashboard"))

        flash("Usuário ou senha incorretos.", "danger")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", users=sorted_users()[:100])

@app.route("/perfil")
@login_required
def perfil():
    user_id = request.args.get("user_id", "").strip()
    profile = None

    if user_id:
        data = load_data()
        user = get_user(data, user_id)
        save_data(data)
        profile = public_user(user_id, user)

    return render_template("perfil.html", user_id=user_id, profile=profile)

@app.route("/alterar", methods=["GET", "POST"])
@login_required
def alterar():
    result = None

    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        kind = request.form.get("kind", "money")

        try:
            amount = int(request.form.get("amount", "0"))
        except ValueError:
            amount = 0

        if kind not in ["money", "xp", "rolls", "anime_rolls", "kakera"]:
            kind = "money"

        data = load_data()
        user = get_user(data, user_id)
        user[kind] = int(user.get(kind, 0) or 0) + amount
        save_data(data)
        result = public_user(user_id, user)
        flash("Alteração aplicada com sucesso.", "success")

    return render_template("alterar.html", result=result)

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    config = load_config()

    if request.method == "POST":
        config["bot_name"] = request.form.get("bot_name", config.get("bot_name", "")).strip()
        config["idol_user_id"] = request.form.get("idol_user_id", "").strip()
        config["idol_role_id"] = request.form.get("idol_role_id", "").strip()
        config["maintenance"] = request.form.get("maintenance") == "on"
        save_config(config)
        flash("Configurações salvas.", "success")
        return redirect(url_for("settings"))

    return render_template("settings.html", config=config)

@app.route("/api")
def api_index():
    return jsonify({
        "ok": True,
        "message": "API + site online no Render",
        "users_saved": len(load_data()),
        "bot_name": load_config().get("bot_name", "Livinho do Maranhão")
    })

@app.route("/api/config")
def api_config():
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(load_config())

@app.route("/api/users")
def api_users():
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(sorted_users()[:200])

@app.route("/api/user/<user_id>")
def api_get_user(user_id):
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401

    data = load_data()
    user = get_user(data, user_id)
    save_data(data)
    return jsonify(public_user(user_id, user))

@app.route("/api/sync_user", methods=["POST"])
def api_sync_user():
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    user_id = str(body.get("id") or body.get("user_id") or "").strip()

    if not user_id:
        return jsonify({"error": "user_id vazio"}), 400

    allowed = [
        "money", "xp", "rolls", "anime_rolls", "luck", "classe",
        "melhor_aura", "melhor_aura_poder", "kakera",
        "aura_frag", "anime_frag", "badges", "titles", "harem"
    ]

    data = load_data()
    user = get_user(data, user_id)

    for key in allowed:
        if key in body:
            user[key] = body[key]

    save_data(data)
    return jsonify({"success": True, "user": public_user(user_id, user)})

@app.route("/api/update", methods=["POST"])
def api_update():
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    user_id = str(body.get("user_id", "")).strip()
    field = body.get("field", "money")

    try:
        amount = int(body.get("amount", 0))
    except Exception:
        amount = 0

    if field not in ["money", "xp", "rolls", "anime_rolls", "kakera"]:
        return jsonify({"error": "campo inválido"}), 400

    data = load_data()
    user = get_user(data, user_id)
    user[field] = int(user.get(field, 0) or 0) + amount
    save_data(data)
    return jsonify({"success": True, "user": public_user(user_id, user)})

@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="Página não encontrada."), 404

@app.errorhandler(500)
def server_error(error):
    return render_template("error.html", code=500, message="Erro interno do servidor."), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
