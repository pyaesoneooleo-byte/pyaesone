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
    return re.sub(r'[\u200e\u200f\u200b\u202a-\u202e\s]', '', str(text)).strip()

# ==========================================
# UI HTML TEMPLATE (Updated with New Features)
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
  <style>
    .tab-active { background-color: #4f46e5; color: white; border-color: #4f46e5; }
    .tab-inactive { background-color: transparent; color: #94a3b8; border-color: #334155; }
  </style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center p-4">

  <div class="max-w-xl w-full bg-slate-800 border border-slate-700 rounded-2xl p-6 shadow-2xl space-y-5">
    <div class="text-center space-y-2">
      <div class="inline-flex items-center gap-2 bg-purple-500/10 text-purple-400 px-3 py-1 rounded-full text-xs font-semibold border border-purple-500/20">
        ✨ Pro Video Speech-to-Dub Engine
      </div>
      <h1 class="text-2xl font-bold text-white">AI Video Dubber</h1>
    </div>

    <!-- Mode Selector -->
    <div class="flex rounded-xl overflow-hidden border border-slate-700 p-1 bg-slate-900 text-sm font-semibold">
      <button type="button" id="tabAuto" onclick="switchTab('auto')" class="flex-1 py-2 text-center rounded-lg transition-all tab-active">
        🤖 Auto AI (Gemini)
      </button>
      <button type="button" id="tabManual" onclick="switchTab('manual')" class="flex-1 py-2 text-center rounded-lg transition-all tab-inactive">
        📝 SRT File ဖြင့် Dub မည်
      </button>
    </div>

    <form id="dubbingForm" class="space-y-4">
      
      <!-- Video Input -->
      <div class="space-y-1.5">
        <label class="block text-xs font-semibold text-slate-300">
          <i class="fa-solid fa-video text-blue-400 mr-1"></i> Video File (.mp4, .mkv)
        </label>
        <div class="border-2 border-dashed border-slate-700 hover:border-blue-500/50 bg-slate-900/50 rounded-xl p-3 text-center cursor-pointer relative">
          <input type="file" id="videoFile" accept="video/*" required onchange="updateName(this, 'videoName')" class="absolute inset-0 opacity-0 cursor-pointer w-full h-full">
          <i class="fa-solid fa-cloud-arrow-up text-xl text-slate-400 mb-1"></i>
          <p id="videoName" class="text-xs text-slate-300">Video ဖိုင်ကို ရွေးပါ</p>
        </div>
      </div>

      <!-- API Key Section (Hidden in Manual Mode) -->
      <div id="apiKeySection" class="space-y-1.5 transition-all">
        <label class="block text-xs font-semibold text-slate-300">
          <i class="fa-solid fa-key text-purple-400 mr-1"></i> Google Gemini API Key
        </label>
        <input type="password" id="apiKey" placeholder="AIzaSy..." 
          class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500">
      </div>

      <!-- SRT Upload Section (Hidden in Auto Mode) -->
      <div id="srtSection" class="space-y-1.5 hidden transition-all">
        <label class="block text-xs font-semibold text-slate-300">
          <i class="fa-solid fa-closed-captioning text-yellow-400 mr-1"></i> SRT Subtitle File (Optional)
        </label>
        <div class="border border-slate-700 bg-slate-900/50 rounded-xl p-3 text-center cursor-pointer relative">
          <input type="file" id="srtFile" accept=".srt" onchange="updateName(this, 'srtName')" class="absolute inset-0 opacity-0 cursor-pointer w-full h-full">
          <p id="srtName" class="text-xs text-slate-300">SRT ဖိုင် ရွေးချယ်ပါ (မရွေးလည်းရသည်)</p>
        </div>
      </div>

      <!-- Base Voice -->
      <div class="space-y-1.5">
        <label class="block text-xs font-semibold text-slate-300">
          <i class="fa-solid fa-microphone text-pink-400 mr-1"></i> အခြေခံ AI Voice
        </label>
        <select id="voiceType" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2 text-xs text-white">
          <option value="my-MM-NilarNeural">မြန်မာ မိန်းကလေး (Nilar)</option>
          <option value="my-MM-ThihaNeural">မြန်မာ ယောကျာ်းလေး (Thiha)</option>
        </select>
      </div>

      <!-- New Features Checkboxes -->
      <div class="bg-slate-900 p-3 rounded-xl border border-slate-700 space-y-2 text-xs text-slate-300 font-semibold">
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" id="multiVoice" checked class="accent-purple-500 w-4 h-4">
          <span>👥 ဇာတ်ကောင်အလိုက် အသံခွဲမည် (Male/Female Auto Switch)</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" id="addHardsub" class="accent-blue-500 w-4 h-4">
          <span>📝 မြန်မာစာတန်းထိုး Video တွင် ထည့်မည် (Hardsub)</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" id="keepBgm" checked class="accent-pink-500 w-4 h-4">
          <span>🎵 မူရင်း နောက်ခံတေးဂီတ (BGM) ကို ချန်ထားမည်</span>
        </label>
      </div>

      <button type="submit" id="submitBtn" class="w-full bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-sm font-bold py-3 rounded-xl shadow-lg transition">
        🚀 Dubbing စတင်ရန်
      </button>
    </form>

    <div id="statusBox" class="hidden p-4 bg-slate-900/90 rounded-xl border border-slate-700 space-y-3">
      <div id="uploadSection" class="space-y-1.5">
        <div class="flex justify-between items-center text-xs text-slate-300 font-semibold">
          <span id="uploadLabel"><i class="fa-solid fa-spinner fa-spin text-blue-400 mr-1"></i> Upload & Processing...</span>
          <span id="uploadPercent" class="text-blue-400 font-bold">0%</span>
        </div>
        <div class="w-full bg-slate-800 h-2.5 rounded-full overflow-hidden border border-slate-700">
          <div id="uploadProgressBar" class="bg-gradient-to-r from-blue-500 to-cyan-400 h-full w-0 transition-all duration-150"></div>
        </div>
      </div>
      <div id="renderSection" class="hidden pt-2 border-t border-slate-800 space-y-1">
        <div class="flex items-center gap-2 text-xs text-purple-400 font-semibold">
          <i class="fa-solid fa-wand-magic-sparkles fa-spin"></i>
          <span id="renderStatusText">Server တွင် အသံနှင့် Video ကို ပေါင်းစပ်နေပါသည်...</span>
        </div>
        <p class="text-[10px] text-yellow-500">* Hardsub ပြုလုပ်ပါက Video အသစ်ပြန်ထုတ်ရသဖြင့် အချိန်ပိုကြာနိုင်ပါသည်။</p>
      </div>
    </div>
  </div>

  <script>
    let currentMode = 'auto';

    function switchTab(mode) {
      currentMode = mode;
      const tabAuto = document.getElementById('tabAuto');
      const tabManual = document.getElementById('tabManual');
      const apiKeySec = document.getElementById('apiKeySection');
      const srtSec = document.getElementById('srtSection');
      
      if(mode === 'auto') {
        tabAuto.className = "flex-1 py-2 text-center rounded-lg transition-all tab-active";
        tabManual.className = "flex-1 py-2 text-center rounded-lg transition-all tab-inactive";
        apiKeySec.classList.remove('hidden');
        srtSec.classList.add('hidden');
        document.getElementById('apiKey').required = true;
      } else {
        tabManual.className = "flex-1 py-2 text-center rounded-lg transition-all tab-active";
        tabAuto.className = "flex-1 py-2 text-center rounded-lg transition-all tab-inactive";
        apiKeySec.classList.add('hidden');
        srtSec.classList.remove('hidden');
        document.getElementById('apiKey').required = false;
      }
    }

    function updateName(input, id) {
      if(input.files && input.files[0]) {
        document.getElementById(id).innerText = "📄 " + input.files[0].name;
      }
    }

    document.getElementById('dubbingForm').addEventListener('submit', function(e) {
      e.preventDefault();

      const btn = document.getElementById('submitBtn');
      const statusBox = document.getElementById('statusBox');
      const uploadProgressBar = document.getElementById('uploadProgressBar');
      const uploadPercent = document.getElementById('uploadPercent');
      const renderSection = document.getElementById('renderSection');

      btn.disabled = true;
      btn.classList.add('opacity-50');
      statusBox.classList.remove('hidden');
      renderSection.classList.add('hidden');
      uploadProgressBar.style.width = '0%';
      uploadPercent.innerText = '0%';

      const formData = new FormData();
      formData.append('mode', currentMode);
      formData.append('video', document.getElementById('videoFile').files[0]);
      formData.append('voice', document.getElementById('voiceType').value);
      formData.append('multiVoice', document.getElementById('multiVoice').checked);
      formData.append('addHardsub', document.getElementById('addHardsub').checked);
      formData.append('keepBgm', document.getElementById('keepBgm').checked);

      if(currentMode === 'auto') {
        formData.append('apiKey', document.getElementById('apiKey').value);
      } else {
        const srtFile = document.getElementById('srtFile').files[0];
        if(srtFile) formData.append('srtFile', srtFile);
      }

      const xhr = new XMLHttpRequest();
      xhr.upload.addEventListener('progress', function(e) {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          uploadProgressBar.style.width = percent + '%';
          uploadPercent.innerText = percent + '%';
          if (percent === 100) {
            document.getElementById('uploadLabel').innerHTML = '<i class="fa-solid fa-cogs text-emerald-400 mr-1"></i> ဖန်တီးနေပါသည်...';
            renderSection.classList.remove('hidden');
          }
        }
      });

      xhr.onload = function() {
        btn.disabled = false;
        btn.classList.remove('opacity-50');
        if (xhr.status === 200) {
          const data = JSON.parse(xhr.responseText);
          if (data.success) {
            document.getElementById('renderStatusText').innerText = "✅ အောင်မြင်စွာ ပြီးဆုံးပါပြီ!";
            window.location.href = data.downloadUrl;
          } else {
            alert('Error: ' + data.message);
          }
        } else {
          alert('Server Error ဖြစ်ပေါ်ခဲ့သည်။ (Video အရှည်ကြီးဖြစ်ပါက Render Timeout ဖြစ်နိုင်ပါသည်)');
        }
      };

      xhr.onerror = function() {
        alert('ကွန်ရက် ချို့ယွင်းမှု ဖြစ်ပေါ်ခဲ့သည်။');
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
    cmd = ['ffmpeg', '-y', '-i', video_path, '-vn', '-ac', '1', '-ar', '16000', '-ab', '64k', audio_output_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def generate_srt_with_gemini_audio(client, audio_path, multi_voice=False):
    uploaded_audio = client.files.upload(file=audio_path)
    
    prompt = """
Listen to the audio track carefully.
1. Transcribe all spoken dialogues with precise start and end timestamps.
2. Translate directly into natural spoken Myanmar (Burmese).
3. Ensure the Burmese translation is concise to fit the timestamp duration.
4. Output STRICTLY in standard SRT format ONLY.
"""
    if multi_voice:
        prompt += """
5. MULTI-SPEAKER TAG: Identify the speaker's gender. Prefix the translation with [M] for male voice, or [F] for female voice.
Example format:
1
00:00:01,000 --> 00:00:03,500
[M] မင်္ဂလာပါ ခင်ဗျာ။

2
00:00:04,000 --> 00:00:05,500
[F] ဟုတ်ကဲ့၊ မင်္ဂလာပါ။
"""
    else:
        prompt += "\nExample format:\n1\n00:00:01,000 --> 00:00:03,500\nမင်္ဂလာပါ ခင်ဗျာ။"

    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[uploaded_audio, prompt]
        )
        try:
            client.files.delete(name=uploaded_audio.name)
        except:
            pass
        raw_text = re.sub(r'[\u200e\u200f\u200b\u202a-\u202e]', '', str(response.text)).strip()
        cleaned_srt = re.sub(r'```(?:srt)?\n?', '', raw_text).strip('` \n')
        return cleaned_srt
    except Exception as e:
        raise Exception(f"Gemini Error: {str(e)}")

async def generate_tts_async(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def adjust_audio_speed_ffmpeg(input_file, output_file, speed_factor):
    safe_speed = max(0.85, min(1.15, speed_factor))
    cmd = ['ffmpeg', '-y', '-i', input_file, '-filter:a', f"atempo={safe_speed:.3f}", output_file]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/dub', methods=['POST'])
def process_dubbing():
    try:
        mode = request.form.get('mode', 'auto')
        voice_default = request.form.get('voice', 'my-MM-NilarNeural')
        multi_voice = request.form.get('multiVoice') == 'true'
        add_hardsub = request.form.get('addHardsub') == 'true'
        keep_bgm = request.form.get('keepBgm') == 'true'
        
        video_file = request.files.get('video')
        if not video_file:
            return jsonify({"success": False, "message": "Video ဖိုင် လိုအပ်ပါသည်။"}), 400

        unique_id = str(uuid.uuid4())[:8]
        video_ext = os.path.splitext(video_file.filename)[1] or ".mp4"
        video_path = os.path.join(UPLOAD_FOLDER, f"input_{unique_id}{video_ext}")
        video_file.save(video_path)

        # Handle SRT Source
        srt_content = ""
        if mode == 'auto':
            api_key = sanitize_text(request.form.get('apiKey', ''))
            if not api_key:
                return jsonify({"success": False, "message": "API Key လိုအပ်ပါသည်။"}), 400
                
            temp_extracted_audio = os.path.join(UPLOAD_FOLDER, f"temp_{unique_id}.mp3")
            extract_audio_from_video(video_path, temp_extracted_audio)
            
            client = genai.Client(api_key=api_key)
            srt_content = generate_srt_with_gemini_audio(client, temp_extracted_audio, multi_voice)
            if os.path.exists(temp_extracted_audio): os.remove(temp_extracted_audio)
        else:
            srt_file = request.files.get('srtFile')
            if srt_file:
                srt_content = srt_file.read().decode('utf-8')
            else:
                return jsonify({"success": False, "message": "SRT ဖိုင် တင်ပေးရန် လိုအပ်ပါသည်။"}), 400

        subtitles = list(srt.parse(srt_content))
        if not subtitles:
            return jsonify({"success": False, "message": "စကားပြောသံ/စာသား ရှာမတွေ့ပါ။"}), 400

        video_info = AudioSegment.from_file(video_path)
        final_audio = AudioSegment.silent(duration=len(video_info))

        # Generate Audio and Clean Subtitles for Hardsub
        cleaned_subtitles_for_export = []
        for idx, sub in enumerate(subtitles):
            start_ms = int(sub.start.total_seconds() * 1000)
            end_ms = int(sub.end.total_seconds() * 1000)
            target_duration = (end_ms - start_ms) / 1000.0
            if target_duration <= 0.3: continue
            
            raw_text = re.sub(r'[\u200e\u200f\u200b\u202a-\u202e]', '', str(sub.content)).replace('\n', ' ').strip()
            if not raw_text: continue

            # Determine Voice for Multi-speaker
            current_voice = voice_default
            if multi_voice:
                if '[M]' in raw_text or '[m]' in raw_text:
                    current_voice = 'my-MM-ThihaNeural'
                elif '[F]' in raw_text or '[f]' in raw_text:
                    current_voice = 'my-MM-NilarNeural'
            
            # Clean tags for speech and subtitle text
            clean_text = re.sub(r'\[[MmFf]\]\s*', '', raw_text).strip()
            
            # Save cleaned text back for Hardsub exporting
            sub.content = clean_text
            cleaned_subtitles_for_export.append(sub)

            if not clean_text: continue

            temp_tts = os.path.join(UPLOAD_FOLDER, f"tts_{unique_id}_{idx}.mp3")
            temp_synced = os.path.join(UPLOAD_FOLDER, f"sync_{unique_id}_{idx}.wav")

            asyncio.run(generate_tts_async(clean_text, current_voice, temp_tts))

            actual_duration = len(AudioSegment.from_file(temp_tts)) / 1000.0
            adjust_audio_speed_ffmpeg(temp_tts, temp_synced, actual_duration / target_duration)

            synced_audio = AudioSegment.from_file(temp_synced)
            final_audio = final_audio.overlay(synced_audio, position=start_ms)

            if os.path.exists(temp_tts): os.remove(temp_tts)
            if os.path.exists(temp_synced): os.remove(temp_synced)

        final_audio_path = os.path.join(UPLOAD_FOLDER, f"ai_audio_{unique_id}.wav")
        final_audio.export(final_audio_path, format="wav")

        output_filename = f"dubbed_{unique_id}.mp4"
        output_video_path = os.path.join(OUTPUT_FOLDER, output_filename)

        # Merge Audio/Video using FFmpeg based on selected features
        ffmpeg_cmd = ['ffmpeg', '-y', '-i', video_path, '-i', final_audio_path]
        
        # 1. Hardsub Filter String
        srt_filename = f"sub_{unique_id}.srt"
        srt_path = os.path.join(UPLOAD_FOLDER, srt_filename)
        
        if add_hardsub:
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt.compose(cleaned_subtitles_for_export))
        
        # 2. Build FFmpeg Arguments
        if add_hardsub and keep_bgm:
            # Video re-encode with subtitle + Audio Ducking
            ffmpeg_cmd.extend([
                '-filter_complex', f"[0:v]subtitles={srt_filename}[v]; [0:a]volume=0.15[a0]; [1:a]volume=1.5[a1]; [a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
                '-map', '[v]', '-map', '[a]',
                '-c:v', 'libx264', '-preset', 'fast', '-c:a', 'aac'
            ])
        elif add_hardsub:
            # Video re-encode with subtitle ONLY
            ffmpeg_cmd.extend([
                '-vf', f"subtitles={srt_filename}",
                '-map', '0:v', '-map', '1:a',
                '-c:v', 'libx264', '-preset', 'fast', '-c:a', 'aac'
            ])
        elif keep_bgm:
            # Audio Ducking ONLY (Copy Video, saves time)
            ffmpeg_cmd.extend([
                '-filter_complex', "[0:a]volume=0.15[a0]; [1:a]volume=1.5[a1]; [a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
                '-map', '0:v', '-map', '[a]',
                '-c:v', 'copy', '-c:a', 'aac'
            ])
        else:
            # Basic Dubbing (Replace Audio completely)
            ffmpeg_cmd.extend(['-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-shortest'])
        
        ffmpeg_cmd.append(output_video_path)
        
        # Run ffmpeg inside UPLOAD_FOLDER to avoid absolute path escaping issues with subtitle filter
        subprocess.run(ffmpeg_cmd, cwd=UPLOAD_FOLDER, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Cleanup Temporary Files
        if os.path.exists(final_audio_path): os.remove(final_audio_path)
        if os.path.exists(srt_path): os.remove(srt_path)
        if os.path.exists(video_path): os.remove(video_path)

        return jsonify({"success": True, "downloadUrl": f"/download/{output_filename}"})

    except Exception as e:
        print("Error:", e)
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
