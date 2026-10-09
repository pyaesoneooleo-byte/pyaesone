import os
import sys
import re
import asyncio
import subprocess
import srt
import uuid
import zipfile
import shutil
from pydub import AudioSegment
from google import genai
import edge_tts
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from flask_cors import CORS

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
OUTPUT_FOLDER = os.path.join(os.getcwd(), "outputs")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def sanitize_text(text):
    if not text:
        return ""
    return re.sub(r'[\u200e\u200f\u200b\u202a-\u202e\s]', '', str(text)).strip()

# ==========================================
# UI HTML TEMPLATE (Updated Options in Magic Merge)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="my">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Video Studio Pro</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    .tab-active { border-bottom: 2px solid #a855f7; color: #a855f7; font-weight: bold; }
    .tab-inactive { color: #94a3b8; }
    .tab-inactive:hover { color: #cbd5e1; }
  </style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center p-4">

  <div class="max-w-2xl w-full bg-slate-800 border border-slate-700 rounded-2xl p-6 shadow-2xl space-y-6">
    <div class="text-center space-y-2">
      <h1 class="text-2xl font-bold text-white"><i class="fa-solid fa-photo-film text-purple-500 mr-2"></i>AI Video Studio Pro</h1>
      <p class="text-xs text-slate-400">All-in-one Video Processing & Dubbing Tool</p>
    </div>

    <!-- Tabs Navigation -->
    <div class="flex flex-wrap gap-4 border-b border-slate-700 text-sm">
      <button onclick="switchTab('autodub')" id="tab-btn-autodub" class="pb-2 tab-active"><i class="fa-solid fa-microphone mr-1"></i> Auto Dub</button>
      <button onclick="switchTab('splitter')" id="tab-btn-splitter" class="pb-2 tab-inactive"><i class="fa-solid fa-scissors mr-1"></i> Splitter</button>
      <button onclick="switchTab('srtdub')" id="tab-btn-srtdub" class="pb-2 tab-inactive"><i class="fa-solid fa-closed-captioning mr-1"></i> Strict SRT Dub</button>
      <button onclick="switchTab('srtfile')" id="tab-btn-srtfile" class="pb-2 tab-inactive"><i class="fa-solid fa-file-import mr-1"></i> SRT File Merge</button>
      <button onclick="switchTab('magic')" id="tab-btn-magic" class="pb-2 tab-inactive"><i class="fa-solid fa-wand-magic-sparkles mr-1"></i> Magic Merge</button>
    </div>

    <!-- 1. Auto Dub Tab -->
    <div id="tab-autodub" class="tab-content space-y-5">
      <form id="autodubForm" class="space-y-5" onsubmit="submitForm(event, 'autodubForm', '/api/dub')">
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">Google Gemini API Key</label>
          <input type="password" name="apiKey" required placeholder="AIzaSy..." class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white focus:border-purple-500">
        </div>
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">Video File (.mp4, .mkv)</label>
          <input type="file" name="video" accept="video/*" required class="w-full text-xs bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2">
        </div>
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">AI Voice</label>
          <select name="voice" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white">
            <option value="my-MM-NilarNeural">မြန်မာ AI မိန်းကလေးအသံ (Nilar)</option>
            <option value="my-MM-ThihaNeural">မြန်မာ AI ယောကျာ်းလေးအသံ (Thiha)</option>
          </select>
        </div>
        <div class="bg-slate-900 p-3 rounded-xl border border-slate-700 space-y-2 text-xs text-slate-300 font-semibold">
          <label class="flex items-center gap-2 cursor-pointer"><input type="checkbox" name="multiVoice" value="true" checked class="accent-purple-500 w-4 h-4"><span>👥 ဇာတ်ကောင်အလိုက် အသံခွဲမည်</span></label>
          <label class="flex items-center gap-2 cursor-pointer"><input type="checkbox" name="keepBgm" value="true" checked class="accent-pink-500 w-4 h-4"><span>🎵 မူရင်း နောက်ခံတေးဂီတ ချန်ထားမည်</span></label>
        </div>
        <button type="submit" class="submit-btn w-full bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 text-white text-xs font-bold py-3 rounded-xl shadow-lg transition">🚀 စတင်ရန်</button>
      </form>
    </div>

    <!-- 2. Video Splitter Tab -->
    <div id="tab-splitter" class="tab-content hidden space-y-5">
      <form id="splitterForm" class="space-y-5" onsubmit="submitForm(event, 'splitterForm', '/api/split')">
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">Video File (.mp4)</label>
          <input type="file" name="video" accept="video/*" required class="w-full text-xs bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2">
        </div>
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">ခွဲလိုသော အချိန်အပိုင်းအခြား</label>
          <select name="duration" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white">
            <option value="5">၅ မိနစ်စီ</option>
            <option value="10">၁၀ မိနစ်စီ</option>
            <option value="15">၁၅ မိနစ်စီ</option>
          </select>
        </div>
        <button type="submit" class="submit-btn w-full bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold py-3 rounded-xl shadow-lg transition">✂️ ဗီဒီယို ဖြတ်တောက်ရန်</button>
      </form>
    </div>

    <!-- 3. Strict SRT Dub Tab -->
    <div id="tab-srtdub" class="tab-content hidden space-y-5">
      <form id="srtdubForm" class="space-y-5" onsubmit="submitForm(event, 'srtdubForm', '/api/srt_strict')">
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">Google Gemini API Key</label>
          <input type="password" name="apiKey" required class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white focus:border-emerald-500">
        </div>
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">Video File</label>
          <input type="file" name="video" accept="video/*" required class="w-full text-xs bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2">
        </div>
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">AI Voice</label>
          <select name="voice" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white">
            <option value="my-MM-NilarNeural">မြန်မာ AI မိန်းကလေးအသံ (Nilar)</option>
            <option value="my-MM-ThihaNeural">မြန်မာ AI ယောကျာ်းလေးအသံ (Thiha)</option>
          </select>
        </div>
        <button type="submit" class="submit-btn w-full bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold py-3 rounded-xl shadow-lg transition">🎯 တိကျစွာ ဘာသာပြန် & အသံသွင်းရန်</button>
      </form>
    </div>

    <!-- 4. SRT File Merge (Strict) Tab -->
    <div id="tab-srtfile" class="tab-content hidden space-y-5">
      <form id="srtfileForm" class="space-y-5" onsubmit="submitForm(event, 'srtfileForm', '/api/srt_file_dub')">
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">Google Gemini API Key</label>
          <input type="password" name="apiKey" required class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white focus:border-teal-500">
        </div>
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">Video File</label>
          <input type="file" name="video" accept="video/*" required class="w-full text-xs bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2">
        </div>
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">Burmese SRT File</label>
          <input type="file" name="srt_file" accept=".srt" required class="w-full text-xs bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2">
        </div>
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">AI Voice</label>
          <select name="voice" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white">
            <option value="my-MM-NilarNeural">မြန်မာ AI မိန်းကလေးအသံ (Nilar)</option>
            <option value="my-MM-ThihaNeural">မြန်မာ AI ယောကျာ်းလေးအသံ (Thiha)</option>
          </select>
        </div>
        <button type="submit" class="submit-btn w-full bg-teal-600 hover:bg-teal-500 text-white text-xs font-bold py-3 rounded-xl shadow-lg transition">🎙️ အချိန်ကိုက် မြန်မာသံထည့်ရန်</button>
      </form>
    </div>

    <!-- 5. Magic Merge (Copyright Bypass) Tab - UPDATED -->
    <div id="tab-magic" class="tab-content hidden space-y-5">
      <div class="bg-orange-500/10 border border-orange-500/20 p-3 rounded-xl text-xs text-orange-300">
        <i class="fa-solid fa-mask mr-1"></i> ဖြတ်ထားသော ဗီဒီယိုများကို အောက်ပါ Option များ ရွေးချယ်၍ ပြန်လည်ဆက်ပေးပါမည်။
      </div>
      <form id="magicForm" class="space-y-5" onsubmit="submitForm(event, 'magicForm', '/api/magic_merge')">
        <div class="space-y-1.5">
          <label class="block text-xs font-semibold text-slate-300">ဗီဒီယို အပိုင်းများ (Multiple Select လုပ်ပါ)</label>
          <input type="file" name="videos" accept="video/*" multiple required class="w-full text-xs bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2">
        </div>

        <div class="bg-slate-900 p-3 rounded-xl border border-slate-700 space-y-2 text-xs text-slate-300 font-semibold">
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" name="useMirror" value="true" class="accent-orange-500 w-4 h-4">
            <span>🪞 Mirror လုပ်မည် (ဘယ်ညာပြောင်းရန်)</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" name="useColor" value="true" class="accent-orange-500 w-4 h-4">
            <span>🎨 Color Change လုပ်မည် (အရောင် ၃ မျိုး အလှည့်ကျပြောင်းရန်)</span>
          </label>
        </div>

        <button type="submit" class="submit-btn w-full bg-orange-600 hover:bg-orange-500 text-white text-xs font-bold py-3 rounded-xl shadow-lg transition">🎭 Copyright Bypass ဖြင့် ပေါင်းရန်</button>
      </form>
    </div>

    <!-- Status Box -->
    <div id="statusBox" class="hidden p-4 bg-slate-900/90 rounded-xl border border-slate-700 text-center space-y-2 mt-4">
      <i class="fa-solid fa-circle-notch fa-spin text-2xl text-purple-500 mb-2"></i>
      <p id="statusText" class="text-xs font-semibold text-slate-300">Processing... ကျေးဇူးပြု၍ ခေတ္တစောင့်ဆိုင်းပါ။</p>
    </div>

  </div>

  <script>
    function switchTab(tabId) {
      document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
      document.getElementById('tab-' + tabId).classList.remove('hidden');
      
      document.querySelectorAll('button[id^="tab-btn-"]').forEach(btn => {
        btn.classList.remove('tab-active');
        btn.classList.add('tab-inactive');
      });
      document.getElementById('tab-btn-' + tabId).classList.remove('tab-inactive');
      document.getElementById('tab-btn-' + tabId).classList.add('tab-active');
    }

    function submitForm(e, formId, endpoint) {
      e.preventDefault();
      const form = document.getElementById(formId);
      const submitBtn = form.querySelector('.submit-btn');
      const statusBox = document.getElementById('statusBox');
      const statusText = document.getElementById('statusText');

      submitBtn.disabled = true;
      submitBtn.classList.add('opacity-50');
      statusBox.classList.remove('hidden');
      statusText.innerText = "ဖိုင်များ Upload တင်နေပြီး လုပ်ဆောင်နေပါသည်... (ခေတ္တစောင့်ပါ)";

      const formData = new FormData(form);

      fetch(endpoint, {
        method: 'POST',
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          statusText.innerHTML = "✅ အောင်မြင်စွာ ပြီးဆုံးပါပြီ! ဒေါင်းလုဒ်စတင်နေပါပြီ...";
          window.location.href = data.downloadUrl;
        } else {
          alert('Error: ' + data.message);
          statusBox.classList.add('hidden');
        }
      })
      .catch(error => {
        alert('Server Error ဖြစ်ပေါ်ခဲ့ပါသည်။');
        statusBox.classList.add('hidden');
      })
      .finally(() => {
        submitBtn.disabled = false;
        submitBtn.classList.remove('opacity-50');
      });
    }
  </script>
</body>
</html>
"""

# ==========================================
# Helper Functions
# ==========================================
def extract_audio_from_video(video_path, audio_output_path):
    cmd = ['ffmpeg', '-y', '-i', video_path, '-vn', '-ac', '1', '-ar', '16000', '-ab', '64k', audio_output_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def generate_srt_with_gemini_audio(client, audio_path, multi_voice=False, strict_mode=False):
    uploaded_audio = client.files.upload(file=audio_path)
    if strict_mode:
        prompt = """
        Listen to the audio track.
        1. Extract the exact start and end timestamps of every dialogue. DO NOT alter the timestamps by even a millisecond.
        2. Translate the dialogue to Burmese (Myanmar).
        3. CRITICAL CONSTRAINT: You must SUMMARIZE the translation. The Burmese text must be extremely concise so the Text-to-Speech can read it naturally within the exact timestamp duration. Avoid word-for-word translation if it causes long sentences. Keep the core meaning but shorten the phrasing aggressively.
        4. Output STRICTLY in standard SRT format ONLY.
        """
    else:
        prompt = """
        Listen to the audio track of this video carefully.
        1. Transcribe all spoken dialogues (Chinese or English) with precise start and end timestamps.
        2. Translate each dialogue directly into natural, natural-sounding spoken Myanmar (Burmese).
        3. STRICTION ON LENGTH: Ensure the Burmese translation is concise enough to fit comfortably within the timestamp duration.
        4. Output STRICTLY in standard SRT format ONLY.
        """
        if multi_voice:
            prompt += "\n5. MULTI-SPEAKER TAG: Identify speaker gender. Prefix Burmese translation with [M] for male, or [F] for female.\n"

    try:
        response = client.models.generate_content(model="gemini-3.8-flash", contents=[uploaded_audio, prompt])
        try: client.files.delete(name=uploaded_audio.name)
        except: pass
        raw_text = re.sub(r'[\u200e\u200f\u200b\u202a-\u202e]', '', str(response.text)).strip()
        return re.sub(r'```(?:srt)?\n?', '', raw_text).strip('` \n')
    except Exception as e:
        print("Gemini Error:", e)
        raise e

def summarize_srt_text_with_gemini(client, srt_content):
    prompt = """
    You are an expert audio script editor.
    I will provide you with a Burmese SRT file. Your task is to shorten the text of each subtitle so that it can be spoken naturally within its timestamp duration.
    Rules:
    1. DO NOT change any timestamps. Keep them EXACTLY as provided down to the millisecond.
    2. Summarize the Burmese text to be concise. Keep the core meaning but shorten the phrasing aggressively so it doesn't sound unnaturally fast when synthesized by Text-to-Speech.
    3. Output ONLY the strictly formatted SRT content. Do not include any explanations or markdown.
    
    SRT Content:
    """ + srt_content
    try:
        response = client.models.generate_content(model="gemini-3.8-flash", contents=[prompt])
        raw_text = re.sub(r'[\u200e\u200f\u200b\u202a-\u202e]', '', str(response.text)).strip()
        return re.sub(r'```(?:srt)?\n?', '', raw_text).strip('` \n')
    except Exception as e:
        print("Gemini SRT Summary Error:", e)
        raise e

async def generate_tts_async(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def adjust_audio_speed_ffmpeg(input_file, output_file, speed_factor):
    safe_speed = max(0.85, min(1.25, speed_factor))
    cmd = ['ffmpeg', '-y', '-i', input_file, '-filter:a', f"atempo={safe_speed:.3f}", output_file]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ==========================================
# Application Routes
# ==========================================

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

# ---------- Route 1: Original Auto Dub ----------
@app.route('/api/dub', methods=['POST'])
def process_dubbing():
    try:
        api_key = sanitize_text(request.form.get('apiKey', ''))
        voice_default = request.form.get('voice', 'my-MM-NilarNeural')
        multi_voice = request.form.get('multiVoice') == 'true'
        keep_bgm = request.form.get('keepBgm') == 'true'
        video_file = request.files.get('video')

        if not api_key or not video_file: return jsonify({"success": False, "message": "Missing Data"}), 400

        unique_id = str(uuid.uuid4())[:8]
        _, ext = os.path.splitext(video_file.filename)
        video_path = os.path.join(UPLOAD_FOLDER, f"v_{unique_id}{ext}")
        video_file.save(video_path)

        output_filename = f"dubbed_{unique_id}.mp4"
        output_video_path = os.path.join(OUTPUT_FOLDER, output_filename)

        temp_extracted_audio = os.path.join(UPLOAD_FOLDER, f"aud_{unique_id}.mp3")
        extract_audio_from_video(video_path, temp_extracted_audio)

        client = genai.Client(api_key=api_key)
        srt_content = generate_srt_with_gemini_audio(client, temp_extracted_audio, multi_voice, strict_mode=False)
        if os.path.exists(temp_extracted_audio): os.remove(temp_extracted_audio)

        subtitles = list(srt.parse(srt_content))
        video_info = AudioSegment.from_file(video_path)
        final_audio = AudioSegment.silent(duration=len(video_info))

        for idx, sub in enumerate(subtitles):
            start_ms = int(sub.start.total_seconds() * 1000)
            end_ms = int(sub.end.total_seconds() * 1000)
            target_dur = (end_ms - start_ms) / 1000.0
            if target_dur <= 0.3: continue
            
            raw_text = re.sub(r'[\u200e\u200f\u200b\u202a-\u202e]', '', str(sub.content)).replace('\n', ' ').strip()
            current_voice = voice_default
            if multi_voice:
                if '[M]' in raw_text or '[m]' in raw_text: current_voice = 'my-MM-ThihaNeural'
                elif '[F]' in raw_text or '[f]' in raw_text: current_voice = 'my-MM-NilarNeural'
            
            clean_text = re.sub(r'\[[MmFf]\]\s*', '', raw_text).strip()
            if not clean_text: continue

            temp_tts = os.path.join(UPLOAD_FOLDER, f"t_{unique_id}_{idx}.mp3")
            temp_synced = os.path.join(UPLOAD_FOLDER, f"s_{unique_id}_{idx}.wav")

            asyncio.run(generate_tts_async(clean_text, current_voice, temp_tts))
            gen_audio = AudioSegment.from_file(temp_tts)
            speed_factor = (len(gen_audio) / 1000.0) / target_dur
            adjust_audio_speed_ffmpeg(temp_tts, temp_synced, speed_factor)

            synced_audio = AudioSegment.from_file(temp_synced)
            final_audio = final_audio.overlay(synced_audio, position=start_ms)
            os.remove(temp_tts)
            os.remove(temp_synced)

        final_audio_path = os.path.join(UPLOAD_FOLDER, f"f_{unique_id}.wav")
        final_audio.export(final_audio_path, format="wav")

        if keep_bgm:
            merge_cmd = ['ffmpeg', '-y', '-i', video_path, '-i', final_audio_path, '-filter_complex', '[0:a]volume=0.15[a0]; [1:a]volume=1.5[a1]; [a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]', '-map', '0:v:0', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', output_video_path]
        else:
            merge_cmd = ['ffmpeg', '-y', '-i', video_path, '-i', final_audio_path, '-c:v', 'copy', '-map', '0:v:0', '-map', '1:a:0', '-shortest', output_video_path]
            
        subprocess.run(merge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.remove(final_audio_path)

        return jsonify({"success": True, "downloadUrl": f"/download/{output_filename}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ---------- Route 2: Video Splitter ----------
@app.route('/api/split', methods=['POST'])
def process_split():
    try:
        video_file = request.files.get('video')
        duration_mins = int(request.form.get('duration', 5))
        if not video_file: return jsonify({"success": False, "message": "Video မပါဝင်ပါ။"}), 400
        unique_id = str(uuid.uuid4())[:8]
        _, ext = os.path.splitext(video_file.filename)
        video_path = os.path.join(UPLOAD_FOLDER, f"split_in_{unique_id}{ext}")
        video_file.save(video_path)
        
        split_dir = os.path.join(OUTPUT_FOLDER, f"split_{unique_id}")
        os.makedirs(split_dir, exist_ok=True)
        segment_time = duration_mins * 60
        output_pattern = os.path.join(split_dir, f"part_%03d{ext}")
        
        cmd = ['ffmpeg', '-y', '-i', video_path, '-c', 'copy', '-map', '0', '-segment_time', str(segment_time), '-f', 'segment', '-reset_timestamps', '1', output_pattern]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        zip_filename = f"splitted_video_{unique_id}.zip"
        zip_path = os.path.join(OUTPUT_FOLDER, zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for root, _, files in os.walk(split_dir):
                for file in files: zipf.write(os.path.join(root, file), file)
        shutil.rmtree(split_dir)
        os.remove(video_path)
        return jsonify({"success": True, "downloadUrl": f"/download/{zip_filename}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ---------- Route 3: Strict SRT Dubbing ----------
@app.route('/api/srt_strict', methods=['POST'])
def process_srt_strict():
    try:
        api_key = sanitize_text(request.form.get('apiKey', ''))
        voice = request.form.get('voice', 'my-MM-NilarNeural')
        video_file = request.files.get('video')
        if not api_key or not video_file: return jsonify({"success": False, "message": "Missing Data"}), 400

        unique_id = str(uuid.uuid4())[:8]
        _, ext = os.path.splitext(video_file.filename)
        video_path = os.path.join(UPLOAD_FOLDER, f"st_v_{unique_id}{ext}")
        video_file.save(video_path)
        output_filename = f"strict_dubbed_{unique_id}.mp4"
        output_video_path = os.path.join(OUTPUT_FOLDER, output_filename)

        temp_audio = os.path.join(UPLOAD_FOLDER, f"st_aud_{unique_id}.mp3")
        extract_audio_from_video(video_path, temp_audio)

        client = genai.Client(api_key=api_key)
        srt_content = generate_srt_with_gemini_audio(client, temp_audio, strict_mode=True)
        if os.path.exists(temp_audio): os.remove(temp_audio)

        subtitles = list(srt.parse(srt_content))
        video_info = AudioSegment.from_file(video_path)
        final_audio = AudioSegment.silent(duration=len(video_info))

        for idx, sub in enumerate(subtitles):
            start_ms = int(sub.start.total_seconds() * 1000)
            end_ms = int(sub.end.total_seconds() * 1000)
            target_dur = (end_ms - start_ms) / 1000.0
            if target_dur <= 0.3: continue
            
            clean_text = re.sub(r'[\u200e\u200f\u200b\u202a-\u202e]', '', str(sub.content)).replace('\n', ' ').strip()
            if not clean_text: continue

            temp_tts = os.path.join(UPLOAD_FOLDER, f"tt_{unique_id}_{idx}.mp3")
            temp_synced = os.path.join(UPLOAD_FOLDER, f"sy_{unique_id}_{idx}.wav")

            asyncio.run(generate_tts_async(clean_text, voice, temp_tts))
            gen_audio = AudioSegment.from_file(temp_tts)
            speed_factor = (len(gen_audio) / 1000.0) / target_dur
            adjust_audio_speed_ffmpeg(temp_tts, temp_synced, speed_factor)

            synced_audio = AudioSegment.from_file(temp_synced)
            final_audio = final_audio.overlay(synced_audio, position=start_ms)
            os.remove(temp_tts)
            os.remove(temp_synced)

        final_audio_path = os.path.join(UPLOAD_FOLDER, f"st_f_{unique_id}.wav")
        final_audio.export(final_audio_path, format="wav")
        merge_cmd = ['ffmpeg', '-y', '-i', video_path, '-i', final_audio_path, '-c:v', 'copy', '-map', '0:v:0', '-map', '1:a:0', '-shortest', output_video_path]
        subprocess.run(merge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.remove(final_audio_path)
        return jsonify({"success": True, "downloadUrl": f"/download/{output_filename}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ---------- Route 4: SRT File Dubbing (Strict) ----------
@app.route('/api/srt_file_dub', methods=['POST'])
def process_srt_file_dub():
    try:
        api_key = sanitize_text(request.form.get('apiKey', ''))
        voice = request.form.get('voice', 'my-MM-NilarNeural')
        video_file = request.files.get('video')
        srt_file = request.files.get('srt_file')
        if not api_key or not video_file or not srt_file: return jsonify({"success": False, "message": "အချက်အလက်များ မစုံလင်ပါ။"}), 400

        unique_id = str(uuid.uuid4())[:8]
        _, ext = os.path.splitext(video_file.filename)
        video_path = os.path.join(UPLOAD_FOLDER, f"srtf_v_{unique_id}{ext}")
        video_file.save(video_path)

        srt_content_raw = srt_file.read().decode('utf-8-sig')
        client = genai.Client(api_key=api_key)
        summarized_srt_content = summarize_srt_text_with_gemini(client, srt_content_raw)

        subtitles = list(srt.parse(summarized_srt_content))
        video_info = AudioSegment.from_file(video_path)
        final_audio = AudioSegment.silent(duration=len(video_info))

        for idx, sub in enumerate(subtitles):
            start_ms = int(sub.start.total_seconds() * 1000)
            end_ms = int(sub.end.total_seconds() * 1000)
            target_dur = (end_ms - start_ms) / 1000.0
            if target_dur <= 0.3: continue
            
            clean_text = re.sub(r'[\u200e\u200f\u200b\u202a-\u202e]', '', str(sub.content)).replace('\n', ' ').strip()
            if not clean_text: continue

            temp_tts = os.path.join(UPLOAD_FOLDER, f"srt_t_{unique_id}_{idx}.mp3")
            temp_synced = os.path.join(UPLOAD_FOLDER, f"srt_s_{unique_id}_{idx}.wav")

            asyncio.run(generate_tts_async(clean_text, voice, temp_tts))
            gen_audio = AudioSegment.from_file(temp_tts)
            speed_factor = (len(gen_audio) / 1000.0) / target_dur
            adjust_audio_speed_ffmpeg(temp_tts, temp_synced, speed_factor)

            synced_audio = AudioSegment.from_file(temp_synced)
            final_audio = final_audio.overlay(synced_audio, position=start_ms)
            if os.path.exists(temp_tts): os.remove(temp_tts)
            if os.path.exists(temp_synced): os.remove(temp_synced)

        final_audio_path = os.path.join(UPLOAD_FOLDER, f"srt_f_{unique_id}.wav")
        final_audio.export(final_audio_path, format="wav")

        output_filename = f"srtfile_dubbed_{unique_id}.mp4"
        output_video_path = os.path.join(OUTPUT_FOLDER, output_filename)
        merge_cmd = ['ffmpeg', '-y', '-i', video_path, '-i', final_audio_path, '-c:v', 'copy', '-map', '0:v:0', '-map', '1:a:0', '-shortest', output_video_path]
        subprocess.run(merge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.remove(final_audio_path)
        return jsonify({"success": True, "downloadUrl": f"/download/{output_filename}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ---------- Route 5: Magic Merge (UPDATED for Optional Checkboxes) ----------
@app.route('/api/magic_merge', methods=['POST'])
def process_magic_merge():
    try:
        videos = request.files.getlist('videos')
        use_mirror = request.form.get('useMirror') == 'true'
        use_color = request.form.get('useColor') == 'true'

        if not videos or len(videos) == 0:
            return jsonify({"success": False, "message": "ဗီဒီယိုများ ရွေးချယ်ထားခြင်း မရှိပါ။"}), 400

        unique_id = str(uuid.uuid4())[:8]
        process_dir = os.path.join(UPLOAD_FOLDER, f"magic_{unique_id}")
        os.makedirs(process_dir, exist_ok=True)
        
        color_filters = [
            "eq=contrast=1.05:brightness=0.02:saturation=1.1",
            "eq=contrast=1.1:brightness=-0.02:saturation=1.2",
            "eq=contrast=1.08:brightness=0.01:saturation=1.05"
        ]
        
        processed_files = []
        for i, video_file in enumerate(videos):
            if video_file.filename == '': continue
            _, ext = os.path.splitext(video_file.filename)
            input_path = os.path.join(process_dir, f"in_{i}{ext}")
            video_file.save(input_path)
            
            output_part_path = os.path.join(process_dir, f"out_{i}.mp4")
            
            # Checkbox အပေါ်မူတည်ပြီး Filters သတ်မှတ်ခြင်း
            filters = []
            if use_mirror:
                filters.append("hflip")
            if use_color:
                filters.append(color_filters[i % 3])
                
            filter_str = ",".join(filters)
            
            if filter_str:
                cmd = ['ffmpeg', '-y', '-i', input_path, '-vf', filter_str, '-c:v', 'libx264', '-crf', '23', '-preset', 'veryfast', '-c:a', 'copy', output_part_path]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processed_files.append(f"file '{output_part_path}'")
            else:
                # ဘာ Option မှ မရွေးထားရင် Input အတိုင်း တိုက်ရိုက် ပေါင်းမည်
                processed_files.append(f"file '{input_path}'")
        
        if not processed_files: return jsonify({"success": False, "message": "Video ဖိုင်များ မှားယွင်းနေသည်။"}), 400

        list_file_path = os.path.join(process_dir, "concat_list.txt")
        with open(list_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(processed_files))
            
        final_merged_name = f"magic_merged_{unique_id}.mp4"
        final_merged_path = os.path.join(OUTPUT_FOLDER, final_merged_name)
        
        concat_cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_file_path, '-c', 'copy', final_merged_path]
        subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        try: shutil.rmtree(process_dir)
        except: pass

        return jsonify({"success": True, "downloadUrl": f"/download/{final_merged_name}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
