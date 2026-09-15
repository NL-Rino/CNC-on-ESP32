// Khung firmware ESP32 (Arduino core) - MOI CHI LA BO XUONG.
// Chua do dac phan cung that nen cac hang so o day chi la cho trong.
#include "brain.h"

static const float SONAR_MAX_M = 2.0f;
static const float V_MAX = 0.60f;
static const float OMEGA_MAX = 2.0f * V_MAX / 0.15f;
static const float BATT_LOW = 0.40f;
static const uint32_t PERIOD_MS = 50;      // 20 Hz, dung bang dt trong mo phong

static brain_state_t brain;
static float obs[BRAIN_OBS];
static float prev_ir[2] = {0, 0};
static float prev_u[2] = {0, 0};

// --- cac ham nay se viet khi co phan cung -----------------------------------
float read_sonar_m(int idx);       // 0..4 = trai90 trai45 truoc phai45 phai90
bool  read_cliff(int idx);         // 0 = truoc, 1 = sau
float read_ir(int channel);        // 0 = kenh goi, 1 = kenh tram sac, tra 0..1
float read_battery();              // 0..1
float read_speed_mps();            // tu encoder, hoac uoc luong tu PWM
float read_yaw_rate();             // tu IMU, hoac (v_phai - v_trai)/wheel_base
bool  read_bump();                 // cong tac va cham, neu co
void  drive(float u_left, float u_right);   // -1..1 -> PWM 2 cap banh
// ---------------------------------------------------------------------------

static float clampf(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

void setup() {
    Serial.begin(115200);
    brain_reset(&brain);
}

void loop() {
    static uint32_t next = 0;
    uint32_t now = millis();
    if ((int32_t)(now - next) < 0) return;
    next = now + PERIOD_MS;

    for (int i = 0; i < 5; ++i)
        obs[i] = clampf(read_sonar_m(i) / SONAR_MAX_M, 0.0f, 1.0f);
    obs[5] = read_cliff(0) ? 1.0f : 0.0f;
    obs[6] = read_cliff(1) ? 1.0f : 0.0f;

    float ir_call = read_ir(0), ir_dock = read_ir(1);
    obs[7]  = ir_call;  obs[8]  = ir_call > 0.05f ? 1.0f : 0.0f;
    obs[9]  = ir_dock;  obs[10] = ir_dock > 0.05f ? 1.0f : 0.0f;
    obs[11] = clampf((ir_call - prev_ir[0]) * 8.0f, -1.0f, 1.0f);
    obs[12] = clampf((ir_dock - prev_ir[1]) * 8.0f, -1.0f, 1.0f);
    prev_ir[0] = ir_call; prev_ir[1] = ir_dock;

    float batt = read_battery();
    obs[13] = batt;
    obs[14] = batt < BATT_LOW ? 1.0f : 0.0f;
    obs[15] = clampf(read_speed_mps() / V_MAX, -1.0f, 1.0f);
    obs[16] = clampf(read_yaw_rate() / OMEGA_MAX, -1.0f, 1.0f);
    obs[17] = prev_u[0];
    obs[18] = prev_u[1];
    obs[19] = read_bump() ? 1.0f : 0.0f;

    float u[BRAIN_ACT];
    brain_step(&brain, obs, u);

    // LOP PHAN XA AN TOAN - luon thang bo nao
    float fwd = 0.5f * (u[0] + u[1]);
    if (obs[5] > 0.5f && fwd > 0.0f) { u[0] = u[1] = -0.7f; }
    if (obs[6] > 0.5f && fwd < 0.0f) { u[0] = u[1] = +0.6f; }

    drive(u[0], u[1]);
    prev_u[0] = u[0]; prev_u[1] = u[1];
}
