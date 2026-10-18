/* Same real FIR coefficients on interleaved complex float32 IQ.
 * input contains ntaps-1 history samples followed by count new samples.
 * Separate input/output buffers are required. No radio/device access. */
#include <stddef.h>
#include <stdint.h>
#ifdef __aarch64__
#include <arm_neon.h>
#endif

void ble_fir(const float *restrict input, const float *restrict taps,
             size_t ntaps, float *restrict output, size_t count) {
#ifdef __aarch64__
    size_t i = 0;
    for (; i + 16 <= count * 2; i += 16) {
        float32x4_t a = vdupq_n_f32(0), b = a, c = a, d = a;
        for (size_t k = 0; k < ntaps; ++k) {
            const float *source = input + i + 2 * (ntaps - 1 - k);
            const float32x4_t coefficient = vdupq_n_f32(taps[k]);
            a = vfmaq_f32(a, vld1q_f32(source), coefficient);
            b = vfmaq_f32(b, vld1q_f32(source + 4), coefficient);
            c = vfmaq_f32(c, vld1q_f32(source + 8), coefficient);
            d = vfmaq_f32(d, vld1q_f32(source + 12), coefficient);
        }
        vst1q_f32(output + i, a);
        vst1q_f32(output + i + 4, b);
        vst1q_f32(output + i + 8, c);
        vst1q_f32(output + i + 12, d);
    }
    for (; i < count * 2; ++i) {
        float value = 0;
        for (size_t k = 0; k < ntaps; ++k)
            value += taps[k] * input[i + 2 * (ntaps - 1 - k)];
        output[i] = value;
    }
#else
    for (size_t i = 0; i < count * 2; ++i) output[i] = 0.0f;
    /* Keep the working set in L1 on small ARM cores. */
    for (size_t begin = 0; begin < count * 2; begin += 256) {
        size_t end = begin + 256;
        if (end > count * 2) end = count * 2;
        for (size_t k = 0; k < ntaps; ++k) {
            const float coefficient = taps[k];
            const float *restrict source = input + 2 * (ntaps - 1 - k);
            for (size_t i = begin; i < end; ++i)
                output[i] += coefficient * source[i];
        }
    }
#endif
}

/* Correlation >= 28 for a 32-bit +/-1 pattern is Hamming distance <= 2.
 * Rolling words avoid repeating 32 multiply/adds for every candidate. */
size_t ble_access_hits(const uint8_t *positive, size_t count, size_t sps,
                       uint32_t pattern, size_t *hits) {
    size_t used = 0;
    for (size_t phase = 0; phase < sps; ++phase) {
        uint32_t word = 0;
        size_t symbols = 0;
        for (size_t i = phase; i < count; i += sps) {
            word = (word << 1) | (positive[i] != 0);
            if (++symbols >= 32 && __builtin_popcount(word ^ pattern) <= 2)
                hits[used++] = i - 31 * sps;
        }
    }
    return used;
}
