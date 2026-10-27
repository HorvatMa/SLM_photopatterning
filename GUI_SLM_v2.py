# -*- coding: utf-8 -*-
"""
SLM controller + minimizer in one GUI.

Combines GUI_SLM_v1 (SLM pattern display, LED diode, Elliptec filter mount)
with GUI_minimize (calculating the optimal SLM bits for a wanted pattern).
After a minimization finishes, the optimized structure is saved, added to the
pattern dropdown and plotted, so you can send it to the SLM with "Show".
"""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QMessageBox, QFrame, QStyle, QLineEdit
import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from pathlib import Path
import os
import sys
import pyvisa as visa
import time

from Calibration import SLMcalibration #Custom module to communicate with SLM
import VISA_connection #Custom module to communicate with the laser
from filtermount import ELL6Bmanager #Custom module to communicate with the Thorlabs ELL6B filter mount
from paths import CALIBRATION_FOLDER, PATTERNS_FOLDER, OPTIMIZED_STRUCTURES_FOLDER #Data folders on the external disk (set in paths.py)




###### THESE PARAMETERS NEED TO BE ADJUSTED IF YOU CHANGE THE SETUP A BIT ######
MAX_CURRENT = 1500 #mA

DEFAULT_VALUES  = {'min_bit': 0,
                    'max_bit': 718,
                    'min_angle': 0,
                    'max_angle': 359,
                    'lamb': 1.0}

###### THESE PARAMETERS NEED TO BE ADJUSTED IF YOU CHANGE THE SETUP A BIT ######


# Use the GPU (cupy) minimizer if there is an NVIDIA GPU, otherwise the CPU one
try:
    import cupy as cp
    CUDA_ON = cp.cuda.runtime.getDeviceCount() > 0
except Exception:
    CUDA_ON = False

if CUDA_ON:
    from minimize_cuda import get_best_psi
else:
    from minimize_pattern import get_best_psi
print(f"Minimizer: {'GPU (cupy)' if CUDA_ON else 'CPU'}")


FRAME_STYLE = """
    QFrame {
        border: 1px solid black;
    }
"""




class Worker(QtCore.QObject):

    # Define signals for updating the progress bar and completing the task
    progress_signal = QtCore.pyqtSignal(int)  # To update progress
    finished_signal = QtCore.pyqtSignal()  # To notify when the task is finished
    error_signal = QtCore.pyqtSignal(str)  # To notify when the minimization failed

    def __init__(self, psi_wanted_loc, calib_info_loc, lamb, bit_b, phase_b):

        super().__init__()
        self.psi_wanted_loc = psi_wanted_loc
        self.calib_info_loc = calib_info_loc
        self.lamb = lamb
        self.bit_b = bit_b
        self.phase_b = phase_b

    def progress_callback(self, progress):
        # This will be called from get_best_psi to update the progress bar
        self.progress_signal.emit(progress)

    def run(self):
        try:
            # Load the array of the pattern
            self.psiwanted = np.load(self.psi_wanted_loc)

            # Call get_best_psi with the progress_callback (only the GPU version takes cuda_on)
            extra_kwargs = {'cuda_on': True} if CUDA_ON else {}
            self.result = get_best_psi(
                self.psiwanted,
                self.calib_info_loc,
                self.lamb,
                self.bit_b,
                self.phase_b,
                with_psi=False,
                progress_callback=self.progress_callback,  # Pass the callback
                **extra_kwargs
            )

            # Notify that the task is finished
            self.finished_signal.emit()

        except Exception as e:
            print(f"Error: {e}")
            self.error_signal.emit(str(e))




class Ui_SLMcontroller(object):
    def setupUi(self, SLMcontroller):



        # Setup the SLM class
        self.cal = SLMcalibration()
        self.cal.init_SLM()


        #Setup the VISA connection module
        self.laser  = VISA_connection.LaserController()
        self.laser.init()
        self.laser.setup()

        # Thorlabs ELL6B filter mount is not connected until the user clicks "Connect"
        self.ell = None

        # Minimizer worker thread
        self.thread = None

        # Images currently shown on the canvas, used for the hover readout: {axes: (data, label)}
        self.hover_images = {}



        SLMcontroller.setObjectName("SLMcontroller")
        SLMcontroller.resize(1200, 900)

        # Create the central widget: controls on the left, plot on the right
        self.centralwidget = QtWidgets.QWidget(SLMcontroller)
        self.centralwidget.setObjectName("centralwidget")
        self.main_layout = QtWidgets.QHBoxLayout(self.centralwidget)

        self.controlsWidget = QtWidgets.QWidget(self.centralwidget)
        self.controlsWidget.setMaximumWidth(560)
        self.grid_layout = QtWidgets.QGridLayout(self.controlsWidget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.controlsWidget)




        ######################## MINIMIZER ########################

        # Create the minimizer label (outside the frame)
        self.minimize_label = QtWidgets.QLabel(self.controlsWidget)
        self.minimize_label.setObjectName("minimize_label")
        self.grid_layout.addWidget(self.minimize_label, 0, 0, 1, 5)

        # Create the frame for the minimizer
        self.minimizeFrame = QFrame(self.controlsWidget)
        self.minimizeFrame.setFrameShape(QFrame.StyledPanel)
        self.minimizeFrame.setFrameShadow(QFrame.Sunken)
        self.minimizeFrame.setStyleSheet(FRAME_STYLE)
        self.minimizeLayout = QtWidgets.QVBoxLayout(self.minimizeFrame)

        folder_icon = SLMcontroller.style().standardIcon(QStyle.SP_DirOpenIcon)

        # --- Wanted pattern row ---
        self.patternLayout = QtWidgets.QHBoxLayout()
        self.browseButton = QtWidgets.QPushButton(self.minimizeFrame)
        self.browseButton.setIcon(folder_icon)
        self.browseButton.setMaximumWidth(40)
        self.browseButton.clicked.connect(self.browse_pattern_directory)
        self.patternLayout.addWidget(self.browseButton)
        self.fileLine = QLineEdit(self.minimizeFrame)
        self.fileLine.setObjectName("fileLine")
        self.patternLayout.addWidget(self.fileLine)
        self.minimizeLayout.addLayout(self.patternLayout)

        # --- Calibration file row ---
        self.calibrationLayout = QtWidgets.QHBoxLayout()
        self.loadCalibration = QtWidgets.QPushButton(self.minimizeFrame)
        self.loadCalibration.setIcon(folder_icon)
        self.loadCalibration.setMaximumWidth(40)
        self.loadCalibration.clicked.connect(self.browse_calibration_directory)
        self.calibrationLayout.addWidget(self.loadCalibration)
        self.calibrationLine = QLineEdit(self.minimizeFrame)
        self.calibrationLine.setObjectName("calibrationLine")
        self.calibrationLayout.addWidget(self.calibrationLine)
        self.minimizeLayout.addLayout(self.calibrationLayout)

        # --- All the settings for the minimizer ---
        self.settingsLayout = QtWidgets.QGridLayout()

        self.minBitLabel = QtWidgets.QLabel("Min bit", self.minimizeFrame)
        self.settingsLayout.addWidget(self.minBitLabel, 0, 0)
        self.minBit = QLineEdit(self.minimizeFrame)
        self.minBit.setMaximumWidth(60)
        #Determine the type in the line and also biggest and smallest values available. Also default.
        self.minBit.editingFinished.connect(lambda: self.save_value_and_clear_focus(self.minBit, dtype=int, min_value=0, max_value=1023, default_value=DEFAULT_VALUES['min_bit']))
        self.settingsLayout.addWidget(self.minBit, 0, 1)

        self.maxBitLabel = QtWidgets.QLabel("Max bit", self.minimizeFrame)
        self.settingsLayout.addWidget(self.maxBitLabel, 1, 0)
        self.maxBit = QLineEdit(self.minimizeFrame)
        self.maxBit.setMaximumWidth(60)
        self.maxBit.editingFinished.connect(lambda: self.save_value_and_clear_focus(self.maxBit, dtype=int, min_value=0, max_value=1023, default_value=DEFAULT_VALUES['max_bit']))
        self.settingsLayout.addWidget(self.maxBit, 1, 1)

        self.minAngleLabel = QtWidgets.QLabel("Min angle (deg)", self.minimizeFrame)
        self.settingsLayout.addWidget(self.minAngleLabel, 0, 2)
        self.minAngle = QLineEdit(self.minimizeFrame)
        self.minAngle.setMaximumWidth(60)
        self.minAngle.editingFinished.connect(lambda: self.save_value_and_clear_focus(self.minAngle, dtype=float, min_value=0, max_value=np.inf, default_value=DEFAULT_VALUES['min_angle']))
        self.settingsLayout.addWidget(self.minAngle, 0, 3)

        self.maxAngleLabel = QtWidgets.QLabel("Max angle (deg)", self.minimizeFrame)
        self.settingsLayout.addWidget(self.maxAngleLabel, 1, 2)
        self.maxAngle = QLineEdit(self.minimizeFrame)
        self.maxAngle.setMaximumWidth(60)
        self.maxAngle.editingFinished.connect(lambda: self.save_value_and_clear_focus(self.maxAngle, dtype=float, min_value=0, max_value=np.inf, default_value=DEFAULT_VALUES['max_angle']))
        self.settingsLayout.addWidget(self.maxAngle, 1, 3)

        self.lambdaLabel = QtWidgets.QLabel(self.minimizeFrame)
        self.lambdaLabel.setTextFormat(QtCore.Qt.RichText)
        self.settingsLayout.addWidget(self.lambdaLabel, 0, 4)
        self.lambdaLine = QLineEdit(self.minimizeFrame)
        self.lambdaLine.setMaximumWidth(60)
        self.lambdaLine.editingFinished.connect(lambda: self.save_value_and_clear_focus(self.lambdaLine, dtype=float, min_value=0, max_value=np.inf, default_value=DEFAULT_VALUES['lamb']))
        self.settingsLayout.addWidget(self.lambdaLine, 0, 5)

        self.minimizeLayout.addLayout(self.settingsLayout)

        # --- Save folder row ---
        self.saveFolderLayout = QtWidgets.QHBoxLayout()
        self.chooseFolderButton = QtWidgets.QPushButton(self.minimizeFrame)
        self.chooseFolderButton.setIcon(folder_icon)
        self.chooseFolderButton.setMaximumWidth(40)
        self.chooseFolderButton.clicked.connect(self.browse_save_directory)
        self.saveFolderLayout.addWidget(self.chooseFolderButton)
        self.saveFolderLabel = QtWidgets.QLabel(self.minimizeFrame)
        self.saveFolderLabel.setObjectName("saveFolderLabel")
        self.saveFolderLayout.addWidget(self.saveFolderLabel)
        self.minimizeLayout.addLayout(self.saveFolderLayout)

        # --- Name + run row ---
        self.runLayout = QtWidgets.QHBoxLayout()
        self.nameOptimized = QLineEdit(self.minimizeFrame)
        self.nameOptimized.setObjectName("nameOptimized")
        # Remove the suffix if the user typed one
        self.nameOptimized.editingFinished.connect(self.remove_suffix)
        self.runLayout.addWidget(self.nameOptimized)
        self.runButton = QtWidgets.QPushButton("Minimize", self.minimizeFrame)
        self.runButton.setIcon(SLMcontroller.style().standardIcon(QStyle.SP_MediaPlay))
        self.runButton.clicked.connect(self.on_run_button_clicked)
        self.runLayout.addWidget(self.runButton)
        self.minimizeLayout.addLayout(self.runLayout)

        # Progress bar under the run button
        self.progressBar = QtWidgets.QProgressBar(self.minimizeFrame)
        self.progressBar.setObjectName("progressBar")
        self.progressBar.setRange(0, 100)  # The progress bar will go from 0 to 100
        self.progressBar.setValue(0)
        self.progressBar.setVisible(False)  # Make the progress bar invisible initially
        self.progressBar.setTextVisible(True)
        self.minimizeLayout.addWidget(self.progressBar)

        self.grid_layout.addWidget(self.minimizeFrame, 1, 0, 1, 5)




        ######################## SLM PATTERN FILE ########################

        # Create the file selection label (outside the frame)
        self.file_selection_label = QtWidgets.QLabel(self.controlsWidget)
        self.file_selection_label.setObjectName("file_selection_label")
        self.grid_layout.addWidget(self.file_selection_label, 2, 0, 1, 5)

        # Create the frame for the file selection section
        self.fileSelectionFrame = QFrame(self.controlsWidget)
        self.fileSelectionFrame.setFrameShape(QFrame.StyledPanel)
        self.fileSelectionFrame.setFrameShadow(QFrame.Sunken)
        self.fileSelectionFrame.setLineWidth(3)
        self.fileSelectionFrame.setStyleSheet(FRAME_STYLE)
        self.fileSelectionLayout = QtWidgets.QHBoxLayout(self.fileSelectionFrame)

        # ComboBox for file selection
        self.comboBox = QtWidgets.QComboBox(self.fileSelectionFrame)
        self.comboBox.setObjectName("comboBox")
        self.loadFilesToComboBox()  # Load files into the comboBox
        self.fileSelectionLayout.addWidget(self.comboBox)

        # Refresh button with an icon
        self.pushButton_2 = QtWidgets.QPushButton(self.fileSelectionFrame)
        self.pushButton_2.setText("")
        self.pushButton_2.setIcon(SLMcontroller.style().standardIcon(QStyle.SP_BrowserReload))
        self.pushButton_2.setIconSize(QtCore.QSize(24, 24))
        self.pushButton_2.clicked.connect(self.loadFilesToComboBox)
        self.fileSelectionLayout.addWidget(self.pushButton_2)

        # Show button
        self.pushButton = QtWidgets.QPushButton("Show", self.fileSelectionFrame)
        self.pushButton.setObjectName("load_button")
        self.pushButton.clicked.connect(self.loadSelectedFile)
        self.fileSelectionLayout.addWidget(self.pushButton)

        self.grid_layout.addWidget(self.fileSelectionFrame, 3, 0, 1, 5)




        ######################## LED DIODE ########################

        # Create the label for the diode frame (outside the frame)
        self.laser_label = QtWidgets.QLabel(self.controlsWidget)
        self.laser_label.setObjectName("laser_label")
        self.grid_layout.addWidget(self.laser_label, 4, 0, 1, 5)

        # Create a frame for laser control (spinbox, slider, buttons)
        self.laserControlFrame = QFrame(self.controlsWidget)
        self.laserControlFrame.setFrameShape(QFrame.StyledPanel)
        self.laserControlFrame.setFrameShadow(QFrame.Sunken)
        self.laserControlFrame.setLineWidth(2)
        self.laserControlFrame.setStyleSheet(FRAME_STYLE)
        self.laserControlLayout = QtWidgets.QVBoxLayout(self.laserControlFrame)

        # Current label, slider and spinbox (horizontal layout)
        self.currentLayout = QtWidgets.QHBoxLayout()

        self.current_slider_label = QtWidgets.QLabel("Current", self.laserControlFrame)
        self.currentLayout.addWidget(self.current_slider_label)

        self.horizontalSlider = QtWidgets.QSlider(self.laserControlFrame)
        self.horizontalSlider.setOrientation(QtCore.Qt.Horizontal)
        self.horizontalSlider.setMinimum(0)
        self.horizontalSlider.setMaximum(MAX_CURRENT)
        self.horizontalSlider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.horizontalSlider.setTickInterval(100)
        self.currentLayout.addWidget(self.horizontalSlider)

        self.spinBox = QtWidgets.QSpinBox(self.laserControlFrame)
        self.spinBox.setMaximum(MAX_CURRENT)
        self.spinBox.setSingleStep(50)
        self.spinBox.setObjectName("spinBox")
        self.spinBox.setSuffix(" mA")
        self.spinBox.setMinimumWidth(100)

        #When a value is changed in the spinbox or in the slider, the current is changed
        self.spinBox.valueChanged.connect(self.sendCurrentToInstrument)
        self.horizontalSlider.valueChanged.connect(self.sendCurrentToInstrument)

        self.currentLayout.addWidget(self.spinBox)
        self.laserControlLayout.addLayout(self.currentLayout)

        # OFF and ON buttons (second line)
        self.buttonLayout = QtWidgets.QHBoxLayout()

        self.OFF_button = QtWidgets.QPushButton("OFF", self.laserControlFrame)
        self.OFF_button.setStyleSheet("background-color:rgb(255, 0, 0); color: white;")
        self.OFF_button.clicked.connect(self.turnOffLaser)
        self.buttonLayout.addWidget(self.OFF_button)

        self.ON_button = QtWidgets.QPushButton("ON", self.laserControlFrame)
        self.ON_button.setStyleSheet("background-color: rgb(85, 170, 0); color: white;")
        self.ON_button.clicked.connect(self.turnOnLaser)
        self.buttonLayout.addWidget(self.ON_button)

        self.laserControlLayout.addLayout(self.buttonLayout)

        self.laserControlLayout.addSpacing(20)

        # Timed Illumination row
        self.timed_illumination_layout = QtWidgets.QHBoxLayout()

        self.timed_illumination_label = QtWidgets.QLabel("Timed Illumination:", self.laserControlFrame)
        self.timed_illumination_layout.addWidget(self.timed_illumination_label)

        self.timed_illumination_spinbox = QtWidgets.QSpinBox(self.laserControlFrame)
        self.timed_illumination_spinbox.setRange(0, 5000)
        self.timed_illumination_spinbox.setValue(300)
        self.timed_illumination_spinbox.setSuffix(" s")
        self.timed_illumination_layout.addWidget(self.timed_illumination_spinbox)

        self.TIMED_button = QtWidgets.QPushButton("SET TIMER", self.laserControlFrame)
        self.TIMED_button.clicked.connect(self.askForDuration)
        self.TIMED_button.setStyleSheet("background-color: rgb(255, 170, 0); color: white;")
        self.timed_illumination_layout.addWidget(self.TIMED_button)

        self.laserControlLayout.addLayout(self.timed_illumination_layout)

        self.grid_layout.addWidget(self.laserControlFrame, 5, 0, 1, 5)




        ######################## ELLIPTEC ########################

        # Create the label for the Elliptec frame (outside the frame)
        self.elliptec_label = QtWidgets.QLabel(self.controlsWidget)
        self.elliptec_label.setObjectName("elliptec_label")
        self.grid_layout.addWidget(self.elliptec_label, 6, 0, 1, 5)

        # Create a frame for the Elliptec connection controls
        self.elliptecFrame = QFrame(self.controlsWidget)
        self.elliptecFrame.setFrameShape(QFrame.StyledPanel)
        self.elliptecFrame.setFrameShadow(QFrame.Sunken)
        self.elliptecFrame.setLineWidth(2)
        self.elliptecFrame.setStyleSheet(FRAME_STYLE)

        # Overall (vertical) layout for the Elliptec frame: COM row, log, position row
        self.elliptecFrameLayout = QtWidgets.QVBoxLayout(self.elliptecFrame)

        # --- COM port / connect row ---
        self.elliptecLayout = QtWidgets.QHBoxLayout()

        self.ell_com_label = QtWidgets.QLabel("COM port:", self.elliptecFrame)
        self.elliptecLayout.addWidget(self.ell_com_label)

        # COM port entry (leave blank to auto-detect)
        self.ell_com_edit = QLineEdit(self.elliptecFrame)
        self.ell_com_edit.setObjectName("ell_com_edit")
        self.ell_com_edit.setPlaceholderText("e.g. COM5 (blank = auto)")
        self.ell_com_edit.setMaximumWidth(160)
        self.elliptecLayout.addWidget(self.ell_com_edit)

        self.ell_connect_button = QtWidgets.QPushButton("Connect", self.elliptecFrame)
        self.ell_connect_button.setObjectName("ell_connect_button")
        self.ell_connect_button.clicked.connect(self.connectElliptec)
        self.elliptecLayout.addWidget(self.ell_connect_button)

        self.ell_status_label = QtWidgets.QLabel(self.elliptecFrame)
        self.ell_status_label.setObjectName("ell_status_label")
        self.ell_status_label.setMinimumWidth(160)
        self.elliptecLayout.addWidget(self.ell_status_label)

        self.elliptecFrameLayout.addLayout(self.elliptecLayout)

        # --- Log box, directly under the COM row ---
        self.ell_log = QtWidgets.QPlainTextEdit(self.elliptecFrame)
        self.ell_log.setObjectName("ell_log")
        self.ell_log.setReadOnly(True)
        self.ell_log.setMaximumHeight(90)
        self.ell_log.setStyleSheet("QPlainTextEdit { background-color: rgb(30, 30, 30); color: rgb(200, 200, 200); font-family: Consolas, monospace; font-size: 9pt; }")
        self.elliptecFrameLayout.addWidget(self.ell_log)

        # --- Position control row ---
        self.elliptecPositionLayout = QtWidgets.QHBoxLayout()

        self.ell_pos1_button = QtWidgets.QPushButton("Position 1 (Home)", self.elliptecFrame)
        self.ell_pos1_button.setObjectName("ell_pos1_button")
        self.ell_pos1_button.clicked.connect(lambda: self.moveElliptecToPosition(1))
        self.elliptecPositionLayout.addWidget(self.ell_pos1_button)

        self.ell_pos2_button = QtWidgets.QPushButton("Position 2", self.elliptecFrame)
        self.ell_pos2_button.setObjectName("ell_pos2_button")
        self.ell_pos2_button.clicked.connect(lambda: self.moveElliptecToPosition(2))
        self.elliptecPositionLayout.addWidget(self.ell_pos2_button)

        self.ell_position_label = QtWidgets.QLabel("Position: --", self.elliptecFrame)
        self.ell_position_label.setObjectName("ell_position_label")
        self.elliptecPositionLayout.addWidget(self.ell_position_label)

        self.elliptecFrameLayout.addLayout(self.elliptecPositionLayout)

        # Initialize as disconnected (also disables the position buttons)
        self.setElliptecStatus(connected=False)

        self.grid_layout.addWidget(self.elliptecFrame, 7, 0, 1, 5)

        # Push all the sections to the top
        self.grid_layout.setRowStretch(8, 1)




        ######################## PLOT ########################

        # Matplotlib canvas on the right side
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.main_layout.addWidget(self.canvas, stretch=1)
        self.canvas.mpl_connect("motion_notify_event", self.on_motion)



        SLMcontroller.setCentralWidget(self.centralwidget)

        # Status bar
        self.statusbar = QtWidgets.QStatusBar(SLMcontroller)
        self.statusbar.setObjectName("statusbar")
        SLMcontroller.setStatusBar(self.statusbar)



        #Connection between the spinbox and the slider
        self.retranslateUi(SLMcontroller)
        self.horizontalSlider.valueChanged['int'].connect(self.spinBox.setValue)  # type: ignore
        self.spinBox.valueChanged['int'].connect(self.horizontalSlider.setValue)  # type: ignore
        QtCore.QMetaObject.connectSlotsByName(SLMcontroller)


        #Get the current current of the controller and set it to that value.
        self.spinBox.setValue(int(float(self.laser.get_current().replace('\n',''))*1000.)) #Set current value of current from the controller (if you meddled with it before)



        # Timer for countdown
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.updateCountdown)


    def retranslateUi(self, SLMcontroller):
        _translate = QtCore.QCoreApplication.translate
        SLMcontroller.setWindowTitle(_translate("SLMcontroller", "SLM controller"))
        self.minimize_label.setText(_translate("SLMcontroller", "<html><head/><body><p align=\"center\"><span style=\" font-weight:600;\">Minimize pattern</span></p></body></html>"))
        self.file_selection_label.setText(_translate("SLMcontroller", "<html><head/><body><p align=\"center\"><span style=\" font-weight:600;\">SLM pattern file</span></p></body></html>"))
        self.laser_label.setText(_translate("SLMcontroller", "<html><head/><body><p align=\"center\"><span style=\" font-weight:600;\">LED diode controller</span></p></body></html>"))
        self.elliptec_label.setText(_translate("SLMcontroller", "<html><head/><body><p align=\"center\"><span style=\" font-weight:600;\">Thorlabs Elliptec (ELL6B) filter mount</span></p></body></html>"))
        self.OFF_button.setText(_translate("SLMcontroller", "OFF"))
        self.TIMED_button.setText(_translate("SLMcontroller", "SET TIMED"))
        self.ON_button.setText(_translate("SLMcontroller", "ON"))
        self.pushButton.setText(_translate("SLMcontroller", "Show"))

        self.fileLine.setPlaceholderText(_translate("SLMcontroller", "Select the pattern you want to calculate for the SLM..."))
        self.calibrationLine.setPlaceholderText(_translate("SLMcontroller", "Select your calibration file."))
        self.minBit.setText(_translate("SLMcontroller", f"{DEFAULT_VALUES['min_bit']}"))
        self.maxBit.setText(_translate("SLMcontroller", f"{DEFAULT_VALUES['max_bit']}"))
        self.minAngle.setText(_translate("SLMcontroller", f"{DEFAULT_VALUES['min_angle']}"))
        self.maxAngle.setText(_translate("SLMcontroller", f"{DEFAULT_VALUES['max_angle']}"))
        self.lambdaLabel.setText(_translate("SLMcontroller", "<html><head/><body><p align=\"center\"><span style=\" font-weight:600;\">λ</span></p></body></html>"))
        self.lambdaLine.setText(_translate("SLMcontroller", f"{DEFAULT_VALUES['lamb']}"))
        self.saveFolderLabel.setText(_translate("SLMcontroller", f"{OPTIMIZED_STRUCTURES_FOLDER}"))
        self.nameOptimized.setPlaceholderText(_translate("SLMcontroller", "Optimized pattern name (without .npz)"))




    ######################## PLOTTING ########################

    def plotImages(self, images):
        """Plots a list of (data, title, label, vmin, vmax, cmap) next to each other on the canvas."""
        self.figure.clear()
        self.hover_images = {}

        for i, (data, title, label, vmin, vmax, cmap) in enumerate(images):
            ax = self.figure.add_subplot(1, len(images), i + 1)
            im = ax.imshow(data, vmin=vmin, vmax=vmax, cmap=cmap)
            cbar = self.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label(label, rotation=270, labelpad=15, fontsize=12)
            cbar.ax.tick_params(labelsize=12)
            ax.tick_params(axis='both', which='major', labelsize=12)
            ax.set_title(title, fontsize=16)
            self.hover_images[ax] = (data, label)

        self.figure.tight_layout()
        self.canvas.draw()  # Update the canvas

    def plotGraph(self):
        """Plots the wanted pattern (psi data)."""
        self.plotImages([(self.psi_data, "Wanted pattern", "Angle of the polarization", 0, 360, None)])

    def on_motion(self, event):
        """Shows the value under the cursor in the status bar."""
        if event.inaxes in self.hover_images and event.xdata is not None:
            data, label = self.hover_images[event.inaxes]
            x, y = int(event.xdata + 0.5), int(event.ydata + 0.5)  # Get the cursor's data coordinates
            if 0 <= x < data.shape[1] and 0 <= y < data.shape[0]:  # Check bounds
                self.statusbar.setStyleSheet("QStatusBar { font-weight: bold; color: red; font-size: 12pt; }")
                self.statusbar.showMessage(f"{label} : {data[y, x]:.2f}")
                return

        # Clear the status bar if out of bounds
        self.statusbar.clearMessage()




    ######################## SLM PATTERN FILE ########################

    def loadFilesToComboBox(self):
        self.current_directory = OPTIMIZED_STRUCTURES_FOLDER
        try:
            files = os.listdir(self.current_directory)
            files = [f for f in files if os.path.isfile(os.path.join(self.current_directory, f))]
        except OSError:
            print("Directory not found!")
            return

        # Add files to the comboBox
        self.comboBox.clear()
        self.comboBox.addItems(files)

    def loadSelectedFile(self):
        selected_file = self.comboBox.currentText()
        if selected_file:
            full_path = os.path.join(self.current_directory, selected_file)
            print(f"Selected file: {full_path}")

            # Load the optimized bits
            optdata = np.load(full_path)
            optbits = optdata['optimal_bits']

            self.psi_data = optdata['psi_wanted']

            rgbimg = self.cal.convert_to_RGB(optbits).astype(dtype=np.int8)[: ,:, :]
            # Update the SLM screen
            self.cal.slm.updateArray(rgbimg)

            # Update the plot
            self.plotGraph()

        else:
            QtWidgets.QMessageBox.warning(None, "No File Selected", "Please select a file from the dropdown.")




    ######################## MINIMIZER ########################

    def browse_pattern_directory(self):
        # Open the file selection dialog with a filter for .npy files
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            None,
            "Select a .npy File",
            PATTERNS_FOLDER,
            "Numpy Files (*.npy);;All Files (*)"
        )

        if file:
            # If a file is selected, update the lineEdit to show the file path
            self.fileLine.setText(file)
            print(f"\n Selected file: {file}")

            #Plot the selected file
            self.plotImages([(np.load(file), "Chosen pattern", "Angle of the polarization", 0, 360, 'plasma')])

        else:
            print("No file selected")

    def browse_calibration_directory(self):
        # Open the file selection dialog with a filter for .npz files
        file, _ = QtWidgets.QFileDialog.getOpenFileName(
            None,
            "Select a calibration info file",
            CALIBRATION_FOLDER,
            "NPZ Files (*.npz);;All Files (*)"
        )

        if file:
            # If a file is selected, update the calibration line
            self.calibrationLine.setText(file)
            print(f"\n Selected file: {file}")
        else:
            print("No file selected")

    def browse_save_directory(self):
        # Open the directory selection dialog with the default folder
        directory = QtWidgets.QFileDialog.getExistingDirectory(None, "Select Directory", OPTIMIZED_STRUCTURES_FOLDER)

        if directory:
            self.saveFolderLabel.setText(directory)
            print(f"\n Selected directory: {directory}")
        else:
            print("No directory selected")

    def remove_suffix(self):
        text = self.nameOptimized.text()

        if '.' in text:
           # Split the string at the dot and take everything except the last part
           text = '.'.join(text.split('.')[:-1])

        self.nameOptimized.clearFocus()
        self.nameOptimized.setText(text)
        print(f"\n Save file name:  {text}")

    def save_value_and_clear_focus(self, line, dtype=float, min_value=None, max_value=None, default_value=None):
        """Save the value, clear focus, and validate dtype with min/max constraints."""
        text = line.text()

        try:
            # If the dtype is int and you accidentally put in float, it can convert it to int, so you dont have an error.
            value = dtype(float(text))

            # Check min/max constraints
            if min_value is not None and value < min_value:
                raise ValueError(f"Value must be greater than or equal to {min_value}.")
            if max_value is not None and value > max_value:
                raise ValueError(f"Value must be less than or equal to {max_value}.")

            print(f"\n Saved Value: {value}")
            line.setText(str(value))

        except (ValueError, TypeError) as e:
            # If there was an error (invalid type or out of bounds), set the default value
            if default_value is not None:
                value = default_value
                self.show_error("Invalid input", f'Invalid input - out of range or wrong dtype. Enter the value of type {dtype} in the range [{min_value}, {max_value}]. Reverting to default value: {value}' )
                line.setText(str(value))

        line.clearFocus()

    def show_error(self, title, message):
        """Show an error dialog with the provided title and message."""
        QMessageBox.critical(None, title, message)

    def on_run_button_clicked(self):

        psi_wanted_loc  = self.fileLine.text()
        calib_info_loc = self.calibrationLine.text()

        # Check the inputs before starting the (long) minimization
        if not os.path.isfile(psi_wanted_loc):
            self.show_error("Invalid input", "Select the pattern (.npy) you want to minimize.")
            return
        if not os.path.isfile(calib_info_loc):
            self.show_error("Invalid input", "Select the calibration info file (.npz).")
            return
        if not self.nameOptimized.text().strip():
            self.show_error("Invalid input", "Enter the name of the optimized pattern.")
            return

        try:
            lamb = float(self.lambdaLine.text())
            bit_b = [int(self.minBit.text()), int(self.maxBit.text())]
            phase_b = [float(self.minAngle.text()), float(self.maxAngle.text())]
        except ValueError:
            self.show_error("Invalid input", "One or more inputs are invalid. Please ensure all fields are correctly filled.")
            return

        print("\n ################## VALUES ##################")
        print(f"Psi Wanted Location: {psi_wanted_loc}")
        print(f"Calibration Info Location: {calib_info_loc}")
        print(f"Lambda Value: {lamb}")
        print(f"Bit bounds: {bit_b}")
        print(f"Angle bounds: {phase_b}")
        print("###################################")

        self.worker = Worker(psi_wanted_loc=psi_wanted_loc,
                             calib_info_loc=calib_info_loc,
                             lamb=lamb,
                             bit_b=bit_b,
                             phase_b=phase_b)

        # Run the worker in its own thread, so the rest of the GUI keeps working
        self.thread = QtCore.QThread()
        self.worker.moveToThread(self.thread)

        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_task_finished)
        self.worker.error_signal.connect(self.on_task_error)

        self.thread.started.connect(self.worker.run)
        self.thread.start()

        # Only one minimization at a time
        self.runButton.setEnabled(False)
        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)
        self.statusbar.showMessage("Minimizing...")

    def update_progress(self, value):
        self.progressBar.setValue(value)

    def stop_worker_thread(self):
        """Stop the worker thread and reset the minimizer controls."""
        self.thread.quit()
        self.thread.wait()
        self.thread = None

        self.progressBar.setVisible(False)
        self.runButton.setEnabled(True)

    def on_task_error(self, message):
        self.stop_worker_thread()
        self.statusbar.showMessage("Minimization failed.")
        self.show_error("Minimization error", f"The minimization failed:\n{message}")

    def on_task_finished(self):
        self.stop_worker_thread()

        self.opt_savepath = Path(self.saveFolderLabel.text())/(self.nameOptimized.text() + '.npz')

        #Save the npz file with the optimal bits to the save location.
        np.savez(self.opt_savepath, psi_wanted=self.worker.psiwanted, optimal_bits = self.worker.result)
        print(f"Task finished. Saved to {self.opt_savepath}")
        self.statusbar.showMessage(f"Saved {self.opt_savepath}")

        # Refresh the pattern dropdown and select the new file, so you can send it to the SLM with "Show"
        self.loadFilesToComboBox()
        if Path(self.opt_savepath).parent == Path(self.current_directory):
            self.comboBox.setCurrentText(self.opt_savepath.name)

        ######## PLOT THE PSI WANTED FILE AND THE OPTIMIZED STRUCTURE #########
        self.plotImages([(self.worker.psiwanted, "Wanted pattern", "Angle of the polarization", 0, 360, 'plasma'),
                         (self.worker.result, "Optimal bits", "Bit", 0, 1023, 'viridis')])

        QMessageBox.information(None, "File Saved", f"The file has been saved at:\n{self.opt_savepath}\n\nIt is selected in the SLM pattern list - press \"Show\" to send it to the SLM.")




    ######################## TIMED ILLUMINATION ########################

    def askForDuration(self):
        """Ask for the duration and start the countdown."""
        # The Elliptec filter mount must be connected before a timed run can be started
        if self.ell is None:
            QMessageBox.warning(
                None,
                "No Instrument Connection",
                "Elliptec filter mount is not connected. Connect it before using timed mode."
            )
            return

        self.countdown = self.timed_illumination_spinbox.value()

        if self.countdown == 0:
            self.statusbar.showMessage("Please enter a valid duration greater than 0.")
            return

        reply = QMessageBox.question(
            None,
            "Confirmation",
            f"Proceed with timed illumination for {self.countdown} seconds? "
            f"The filter mount will move to position 2 for the duration, "
            f"then back to position 1.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:

            # Prevent starting another timed run while this one is active
            self.TIMED_button.setEnabled(False)

            # Move the filter mount to position 2 for the duration of the countdown
            self.moveElliptecToPosition(2)

            # Start the countdown
            self.timer.start(1000)  # 1 second intervals

            # Show the countdown message box with an Abort button
            self.timerMessageBox = QtWidgets.QMessageBox()
            self.timerMessageBox.setWindowTitle("Timed Illumination Countdown")
            self.timerMessageBox.setText(f"Timed illumination activated! Countdown: {self.countdown} seconds.")
            self.timerMessageBox.setIcon(QMessageBox.Information)

            self.abort_button = self.timerMessageBox.addButton("Abort", QMessageBox.RejectRole)

            self.timerMessageBox.setStandardButtons(QMessageBox.NoButton)
            self.timerMessageBox.show()

            self.abort_button.clicked.connect(self.abortCountdown)

    def abortCountdown(self):
        """Handles the abort button press to stop the countdown and reset the values."""
        self.timer.stop()

        # Move the filter mount back to position 1
        self.moveElliptecToPosition(1)

        # Re-enable the timed button (only if the mount is still connected)
        self.TIMED_button.setEnabled(self.ell is not None)

        self.timerMessageBox.close()

    def updateCountdown(self):
        """Updates the countdown every second and shows it in the message box."""
        self.countdown -= 1
        if self.countdown >= 0:
            self.timerMessageBox.setText(f"Filter mount at position 2. Countdown: {self.countdown} seconds.")
        else:
            self.timer.stop()

            # Move the filter mount back to position 1
            self.moveElliptecToPosition(1)

            # Re-enable the timed button (only if the mount is still connected)
            self.TIMED_button.setEnabled(self.ell is not None)

            self.timerMessageBox.setText("Illumination ended.")
            self.timerMessageBox.removeButton(self.abort_button)
            self.timerMessageBox.setStandardButtons(QMessageBox.Ok)




    ######################## ELLIPTEC ########################

    def logElliptec(self, message):
        """Append a timestamped line to the Elliptec log box."""
        timestamp = time.strftime("%H:%M:%S")
        self.ell_log.appendPlainText(f"[{timestamp}] {message}")
        # Keep the view scrolled to the latest entry
        self.ell_log.verticalScrollBar().setValue(self.ell_log.verticalScrollBar().maximum())

    def updateElliptecPositionDisplay(self, position):
        """Update the position label and highlight the button matching the current position in green."""
        active_style = "background-color: rgb(85, 170, 0); color: white;"

        self.ell_position_label.setText(f"Position: {position}")

        self.ell_pos1_button.setStyleSheet(active_style if position == 1 else "")
        self.ell_pos2_button.setStyleSheet(active_style if position == 2 else "")

    def setElliptecStatus(self, connected, port_name=None):
        """Update the status label/color for the Elliptec connection, and enable/disable position controls."""
        if connected:
            self.ell_status_label.setText(f"\u25CF Connected ({port_name})")
            self.ell_status_label.setStyleSheet("color: rgb(85, 170, 0); font-weight: bold;")
            self.ell_connect_button.setText("Reconnect")
        else:
            self.ell_status_label.setText("\u25CF Disconnected")
            self.ell_status_label.setStyleSheet("color: rgb(255, 0, 0); font-weight: bold;")
            self.ell_connect_button.setText("Connect")
            self.ell_position_label.setText("Position: --")
            self.ell_pos1_button.setStyleSheet("")
            self.ell_pos2_button.setStyleSheet("")

        self.ell_pos1_button.setEnabled(connected)
        self.ell_pos2_button.setEnabled(connected)
        # Timed mode drives the filter mount, so it requires a connection
        self.TIMED_button.setEnabled(connected)

    def connectElliptec(self):
        """Connect (or reconnect) to the Thorlabs ELL6B filter mount on the given COM port."""
        requested_port = self.ell_com_edit.text().strip()
        port = requested_port if requested_port else None

        # If already connected, close the existing connection first (reconnect / switch port)
        if self.ell is not None:
            self.logElliptec("Closing existing connection...")
            try:
                self.ell.close()
            except Exception:
                pass
            self.ell = None
            self.setElliptecStatus(connected=False)

        self.ell_connect_button.setEnabled(False)
        port_desc = port if port else "auto-detect"
        self.logElliptec(f"Connecting on {port_desc}...")
        self.statusbar.showMessage("Connecting to Elliptec filter mount...")
        QtWidgets.QApplication.processEvents()

        try:
            self.ell = ELL6Bmanager(port=port)
            self.setElliptecStatus(connected=True, port_name=self.ell.port_name)

            #Move it to the default position
            position = 1
            self.moveElliptecToPosition(position)

            self.updateElliptecPositionDisplay(position)
            self.logElliptec(f"Connected on {self.ell.port_name}. Current position: {position}.")
            self.statusbar.showMessage(f"Elliptec connected on {self.ell.port_name}")
        except Exception as e:
            self.ell = None
            self.setElliptecStatus(connected=False)
            self.logElliptec(f"ERROR: connection failed - {str(e)}")
            self.statusbar.showMessage("Failed to connect to Elliptec filter mount.")
            QMessageBox.critical(None, "Elliptec Connection Error", f"Failed to connect to the ELL6B:\n{str(e)}")
        finally:
            self.ell_connect_button.setEnabled(True)

    def moveElliptecToPosition(self, position):
        """Move the ELL6B filter mount to logical position 1 or 2."""
        if self.ell is None:
            QMessageBox.warning(None, "No Instrument Connection", "Elliptec filter mount is not connected.")
            return

        self.ell_pos1_button.setEnabled(False)
        self.ell_pos2_button.setEnabled(False)
        self.logElliptec(f"Moving to position {position}...")
        self.statusbar.showMessage(f"Moving Elliptec filter mount to position {position}...")
        QtWidgets.QApplication.processEvents()

        try:
            self.ell.set_position(position)
            # Use the manager's get_position() function to confirm the actual hardware position
            reached_position = self.ell.get_position()
            self.updateElliptecPositionDisplay(reached_position)
            self.logElliptec(f"Reached position {reached_position}.")
            self.statusbar.showMessage(f"Elliptec filter mount at position {reached_position}")
        except Exception as e:
            self.logElliptec(f"ERROR: move failed - {str(e)}")
            self.statusbar.showMessage("Failed to move Elliptec filter mount.")
            QMessageBox.critical(None, "Elliptec Move Error", f"Failed to move the ELL6B:\n{str(e)}")
        finally:
            self.ell_pos1_button.setEnabled(True)
            self.ell_pos2_button.setEnabled(True)




    ######################## LED DIODE ########################

    def turnOffLaser(self):
        # Set the OFF button to blue background with yellow text when clicked
        self.OFF_button.setStyleSheet("background-color: rgb(0, 0, 255); color: rgb(255, 255, 0);")
        # Keep the ON button's original color (green background with white text)
        self.ON_button.setStyleSheet("background-color: rgb(85, 170, 0); color: white;")

        #Turn the laser off
        self.laser.ld_off()

    def turnOnLaser(self):
        # Set the ON button to blue background with yellow text when clicked
        self.ON_button.setStyleSheet("background-color: rgb(0, 0, 255); color: rgb(255, 255, 0);")
        # Keep the OFF button's original color (red background with white text)
        self.OFF_button.setStyleSheet("background-color: rgb(255, 0, 0); color: white;")

        #Turn the laser on
        self.laser.ld_on()

    def sendCurrentToInstrument(self, value):
        """Send the current value from the SpinBox to the instrument."""
        if self.laser is not None:
            try:
                self.laser.set_current(value/1000) #Tu nujno faktor 1000!!!! Ker imaš mA
                self.statusbar.showMessage(f"Current set to {value} mA")
            except visa.VisaIOError as e:
                QMessageBox.critical(None, "Communication Error", f"Failed to send current value: {str(e)}")
        else:
            QMessageBox.warning(None, "No Instrument Connection", "Instrument is not connected.")






# Main block to run the app
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    SLMcontroller = QtWidgets.QMainWindow()
    ui = Ui_SLMcontroller()
    ui.setupUi(SLMcontroller)

    # Ensure the program exits when the main window is closed
    app.aboutToQuit.connect(app.quit)

    SLMcontroller.show()
    sys.exit(app.exec_())
