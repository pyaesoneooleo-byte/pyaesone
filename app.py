import os
import sys
import re
import asyncio
import subprocess
import srt
import uuid
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
    # မမြင်ရသော Unicode စာလုံးများကို ဖြတ်ထုတ်ပေးမည့်အပိုင်း
    return re.sub(r'[\u200e\u200f\u200b\u202a-\u202e\s]', '', str(text)).strip()

# ==========================================
# UI HTML TEMPLATE
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="my">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Auto Video Dubber</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center p-4">

  <div class="max-w-xl w-full bg-slate-800 border border-slate-700 rounded-2xl p-6 shadow-2xl space-y-6">
    <div class="text-center space-y-2">
      <div class="inline-flex items-center gap-2 bg-purple-500/10 text-purple-400 px-3 py-1 rounded-full text-xs font-semibold border border-purple-500/20">
        ✨ Direct Video Speech-to-Dub Engine
      </div>
      <h1 class="text-2xl font-bold text-white">AI Direct Video Dubber</h1>
      <p class="text-xs text-slate-400">SRT မလိုပါ။ Video တင်ရုံဖြင့် Chinese/English အသံကို မြန်မာလို အလိုအလျောက် Dubbing လုပ်ပေးမည်။</p>
    </div>

    <form id="dubbingForm" class="space-y-5">
      <div class="space-y-1.5">
        <label class="block text-xs font-semibold text-slate-300">
          <i class="fa-solid fa-key text-purple-400 mr-1"></i> Google Gemini API Key
        </label>
        <input type="password" id="apiKey" required placeholder="AIzaSy..." 
          class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500">
      </div>

      <div class="space-y-1.5">
        <label class="block text-xs font-semibold text-slate-300">
          <i class="fa-solid fa-video text-blue-400 mr-1"></i> Video File (.mp4, .mkv)
        </label>
        <div class="border-2 border-dashed border-slate-700 hover:border-blue-500/50 bg-slate-900/50 rounded-xl p-4 text-center cursor-pointer relative">
          <input type="file" id="videoFile" accept="video/*" required onchange="updateName(this, 'videoName')" class="absolute inset-0 opacity-0 cursor-pointer w-full h-full">
          <i class="fa-solid fa-cloud-arrow-up text-2xl text-slate-400 mb-1"></i>
          <p id="videoName" class="text-xs text-slate-300">Video ဖိုင်ကို ရွေးပါ သို့မဟုတ် Drag ဆွဲထည့်ပါ</p>
        </div>
      </div>

      <div class="space-y-1.5">
        <label class="block text-xs font-semibold text-slate-300">
          <i class="fa-solid fa-microphone text-pink-400 mr-1"></i> AI Voice ရွေးရန်
        </label>
        <select id="voiceType" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white">
          <option value="my-MM-NilarNeural">မြန်မာ AI မိန်းကလေးအသံ (Nilar)</option>
          <option value="my-MM-ThihaNeural">မြန်မာ AI ယောကျာ်းလေးအသံ (Thiha)</option>
        </select>
      </div>

      <button type="submit" id="submitBtn" class="w-full bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-bold py-3 rounded-xl shadow-lg transition">
        🚀 Auto Dubbing စတင်ရန်
      </button>
    </form>

    <div id="statusBox" class="hidden p-4 bg-slate-900/90 rounded-xl border border-slate-700 space-y-3">
      <div id="uploadSection" class="space-y-1.5">
        <div class="flex justify-between items-center text-xs text-slate-300 font-semibold">
          <span id="uploadLabel"><i class="fa-solid fa-spinner fa-spin text-blue-400 mr-1"></i> Video Upload တင်နေသည်...</span>
          <span id="uploadPercent" class="text-blue-400 font-bold">0%</span>
        </div>
        <div class="w-full bg-slate-800 h-2.5 rounded-full overflow-hidden border border-slate-700">
          <div id="uploadProgressBar" class="bg-gradient-to-r from-blue-500 to-cyan-400 h-full w-0 transition-all duration-150"></div>
        </div>
      </div>

      <div id="renderSection" class="hidden pt-2 border-t border-slate-800 space-y-1">
        <div class="flex items-center gap-2 text-xs text-purple-400 font-semibold">
          <i class="fa-solid fa-wand-magic-sparkles fa-spin"></i>
          <span id="renderStatusText">Gemini က မူရင်းအသံကို နားထောင်၍ Timestamp နှင့် ဘာသာပြန်ယူနေပါသည်...</span>
        </div>
        <p class="text-[10px] text-slate-500">Video အတို/အရှည်ပေါ် မူတည်၍ ခဏ ကြာမြင့်နိုင်ပါသည်။</p>
      </div>
    </div>
  </div>

  <script>
    function updateName(input, id) {
      if(input.files && input.files[0]) {
        document.getElementById(id).innerText = "📄 " + input.files[0].name;
      }
    }

    document.getElementById('dubbingForm').addEventListener('submit', function(e) {
      e.preventDefault();

      const btn = document.getElementById('submitBtn');
      const statusBox = document.getElementById('statusBox');
      const uploadSection = document.getElementById('uploadSection');
      const renderSection = document.getElementById('renderSection');
      const uploadProgressBar = document.getElementById('uploadProgressBar');
      const uploadPercent = document.getElementById('uploadPercent');

      btn.disabled = true;
      btn.classList.add('opacity-50');
      statusBox.classList.remove('hidden');
      renderSection.classList.add('hidden');
      uploadProgressBar.style.width = '0%';
      uploadPercent.innerText = '0%';

      const formData = new FormData();
      formData.append('apiKey', document.getElementById('apiKey').value);
      formData.append('video', document.getElementById('videoFile').files[0]);
      formData.append('voice', document.getElementById('voiceType').value);

      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener('progress', function(e) {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          uploadProgressBar.style.width = percent + '%';
          uploadPercent.innerText = percent + '%';

          if (percent === 100) {
            document.getElementById('uploadLabel').innerHTML = '<i class="fa-solid fa-check text-emerald-400 mr-1"></i> File Upload ပြီးစီးပါပြီ';
            renderSection.classList.remove('hidden');
          }
        }
      });

      xhr.onload = function() {
        if (xhr.status === 200) {
          const data = JSON.parse(xhr.responseText);
          if (data.success) {
            document.getElementById('renderStatusText').innerText = "✅ အောင်မြင်စွာ ပြီးဆုံးပါပြီ!";
            window.location.href = data.downloadUrl;
          } else {
            alert('Error: ' + data.message);
          }
        } else {
          alert('Processing အဆင်မပြေပါ။ Server Error ဖြစ်ပေါ်ခဲ့သည်။');
        }
        btn.disabled = false;
        btn.classList.remove('opacity-50');
      };

      xhr.onerror = function() {
        alert('Upload လုပ်နေစဉ် ကွန်ရက် ချို့ယွင်းမှု ဖြစ်ပေါ်ခဲ့သည်။');
        btn.disabled = false;
        btn.classList.remove('opacity-50');
      };

      xhr.open('POST', '/api/dub', true);
      xhr.send(formData);
    });
  </script>
</body>
</html>
"""

def extract_audio_from_video(video_path, audio_output_path):
    cmd = [
        'ffmpeg', '-y', '-i', video_path,
        '-vn', '-ac', '1', '-ar', '16000', '-ab', '64k',
        audio_output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def generate_srt_with_gemini_audio(client, audio_path):
    uploaded_audio = client.files.upload(file=audio_path)
    prompt = """
Listen to the audio track of this video carefully.
1. Transcribe all spoken dialogues (Chinese or English) with precise start and end timestamps.
2. Translate each dialogue directly into natural, natural-sounding spoken Myanmar (Burmese).
3. STRICTION ON LENGTH: Ensure the Burmese translation is concise enough to fit comfortably within the timestamp duration (approx 3.5 syllables per second).
4. Output STRICTLY in standard SRT format ONLY (No markdown formatting, no explanations, no html tags).

Example SRT format:
1
00:00:01,000 --> 00:00:03,500
မင်္ဂလာပါ ခင်ဗျာ။
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[uploaded_audio, prompt]
        )
        try:
            client.files.delete(name=uploaded_audio.name)
        except Exception:
            pass
        # SRT မှ မမြင်ရသောစာလုံးများ ရှင်းလင်းရန်
        raw_text = re.sub(r'[\u200e\u200f\u200b\u202a-\u202e]', '', str(response.text)).strip()
        cleaned_srt = re.sub(r'```(?:srt)?\n?', '', raw_text).strip('` \n')
        return cleaned_srt
    except Exception as e:
        print("Gemini Audio Error:", e)
        raise e

async def generate_tts_async(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def adjust_audio_speed_ffmpeg(input_file, output_file, speed_factor):
    safe_speed = max(0.85, min(1.15, speed_factor))
    cmd = [
        'ffmpeg', '-y', '-i', input_file,
        '-filter:a', f"atempo={safe_speed:.3f}",
        output_file
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/dub', methods=['POST'])
def process_dubbing():
    try:
        # ဤနေရာတွင် API Key နှင့် Filename ထဲမှ \u200e ကို ဖြတ်ထုတ်ပါမည်
        raw_api_key = request.form.get('apiKey', '')
        api_key = sanitize_text(raw_api_key)
        
        voice = request.form.get('voice', 'my-MM-NilarNeural')
        video_file = request.files.get('video')

        if not api_key or not video_file:
            return jsonify({"success": False, "message": "အချက်အလက်များ မစုံလင်ပါ။"}), 400

        # Filename Extension ကိုပါ သန့်ရှင်းရေးလုပ်ပါမည်
        clean_filename = sanitize_text(video_file.filename)
        _, ext = os.path.splitext(clean_filename)
        if not ext:
            ext = ".mp4"
            
        unique_id = str(uuid.uuid4())[:8]
        safe_filename = f"video_{unique_id}{ext}"
        video_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        video_file.save(video_path)

        output_filename = f"dubbed_{safe_filename}"
        output_video_path = os.path.join(OUTPUT_FOLDER, output_filename)

        # 1. Extract Audio
        temp_extracted_audio = os.path.join(UPLOAD_FOLDER, f"temp_speech_{unique_id}.mp3")
        extract_audio_from_video(video_path, temp_extracted_audio)

        # 2. Gemini Speech-to-SRT
        client = genai.Client(api_key=api_key)
        srt_content = generate_srt_with_gemini_audio(client, temp_extracted_audio)

        if os.path.exists(temp_extracted_audio):
            os.remove(temp_extracted_audio)

        subtitles = list(srt.parse(srt_content))
        if not subtitles:
            return jsonify({"success": False, "message": "Video ထဲတွင် စကားပြောသံ ရှာမတွေ့ပါ။"}), 400

        # Timeline Audio
        video_info = AudioSegment.from_file(video_path)
        total_duration_ms = len(video_info)
        final_audio = AudioSegment.silent(duration=total_duration_ms)

        # 3. TTS + Dynamic Speed
        for idx, sub in enumerate(subtitles):
            start_ms = int(sub.start.total_seconds() * 1000)
            end_ms = int(sub.end.total_seconds() * 1000)
            target_duration = (end_ms - start_ms) / 1000.0

            if target_duration <= 0.3:
                continue
            
            # Subtitle စာသားထဲမှ \u200e များကို ဖျက်ရန်
            mm_text = re.sub(r'[\u200e\u200f\u200b\u202a-\u202e]', '', str(sub.content)).replace('\n', ' ').strip()
            if not mm_text:
                continue

            temp_tts = os.path.join(UPLOAD_FOLDER, f"temp_{unique_id}_{idx}.mp3")
            temp_synced = os.path.join(UPLOAD_FOLDER, f"synced_{unique_id}_{idx}.wav")

            asyncio.run(generate_tts_async(mm_text, voice, temp_tts))

            gen_audio = AudioSegment.from_file(temp_tts)
            actual_duration = len(gen_audio) / 1000.0
            
            speed_factor = actual_duration / target_duration
            adjust_audio_speed_ffmpeg(temp_tts, temp_synced, speed_factor)

            synced_audio = AudioSegment.from_file(temp_synced)
            final_audio = final_audio.overlay(synced_audio, position=start_ms)

            if os.path.exists(temp_tts): os.remove(temp_tts)
            if os.path.exists(temp_synced): os.remove(temp_synced)

        # 4. Export & Merge
        final_audio_path = os.path.join(UPLOAD_FOLDER, f"final_dubbed_{unique_id}.wav")
        final_audio.export(final_audio_path, format="wav")

        merge_cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', final_audio_path,
            '-c:v', 'copy',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            output_video_path
        ]
        subprocess.run(merge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(final_audio_path): os.remove(final_audio_path)

        return jsonify({
            "success": True,
            "downloadUrl": f"/download/{output_filename}"
        })

    except Exception as e:
        print("Error:", e)
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)