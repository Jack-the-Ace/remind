import time
import cv2
import mediapipe as np

from pathlib import Path
from urllib.request import urlretrieve
model_url= "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
