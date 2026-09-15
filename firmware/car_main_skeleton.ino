// Khung firmware ESP32 (Arduino core) - MOI CHI LA BO XUONG.
// Chua do dac phan cung that nen cac hang so o day chi la cho trong.
//
// Vong chay: LiDAR Camsense day goi lien tuc qua UART -> gom du MOT VONG ->
// chay dock_detect() -> dung mang obs[48] -> brain_step() -> PWM 2 cap banh.
#include "brain.h"
#include "dock_detect.h"

#define LIDAR_N     468           // so diem moi vong, phai chia het cho NSEC
#define NSEC        12            // so quat gop lai cho mang no-ron
#define SEC_CLIP    3.0f          // tam nhin dua vao mang (m)
#define V_MAX       0.60f
#define OMEGA_MAX   (2.0f * V_MAX / 0.15f)
#define BATT_LOW    0.40f
#define PERIOD_MS   50            // 20 Hz, dung bang dt trong mo phong
#define IR_HANDSHAKE_MS 1500      // con nho tin hieu IR bao lau thi cho phep sac

static brain_state_t brain;
static float obs[BRAIN_OBS];
static float scan[LIDAR_N], cos_a[LIDAR_N], sin_a[LIDAR_N];
static float prev_ir[2], prev_u[2];
static uint32_t last_ir_dock_ms;
static float odo_x, odo_y, odo_th;         // odometry tich luy tu encoder
static float mem_x, mem_y;                 // vi tri tram sac da nho
static bool  mem_known;
static float e_per_m = 0.045f;             // pin hao moi met - do duoc khi chay
static float trip_dist, trip_batt;

// --- cac ham nay se viet khi co phan cung -----------------------------------
bool  lidar_take_scan(float *dst, int n, float *scan_theta);  // true khi du 1 vong
bool  read_cliff(int idx);                 // 0 = truoc, 1 = sau
float read_ir(int channel);                // 0 = kenh goi, 1 = kenh tram sac
float read_battery();                      // 0..1
void  read_odometry(float *x, float *y, float *th, float *v, float *w);
bool  read_bump();
void  drive(float u_left, float u_right);  // -1..1 -> PWM 2 cap banh
// ---------------------------------------------------------------------------

static float clampf(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

static void fill_sectors(float scan_theta, float theta_now)
{
    const int per = LIDAR_N / NSEC;
    for (int s = 0; s < NSEC; ++s) obs[s] = 1.0f;
    // bu phan xe da quay ke tu luc bat dau vong quet (de-skew)
    float d = scan_theta - theta_now;
    while (d < 0) d += 2.0f * (float)M_PI;
    int shift = (int)(d / (2.0f * (float)M_PI) * LIDAR_N + 0.5f) % LIDAR_N;
    for (int i = 0; i < LIDAR_N; ++i) {
        float r = scan[i];
        if (r <= 0.0f) continue;                  // khong phan hoi = trong
        int j = (i + shift) % LIDAR_N;
        int s = j / per;
        float v = clampf(r / SEC_CLIP, 0.0f, 1.0f);
        if (v < obs[s]) obs[s] = v;
    }
}

void setup() {
    Serial.begin(115200);
    brain_reset(&brain);
    for (int i = 0; i < LIDAR_N; ++i) {
        float a = -(float)M_PI + 2.0f * (float)M_PI * i / LIDAR_N;
        cos_a[i] = cosf(a);
        sin_a[i] = sinf(a);
    }
}

void loop() {
    static uint32_t next = 0;
    static dock_cand_t cand[DOCK_MAX_CAND];
    static int ncand = 0;
    static float scan_theta = 0.0f;

    uint32_t now = millis();
    if ((int32_t)(now - next) < 0) return;
    next = now + PERIOD_MS;

    float px = odo_x, py = odo_y, v, w;
    read_odometry(&odo_x, &odo_y, &odo_th, &v, &w);
    float moved = hypotf(odo_x - px, odo_y - py);

    // 1) LiDAR: chi xu ly khi da gom du mot vong (~143 ms o 7 Hz)
    if (lidar_take_scan(scan, LIDAR_N, &scan_theta)) {
        ncand = dock_detect(scan, cos_a, sin_a, LIDAR_N,
                            scan_theta - odo_th, cand);
    }
    fill_sectors(scan_theta, odo_th);

    obs[12] = read_cliff(0) ? 1.0f : 0.0f;
    obs[13] = read_cliff(1) ? 1.0f : 0.0f;
    for (int i = 0; i < DOCK_MAX_CAND; ++i) {
        int b = 14 + 4 * i;
        if (i < ncand) {
            obs[b]     = 1.0f;
            obs[b + 1] = sinf(cand[i].bearing);
            obs[b + 2] = cosf(cand[i].bearing);
            obs[b + 3] = clampf(cand[i].dist / SEC_CLIP, 0.0f, 1.0f);
        } else {
            obs[b] = obs[b + 1] = obs[b + 2] = 0.0f;
            obs[b + 3] = 1.0f;
        }
    }

    float ir_call = read_ir(0), ir_dock = read_ir(1);
    obs[22] = ir_call;  obs[23] = ir_call > 0.05f ? 1.0f : 0.0f;
    obs[24] = ir_dock;  obs[25] = ir_dock > 0.05f ? 1.0f : 0.0f;
    obs[26] = clampf((ir_call - prev_ir[0]) * 8.0f, -1.0f, 1.0f);
    obs[27] = clampf((ir_dock - prev_ir[1]) * 8.0f, -1.0f, 1.0f);
    prev_ir[0] = ir_call; prev_ir[1] = ir_dock;

    // 2) Hong ngoai xac nhan tram sac -> ghi lai vi tri theo odometry
    if (obs[25] > 0.5f) {
        last_ir_dock_ms = now;
        for (int i = 0; i < ncand; ++i) {
            if (fabsf(cand[i].bearing) < 0.45f) {
                float a = odo_th + cand[i].bearing;
                mem_x = odo_x + cand[i].dist * cosf(a);
                mem_y = odo_y + cand[i].dist * sinf(a);
                mem_known = true;
                break;
            }
        }
    }
    float mem_d = 0.0f, mem_b = 0.0f;
    if (mem_known) {
        mem_d = hypotf(mem_x - odo_x, mem_y - odo_y);
        mem_b = atan2f(mem_y - odo_y, mem_x - odo_x) - odo_th;
        while (mem_b > (float)M_PI)  mem_b -= 2.0f * (float)M_PI;
        while (mem_b < -(float)M_PI) mem_b += 2.0f * (float)M_PI;
    }
    obs[28] = mem_known ? 1.0f : 0.0f;
    obs[29] = mem_known ? sinf(mem_b) : 0.0f;
    obs[30] = mem_known ? cosf(mem_b) : 0.0f;
    obs[31] = mem_known ? clampf(mem_d / SEC_CLIP, 0.0f, 1.0f) : 1.0f;

    // 3) Pin va "kinh nghiem": do xem chay mot met ton bao nhieu pin
    float batt = read_battery();
    trip_dist += moved;
    trip_batt += fmaxf(0.0f, prev_u[0] == 0 ? 0.0f : 0.0f);   // xem ghi chu duoi
    if (trip_dist > 0.5f) {
        float e = trip_batt / trip_dist;
        e_per_m = 0.9f * e_per_m + 0.1f * e;
    }
    float need = mem_known ? (e_per_m * mem_d * 1.5f + 0.06f) : 0.25f;
    obs[32] = batt;
    obs[33] = batt < BATT_LOW ? 1.0f : 0.0f;
    obs[34] = clampf(batt - need, -1.0f, 1.0f);

    obs[35] = clampf(v / V_MAX, -1.0f, 1.0f);
    obs[36] = clampf(w / OMEGA_MAX, -1.0f, 1.0f);
    obs[37] = prev_u[0];
    obs[38] = prev_u[1];
    obs[39] = read_bump() ? 1.0f : 0.0f;

    float u[BRAIN_ACT];
    brain_step(&brain, obs, u);

    // 4) LOP PHAN XA AN TOAN - luon thang bo nao
    float fwd = 0.5f * (u[0] + u[1]);
    if (obs[12] > 0.5f && fwd > 0.0f) { u[0] = u[1] = -0.7f; }
    if (obs[13] > 0.5f && fwd < 0.0f) { u[0] = u[1] = +0.6f; }

    drive(u[0], u[1]);
    prev_u[0] = u[0]; prev_u[1] = u[1];

    // Ghi chu: trip_batt phai cong don phan pin TUT DI moi chu ky
    // (batt_truoc - batt_sau, bo qua luc dang sac). Giu bien batt_prev rieng
    // khi viet that - o day de trong cho khoi doan nham la da xong.
}
