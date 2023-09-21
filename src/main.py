import sys
import mediapipe as mp
import time
import pyautogui

from PySide6.QtGui import (
    QImage,
    QPixmap,
    QKeySequence,
    QIcon,
    QShortcut,
    QAction,
)
from PySide6.QtCore import QTimer, QThread, Signal, Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
    QSlider,
    QWidget,
    QMenuBar,
    QMenu,
    QSystemTrayIcon,
    QComboBox,
)
from qt_material import apply_stylesheet, list_themes

from MouseControl import MouseCtrl
from FaceLandmarkProcessing import FaceLandmarkProcessing
from VideoSource import VideoSource
import VideoSourceProvider

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.0
pyautogui.DARWIN_CATCH_UP_TIME = 0.00

mp_holistic = mp.solutions.holistic


class SystemTrayApp(QSystemTrayIcon):
    def __init__(self, icon, parent=None):
        super(SystemTrayApp, self).__init__(icon, parent)
        self.setToolTip("Virtual Keyboard Access")

        # Create the menu
        self.menu = QMenu(parent)

        # Create an action for opening the virtual keyboard
        self.open_keyboard_action = QAction("Open Virtual Keyboard", self)
        self.open_keyboard_action.triggered.connect(self.open_virtual_keyboard)

        # Add the action to the menu
        self.menu.addAction(self.open_keyboard_action)

        # Add a quit action to the menu
        self.quit_action = QAction("Quit", self)
        self.quit_action.triggered.connect(app.quit)
        self.menu.addAction(self.quit_action)

        # Set the context menu for the system tray
        self.setContextMenu(self.menu)

    def open_virtual_keyboard(self):
        # Code to open the virtual keyboard
        print("Virtual Keyboard opened!")


class MediaPipeThread(QThread):
    signalFrame = Signal(QImage)

    def __init__(self, camera_id=0):
        super().__init__()
        self.camera_id = camera_id

        self.webcam_source = VideoSource(camera_id, 1280, 720)

    def run(self):
        holistic = mp.solutions.holistic.Holistic()

        self.mouseCtrl = MouseCtrl()
        self.mouseCtrl.last_left_click_ms = 0
        self.mouseCtrl.set_center()

        with mp_holistic.Holistic(
            min_detection_confidence=0.5, min_tracking_confidence=0.5
        ) as holistic:
            for frame_rgb in self.webcam_source:
                results = holistic.process(frame_rgb)

                if results.face_landmarks is not None:
                    face = FaceLandmarkProcessing(frame_rgb, results.face_landmarks)
                    face.draw_landmarks()

                    if MouseCtrl.AUTO_MODE == True:
                        if self.mouseCtrl.frozen_mouse_pos == False:
                            # mouseCtrl.check_mouse_on_screen()
                            self.mouseCtrl.move_mouse(face.get_direction())

                        if face.is_mouth_open():
                            current_time = time.time() * 1000  # convert to ms

                            if self.mouseCtrl.frozen_mouse_pos == False:
                                self.mouseCtrl.frozen_mouse_pos = True

                            if (
                                FaceLandmarkProcessing.mouth_open_state == False
                                and self.mouseCtrl.mouse_left_clicks == 0
                            ):
                                self.mouseCtrl.left_click()
                                self.mouseCtrl.last_left_click_ms = current_time
                                self.mouseCtrl.mouse_left_clicks = 1
                                FaceLandmarkProcessing.mouth_open_state = True

                            if (
                                FaceLandmarkProcessing.mouth_open_state == True
                                and self.mouseCtrl.mouse_left_clicks == 1
                                and (current_time - self.mouseCtrl.last_left_click_ms)
                                > 500
                            ):
                                self.mouseCtrl.double_click()
                                self.mouseCtrl.last_left_click_ms = time.time() * 1000
                                self.mouseCtrl.mouse_left_clicks = 0
                        else:
                            FaceLandmarkProcessing.mouth_open_state = False
                            self.mouseCtrl.mouse_left_clicks = 0
                            self.mouseCtrl.frozen_mouse_pos = False

                        if face.is_mouth_small():
                            if self.mouseCtrl.right_mouse_clicked == False:
                                self.mouseCtrl.right_click()
                        else:
                            self.mouseCtrl.right_mouse_clicked = False

                # source.show(frame)
                height, width, channel = frame_rgb.shape
                bytesPerLine = 3 * width
                qImg = QImage(
                    frame_rgb.data, width, height, bytesPerLine, QImage.Format_RGB888
                )

                self.signalFrame.emit(qImg)

        holistic.close()
        self.source.release()

    def change_camera(self, camera_id):
        self.camera_id = camera_id
        self.webcam_source.change_camera(camera_id)


class MediaPipeApp(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app  # Store the QApplication reference here

        self.setWindowTitle("CTRLABILITY")
        # Setup Menu Bar
        self.setupMenuBar()
        self.mouseCtrl = MouseCtrl()

        self.initUI()

    def initUI(self):
        main_layout = QHBoxLayout()

        # Webcam display area (equivalent to BorderLayout::Center)
        self.label = QLabel(self)
        main_layout.addWidget(self.label)

        # Settings area (equivalent to BorderLayout::East)
        settings_layout = QVBoxLayout()

        # Create a QVBoxLayout for the buttons, labels, and sliders
        grouped_layout = QVBoxLayout()

        # Create a QComboBox to liste the connected webcames
        self.webcam_combo_box = QComboBox(self)
        webcam_dict = VideoSourceProvider.get_available_vidsources()
        for key, value in webcam_dict.items():
            self.webcam_combo_box.addItem(value)
        self.webcam_combo_box.setFixedWidth(250)
        grouped_layout.addWidget(self.webcam_combo_box)

        # Connect the activated signal to our custom slot
        self.webcam_combo_box.currentIndexChanged.connect(self.on_select_camsource)

        # Create the checkbox
        self.tracking_checkbox = QCheckBox("Tracking", self)
        # Connect the checkbox's state change signal to the callback
        self.tracking_checkbox.stateChanged.connect(self.tracking_callback)
        grouped_layout.addWidget(self.tracking_checkbox)

        # Create a shortcut for the 'T' key
        self.shortcut = QShortcut(QKeySequence(Qt.Key_T), self)
        self.shortcut.activated.connect(self.toggle_tracking_by_shortcut)

        # Adding buttons to the grouped layout
        self.buttons = []
        for i in range(4):
            btn = QPushButton(f"Button {i+1}", self)
            self.buttons.append(btn)
            grouped_layout.addWidget(btn)

        # Adding labels and sliders just below the buttons
        self.sliders = []
        for i in range(4):
            lbl = QLabel(f"Slider {i+1}", self)
            slider = QSlider(Qt.Horizontal, self)
            slider.valueChanged.connect(
                self.slider_callback
            )  # Connect the callback to valueChanged signal
            self.sliders.append(slider)
            grouped_layout.addWidget(lbl)
            grouped_layout.addWidget(slider)

        # Add the grouped layout to settings layout
        settings_layout.addLayout(grouped_layout)

        # Push the remaining space to the bottom
        settings_layout.addStretch()

        main_layout.addLayout(settings_layout)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Use a QTimer to delay the centering by 2000 milliseconds
        QTimer.singleShot(2000, self.center_on_screen)

        # Start the MediaPipe processing thread.
        self.thread = MediaPipeThread()
        self.thread.signalFrame.connect(self.update_frame)
        self.thread.start()

    def setupMenuBar(self):
        menubar = QMenuBar(self)
        self.setMenuBar(menubar)

        themeMenu = QMenu("Themes", self)
        menubar.addMenu(themeMenu)

        for theme in list_themes():
            themeMenu.addAction(
                theme, lambda theme_name=theme: self.applyTheme(theme_name)
            )

    def applyTheme(self, theme_name):
        apply_stylesheet(self.app, theme=theme_name)  # apply the chosen theme

    def center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()  # Get screen geometry
        window = self.geometry()  # Get window geometry
        self.move(
            (screen.width() - window.width()) / 2,
            (screen.height() - window.height()) / 2,
        )

    @Slot(int)
    def on_select_camsource(self, index):
        """Slot that is called when an item in the QComboBox is selected."""
        print(f"Selected index: {index}")
        self.thread.change_camera(index)

    def tracking_callback(self, state):
        if state == 0:
            print("Tracking is off.")
            MouseCtrl.AUTO_MODE = False

        elif state == 2:
            print("Tracking is on.")
            MouseCtrl.AUTO_MODE = True
            pyautogui.moveTo(pyautogui.size()[0] / 2, pyautogui.size()[1] / 2)

    def toggle_tracking_by_shortcut(self):
        current_state = self.tracking_checkbox.isChecked()
        self.tracking_checkbox.setChecked(not current_state)

    def slider_callback(self, value):
        sender = self.sender()  # Find out which slider sent the signal
        index = self.sliders.index(sender) + 1  # Get the slider number (1-based)
        print(f"Slider {index} value changed to: {value}")

    def update_frame(self, qImg):
        pixmap = QPixmap.fromImage(qImg)
        self.label.setPixmap(pixmap)

    def closeEvent(self, event):
        self.thread.terminate()
        event.accept()


if __name__ == "__main__":
    # ToDo: fix in deployment: currently development hack to show application name in menu bar
    if sys.platform == "darwin":
        from Foundation import NSBundle

        app_info = NSBundle.mainBundle().infoDictionary()
        app_info["CFBundleName"] = "CTRLABILITY"

    app = QApplication(sys.argv)
    app.setApplicationName("CTRLABILITY")  # Set the application name
    # setup stylesheet
    apply_stylesheet(app, theme="light_blue.xml")

    # Ensure the app doesn't exit when the window is closed
    app.setQuitOnLastWindowClosed(False)

    # Setup the system tray icon
    # icon = QIcon("./assets/minimize.png")  # Replace with the path to your icon
    # tray = SystemTrayApp(icon)
    # tray.show()

    mainWin = MediaPipeApp(app)
    mainWin.show()
    sys.exit(app.exec())
