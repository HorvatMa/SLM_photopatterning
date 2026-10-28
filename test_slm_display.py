# -*- coding: utf-8 -*-
"""
Checks that the SLM image is displayed right on this PC (run it once on every new PC).

Part 1 - Display setup: the SLM monitor exists, has the right resolution, 32-bit color,
         100% scaling and an untouched (identity) gamma table.
Part 2 - Pixel check: shows a test pattern with all 1024 SLM values and a 1-pixel checkerboard
         on the SLM, takes a screenshot of the SLM monitor and compares it pixel by pixel with
         what was sent. Catches the wrong monitor, scaling/stretching, mirroring and color changes
         made by Windows.
Part 3 - Optical check (optional, needs the camera, laser on and the same optics as the calibration):
         shows uniform values on the SLM, measures the polarization angle with the camera and
         compares it with an existing calibration file. This is the only part that also sees
         what happens after the graphics card (e.g. "Limited RGB range 16-235" over HDMI, which a
         screenshot can not see).

Usage:
    python test_slm_display.py                                   # parts 1 and 2
    python test_slm_display.py --camera 9_6_2025_info.npz        # parts 1, 2 and 3
    python test_slm_display.py --camera 9_6_2025_info.npz --exposure 5e5 --levels 24

The calibration file is looked up in CALIBRATION_FOLDER (paths.py) if it is not a full path.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time
from pathlib import Path

import numpy as np

# Screenshots and display sizes must be in real pixels, so make the process DPI aware
# before any window (wx, tk, matplotlib) is created.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI aware
except Exception:
    pass

from PIL import ImageGrab

import polarimetry as stks
from Calibration import SLMcalibration
from paths import CALIBRATION_FOLDER, find_calibration_dat

SLM_MONITOR = 1          # slmpy opens the SLM window on monitor 1 (the second one)
SLM_RES = (1920, 1200)   # (width, height) of the SLM

results = []  # (name, passed, message)
TAGS = {True: 'PASS', False: 'FAIL', None: 'WARN'}


def report(name, passed, message=''):
    results.append((name, passed, message))
    print(f'[{TAGS[passed]}] {name}' + (f': {message}' if message else ''))


def bits_from_rgb(rgb):
    '''Inverse of SLMcalibration.convert_to_RGB.'''
    rgb = rgb.astype(int)
    return (rgb[..., 0] // 32) * 128 + (rgb[..., 1] // 32) * 16 + rgb[..., 2] // 16


######################## PART 1: DISPLAY SETUP ########################

class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('rcMonitor', wt.RECT), ('rcWork', wt.RECT),
                ('dwFlags', wt.DWORD), ('szDevice', wt.WCHAR * 32)]


class DEVMODEW(ctypes.Structure):
    _fields_ = [('dmDeviceName', wt.WCHAR * 32), ('dmSpecVersion', wt.WORD), ('dmDriverVersion', wt.WORD),
                ('dmSize', wt.WORD), ('dmDriverExtra', wt.WORD), ('dmFields', wt.DWORD),
                ('dmPositionX', wt.LONG), ('dmPositionY', wt.LONG), ('dmDisplayOrientation', wt.DWORD),
                ('dmDisplayFixedOutput', wt.DWORD), ('dmColor', ctypes.c_short), ('dmDuplex', ctypes.c_short),
                ('dmYResolution', ctypes.c_short), ('dmTTOption', ctypes.c_short), ('dmCollate', ctypes.c_short),
                ('dmFormName', wt.WCHAR * 32), ('dmLogPixels', wt.WORD), ('dmBitsPerPel', wt.DWORD),
                ('dmPelsWidth', wt.DWORD), ('dmPelsHeight', wt.DWORD), ('dmDisplayFlags', wt.DWORD),
                ('dmDisplayFrequency', wt.DWORD), ('dmICMMethod', wt.DWORD), ('dmICMIntent', wt.DWORD),
                ('dmMediaType', wt.DWORD), ('dmDitherType', wt.DWORD), ('dmReserved1', wt.DWORD),
                ('dmReserved2', wt.DWORD), ('dmPanningWidth', wt.DWORD), ('dmPanningHeight', wt.DWORD)]


def list_monitors():
    '''Monitors in the order Windows enumerates them (the same order wx.Display, and so slmpy, uses).'''
    user32 = ctypes.windll.user32
    monitors = []
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_int, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)

    def callback(hmon, hdc, rect, data):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        r = info.rcMonitor
        monitors.append((hmon, info.szDevice, (r.left, r.top, r.right - r.left, r.bottom - r.top), bool(info.dwFlags & 1)))
        return 1

    user32.EnumDisplayMonitors(None, None, proc_type(callback), 0)
    return monitors


def check_display_setup():
    '''Returns the (x0, y0, w, h) of the SLM monitor or None if the test can not continue.'''
    print('\n===== Part 1: display setup =====')
    monitors = list_monitors()
    for i, (_, device, (x, y, w, h), primary) in enumerate(monitors):
        print(f'  monitor {i}: {w} x {h} at ({x}, {y}) {device}' + ('  (primary)' if primary else ''))
    if len(monitors) <= SLM_MONITOR:
        report('SLM connected as a second monitor', False,
               f'only {len(monitors)} monitor(s) found. Connect the SLM and set Windows to "Extend these displays".')
        return None
    report('SLM connected as a second monitor', True)

    hmon, device, geometry, primary = monitors[SLM_MONITOR]
    w, h = geometry[2:]
    if primary:
        report('SLM is not the primary monitor', None, 'monitor 1 is the primary one -> is the SLM really monitor 1?')
    report('SLM resolution', (w, h) == SLM_RES, f'{w} x {h}, expected {SLM_RES[0]} x {SLM_RES[1]}')
    user32 = ctypes.windll.user32

    # Windows scaling must be 100% (96 dpi), otherwise Windows stretches the image
    dpi_x, dpi_y = wt.UINT(), wt.UINT()
    try:
        ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        report('Windows scaling 100%', dpi_x.value == 96,
               f'{round(dpi_x.value / 96 * 100)}%' + ('' if dpi_x.value == 96 else
               ' -> Settings > Display > select the SLM > Scale = 100%'))
    except Exception as e:
        report('Windows scaling 100%', None, f'could not read it ({e})')

    # Display mode: real resolution and color depth
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    if user32.EnumDisplaySettingsW(device, -1, ctypes.byref(mode)):  # -1 = current settings
        report('Display mode', (mode.dmPelsWidth, mode.dmPelsHeight) == SLM_RES and mode.dmBitsPerPel == 32,
               f'{mode.dmPelsWidth} x {mode.dmPelsHeight}, {mode.dmBitsPerPel}-bit color, {mode.dmDisplayFrequency} Hz')

    # Gamma table of the graphics card: must be the identity, otherwise every value is changed on the way out
    gdi32 = ctypes.windll.gdi32
    hdc = gdi32.CreateDCW('DISPLAY', device, None, None)
    ramp = (wt.WORD * 768)()
    if hdc and gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(ramp)):
        ramp = np.array(ramp).reshape(3, 256) >> 8
        bad = int(np.sum(ramp != np.arange(256)))
        report('Gamma table untouched', bad == 0,
               '' if bad == 0 else f'{bad} of 768 entries changed -> turn off night light / color calibration / color profile for the SLM')
    else:
        report('Gamma table untouched', None, 'could not read it')
    if hdc:
        gdi32.DeleteDC(hdc)

    print(f'  SLM monitor device: {device}')
    return geometry


######################## PART 2: PIXEL CHECK ########################

def test_pattern(w, h):
    '''Top half: all 1024 SLM values as a ramp. Bottom half: 1-pixel checkerboard 0/1023 and an
    orientation marker in the bottom left corner.'''
    bits = np.zeros((h, w), dtype=int)
    bits[:h // 2, :] = (np.arange(w) * 1024 // w)[None, :]
    yy, xx = np.mgrid[h // 2:h, 0:w]
    bits[h // 2:, :] = ((xx + yy) % 2) * 1023
    bits[-100:, :100] = 700
    return bits


def check_pixels(cal, geometry):
    print('\n===== Part 2: pixel check (screenshot of the SLM monitor) =====')
    x0, y0, w, h = geometry
    frame = cal.slm.vt.frame
    if (frame._x0, frame._y0, cal.resX, cal.resY) != geometry:
        report('SLM window size', False, f'slmpy window is {cal.resX} x {cal.resY} at ({frame._x0}, {frame._y0}), '
                                         f'SLM monitor is {w} x {h} at ({x0}, {y0})')
        return
    report('SLM window size', True, f'{w} x {h}')

    sent_bits = test_pattern(w, h)
    sent_rgb = SLMcalibration.convert_to_RGB(sent_bits)
    cal.slm.updateArray(sent_rgb.astype(dtype=np.int8))  # exactly like the rest of the program
    time.sleep(1.5)

    shot = np.array(ImageGrab.grab(bbox=(x0, y0, x0 + w, y0 + h), all_screens=True).convert('RGB'))
    if shot.shape[:2] != (h, w):
        report('Screenshot', False, f'got {shot.shape[1]} x {shot.shape[0]}')
        return

    wrong = np.any(shot != sent_rgb, axis=-1)
    n_wrong = int(wrong.sum())
    if n_wrong == 0:
        report('Pixels on the SLM monitor = pixels sent', True, f'all {w * h} pixels exact, all 1024 values OK')
        return

    msg = f'{n_wrong} of {w * h} pixels differ ({100 * n_wrong / (w * h):.2f}%)'

    #Is the 1-pixel checkerboard still sharp (two colors, each the same everywhere)? Then the geometry is fine and only the colors changed.
    board = shot[h // 2:-100], sent_bits[h // 2:-100]
    dark, bright = board[0][board[1] == 0], board[0][board[1] == 1023]
    board_sharp = np.all(dark == dark[0]) and np.all(bright == bright[0]) and not np.array_equal(dark[0], bright[0])
    if np.array_equal(shot[::-1, ::-1], sent_rgb) or np.array_equal(shot[:, ::-1], sent_rgb) or np.array_equal(shot[::-1], sent_rgb):
        msg += ' -> the image is MIRRORED (Windows display orientation?)'
    elif board_sharp:
        msg += ' -> the geometry is right but the COLORS are changed (color profile, night light, HDR, color enhancement?)'
    else:
        msg += ' -> the 1-pixel checkerboard is blurred/shifted: the image is SCALED (Windows scaling, resolution, wrong monitor?)'

    #Which SLM values come out wrong (from the ramp in the top half; most columns there are one value)
    sent_row, shown_row = sent_bits[h // 4], bits_from_rgb(shot[h // 4])
    bad = sent_row != shown_row
    if bad.any():
        bad_values, first = np.unique(sent_row[bad], return_index=True)
        cols = np.flatnonzero(bad)[first]
        worst = cols[np.argsort(-np.abs(shown_row[cols] - sent_row[cols]))][:8]
        examples = ', '.join(f'{sent_row[c]}->{shown_row[c]}' for c in sorted(worst))
        msg += f'\n         {len(bad_values)} of 1024 SLM values are shown wrong, worst (sent->shown): {examples}'
    report('Pixels on the SLM monitor = pixels sent', False, msg)


######################## PART 3: OPTICAL CHECK ########################

def check_optics(cal, info_file, exposure, n_levels):
    print('\n===== Part 3: optical check with the camera =====')
    info_loc = Path(info_file)
    if not info_loc.is_file():
        info_loc = Path(CALIBRATION_FOLDER) / info_file
    metadata = np.load(info_loc, allow_pickle=True)
    calib_bits = metadata['bits']
    bar_shape = tuple(metadata['bar_shape'])
    bar_location = find_calibration_dat(info_loc, str(metadata['location']))
    calibmap = np.memmap(bar_location, dtype=str(metadata['bar_dtype']), mode='r', shape=bar_shape)

    idx = np.unique(np.linspace(0, len(calib_bits) - 1, n_levels).astype(int))
    test_bits = calib_bits[idx]

    #Reference: polarization angle of the mean Stokes vector over the calibration ROI
    psi_ref = np.array([0.5 * np.degrees(np.arctan2(np.mean(calibmap[i, ..., 1]), np.mean(calibmap[i, ..., 0]))) for i in idx])

    cal.init_camera(exposure_time=exposure)
    cal.slm.updateArray(SLMcalibration.convert_to_RGB(500 * np.ones((cal.resY, cal.resX))).astype(dtype=np.int8))
    time.sleep(1.2)
    print('Select the SAME SLM area as for the calibration (first rectangle is used), then close the window.')
    cal.get_region()

    psi_new = []
    max_int = 0
    for b in test_bits:
        cal.slm.updateArray(SLMcalibration.convert_to_RGB(b * np.ones((cal.resY, cal.resX))).astype(dtype=np.int8))
        time.sleep(1.1)  #SLM response time
        intensity = stks.polar_image(cal.get_image()) / SLMcalibration.NORM
        roi = intensity[cal.Imin:cal.Imax, cal.Jmin:cal.Jmax, :]
        max_int = max(max_int, roi.max())
        i90, i45, i135, i0 = roi[..., 0], roi[..., 1], roi[..., 2], roi[..., 3]
        s0 = i0 + i90
        s1 = np.mean((i90 - i0) / s0)   #same sign convention as SLM_scan
        s2 = np.mean((i135 - i45) / s0)
        psi_new.append(0.5 * np.degrees(np.arctan2(s2, s1)))
        print(f'  bit {b:4d}: psi now {psi_new[-1]:7.2f} deg, calibration {psi_ref[len(psi_new) - 1]:7.2f} deg')
    cal.close_camera()
    psi_new = np.array(psi_new)

    if max_int > 0.9:
        report('Camera exposure', None, f'max intensity {max_int:.2f}, close to saturation -> lower --exposure')
    elif max_int < 0.05:
        report('Camera exposure', None, f'max intensity {max_int:.3f}, very dark -> laser on? raise --exposure')

    diff = (psi_new - psi_ref + 90) % 180 - 90  #angle difference, psi is defined modulo 180
    offset = np.median(diff)
    spread = np.abs(diff - offset)
    print(f'  difference: median {offset:.2f} deg, max {np.max(np.abs(diff)):.2f} deg, max around the median {spread.max():.2f} deg')
    if spread.max() < 10:
        report('SLM response matches the calibration', True if abs(offset) < 10 else None,
               '' if abs(offset) < 10 else f'same shape but shifted by {offset:.1f} deg -> optics moved? (not a display problem)')
    else:
        report('SLM response matches the calibration', False,
               'values do not match -> check "Full RGB range (0-255)" in the Intel/AMD/NVIDIA control panel for the SLM display, '
               'turn off color enhancement/HDR, and that the optics and ROI are the same as for the calibration')

    try:
        import matplotlib.pyplot as plt
        plt.ioff()
        f, a = plt.subplots(1)
        a.plot(calib_bits, [0.5 * np.degrees(np.arctan2(np.mean(calibmap[i, ..., 1]), np.mean(calibmap[i, ..., 0])))
                            for i in range(len(calib_bits))], '-', label='calibration')
        a.plot(test_bits, psi_new, 'o', label='now')
        a.set_xlabel('SLM bit')
        a.set_ylabel('psi (deg)')
        a.legend()
        plt.show()
    except Exception as e:
        print(f'(could not plot: {e})')


######################## MAIN ########################

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check that the SLM image is displayed right on this PC.')
    parser.add_argument('--camera', metavar='INFO_NPZ', help='calibration _info.npz file for the optical check (part 3)')
    parser.add_argument('--exposure', type=float, default=5e5, help='camera exposure in microseconds (default 5e5, as calibration_run.py)')
    parser.add_argument('--levels', type=int, default=24, help='number of SLM values to compare in part 3 (default 24)')
    args = parser.parse_args()

    geometry = check_display_setup()
    if geometry is not None:
        cal = SLMcalibration()
        cal.init_SLM()
        try:
            check_pixels(cal, geometry)
            if args.camera:
                check_optics(cal, args.camera, args.exposure, args.levels)
        finally:
            cal.slm.close()

    print('\n===== Summary =====')
    for name, passed, message in results:
        print(f'{TAGS[passed]}  {name}')
    if not args.camera:
        print('\nNOTE: a screenshot can not see the "Limited RGB range (16-235)" setting of the graphics driver.\n'
              '      Check that the SLM display is set to Full range (0-255), or run with --camera for the optical check.')
    failed = any(p is False for _, p, _ in results)
    print('\nRESULT:', 'FAILED' if failed else 'OK')
    sys.stdout.flush()
    os._exit(1 if failed else 0)  #skip the normal shutdown, slmpy's wx thread crashes it otherwise
