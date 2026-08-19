#include "talmaci_native.h"

#include "whisper.h"

#include <ctranslate2/translator.h>
#include <sentencepiece_processor.h>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace {

void set_err(char *err, int err_len, const std::string &msg) {
  if (err && err_len > 0) {
    std::snprintf(err, static_cast<size_t>(err_len), "%s", msg.c_str());
  }
}

char *dup_string(const std::string &s) {
  char *out = static_cast<char *>(std::malloc(s.size() + 1));
  if (out) {
    std::memcpy(out, s.c_str(), s.size() + 1);
  }
  return out;
}

void json_escape_into(std::string &out, const std::string &s) {
  for (unsigned char c : s) {
    switch (c) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (c < 0x20) {
          char buf[8];
          std::snprintf(buf, sizeof(buf), "\\u%04x", c);
          out += buf;
        } else {
          out += static_cast<char>(c);
        }
    }
  }
}

// Split text into sentences on ., !, ?, … followed by whitespace (or end).
// Keeps the terminator with the sentence. Anything left over is its own entry.
std::vector<std::string> split_sentences(const std::string &text) {
  std::vector<std::string> out;
  std::string cur;
  const std::string enders = ".!?";
  for (size_t i = 0; i < text.size(); ++i) {
    cur += text[i];
    bool is_end = enders.find(text[i]) != std::string::npos;
    // UTF-8 ellipsis "…" = E2 80 A6
    if (!is_end && i >= 2 && static_cast<unsigned char>(text[i]) == 0xA6 &&
        static_cast<unsigned char>(text[i - 1]) == 0x80 &&
        static_cast<unsigned char>(text[i - 2]) == 0xE2) {
      is_end = true;
    }
    if (is_end && (i + 1 >= text.size() || std::isspace(static_cast<unsigned char>(text[i + 1])))) {
      // Trim leading whitespace of the finished sentence.
      size_t b = cur.find_first_not_of(" \t\n\r");
      if (b != std::string::npos) {
        out.push_back(cur.substr(b));
      }
      cur.clear();
    }
  }
  size_t b = cur.find_first_not_of(" \t\n\r");
  if (b != std::string::npos) {
    out.push_back(cur.substr(b));
  }
  return out;
}

} // namespace

struct tn_stt {
  whisper_context *ctx = nullptr;
  std::mutex mu;
};

struct tn_mt {
  std::unique_ptr<ctranslate2::Translator> translator;
  sentencepiece::SentencePieceProcessor sp_src;
  sentencepiece::SentencePieceProcessor sp_tgt;
  // Some OPUS-MT models (e.g. eng-ron) need a target-language token like
  // ">>ron<<" prepended to the source tokens. Stored in prefix_token.txt in
  // the model dir by the fetch script; empty when not needed.
  std::string prefix_token;
  std::mutex mu;
};

extern "C" {

const char *tn_version(void) { return "talmaci-native 0.1.0"; }

tn_stt *tn_stt_load(const char *model_path, int use_gpu, char *err, int err_len) {
  if (!model_path) {
    set_err(err, err_len, "model_path is NULL");
    return nullptr;
  }
  whisper_context_params cparams = whisper_context_default_params();
  cparams.use_gpu = use_gpu != 0;
  whisper_context *ctx = whisper_init_from_file_with_params(model_path, cparams);
  if (!ctx) {
    set_err(err, err_len, std::string("failed to load whisper model: ") + model_path);
    return nullptr;
  }
  auto *h = new tn_stt();
  h->ctx = ctx;
  return h;
}

void tn_stt_free(tn_stt *h) {
  if (!h) return;
  if (h->ctx) whisper_free(h->ctx);
  delete h;
}

char *tn_stt_transcribe(tn_stt *h, const float *samples, int32_t n_samples,
                        const char *lang, int32_t n_threads,
                        char *err, int err_len) {
  if (!h || !h->ctx) {
    set_err(err, err_len, "invalid stt handle");
    return nullptr;
  }
  if (!samples || n_samples <= 0) {
    set_err(err, err_len, "no samples");
    return nullptr;
  }
  std::lock_guard<std::mutex> lock(h->mu);

  const auto t_start = std::chrono::steady_clock::now();

  whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
  params.language = (lang && lang[0]) ? lang : "en";
  params.translate = false;
  params.no_context = true;
  params.no_timestamps = false;
  params.print_progress = false;
  params.print_realtime = false;
  params.print_special = false;
  params.print_timestamps = false;
  params.suppress_blank = true;
  params.suppress_nst = true; // drop non-speech tokens like (music)
  params.temperature_inc = 0.0f; // no fallback re-decodes: latency over rescue
  if (n_threads > 0) {
    params.n_threads = n_threads;
  }

  if (whisper_full(h->ctx, params, samples, n_samples) != 0) {
    set_err(err, err_len, "whisper_full failed");
    return nullptr;
  }

  const auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                              std::chrono::steady_clock::now() - t_start)
                              .count();

  std::string json = "{\"segments\":[";
  const int n = whisper_full_n_segments(h->ctx);
  for (int i = 0; i < n; ++i) {
    const char *text = whisper_full_get_segment_text(h->ctx, i);
    const int64_t t0 = whisper_full_get_segment_t0(h->ctx, i) * 10; // centisec -> ms
    const int64_t t1 = whisper_full_get_segment_t1(h->ctx, i) * 10;
    if (i > 0) json += ",";
    json += "{\"t0\":" + std::to_string(t0) + ",\"t1\":" + std::to_string(t1) + ",\"text\":\"";
    json_escape_into(json, text ? text : "");
    json += "\"}";
  }
  json += "],\"elapsed_ms\":" + std::to_string(elapsed_ms) + "}";
  return dup_string(json);
}

tn_mt *tn_mt_load(const char *model_dir, char *err, int err_len) {
  if (!model_dir) {
    set_err(err, err_len, "model_dir is NULL");
    return nullptr;
  }
  try {
    auto h = std::make_unique<tn_mt>();
    const std::string dir(model_dir);
    if (!h->sp_src.Load(dir + "/source.spm").ok()) {
      set_err(err, err_len, "failed to load " + dir + "/source.spm");
      return nullptr;
    }
    if (!h->sp_tgt.Load(dir + "/target.spm").ok()) {
      set_err(err, err_len, "failed to load " + dir + "/target.spm");
      return nullptr;
    }
    h->translator = std::make_unique<ctranslate2::Translator>(
        dir, ctranslate2::Device::CPU, ctranslate2::ComputeType::DEFAULT);
    {
      std::ifstream pf(dir + "/prefix_token.txt");
      if (pf) {
        std::getline(pf, h->prefix_token);
        while (!h->prefix_token.empty() &&
               (h->prefix_token.back() == '\r' || h->prefix_token.back() == '\n' ||
                h->prefix_token.back() == ' ')) {
          h->prefix_token.pop_back();
        }
      }
    }
    return h.release();
  } catch (const std::exception &e) {
    set_err(err, err_len, std::string("failed to load translator: ") + e.what());
    return nullptr;
  }
}

void tn_mt_free(tn_mt *h) { delete h; }

char *tn_mt_translate(tn_mt *h, const char *text, int32_t beam_size,
                      char *err, int err_len) {
  if (!h || !h->translator) {
    set_err(err, err_len, "invalid mt handle");
    return nullptr;
  }
  if (!text) {
    set_err(err, err_len, "text is NULL");
    return nullptr;
  }
  std::lock_guard<std::mutex> lock(h->mu);
  try {
    const std::vector<std::string> sentences = split_sentences(text);
    if (sentences.empty()) {
      return dup_string("");
    }
    std::vector<std::vector<std::string>> batch;
    batch.reserve(sentences.size());
    for (const auto &s : sentences) {
      std::vector<std::string> pieces;
      h->sp_src.Encode(s, &pieces);
      if (!h->prefix_token.empty()) {
        pieces.insert(pieces.begin(), h->prefix_token);
      }
      batch.push_back(std::move(pieces));
    }
    ctranslate2::TranslationOptions options;
    options.beam_size = beam_size > 0 ? beam_size : 2;
    options.max_decoding_length = 512;
    const auto results = h->translator->translate_batch(batch, options);
    std::string out;
    for (size_t i = 0; i < results.size(); ++i) {
      if (results[i].hypotheses.empty()) continue;
      std::string detok;
      h->sp_tgt.Decode(results[i].hypotheses[0], &detok);
      if (!out.empty() && !detok.empty()) out += " ";
      out += detok;
    }
    return dup_string(out);
  } catch (const std::exception &e) {
    set_err(err, err_len, std::string("translate failed: ") + e.what());
    return nullptr;
  }
}

void tn_str_free(char *s) { std::free(s); }

} // extern "C"
