import os
import re
import time
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify

app = Flask(__name__)

FH_EMAIL = os.environ.get("FH_EMAIL")
FH_PASSWORD = os.environ.get("FH_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_ADMIN_CHAT_ID = os.environ.get("TG_ADMIN_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

class FapHouseExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def notify_admin(self, message):
        if TG_BOT_TOKEN and TG_ADMIN_CHAT_ID:
            tg_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            try:
                requests.post(tg_url, json={"chat_id": TG_ADMIN_CHAT_ID, "text": message})
            except Exception:
                pass

    def login(self):
        if not FH_EMAIL or not FH_PASSWORD:
            return False
            
        login_url = "https://faphouse2.com/api/auth/signin"
        payload = {
            "login": FH_EMAIL,
            "password": FH_PASSWORD,
            "rememberMe": "1",
            "recaptcha": ""
        }
        
        try:
            resp = self.session.post(login_url, json=payload, timeout=15)
            if resp.status_code == 200 and "userId" in resp.text:
                self.notify_admin("⚠️ *Bot Alert:* Successfully logged into Faphouse to refresh cookies and extract premium video data.")
                return True
        except Exception as e:
            print(f"Login exception: {e}")
        return False

    def extract_video_data(self, url):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, timeout=15)
                soup = BeautifulSoup(resp.text, "html.parser")
                player = soup.select_one(".video__player[data-el='VideoPlayer']")

                if player:
                    access_type = player.get("data-el-video-access-type", "")
                    
                    if str(access_type).lower() != "premium":
                        return {"error": "Ultra Video not Supported.", "access_type": access_type}

                    title = player.get("data-el-video-title")
                    cover = player.get("data-el-cover")
                    duration_sec = int(player.get("data-el-duration", 0))
                    
                    mins, secs = divmod(duration_sec, 60)
                    duration_str = f"{mins:02d}:{secs:02d}"

                    hls_master = player.get("data-el-hls-url")
                    
                    mp4_formats = {}
                    raw_formats = player.get("data-el-formats")
                    if raw_formats:
                        try:
                            mp4_formats = json.loads(raw_formats)
                        except json.JSONDecodeError:
                            pass
                            
                    quality = f"{max([int(k) for k in mp4_formats.keys() if k.isdigit()], default=1080)}p" if mp4_formats else "HD"

                    return {
                        "title": title,
                        "thumbnail_url": cover,
                        "duration": duration_str,
                        "quality": quality,
                        "access_type": access_type,
                        "hls_master_url": hls_master,
                        "streams": mp4_formats
                    }
                
                # If player not found, data might be gated. Attempt login.
                if attempt < max_retries - 1:
                    time.sleep(1)
                    self.login()
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    return {"error": f"Extraction failed: {str(e)}"}
                time.sleep(1)

        return {"error": "Video player not found. Video may be deleted or requires active subscription."}

extractor = FapHouseExtractor()

@app.route('/api/extract', methods=['GET'])
def extract_api():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    if not re.search(r'faphouse\.com|faphouse2\.com', url):
        return jsonify({"error": "Invalid domain. Only faphouse.com or faphouse2.com allowed."}), 400

    data = extractor.extract_video_data(url)
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
