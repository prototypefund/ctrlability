import mediapipe as mp

from ctrlability.core import Processor, MappingEngine, bootstrapper
from ctrlability.core.data_types import FrameData, LandmarkData


@bootstrapper.add()
class PoseLandmarkProcessor(Processor):
    def __init__(self, mapping_engine: MappingEngine):
        super().__init__(mapping_engine)

        self.pose_mesh = mp.solutions.pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)

    def compute(self, data: FrameData):
        results = self.pose_mesh.process(data.frame)

        if results.pose_landmarks:
            pose_landmarks = results.pose_landmarks
            return LandmarkData(pose_landmarks.landmark, data.width, data.height)
