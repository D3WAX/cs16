#!/usr/bin/env python3
"""client_aim: silent aim murni di client (tanpa DLL server). Buat latihan red team di server tim sendiri.
Jalankan dari root repo:  python3 scripts/install_client_aim.py   (aman dijalankan 2x)

Console:
  ca_on 0/1      nyalain; hanya aktif saat tombol tembak ditekan
  ca_fov <der>   radius FOV dalam derajat (default 8)
  ca_team 0/1    1 = teman satu tim juga jadi target
Kamera lo tidak bergerak: hanya cmd->viewangles yang dikirim ke server yang diubah.
"""
import os, re, sys

NEW = "cl_dll/client_aim.cpp"
INPUT = "cl_dll/input.cpp"
HUD = "cl_dll/hud.cpp"

CPP = r'''// client_aim: client-side silent aim (cmd->viewangles only; the camera is untouched)
#include "hud.h"
#include "cl_util.h"
#include "event_api.h"
#include "pm_defs.h"
#include "pmtrace.h"
#include "usercmd.h"
#include <math.h>

extern vec3_t v_origin;
extern vec3_t ev_punchangle;
bool CL_IsDead( void );

static cvar_t *ca_on = NULL, *ca_fov = NULL, *ca_team = NULL;

void ClientAim_Init( void )
{
	ca_on   = CVAR_CREATE( "ca_on", "0", 0 );
	ca_fov  = CVAR_CREATE( "ca_fov", "8", FCVAR_ARCHIVE );
	ca_team = CVAR_CREATE( "ca_team", "0", 0 );
}

static float NormYaw( float a )
{
	while( a > 180.0f ) a -= 360.0f;
	while( a < -180.0f ) a += 360.0f;
	return a;
}

static void AnglesTo( const float *from, const float *to, float *out )
{
	float d[3] = { to[0] - from[0], to[1] - from[1], to[2] - from[2] };
	float hyp = sqrtf( d[0] * d[0] + d[1] * d[1] );
	out[0] = -atan2f( d[2], hyp ) * 180.0f / (float)M_PI; // GoldSrc: +pitch = down
	out[1] = atan2f( d[1], d[0] ) * 180.0f / (float)M_PI;
	out[2] = 0.0f;
}

static bool Visible( const float *eye, const float *pt, int targetIndex )
{
	cl_entity_t *local = gEngfuncs.GetLocalPlayer();
	pmtrace_t tr;

	gEngfuncs.pEventAPI->EV_SetUpPlayerPrediction( false, true );
	gEngfuncs.pEventAPI->EV_PushPMStates();
	gEngfuncs.pEventAPI->EV_SetSolidPlayers( local->index - 1 );
	gEngfuncs.pEventAPI->EV_SetTraceHull( 2 );
	gEngfuncs.pEventAPI->EV_PlayerTrace( (float *)eye, (float *)pt, PM_STUDIO_BOX, -1, &tr );
	gEngfuncs.pEventAPI->EV_PopPMStates();

	if( tr.fraction >= 1.0f )
		return true;
	if( tr.ent > 0 )
	{
		physent_t *pe = gEngfuncs.pEventAPI->EV_GetPhysent( tr.ent );
		if( pe && pe->info == targetIndex )
			return true;
	}
	return false;
}

void ClientAim_Apply( struct usercmd_s *cmd, const float *viewangles )
{
	if( !ca_on || ca_on->value == 0.0f || !( cmd->buttons & IN_ATTACK ) || CL_IsDead() )
		return;

	cl_entity_t *local = gEngfuncs.GetLocalPlayer();
	if( !local )
		return;

	const int myTeam = g_PlayerExtraInfo[local->index].teamnumber;
	const float maxFov = ca_fov ? ca_fov->value : 8.0f;
	float bestFov = maxFov, bestAng[3] = { 0, 0, 0 };
	bool found = false;

	for( int i = 1; i <= gEngfuncs.GetMaxClients() && i <= MAX_PLAYERS; i++ )
	{
		cl_entity_t *ent = gEngfuncs.GetEntityByIndex( i );
		if( !ent || !ent->model || i == local->index )
			continue;
		if( ent->curstate.spectator || g_PlayerExtraInfo[i].dead )
			continue;
		if( ca_team->value == 0.0f && g_PlayerExtraInfo[i].teamnumber == myTeam )
			continue;

		float head[3] = { ent->origin[0], ent->origin[1], ent->origin[2] + ( ent->curstate.usehull ? 8.0f : 17.0f ) };
		float ang[3];
		AnglesTo( v_origin, head, ang );

		float dp = NormYaw( ang[0] - viewangles[0] );
		float dy = NormYaw( ang[1] - viewangles[1] );
		float fov = sqrtf( dp * dp + dy * dy );
		if( fov >= bestFov || !Visible( v_origin, head, i ) )
			continue;

		bestFov = fov;
		bestAng[0] = ang[0];
		bestAng[1] = ang[1];
		found = true;
	}

	if( !found )
		return;

	// server aims along (v_angle + punchangle), so subtract punch => also cancels recoil on the aim line
	float oldYaw = cmd->viewangles[1];
	cmd->viewangles[0] = bestAng[0] - ev_punchangle[0];
	cmd->viewangles[1] = bestAng[1] - ev_punchangle[1];

	// keep the movement direction the same relative to the real camera
	float d = ( oldYaw - cmd->viewangles[1] ) * (float)M_PI / 180.0f;
	float fm = cmd->forwardmove, sm = cmd->sidemove;
	cmd->forwardmove = fm * cosf( d ) + sm * sinf( d );
	cmd->sidemove    = -fm * sinf( d ) + sm * cosf( d );
}
'''

def read(p):
    with open(p, encoding="utf-8", newline="") as f: return f.read()
def write(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f: f.write(s)

def main():
    for p in (INPUT, HUD):
        if not os.path.exists(p):
            sys.exit("jalankan dari root repo (nggak nemu %s)" % p)

    write(NEW, CPP)
    print("[ok] %s ditulis" % NEW)

    s = read(INPUT)
    if "ClientAim_Apply" not in s:
        anchor = "\t\tVectorCopy( viewangles, cmd->viewangles );\r\n\t\tVectorCopy( viewangles, oldangles );" if "\r\n" in s else \
                 "\t\tVectorCopy( viewangles, cmd->viewangles );\n\t\tVectorCopy( viewangles, oldangles );"
        if anchor not in s:
            sys.exit("anchor CL_CreateMove nggak ketemu di input.cpp")
        nl = "\r\n" if "\r\n" in s else "\n"
        s = s.replace(anchor, anchor + nl + "\t\tClientAim_Apply( cmd, viewangles );", 1)
        decl = "void ClientAim_Apply( struct usercmd_s *cmd, const float *viewangles );" + nl
        s = s.replace("void DLLEXPORT CL_CreateMove (", decl + "void DLLEXPORT CL_CreateMove (", 1)
        write(INPUT, s)
        print("[ok] hook CL_CreateMove dipasang")
    else:
        print("[skip] input.cpp sudah ke-patch")

    h = read(HUD)
    if "ClientAim_Init" not in h:
        nl = "\r\n" if "\r\n" in h else "\n"
        # panggil ClientAim_Init() tepat setelah cvar "_ah" dibuat di CHud::Init (ada di semua varian repo ini)
        m = re.search(r'^([ \t]*)CVAR_CREATE\(\s*"_ah"[^\n]*\n', h, re.M)
        if not m:
            sys.exit("anchor CVAR_CREATE(\"_ah\") nggak ketemu di hud.cpp -- patch dibatalkan")
        h = h[:m.end()] + m.group(1) + "ClientAim_Init();" + nl + h[m.end():]
        m2 = re.search(r'^void CHud\s*::\s*Init\s*\(', h, re.M)
        if not m2:
            sys.exit("CHud::Init nggak ketemu di hud.cpp -- patch dibatalkan")
        h = h[:m2.start()] + "void ClientAim_Init( void );" + nl + h[m2.start():]
        write(HUD, h)
        print("[ok] cvar init dipasang")
    else:
        print("[skip] hud.cpp sudah ke-patch")

    # verifikasi: kalau salah satu nggak ada, build harus gagal (jangan diam-diam)
    for path, needle in ((INPUT, "ClientAim_Apply( cmd, viewangles )"), (HUD, "ClientAim_Init();")):
        if needle not in read(path):
            sys.exit("VERIFIKASI GAGAL: %s tidak berisi %s" % (path, needle))
    print("[ok] verifikasi lolos")

if __name__ == "__main__":
    main()
																		 
