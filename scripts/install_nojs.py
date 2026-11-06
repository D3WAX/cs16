#!/usr/bin/env python3
"""nojs: auto-bhop client-side supaya slowdown pendaratan (friction) sebisa mungkin hilang.
Jalankan dari root repo:  python3 scripts/install_nojs.py   (aman dijalankan berkali-kali)

Console:
  nojs 0/1       nyalain/matiin. Cara pakai: TAHAN tombol lompat, auto-hop jalan sendiri.
  nojs_debug 0/1 print status nojs_air ke console tiap 0,25 dtk (speed, theta, fm/sm)
  nojs_air 0/1   easy air movement + autostrafe optimal. Di udara dengan tombol lompat ditahan, arah gerak
                 (velocity) otomatis diputar MENUJU arah pandang kamera. Muter kamera = arah lari ikut muter,
                 sambil nambah speed pada sudut optimal acos((30 - accel)/speed). Kamera lo nggak diubah.
                 Aktif kalau speed horizontal > ~50.

Cara kerja: tiap tick player dikirim IN_JUMP hanya saat menyentuh tanah (lompat di frame pertama
mendarat, sebelum friction sempat makan speed) dan IN_JUMP dilepas selama di udara (CS butuh tombol
dilepas antar lompatan). Status onground diambil dari prediksi pmove client.

BATAS: slowdown yang dihitung server (cap speed bhop, penalti jatuh) tetap berlaku dan tidak bisa
dihapus dari client. Ini cuma menghilangkan kehilangan speed karena telat lompat saat mendarat.
"""
import os, re, sys

NEW = "cl_dll/nojs.cpp"
INPUT = "cl_dll/input.cpp"
CDLL = "cl_dll/cdll_int.cpp"
HUD = "cl_dll/hud.cpp"

CPP = r'''// nojs: client-side auto-bhop (IN_JUMP hanya saat onground)
#include "hud.h"
#include "cl_util.h"
#include "usercmd.h"
#include "in_buttons.h"
#include "pm_defs.h"
#include "pm_movevars.h"
#include "const.h"
#include <math.h>

static cvar_t *nojs = NULL, *nojs_air = NULL, *nojs_debug = NULL;
static int g_onGround = 1;
static int g_skip = 0;            // air/ladder: jangan sentuh tombol lompat
static float g_vel[2] = { 0, 0 }; // velocity horizontal dari prediksi pmove
static float g_speed = 0.0f;
static float g_airAccel = 10.0f;  // sv_airaccelerate (CS default 10)
static float g_maxSpeed = 250.0f;
static float g_frametime = 0.01f; // frametime cmd terakhir yang diprediksi
static float g_lastYaw = 0.0f;
static float g_dir = 0.0f;        // sisi belok yang "nempel": +1 kiri, -1 kanan, 0 belum ada

void NoJS_Init( void )
{
	nojs = CVAR_CREATE( "nojs", "0", 0 );
	nojs_air = CVAR_CREATE( "nojs_air", "0", 0 );
	nojs_debug = CVAR_CREATE( "nojs_debug", "0", 0 );
}

static float NormYaw( float a )
{
	while( a > 180.0f ) a -= 360.0f;
	while( a < -180.0f ) a += 360.0f;
	return a;
}

// dipanggil setelah prediksi pmove client
void NoJS_SavePM( struct playermove_s *pm )
{
	if( !pm )
		return;
	g_onGround = ( pm->onground != -1 );
	g_skip = ( pm->waterlevel >= 2 || pm->movetype == MOVETYPE_FLY || pm->dead );
	g_vel[0] = pm->velocity[0];
	g_vel[1] = pm->velocity[1];
	g_speed = sqrtf( g_vel[0] * g_vel[0] + g_vel[1] * g_vel[1] );
	if( pm->movevars && pm->movevars->airaccelerate > 0.0f )
		g_airAccel = pm->movevars->airaccelerate;
	if( pm->maxspeed > 1.0f )
		g_maxSpeed = pm->maxspeed;
	if( pm->frametime > 0.001f && pm->frametime < 0.1f )
		g_frametime = pm->frametime;
}

// dipanggil dari CL_CreateMove (player hidup)
void NoJS_Apply( struct usercmd_s *cmd )
{
	// selisih yaw mouse sejak tick lalu (+ = belok kiri). Selalu diupdate biar nggak lompat nilainya.
	float va[3];
	gEngfuncs.GetViewAngles( va );
	const float dyaw = NormYaw( va[1] - g_lastYaw );
	g_lastYaw = va[1];

	if( !nojs || nojs->value == 0.0f || g_skip )
		return;
	if( !( cmd->buttons & IN_JUMP ) ) // hanya kalau player menahan tombol lompat
	{
		g_dir = 0.0f;
		return;
	}

	if( g_onGround )
	{
		cmd->buttons |= IN_JUMP;
		g_dir = 0.0f; // sisi belok di-reset tiap mendarat
		return;
	}

	// lepas tombol lompat di udara (CS butuh tombol dilepas antar lompatan)
	cmd->buttons &= ~IN_JUMP;

	if( !nojs_air || nojs_air->value == 0.0f || g_speed < 50.0f )
		return;

	// arah velocity sekarang dan selisihnya terhadap arah pandang. Velocity diputar MENUJU arah pandang:
	// pandangan di kiri velocity -> dorong ke kiri (dir=+1), di kanan -> dorong ke kanan (dir=-1).
	// Begitu velocity sejajar pandangan, dorongan selang-seling kiri/kanan di sekitar arah pandang
	// (tetap nambah speed, tapi arah gerak nempel ke kamera dan nggak muter sendiri).
	const float velYaw = atan2f( g_vel[1], g_vel[0] ) * 180.0f / (float)M_PI;
	const float diff = NormYaw( va[1] - velYaw );
	g_dir = ( diff >= 0.0f ) ? 1.0f : -1.0f;

	// sudut optimal antara velocity dan arah dorongan (GoldSrc PM_AirAccelerate: wishspd dibatasi 30,
	// accelspeed = airaccel * maxspeed * frametime) -> cos(theta) = (30 - accelspeed) / speed
	// c dibatasi [0,1] supaya arah dorongan nggak pernah lewat tegak lurus (nggak mungkin ngerem).
	const float accelspeed = g_airAccel * g_maxSpeed * g_frametime;
	float c = ( 30.0f - accelspeed ) / g_speed;
	if( c > 1.0f ) c = 1.0f;
	if( c < 0.0f ) c = 0.0f;
	const float theta = acosf( c ) * 180.0f / (float)M_PI;

	// arah dorongan (world yaw) = arah velocity digeser theta ke sisi belok
	const float wishYaw = velYaw + g_dir * theta;

	// proyeksikan ke sumbu forward/right dari view yaw saat ini (kamera nggak diubah)
	const float rad = NormYaw( wishYaw - va[1] ) * (float)M_PI / 180.0f;
	cmd->forwardmove = 400.0f * cosf( rad );
	cmd->sidemove = -400.0f * sinf( rad );

	if( nojs_debug && nojs_debug->value != 0.0f )
	{
		static float nextPrint = 0.0f;
		const float now = gEngfuncs.GetClientTime();
		if( now >= nextPrint )
		{
			nextPrint = now + 0.25f;
			gEngfuncs.Con_Printf( "[js] air speed=%.0f view-vel=%.1f dir=%.0f theta=%.1f ft=%.4f accel=%.0f max=%.0f fm=%.0f sm=%.0f\n",
				g_speed, diff, g_dir, theta, g_frametime, g_airAccel, g_maxSpeed, cmd->forwardmove, cmd->sidemove );
		}
	}
}
'''

def read(p):
    with open(p, encoding="utf-8", newline="") as f: return f.read()
def write(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f: f.write(s)
def nl_of(s): return "\r\n" if "\r\n" in s else "\n"
def die(msg): sys.exit("GAGAL: " + msg)

def main():
    for p in (INPUT, CDLL, HUD):
        if not os.path.exists(p):
            die("jalankan dari root repo (nggak nemu %s)" % p)

    write(NEW, CPP)
    print("[ok] %s ditulis" % NEW)

    # --- input.cpp: panggil NoJS_Apply di CL_CreateMove (cabang player hidup)
    s = read(INPUT)
    if "NoJS_Apply" not in s:
        nl = nl_of(s)
        a = "\t\tVectorCopy( viewangles, cmd->viewangles );"
        if s.count(a) != 1: die("anchor VectorCopy(viewangles, cmd->viewangles) tidak unik/ketemu di input.cpp")
        s = s.replace(a, "\t\tNoJS_Apply( cmd );" + nl + a, 1)
        m = re.search(r"^void DLLEXPORT CL_CreateMove\s*\(", s, re.M)
        if not m: die("CL_CreateMove nggak ketemu di input.cpp")
        s = s[:m.start()] + "void NoJS_Apply( struct usercmd_s *cmd );" + nl + s[m.start():]
        write(INPUT, s)
        print("[ok] hook CL_CreateMove dipasang")
    else:
        print("[skip] input.cpp sudah ke-patch")

    # --- cdll_int.cpp: simpan state pmove setelah prediksi
    c = read(CDLL)
    if "NoJS_SavePM" not in c:
        nl = nl_of(c)
        a = "\tPM_Move( ppmove, server );"
        if c.count(a) != 1: die("anchor PM_Move(ppmove, server) tidak unik/ketemu di cdll_int.cpp")
        c = c.replace(a, a + nl + "\tif( !server )" + nl + "\t\tNoJS_SavePM( ppmove );", 1)
        m = re.search(r"^void DLLEXPORT HUD_PlayerMove\s*\(", c, re.M)
        if not m: die("HUD_PlayerMove nggak ketemu di cdll_int.cpp")
        c = c[:m.start()] + "void NoJS_SavePM( struct playermove_s *pm );" + nl + c[m.start():]
        write(CDLL, c)
        print("[ok] hook HUD_PlayerMove dipasang")
    else:
        print("[skip] cdll_int.cpp sudah ke-patch")

    # --- hud.cpp: registrasi cvar
    h = read(HUD)
    if "NoJS_Init" not in h:
        nl = nl_of(h)
        m = re.search(r'^([ \t]*)CVAR_CREATE\(\s*"_ah"[^\n]*\n', h, re.M)
        if not m: die('anchor CVAR_CREATE("_ah") nggak ketemu di hud.cpp')
        h = h[:m.end()] + m.group(1) + "NoJS_Init();" + nl + h[m.end():]
        m2 = re.search(r'^void CHud\s*::\s*Init\s*\(', h, re.M)
        if not m2: die("CHud::Init nggak ketemu di hud.cpp")
        h = h[:m2.start()] + "void NoJS_Init( void );" + nl + h[m2.start():]
        write(HUD, h)
        print("[ok] cvar init dipasang")
    else:
        print("[skip] hud.cpp sudah ke-patch")

    for path, needle in ((INPUT, "NoJS_Apply( cmd );"), (CDLL, "NoJS_SavePM( ppmove );"), (HUD, "NoJS_Init();")):
        if needle not in read(path):
            die("VERIFIKASI: %s tidak berisi %s" % (path, needle))
    print("[ok] verifikasi lolos")

if __name__ == "__main__":
    main()
	
