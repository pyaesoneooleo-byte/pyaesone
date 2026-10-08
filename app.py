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
# UI HTML TEMPLATE (Updated with 2 New Checkboxes)
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
          <i class="fa-solid fa-microphone text-pink-400 mr-1"></i> အခြေခံ AI Voice ရွေးရန်
        </label>
        <select id="voiceType" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs text-white">
          <option value="my-MM-NilarNeural">မြန်မာ AI မိန်းကလေးအသံ (Nilar)</option>
          <option value="my-MM-ThihaNeural">မြန်မာ AI ယောကျာ်းလေးအသံ (Thiha)</option>
        </select>
      </div>

      <!-- NEW OPTIONS: Multi-Voice and Keep BGM -->
      <div class="bg-slate-900 p-3 rounded-xl border border-slate-700 space-y-2 text-xs text-slate-300 font-semibold">
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" id="multiVoice" checked class="accent-purple-500 w-4 h-4">
          <span>👥 ဇာတ်ကောင်အလိုက် အသံခွဲမည် (Male/Female Auto Switch)</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" id="keepBgm" checked class="accent-pink-500 w-4 h-4">
          <span>🎵 မူရင်း နောက်ခံတေးဂီတ (BGM) ကို ချန်ထားမည်</span>
        </label>
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
      
      // Append new Checkbox values
      formData.append('multiVoice', document.getElementById('multiVoice').checked);
      formData.append('keepBgm', document.getElementById('keepBgm').checked);

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

# Updated Gemini Prompt function to handle Multi-Voice
def generate_srt_with_gemini_audio(client, audio_path, multi_voice=False):
    uploaded_audio
