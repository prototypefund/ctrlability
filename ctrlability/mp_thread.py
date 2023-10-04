from ctrlability.landmark_processing.face import FaceLandmarkProcessing
from ctrlability.landmark_processing.hand import HandLandmarkProcessing
from ctrlability.video.source import VideoSource
from ctrlability.mousectrl import MouseCtrl
from ctrlability.roi_processing import RoiProcessing
from PySide6.QtCore import Signal, QObject, Slot
from PySide6.QtGui import QImage
import mediapipe as mp
import time
import logging as log
import numpy as np


class MediaPipeThread(QObject):
    started = Signal()
    finished = Signal()
    signalFrame = Signal(QImage, int)

    def __init__(self, camera_id=0, name="mp_thread"):
        super().__init__()
        self.camera_id = camera_id
        self.name = name
        self.webcam_source = VideoSource(camera_id, 640, 480)
        # local state variables
        self.is_keeping_mouth_open = False

        self.process_times_running_sum = 0
        self.process_times_count = 0

        self._continue_processing = True
        self.tracking_state = False

        self.selected_mp_model = "Face"
        self.break_loop = False
        self.roi_processing = RoiProcessing(self.webcam_source.width, self.webcam_source.height)
        self.triggered_roi_index = -1

    def change_camera(self, camera_id):
        self.camera_id = camera_id
        self.webcam_source.change_camera(camera_id)

    def process(self):
        self.started.emit()

        # initialize Qimage for color conversion outside of loop to improve performance
        probe_frame_rgb = self.webcam_source.get_probe_frame()
        height, width, channel = probe_frame_rgb.shape
        bytesPerLine = 3 * width
        qImg = QImage(width, height, QImage.Format_RGB888)
        img_data = np.frombuffer(qImg.bits(), np.uint8).reshape((qImg.height(), qImg.width(), 3))

        while True:
            if self.selected_mp_model == "Face":
                with mp.solutions.face_mesh.FaceMesh(
                    min_detection_confidence=0.5, min_tracking_confidence=0.5, static_image_mode=False, max_num_faces=1
                ) as face_mesh:
                    for frame_rgb in self.webcam_source:
                        if self.break_loop == True:
                            self.break_loop = False
                            break
                        if self._continue_processing:
                            current_time = time.time() * 1000  # convert to ms

                            results = face_mesh.process(frame_rgb)
                            if results.multi_face_landmarks:
                                # Only process the first detected face
                                face_landmarks = results.multi_face_landmarks[0]

                                face = FaceLandmarkProcessing(frame_rgb, face_landmarks)
                                face.draw_landmarks()  # TODO: refactor drawing out of landmark processing

                                self.triggered_roi_index = self.roi_processing.check_collision(face_landmarks)

                                if self.tracking_state:
                                    self.handle_mouse_events(face)

                            # convert frame to QImage
                            np.copyto(img_data, frame_rgb)

                            time_taken = time.time() * 1000 - current_time
                            self.process_times_running_sum += time_taken
                            self.process_times_count += 1

                            self.signalFrame.emit(qImg, self.triggered_roi_index)
                            self.triggered_roi_index = -1

            elif self.selected_mp_model == "Hands":
                with mp.solutions.hands.Hands(
                    min_detection_confidence=0.5, min_tracking_confidence=0.5, static_image_mode=False
                ) as hands:
                    for frame_rgb in self.webcam_source:
                        if self.break_loop:
                            self.break_loop = False
                            break
                        results = hands.process(frame_rgb)

                        if results.multi_hand_landmarks:
                            for hand_landmarks in results.multi_hand_landmarks:
                                hand = HandLandmarkProcessing(frame_rgb, hand_landmarks)
                                hand.draw_landmarks()
                                self.triggered_roi_index = self.roi_processing.check_collision(hand_landmarks)

                        # convert frame to QImage
                        np.copyto(img_data, frame_rgb)

                        self.signalFrame.emit(qImg, self.triggered_roi_index)
                        self.triggered_roi_index = -1

            self.finished.emit()

    def handle_mouse_events(self, face):
        if not MouseCtrl.is_mouse_frozen:
            MouseCtrl.move_mouse(face.get_direction())

        if face.is_mouth_open():
            current_time = time.time() * 1000  # convert to ms

            # lets freeze the mouse position when the mouth is open to prevent
            # accidental mouse movement
            MouseCtrl.freeze_mouse_pos()

            first_time_open = self.is_keeping_mouth_open == False and MouseCtrl.left_click_count == 0
            if first_time_open:
                MouseCtrl.left_click()
                self.is_keeping_mouth_open = True

            mouth_open_time = current_time - MouseCtrl.last_left_click_ms
            is_long_open = mouth_open_time > 500
            is_already_clicked = MouseCtrl.left_click_count == 1
            log.debug(
                f"Mouth open time: {mouth_open_time}ms, is_long_open: {is_long_open}, is_already_clicked: {is_already_clicked}"
            )
            if is_long_open and is_already_clicked:
                MouseCtrl.double_click()
                MouseCtrl.release_left_click()
        else:
            self.is_keeping_mouth_open = False
            MouseCtrl.unfreeze_mouse_pos()
            MouseCtrl.release_left_click()

        if face.is_mouth_small():
            is_already_right_clicked = MouseCtrl.is_right_mouse_clicked == True
            if not is_already_right_clicked:
                MouseCtrl.right_click()
        else:
            MouseCtrl.release_right_click()

    def handle_cam_index_change(self, camera_id):
        self.camera_id = camera_id
        self.webcam_source.change_camera(camera_id)

    def handle_tracking_state_change(self, is_tracking_enabled):
        self.tracking_state = is_tracking_enabled
        # ToDO change implemetation of MouseCtrl.set_tracking_mode(True) will be never called
        if is_tracking_enabled:
            MouseCtrl.set_cursor_center()

    def handle_cam_resolution_index_change(self, resolution_index):
        self.webcam_source.change_resolution(resolution_index)

    def handle_model_changed(self, name):
        self.break_loop = True
        self.selected_mp_model = name

    def handle_add_roi(self, roi):
        self.roi_processing.add_roi(roi)

    def terminate(self):
        log.debug(
            f"Average processing time on {self.name}: {self.process_times_running_sum / self.process_times_count if self.process_times_count else 0}ms"
        )

    def pause(self):
        self._continue_processing = False

    def resume(self):
        self._continue_processing = True
