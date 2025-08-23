# app.py — Webhook asynchrone + health + logs + dédup


def _process_incoming(sender: str, incoming_msg: str, msg_sid: str | None):
"""Traite un message entrant en tâche de fond (GPT + envoi Twilio)."""
try:
print(f"[IN] sid={msg_sid} from={sender} body={incoming_msg[:140]}", flush=True)
# 1) Persister le message entrant (avec dédup via provider_sid)
try:
add_message_ext(sender, role="user", content=incoming_msg, direction="in", provider_sid=msg_sid)
except Exception as e_db_in:
print(f"[ERR][DB-IN] {e_db_in}", flush=True)


# 2) Historique + GPT
hist = get_history(sender, limit=20)
messages = [{"role": "system", "content": system_message_content}] + hist + [{"role": "user", "content": incoming_msg}]
try:
assistant_reply = chat_gpt(messages)
except Exception as e_gpt:
print(f"[ERR][GPT] {e_gpt}", flush=True)
assistant_reply = "Désolé, je n'ai pas bien compris. Peux-tu reformuler ?"


# 3) Envoi WhatsApp + persistance
try:
msg = twilio_client.messages.create(
from_=twilio_whatsapp,
body=assistant_reply,
to=sender
)
print(f"[OUT] sid={msg.sid} to={sender}", flush=True)
try:
add_message_ext(sender, role="assistant", content=assistant_reply, direction="out", provider_sid=msg.sid)
except Exception as e_db_out:
print(f"[ERR][DB-OUT] {e_db_out}", flush=True)
except Exception as e_tw:
print(f"[ERR][TWILIO-SEND] {e_tw}", flush=True)


except Exception as e:
print(f"[ERR][WORKER] {e}", flush=True)




# ====== Routes ======


@app.route("/webhook", methods=["POST"]) # Twilio → nous
def receive_message():
sender = request.form.get("From") # ex 'whatsapp:+33...'
incoming_msg = (request.form.get("Body") or "").strip()
msg_sid = request.form.get("MessageSid") # utile pour dédup


if not sender or not incoming_msg:
return ("", 200)


# Réponse immédiate (évite le timeout Twilio)
executor.submit(_process_incoming, sender, incoming_msg, msg_sid)
return ("", 200)




@app.route("/health", methods=["GET"]) # pour UptimeRobot
def health():
ok_db = ping_db()
return jsonify({"ok": True, "db": ok_db}), 200




@app.route("/", methods=["GET"]) # simple wake
def root():
return "Lanai OK", 200




if __name__ == "__main__":
app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
