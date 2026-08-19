// talmaci-cli — exercises the exact same native API the Mac app uses,
// from the command line, on any platform. Used by CI and for diagnostics.
//
//   talmaci-cli --stt ggml-small.bin --lang ro audio.wav
//   talmaci-cli --mt models/opus-mt-ro-en --text "Bună dimineața!"
//   talmaci-cli --stt ... --mt ... --lang ro audio.wav        (full pipeline)
//   ... --stream        simulate near-real-time windowed transcription
//
// WAV input must be PCM (16-bit int or 32-bit float); it is converted to
// 16 kHz mono the same way the app does (averaging channels, linear resample).

#include "talmaci_native.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

namespace {

struct WavData {
  std::vector<float> samples; // mono
  uint32_t sample_rate = 0;
};

bool read_wav(const std::string &path, WavData &out, std::string &err) {
  std::ifstream f(path, std::ios::binary);
  if (!f) {
    err = "cannot open " + path;
    return false;
  }
  auto read_u32 = [&](uint32_t &v) { f.read(reinterpret_cast<char *>(&v), 4); return bool(f); };
  auto read_u16 = [&](uint16_t &v) { f.read(reinterpret_cast<char *>(&v), 2); return bool(f); };

  char tag[5] = {0};
  uint32_t riff_size = 0;
  f.read(tag, 4);
  if (std::strncmp(tag, "RIFF", 4) != 0) { err = "not a RIFF file"; return false; }
  read_u32(riff_size);
  f.read(tag, 4);
  if (std::strncmp(tag, "WAVE", 4) != 0) { err = "not a WAVE file"; return false; }

  uint16_t format = 0, channels = 0, bits = 0;
  uint32_t rate = 0;
  bool got_fmt = false;
  while (f) {
    f.read(tag, 4);
    uint32_t chunk_size = 0;
    if (!read_u32(chunk_size)) break;
    if (std::strncmp(tag, "fmt ", 4) == 0) {
      uint32_t byte_rate; uint16_t block_align;
      read_u16(format); read_u16(channels); read_u32(rate);
      read_u32(byte_rate); read_u16(block_align); read_u16(bits);
      if (chunk_size > 16) f.seekg(chunk_size - 16, std::ios::cur);
      got_fmt = true;
    } else if (std::strncmp(tag, "data", 4) == 0) {
      if (!got_fmt) { err = "data chunk before fmt"; return false; }
      std::vector<char> raw(chunk_size);
      f.read(raw.data(), chunk_size);
      size_t frames = 0;
      std::vector<float> interleaved;
      if (format == 1 && bits == 16) {
        frames = chunk_size / 2 / channels;
        interleaved.resize(frames * channels);
        const int16_t *p = reinterpret_cast<const int16_t *>(raw.data());
        for (size_t i = 0; i < frames * channels; ++i) interleaved[i] = p[i] / 32768.0f;
      } else if (format == 3 && bits == 32) {
        frames = chunk_size / 4 / channels;
        interleaved.resize(frames * channels);
        std::memcpy(interleaved.data(), raw.data(), frames * channels * 4);
      } else {
        err = "unsupported WAV format (need PCM16 or float32)";
        return false;
      }
      out.samples.resize(frames);
      for (size_t i = 0; i < frames; ++i) {
        float acc = 0;
        for (uint16_t c = 0; c < channels; ++c) acc += interleaved[i * channels + c];
        out.samples[i] = acc / channels;
      }
      out.sample_rate = rate;
      return true;
    } else {
      f.seekg(chunk_size + (chunk_size & 1), std::ios::cur);
    }
  }
  err = "no data chunk found";
  return false;
}

std::vector<float> resample_to_16k(const std::vector<float> &in, uint32_t rate) {
  if (rate == 16000) return in;
  const double ratio = 16000.0 / rate;
  const size_t n_out = static_cast<size_t>(in.size() * ratio);
  std::vector<float> out(n_out);
  for (size_t i = 0; i < n_out; ++i) {
    const double src = i / ratio;
    const size_t i0 = static_cast<size_t>(src);
    const size_t i1 = std::min(i0 + 1, in.size() - 1);
    const double frac = src - i0;
    out[i] = static_cast<float>(in[i0] * (1.0 - frac) + in[i1] * frac);
  }
  return out;
}

// Very small JSON text extractor: concatenates all "text" values.
std::string extract_texts(const std::string &json) {
  std::string out;
  size_t pos = 0;
  while ((pos = json.find("\"text\":\"", pos)) != std::string::npos) {
    pos += 8;
    std::string piece;
    while (pos < json.size()) {
      char c = json[pos];
      if (c == '\\' && pos + 1 < json.size()) {
        char n = json[pos + 1];
        if (n == 'n') piece += '\n';
        else if (n == 't') piece += '\t';
        else if (n == 'u') { pos += 4; } // skip \uXXXX crudely (control chars only)
        else piece += n;
        pos += 2;
        continue;
      }
      if (c == '"') break;
      piece += c;
      ++pos;
    }
    out += piece;
  }
  return out;
}

int usage() {
  std::fprintf(stderr,
    "usage: talmaci-cli [--stt GGML_MODEL --lang ro|en] [--mt CT2_DIR] "
    "[--text TEXT] [--threads N] [--beam N] [--stream] [--no-gpu] [WAV]\n");
  return 2;
}

} // namespace

int main(int argc, char **argv) {
  std::string stt_model, mt_dir, lang = "en", text, wav_path;
  int threads = 4, beam = 2;
  bool stream = false, use_gpu = true;

  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    auto next = [&]() -> const char * { return (i + 1 < argc) ? argv[++i] : nullptr; };
    if (a == "--stt") { const char *v = next(); if (!v) return usage(); stt_model = v; }
    else if (a == "--mt") { const char *v = next(); if (!v) return usage(); mt_dir = v; }
    else if (a == "--lang") { const char *v = next(); if (!v) return usage(); lang = v; }
    else if (a == "--text") { const char *v = next(); if (!v) return usage(); text = v; }
    else if (a == "--threads") { const char *v = next(); if (!v) return usage(); threads = std::atoi(v); }
    else if (a == "--beam") { const char *v = next(); if (!v) return usage(); beam = std::atoi(v); }
    else if (a == "--stream") { stream = true; }
    else if (a == "--no-gpu") { use_gpu = false; }
    else if (a == "--help" || a == "-h") { return usage(); }
    else if (!a.empty() && a[0] == '-') { std::fprintf(stderr, "unknown flag %s\n", a.c_str()); return usage(); }
    else { wav_path = a; }
  }

  std::printf("%s\n", tn_version());
  char err[512] = {0};

  tn_mt *mt = nullptr;
  if (!mt_dir.empty()) {
    mt = tn_mt_load(mt_dir.c_str(), err, sizeof(err));
    if (!mt) { std::fprintf(stderr, "mt load error: %s\n", err); return 1; }
    std::printf("mt loaded: %s\n", mt_dir.c_str());
  }

  std::string transcript;

  if (!stt_model.empty()) {
    if (wav_path.empty()) { std::fprintf(stderr, "--stt requires a WAV file\n"); return usage(); }
    WavData wav;
    std::string werr;
    if (!read_wav(wav_path, wav, werr)) { std::fprintf(stderr, "wav error: %s\n", werr.c_str()); return 1; }
    std::vector<float> samples = resample_to_16k(wav.samples, wav.sample_rate);
    std::printf("audio: %.2fs @16kHz mono\n", samples.size() / 16000.0);

    tn_stt *stt = tn_stt_load(stt_model.c_str(), use_gpu ? 1 : 0, err, sizeof(err));
    if (!stt) { std::fprintf(stderr, "stt load error: %s\n", err); return 1; }

    if (stream) {
      // Simulate the app: grow the window in 0.6 s ticks, re-transcribing the
      // window each tick, exactly like StreamingTranscriber does.
      const size_t tick = 16000 * 6 / 10;
      const size_t max_window = 16000 * 12;
      size_t start = 0;
      for (size_t end = tick; end <= samples.size(); end += tick) {
        if (end - start > max_window) start = end - max_window;
        char *json = tn_stt_transcribe(stt, samples.data() + start,
                                       static_cast<int32_t>(end - start),
                                       lang.c_str(), threads, err, sizeof(err));
        if (!json) { std::fprintf(stderr, "stt error: %s\n", err); return 1; }
        std::string t = extract_texts(json);
        std::string j(json);
        size_t e = j.find("\"elapsed_ms\":");
        std::string ms = e == std::string::npos ? "?" : j.substr(e + 13, j.find('}', e) - e - 13);
        std::printf("[%5.1fs win=%4.1fs %5sms] %s\n", end / 16000.0,
                    (end - start) / 16000.0, ms.c_str(), t.c_str());
        tn_str_free(json);
        transcript = t;
      }
    } else {
      char *json = tn_stt_transcribe(stt, samples.data(),
                                     static_cast<int32_t>(samples.size()),
                                     lang.c_str(), threads, err, sizeof(err));
      if (!json) { std::fprintf(stderr, "stt error: %s\n", err); return 1; }
      transcript = extract_texts(json);
      std::printf("json: %s\n", json);
      std::printf("transcript: %s\n", transcript.c_str());
      tn_str_free(json);
    }
    tn_stt_free(stt);
  }

  if (!text.empty()) transcript = text;

  if (mt && !transcript.empty()) {
    char *out = tn_mt_translate(mt, transcript.c_str(), beam, err, sizeof(err));
    if (!out) { std::fprintf(stderr, "mt error: %s\n", err); return 1; }
    std::printf("translation: %s\n", out);
    tn_str_free(out);
  }
  if (mt) tn_mt_free(mt);
  return 0;
}
