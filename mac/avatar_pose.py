from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Point2D:
    x: float = 0.0
    y: float = 0.0
    confidence: float = 0.0
    visible: bool = False


@dataclass
class AvatarPose:
    timestamp: float = 0.0

    nose: Point2D = field(default_factory=Point2D)

    left_shoulder: Point2D = field(default_factory=Point2D)
    right_shoulder: Point2D = field(default_factory=Point2D)
    left_elbow: Point2D = field(default_factory=Point2D)
    right_elbow: Point2D = field(default_factory=Point2D)
    left_wrist: Point2D = field(default_factory=Point2D)
    right_wrist: Point2D = field(default_factory=Point2D)

    left_hip: Point2D = field(default_factory=Point2D)
    right_hip: Point2D = field(default_factory=Point2D)
    left_knee: Point2D = field(default_factory=Point2D)
    right_knee: Point2D = field(default_factory=Point2D)
    left_ankle: Point2D = field(default_factory=Point2D)
    right_ankle: Point2D = field(default_factory=Point2D)

    def all_joints(self) -> List[tuple]:
        return [
            ("nose", self.nose),
            ("left_shoulder", self.left_shoulder),
            ("right_shoulder", self.right_shoulder),
            ("left_elbow", self.left_elbow),
            ("right_elbow", self.right_elbow),
            ("left_wrist", self.left_wrist),
            ("right_wrist", self.right_wrist),
            ("left_hip", self.left_hip),
            ("right_hip", self.right_hip),
            ("left_knee", self.left_knee),
            ("right_knee", self.right_knee),
            ("left_ankle", self.left_ankle),
            ("right_ankle", self.right_ankle),
        ]
