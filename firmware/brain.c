#include <math.h>
#include <string.h>

#include "brain.h"
#include "policy_weights.h"

static inline float sigmoidf_(float x) { return 1.0f / (1.0f + expf(-x)); }

// y = W * x  (W la [rows][cols] duoc trai phang)
static void matvec(const float *W, const float *x, int rows, int cols, float *y)
{
    for (int i = 0; i < rows; ++i) {
        const float *w = W + (size_t)i * cols;
        float s = 0.0f;
        for (int j = 0; j < cols; ++j) s += w[j] * x[j];
        y[i] = s;
    }
}

void brain_reset(brain_state_t *st) { memset(st->h, 0, sizeof(st->h)); }

void brain_step(brain_state_t *st, const float *obs, float *out)
{
    float wx[BRAIN_HID], uh[BRAIN_HID];
    float z[BRAIN_HID], r[BRAIN_HID], n[BRAIN_HID];

    matvec(BRAIN_Wz, obs, BRAIN_HID, BRAIN_OBS, wx);
    matvec(BRAIN_Uz, st->h, BRAIN_HID, BRAIN_HID, uh);
    for (int i = 0; i < BRAIN_HID; ++i) z[i] = sigmoidf_(wx[i] + uh[i] + BRAIN_bz[i]);

    matvec(BRAIN_Wr, obs, BRAIN_HID, BRAIN_OBS, wx);
    matvec(BRAIN_Ur, st->h, BRAIN_HID, BRAIN_HID, uh);
    for (int i = 0; i < BRAIN_HID; ++i) r[i] = sigmoidf_(wx[i] + uh[i] + BRAIN_br[i]);

    matvec(BRAIN_Wn, obs, BRAIN_HID, BRAIN_OBS, wx);
    matvec(BRAIN_Un, st->h, BRAIN_HID, BRAIN_HID, uh);
    for (int i = 0; i < BRAIN_HID; ++i)
        n[i] = tanhf(wx[i] + r[i] * uh[i] + BRAIN_bn[i]);

    for (int i = 0; i < BRAIN_HID; ++i)
        st->h[i] = (1.0f - z[i]) * st->h[i] + z[i] * n[i];

    matvec(BRAIN_Wo, st->h, BRAIN_ACT, BRAIN_HID, out);
    for (int i = 0; i < BRAIN_ACT; ++i) out[i] = tanhf(out[i] + BRAIN_bo[i]);
}
