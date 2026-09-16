// ESP32: doc cam bien, day len laptop qua wifi, nhan lai lenh ga.
// Bo nao chay tren laptop (link/brain_server.py). Day la che do "nao tu xa".
//
// Che do con lai - bo nao chay ngay tren ESP32 - nam o car_main_skeleton.ino.
// Giu ca hai: khi wifi chet ma van muon xe ve duoc tram sac thi can no.
//
// Dinh dang goi PHAI khop link/protocol.py. Khong dung struct de gui thang
// ma ghi tung byte: struct cua C co the them byte chen giua cac truong tuy
// trinh dich, va loi do chi lo ra khi chay that.
#include <WiFi.h>
#include <WiFiUdp.h>
#include <math.h>
#include <string.h>

// ------------------------------------------------------------------ cau hinh
static const char *WIFI_SSID = "TEN_WIFI";
static const char *WIFI_PASS = "MAT_KHAU";
static const char *BRAIN_IP  = "192.168.1.100";   // dia chi laptop
static const uint16_t BRAIN_PORT = 4210;

#define LIDAR_N       432      // so diem moi vong, phai khop ben Python
#define CTRL_HZ       20
#define CMD_TIMEOUT_MS 150     // mat lenh lau hon ngan nay -> dung banh
#define REFLEX_BACK   0.6f     // ga lui khi cam bien vuc keu
#define V_MAX         0.50f
#define OMEGA_MAX     (2.0f * V_MAX / 0.240f)

#include "link_pack.h"     // dong goi/mo goi - da doi chieu voi Python bang may

// --------------------------------------------- ham phan cung (tu viet lay)
void  motors(float u_left, float u_right);   // [-1,1] -> PWM 2 cap banh
bool  read_cliff(int idx);                   // 0 = truoc, 1 = sau
float read_ir(int channel);                  // 0 = goi, 1 = tram sac
float read_battery(void);                    // 0..1
bool  read_bump(void);
// Dien ap tren tiep diem sac. Chi can biet CO CHAM hay khong, khong can biet
// co dong dien - dong dien la chuyen cua bat tay hong ngoai.
bool  read_dock_contact(void);
void  read_odometry(float *x, float *y, float *th, float *v, float *w);
// Tra ve true khi vua gom du MOT VONG quet. scan[i] la khoang cach (m) o goc
// -pi + 2*pi*i/LIDAR_N; 0 = khong co tia ve. *theta la goc ODOMETRY cua xe
// luc bat dau vong quet - KHONG phai goc that, va khong phai goc hien tai:
// lay hieu hai so cung he thi phan troi odometry tu triet tieu.
bool  lidar_take_scan(float *scan, int n, float *theta);

// ------------------------------------------------------------------- goi tin
static WiFiUDP udp;
static uint8_t txbuf[LINK_SCAN_SIZE(LIDAR_N)];
static uint8_t rxbuf[256];
static float scan[LIDAR_N];
static uint32_t seq = 0;
static uint32_t last_cmd_ms = 0;
static float u_cmd[2] = {0.0f, 0.0f};      // ga bo nao yeu cau
static float u_applied[2] = {0.0f, 0.0f};  // ga THUC SU da vao dong co
static uint8_t sticky_flags = 0;

static void send_state(void)
{
    link_state_t st;
    read_odometry(&st.x, &st.y, &st.th, &st.v, &st.w);
    st.battery = read_battery();
    st.ir_call = read_ir(0);
    st.ir_dock = read_ir(1);
    st.u_applied_l = u_applied[0];
    st.u_applied_r = u_applied[1];
    st.flags = sticky_flags;
    if (read_cliff(0)) st.flags |= LINK_F_CLIFF_F;
    if (read_cliff(1)) st.flags |= LINK_F_CLIFF_R;
    if (read_bump())   st.flags |= LINK_F_BUMP;
    if (read_dock_contact()) st.flags |= LINK_F_ON_DOCK;
    sticky_flags = 0;

    int n = link_pack_state(txbuf, ++seq, millis(), &st);
    udp.beginPacket(BRAIN_IP, BRAIN_PORT);
    udp.write(txbuf, n);
    udp.endPacket();
}

static void send_scan(float theta)
{
    int n = link_pack_scan(txbuf, seq, millis(), scan, LIDAR_N,
                           theta, millis());
    udp.beginPacket(BRAIN_IP, BRAIN_PORT);
    udp.write(txbuf, n);
    udp.endPacket();
}

static void poll_cmd(void)
{
    while (udp.parsePacket() > 0) {
        int len = udp.read(rxbuf, sizeof(rxbuf));
        // Bo qua lenh tra loi cho goi cam bien CU: chay theo no con te hon
        // la dung yen, vi the gioi da khac di roi.
        if (link_parse_cmd(rxbuf, len, seq, &u_cmd[0], &u_cmd[1], NULL, NULL))
            last_cmd_ms = millis();
    }
}

// Phan xa an toan. CHAY TREN ESP32, khong hoi bo nao.
// Tu luc cam bien vuc keu den luc tam xe qua mep chi ~290 ms; tru 120 ms
// quang duong phanh con 170 ms. Mot cu nghen wifi an het chung do.
static void apply_with_reflex(void)
{
    float ul = u_cmd[0], ur = u_cmd[1];
    if (millis() - last_cmd_ms > CMD_TIMEOUT_MS) {   // watchdog
        ul = ur = 0.0f;
    }
    if (read_cliff(0) && (ul + ur) > 0.0f) {
        ul = ur = -REFLEX_BACK;
        sticky_flags |= LINK_F_REFLEX;
    } else if (read_cliff(1) && (ul + ur) < 0.0f) {
        ul = ur = REFLEX_BACK;
        sticky_flags |= LINK_F_REFLEX;
    }
    u_applied[0] = ul;
    u_applied[1] = ur;
    motors(ul, ur);
}

void setup(void)
{
    Serial.begin(115200);
    motors(0.0f, 0.0f);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    WiFi.setSleep(false);          // ngu tiet kiem dien = tre them 100+ ms
    while (WiFi.status() != WL_CONNECTED) { delay(200); Serial.print("."); }
    Serial.printf("\nwifi ok, ip %s\n", WiFi.localIP().toString().c_str());
    udp.begin(BRAIN_PORT);
    last_cmd_ms = millis();
}

void loop(void)
{
    static uint32_t next = 0;
    float theta;
    if (lidar_take_scan(scan, LIDAR_N, &theta)) send_scan(theta);

    uint32_t now = millis();
    if ((int32_t)(now - next) < 0) { poll_cmd(); return; }
    next = now + 1000 / CTRL_HZ;

    send_state();
    // Doi lenh tra loi trong nua chu ky. Het thi gio thi chay tiep voi lenh
    // cu; watchdog o tren se cat neu lau qua.
    uint32_t deadline = now + (1000 / CTRL_HZ) / 2;
    while ((int32_t)(millis() - deadline) < 0) {
        poll_cmd();
        if (last_cmd_ms >= now) break;
    }
    apply_with_reflex();

    if (WiFi.status() != WL_CONNECTED) {     // mat wifi han: dung, roi noi lai
        motors(0.0f, 0.0f);
        WiFi.reconnect();
    }
}
