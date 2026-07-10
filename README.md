# NutriBot — AI Nutrition Agent

> An AI-powered nutrition web application built with **Python Flask** and **IBM Watsonx.ai (Granite models)**. Features a full chat UI, BMI/TDEE calculators, meal planner, food analyzer, and family profile support — all in a clean black-and-white responsive design.

---

## Features

| Feature | Description |
|---|---|
| 🤖 **AI Chat** | Conversational nutrition advice via IBM Granite LLM |
| 🥗 **Meal Planner** | Generate personalised 1–7 day Indian meal plans |
| 🔍 **Food Analyzer** | Instant calorie & macro breakdown for any meal |
| 👨‍👩‍👧 **Family Profiles** | Multi-member family diet planning |
| 📊 **BMI Calculator** | BMI with visual gauge and advice |
| ⚡ **TDEE Calculator** | Daily energy needs (Mifflin-St Jeor formula) |
| 🌙 **Dark Mode** | Toggle between light and dark monochromatic themes |
| 📱 **Mobile Ready** | Fully responsive Bootstrap 5 layout |

---

## Project Structure

```
nutrition-agent/
├── app.py                  ← Flask backend + AGENT_INSTRUCTIONS
├── requirements.txt
├── .env.example            ← Copy to .env and fill credentials
├── .env                    ← Your secrets (never commit this)
├── templates/
│   └── index.html          ← Full frontend (chat, dashboard, tools)
└── README.md
```

---

## Quick Start

### 1 — Prerequisites

- Python 3.10+
- An [IBM Cloud account](https://cloud.ibm.com/registration)
- A [Watsonx.ai project](https://dataplatform.cloud.ibm.com/)

### 2 — Clone / download the project

```bash
cd nutrition-agent
```

### 3 — Create and activate a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

### 4 — Install dependencies

```bash
pip install -r requirements.txt
```

### 5 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

```
IBM_API_KEY=<your IBM Cloud API key>
IBM_PROJECT_ID=<your Watsonx.ai project ID>
IBM_URL=https://us-south.ml.cloud.ibm.com
FLASK_SECRET_KEY=<any random secure string>
```

**Getting your IBM credentials:**

1. Log in to [IBM Cloud](https://cloud.ibm.com)
2. Go to **Manage → Access (IAM) → API keys** → Create an API key
3. Open [Watsonx.ai](https://dataplatform.cloud.ibm.com/) → Create a project
4. Copy the **Project ID** from the project settings page

### 6 — Run the development server

```bash
python app.py
```

Open your browser at **http://localhost:5000**

---

## Customising Agent Behaviour

All agent customisation lives in the `AGENT_INSTRUCTIONS` dictionary near the top of [`app.py`](app.py). No other code changes needed.

```python
AGENT_INSTRUCTIONS = {
    "persona":         "...",   # Tone, name, personality
    "specialization":  "...",   # Diet expertise areas
    "indian_food":     "...",   # Indian cuisine preferences
    "safety_rules":    "...",   # Medical safety guardrails (keep these!)
    "format":          "...",   # Response structure rules
    "custom":          "...",   # Your own additional rules
}
```

**Examples of quick customisations:**

- Change the agent's name: edit `"NutriBot"` in `persona`
- Add keto diet specialisation: append to `specialization`
- Enforce Bengali cuisine: add to `indian_food`
- Require every response in Hindi: add `"Always respond in Hindi."` to `custom`

---

## Production Deployment

### Option A — Gunicorn (Linux/macOS server)

```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Option B — Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
```

```bash
docker build -t nutribot .
docker run -p 5000:5000 --env-file .env nutribot
```

### Option C — IBM Code Engine / Cloud Foundry

1. Push your code to a Git repository
2. In IBM Cloud, create a **Code Engine** project
3. Deploy as a container or from source, providing the `.env` variables as **secrets**

---

## API Reference

| Method | Endpoint | Body | Description |
|---|---|---|---|
| POST | `/api/chat` | `{message, history, profile}` | Main chat endpoint |
| POST | `/api/bmi` | `{weight, height}` | BMI calculation |
| POST | `/api/tdee` | `{weight, height, age, gender, activity}` | TDEE calculation |
| POST | `/api/meal-plan` | `{calories, days, diet, profile}` | Generate meal plan |
| POST | `/api/family-plan` | `{members: [{name, age, goal}]}` | Family plan |
| POST | `/api/analyze` | `{meal}` | Nutritional analysis |
| GET  | `/health` | — | Health check |

---

## Security Notes

- `.env` is in `.gitignore` — never commit it
- `IBM_API_KEY` is only read server-side; it is never sent to the browser
- The Flask secret key should be a long random string in production
- Watsonx.ai calls happen exclusively on the backend

---

## Disclaimer

NutriBot provides general nutrition information for educational purposes only. Always consult a registered dietitian or medical professional before making significant dietary changes.

---

*Built with ❤️ using IBM Watsonx.ai Granite & Python Flask*
