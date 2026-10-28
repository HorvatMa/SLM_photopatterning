# SLMwGUI

Control software for writing **polarization patterns** with a spatial light modulator (SLM).

You describe the wanted polarization angle for every SLM pixel, the program calculates which
SLM gray level (bit, 0–1023) produces that angle (using a measured calibration), shows the
result on the SLM and controls the illumination (LED diode + filter mount) used to expose the sample.

Everything runs from one GUI: **`GUI_SLM_v2.py`**.

---

## Contents

- [Hardware](#hardware)
- [Installation](#installation)
- [Running](#running)
- [Workflow](#workflow)
- [Data folders and file formats](#data-folders-and-file-formats)
- [Code overview](#code-overview)
- [Technical notes and gotchas](#technical-notes-and-gotchas)

---

## Hardware

| Device | Used for | Talks to the PC via | Code |
|---|---|---|---|
| SLM, 1920 × 1200, connected as a **second monitor** | displays the pattern; the 10-bit value of every pixel is encoded in the RGB color | `slmpy` (wxPython fullscreen window) | `Calibration.SLMcalibration.init_SLM`, `convert_to_RGB` |
| FLIR polarization camera (Sony IMX250MZR sensor, 2448 × 2048) | measuring the SLM response for the calibration | PySpin (Spinnaker SDK) | `Calibration.SLMcalibration.init_camera` / `get_image` |
| Thorlabs ITC4020 LED/laser diode controller | illumination current, on/off | PyVISA (USB, serial `M00248415`) | `VISA_connection.LaserController` |
| Thorlabs ELL6B Elliptec 2-position filter mount | timed exposure (pos. 1 = home, ND filter; pos. 2 = open) | `thorlabs_elliptec` (serial COM port) | `filtermount.ELL6Bmanager` |
| NVIDIA GPU (optional) | fast minimization with cupy | CUDA 12 | `minimize_cuda.py` |

The camera is only needed for the calibration scan; the GUI itself does not use it.

---

## Installation

Tested on **Windows 10/11, Python 3.12 (64-bit)**.

### 1. System software (once per PC)

1. **[uv](https://docs.astral.sh/uv/)** (`winget install astral-sh.uv`): installs Python 3.12 and the packages.
2. **git**: uv needs it to install `slmpy` from GitHub.
3. **FLIR Spinnaker SDK + PySpin.** This is handled separately and isn't in `requirements.txt`,
   because it isn't on PyPI.
   - Install the Spinnaker SDK (this program was tested with **4.4.0.246**) from the
     [Teledyne FLIR website](https://www.teledynevisionsolutions.com/products/spinnaker-sdk/) (free account needed).
     The camera is USB, so if the installer fails on the **GigE Vision** interface, run it again with the GigE drivers turned off.
   - Download the matching Python wheel for Python 3.12 (`spinnaker_python-4.4.0.246-cp312-cp312-win_amd64.whl`, inside a zip)
     and install it into the environment *after* step 2 below. FLIR only offers PySpin 4.x wheels for Python 3.10 and 3.12.
   - Only needed for the calibration scan. Without PySpin the GUI still runs, and only `init_camera` raises an error.
4. **A VISA backend** for PyVISA: NI-VISA or Thorlabs VISA (the ITC4020 driver package from Thorlabs).
5. **Elliptec**: the ELL6B shows up as a COM port (FTDI virtual COM port driver; Windows usually installs it automatically).
6. **NVIDIA driver with CUDA 12 support** (optional, for the GPU minimizer).

### 2. Python environment

```bat
git clone <this repo url> SLMwGUI
cd SLMwGUI

uv python install 3.12
uv venv --python 3.12 .venv
.venv\Scripts\activate

uv pip install -r requirements-lock.txt
uv pip install path\to\spinnaker_python-4.4.0.246-cp312-cp312-win_amd64.whl
```

There are two requirement files:

| File | What it is | Use it to |
|---|---|---|
| `requirements.txt` | the packages the code uses directly, pinned, with the reason for the important pins | read and edit by hand |
| `requirements-lock.txt` | **every** package including dependencies, at the exact versions tested in the lab | install, so every machine gets an identical environment |

If you change `requirements.txt` (add or upgrade a package), regenerate the lock file in a fresh environment:

```bat
uv pip install -r requirements.txt
uv pip freeze --exclude-editable > requirements-lock.txt
```

Then check that the `slmpy` line in the lock file is still the `git+https://...@<commit>` form, and
remove `spinnaker-python` if it was installed in that environment.

### 3. Data folder

Set where the data lives (see [Data folders](#data-folders-and-file-formats)): either edit `DATA_ROOT` in
`paths.py` or set an environment variable:

```bat
setx SLM_DATA_ROOT "D:\SLMwGUI_data"
:: or a NAS:  setx SLM_DATA_ROOT "\\server\share\SLMwGUI_data"
```

The three sub-folders are created automatically the first time the program runs.

---

## Running

```bat
python GUI_SLM_v2.py           :: main GUI
python calibration_run.py      :: calibration scan (interactive, in a terminal)
python create_vzorec_360.py    :: generate a wanted pattern (edit the bottom of the file first)
python see_scan_file.py        :: inspect a calibration scan (set the file name at the top)
python test_slm_display.py     :: check that the SLM image is displayed right (new PC)
```

At startup the GUI opens the SLM window on the second screen and connects to the ITC4020; both must
be connected. The Elliptec mount connects only when you press **Connect**. The console prints which minimizer is used:
`Minimizer: GPU (cupy)` or `Minimizer: CPU`.

### Checking a new PC (`test_slm_display.py`)

The SLM reads its 10-bit value from the exact RGB numbers of every pixel, so the PC must send them **unchanged**.
Run this once on every new PC (or after a graphics driver update):

```bat
python test_slm_display.py                               :: parts 1 + 2, needs only the SLM connected
python test_slm_display.py --camera 9_6_2025_info.npz    :: + part 3, needs camera, laser on, same optics as the calibration
```

1. **Display setup.** The SLM must be monitor 1 (Extend, not Duplicate), 1920 × 1200, 32-bit, Windows scaling 100%, and the gamma table must be untouched.
2. **Pixel check.** It shows a pattern with all 1024 values plus a 1-pixel checkerboard, takes a screenshot of the SLM monitor, and compares it
   with what was sent, pixel by pixel. If they differ, it says whether the image is mirrored, scaled, or has its colors changed.
3. **Optical check (optional).** It shows uniform values, measures the polarization angle with the camera, and compares it with a
   calibration file. Select the same ROI as for the calibration. Only this part sees what happens *after* the graphics card.

A screenshot can't see the graphics driver's **"Limited" RGB range (16–235)**. Intel and AMD drivers often use it over HDMI by
default, and it changes almost every SLM value. Set the SLM display to **Full range (0–255)** in the Intel/AMD/NVIDIA control
panel, and turn off color enhancement, night light and HDR for it. The script exits with code 1 if anything fails.

The SLM works with any graphics card (Intel/AMD/NVIDIA); NVIDIA is only needed for the GPU minimizer.

---

## Workflow

1. **Make a wanted pattern** (`create_vzorec_360.py`): a `1200 × 1920` array of polarization angles
   in **degrees, 0–360**, saved as `.npy` into `SLM_patterns/`. The file has helper functions for lines, splay/bend
   defects, text, sinusoidal patterns, etc.
2. **Calibrate** (`calibration_run.py`). Do this once per setup or wavelength, or when the optics change:
   - the SLM shows a uniform image, the camera takes a frame and you **select the SLM area (ROI)** with the mouse
     in a Tk window (`RectangleFinder_v2.py`)
   - the program sets every bit (default `0..1022` in steps of 2) on the whole SLM, waits 1.1 s for the SLM to respond,
     averages `n_average` frames, optionally Gaussian-smooths them, and stores the normalized Stokes parameters for every ROI pixel
   - output: `<name>.dat` (big array) + `<name>_info.npz` (metadata) in `SLM_scan_files/`
3. **Minimize** (GUI, *Minimize pattern* section): choose the wanted pattern, the calibration `_info.npz`, bit
   bounds, angle bounds and λ (the smoothness weight), then press **Minimize**. For every pixel the minimizer finds the bit whose
   measured (S1, S2) is closest to the wanted `(cos 2ψ, sin 2ψ)`, with a smoothness term weighted by λ.
   The result is saved as `<name>.npz` in `SLM_optimized_structures/` and plotted.
4. **Show** (GUI, *SLM pattern file* section): the new file is already selected in the list; **Show** sends it to the SLM.
5. **Expose** (GUI): set the LED current and turn the diode **ON**, connect the Elliptec, then **SET TIMED** moves the filter mount to
   position 2 for the set time and back to position 1 afterwards. **Abort** returns it at once.

---

## Data folders and file formats

`paths.py` defines all folders (default root `D:\SLMwGUI_data`, or `SLM_DATA_ROOT`):

| Folder | Contents |
|---|---|
| `SLM_scan_files/` | calibration scans |
| `SLM_patterns/` | wanted patterns (`.npy`) |
| `SLM_optimized_structures/` | minimized SLM bit maps (`.npz`) shown by the GUI |

Data files are **not** in the repo (`.gitignore`).

**Calibration scan**
- `<name>.dat`: raw `np.memmap`, shape `(N_bits, N_roi, M_roi, 3)`, usually `float32`. The last axis is
  `S1/S0, S2/S0, S3/S0` per ROI pixel, where ROI pixels are camera *superpixels* (half the sensor resolution).
- `<name>_info.npz`: `bits` (the bit values scanned), `bar_shape`, `bar_dtype`, `location` (absolute path of the `.dat`
  at the time of the scan).
- Keep the two files **together**. If `location` doesn't exist anymore (data moved to another disk or a NAS),
  `paths.find_calibration_dat` looks for the `.dat` next to the `_info.npz`.
- Size: ~1.5 GB for a 512-bit scan. **Use NTFS/exFAT**: FAT32 can't hold files over 4 GB.

**Wanted pattern**: `.npy`, `float`, shape `(1200, 1920)`, angle in degrees 0–360.

**Optimized structure**: `.npz` with `psi_wanted` (the pattern) and `optimal_bits` (`int`, 0–1023, `1200 × 1920`).

---

## Code overview

```
GUI_SLM_v2.py         main PyQt5 GUI: minimizer + SLM pattern display + LED diode + Elliptec
Calibration.py        SLMcalibration: SLM (slmpy) and camera (PySpin) wrapper + calibration scan (SLM_scan)
calibration_run.py    script that runs a calibration scan
polarimetry.py        polarization camera image -> 4 channels (polar_image) -> Stokes (stokes, psi, chi)
minimize_cuda.py      get_best_psi on the GPU (cupy)
minimize_pattern.py   get_best_psi on the CPU (numba), same interface without cuda_on
VISA_connection.py    LaserController: Thorlabs ITC4020 over VISA (SCPI commands)
filtermount.py        ELL6Bmanager: Thorlabs ELL6B 2-position mount (positions 1/2 <-> raw 0/31)
paths.py              data folder locations + find_calibration_dat
RectangleFinder_v2.py Tk tool to draw the ROI rectangle on a camera image
create_vzorec_360.py  pattern generator (script)
see_scan_file.py      calibration scan viewer / analysis (script)
test_slm_display.py   checks that the SLM image arrives unchanged on this PC (run on every new PC)
```

### SLM pixel encoding (`SLMcalibration.convert_to_RGB`)
The SLM takes a **10-bit** value per pixel, packed into the RGB of the second-screen image:
`R = (v // 128) * 32`, `G = ((v % 128) // 16) * 32`, `B = (v % 16) * 16`.
The result must be cast to `np.int8` before `slm.updateArray`. Some scripts mirror the image (`[::-1, ::-1]`) to match the optics.

### Camera (`Calibration.py`, standard PySpin)
`init_camera` takes the first camera, then sets `SingleFrame` acquisition, auto exposure and gain off, gain 0, gamma off, `Mono16`, and
12-bit ADC. `get_image` runs one `BeginAcquisition` → `GetNextImage` → `EndAcquisition` cycle and **copies** the
array before `Release()`. `close_camera` releases everything in the order PySpin requires (DeInit → drop the camera
reference → `CameraList.Clear()` → `System.ReleaseInstance()`); it is also registered with `atexit`.

### Polarization camera mosaic (`polarimetry.py`)
In each 2×2 superpixel: `[0,0]=90°`, `[0,1]=135°`, `[1,0]=45°`, `[1,1]=0°`.
`polar_image` returns `(H/2, W/2, 4)` with channels `(i90, i45, i135, i0)`.
The calibration scan uses `S1 = i90 − i0` and `S2 = i135 − i45`, the **opposite sign** of `polarimetry.stokes`, so the angle
matches what the camera software shows. Keep that in mind if you compare the two.

### Threading in the GUI
The minimization runs in a `QThread` (`Worker`), which reports progress through `progress_callback` → progress bar.
Errors are passed back with `error_signal` and shown in a message box. Everything else in the GUI keeps working during a run.

---

## Technical notes and gotchas

- **History.** The camera code used to depend on the lab's `spinview` library: its `pyspin` memory-management wrapper,
  its `camera_features` settings and its image/Stokes functions. Now it uses plain FLIR `PySpin`, and the few image functions it
  needed are in `polarimetry.py`, giving identical results. `GUI_SLM_v2.py` merges the earlier `GUI_SLM_v1.py` (SLM, LED, Elliptec) and
  `GUI_minimize.py` (minimizer).
- **Version pins** (see `requirements.txt`): Python 3.12 because the newest PySpin wheels (4.x) exist only for 3.10 and 3.12, and 3.10
  reaches end of life in October 2026. PySpin 4.4 needs `numpy>=2.0`, and numba 0.61 supports numpy up to 2.2, so numpy is 2.2.
  Keep numpy **below 2.3** also because of `slmpy`: it sends every image with `ndarray.tostring()`, which numpy 2.3 removed
  (it would fail with an `AttributeError` the first time an image is shown).
  wxPython is 4.2 because 4.1 has no 3.12 wheels. `slmpy` is pinned to a commit of the upstream repo, unmodified.
- **Python 3.8 → 3.12 migration.** The minimizer (both modes) and the SLM RGB encoding were compared on a synthetic calibration
  between the old 3.8 environment and the new one, and the results are identical. The unused `scipy.interpolate.interp2d`
  import (removed in scipy 1.14) was dropped.
- **The ITC4020 is found by its serial number `M00248415`** (`VISA_connection.LaserController.init`). For another unit,
  pass `findstr=` or `address=`.
- **LED current limits:** the GUI caps the current at `MAX_CURRENT = 1500 mA`, and the controller is set to a 1.55 A limit and 5.5 V
  protection (`_LD_CONFIG_DEFAULT`).
- **ELL6B positions** are raw encoder values 0 (home) and 31. `ELL6Bmanager` waits for the first status poll after
  connecting, because the driver reports position 0 until then.
- **The minimizer defaults** (bit 0–718, angle 0–359°, λ = 1) are in `DEFAULT_VALUES` at the top of `GUI_SLM_v2.py`, and are
  specific to the current SLM, wavelength and calibration.
- **The calibration scan asks in the terminal** before creating the big file (it shows the disk space needed), so run it from a terminal, not the GUI.
- **Data on USB sticks:** a FAT32 flash stick caused timeouts (`WinError 121`) and has the 4 GB file limit. Prefer an NTFS disk or a NAS.
  If the data folder can't be reached, `paths.py` only prints a warning.
