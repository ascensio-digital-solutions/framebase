import torch
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import numpy as np

device = "mps" if torch.backends.mps.is_available() else "cpu"
print("Device:", device)
model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device)
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

img = Image.fromarray(np.zeros((224, 224, 3), dtype=np.uint8))
inputs = processor(images=img, return_tensors="pt").to(device)
with torch.no_grad():
    image_features = model.get_image_features(**inputs)
    print("Features shape:", image_features.shape)
