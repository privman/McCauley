// talmaci_native — C API over whisper.cpp (speech-to-text) and
// CTranslate2 + SentencePiece (OPUS-MT machine translation).
//
// The Swift app dlopen()s this library, so this header is the whole contract:
// plain C, no C++ types, caller frees returned strings with tn_str_free().
// All functions are thread-safe with respect to *different* handles; a single
// handle must not be used from two threads at once.

#ifndef TALMACI_NATIVE_H
#define TALMACI_NATIVE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct tn_stt tn_stt;
typedef struct tn_mt tn_mt;

// Library version string, static storage (do not free).
const char *tn_version(void);

// ---- Speech to text (whisper) ----

// Load a ggml whisper model. use_gpu != 0 enables Metal where available.
// On failure returns NULL and writes a message into err (if non-NULL).
tn_stt *tn_stt_load(const char *model_path, int use_gpu, char *err, int err_len);
void tn_stt_free(tn_stt *h);

// Transcribe 16 kHz mono float32 PCM. lang is an ISO 639-1 code ("ro", "en").
// Returns a malloc'd JSON string:
//   {"segments":[{"t0":ms,"t1":ms,"text":"..."}], "elapsed_ms": n}
// or NULL on failure (message in err). Free the result with tn_str_free().
char *tn_stt_transcribe(tn_stt *h, const float *samples, int32_t n_samples,
                        const char *lang, int32_t n_threads,
                        char *err, int err_len);

// ---- Machine translation (CTranslate2 + SentencePiece) ----

// Load a CTranslate2 model directory that also contains source.spm and
// target.spm (as produced by scripts/fetch-models.sh).
tn_mt *tn_mt_load(const char *model_dir, char *err, int err_len);
void tn_mt_free(tn_mt *h);

// Translate one chunk of text (may contain several sentences; sentences are
// split and batched internally). beam_size <= 0 selects the default (2).
// Returns a malloc'd UTF-8 string, or NULL on failure. Free with tn_str_free().
char *tn_mt_translate(tn_mt *h, const char *text, int32_t beam_size,
                      char *err, int err_len);

void tn_str_free(char *s);

#ifdef __cplusplus
}
#endif

#endif // TALMACI_NATIVE_H
