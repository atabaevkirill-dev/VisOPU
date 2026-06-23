"""Custom PyQt6 widgets for VisOPU."""
from app.widgets.collapsible import CollapsiblePanel
from app.widgets.sliding_panel import SlidingPanel
from app.widgets.direction_pad import DirectionPad
from app.widgets.speed_control import SpeedControl
from app.widgets.camera_widget import CameraWidget, HAS_CV2
from app.widgets.map_widget import YandexMapWidget
from app.widgets.dashboard import ArcGauge, DashboardWidget

__all__ = [
    "CollapsiblePanel", "SlidingPanel", "DirectionPad", "SpeedControl",
    "CameraWidget", "HAS_CV2", "YandexMapWidget", "ArcGauge", "DashboardWidget",
]
