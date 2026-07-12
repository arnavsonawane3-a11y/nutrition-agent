"""
AI-Powered Nutrition Agent — Flask + IBM Watsonx.ai (Granite)
Vercel Serverless Deployment Version
=============================================================
Customise agent behaviour in the AGENT_INSTRUCTIONS block below.
"""

import os
import json
import re
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv
from ibm_watsonx_ai import APIClient, Credentials
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai.foundation_models.utils.enums import ModelTypes
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

# ────────────────────────────────────────────────────────────────────────────
# AGENT INSTRUCTIONS  ← Customise everything here
# ────────────────────────────────────────────────────────────────────────────
AGENT_INSTRUCTIONS = {
    # Persona & tone
    "persona": (
        "You are NutriBot, a warm, knowledgeable, and encouraging AI nutrition coach. "
        "You communicate in a friendly yet professional tone. You never sound robotic. "
        "You always motivate users and celebrate small wins."
    ),

    # Diet specialization
    "specialization": (
        "You specialise in balanced Indian and South-Asian diets, vegetarian and "
        "vegan meal planning, diabetic-friendly nutrition, weight management, "
        "sports nutrition, and family meal planning for all age groups."
    ),

    # Indian food preferences
    "indian_food": (
        "Prioritise traditional Indian foods: dal, sabzi, roti, rice, idli, dosa, "
        "poha, upma, khichdi, curd, paneer, sprouts, and seasonal vegetables. "
        "Incorporate Ayurvedic principles where relevant (e.g., warm foods in winter). "
        "Suggest regional variety — North Indian, South Indian, Bengali, Gujarati, etc."
    ),

    # Safety rules  ← NEVER remove or weaken these
    "safety_rules": (
        "ALWAYS include this disclaimer when giving specific medical nutrition advice: "
        "'Please consult a registered dietitian or your doctor before making major "
        "dietary changes, especially if you have a medical condition.' "
        "NEVER recommend extreme calorie restriction below 1200 kcal/day for adults. "
        "NEVER diagnose medical conditions. "
        "NEVER suggest supplements as meal replacements. "
        "Flag any query that involves eating disorders with compassionate redirection "
        "to professional help."
    ),

    # Response format guidelines
    "format": (
        "Structure responses clearly with headings, bullet points, and emoji where "
        "appropriate. For meal plans use a table or numbered list. "
        "Keep individual answers concise (under 400 words) unless a full meal plan "
        "is explicitly requested. Always end with a helpful follow-up question."
    ),

    # Extra custom rules — add your own below
    "custom": (
        "Respect religious dietary restrictions (Jain, Hindu vegetarian, halal, etc.) "
        "when the user mentions them. "
        "For children under 12 always recommend consulting a paediatrician."
    ),
}

# Build the system prompt from AGENT_INSTRUCTIONS
SYSTEM_PROMPT = "\n\n".join([
    AGENT_INSTRUCTIONS["persona"],
    AGENT_INSTRUCTIONS["specialization"],
    AGENT_INSTRUCTIONS["indian_food"],
    AGENT_INSTRUCTIONS["safety_rules"],
    AGENT_INSTRUCTIONS["format"],
    AGENT_INSTRUCTIONS["custom"],
])

# ────────────────────────────────────────────────────────────────────────────
# App setup
# ────────────────────────────────────────────────────────────────────────────
load_dotenv()

app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "nutrition-agent-secret-2024")
CORS(app)

# Initialise database tables on startup (no-op if they already exist)
try:
    db.init_db()
except Exception as _db_err:
    print(f"[warn] DB init skipped: {_db_err}")

IBM_API_KEY   = os.getenv("IBM_API_KEY")
IBM_PROJECT_ID = os.getenv("IBM_PROJECT_ID")
IBM_URL       = os.getenv("IBM_URL", "https://us-south.ml.cloud.ibm.com")

# ────────────────────────────────────────────────────────────────────────────
# Watsonx model initialisation (lazy — created once on first request)
# ────────────────────────────────────────────────────────────────────────────
_model = None

def get_model():
    global _model
    if _model is None:
        if not IBM_API_KEY or not IBM_PROJECT_ID:
            raise ValueError(
                "IBM_API_KEY and IBM_PROJECT_ID must be set in the .env file."
            )
        credentials = Credentials(url=IBM_URL, api_key=IBM_API_KEY)
        client      = APIClient(credentials)
        _model = ModelInference(
            model_id="ibm/granite-13b-instruct-v2",
            api_client=client,
            project_id=IBM_PROJECT_ID,
            params={
                "max_new_tokens": 1024,
                "min_new_tokens": 20,
                "temperature":    0.7,
                "top_p":          0.9,
                "repetition_penalty": 1.1,
            },
        )
    return _model

# ────────────────────────────────────────────────────────────────────────────
# Helper — build prompt
# ────────────────────────────────────────────────────────────────────────────
def build_prompt(user_message: str, history: list, profile: dict | None = None) -> str:
    profile_context = ""
    if profile:
        profile_context = (
            f"\n\nUser profile: Name={profile.get('name','')}, "
            f"Age={profile.get('age','')}, Gender={profile.get('gender','')}, "
            f"Weight={profile.get('weight','')} kg, Height={profile.get('height','')} cm, "
            f"Goal={profile.get('goal','')}, Diet={profile.get('diet','')}, "
            f"Allergies={profile.get('allergies','none')}."
        )

    history_text = ""
    for turn in history[-6:]:          # keep last 3 exchanges
        role = "User" if turn["role"] == "user" else "NutriBot"
        history_text += f"\n{role}: {turn['content']}"

    prompt = (
        f"[SYSTEM]\n{SYSTEM_PROMPT}{profile_context}\n\n"
        f"[CONVERSATION]{history_text}\nUser: {user_message}\nNutriBot:"
    )
    return prompt

# ────────────────────────────────────────────────────────────────────────────
# Nutrition utilities
# ────────────────────────────────────────────────────────────────────────────
def calculate_bmi(weight_kg: float, height_cm: float) -> dict:
    height_m = height_cm / 100
    bmi      = round(weight_kg / (height_m ** 2), 1)
    if   bmi < 18.5: category = "Underweight"
    elif bmi < 25.0: category = "Normal weight"
    elif bmi < 30.0: category = "Overweight"
    else:            category = "Obese"
    return {"bmi": bmi, "category": category}

def calculate_tdee(weight_kg: float, height_cm: float,
                   age: int, gender: str, activity: str) -> dict:
    # Mifflin-St Jeor BMR
    if gender.lower() in ("male", "m"):
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    activity_map = {
        "sedentary":  1.2,
        "light":      1.375,
        "moderate":   1.55,
        "active":     1.725,
        "very_active":1.9,
    }
    factor = activity_map.get(activity.lower(), 1.55)
    tdee   = round(bmr * factor)
    return {
        "bmr":       round(bmr),
        "tdee":      tdee,
        "loss":      tdee - 500,
        "gain":      tdee + 300,
        "maintain":  tdee,
    }

# ────────────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────────────
def _get_session_id() -> str:
    """Return a stable session ID, creating one if absent."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data       = request.get_json(force=True)
    message    = data.get("message", "").strip()
    history    = data.get("history", [])
    profile    = data.get("profile")
    session_id = data.get("session_id") or _get_session_id()

    if not message:
        return jsonify({"error": "Empty message"}), 400

    # Persist the incoming user message
    try:
        db.append_message(session_id, "user", message)
    except Exception:
        pass  # DB failure must never break chat

    try:
        model  = get_model()
        prompt = build_prompt(message, history, profile)
        result = model.generate_text(prompt=prompt)
        reply  = result.strip() if isinstance(result, str) else result
        # Strip any echoed prompt prefix that the model might include
        for prefix in ("NutriBot:", "Assistant:"):
            if reply.startswith(prefix):
                reply = reply[len(prefix):].strip()

        # Persist the assistant reply
        try:
            db.append_message(session_id, "assistant", reply)
        except Exception:
            pass

        return jsonify({
            "reply":      reply,
            "timestamp":  datetime.now().isoformat(),
            "session_id": session_id,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/profile", methods=["GET"])
def get_profile():
    session_id = request.args.get("session_id") or _get_session_id()
    profile = db.load_profile(session_id)
    if profile is None:
        return jsonify({"profile": None}), 200
    return jsonify({"profile": profile, "session_id": session_id})


@app.route("/api/profile", methods=["POST"])
def post_profile():
    data       = request.get_json(force=True)
    session_id = data.get("session_id") or _get_session_id()
    profile    = data.get("profile", {})
    try:
        db.save_profile(session_id, profile)
        return jsonify({"ok": True, "session_id": session_id})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/history", methods=["GET"])
def get_history():
    session_id = request.args.get("session_id") or _get_session_id()
    limit      = min(int(request.args.get("limit", 40)), 200)
    try:
        history = db.get_recent_history(session_id, limit)
        return jsonify({"history": history, "session_id": session_id})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/history", methods=["DELETE"])
def delete_history():
    data       = request.get_json(force=True)
    session_id = data.get("session_id") or _get_session_id()
    try:
        db.clear_history(session_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/bmi", methods=["POST"])
def bmi_endpoint():
    data = request.get_json(force=True)
    try:
        result = calculate_bmi(float(data["weight"]), float(data["height"]))
        return jsonify(result)
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/tdee", methods=["POST"])
def tdee_endpoint():
    data = request.get_json(force=True)
    try:
        result = calculate_tdee(
            float(data["weight"]),
            float(data["height"]),
            int(data["age"]),
            data["gender"],
            data.get("activity", "moderate"),
        )
        return jsonify(result)
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/meal-plan", methods=["POST"])
def meal_plan():
    """Generate a quick AI meal plan for given calories & preferences."""
    data       = request.get_json(force=True)
    calories   = data.get("calories", 2000)
    diet_type  = data.get("diet", "balanced")
    days       = min(int(data.get("days", 3)), 7)
    profile    = data.get("profile")

    prompt_msg = (
        f"Create a {days}-day Indian meal plan for {calories} kcal/day, "
        f"{diet_type} diet. Include breakfast, lunch, dinner and one snack per day. "
        "Show approximate calories for each meal in a structured table format."
    )
    try:
        model  = get_model()
        prompt = build_prompt(prompt_msg, [], profile)
        result = model.generate_text(prompt=prompt)
        reply  = result.strip() if isinstance(result, str) else result
        return jsonify({"plan": reply})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/family-plan", methods=["POST"])
def family_plan():
    """Generate a family nutrition plan."""
    data    = request.get_json(force=True)
    members = data.get("members", [])

    members_text = "; ".join(
        f"{m.get('name','Member')} (age {m.get('age','?')}, {m.get('goal','healthy eating')})"
        for m in members
    )
    prompt_msg = (
        f"Create a balanced Indian weekly meal plan for this family: {members_text}. "
        "Consider each member's age and goal. Suggest shared meals where possible "
        "with minor modifications for different needs."
    )
    try:
        model  = get_model()
        prompt = build_prompt(prompt_msg, [], None)
        result = model.generate_text(prompt=prompt)
        reply  = result.strip() if isinstance(result, str) else result
        return jsonify({"plan": reply})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/analyze", methods=["POST"])
def analyze_food():
    """Analyse calories & nutrition of a described meal."""
    data = request.get_json(force=True)
    meal = data.get("meal", "").strip()
    if not meal:
        return jsonify({"error": "No meal description provided"}), 400

    prompt_msg = (
        f"Analyse the nutritional content of: '{meal}'. "
        "Provide: total calories, protein (g), carbohydrates (g), fat (g), "
        "fibre (g), key vitamins/minerals, and a brief health rating (1–10). "
        "Format as a structured breakdown."
    )
    try:
        model  = get_model()
        prompt = build_prompt(prompt_msg, [], None)
        result = model.generate_text(prompt=prompt)
        reply  = result.strip() if isinstance(result, str) else result
        return jsonify({"analysis": reply})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "NutriBot Nutrition Agent"})


# ────────────────────────────────────────────────────────────────────────────
# Vercel handler export (required for serverless deployment)
# ────────────────────────────────────────────────────────────────────────────
# The 'app' variable is automatically detected by Vercel's Python runtime
