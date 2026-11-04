from transformers import pipeline
from PIL import Image
import numpy as np

classifier = pipeline("image-classification", model="Falconsai/nsfw_image_detection")
img = Image.fromarray(np.zeros((224, 224, 3), dtype=np.uint8))
print(classifier(img))
