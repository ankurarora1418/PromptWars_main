// Read answers aloud with the browser's built-in text-to-speech (no data leaves the phone).

const VOICE_LANG = { en: "en-IN", hi: "hi-IN", pa: "pa-IN", ta: "ta-IN", te: "te-IN", bn: "bn-IN", mr: "mr-IN", kn: "kn-IN" };
let activeButton = null;

export function speechSupported() {
  return "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}

function pickVoice(lang) {
  const voices = window.speechSynthesis.getVoices();
  return voices.find((v) => v.lang === lang) || voices.find((v) => v.lang.startsWith(lang.slice(0, 2)));
}

export function stopSpeaking() {
  if (speechSupported()) window.speechSynthesis.cancel();
  if (activeButton) activeButton.setAttribute("aria-pressed", "false");
  activeButton = null;
}

/** Toggle reading `text` aloud; `button` reflects the playing state. */
export function toggleSpeak(text, langCode, button, labels) {
  if (!speechSupported()) return;
  if (activeButton === button) {
    stopSpeaking();
    button.textContent = labels.play;
    return;
  }
  stopSpeaking();
  const utterance = new SpeechSynthesisUtterance(text.replace(/[-•*]\s/g, ""));
  utterance.lang = VOICE_LANG[langCode] || "en-IN";
  const voice = pickVoice(utterance.lang);
  if (voice) utterance.voice = voice;
  utterance.rate = 0.95;
  utterance.onend = () => {
    if (activeButton === button) {
      button.setAttribute("aria-pressed", "false");
      button.textContent = labels.play;
      activeButton = null;
    }
  };
  activeButton = button;
  button.setAttribute("aria-pressed", "true");
  button.textContent = labels.stop;
  window.speechSynthesis.speak(utterance);
}
